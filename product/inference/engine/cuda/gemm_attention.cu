#include "gradiated/engine/gemm_attention.h"

#include <cublas_v2.h>
#include <cuda_bf16.h>
#include <cuda_runtime.h>
#include <math_constants.h>

#include <cstdint>
#include <stdexcept>
#include <string>

namespace gradiated::engine {
namespace {

void cuda_check(cudaError_t result, const char* operation) {
  if (result != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(result));
  }
}

void cublas_check(cublasStatus_t result, const char* operation) {
  if (result != CUBLAS_STATUS_SUCCESS) {
    throw std::runtime_error(std::string(operation) + " failed with status " + std::to_string(result));
  }
}

__device__ float warp_max(float value) {
  for (unsigned offset = 16; offset > 0; offset >>= 1U) {
    value = max(value, __shfl_down_sync(0xffffffffU, value, offset));
  }
  return value;
}

__device__ float warp_sum(float value) {
  for (unsigned offset = 16; offset > 0; offset >>= 1U) {
    value += __shfl_down_sync(0xffffffffU, value, offset);
  }
  return value;
}

__global__ void softmax_bf16_kernel(__nv_bfloat16* scores, int width) {
  __shared__ float warp_values[32];
  __nv_bfloat16* row = scores + static_cast<std::uint64_t>(blockIdx.x) * width;
  float maximum = -CUDART_INF_F;
  for (int index = threadIdx.x; index < width; index += blockDim.x) {
    maximum = max(maximum, __bfloat162float(row[index]));
  }
  maximum = warp_max(maximum);
  if ((threadIdx.x & 31U) == 0U) warp_values[threadIdx.x >> 5U] = maximum;
  __syncthreads();
  maximum = threadIdx.x < (blockDim.x + 31U) / 32U ? warp_values[threadIdx.x] : -CUDART_INF_F;
  if (threadIdx.x < 32U) maximum = warp_max(maximum);
  if (threadIdx.x == 0U) warp_values[0] = maximum;
  __syncthreads();
  maximum = warp_values[0];

  float sum = 0.0F;
  for (int index = threadIdx.x; index < width; index += blockDim.x) {
    sum += expf(__bfloat162float(row[index]) - maximum);
  }
  sum = warp_sum(sum);
  if ((threadIdx.x & 31U) == 0U) warp_values[threadIdx.x >> 5U] = sum;
  __syncthreads();
  sum = threadIdx.x < (blockDim.x + 31U) / 32U ? warp_values[threadIdx.x] : 0.0F;
  if (threadIdx.x < 32U) sum = warp_sum(sum);
  if (threadIdx.x == 0U) warp_values[0] = 1.0F / sum;
  __syncthreads();
  const float inverse_sum = warp_values[0];
  for (int index = threadIdx.x; index < width; index += blockDim.x) {
    row[index] = __float2bfloat16_rn(expf(__bfloat162float(row[index]) - maximum) * inverse_sum);
  }
}

__global__ void ragged_softmax_bf16_kernel(__nv_bfloat16* scores, const int* positions,
                                           int kv_heads, int query_group, int width,
                                           int cache_capacity) {
  __shared__ float warp_values[32];
  const int request = static_cast<int>(blockIdx.x) / (kv_heads * query_group);
  const int valid = min(positions[request] + 1, cache_capacity);
  __nv_bfloat16* row = scores + static_cast<std::uint64_t>(blockIdx.x) * width;
  float maximum = -CUDART_INF_F;
  for (int index = threadIdx.x; index < valid; index += blockDim.x) {
    maximum = max(maximum, __bfloat162float(row[index]));
  }
  maximum = warp_max(maximum);
  if ((threadIdx.x & 31U) == 0U) warp_values[threadIdx.x >> 5U] = maximum;
  __syncthreads();
  maximum = threadIdx.x < (blockDim.x + 31U) / 32U ? warp_values[threadIdx.x] : -CUDART_INF_F;
  if (threadIdx.x < 32U) maximum = warp_max(maximum);
  if (threadIdx.x == 0U) warp_values[0] = maximum;
  __syncthreads();
  maximum = warp_values[0];

  float sum = 0.0F;
  for (int index = threadIdx.x; index < valid; index += blockDim.x) {
    sum += expf(__bfloat162float(row[index]) - maximum);
  }
  sum = warp_sum(sum);
  if ((threadIdx.x & 31U) == 0U) warp_values[threadIdx.x >> 5U] = sum;
  __syncthreads();
  sum = threadIdx.x < (blockDim.x + 31U) / 32U ? warp_values[threadIdx.x] : 0.0F;
  if (threadIdx.x < 32U) sum = warp_sum(sum);
  if (threadIdx.x == 0U) warp_values[0] = 1.0F / sum;
  __syncthreads();
  const float inverse_sum = warp_values[0];
  for (int index = threadIdx.x; index < width; index += blockDim.x) {
    row[index] = index < valid
        ? __float2bfloat16_rn(expf(__bfloat162float(row[index]) - maximum) * inverse_sum)
        : __float2bfloat16_rn(0.0F);
  }
}

__global__ void ragged_pointer_kernel(
    const __nv_bfloat16* query, const __nv_bfloat16* key_cache,
    const __nv_bfloat16* value_cache, __nv_bfloat16* scores, __nv_bfloat16* output,
    const int* slots, int batch, int maximum_slots, int kv_heads, int query_group,
    int width, int cache_capacity, int head_dimension, const void** key_pointers,
    const void** query_pointers, const void** value_pointers, void** score_pointers,
    void** output_pointers) {
  const int index = static_cast<int>(blockIdx.x) * blockDim.x + threadIdx.x;
  const int head_batches = batch * kv_heads;
  if (index >= head_batches) return;
  const int row = index / kv_heads;
  const int kv_head = index % kv_heads;
  const int slot = slots[row];
  if (slot < 0 || slot >= maximum_slots) return;
  const std::uint64_t cache_head = static_cast<std::uint64_t>(slot) * kv_heads + kv_head;
  const std::uint64_t compact_head = static_cast<std::uint64_t>(row) * kv_heads + kv_head;
  key_pointers[index] = key_cache + cache_head * cache_capacity * head_dimension;
  value_pointers[index] = value_cache + cache_head * cache_capacity * head_dimension;
  query_pointers[index] = query + compact_head * query_group * head_dimension;
  score_pointers[index] = scores + compact_head * query_group * width;
  output_pointers[index] = output + compact_head * query_group * head_dimension;
}

}  // namespace

struct GemmGroupedDecodeAttention::Implementation {
  cublasHandle_t handle{};
  void* scores{nullptr};
  void* pointers{nullptr};
  std::uint64_t maximum_score_elements;
  int maximum_batch;
  int maximum_head_batches;

  Implementation(int batch, int kv_heads, int query_group, int context)
      : maximum_score_elements(static_cast<std::uint64_t>(batch) * kv_heads * query_group * context),
        maximum_batch(batch),
        maximum_head_batches(batch * kv_heads) {
    if (batch <= 0 || kv_heads <= 0 || query_group <= 0 || context <= 0) {
      throw std::runtime_error("invalid maximum attention shape");
    }
    cublas_check(cublasCreate(&handle), "cublasCreate attention");
    cuda_check(cudaMalloc(&scores, static_cast<std::size_t>(maximum_score_elements * 2ULL)),
               "allocate attention score workspace");
    cuda_check(cudaMalloc(&pointers, static_cast<std::size_t>(5ULL * maximum_head_batches *
                                                              sizeof(void*))),
               "allocate ragged attention pointers");
  }
  ~Implementation() {
    if (pointers != nullptr) cudaFree(pointers);
    if (scores != nullptr) cudaFree(scores);
    if (handle != nullptr) cublasDestroy(handle);
  }
};

GemmGroupedDecodeAttention::GemmGroupedDecodeAttention(int maximum_batch, int maximum_kv_heads,
                                                       int maximum_query_group, int maximum_context)
    : implementation_(std::make_unique<Implementation>(maximum_batch, maximum_kv_heads,
                                                        maximum_query_group, maximum_context)) {}
GemmGroupedDecodeAttention::~GemmGroupedDecodeAttention() = default;

void GemmGroupedDecodeAttention::run(const void* query, const void* key_cache, const void* value_cache,
                                     void* output, int batch, int kv_heads, int query_group,
                                     int context_length, int head_dimension, cudaStream_t stream,
                                     int cache_capacity) {
  if (cache_capacity == 0) cache_capacity = context_length;
  const std::uint64_t score_elements =
      static_cast<std::uint64_t>(batch) * kv_heads * query_group * context_length;
  if (batch <= 0 || kv_heads <= 0 || query_group <= 0 || context_length <= 0 ||
      cache_capacity < context_length || head_dimension <= 0 ||
      score_elements > implementation_->maximum_score_elements) {
    throw std::runtime_error("attention shape exceeds workspace");
  }
  cublas_check(cublasSetStream(implementation_->handle, stream), "set attention stream");
  constexpr float alpha = 1.0F;
  constexpr float beta = 0.0F;
  const int head_batches = batch * kv_heads;
  const long long cache_stride = static_cast<long long>(cache_capacity) * head_dimension;
  const long long query_stride = static_cast<long long>(query_group) * head_dimension;
  const long long score_stride = static_cast<long long>(query_group) * context_length;
  cublas_check(cublasGemmStridedBatchedEx(
      implementation_->handle, CUBLAS_OP_T, CUBLAS_OP_N,
      context_length, query_group, head_dimension, &alpha,
      key_cache, CUDA_R_16BF, head_dimension, cache_stride,
      query, CUDA_R_16BF, head_dimension, query_stride,
      &beta, implementation_->scores, CUDA_R_16BF, context_length, score_stride,
      head_batches, CUBLAS_COMPUTE_32F, CUBLAS_GEMM_DEFAULT_TENSOR_OP), "grouped QK GEMM");
  softmax_bf16_kernel<<<head_batches * query_group, 256, 0, stream>>>(
      static_cast<__nv_bfloat16*>(implementation_->scores), context_length);
  cuda_check(cudaPeekAtLastError(), "launch attention softmax");
  cublas_check(cublasGemmStridedBatchedEx(
      implementation_->handle, CUBLAS_OP_N, CUBLAS_OP_N,
      head_dimension, query_group, context_length, &alpha,
      value_cache, CUDA_R_16BF, head_dimension, cache_stride,
      implementation_->scores, CUDA_R_16BF, context_length, score_stride,
      &beta, output, CUDA_R_16BF, head_dimension, query_stride,
      head_batches, CUBLAS_COMPUTE_32F, CUBLAS_GEMM_DEFAULT_TENSOR_OP), "grouped PV GEMM");
}

void GemmGroupedDecodeAttention::run_ragged(
    const void* query, const void* key_cache, const void* value_cache, void* output,
    const int* positions, const int* slots, int batch, int maximum_slots, int kv_heads,
    int query_group, int maximum_context_length, int head_dimension, cudaStream_t stream,
    int cache_capacity) {
  const std::uint64_t score_elements = static_cast<std::uint64_t>(batch) * kv_heads *
                                       query_group * maximum_context_length;
  if (query == nullptr || key_cache == nullptr || value_cache == nullptr || output == nullptr ||
      positions == nullptr || slots == nullptr || batch <= 0 || maximum_slots < batch ||
      kv_heads <= 0 || query_group <= 0 || maximum_context_length <= 0 ||
      maximum_context_length > cache_capacity || head_dimension <= 0 ||
      batch * kv_heads > implementation_->maximum_head_batches ||
      score_elements > implementation_->maximum_score_elements) {
    throw std::runtime_error("ragged attention shape exceeds workspace");
  }
  auto& state = *implementation_;
  cublas_check(cublasSetStream(state.handle, stream), "set ragged attention stream");
  const int head_batches = batch * kv_heads;
  auto** pointer_base = static_cast<void**>(state.pointers);
  auto** key_pointers = const_cast<void**>(pointer_base);
  auto** query_pointers = pointer_base + state.maximum_head_batches;
  auto** value_pointers = pointer_base + 2 * state.maximum_head_batches;
  auto** score_pointers = pointer_base + 3 * state.maximum_head_batches;
  auto** output_pointers = pointer_base + 4 * state.maximum_head_batches;
  constexpr int pointer_threads = 256;
  ragged_pointer_kernel<<<(head_batches + pointer_threads - 1) / pointer_threads,
                           pointer_threads, 0, stream>>>(
      static_cast<const __nv_bfloat16*>(query), static_cast<const __nv_bfloat16*>(key_cache),
      static_cast<const __nv_bfloat16*>(value_cache), static_cast<__nv_bfloat16*>(state.scores),
      static_cast<__nv_bfloat16*>(output), slots, batch, maximum_slots, kv_heads, query_group,
      maximum_context_length, cache_capacity, head_dimension,
      const_cast<const void**>(key_pointers), const_cast<const void**>(query_pointers),
      const_cast<const void**>(value_pointers), score_pointers, output_pointers);
  cuda_check(cudaPeekAtLastError(), "build ragged attention pointers");

  constexpr float alpha = 1.0F;
  constexpr float beta = 0.0F;
  cublas_check(cublasGemmBatchedEx(
      state.handle, CUBLAS_OP_T, CUBLAS_OP_N, maximum_context_length, query_group,
      head_dimension, &alpha, reinterpret_cast<const void* const*>(key_pointers), CUDA_R_16BF,
      head_dimension, reinterpret_cast<const void* const*>(query_pointers), CUDA_R_16BF,
      head_dimension, &beta, score_pointers, CUDA_R_16BF, maximum_context_length,
      head_batches, CUBLAS_COMPUTE_32F, CUBLAS_GEMM_DEFAULT_TENSOR_OP),
      "ragged grouped QK GEMM");
  ragged_softmax_bf16_kernel<<<batch * kv_heads * query_group, 256, 0, stream>>>(
      static_cast<__nv_bfloat16*>(state.scores), positions, kv_heads, query_group,
      maximum_context_length, cache_capacity);
  cuda_check(cudaPeekAtLastError(), "launch ragged attention softmax");
  cublas_check(cublasGemmBatchedEx(
      state.handle, CUBLAS_OP_N, CUBLAS_OP_N, head_dimension, query_group,
      maximum_context_length, &alpha, reinterpret_cast<const void* const*>(value_pointers),
      CUDA_R_16BF, head_dimension, reinterpret_cast<const void* const*>(score_pointers),
      CUDA_R_16BF, maximum_context_length, &beta, output_pointers, CUDA_R_16BF,
      head_dimension, head_batches, CUBLAS_COMPUTE_32F, CUBLAS_GEMM_DEFAULT_TENSOR_OP),
      "ragged grouped PV GEMM");
}

void GemmGroupedDecodeAttention::run_ragged_contiguous(
    const void* query, const void* key_cache, const void* value_cache, void* output,
    const int* positions, int batch, int kv_heads, int query_group,
    int maximum_context_length, int head_dimension, int first_slot, cudaStream_t stream,
    int cache_capacity) {
  const std::uint64_t score_elements = static_cast<std::uint64_t>(batch) * kv_heads *
                                       query_group * maximum_context_length;
  if (query == nullptr || key_cache == nullptr || value_cache == nullptr || output == nullptr ||
      positions == nullptr || batch <= 0 || kv_heads <= 0 || query_group <= 0 || first_slot < 0 ||
      first_slot + batch > implementation_->maximum_batch ||
      maximum_context_length <= 0 || maximum_context_length > cache_capacity ||
      head_dimension <= 0 || batch * kv_heads > implementation_->maximum_head_batches ||
      score_elements > implementation_->maximum_score_elements) {
    throw std::runtime_error("contiguous ragged attention shape exceeds workspace");
  }
  auto& state = *implementation_;
  cublas_check(cublasSetStream(state.handle, stream),
               "set contiguous ragged attention stream");
  constexpr float alpha = 1.0F;
  constexpr float beta = 0.0F;
  const int head_batches = batch * kv_heads;
  const long long cache_stride = static_cast<long long>(cache_capacity) * head_dimension;
  const long long query_stride = static_cast<long long>(query_group) * head_dimension;
  const long long score_stride = static_cast<long long>(query_group) * maximum_context_length;
  const auto cache_offset = static_cast<std::uint64_t>(first_slot) * kv_heads *
                            cache_capacity * head_dimension;
  const auto* contiguous_keys = static_cast<const __nv_bfloat16*>(key_cache) + cache_offset;
  const auto* contiguous_values = static_cast<const __nv_bfloat16*>(value_cache) + cache_offset;
  cublas_check(cublasGemmStridedBatchedEx(
      state.handle, CUBLAS_OP_T, CUBLAS_OP_N, maximum_context_length, query_group,
      head_dimension, &alpha, contiguous_keys, CUDA_R_16BF, head_dimension, cache_stride,
      query, CUDA_R_16BF, head_dimension, query_stride, &beta, state.scores, CUDA_R_16BF,
      maximum_context_length, score_stride, head_batches, CUBLAS_COMPUTE_32F,
      CUBLAS_GEMM_DEFAULT_TENSOR_OP), "contiguous ragged grouped QK GEMM");
  ragged_softmax_bf16_kernel<<<batch * kv_heads * query_group, 256, 0, stream>>>(
      static_cast<__nv_bfloat16*>(state.scores), positions, kv_heads, query_group,
      maximum_context_length, cache_capacity);
  cuda_check(cudaPeekAtLastError(), "launch contiguous ragged attention softmax");
  cublas_check(cublasGemmStridedBatchedEx(
      state.handle, CUBLAS_OP_N, CUBLAS_OP_N, head_dimension, query_group,
      maximum_context_length, &alpha, contiguous_values, CUDA_R_16BF, head_dimension, cache_stride,
      state.scores, CUDA_R_16BF, maximum_context_length, score_stride, &beta, output,
      CUDA_R_16BF, head_dimension, query_stride, head_batches, CUBLAS_COMPUTE_32F,
      CUBLAS_GEMM_DEFAULT_TENSOR_OP), "contiguous ragged grouped PV GEMM");
}

}  // namespace gradiated::engine
