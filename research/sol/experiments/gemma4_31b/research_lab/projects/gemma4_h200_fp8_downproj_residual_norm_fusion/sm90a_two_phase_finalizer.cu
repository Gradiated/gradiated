#include <cuda_bf16.h>
#include <cuda_fp8.h>
#include <cuda_runtime.h>

#include <cstdint>

namespace gemma4_down_residual_norm_fp8 {

constexpr int kHidden = 5376;
constexpr int kReductionLanes = 8192;
constexpr int kThreads = 256;
constexpr float kE4M3Max = 448.0f;

__device__ float ordered_sum(float* tree) {
  for (int width = 1; width < kReductionLanes; width *= 2) {
    for (int left = threadIdx.x * width * 2; left < kReductionLanes;
         left += blockDim.x * width * 2) {
      tree[left] = tree[left] + tree[left + width];
    }
    __syncthreads();
  }
  return tree[0];
}

__device__ float ordered_max(float* tree) {
  for (int width = 1; width < kReductionLanes; width *= 2) {
    for (int left = threadIdx.x * width * 2; left < kReductionLanes;
         left += blockDim.x * width * 2) {
      tree[left] = fmaxf(tree[left], tree[left + width]);
    }
    __syncthreads();
  }
  return tree[0];
}

__global__ void finalize_post_ff_residual_next_norm_e4m3(
    const __nv_bfloat16* down_bf16,
    const __nv_bfloat16* post_ff_weight,
    const __nv_bfloat16* residual_bf16,
    const __nv_bfloat16* next_input_weight,
    const float* layer_scalar,
    __nv_bfloat16* next_residual_bf16,
    __nv_fp8_e4m3* next_qkv_input_e4m3,
    float* next_qkv_input_scale,
    int rows,
    float epsilon) {
  const int row = blockIdx.x;
  if (row >= rows) {
    return;
  }

  extern __shared__ __align__(16) unsigned char storage[];
  float* tree = reinterpret_cast<float*>(storage);
  __nv_bfloat16* row_values =
      reinterpret_cast<__nv_bfloat16*>(storage + kReductionLanes * sizeof(float));

  for (int column = threadIdx.x; column < kReductionLanes;
       column += blockDim.x) {
    float value = 0.0f;
    if (column < kHidden) {
      value = __bfloat162float(down_bf16[row * kHidden + column]);
    }
    tree[column] = value * value;
  }
  __syncthreads();
  const float post_rrms =
      rsqrtf(ordered_sum(tree) / static_cast<float>(kHidden) + epsilon);

  const float scalar = layer_scalar[0];
  for (int column = threadIdx.x; column < kHidden; column += blockDim.x) {
    const float down = __bfloat162float(down_bf16[row * kHidden + column]);
    const float weight = __bfloat162float(post_ff_weight[column]);
    const float residual =
        __bfloat162float(residual_bf16[row * kHidden + column]);
    const __nv_bfloat16 rounded =
        __float2bfloat16_rn((down * post_rrms * weight + residual) * scalar);
    row_values[column] = rounded;
    next_residual_bf16[row * kHidden + column] = rounded;
  }
  __syncthreads();

  for (int column = threadIdx.x; column < kReductionLanes;
       column += blockDim.x) {
    float value = 0.0f;
    if (column < kHidden) {
      value = __bfloat162float(row_values[column]);
    }
    tree[column] = value * value;
  }
  __syncthreads();
  const float next_rrms =
      rsqrtf(ordered_sum(tree) / static_cast<float>(kHidden) + epsilon);

  for (int column = threadIdx.x; column < kReductionLanes;
       column += blockDim.x) {
    float absolute = 0.0f;
    if (column < kHidden) {
      const float residual = __bfloat162float(row_values[column]);
      const float weight = __bfloat162float(next_input_weight[column]);
      const __nv_bfloat16 normalized =
          __float2bfloat16_rn(residual * next_rrms * weight);
      row_values[column] = normalized;
      absolute = fabsf(__bfloat162float(normalized));
    }
    tree[column] = absolute;
  }
  __syncthreads();
  const float scale = ordered_max(tree) / kE4M3Max;
  if (threadIdx.x == 0) {
    next_qkv_input_scale[row] = scale;
  }
  __syncthreads();

  const float inverse_scale = scale == 0.0f ? 0.0f : 1.0f / scale;
  for (int column = threadIdx.x; column < kHidden; column += blockDim.x) {
    float normalized;
    if (scale == 0.0f) {
      normalized = kE4M3Max;
    } else {
      normalized =
          fmaxf(fminf(__bfloat162float(row_values[column]) * inverse_scale,
                      kE4M3Max),
                -kE4M3Max);
    }
    next_qkv_input_e4m3[row * kHidden + column] =
        static_cast<__nv_fp8_e4m3>(normalized);
  }
}

constexpr int dynamic_shared_bytes() {
  return kReductionLanes * sizeof(float) + kHidden * sizeof(__nv_bfloat16);
}

static_assert(dynamic_shared_bytes() == 43520);

}  // namespace gemma4_down_residual_norm_fp8
