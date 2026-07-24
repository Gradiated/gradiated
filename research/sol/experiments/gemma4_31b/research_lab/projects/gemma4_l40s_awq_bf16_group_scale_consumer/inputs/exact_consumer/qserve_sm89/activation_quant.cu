#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAException.h>
#include <cuda_bf16.h>
#include <cuda_fp16.h>
#include <torch/extension.h>

namespace {

constexpr int kThreads = 256;

__device__ float block_max(float value, float *scratch) {
  scratch[threadIdx.x] = value;
  __syncthreads();
  for (int stride = blockDim.x / 2; stride > 0; stride >>= 1) {
    if (threadIdx.x < stride) {
      scratch[threadIdx.x] = fmaxf(scratch[threadIdx.x], scratch[threadIdx.x + stride]);
    }
    __syncthreads();
  }
  return scratch[0];
}

__device__ int8_t quantize_s8(float value, float inverse_scale) {
  int quantized = __float2int_rn(value * inverse_scale);
  quantized = max(-127, min(127, quantized));
  return static_cast<int8_t>(quantized);
}

__device__ float gelu_tanh(float value) {
  constexpr float kAlpha = 0.7978845608028654f;
  return 0.5f * value *
      (1.0f + tanhf(kAlpha * (value + 0.044715f * value * value * value)));
}

__global__ void quantize_bf16_s8_kernel(
    const __nv_bfloat16 *__restrict__ input,
    int8_t *__restrict__ output,
    half *__restrict__ scales,
    int rows,
    int columns) {
  int row = blockIdx.x;
  if (row >= rows) {
    return;
  }
  extern __shared__ float scratch[];
  float local_max = 0.0f;
  for (int column = threadIdx.x; column < columns; column += blockDim.x) {
    local_max = fmaxf(
        local_max,
        fabsf(__bfloat162float(input[static_cast<int64_t>(row) * columns + column])));
  }
  float absolute_max = block_max(local_max, scratch);
  float scale = absolute_max > 0.0f ? absolute_max / 127.0f : 1.0f;
  if (threadIdx.x == 0) {
    scales[row] = __float2half_rn(scale);
  }
  float inverse_scale = 1.0f / scale;
  for (int column = threadIdx.x; column < columns; column += blockDim.x) {
    float value =
        __bfloat162float(input[static_cast<int64_t>(row) * columns + column]);
    output[static_cast<int64_t>(row) * columns + column] =
        quantize_s8(value, inverse_scale);
  }
}

__global__ void gelu_mul_quant_s8_kernel(
    const __nv_bfloat16 *__restrict__ input,
    int8_t *__restrict__ output,
    half *__restrict__ scales,
    int rows,
    int intermediate) {
  int row = blockIdx.x;
  if (row >= rows) {
    return;
  }
  extern __shared__ float scratch[];
  int64_t row_offset = static_cast<int64_t>(row) * 2 * intermediate;
  float local_max = 0.0f;
  for (int column = threadIdx.x; column < intermediate; column += blockDim.x) {
    float gate = __bfloat162float(input[row_offset + column]);
    float up = __bfloat162float(input[row_offset + intermediate + column]);
    local_max = fmaxf(local_max, fabsf(gelu_tanh(gate) * up));
  }
  float absolute_max = block_max(local_max, scratch);
  float scale = absolute_max > 0.0f ? absolute_max / 127.0f : 1.0f;
  if (threadIdx.x == 0) {
    scales[row] = __float2half_rn(scale);
  }
  float inverse_scale = 1.0f / scale;
  for (int column = threadIdx.x; column < intermediate; column += blockDim.x) {
    float gate = __bfloat162float(input[row_offset + column]);
    float up = __bfloat162float(input[row_offset + intermediate + column]);
    output[static_cast<int64_t>(row) * intermediate + column] =
        quantize_s8(gelu_tanh(gate) * up, inverse_scale);
  }
}

}  // namespace

void quantize_bf16_s8_cuda(
    torch::Tensor input,
    torch::Tensor output,
    torch::Tensor scales) {
  TORCH_CHECK(input.is_cuda() && input.is_contiguous(), "input must be contiguous CUDA");
  TORCH_CHECK(output.is_cuda() && output.is_contiguous(), "output must be contiguous CUDA");
  TORCH_CHECK(scales.is_cuda() && scales.is_contiguous(), "scales must be contiguous CUDA");
  TORCH_CHECK(input.scalar_type() == torch::kBFloat16, "input must be bfloat16");
  TORCH_CHECK(output.scalar_type() == torch::kInt8, "output must be int8");
  TORCH_CHECK(scales.scalar_type() == torch::kFloat16, "scales must be float16");
  TORCH_CHECK(input.dim() == 2, "input must be rank 2");
  TORCH_CHECK(input.size(0) > 0 && input.size(0) <= 32, "M must be in [1,32]");
  TORCH_CHECK(output.sizes() == input.sizes(), "output shape mismatch");
  TORCH_CHECK(scales.numel() == input.size(0), "scale shape mismatch");
  cudaStream_t stream = at::cuda::getCurrentCUDAStream();
  quantize_bf16_s8_kernel<<<input.size(0), kThreads, kThreads * sizeof(float), stream>>>(
      reinterpret_cast<const __nv_bfloat16 *>(input.data_ptr<at::BFloat16>()),
      output.data_ptr<int8_t>(),
      reinterpret_cast<half *>(scales.data_ptr<at::Half>()),
      input.size(0),
      input.size(1));
  C10_CUDA_KERNEL_LAUNCH_CHECK();
}

void gelu_mul_quant_s8_cuda(
    torch::Tensor input,
    torch::Tensor output,
    torch::Tensor scales) {
  TORCH_CHECK(input.is_cuda() && input.is_contiguous(), "input must be contiguous CUDA");
  TORCH_CHECK(output.is_cuda() && output.is_contiguous(), "output must be contiguous CUDA");
  TORCH_CHECK(scales.is_cuda() && scales.is_contiguous(), "scales must be contiguous CUDA");
  TORCH_CHECK(input.scalar_type() == torch::kBFloat16, "input must be bfloat16");
  TORCH_CHECK(output.scalar_type() == torch::kInt8, "output must be int8");
  TORCH_CHECK(scales.scalar_type() == torch::kFloat16, "scales must be float16");
  TORCH_CHECK(input.dim() == 2, "input must be rank 2");
  TORCH_CHECK(input.size(0) > 0 && input.size(0) <= 32, "M must be in [1,32]");
  TORCH_CHECK(input.size(1) % 2 == 0, "gate/up width must be even");
  int64_t intermediate = input.size(1) / 2;
  TORCH_CHECK(
      output.size(0) == input.size(0) && output.size(1) == intermediate,
      "output shape mismatch");
  TORCH_CHECK(scales.numel() == input.size(0), "scale shape mismatch");
  cudaStream_t stream = at::cuda::getCurrentCUDAStream();
  gelu_mul_quant_s8_kernel<<<input.size(0), kThreads, kThreads * sizeof(float), stream>>>(
      reinterpret_cast<const __nv_bfloat16 *>(
          input.data_ptr<at::BFloat16>()),
      output.data_ptr<int8_t>(),
      reinterpret_cast<half *>(scales.data_ptr<at::Half>()),
      input.size(0),
      intermediate);
  C10_CUDA_KERNEL_LAUNCH_CHECK();
}
