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

}  // namespace

struct GemmGroupedDecodeAttention::Implementation {
  cublasHandle_t handle{};
  void* scores{nullptr};
  std::uint64_t maximum_score_elements;

  Implementation(int batch, int kv_heads, int query_group, int context)
      : maximum_score_elements(static_cast<std::uint64_t>(batch) * kv_heads * query_group * context) {
    if (batch <= 0 || kv_heads <= 0 || query_group <= 0 || context <= 0) {
      throw std::runtime_error("invalid maximum attention shape");
    }
    cublas_check(cublasCreate(&handle), "cublasCreate attention");
    cuda_check(cudaMalloc(&scores, static_cast<std::size_t>(maximum_score_elements * 2ULL)),
               "allocate attention score workspace");
  }
  ~Implementation() {
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

}  // namespace gradiated::engine
