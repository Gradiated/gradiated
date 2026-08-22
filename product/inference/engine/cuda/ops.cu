#include "gradiated/engine/cuda_ops.h"

#include <cuda_bf16.h>
#include <cuda_runtime.h>
#include <math_constants.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>

namespace gradiated::engine {
namespace {

void check(cudaError_t result, const char* operation) {
  if (result != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(result));
  }
}

__global__ void rms_norm_kernel(const __nv_bfloat16* input, const __nv_bfloat16* weight,
                                const __nv_bfloat16* residual, __nv_bfloat16* output,
                                std::size_t width, float epsilon) {
  const std::size_t row = blockIdx.x;
  const __nv_bfloat16* row_input = input + row * width;
  __nv_bfloat16* row_output = output + row * width;
  float square_sum = 0.0F;
  for (std::size_t column = threadIdx.x; column < width; column += blockDim.x) {
    const float value = __bfloat162float(row_input[column]);
    square_sum += value * value;
  }
  for (unsigned offset = 16; offset > 0; offset >>= 1U) {
    square_sum += __shfl_down_sync(0xffffffffU, square_sum, offset);
  }
  __shared__ float warp_sums[32];
  if ((threadIdx.x & 31U) == 0U) warp_sums[threadIdx.x >> 5U] = square_sum;
  __syncthreads();
  if (threadIdx.x < 32U) {
    square_sum = threadIdx.x < (blockDim.x + 31U) / 32U ? warp_sums[threadIdx.x] : 0.0F;
    for (unsigned offset = 16; offset > 0; offset >>= 1U) {
      square_sum += __shfl_down_sync(0xffffffffU, square_sum, offset);
    }
    if (threadIdx.x == 0U) warp_sums[0] = rsqrtf(square_sum / static_cast<float>(width) + epsilon);
  }
  __syncthreads();
  const float inverse_rms = warp_sums[0];
  for (std::size_t column = threadIdx.x; column < width; column += blockDim.x) {
    const float value = __bfloat162float(row_input[column]);
    const float scale = __bfloat162float(weight[column]);
    float result = value * inverse_rms * scale;
    if (residual != nullptr) result += __bfloat162float(residual[row * width + column]);
    row_output[column] = __float2bfloat16_rn(result);
  }
}

__global__ void scale_kernel(__nv_bfloat16* values, const __nv_bfloat16* scalar,
                             std::size_t elements) {
  const std::size_t index = static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < elements) {
    values[index] = __float2bfloat16_rn(__bfloat162float(values[index]) * __bfloat162float(*scalar));
  }
}

__device__ float gelu_tanh(float value) {
  constexpr float coefficient = 0.7978845608028654F;
  return 0.5F * value * (1.0F + tanhf(coefficient * (value + 0.044715F * value * value * value)));
}

__global__ void gelu_tanh_gate_kernel(const __nv_bfloat16* gate, const __nv_bfloat16* up,
                                      __nv_bfloat16* output, std::size_t elements) {
  const std::size_t index = static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < elements) {
    output[index] = __float2bfloat16_rn(gelu_tanh(__bfloat162float(gate[index])) *
                                        __bfloat162float(up[index]));
  }
}

__global__ void gelu_tanh_gate_rows_kernel(const __nv_bfloat16* packed, __nv_bfloat16* output,
                                           int rows, int width) {
  const int index = static_cast<int>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < rows * width) {
    const int row = index / width;
    const int column = index % width;
    const std::uint64_t base = static_cast<std::uint64_t>(row) * 2 * width;
    output[index] = __float2bfloat16_rn(gelu_tanh(__bfloat162float(packed[base + column])) *
                                        __bfloat162float(packed[base + width + column]));
  }
}

__global__ void embedding_kernel(const __nv_bfloat16* weight, int token_id,
                                 __nv_bfloat16* output, int hidden_size, __nv_bfloat16 scale) {
  const int index = static_cast<int>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < hidden_size) {
    output[index] = __float2bfloat16_rn(
        __bfloat162float(weight[static_cast<std::size_t>(token_id) * hidden_size + index]) *
        __bfloat162float(scale));
  }
}

__global__ void embedding_batch_kernel(const __nv_bfloat16* weight, const int* token_ids,
                                       __nv_bfloat16* output, int batch, int vocabulary_size,
                                       int hidden_size, __nv_bfloat16 scale) {
  const int index = static_cast<int>(blockIdx.x) * blockDim.x + threadIdx.x;
  if (index < batch * hidden_size) {
    const int row = index / hidden_size;
    const int column = index % hidden_size;
    const int token_id = token_ids[row];
    if (token_id >= 0 && token_id < vocabulary_size) {
      output[index] = __float2bfloat16_rn(
          __bfloat162float(weight[static_cast<std::size_t>(token_id) * hidden_size + column]) *
          __bfloat162float(scale));
    }
  }
}

struct Maximum {
  float value;
  int index;
};

__device__ Maximum better(Maximum left, Maximum right) {
  return right.value > left.value || (right.value == left.value && right.index < left.index) ? right : left;
}

__global__ void argmax_partials_kernel(const __nv_bfloat16* values, int elements, Maximum* partials) {
  Maximum current{-CUDART_INF_F, 0};
  for (int index = static_cast<int>(blockIdx.x) * blockDim.x + threadIdx.x;
       index < elements; index += blockDim.x * gridDim.x) {
    current = better(current, {__bfloat162float(values[index]), index});
  }
  __shared__ Maximum reduction[256];
  reduction[threadIdx.x] = current;
  __syncthreads();
  for (int stride = blockDim.x / 2; stride > 0; stride >>= 1) {
    if (threadIdx.x < stride) reduction[threadIdx.x] = better(reduction[threadIdx.x], reduction[threadIdx.x + stride]);
    __syncthreads();
  }
  if (threadIdx.x == 0) partials[blockIdx.x] = reduction[0];
}

__global__ void argmax_final_kernel(const Maximum* partials, int count, int* output) {
  Maximum current{-CUDART_INF_F, 0};
  for (int index = threadIdx.x; index < count; index += blockDim.x) current = better(current, partials[index]);
  __shared__ Maximum reduction[256];
  reduction[threadIdx.x] = current;
  __syncthreads();
  for (int stride = blockDim.x / 2; stride > 0; stride >>= 1) {
    if (threadIdx.x < stride) reduction[threadIdx.x] = better(reduction[threadIdx.x], reduction[threadIdx.x + stride]);
    __syncthreads();
  }
  if (threadIdx.x == 0) *output = reduction[0].index;
}

}  // namespace

void rms_norm_bf16(const void* input, const void* weight, void* output,
                   std::size_t rows, std::size_t width, float epsilon, cudaStream_t stream) {
  if (rows == 0 || width == 0) return;
  rms_norm_kernel<<<static_cast<unsigned>(rows), 256, 0, stream>>>(
      static_cast<const __nv_bfloat16*>(input), static_cast<const __nv_bfloat16*>(weight),
      nullptr, static_cast<__nv_bfloat16*>(output), width, epsilon);
  check(cudaPeekAtLastError(), "launch rms_norm_kernel");
}

void rms_norm_add_bf16(const void* input, const void* weight, const void* residual, void* output,
                       std::size_t rows, std::size_t width, float epsilon, cudaStream_t stream) {
  if (rows == 0 || width == 0) return;
  rms_norm_kernel<<<static_cast<unsigned>(rows), 256, 0, stream>>>(
      static_cast<const __nv_bfloat16*>(input), static_cast<const __nv_bfloat16*>(weight),
      static_cast<const __nv_bfloat16*>(residual), static_cast<__nv_bfloat16*>(output), width, epsilon);
  check(cudaPeekAtLastError(), "launch rms_norm_add_kernel");
}

void scale_bf16(void* values, const void* scalar, std::size_t elements, cudaStream_t stream) {
  if (elements == 0) return;
  constexpr unsigned threads = 256;
  const auto blocks = static_cast<unsigned>((elements + threads - 1U) / threads);
  scale_kernel<<<blocks, threads, 0, stream>>>(static_cast<__nv_bfloat16*>(values),
      static_cast<const __nv_bfloat16*>(scalar), elements);
  check(cudaPeekAtLastError(), "launch scale_kernel");
}

void gelu_tanh_gate_bf16(const void* gate, const void* up, void* output,
                         std::size_t elements, cudaStream_t stream) {
  if (elements == 0) return;
  constexpr unsigned threads = 256;
  const auto blocks = static_cast<unsigned>((elements + threads - 1U) / threads);
  gelu_tanh_gate_kernel<<<blocks, threads, 0, stream>>>(static_cast<const __nv_bfloat16*>(gate),
      static_cast<const __nv_bfloat16*>(up), static_cast<__nv_bfloat16*>(output), elements);
  check(cudaPeekAtLastError(), "launch gelu_tanh_gate_kernel");
}

void gelu_tanh_gate_rows_bf16(const void* packed_gate_up, void* output,
                              int rows, int width, cudaStream_t stream) {
  if (rows <= 0 || width <= 0) throw std::runtime_error("invalid packed gate/up shape");
  constexpr int block_size = 256;
  const int elements = rows * width;
  gelu_tanh_gate_rows_kernel<<<(elements + block_size - 1) / block_size, block_size, 0, stream>>>(
      static_cast<const __nv_bfloat16*>(packed_gate_up), static_cast<__nv_bfloat16*>(output), rows, width);
  check(cudaPeekAtLastError(), "launch row-wise GELU gate kernel");
}

void embedding_bf16(const void* embedding_weight, int token_id, void* output,
                    int vocabulary_size, int hidden_size, float scale, cudaStream_t stream) {
  if (token_id < 0 || token_id >= vocabulary_size || hidden_size <= 0) {
    throw std::runtime_error("invalid embedding lookup");
  }
  constexpr int block_size = 256;
  embedding_kernel<<<(hidden_size + block_size - 1) / block_size, block_size, 0, stream>>>(
      static_cast<const __nv_bfloat16*>(embedding_weight), token_id,
      static_cast<__nv_bfloat16*>(output), hidden_size, __float2bfloat16_rn(scale));
  check(cudaPeekAtLastError(), "launch embedding kernel");
}

void embedding_batch_bf16(const void* embedding_weight, const int* device_token_ids,
                          void* output, int batch, int vocabulary_size, int hidden_size,
                          float scale, cudaStream_t stream) {
  if (batch <= 0 || device_token_ids == nullptr || vocabulary_size <= 0 || hidden_size <= 0) {
    throw std::runtime_error("invalid batched embedding lookup");
  }
  constexpr int block_size = 256;
  const int elements = batch * hidden_size;
  embedding_batch_kernel<<<(elements + block_size - 1) / block_size, block_size, 0, stream>>>(
      static_cast<const __nv_bfloat16*>(embedding_weight), device_token_ids,
      static_cast<__nv_bfloat16*>(output), batch, vocabulary_size, hidden_size,
      __float2bfloat16_rn(scale));
  check(cudaPeekAtLastError(), "launch batched embedding kernel");
}

std::size_t argmax_bf16_workspace_bytes(int elements) {
  if (elements <= 0) throw std::runtime_error("invalid argmax size");
  const int blocks = std::min(256, (elements + 255) / 256);
  return static_cast<std::size_t>(blocks) * sizeof(Maximum);
}

void argmax_bf16(const void* values, int elements, int* device_output,
                 void* workspace, cudaStream_t stream) {
  if (elements <= 0 || device_output == nullptr || workspace == nullptr) {
    throw std::runtime_error("invalid argmax arguments");
  }
  const int blocks = std::min(256, (elements + 255) / 256);
  auto* partials = static_cast<Maximum*>(workspace);
  argmax_partials_kernel<<<blocks, 256, 0, stream>>>(
      static_cast<const __nv_bfloat16*>(values), elements, partials);
  argmax_final_kernel<<<1, 256, 0, stream>>>(partials, blocks, device_output);
  check(cudaPeekAtLastError(), "launch argmax kernels");
}

}  // namespace gradiated::engine
