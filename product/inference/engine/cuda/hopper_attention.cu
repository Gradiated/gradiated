#include "gradiated/engine/attention.h"

#include <cuda_bf16.h>
#include <cuda_runtime.h>

#include <cute/tensor.hpp>
#include <cutlass/bfloat16.h>

#include <cstdint>
#include <stdexcept>
#include <string>

namespace gradiated::engine {
namespace {

using namespace cute;
using Element = cutlass::bfloat16_t;
using KeyLayout = decltype(tile_to_shape(
    GMMA::Layout_K_SW128_Atom<Element>{}, make_shape(Int<64>{}, Int<512>{})));
using QueryLayout = decltype(tile_to_shape(
    GMMA::Layout_K_SW128_Atom<Element>{}, make_shape(Int<8>{}, Int<512>{})));
using GlobalQkMma = decltype(make_tiled_mma(
    SM90_64x8x16_F32BF16BF16_SS<GMMA::Major::K, GMMA::Major::K>{}));
using GlobalKeyCopy = decltype(make_tiled_copy(
    Copy_Atom<SM80_CP_ASYNC_CACHEALWAYS<uint128_t>, Element>{},
    Layout<Shape<_16, _8>, Stride<_8, _1>>{}, Layout<Shape<_1, _8>>{}));
using ValueTileLayout = decltype(tile_to_shape(
    GMMA::Layout_MN_SW128_Atom<Element>{}, make_shape(Int<64>{}, Int<64>{})));
using ProbabilityLayout = decltype(tile_to_shape(
    GMMA::Layout_K_SW128_Atom<Element>{}, make_shape(Int<8>{}, Int<64>{})));
using ScoreLayout = Layout<Shape<_64, _8>, Stride<_8, _1>>;
using GlobalPvMma = decltype(make_tiled_mma(
    SM90_64x8x16_F32BF16BF16_SS<GMMA::Major::MN, GMMA::Major::K>{}));

struct alignas(128) GlobalQkSharedStorage {
  ArrayEngine<Element, cosize_v<KeyLayout>> keys;
  ArrayEngine<Element, cosize_v<QueryLayout>> queries;
};

struct alignas(128) GlobalAttentionTileSharedStorage {
  ArrayEngine<Element, cosize_v<KeyLayout>> keys;
  ArrayEngine<Element, cosize_v<QueryLayout>> queries;
  ArrayEngine<Element, cosize_v<ValueTileLayout>> values[8];
  ArrayEngine<Element, cosize_v<ProbabilityLayout>> probabilities;
  ArrayEngine<Element, cosize_v<ScoreLayout>> scores;
};

void check(cudaError_t result, const char* operation) {
  if (result != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(result));
  }
}

__device__ float warp_maximum(float value) {
  for (unsigned offset = 16; offset > 0; offset >>= 1U) {
    value = max(value, __shfl_down_sync(0xffffffffU, value, offset));
  }
  return __shfl_sync(0xffffffffU, value, 0);
}

__device__ float warp_total(float value) {
  for (unsigned offset = 16; offset > 0; offset >>= 1U) {
    value += __shfl_down_sync(0xffffffffU, value, offset);
  }
  return __shfl_sync(0xffffffffU, value, 0);
}

__global__ __launch_bounds__(128) void global_qk_wgmma_kernel(
    const Element* queries, const Element* keys, Element* scores,
    int kv_heads, int context_length, int tiles_per_block) {
  constexpr int tile_tokens = 64;
  constexpr int dimension = 512;
  constexpr int query_group = 8;
  const int tiles_per_head = context_length / tile_tokens;
  const int segments_per_head = tiles_per_head / tiles_per_block;
  const int head_segment = static_cast<int>(blockIdx.x);
  const int head = head_segment / segments_per_head;
  const int segment = head_segment - head * segments_per_head;
  const int first_tile = segment * tiles_per_block;
  const std::uint64_t query_base =
      static_cast<std::uint64_t>(head) * query_group * dimension;

  extern __shared__ __align__(128) unsigned char storage_bytes[];
  auto& storage = *reinterpret_cast<GlobalQkSharedStorage*>(storage_bytes);
  Tensor shared_keys = make_tensor(make_smem_ptr(storage.keys.begin()), KeyLayout{});
  Tensor shared_queries = make_tensor(make_smem_ptr(storage.queries.begin()), QueryLayout{});

  for (int index = static_cast<int>(threadIdx.x); index < query_group * dimension;
       index += static_cast<int>(blockDim.x)) {
    const int query = index / dimension;
    const int component = index - query * dimension;
    shared_queries(query, component) = queries[query_base + index];
  }
  GlobalKeyCopy key_copy;
  ThrCopy thread_copy = key_copy.get_slice(threadIdx.x);
  Tensor position_independent_keys = as_position_independent_swizzle_tensor(shared_keys);
  Tensor thread_shared_keys = thread_copy.partition_D(position_independent_keys);
  GlobalQkMma mma;
  ThrMMA thread_mma = mma.get_slice(threadIdx.x);
  Tensor fragment_keys = thread_mma.partition_A(shared_keys);
  Tensor fragment_queries = thread_mma.partition_B(shared_queries);
  for (int tile_offset = 0; tile_offset < tiles_per_block; ++tile_offset) {
    const int tile = first_tile + tile_offset;
    const std::uint64_t key_base =
        (static_cast<std::uint64_t>(head) * context_length + tile * tile_tokens) * dimension;
    Tensor global_keys = make_tensor(
        make_gmem_ptr(keys + key_base), make_shape(Int<64>{}, Int<512>{}),
        make_stride(Int<512>{}, Int<1>{}));
    Tensor thread_global_keys = thread_copy.partition_S(global_keys);
    copy(key_copy, thread_global_keys, thread_shared_keys);
    cp_async_fence();
    cp_async_wait<0>();
    __syncthreads();
    const std::uint64_t score_base =
        static_cast<std::uint64_t>(head) * query_group * context_length + tile * tile_tokens;
    Tensor global_scores = make_tensor(
        make_gmem_ptr(scores + score_base), make_shape(Int<64>{}, Int<8>{}),
        make_stride(Int<1>{}, context_length));
    Tensor fragment_global_scores = thread_mma.partition_C(global_scores);
    Tensor accumulators = thread_mma.make_fragment_C(fragment_global_scores);
    clear(accumulators);
    warpgroup_fence_operand(accumulators);
    warpgroup_arrive();
    cute::gemm(mma, fragment_keys, fragment_queries, accumulators);
    warpgroup_commit_batch();
    warpgroup_wait<0>();
    warpgroup_fence_operand(accumulators);
    copy(accumulators, fragment_global_scores);
    __syncthreads();
  }
}

__global__ __launch_bounds__(256) void global_attention_wgmma_tile_kernel(
    const Element* queries, const Element* keys, const Element* values, Element* output,
    int context_length) {
  constexpr int dimension = 512;
  constexpr int query_group = 8;
  const int head = static_cast<int>(blockIdx.x);
  const std::uint64_t key_value_base =
      static_cast<std::uint64_t>(head) * context_length * dimension;
  const std::uint64_t query_output_base =
      static_cast<std::uint64_t>(head) * query_group * dimension;
  extern __shared__ __align__(128) unsigned char storage_bytes[];
  auto& storage = *reinterpret_cast<GlobalAttentionTileSharedStorage*>(storage_bytes);
  Tensor shared_keys = make_tensor(make_smem_ptr(storage.keys.begin()), KeyLayout{});
  Tensor shared_queries = make_tensor(make_smem_ptr(storage.queries.begin()), QueryLayout{});
  Tensor shared_probabilities =
      make_tensor(make_smem_ptr(storage.probabilities.begin()), ProbabilityLayout{});
  Tensor shared_scores = make_tensor(make_smem_ptr(storage.scores.begin()), ScoreLayout{});

  for (int index = static_cast<int>(threadIdx.x); index < query_group * dimension;
       index += static_cast<int>(blockDim.x)) {
    const int query = index / dimension;
    const int component = index - query * dimension;
    shared_queries(query, component) = queries[query_output_base + index];
  }
  if (threadIdx.x < 128) {
    GlobalKeyCopy key_copy;
    ThrCopy thread_copy = key_copy.get_slice(threadIdx.x);
    Tensor global_keys = make_tensor(
        make_gmem_ptr(keys + key_value_base), make_shape(Int<64>{}, Int<512>{}),
        make_stride(Int<512>{}, Int<1>{}));
    Tensor independent_keys = as_position_independent_swizzle_tensor(shared_keys);
    copy(key_copy, thread_copy.partition_S(global_keys),
         thread_copy.partition_D(independent_keys));
    cp_async_fence();
    cp_async_wait<0>();
  }
  __syncthreads();

  if (threadIdx.x < 128) {
    GlobalQkMma qk_mma;
    ThrMMA thread_mma = qk_mma.get_slice(threadIdx.x);
    Tensor fragment_keys = thread_mma.partition_A(shared_keys);
    Tensor fragment_queries = thread_mma.partition_B(shared_queries);
    Tensor fragment_scores = thread_mma.partition_C(shared_scores);
    Tensor accumulators = thread_mma.make_fragment_C(fragment_scores);
    clear(accumulators);
    warpgroup_fence_operand(accumulators);
    warpgroup_arrive();
    cute::gemm(qk_mma, fragment_keys, fragment_queries, accumulators);
    warpgroup_commit_batch();
    warpgroup_wait<0>();
    warpgroup_fence_operand(accumulators);
    copy(accumulators, fragment_scores);
  }
  __syncthreads();

  const int warp = static_cast<int>(threadIdx.x) / 32;
  const int lane = static_cast<int>(threadIdx.x) & 31;
  if (warp < query_group) {
    const float score0 = static_cast<float>(shared_scores(lane, warp));
    const float score1 = static_cast<float>(shared_scores(lane + 32, warp));
    const float maximum = warp_maximum(max(score0, score1));
    const float exponential0 = expf(score0 - maximum);
    const float exponential1 = expf(score1 - maximum);
    const float inverse_sum = 1.0F / warp_total(exponential0 + exponential1);
    shared_probabilities(warp, lane) = Element(exponential0 * inverse_sum);
    shared_probabilities(warp, lane + 32) = Element(exponential1 * inverse_sum);
  }
  __syncthreads();

  if (threadIdx.x < 128) {
    for (int dimension_tile = 0; dimension_tile < 8; ++dimension_tile) {
      Tensor shared_values = make_tensor(
          make_smem_ptr(storage.values[dimension_tile].begin()), ValueTileLayout{});
      constexpr int vectors_per_token = 8;
      for (int vector_index = static_cast<int>(threadIdx.x);
           vector_index < 64 * vectors_per_token; vector_index += 128) {
        const int token = vector_index / vectors_per_token;
        const int component_group = vector_index - token * vectors_per_token;
        const auto source = key_value_base + static_cast<std::uint64_t>(token) * 512 +
                            dimension_tile * 64 + component_group * 8;
        const uint4 packed = *reinterpret_cast<const uint4*>(values + source);
        const auto* lanes = reinterpret_cast<const Element*>(&packed);
        #pragma unroll
        for (int lane_index = 0; lane_index < 8; ++lane_index) {
          shared_values(component_group * 8 + lane_index, token) = lanes[lane_index];
        }
      }
    }
  }
  __syncthreads();

  if (threadIdx.x < 128) {
    GlobalPvMma pv_mma;
    ThrMMA thread_mma = pv_mma.get_slice(threadIdx.x);
    Tensor fragment_probabilities = thread_mma.partition_B(shared_probabilities);
    for (int dimension_tile = 0; dimension_tile < 8; ++dimension_tile) {
      Tensor shared_values = make_tensor(
          make_smem_ptr(storage.values[dimension_tile].begin()), ValueTileLayout{});
      Tensor global_output = make_tensor(
          make_gmem_ptr(output + query_output_base + dimension_tile * 64),
          make_shape(Int<64>{}, Int<8>{}), make_stride(Int<1>{}, Int<512>{}));
      Tensor fragment_values = thread_mma.partition_A(shared_values);
      Tensor fragment_output = thread_mma.partition_C(global_output);
      Tensor accumulators = thread_mma.make_fragment_C(fragment_output);
      clear(accumulators);
      warpgroup_fence_operand(accumulators);
      warpgroup_arrive();
      cute::gemm(pv_mma, fragment_values, fragment_probabilities, accumulators);
      warpgroup_commit_batch();
      warpgroup_wait<0>();
      warpgroup_fence_operand(accumulators);
      copy(accumulators, fragment_output);
    }
  }
}

}  // namespace

void grouped_global_qk_wgmma_bf16(const void* query, const void* key_cache, void* scores,
                                  int batch, int kv_heads, int query_group,
                                  int context_length, int head_dimension,
                                  cudaStream_t stream, int tiles_per_block) {
  if (query == nullptr || key_cache == nullptr || scores == nullptr || batch <= 0 ||
      kv_heads <= 0 || query_group != 8 || context_length <= 0 ||
      context_length % 64 != 0 || head_dimension != 512 || tiles_per_block <= 0 ||
      (context_length / 64) % tiles_per_block != 0) {
    throw std::runtime_error("invalid Hopper global QK shape");
  }
  constexpr int threads = 128;
  constexpr std::size_t shared_bytes = sizeof(GlobalQkSharedStorage);
  check(cudaFuncSetAttribute(global_qk_wgmma_kernel,
                             cudaFuncAttributeMaxDynamicSharedMemorySize,
                             static_cast<int>(shared_bytes)),
        "set Hopper global QK shared memory");
  const int blocks = batch * kv_heads * (context_length / 64 / tiles_per_block);
  global_qk_wgmma_kernel<<<blocks, threads, shared_bytes, stream>>>(
      static_cast<const Element*>(query), static_cast<const Element*>(key_cache),
      static_cast<Element*>(scores), kv_heads, context_length, tiles_per_block);
  check(cudaPeekAtLastError(), "launch Hopper global QK");
}

void grouped_global_attention_wgmma_tile_bf16(
    const void* query, const void* key_cache, const void* value_cache, void* output,
    int batch, int kv_heads, int query_group, int context_length, int head_dimension,
    cudaStream_t stream) {
  if (query == nullptr || key_cache == nullptr || value_cache == nullptr || output == nullptr ||
      batch <= 0 || kv_heads <= 0 || query_group != 8 || context_length != 64 ||
      head_dimension != 512) {
    throw std::runtime_error("invalid Hopper global-attention tile shape");
  }
  constexpr int threads = 256;
  constexpr std::size_t shared_bytes = sizeof(GlobalAttentionTileSharedStorage);
  check(cudaFuncSetAttribute(global_attention_wgmma_tile_kernel,
                             cudaFuncAttributeMaxDynamicSharedMemorySize,
                             static_cast<int>(shared_bytes)),
        "set Hopper global-attention tile shared memory");
  global_attention_wgmma_tile_kernel<<<batch * kv_heads, threads, shared_bytes, stream>>>(
      static_cast<const Element*>(query), static_cast<const Element*>(key_cache),
      static_cast<const Element*>(value_cache), static_cast<Element*>(output),
      context_length);
  check(cudaPeekAtLastError(), "launch Hopper global-attention tile");
}

}  // namespace gradiated::engine
