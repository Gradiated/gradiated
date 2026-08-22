#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAGuard.h>
#include <c10/cuda/CUDAException.h>
#include <cuda_bf16.h>
#include <cuda_fp8.h>
#include <flashinfer/math.cuh>
#include <torch/extension.h>

#include <cmath>
#include <tuple>

namespace {

constexpr int kHidden = 5376;
constexpr int kMaximumRows = 32;
constexpr int kWarpSize = 32;
constexpr int kRmsVecSize = 8;
constexpr int kRmsThreads = kHidden / kRmsVecSize;
constexpr int kRmsWarps = kRmsThreads / kWarpSize;
constexpr int kQuantThreads = 256;
constexpr int kQuantWarps = kQuantThreads / kWarpSize;
constexpr int kQuantVecSize = 16;
constexpr float kFp8Maximum = 448.0f;

struct __align__(16) Bf16Vec8 {
  __nv_bfloat16 values[kRmsVecSize];
};

struct __align__(16) Bf16Vec16 {
  __nv_bfloat16 values[kQuantVecSize];
};

__device__ __forceinline__ float xor_sum(float value) {
#pragma unroll
  for (int offset = 16; offset > 0; offset /= 2) {
    value += __shfl_xor_sync(0xffffffff, value, offset);
  }
  return value;
}

__device__ __forceinline__ float xor_max(float value) {
#pragma unroll
  for (int offset = 16; offset > 0; offset /= 2) {
    value = fmaxf(value, __shfl_xor_sync(0xffffffff, value, offset));
  }
  return value;
}

__global__ void gemma4_decode_rmsnorm_quant_e4m3_exact_order(
    const __nv_bfloat16* __restrict__ input,
    const __nv_bfloat16* __restrict__ weight,
    __nv_fp8_e4m3* __restrict__ output,
    float* __restrict__ scales,
    float epsilon) {
  const int row = blockIdx.x;
  const int tx = threadIdx.x;
  const int ty = threadIdx.y;
  const int thread_id = tx + ty * kWarpSize;
  const int row_offset = row * kHidden;

  __shared__ float rms_warp_sums[kRmsWarps];
  __shared__ float quant_warp_maxima[kQuantWarps];
  __shared__ float inverse_rms;
  __shared__ float quant_scale;
  __shared__ __align__(16) __nv_bfloat16 normalized[kHidden];

  const Bf16Vec8 input_vec =
      *reinterpret_cast<const Bf16Vec8*>(
          input + row_offset + thread_id * kRmsVecSize);

  float sum_sq = 0.0f;
#pragma unroll
  for (int j = 0; j < kRmsVecSize; ++j) {
    const float value = __bfloat162float(input_vec.values[j]);
    sum_sq += value * value;
  }
  sum_sq = xor_sum(sum_sq);
  rms_warp_sums[ty] = sum_sq;
  __syncthreads();

  if (ty == 0) {
    sum_sq = tx < kRmsWarps ? rms_warp_sums[tx] : 0.0f;
    sum_sq = xor_sum(sum_sq);
    if (tx == 0) {
      inverse_rms = flashinfer::math::rsqrt(
          sum_sq / static_cast<float>(kHidden) + epsilon);
    }
  }
  __syncthreads();

  const Bf16Vec8 weight_vec =
      *reinterpret_cast<const Bf16Vec8*>(
          weight + thread_id * kRmsVecSize);
  Bf16Vec8 normalized_vec;
#pragma unroll
  for (int j = 0; j < kRmsVecSize; ++j) {
    normalized_vec.values[j] = __float2bfloat16_rn(
        __bfloat162float(input_vec.values[j]) * inverse_rms *
        __bfloat162float(weight_vec.values[j]));
  }
  *reinterpret_cast<Bf16Vec8*>(
      normalized + thread_id * kRmsVecSize) = normalized_vec;
  __syncthreads();

  if (thread_id < kQuantThreads) {
    const int vector_count = kHidden / kQuantVecSize;
    float local_maximum = 0.0f;
    for (int i = thread_id; i < vector_count; i += kQuantThreads) {
      const Bf16Vec16 vector =
          *reinterpret_cast<const Bf16Vec16*>(
              normalized + i * kQuantVecSize);
#pragma unroll
      for (int j = 0; j < kQuantVecSize; ++j) {
        local_maximum = fmaxf(
            local_maximum, fabsf(__bfloat162float(vector.values[j])));
      }
    }
    local_maximum = xor_max(local_maximum);
    if (tx == 0) {
      quant_warp_maxima[ty] = local_maximum;
    }
  }
  __syncthreads();

  if (ty == 0) {
    float maximum = tx < kQuantWarps ? quant_warp_maxima[tx] : 0.0f;
    maximum = xor_max(maximum);
    if (tx == 0) {
      quant_scale = maximum / kFp8Maximum;
      scales[row] = quant_scale;
    }
  }
  __syncthreads();

  if (thread_id < kQuantThreads) {
    const int vector_count = kHidden / kQuantVecSize;
    const float scale_inverse = 1.0f / quant_scale;
    for (int i = thread_id; i < vector_count; i += kQuantThreads) {
      const Bf16Vec16 vector =
          *reinterpret_cast<const Bf16Vec16*>(
              normalized + i * kQuantVecSize);
      __nv_fp8_e4m3 quantized[kQuantVecSize];
#pragma unroll
      for (int j = 0; j < kQuantVecSize; ++j) {
        float value =
            __bfloat162float(vector.values[j]) * scale_inverse;
        value = fmaxf(fminf(value, kFp8Maximum), -kFp8Maximum);
        quantized[j] = static_cast<__nv_fp8_e4m3>(value);
      }
      *reinterpret_cast<uint4*>(output + row_offset + i * kQuantVecSize) =
          *reinterpret_cast<uint4*>(quantized);
    }
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

std::tuple<torch::Tensor, torch::Tensor>
gemma4_decode_norm_fp8_exact_order(
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
  const dim3 threads(kWarpSize, kRmsWarps);
  gemma4_decode_rmsnorm_quant_e4m3_exact_order
      <<<input.size(0), threads, 0, stream>>>(
          reinterpret_cast<const __nv_bfloat16*>(input.data_ptr()),
          reinterpret_cast<const __nv_bfloat16*>(weight.data_ptr()),
          reinterpret_cast<__nv_fp8_e4m3*>(quantized.data_ptr()),
          scales.data_ptr<float>(),
          static_cast<float>(epsilon));
  C10_CUDA_KERNEL_LAUNCH_CHECK();
  return {quantized, scales};
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def(
      "gemma4_decode_norm_fp8_exact_order",
      &gemma4_decode_norm_fp8_exact_order);
}
