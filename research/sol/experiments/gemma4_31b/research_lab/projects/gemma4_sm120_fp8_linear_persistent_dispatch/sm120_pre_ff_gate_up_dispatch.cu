#include <ATen/ATen.h>
#include <ATen/core/dispatch/Dispatcher.h>
#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAException.h>
#include <cuda_bf16.h>
#include <cuda_fp8.h>
#include <torch/library.h>

#include <algorithm>
#include <cstdint>
#include <optional>
#include <tuple>

namespace {

constexpr int64_t kM = 32;
constexpr int64_t kK = 5376;
constexpr int64_t kN = 43008;
constexpr int kWarpSize = 32;
constexpr int kVecSize = 8;
constexpr int kThreads = kK / kVecSize;
constexpr int kWarps = kThreads / kWarpSize;
constexpr int kWarpSlots = 24;
constexpr float kFp8Max = 448.0F;

static_assert(kThreads == 672);
static_assert(kThreads % kWarpSize == 0);
static_assert(kWarpSlots >= kWarps);

struct alignas(16) Bf16x8 {
  __nv_bfloat16 values[kVecSize];
};

struct alignas(8) Fp8x8 {
  __nv_fp8_e4m3 values[kVecSize];
};

__device__ float warp_sum(float value) {
#pragma unroll
  for (int offset = kWarpSize / 2; offset > 0; offset /= 2) {
    value += __shfl_xor_sync(0xffffffffU, value, offset);
  }
  return value;
}

__device__ float warp_max(float value) {
#pragma unroll
  for (int offset = kWarpSize / 2; offset > 0; offset /= 2) {
    value = fmaxf(value, __shfl_xor_sync(0xffffffffU, value, offset));
  }
  return value;
}

__global__ void fused_add_rmsnorm_per_token_fp8_m32_kernel(
    const __nv_bfloat16* __restrict__ input,
    __nv_bfloat16* __restrict__ residual,
    const __nv_bfloat16* __restrict__ norm_weight,
    __nv_fp8_e4m3* __restrict__ quantized,
    float* __restrict__ scales,
    __nv_bfloat16* __restrict__ normalized_debug,
    float eps) {
  const int row = blockIdx.x;
  const int lane = threadIdx.x;
  const int warp = threadIdx.y;
  const int thread = lane + warp * kWarpSize;
  const int element = thread * kVecSize;

  extern __shared__ unsigned char shared_raw[];
  float* warp_values = reinterpret_cast<float*>(shared_raw);
  float* summed = warp_values + kWarpSlots;
  __nv_bfloat16* normalized = reinterpret_cast<__nv_bfloat16*>(summed + kK);

  const int64_t row_offset = static_cast<int64_t>(row) * kK + element;
  const Bf16x8 input_vec =
      *reinterpret_cast<const Bf16x8*>(input + row_offset);
  Bf16x8 residual_vec =
      *reinterpret_cast<const Bf16x8*>(residual + row_offset);

  float local_sum = 0.0F;
#pragma unroll
  for (int i = 0; i < kVecSize; ++i) {
    float value = __bfloat162float(input_vec.values[i]);
    value += __bfloat162float(residual_vec.values[i]);
    local_sum += value * value;
    residual_vec.values[i] = __float2bfloat16_rn(value);
    summed[element + i] = value;
  }
  *reinterpret_cast<Bf16x8*>(residual + row_offset) = residual_vec;

  local_sum = warp_sum(local_sum);
  if (lane == 0) {
    warp_values[warp] = local_sum;
  }
  __syncthreads();

  if (warp == 0) {
    float cross_warp = lane < kWarps ? warp_values[lane] : 0.0F;
    cross_warp = warp_sum(cross_warp);
    if (lane == 0) {
      warp_values[0] = cross_warp;
    }
  }
  __syncthreads();

  const float rms_reciprocal = rsqrtf(warp_values[0] / float(kK) + eps);
  const Bf16x8 weight_vec =
      *reinterpret_cast<const Bf16x8*>(norm_weight + element);
  Bf16x8 normalized_vec;
  float local_max = 0.0F;
#pragma unroll
  for (int i = 0; i < kVecSize; ++i) {
    const float value =
        summed[element + i] * rms_reciprocal *
        __bfloat162float(weight_vec.values[i]);
    normalized_vec.values[i] = __float2bfloat16_rn(value);
    local_max = fmaxf(
        local_max, fabsf(__bfloat162float(normalized_vec.values[i])));
  }
  *reinterpret_cast<Bf16x8*>(normalized + element) = normalized_vec;
  if (normalized_debug != nullptr) {
    *reinterpret_cast<Bf16x8*>(normalized_debug + row_offset) = normalized_vec;
  }

  local_max = warp_max(local_max);
  if (lane == 0) {
    warp_values[warp] = local_max;
  }
  __syncthreads();

  if (warp == 0) {
    float cross_warp = lane < kWarps ? warp_values[lane] : 0.0F;
    cross_warp = warp_max(cross_warp);
    if (lane == 0) {
      const float scale = cross_warp / kFp8Max;
      warp_values[0] = scale;
      scales[row] = scale;
    }
  }
  __syncthreads();

  const float scale_reciprocal = 1.0F / warp_values[0];
  Fp8x8 quantized_vec;
#pragma unroll
  for (int i = 0; i < kVecSize; ++i) {
    float value =
        __bfloat162float(normalized_vec.values[i]) * scale_reciprocal;
    value = fmaxf(fminf(value, kFp8Max), -kFp8Max);
    quantized_vec.values[i] = static_cast<__nv_fp8_e4m3>(value);
  }
  *reinterpret_cast<Fp8x8*>(quantized + row_offset) = quantized_vec;
}

void check_contract(
    const at::Tensor& input,
    const at::Tensor& residual,
    const at::Tensor& norm_weight,
    const at::Tensor& gate_up_weight,
    const at::Tensor& gate_up_weight_scale,
    const std::optional<at::Tensor>& normalized_debug) {
  TORCH_CHECK(input.is_cuda(), "input must be CUDA");
  TORCH_CHECK(residual.is_cuda(), "residual must be CUDA");
  TORCH_CHECK(norm_weight.is_cuda(), "norm_weight must be CUDA");
  TORCH_CHECK(gate_up_weight.is_cuda(), "gate_up_weight must be CUDA");
  TORCH_CHECK(gate_up_weight_scale.is_cuda(), "gate_up_weight_scale must be CUDA");
  TORCH_CHECK(input.scalar_type() == at::kBFloat16, "input must be BF16");
  TORCH_CHECK(residual.scalar_type() == at::kBFloat16, "residual must be BF16");
  TORCH_CHECK(norm_weight.scalar_type() == at::kBFloat16, "norm_weight must be BF16");
  TORCH_CHECK(
      gate_up_weight.scalar_type() == at::kFloat8_e4m3fn,
      "gate_up_weight must be E4M3FN");
  TORCH_CHECK(
      gate_up_weight_scale.scalar_type() == at::kFloat,
      "gate_up_weight_scale must be FP32");
  TORCH_CHECK(input.sizes() == at::IntArrayRef({kM, kK}), "input must be [32, 5376]");
  TORCH_CHECK(
      residual.sizes() == at::IntArrayRef({kM, kK}),
      "residual must be [32, 5376]");
  TORCH_CHECK(norm_weight.numel() == kK, "norm_weight must contain 5376 values");
  TORCH_CHECK(
      gate_up_weight.sizes() == at::IntArrayRef({kK, kN}),
      "gate_up_weight must be [5376, 43008]");
  TORCH_CHECK(gate_up_weight.stride(0) == 1, "gate_up_weight K stride must be 1");
  TORCH_CHECK(
      gate_up_weight.stride(1) == kK,
      "gate_up_weight N stride must be 5376");
  TORCH_CHECK(
      gate_up_weight_scale.numel() == kN,
      "gate_up_weight_scale must contain 43008 values");
  TORCH_CHECK(input.is_contiguous(), "input must be row-major contiguous");
  TORCH_CHECK(residual.is_contiguous(), "residual must be row-major contiguous");
  TORCH_CHECK(norm_weight.is_contiguous(), "norm_weight must be contiguous");
  TORCH_CHECK(
      gate_up_weight_scale.is_contiguous(),
      "gate_up_weight_scale must be contiguous");
  TORCH_CHECK(
      input.device() == residual.device() &&
          input.device() == norm_weight.device() &&
          input.device() == gate_up_weight.device() &&
          input.device() == gate_up_weight_scale.device(),
      "all tensors must share one CUDA device");
  if (normalized_debug.has_value()) {
    TORCH_CHECK(
        normalized_debug->sizes() == input.sizes(),
        "normalized_debug must be [32, 5376]");
    TORCH_CHECK(
        normalized_debug->scalar_type() == at::kBFloat16,
        "normalized_debug must be BF16");
    TORCH_CHECK(
        normalized_debug->is_contiguous(),
        "normalized_debug must be contiguous");
    TORCH_CHECK(
        normalized_debug->device() == input.device(),
        "normalized_debug must share the input device");
  }

  const auto* properties = at::cuda::getCurrentDeviceProperties();
  TORCH_CHECK(
      properties->major == 12 && properties->minor == 0,
      "entrypoint is bound to sm_120");
}

std::tuple<at::Tensor, at::Tensor, at::Tensor> gate_up_m32(
    const at::Tensor& input,
    at::Tensor residual,
    const at::Tensor& norm_weight,
    const at::Tensor& gate_up_weight,
    const at::Tensor& gate_up_weight_scale,
    double eps,
    const std::optional<at::Tensor>& normalized_debug) {
  check_contract(
      input,
      residual,
      norm_weight,
      gate_up_weight,
      gate_up_weight_scale,
      normalized_debug);

  auto quantized =
      at::empty({kM, kK}, input.options().dtype(at::kFloat8_e4m3fn));
  auto scales = at::empty({kM, 1}, input.options().dtype(at::kFloat));
  auto stream = at::cuda::getCurrentCUDAStream(input.get_device());
  const dim3 blocks(kM);
  const dim3 threads(kWarpSize, kWarps);
  constexpr size_t shared_bytes =
      (kWarpSlots + kK) * sizeof(float) + kK * sizeof(__nv_bfloat16);
  __nv_bfloat16* normalized_debug_ptr =
      normalized_debug.has_value()
      ? reinterpret_cast<__nv_bfloat16*>(normalized_debug->data_ptr())
      : nullptr;
  fused_add_rmsnorm_per_token_fp8_m32_kernel<<<
      blocks,
      threads,
      shared_bytes,
      stream>>>(
      reinterpret_cast<const __nv_bfloat16*>(input.data_ptr()),
      reinterpret_cast<__nv_bfloat16*>(residual.data_ptr()),
      reinterpret_cast<const __nv_bfloat16*>(norm_weight.data_ptr()),
      reinterpret_cast<__nv_fp8_e4m3*>(quantized.data_ptr()),
      scales.data_ptr<float>(),
      normalized_debug_ptr,
      static_cast<float>(eps));
  C10_CUDA_KERNEL_LAUNCH_CHECK();

  using StockFp8ScaledMm = at::Tensor(
      const at::Tensor&,
      const at::Tensor&,
      const at::Tensor&,
      const at::Tensor&,
      const at::ScalarType&,
      const std::optional<at::Tensor>&);
  static auto stock_fp8_scaled_mm =
      c10::Dispatcher::singleton()
          .findSchemaOrThrow("sgl_kernel::fp8_scaled_mm", "")
          .typed<StockFp8ScaledMm>();
  const at::ScalarType output_dtype = at::kBFloat16;
  const std::optional<at::Tensor> bias = std::nullopt;
  auto gate_up = stock_fp8_scaled_mm.call(
      quantized,
      gate_up_weight,
      scales,
      gate_up_weight_scale,
      output_dtype,
      bias);
  return {gate_up, quantized, scales};
}

}  // namespace

TORCH_LIBRARY(sm120_fp8_linear_persistent_dispatch, library) {
  library.def(
      "gate_up_m32(Tensor input, Tensor(a!) residual, Tensor norm_weight, "
      "Tensor gate_up_weight, Tensor gate_up_weight_scale, float eps, "
      "Tensor(b!)? normalized_debug=None) -> (Tensor, Tensor, Tensor)");
}

TORCH_LIBRARY_IMPL(
    sm120_fp8_linear_persistent_dispatch, CUDA, library) {
  library.impl("gate_up_m32", &gate_up_m32);
}
