#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAGuard.h>
#include <cuda_bf16.h>
#include <torch/extension.h>

#include <cmath>
#include <cstdint>
#include <limits>

namespace {

constexpr int kHeadDim = 256;
constexpr int kGroupSize = 64;
constexpr int kGroups = 4;
constexpr int kOutliers = 4;
constexpr int kPackedBytes = 128;
constexpr int kScaleOffset = 128;
constexpr int kIndexOffset = 136;
constexpr int kResidualOffset = 140;
constexpr int kVectorBytes = 144;

__device__ __forceinline__ uint8_t encode_e5m2(float value) {
  if (!isfinite(value)) {
    return 0x7c;
  }
  const uint8_t sign = signbit(value) ? 0x80 : 0;
  float magnitude = fminf(fabsf(value), 57344.0f);
  if (magnitude == 0.0f) {
    return sign;
  }
  if (magnitude < ldexpf(1.0f, -14)) {
    int mantissa = __float2int_rn(ldexpf(magnitude, 16));
    mantissa = max(0, min(3, mantissa));
    return sign | static_cast<uint8_t>(mantissa);
  }
  int exponent;
  float fraction = frexpf(magnitude, &exponent);
  exponent -= 1;
  float normalized = ldexpf(fraction, 1);
  int mantissa = __float2int_rn((normalized - 1.0f) * 4.0f);
  if (mantissa == 4) {
    mantissa = 0;
    ++exponent;
  }
  int encoded_exponent = exponent + 15;
  if (encoded_exponent >= 31) {
    encoded_exponent = 30;
    mantissa = 3;
  }
  return sign | static_cast<uint8_t>((encoded_exponent << 2) | mantissa);
}

__device__ __forceinline__ float decode_e5m2(uint8_t code) {
  const float sign = (code & 0x80) ? -1.0f : 1.0f;
  const int exponent = (code >> 2) & 0x1f;
  const int mantissa = code & 0x3;
  if (exponent == 0) {
    return sign * ldexpf(static_cast<float>(mantissa), -16);
  }
  return sign * ldexpf(1.0f + 0.25f * mantissa, exponent - 15);
}

__device__ __forceinline__ int signed_nibble(uint8_t nibble) {
  int value = static_cast<int>(nibble & 0xf);
  return value >= 8 ? value - 16 : value;
}

__device__ __forceinline__ float decode_channel(const uint8_t* row, int channel,
                                                 bool corrected) {
  const uint8_t byte = row[channel >> 1];
  const uint8_t nibble = (channel & 1) ? byte >> 4 : byte & 0xf;
  const __nv_bfloat16* scales =
      reinterpret_cast<const __nv_bfloat16*>(row + kScaleOffset);
  float value = static_cast<float>(scales[channel / kGroupSize]) *
                signed_nibble(nibble);
  if (corrected) {
#pragma unroll
    for (int i = 0; i < kOutliers; ++i) {
      if (row[kIndexOffset + i] == channel) {
        value += decode_e5m2(row[kResidualOffset + i]);
      }
    }
  }
  return value;
}

template <typename scalar_t>
__global__ void pack_kernel(const scalar_t* input, const int64_t* locations,
                            uint8_t* cache, int64_t tokens, int64_t kv_heads,
                            int64_t capacity) {
  const int64_t vector_index = blockIdx.x;
  const int64_t token = vector_index / kv_heads;
  const int64_t head = vector_index % kv_heads;
  if (token >= tokens) {
    return;
  }
  const int64_t slot = locations[token];
  if (slot < 0) {
    return;
  }
  if (slot >= capacity) {
    return;
  }
  const int channel = threadIdx.x;
  const scalar_t* source =
      input + (token * kv_heads + head) * static_cast<int64_t>(kHeadDim);
  uint8_t* row =
      cache + (slot * kv_heads + head) * static_cast<int64_t>(kVectorBytes);

  __shared__ float values[kHeadDim];
  __shared__ float residuals[kHeadDim];
  __shared__ int8_t codes[kHeadDim];
  __shared__ float reductions[kHeadDim];
  __shared__ __nv_bfloat16 scales[kGroups];
  __shared__ uint8_t selected[kOutliers];
  __shared__ uint8_t residual_codes[kOutliers];
  __shared__ uint8_t chosen[kHeadDim];

  const float value = static_cast<float>(source[channel]);
  values[channel] = value;
  reductions[channel] = fabsf(value);
  chosen[channel] = 0;
  __syncthreads();

  if (channel < kGroups) {
    float maximum = 0.0f;
    float second_maximum = 0.0f;
#pragma unroll
    for (int i = 0; i < kGroupSize; ++i) {
      const float candidate = reductions[channel * kGroupSize + i];
      if (candidate >= maximum) {
        second_maximum = maximum;
        maximum = candidate;
      } else if (candidate > second_maximum) {
        second_maximum = candidate;
      }
    }
    scales[channel] =
        second_maximum == 0.0f
            ? __float2bfloat16(0.0f)
            : __float2bfloat16_rn(second_maximum / 7.0f);
  }
  __syncthreads();

  const float scale = static_cast<float>(scales[channel / kGroupSize]);
  int quantized = scale == 0.0f ? 0 : __float2int_rn(value / scale);
  quantized = max(-7, min(7, quantized));
  codes[channel] = static_cast<int8_t>(quantized);
  residuals[channel] = value - scale * quantized;
  __syncthreads();

  if (channel == 0) {
#pragma unroll
    for (int rank = 0; rank < kOutliers; ++rank) {
      int best_channel = 0;
      float best_magnitude = -1.0f;
      for (int candidate = 0; candidate < kHeadDim; ++candidate) {
        if (chosen[candidate]) {
          continue;
        }
        const float magnitude = fabsf(residuals[candidate]);
        if (magnitude > best_magnitude) {
          best_magnitude = magnitude;
          best_channel = candidate;
        }
      }
      selected[rank] = static_cast<uint8_t>(best_channel);
      residual_codes[rank] = encode_e5m2(residuals[best_channel]);
      chosen[best_channel] = 1;
    }
    __nv_bfloat16* stored_scales =
        reinterpret_cast<__nv_bfloat16*>(row + kScaleOffset);
#pragma unroll
    for (int group = 0; group < kGroups; ++group) {
      stored_scales[group] = scales[group];
      row[kIndexOffset + group] = selected[group];
      row[kResidualOffset + group] = residual_codes[group];
    }
  }
  if (channel < kPackedBytes) {
    const uint8_t low = static_cast<uint8_t>(codes[2 * channel]) & 0xf;
    const uint8_t high = static_cast<uint8_t>(codes[2 * channel + 1]) & 0xf;
    row[channel] = low | (high << 4);
  }
}

template <typename scalar_t>
__global__ void paged_attention_kernel(
    const scalar_t* query, const uint8_t* cache_k, const uint8_t* cache_v,
    const int32_t* qo_indptr, const int32_t* kv_indptr,
    const int64_t* kv_indices, scalar_t* output, int64_t batch,
    int64_t query_heads, int64_t kv_heads, int64_t capacity, int window,
    float softmax_scale, bool corrected) {
  const int request = blockIdx.x;
  const int query_head = blockIdx.y;
  const int query_offset = blockIdx.z;
  if (request >= batch || query_head >= query_heads) {
    return;
  }
  const int query_start = qo_indptr[request];
  const int query_stop = qo_indptr[request + 1];
  const int query_index = query_start + query_offset;
  if (query_index >= query_stop) {
    return;
  }
  const int channel = threadIdx.x;
  const int group = query_heads / kv_heads;
  const int kv_head = query_head / group;
  const scalar_t* q =
      query + (query_index * query_heads + query_head) * kHeadDim;
  scalar_t* out =
      output + (query_index * query_heads + query_head) * kHeadDim;

  __shared__ float reduction[kHeadDim];
  __shared__ float update[3];
  float accumulator = 0.0f;
  float running_max = -CUDART_INF_F;
  float running_sum = 0.0f;
  const int kv_start = kv_indptr[request];
  const int kv_stop = kv_indptr[request + 1];
  const int query_count = query_stop - query_start;
  const int visible_kv_stop =
      kv_stop - query_count + query_offset + 1;
  const int visible_kv_start = max(kv_start, visible_kv_stop - window);

  for (int cursor = visible_kv_start; cursor < visible_kv_stop; ++cursor) {
    const int64_t slot = kv_indices[cursor];
    if (slot < 0 || slot >= capacity) {
      continue;
    }
    const uint8_t* key_row =
        cache_k + (slot * kv_heads + kv_head) * kVectorBytes;
    reduction[channel] =
        static_cast<float>(q[channel]) *
        decode_channel(key_row, channel, corrected);
    __syncthreads();
    for (int stride = kHeadDim / 2; stride > 0; stride >>= 1) {
      if (channel < stride) {
        reduction[channel] += reduction[channel + stride];
      }
      __syncthreads();
    }
    if (channel == 0) {
      const float score = reduction[0] * softmax_scale;
      const float new_max = fmaxf(running_max, score);
      const float old_factor =
          isinf(running_max) ? 0.0f : expf(running_max - new_max);
      const float probability = expf(score - new_max);
      update[0] = old_factor;
      update[1] = probability;
      running_sum = running_sum * old_factor + probability;
      running_max = new_max;
      update[2] = running_sum;
    }
    __syncthreads();
    const uint8_t* value_row =
        cache_v + (slot * kv_heads + kv_head) * kVectorBytes;
    accumulator = accumulator * update[0] +
                  update[1] * decode_channel(value_row, channel, corrected);
    running_sum = update[2];
    __syncthreads();
  }
  out[channel] = static_cast<scalar_t>(
      running_sum == 0.0f ? 0.0f : accumulator / running_sum);
}

void check_common(const torch::Tensor& tensor) {
  TORCH_CHECK(tensor.is_cuda(), "all candidate tensors must be CUDA tensors");
  TORCH_CHECK(tensor.is_contiguous(), "all candidate tensors must be contiguous");
}

}  // namespace

void local_kv4_outlier_pack(torch::Tensor input, torch::Tensor locations,
                            torch::Tensor cache) {
  check_common(input);
  check_common(locations);
  check_common(cache);
  TORCH_CHECK(input.dim() == 3 && input.size(2) == kHeadDim,
              "input must be [tokens, kv_heads, 256]");
  TORCH_CHECK(locations.scalar_type() == torch::kInt64 &&
                  locations.numel() == input.size(0),
              "locations must be int64[tokens]");
  TORCH_CHECK(cache.scalar_type() == torch::kUInt8 && cache.dim() == 3 &&
                  cache.size(1) == input.size(1) &&
                  cache.size(2) == kVectorBytes,
              "cache must be uint8[slots, kv_heads, 144]");
  c10::cuda::CUDAGuard guard(input.device());
  const int64_t vectors = input.size(0) * input.size(1);
  AT_DISPATCH_FLOATING_TYPES_AND2(
      torch::kHalf, torch::kBFloat16, input.scalar_type(),
      "local_kv4_outlier_pack", [&] {
        pack_kernel<scalar_t><<<vectors, kHeadDim, 0,
                                at::cuda::getDefaultCUDAStream()>>>(
            input.data_ptr<scalar_t>(), locations.data_ptr<int64_t>(),
            cache.data_ptr<uint8_t>(), input.size(0), input.size(1),
            cache.size(0));
      });
  C10_CUDA_KERNEL_LAUNCH_CHECK();
}

torch::Tensor local_kv4_outlier_paged_attention(
    torch::Tensor query, torch::Tensor cache_k, torch::Tensor cache_v,
    torch::Tensor qo_indptr, torch::Tensor kv_indptr, torch::Tensor kv_indices,
    int64_t window, int64_t max_query_len, double softmax_scale,
    bool corrected) {
  check_common(query);
  check_common(cache_k);
  check_common(cache_v);
  check_common(qo_indptr);
  check_common(kv_indptr);
  check_common(kv_indices);
  TORCH_CHECK(query.dim() == 3 && query.size(2) == kHeadDim,
              "query must be [queries, query_heads, 256]");
  TORCH_CHECK(cache_k.sizes() == cache_v.sizes() &&
                  cache_k.scalar_type() == torch::kUInt8 &&
                  cache_k.size(2) == kVectorBytes,
              "K/V cache must be matching uint8[slots, kv_heads, 144]");
  TORCH_CHECK(qo_indptr.scalar_type() == torch::kInt32 &&
                  kv_indptr.scalar_type() == torch::kInt32,
              "indptr tensors must be int32");
  TORCH_CHECK(kv_indices.scalar_type() == torch::kInt64,
              "kv_indices must be int64");
  TORCH_CHECK(query.size(1) % cache_k.size(1) == 0,
              "query heads must divide evenly over KV heads");
  TORCH_CHECK(window == 1024, "the frozen local window is 1024");
  const int64_t batch = qo_indptr.numel() - 1;
  TORCH_CHECK(max_query_len >= 0 && max_query_len <= query.size(0),
              "max_query_len must bound the longest ragged request");
  auto output = torch::empty_like(query);
  if (query.numel() == 0) {
    return output;
  }
  c10::cuda::CUDAGuard guard(query.device());
  const dim3 grid(batch, query.size(1), max_query_len);
  AT_DISPATCH_FLOATING_TYPES_AND2(
      torch::kHalf, torch::kBFloat16, query.scalar_type(),
      "local_kv4_outlier_paged_attention", [&] {
        paged_attention_kernel<scalar_t>
            <<<grid, kHeadDim, 0, at::cuda::getDefaultCUDAStream()>>>(
                query.data_ptr<scalar_t>(), cache_k.data_ptr<uint8_t>(),
                cache_v.data_ptr<uint8_t>(), qo_indptr.data_ptr<int32_t>(),
                kv_indptr.data_ptr<int32_t>(), kv_indices.data_ptr<int64_t>(),
                output.data_ptr<scalar_t>(), batch, query.size(1),
                cache_k.size(1), cache_k.size(0), static_cast<int>(window),
                static_cast<float>(softmax_scale), corrected);
      });
  C10_CUDA_KERNEL_LAUNCH_CHECK();
  return output;
}
