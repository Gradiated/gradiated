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
constexpr int kExactWidth = 21504;
constexpr float kFp8Max = 448.0f;
constexpr float kGeluAlpha = 0.044715f;
constexpr float kGeluBeta = 0.7978845608028654f;

__device__ __forceinline__ float warp_max(float value) {
  for (int offset = 16; offset > 0; offset /= 2) {
    value = fmaxf(value, __shfl_down_sync(0xffffffff, value, offset));
  }
  return value;
}

__device__ __forceinline__ float block_max(float value) {
  __shared__ float warp_values[32];
  const int lane = threadIdx.x & 31;
  const int warp = threadIdx.x >> 5;
  value = warp_max(value);
  if (lane == 0) {
    warp_values[warp] = value;
  }
  __syncthreads();
  value = threadIdx.x < blockDim.x / 32 ? warp_values[lane] : 0.0f;
  return warp_max(value);
}

__global__ void fused_gelu_tanh_mul_quant_kernel(
    const __nv_bfloat16* __restrict__ input,
    __nv_fp8_e4m3* __restrict__ output,
    float* __restrict__ scales,
    int64_t width) {
  extern __shared__ __nv_bfloat16 activated[];
  const int64_t row = blockIdx.x;
  const int64_t input_offset = row * width * 2;
  const int64_t output_offset = row * width;

  float local_max = 0.0f;
  for (int64_t column = threadIdx.x; column < width; column += blockDim.x) {
    const float gate = __bfloat162float(input[input_offset + column]);
    const float up = __bfloat162float(input[input_offset + width + column]);
    const float gate3 = gate * gate * gate;
    const float cdf = 0.5f * (1.0f + tanhf(kGeluBeta * (gate + kGeluAlpha * gate3)));
    const __nv_bfloat16 activated_gate = __float2bfloat16_rn(gate * cdf);
    const __nv_bfloat16 value_bf16 =
        __float2bfloat16_rn(__bfloat162float(activated_gate) * up);
    activated[column] = value_bf16;
    local_max = fmaxf(local_max, fabsf(__bfloat162float(value_bf16)));
  }

  const float maximum = block_max(local_max);
  __shared__ float scale;
  if (threadIdx.x == 0) {
    scale = maximum / kFp8Max;
    scales[row] = scale;
  }
  __syncthreads();

  const float inverse_scale = scale == 0.0f ? 0.0f : 1.0f / scale;
  for (int64_t column = threadIdx.x; column < width; column += blockDim.x) {
    float value = __bfloat162float(activated[column]) * inverse_scale;
    value = fmaxf(fminf(value, kFp8Max), -kFp8Max);
    output[output_offset + column] = static_cast<__nv_fp8_e4m3>(value);
  }
}

}  // namespace

std::tuple<torch::Tensor, torch::Tensor> fused_gelu_tanh_mul_quant(
    const torch::Tensor& input) {
  TORCH_CHECK(input.is_cuda(), "input must be CUDA");
  TORCH_CHECK(input.scalar_type() == at::ScalarType::BFloat16, "input must be bfloat16");
  TORCH_CHECK(input.dim() == 2, "input must be two-dimensional");
  TORCH_CHECK(input.is_contiguous(), "input must be contiguous");
  TORCH_CHECK(input.size(1) == kExactWidth * 2, "expected exact Gemma gate/up width 43008");

  const auto rows = input.size(0);
  c10::cuda::CUDAGuard guard(input.device());
  auto quantized = torch::empty(
      {rows, kExactWidth}, input.options().dtype(at::ScalarType::Float8_e4m3fn));
  auto scales = torch::empty(
      {rows, 1}, input.options().dtype(at::ScalarType::Float));
  const auto stream = at::cuda::getCurrentCUDAStream(input.get_device());
  const auto shared_bytes = static_cast<size_t>(kExactWidth) * sizeof(__nv_bfloat16);
  fused_gelu_tanh_mul_quant_kernel<<<rows, kThreads, shared_bytes, stream>>>(
      reinterpret_cast<const __nv_bfloat16*>(input.data_ptr()),
      reinterpret_cast<__nv_fp8_e4m3*>(quantized.data_ptr()),
      scales.data_ptr<float>(),
      kExactWidth);
  C10_CUDA_KERNEL_LAUNCH_CHECK();
  return {quantized, scales};
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def(
      "fused_gelu_tanh_mul_quant",
      &fused_gelu_tanh_mul_quant,
      "Exact Gemma GELU(tanh)-and-mul with dynamic per-token FP8 quantization");
}
