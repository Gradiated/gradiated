#include "gradiated/engine/prefill_gemm_attention.h"

#include <cublas_v2.h>
#include <cuda_bf16.h>
#include <cuda_runtime.h>
#include <math_constants.h>

#include <algorithm>
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

__global__ void causal_softmax_kernel(__nv_bfloat16* scores, int tokens) {
  __shared__ float warp_values[32];
  const int query_position = static_cast<int>(blockIdx.x) % tokens;
  __nv_bfloat16* row = scores + static_cast<std::uint64_t>(blockIdx.x) * tokens;
  float maximum = -CUDART_INF_F;
  for (int key_position = threadIdx.x; key_position <= query_position; key_position += blockDim.x) {
    maximum = max(maximum, __bfloat162float(row[key_position]));
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
  for (int key_position = threadIdx.x; key_position <= query_position; key_position += blockDim.x) {
    sum += expf(__bfloat162float(row[key_position]) - maximum);
  }
  sum = warp_sum(sum);
  if ((threadIdx.x & 31U) == 0U) warp_values[threadIdx.x >> 5U] = sum;
  __syncthreads();
  sum = threadIdx.x < (blockDim.x + 31U) / 32U ? warp_values[threadIdx.x] : 0.0F;
  if (threadIdx.x < 32U) sum = warp_sum(sum);
  if (threadIdx.x == 0U) warp_values[0] = 1.0F / sum;
  __syncthreads();
  const float inverse_sum = warp_values[0];
  for (int key_position = threadIdx.x; key_position < tokens; key_position += blockDim.x) {
    const float probability = key_position <= query_position
        ? expf(__bfloat162float(row[key_position]) - maximum) * inverse_sum : 0.0F;
    row[key_position] = __float2bfloat16_rn(probability);
  }
}

}  // namespace

struct GemmCausalPrefillAttention::Implementation {
  cublasHandle_t handle{};
  void* scores{nullptr};
  std::uint64_t maximum_score_elements;

  Implementation(int maximum_tokens, int maximum_query_heads)
      : maximum_score_elements(static_cast<std::uint64_t>(maximum_query_heads) *
                               maximum_tokens * maximum_tokens) {
    if (maximum_tokens <= 0 || maximum_query_heads <= 0) {
      throw std::runtime_error("invalid global prefill workspace shape");
    }
    cublas_check(cublasCreate(&handle), "create global prefill cuBLAS handle");
    cuda_check(cudaMalloc(&scores, static_cast<std::size_t>(2ULL * maximum_score_elements)),
               "allocate global prefill scores");
  }

  ~Implementation() {
    if (scores != nullptr) cudaFree(scores);
    if (handle != nullptr) cublasDestroy(handle);
  }
};

GemmCausalPrefillAttention::GemmCausalPrefillAttention(int maximum_tokens, int maximum_query_heads)
    : implementation_(std::make_unique<Implementation>(maximum_tokens, maximum_query_heads)) {}
GemmCausalPrefillAttention::~GemmCausalPrefillAttention() = default;

void GemmCausalPrefillAttention::run(const void* query, const void* key, const void* value,
                                     void* output, int query_heads, int kv_heads, int tokens,
                                     int head_dimension, cudaStream_t stream) {
  const std::uint64_t score_elements = static_cast<std::uint64_t>(query_heads) * tokens * tokens;
  if (query == nullptr || key == nullptr || value == nullptr || output == nullptr ||
      query_heads <= 0 || kv_heads <= 0 || query_heads % kv_heads != 0 || tokens <= 0 ||
      head_dimension <= 0 || score_elements > implementation_->maximum_score_elements) {
    throw std::runtime_error("invalid global prefill attention shape");
  }
  auto& state = *implementation_;
  cublas_check(cublasSetStream(state.handle, stream), "set global prefill stream");
  constexpr float alpha = 1.0F;
  constexpr float beta = 0.0F;
  const int query_group = query_heads / kv_heads;
  const std::int64_t head_elements = static_cast<std::int64_t>(tokens) * head_dimension;
  const std::int64_t score_head_elements = static_cast<std::int64_t>(tokens) * tokens;
  for (int kv_head = 0; kv_head < kv_heads; ++kv_head) {
    const auto* key_head = static_cast<const unsigned char*>(key) + 2ULL * kv_head * head_elements;
    const auto* query_group_begin = static_cast<const unsigned char*>(query) +
                                    2ULL * kv_head * query_group * head_elements;
    auto* score_group = static_cast<unsigned char*>(state.scores) +
                        2ULL * kv_head * query_group * score_head_elements;
    cublas_check(cublasGemmStridedBatchedEx(
        state.handle, CUBLAS_OP_T, CUBLAS_OP_N, tokens, tokens, head_dimension, &alpha,
        key_head, CUDA_R_16BF, head_dimension, 0,
        query_group_begin, CUDA_R_16BF, head_dimension, head_elements,
        &beta, score_group, CUDA_R_16BF, tokens, score_head_elements,
        query_group, CUBLAS_COMPUTE_32F, CUBLAS_GEMM_DEFAULT_TENSOR_OP),
        "global prefill QK GEMM");
  }
  causal_softmax_kernel<<<query_heads * tokens, 256, 0, stream>>>(
      static_cast<__nv_bfloat16*>(state.scores), tokens);
  cuda_check(cudaPeekAtLastError(), "launch global prefill causal softmax");
  for (int kv_head = 0; kv_head < kv_heads; ++kv_head) {
    const auto* value_head = static_cast<const unsigned char*>(value) + 2ULL * kv_head * head_elements;
    const auto* score_group = static_cast<const unsigned char*>(state.scores) +
                              2ULL * kv_head * query_group * score_head_elements;
    auto* output_group = static_cast<unsigned char*>(output) +
                         2ULL * kv_head * query_group * head_elements;
    cublas_check(cublasGemmStridedBatchedEx(
        state.handle, CUBLAS_OP_N, CUBLAS_OP_N, head_dimension, tokens, tokens, &alpha,
        value_head, CUDA_R_16BF, head_dimension, 0,
        score_group, CUDA_R_16BF, tokens, score_head_elements,
        &beta, output_group, CUDA_R_16BF, head_dimension, head_elements,
        query_group, CUBLAS_COMPUTE_32F, CUBLAS_GEMM_DEFAULT_TENSOR_OP),
        "global prefill PV GEMM");
  }
}

}  // namespace gradiated::engine
