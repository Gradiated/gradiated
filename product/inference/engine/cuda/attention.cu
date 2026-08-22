#include "gradiated/engine/attention.h"

#include <cuda_bf16.h>
#include <cuda_runtime.h>
#include <math_constants.h>

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

template <int head_dimension, int query_group, int tile_tokens>
__global__ void grouped_decode_kernel(const __nv_bfloat16* query, const __nv_bfloat16* key_cache,
                                      const __nv_bfloat16* value_cache, __nv_bfloat16* output,
                                      int kv_heads, int context_length) {
  const int batch_index = static_cast<int>(blockIdx.x) / kv_heads;
  const int kv_head = static_cast<int>(blockIdx.x) % kv_heads;
  const std::uint64_t cache_base =
      (static_cast<std::uint64_t>(batch_index) * kv_heads + kv_head) * context_length * head_dimension;
  const std::uint64_t query_base =
      (static_cast<std::uint64_t>(batch_index) * kv_heads + kv_head) * query_group * head_dimension;

  extern __shared__ __align__(16) unsigned char storage[];
  auto* shared_query = reinterpret_cast<__nv_bfloat16*>(storage);
  auto* shared_key = shared_query + query_group * head_dimension;
  auto* shared_value = shared_key + tile_tokens * head_dimension;
  auto* scores = reinterpret_cast<float*>(shared_value + tile_tokens * head_dimension);
  __shared__ float running_max[query_group];
  __shared__ float running_sum[query_group];
  __shared__ float old_scale[query_group];

  for (int index = threadIdx.x; index < query_group * head_dimension; index += threads) {
    shared_query[index] = query[query_base + index];
  }
  if (threadIdx.x < query_group) {
    running_max[threadIdx.x] = -CUDART_INF_F;
    running_sum[threadIdx.x] = 0.0F;
  }
  constexpr int dimensions_per_thread = (head_dimension + threads - 1) / threads;
  float accumulator[query_group][dimensions_per_thread]{};
  __syncthreads();

  for (int tile_begin = 0; tile_begin < context_length; tile_begin += tile_tokens) {
    const int valid_tokens = min(tile_tokens, context_length - tile_begin);
    const int tile_elements = valid_tokens * head_dimension;
    for (int index = threadIdx.x; index < tile_elements; index += threads) {
      const int token = index / head_dimension;
      const int dimension = index % head_dimension;
      const std::uint64_t cache_index = cache_base +
          static_cast<std::uint64_t>(tile_begin + token) * head_dimension + dimension;
      shared_key[index] = key_cache[cache_index];
      shared_value[index] = value_cache[cache_index];
    }
    __syncthreads();

    const int score_count = query_group * valid_tokens;
    if (threadIdx.x < score_count) {
      const int query_index = threadIdx.x / valid_tokens;
      const int token = threadIdx.x % valid_tokens;
      float sum0 = 0.0F, sum1 = 0.0F, sum2 = 0.0F, sum3 = 0.0F;
      int dimension = 0;
      for (; dimension + 3 < head_dimension; dimension += 4) {
        sum0 += __bfloat162float(shared_query[query_index * head_dimension + dimension]) *
                __bfloat162float(shared_key[token * head_dimension + dimension]);
        sum1 += __bfloat162float(shared_query[query_index * head_dimension + dimension + 1]) *
                __bfloat162float(shared_key[token * head_dimension + dimension + 1]);
        sum2 += __bfloat162float(shared_query[query_index * head_dimension + dimension + 2]) *
                __bfloat162float(shared_key[token * head_dimension + dimension + 2]);
        sum3 += __bfloat162float(shared_query[query_index * head_dimension + dimension + 3]) *
                __bfloat162float(shared_key[token * head_dimension + dimension + 3]);
      }
      scores[query_index * tile_tokens + token] = (sum0 + sum1) + (sum2 + sum3);
    }
    __syncthreads();

    if (threadIdx.x < query_group) {
      const int query_index = threadIdx.x;
      float tile_max = -CUDART_INF_F;
      for (int token = 0; token < valid_tokens; ++token) {
        tile_max = max(tile_max, scores[query_index * tile_tokens + token]);
      }
      const float next_max = max(running_max[query_index], tile_max);
      const float alpha = expf(running_max[query_index] - next_max);
      float tile_sum = 0.0F;
      for (int token = 0; token < valid_tokens; ++token) {
        const float probability = expf(scores[query_index * tile_tokens + token] - next_max);
        scores[query_index * tile_tokens + token] = probability;
        tile_sum += probability;
      }
      old_scale[query_index] = alpha;
      running_sum[query_index] = running_sum[query_index] * alpha + tile_sum;
      running_max[query_index] = next_max;
    }
    __syncthreads();

    #pragma unroll
    for (int query_index = 0; query_index < query_group; ++query_index) {
      #pragma unroll
      for (int dimension_slot = 0; dimension_slot < dimensions_per_thread; ++dimension_slot) {
        const int dimension = threadIdx.x + dimension_slot * threads;
        if (dimension >= head_dimension) continue;
        float value = accumulator[query_index][dimension_slot] * old_scale[query_index];
        for (int token = 0; token < valid_tokens; ++token) {
          value += scores[query_index * tile_tokens + token] *
                   __bfloat162float(shared_value[token * head_dimension + dimension]);
        }
        accumulator[query_index][dimension_slot] = value;
      }
    }
    __syncthreads();
  }

  #pragma unroll
  for (int query_index = 0; query_index < query_group; ++query_index) {
    #pragma unroll
    for (int dimension_slot = 0; dimension_slot < dimensions_per_thread; ++dimension_slot) {
      const int dimension = threadIdx.x + dimension_slot * threads;
      if (dimension < head_dimension) {
        output[query_base + query_index * head_dimension + dimension] =
            __float2bfloat16_rn(accumulator[query_index][dimension_slot] / running_sum[query_index]);
      }
    }
  }
}

template <int head_dimension, int query_group, int tile_tokens>
void launch(const void* query, const void* key_cache, const void* value_cache, void* output,
            int batch, int kv_heads, int context_length, cudaStream_t stream) {
  const std::size_t shared_bytes = sizeof(__nv_bfloat16) *
      (query_group * head_dimension + 2 * tile_tokens * head_dimension) +
      sizeof(float) * query_group * tile_tokens;
  check(cudaFuncSetAttribute(grouped_decode_kernel<head_dimension, query_group, tile_tokens>,
                             cudaFuncAttributeMaxDynamicSharedMemorySize,
                             static_cast<int>(shared_bytes)),
        "set grouped attention shared memory");
  grouped_decode_kernel<head_dimension, query_group, tile_tokens>
      <<<batch * kv_heads, threads, shared_bytes, stream>>>(
          static_cast<const __nv_bfloat16*>(query), static_cast<const __nv_bfloat16*>(key_cache),
          static_cast<const __nv_bfloat16*>(value_cache), static_cast<__nv_bfloat16*>(output),
          kv_heads, context_length);
  check(cudaPeekAtLastError(), "launch grouped decode attention");
}

}  // namespace

void grouped_decode_attention_bf16(const void* query, const void* key_cache, const void* value_cache,
                                   void* output, int batch, int kv_heads, int query_group,
                                   int context_length, int head_dimension, cudaStream_t stream) {
  if (batch <= 0 || kv_heads <= 0 || context_length <= 0) {
    throw std::runtime_error("invalid grouped attention shape");
  }
  if (head_dimension == 256 && query_group == 2) {
    launch<256, 2, 64>(query, key_cache, value_cache, output, batch, kv_heads, context_length, stream);
  } else if (head_dimension == 512 && query_group == 8) {
    launch<512, 8, 32>(query, key_cache, value_cache, output, batch, kv_heads, context_length, stream);
  } else {
    throw std::runtime_error("unsupported grouped attention head shape");
  }
}

}  // namespace gradiated::engine
