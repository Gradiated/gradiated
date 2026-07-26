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
constexpr int kIntermediate = 21504;
constexpr int kGateUp = 43008;
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

__global__ void fused_swiglu_quant_kernel(
    const __nv_bfloat16* __restrict__ gate_up,
    __nv_fp8_e4m3* __restrict__ quantized,
    float* __restrict__ scales) {
  extern __shared__ __nv_bfloat16 activated[];
  const int64_t row = blockIdx.x;
  const int64_t input_offset = row * kGateUp;
  const int64_t output_offset = row * kIntermediate;

  float local_max = 0.0f;
  for (int column = threadIdx.x; column < kIntermediate;
       column += blockDim.x) {
    const float gate = __bfloat162float(gate_up[input_offset + column]);
    const float up =
        __bfloat162float(gate_up[input_offset + kIntermediate + column]);
    const float gate3 = gate * gate * gate;
    const float cdf =
        0.5f * (1.0f + tanhf(kGeluBeta * (gate + kGeluAlpha * gate3)));
    const __nv_bfloat16 value =
        __float2bfloat16_rn((gate * cdf) * up);
    activated[column] = value;
    local_max = fmaxf(local_max, fabsf(__bfloat162float(value)));
  }

  const float maximum = block_max(local_max);
  __shared__ float scale;
  if (threadIdx.x == 0) {
    scale = maximum / kFp8Max;
    scales[row] = scale;
  }
  __syncthreads();

  const float inverse_scale = scale == 0.0f ? 0.0f : 1.0f / scale;
  for (int column = threadIdx.x; column < kIntermediate;
       column += blockDim.x) {
    float value = __bfloat162float(activated[column]) * inverse_scale;
    value = fmaxf(fminf(value, kFp8Max), -kFp8Max);
    quantized[output_offset + column] = static_cast<__nv_fp8_e4m3>(value);
  }
}

}  // namespace

std::tuple<torch::Tensor, torch::Tensor> fused_swiglu_quant(
    const torch::Tensor& gate_up) {
  TORCH_CHECK(gate_up.is_cuda(), "gate_up must be CUDA");
  TORCH_CHECK(
      gate_up.scalar_type() == at::ScalarType::BFloat16,
      "gate_up must be bfloat16");
  TORCH_CHECK(gate_up.dim() == 2, "gate_up must be two-dimensional");
  TORCH_CHECK(gate_up.is_contiguous(), "gate_up must be contiguous");
  TORCH_CHECK(
      gate_up.size(1) == kGateUp,
      "expected exact Gemma gate/up width 43008");

  const auto rows = gate_up.size(0);
  c10::cuda::CUDAGuard guard(gate_up.device());
  auto quantized = torch::empty(
      {rows, kIntermediate},
      gate_up.options().dtype(at::ScalarType::Float8_e4m3fn));
  auto scales =
      torch::empty({rows, 1}, gate_up.options().dtype(at::ScalarType::Float));
  const auto stream = at::cuda::getCurrentCUDAStream(gate_up.get_device());
  const auto shared_bytes =
      static_cast<size_t>(kIntermediate) * sizeof(__nv_bfloat16);
  fused_swiglu_quant_kernel<<<rows, kThreads, shared_bytes, stream>>>(
      reinterpret_cast<const __nv_bfloat16*>(gate_up.data_ptr()),
      reinterpret_cast<__nv_fp8_e4m3*>(quantized.data_ptr()),
      scales.data_ptr<float>());
  C10_CUDA_KERNEL_LAUNCH_CHECK();
  return {quantized, scales};
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def(
      "fused_swiglu_quant",
      &fused_swiglu_quant,
      "Exact Gemma SwiGLU BF16 boundary plus dynamic E4M3 quantization");
}
