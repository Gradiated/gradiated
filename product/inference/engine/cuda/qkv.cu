#include "gradiated/engine/qkv.h"

#include <cuda_bf16.h>
#include <cuda_runtime.h>

#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>

namespace gradiated::engine {
namespace {

constexpr int threads = 256;

void check(cudaError_t result, const char* operation) {
  if (result != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(result));
  }
}

__device__ float block_sum(float value) {
  for (unsigned offset = 16; offset > 0; offset >>= 1U) {
    value += __shfl_down_sync(0xffffffffU, value, offset);
  }
  __shared__ float warp_sums[32];
  if ((threadIdx.x & 31U) == 0U) warp_sums[threadIdx.x >> 5U] = value;
  __syncthreads();
  value = threadIdx.x < (blockDim.x + 31U) / 32U ? warp_sums[threadIdx.x] : 0.0F;
  if (threadIdx.x < 32U) {
    for (unsigned offset = 16; offset > 0; offset >>= 1U) {
      value += __shfl_down_sync(0xffffffffU, value, offset);
    }
  }
  if (threadIdx.x == 0U) warp_sums[0] = value;
  __syncthreads();
  return warp_sums[0];
}

template <int dimension, bool proportional>
__global__ void rope_cache_kernel(__nv_bfloat16* cosine, __nv_bfloat16* sine, int positions) {
  const int index = static_cast<int>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index >= positions * dimension) return;
  const int position = index / dimension;
  const int half_index = index % (dimension / 2);
  float frequency = 0.0F;
  if constexpr (proportional) {
    if (half_index < dimension / 8) {
      frequency = powf(1000000.0F, -2.0F * static_cast<float>(half_index) / dimension);
    }
  } else {
    frequency = powf(10000.0F, -2.0F * static_cast<float>(half_index) / dimension);
  }
  float sin_value = 0.0F;
  float cos_value = 0.0F;
  sincosf(static_cast<float>(position) * frequency, &sin_value, &cos_value);
  cosine[index] = __float2bfloat16_rn(cos_value);
  sine[index] = __float2bfloat16_rn(sin_value);
}

template <int dimension, bool batched>
__global__ void query_kernel(const __nv_bfloat16* packed, const __nv_bfloat16* norm_weight,
                             const __nv_bfloat16* cosine, const __nv_bfloat16* sine,
                             __nv_bfloat16* output, int tokens, int query_heads,
                             int packed_width, int position_start, float epsilon) {
  const int token = static_cast<int>(blockIdx.x) / query_heads;
  const int head = static_cast<int>(blockIdx.x) % query_heads;
  const __nv_bfloat16* input = packed + static_cast<std::uint64_t>(token) * packed_width + head * dimension;
  float square_sum = 0.0F;
  for (int index = threadIdx.x; index < dimension; index += threads) {
    const float value = __bfloat162float(input[index]);
    square_sum += value * value;
  }
  const float inverse_rms = rsqrtf(block_sum(square_sum) / dimension + epsilon);
  const int position = position_start + (batched ? 0 : token);
  const int half = dimension / 2;
  for (int index = threadIdx.x; index < dimension; index += threads) {
    const int partner = index < half ? index + half : index - half;
    const float normalized = __bfloat162float(__float2bfloat16_rn(
        __bfloat162float(input[index]) * inverse_rms * __bfloat162float(norm_weight[index])));
    const float partner_normalized = __bfloat162float(__float2bfloat16_rn(
        __bfloat162float(input[partner]) * inverse_rms * __bfloat162float(norm_weight[partner])));
    const float rotated = index < half ? -partner_normalized : partner_normalized;
    const float cos_value = __bfloat162float(cosine[position * dimension + index]);
    const float sin_value = __bfloat162float(sine[position * dimension + index]);
    output[(static_cast<std::uint64_t>(token) * query_heads + head) * dimension + index] =
        __float2bfloat16_rn(normalized * cos_value + rotated * sin_value);
  }
}

template <int dimension, bool key_equals_value, bool batched>
__global__ void key_value_kernel(const __nv_bfloat16* packed, const __nv_bfloat16* norm_weight,
                                 const __nv_bfloat16* cosine, const __nv_bfloat16* sine,
                                 __nv_bfloat16* key_cache, __nv_bfloat16* value_cache,
                                 int tokens, int query_width, int kv_heads, int packed_width,
                                 int position_start, int cache_position_start,
                                 int cache_capacity, float epsilon) {
  const int token = static_cast<int>(blockIdx.x) / kv_heads;
  const int head = static_cast<int>(blockIdx.x) % kv_heads;
  const __nv_bfloat16* key_input = packed + static_cast<std::uint64_t>(token) * packed_width +
                                   query_width + head * dimension;
  const __nv_bfloat16* value_input = key_equals_value
      ? key_input
      : packed + static_cast<std::uint64_t>(token) * packed_width + query_width +
            kv_heads * dimension + head * dimension;
  float key_square_sum = 0.0F;
  float value_square_sum = 0.0F;
  for (int index = threadIdx.x; index < dimension; index += threads) {
    const float key = __bfloat162float(key_input[index]);
    const float value = __bfloat162float(value_input[index]);
    key_square_sum += key * key;
    value_square_sum += value * value;
  }
  const float inverse_key_rms = rsqrtf(block_sum(key_square_sum) / dimension + epsilon);
  const float inverse_value_rms = key_equals_value
      ? inverse_key_rms
      : rsqrtf(block_sum(value_square_sum) / dimension + epsilon);
  const int position = position_start + (batched ? 0 : token);
  const int cache_position = batched ? position % cache_capacity : cache_position_start + token;
  const int half = dimension / 2;
  const std::uint64_t cache_head = (batched ? static_cast<std::uint64_t>(token) * kv_heads : 0ULL) + head;
  const std::uint64_t cache_base = (cache_head * cache_capacity + cache_position) * dimension;
  for (int index = threadIdx.x; index < dimension; index += threads) {
    const int partner = index < half ? index + half : index - half;
    const float normalized = __bfloat162float(__float2bfloat16_rn(
        __bfloat162float(key_input[index]) * inverse_key_rms * __bfloat162float(norm_weight[index])));
    const float partner_normalized = __bfloat162float(__float2bfloat16_rn(
        __bfloat162float(key_input[partner]) * inverse_key_rms * __bfloat162float(norm_weight[partner])));
    const float rotated = index < half ? -partner_normalized : partner_normalized;
    const float cos_value = __bfloat162float(cosine[position * dimension + index]);
    const float sin_value = __bfloat162float(sine[position * dimension + index]);
    key_cache[cache_base + index] = __float2bfloat16_rn(normalized * cos_value + rotated * sin_value);
    value_cache[cache_base + index] = __float2bfloat16_rn(
        __bfloat162float(value_input[index]) * inverse_value_rms);
  }
}

template <int dimension>
__global__ void ragged_query_kernel(
    const __nv_bfloat16* packed, const __nv_bfloat16* norm_weight,
    const __nv_bfloat16* cosine, const __nv_bfloat16* sine, __nv_bfloat16* output,
    const int* positions, int batch, int query_heads, int packed_width, float epsilon) {
  const int row = static_cast<int>(blockIdx.x) / query_heads;
  const int head = static_cast<int>(blockIdx.x) % query_heads;
  if (row >= batch) return;
  const __nv_bfloat16* input =
      packed + static_cast<std::uint64_t>(row) * packed_width + head * dimension;
  float square_sum = 0.0F;
  for (int index = threadIdx.x; index < dimension; index += threads) {
    const float value = __bfloat162float(input[index]);
    square_sum += value * value;
  }
  const float inverse_rms = rsqrtf(block_sum(square_sum) / dimension + epsilon);
  const int position = positions[row];
  const int half = dimension / 2;
  for (int index = threadIdx.x; index < dimension; index += threads) {
    const int partner = index < half ? index + half : index - half;
    const float normalized = __bfloat162float(__float2bfloat16_rn(
        __bfloat162float(input[index]) * inverse_rms * __bfloat162float(norm_weight[index])));
    const float partner_normalized = __bfloat162float(__float2bfloat16_rn(
        __bfloat162float(input[partner]) * inverse_rms * __bfloat162float(norm_weight[partner])));
    const float rotated = index < half ? -partner_normalized : partner_normalized;
    const float cos_value = __bfloat162float(cosine[position * dimension + index]);
    const float sin_value = __bfloat162float(sine[position * dimension + index]);
    output[(static_cast<std::uint64_t>(row) * query_heads + head) * dimension + index] =
        __float2bfloat16_rn(normalized * cos_value + rotated * sin_value);
  }
}

template <int dimension, bool key_equals_value>
__global__ void ragged_key_value_kernel(
    const __nv_bfloat16* packed, const __nv_bfloat16* norm_weight,
    const __nv_bfloat16* cosine, const __nv_bfloat16* sine,
    __nv_bfloat16* key_cache, __nv_bfloat16* value_cache,
    const int* positions, const int* slots, int batch, int maximum_slots,
    int query_width, int kv_heads, int packed_width, int cache_capacity, float epsilon) {
  const int row = static_cast<int>(blockIdx.x) / kv_heads;
  const int head = static_cast<int>(blockIdx.x) % kv_heads;
  if (row >= batch) return;
  const int position = positions[row];
  const int slot = slots[row];
  if (position < 0 || slot < 0 || slot >= maximum_slots) return;
  const __nv_bfloat16* key_input = packed + static_cast<std::uint64_t>(row) * packed_width +
                                   query_width + head * dimension;
  const __nv_bfloat16* value_input = key_equals_value
      ? key_input
      : packed + static_cast<std::uint64_t>(row) * packed_width + query_width +
            kv_heads * dimension + head * dimension;
  float key_square_sum = 0.0F;
  float value_square_sum = 0.0F;
  for (int index = threadIdx.x; index < dimension; index += threads) {
    const float key = __bfloat162float(key_input[index]);
    const float value = __bfloat162float(value_input[index]);
    key_square_sum += key * key;
    value_square_sum += value * value;
  }
  const float inverse_key_rms = rsqrtf(block_sum(key_square_sum) / dimension + epsilon);
  const float inverse_value_rms = key_equals_value
      ? inverse_key_rms
      : rsqrtf(block_sum(value_square_sum) / dimension + epsilon);
  const int cache_position = position % cache_capacity;
  const int half = dimension / 2;
  const std::uint64_t cache_head = static_cast<std::uint64_t>(slot) * kv_heads + head;
  const std::uint64_t cache_base = (cache_head * cache_capacity + cache_position) * dimension;
  for (int index = threadIdx.x; index < dimension; index += threads) {
    const int partner = index < half ? index + half : index - half;
    const float normalized = __bfloat162float(__float2bfloat16_rn(
        __bfloat162float(key_input[index]) * inverse_key_rms * __bfloat162float(norm_weight[index])));
    const float partner_normalized = __bfloat162float(__float2bfloat16_rn(
        __bfloat162float(key_input[partner]) * inverse_key_rms * __bfloat162float(norm_weight[partner])));
    const float rotated = index < half ? -partner_normalized : partner_normalized;
    const float cos_value = __bfloat162float(cosine[position * dimension + index]);
    const float sin_value = __bfloat162float(sine[position * dimension + index]);
    key_cache[cache_base + index] = __float2bfloat16_rn(normalized * cos_value + rotated * sin_value);
    value_cache[cache_base + index] = __float2bfloat16_rn(
        __bfloat162float(value_input[index]) * inverse_value_rms);
  }
}

}  // namespace

struct Gemma4QkvPostprocessor::Implementation {
  int maximum_positions;
  __nv_bfloat16* sliding_cosine{nullptr};
  __nv_bfloat16* sliding_sine{nullptr};
  __nv_bfloat16* global_cosine{nullptr};
  __nv_bfloat16* global_sine{nullptr};

  explicit Implementation(int positions) : maximum_positions(positions) {
    if (positions <= 0) throw std::runtime_error("invalid RoPE cache size");
    check(cudaMalloc(&sliding_cosine, static_cast<std::size_t>(positions) * 256 * 2), "allocate sliding cosine");
    check(cudaMalloc(&sliding_sine, static_cast<std::size_t>(positions) * 256 * 2), "allocate sliding sine");
    check(cudaMalloc(&global_cosine, static_cast<std::size_t>(positions) * 512 * 2), "allocate global cosine");
    check(cudaMalloc(&global_sine, static_cast<std::size_t>(positions) * 512 * 2), "allocate global sine");
    const int sliding_elements = positions * 256;
    const int global_elements = positions * 512;
    rope_cache_kernel<256, false><<<(sliding_elements + threads - 1) / threads, threads>>>(
        sliding_cosine, sliding_sine, positions);
    rope_cache_kernel<512, true><<<(global_elements + threads - 1) / threads, threads>>>(
        global_cosine, global_sine, positions);
    check(cudaGetLastError(), "initialize RoPE cache");
  }
  ~Implementation() {
    cudaFree(global_sine);
    cudaFree(global_cosine);
    cudaFree(sliding_sine);
    cudaFree(sliding_cosine);
  }
};

Gemma4QkvPostprocessor::Gemma4QkvPostprocessor(int maximum_positions)
    : implementation_(std::make_unique<Implementation>(maximum_positions)) {}
Gemma4QkvPostprocessor::~Gemma4QkvPostprocessor() = default;

void Gemma4QkvPostprocessor::run(
    const void* packed_qkv, const void* query_norm_weight, const void* key_norm_weight,
    void* queries, void* key_cache, void* value_cache, int tokens, int query_heads,
    int kv_heads, int head_dimension, bool key_equals_value, int position_start,
    int cache_capacity, float epsilon, cudaStream_t stream) {
  run_positioned(packed_qkv, query_norm_weight, key_norm_weight, queries, key_cache, value_cache,
                 tokens, query_heads, kv_heads, head_dimension, key_equals_value, position_start,
                 position_start, cache_capacity, epsilon, stream);
}

void Gemma4QkvPostprocessor::run_positioned(
    const void* packed_qkv, const void* query_norm_weight, const void* key_norm_weight,
    void* queries, void* key_cache, void* value_cache, int tokens, int query_heads,
    int kv_heads, int head_dimension, bool key_equals_value, int position_start,
    int cache_position_start, int cache_capacity, float epsilon, cudaStream_t stream) {
  if (tokens <= 0 || position_start < 0 || cache_position_start < 0 ||
      cache_position_start + tokens > cache_capacity ||
      position_start + tokens > implementation_->maximum_positions) {
    throw std::runtime_error("invalid QKV positions");
  }
  const int query_width = query_heads * head_dimension;
  const int kv_width = kv_heads * head_dimension;
  const int packed_width = query_width + kv_width * (key_equals_value ? 1 : 2);
  if (head_dimension == 256 && !key_equals_value) {
    query_kernel<256, false><<<tokens * query_heads, threads, 0, stream>>>(
        static_cast<const __nv_bfloat16*>(packed_qkv), static_cast<const __nv_bfloat16*>(query_norm_weight),
        implementation_->sliding_cosine, implementation_->sliding_sine,
        static_cast<__nv_bfloat16*>(queries), tokens, query_heads, packed_width, position_start, epsilon);
    key_value_kernel<256, false, false><<<tokens * kv_heads, threads, 0, stream>>>(
        static_cast<const __nv_bfloat16*>(packed_qkv), static_cast<const __nv_bfloat16*>(key_norm_weight),
        implementation_->sliding_cosine, implementation_->sliding_sine,
        static_cast<__nv_bfloat16*>(key_cache), static_cast<__nv_bfloat16*>(value_cache),
        tokens, query_width, kv_heads, packed_width, position_start, cache_position_start,
        cache_capacity, epsilon);
  } else if (head_dimension == 512 && key_equals_value) {
    query_kernel<512, false><<<tokens * query_heads, threads, 0, stream>>>(
        static_cast<const __nv_bfloat16*>(packed_qkv), static_cast<const __nv_bfloat16*>(query_norm_weight),
        implementation_->global_cosine, implementation_->global_sine,
        static_cast<__nv_bfloat16*>(queries), tokens, query_heads, packed_width, position_start, epsilon);
    key_value_kernel<512, true, false><<<tokens * kv_heads, threads, 0, stream>>>(
        static_cast<const __nv_bfloat16*>(packed_qkv), static_cast<const __nv_bfloat16*>(key_norm_weight),
        implementation_->global_cosine, implementation_->global_sine,
        static_cast<__nv_bfloat16*>(key_cache), static_cast<__nv_bfloat16*>(value_cache),
        tokens, query_width, kv_heads, packed_width, position_start, cache_position_start,
        cache_capacity, epsilon);
  } else {
    throw std::runtime_error("unsupported Gemma 4 QKV shape");
  }
  check(cudaPeekAtLastError(), "launch QKV postprocessing");
}

void Gemma4QkvPostprocessor::run_decode_batch(
    const void* packed_qkv, const void* query_norm_weight, const void* key_norm_weight,
    void* queries, void* key_cache, void* value_cache, int batch, int query_heads,
    int kv_heads, int head_dimension, bool key_equals_value, int position,
    int cache_capacity, float epsilon, cudaStream_t stream) {
  if (batch <= 0 || position < 0 || position >= implementation_->maximum_positions) {
    throw std::runtime_error("invalid batched QKV position");
  }
  const int query_width = query_heads * head_dimension;
  const int kv_width = kv_heads * head_dimension;
  const int packed_width = query_width + kv_width * (key_equals_value ? 1 : 2);
  if (head_dimension == 256 && !key_equals_value) {
    query_kernel<256, true><<<batch * query_heads, threads, 0, stream>>>(
        static_cast<const __nv_bfloat16*>(packed_qkv), static_cast<const __nv_bfloat16*>(query_norm_weight),
        implementation_->sliding_cosine, implementation_->sliding_sine,
        static_cast<__nv_bfloat16*>(queries), batch, query_heads, packed_width, position, epsilon);
    key_value_kernel<256, false, true><<<batch * kv_heads, threads, 0, stream>>>(
        static_cast<const __nv_bfloat16*>(packed_qkv), static_cast<const __nv_bfloat16*>(key_norm_weight),
        implementation_->sliding_cosine, implementation_->sliding_sine,
        static_cast<__nv_bfloat16*>(key_cache), static_cast<__nv_bfloat16*>(value_cache),
        batch, query_width, kv_heads, packed_width, position, 0, cache_capacity, epsilon);
  } else if (head_dimension == 512 && key_equals_value) {
    query_kernel<512, true><<<batch * query_heads, threads, 0, stream>>>(
        static_cast<const __nv_bfloat16*>(packed_qkv), static_cast<const __nv_bfloat16*>(query_norm_weight),
        implementation_->global_cosine, implementation_->global_sine,
        static_cast<__nv_bfloat16*>(queries), batch, query_heads, packed_width, position, epsilon);
    key_value_kernel<512, true, true><<<batch * kv_heads, threads, 0, stream>>>(
        static_cast<const __nv_bfloat16*>(packed_qkv), static_cast<const __nv_bfloat16*>(key_norm_weight),
        implementation_->global_cosine, implementation_->global_sine,
        static_cast<__nv_bfloat16*>(key_cache), static_cast<__nv_bfloat16*>(value_cache),
        batch, query_width, kv_heads, packed_width, position, 0, cache_capacity, epsilon);
  } else {
    throw std::runtime_error("unsupported batched Gemma 4 QKV shape");
  }
  check(cudaPeekAtLastError(), "launch batched QKV postprocessing");
}

void Gemma4QkvPostprocessor::run_decode_ragged(
    const void* packed_qkv, const void* query_norm_weight, const void* key_norm_weight,
    void* queries, void* key_cache, void* value_cache, const int* positions,
    const int* slots, int batch, int maximum_slots, int query_heads, int kv_heads,
    int head_dimension, bool key_equals_value, int cache_capacity, float epsilon,
    cudaStream_t stream) {
  if (batch <= 0 || maximum_slots <= 0 || batch > maximum_slots || positions == nullptr ||
      slots == nullptr || cache_capacity <= 0 || cache_capacity > implementation_->maximum_positions) {
    throw std::runtime_error("invalid ragged QKV shape");
  }
  const int query_width = query_heads * head_dimension;
  const int kv_width = kv_heads * head_dimension;
  const int packed_width = query_width + kv_width * (key_equals_value ? 1 : 2);
  if (head_dimension == 256 && !key_equals_value) {
    ragged_query_kernel<256><<<batch * query_heads, threads, 0, stream>>>(
        static_cast<const __nv_bfloat16*>(packed_qkv),
        static_cast<const __nv_bfloat16*>(query_norm_weight), implementation_->sliding_cosine,
        implementation_->sliding_sine, static_cast<__nv_bfloat16*>(queries), positions,
        batch, query_heads, packed_width, epsilon);
    ragged_key_value_kernel<256, false><<<batch * kv_heads, threads, 0, stream>>>(
        static_cast<const __nv_bfloat16*>(packed_qkv),
        static_cast<const __nv_bfloat16*>(key_norm_weight), implementation_->sliding_cosine,
        implementation_->sliding_sine, static_cast<__nv_bfloat16*>(key_cache),
        static_cast<__nv_bfloat16*>(value_cache), positions, slots, batch, maximum_slots,
        query_width, kv_heads, packed_width, cache_capacity, epsilon);
  } else if (head_dimension == 512 && key_equals_value) {
    ragged_query_kernel<512><<<batch * query_heads, threads, 0, stream>>>(
        static_cast<const __nv_bfloat16*>(packed_qkv),
        static_cast<const __nv_bfloat16*>(query_norm_weight), implementation_->global_cosine,
        implementation_->global_sine, static_cast<__nv_bfloat16*>(queries), positions,
        batch, query_heads, packed_width, epsilon);
    ragged_key_value_kernel<512, true><<<batch * kv_heads, threads, 0, stream>>>(
        static_cast<const __nv_bfloat16*>(packed_qkv),
        static_cast<const __nv_bfloat16*>(key_norm_weight), implementation_->global_cosine,
        implementation_->global_sine, static_cast<__nv_bfloat16*>(key_cache),
        static_cast<__nv_bfloat16*>(value_cache), positions, slots, batch, maximum_slots,
        query_width, kv_heads, packed_width, cache_capacity, epsilon);
  } else {
    throw std::runtime_error("unsupported ragged Gemma 4 QKV shape");
  }
  check(cudaPeekAtLastError(), "launch ragged QKV postprocessing");
}

}  // namespace gradiated::engine
