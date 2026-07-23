#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAGuard.h>
#include <c10/cuda/CUDAException.h>
#include <cuda_bf16.h>
#include <cuda_fp8.h>
#include <torch/extension.h>

#include <cmath>
#include <tuple>

namespace {

constexpr int kThreads = 256;
constexpr int kHidden = 5376;
constexpr float kFp8Max = 448.0f;

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

template <bool AddResidual>
__global__ void rmsnorm_quant_kernel(
    const __nv_bfloat16* __restrict__ input,
    const __nv_bfloat16* __restrict__ weight,
    __nv_bfloat16* __restrict__ residual,
    __nv_fp8_e4m3* __restrict__ output,
    float* __restrict__ scales,
    float epsilon) {
  const int64_t row = blockIdx.x;
  const int64_t offset = row * kHidden;
  float local_sum = 0.0f;

  for (int column = threadIdx.x; column < kHidden; column += blockDim.x) {
    float value = __bfloat162float(input[offset + column]);
    if constexpr (AddResidual) {
      value += __bfloat162float(residual[offset + column]);
      const __nv_bfloat16 rounded = __float2bfloat16_rn(value);
      residual[offset + column] = rounded;
      value = __bfloat162float(rounded);
    }
    local_sum += value * value;
  }

  const float sum = block_sum(local_sum);
  __shared__ float inverse_rms;
  if (threadIdx.x == 0) {
    inverse_rms = rsqrtf(sum / static_cast<float>(kHidden) + epsilon);
  }
  __syncthreads();

  float local_max = 0.0f;
  for (int column = threadIdx.x; column < kHidden; column += blockDim.x) {
    const float value = AddResidual
        ? __bfloat162float(residual[offset + column])
        : __bfloat162float(input[offset + column]);
    const __nv_bfloat16 normalized = __float2bfloat16_rn(
        value * inverse_rms * __bfloat162float(weight[column]));
    local_max = fmaxf(local_max, fabsf(__bfloat162float(normalized)));
  }

  const float maximum = block_max(local_max);
  __shared__ float scale;
  if (threadIdx.x == 0) {
    scale = maximum / kFp8Max;
    scales[row] = scale;
  }
  __syncthreads();

  const float inverse_scale = scale == 0.0f ? 0.0f : 1.0f / scale;
  for (int column = threadIdx.x; column < kHidden; column += blockDim.x) {
    const float value = AddResidual
        ? __bfloat162float(residual[offset + column])
        : __bfloat162float(input[offset + column]);
    const __nv_bfloat16 normalized = __float2bfloat16_rn(
        value * inverse_rms * __bfloat162float(weight[column]));
    float quantized = __bfloat162float(normalized) * inverse_scale;
    quantized = fmaxf(fminf(quantized, kFp8Max), -kFp8Max);
    output[offset + column] = static_cast<__nv_fp8_e4m3>(quantized);
  }
}

void validate(const torch::Tensor& input, const torch::Tensor& weight) {
  TORCH_CHECK(input.is_cuda(), "input must be CUDA");
  TORCH_CHECK(input.scalar_type() == at::ScalarType::BFloat16, "input must be bfloat16");
  TORCH_CHECK(input.dim() == 2 && input.size(1) == kHidden, "expected [M, 5376] input");
  TORCH_CHECK(input.is_contiguous(), "input must be contiguous");
  TORCH_CHECK(weight.is_cuda(), "weight must be CUDA");
  TORCH_CHECK(weight.scalar_type() == at::ScalarType::BFloat16, "weight must be bfloat16");
  TORCH_CHECK(weight.dim() == 1 && weight.numel() == kHidden, "expected [5376] weight");
  TORCH_CHECK(weight.is_contiguous(), "weight must be contiguous");
}

std::tuple<torch::Tensor, torch::Tensor> allocate_outputs(const torch::Tensor& input) {
  const auto rows = input.size(0);
  auto quantized = torch::empty(
      {rows, kHidden}, input.options().dtype(at::ScalarType::Float8_e4m3fn));
  auto scales = torch::empty({rows, 1}, input.options().dtype(at::ScalarType::Float));
  return {quantized, scales};
}

}  // namespace

std::tuple<torch::Tensor, torch::Tensor> rmsnorm_quant(
    const torch::Tensor& input,
    const torch::Tensor& weight,
    double epsilon) {
  validate(input, weight);
  c10::cuda::CUDAGuard guard(input.device());
  auto [quantized, scales] = allocate_outputs(input);
  const auto stream = at::cuda::getCurrentCUDAStream(input.get_device());
  rmsnorm_quant_kernel<false><<<input.size(0), kThreads, 0, stream>>>(
      reinterpret_cast<const __nv_bfloat16*>(input.data_ptr()),
      reinterpret_cast<const __nv_bfloat16*>(weight.data_ptr()),
      nullptr,
      reinterpret_cast<__nv_fp8_e4m3*>(quantized.data_ptr()),
      scales.data_ptr<float>(),
      static_cast<float>(epsilon));
  C10_CUDA_KERNEL_LAUNCH_CHECK();
  return {quantized, scales};
}

std::tuple<torch::Tensor, torch::Tensor, torch::Tensor> fused_add_rmsnorm_quant(
    const torch::Tensor& input,
    torch::Tensor residual,
    const torch::Tensor& weight,
    double epsilon) {
  validate(input, weight);
  TORCH_CHECK(residual.is_cuda(), "residual must be CUDA");
  TORCH_CHECK(residual.scalar_type() == at::ScalarType::BFloat16, "residual must be bfloat16");
  TORCH_CHECK(residual.sizes() == input.sizes(), "residual shape mismatch");
  TORCH_CHECK(residual.is_contiguous(), "residual must be contiguous");
  c10::cuda::CUDAGuard guard(input.device());
  auto [quantized, scales] = allocate_outputs(input);
  const auto stream = at::cuda::getCurrentCUDAStream(input.get_device());
  rmsnorm_quant_kernel<true><<<input.size(0), kThreads, 0, stream>>>(
      reinterpret_cast<const __nv_bfloat16*>(input.data_ptr()),
      reinterpret_cast<const __nv_bfloat16*>(weight.data_ptr()),
      reinterpret_cast<__nv_bfloat16*>(residual.data_ptr()),
      reinterpret_cast<__nv_fp8_e4m3*>(quantized.data_ptr()),
      scales.data_ptr<float>(),
      static_cast<float>(epsilon));
  C10_CUDA_KERNEL_LAUNCH_CHECK();
  return {quantized, scales, residual};
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def("rmsnorm_quant", &rmsnorm_quant);
  module.def("fused_add_rmsnorm_quant", &fused_add_rmsnorm_quant);
}
