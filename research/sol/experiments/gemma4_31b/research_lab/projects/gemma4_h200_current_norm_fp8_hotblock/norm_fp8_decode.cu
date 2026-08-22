#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAGuard.h>
#include <c10/cuda/CUDAException.h>
#include <cuda_bf16.h>
#include <cuda_fp8.h>
#include <torch/extension.h>

#include <cmath>
#include <tuple>

namespace {

constexpr int kHidden = 5376;
constexpr int kMaximumRows = 32;
constexpr int kThreads = 256;
constexpr float kFp8Maximum = 448.0f;

__device__ __forceinline__ float warp_sum(float value) {
  for (int offset = 16; offset > 0; offset /= 2) {
    value += __shfl_down_sync(0xffffffff, value, offset);
  }
  return value;
}

__device__ __forceinline__ float warp_max(float value) {
  for (int offset = 16; offset > 0; offset /= 2) {
    value = fmaxf(value, __shfl_down_sync(0xffffffff, value, offset));
  }
  return value;
}

__device__ __forceinline__ float block_sum(float value) {
  __shared__ float warp_values[8];
  const int lane = threadIdx.x & 31;
  const int warp = threadIdx.x >> 5;
  value = warp_sum(value);
  if (lane == 0) {
    warp_values[warp] = value;
  }
  __syncthreads();
  value = threadIdx.x < 8 ? warp_values[lane] : 0.0f;
  return warp_sum(value);
}

__device__ __forceinline__ float block_max(float value) {
  __shared__ float warp_values[8];
  const int lane = threadIdx.x & 31;
  const int warp = threadIdx.x >> 5;
  value = warp_max(value);
  if (lane == 0) {
    warp_values[warp] = value;
  }
  __syncthreads();
  value = threadIdx.x < 8 ? warp_values[lane] : 0.0f;
  return warp_max(value);
}

__global__ void gemma4_decode_rmsnorm_quant_e4m3(
    const __nv_bfloat16* __restrict__ input,
    const __nv_bfloat16* __restrict__ weight,
    __nv_fp8_e4m3* __restrict__ output,
    float* __restrict__ scales,
    float epsilon) {
  const int64_t row = blockIdx.x;
  const int64_t row_offset = row * kHidden;
  float local_square_sum = 0.0f;

  for (int column = threadIdx.x; column < kHidden; column += blockDim.x) {
    const float value = __bfloat162float(input[row_offset + column]);
    local_square_sum += value * value;
  }

  const float square_sum = block_sum(local_square_sum);
  __shared__ float inverse_rms;
  if (threadIdx.x == 0) {
    inverse_rms =
        rsqrtf(square_sum / static_cast<float>(kHidden) + epsilon);
  }
  __syncthreads();

  float local_maximum = 0.0f;
  for (int column = threadIdx.x; column < kHidden; column += blockDim.x) {
    const float value = __bfloat162float(input[row_offset + column]);
    const float normalized = __bfloat162float(__float2bfloat16_rn(
        value * inverse_rms * __bfloat162float(weight[column])));
    local_maximum = fmaxf(local_maximum, fabsf(normalized));
  }

  const float maximum = block_max(local_maximum);
  __shared__ float scale;
  if (threadIdx.x == 0) {
    scale = maximum / kFp8Maximum;
    scales[row] = scale;
  }
  __syncthreads();

  const float inverse_scale = scale == 0.0f ? 0.0f : 1.0f / scale;
  for (int column = threadIdx.x; column < kHidden; column += blockDim.x) {
    const float value = __bfloat162float(input[row_offset + column]);
    const float normalized = __bfloat162float(__float2bfloat16_rn(
        value * inverse_rms * __bfloat162float(weight[column])));
    const float unbounded = normalized * inverse_scale;
    const float bounded =
        fmaxf(fminf(unbounded, kFp8Maximum), -kFp8Maximum);
    output[row_offset + column] = static_cast<__nv_fp8_e4m3>(bounded);
  }
}

void validate(
    const torch::Tensor& input,
    const torch::Tensor& weight,
    double epsilon) {
  TORCH_CHECK(input.is_cuda(), "input must be CUDA");
  TORCH_CHECK(
      input.scalar_type() == at::ScalarType::BFloat16,
      "input must be bfloat16");
  TORCH_CHECK(
      input.dim() == 2 && input.size(1) == kHidden,
      "input must have shape [M, 5376]");
  TORCH_CHECK(
      input.size(0) >= 1 && input.size(0) <= kMaximumRows,
      "decode candidate requires 1 <= M <= 32");
  TORCH_CHECK(input.is_contiguous(), "input must be contiguous");
  TORCH_CHECK(weight.is_cuda(), "weight must be CUDA");
  TORCH_CHECK(
      weight.scalar_type() == at::ScalarType::BFloat16,
      "weight must be bfloat16");
  TORCH_CHECK(
      weight.dim() == 1 && weight.numel() == kHidden,
      "weight must have shape [5376]");
  TORCH_CHECK(weight.is_contiguous(), "weight must be contiguous");
  TORCH_CHECK(
      input.get_device() == weight.get_device(),
      "input and weight must be on the same device");
  TORCH_CHECK(
      std::isfinite(epsilon) && epsilon > 0.0,
      "epsilon must be finite and positive");
}

}  // namespace

std::tuple<torch::Tensor, torch::Tensor> gemma4_decode_norm_fp8(
    const torch::Tensor& input,
    const torch::Tensor& weight,
    double epsilon) {
  validate(input, weight, epsilon);
  c10::cuda::CUDAGuard guard(input.device());
  auto quantized = torch::empty(
      input.sizes(),
      input.options().dtype(at::ScalarType::Float8_e4m3fn));
  auto scales = torch::empty(
      {input.size(0), 1},
      input.options().dtype(at::ScalarType::Float));
  const auto stream = at::cuda::getCurrentCUDAStream(input.get_device());
  gemma4_decode_rmsnorm_quant_e4m3
      <<<input.size(0), kThreads, 0, stream>>>(
          reinterpret_cast<const __nv_bfloat16*>(input.data_ptr()),
          reinterpret_cast<const __nv_bfloat16*>(weight.data_ptr()),
          reinterpret_cast<__nv_fp8_e4m3*>(quantized.data_ptr()),
          scales.data_ptr<float>(),
          static_cast<float>(epsilon));
  C10_CUDA_KERNEL_LAUNCH_CHECK();
  return {quantized, scales};
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def("gemma4_decode_norm_fp8", &gemma4_decode_norm_fp8);
}
