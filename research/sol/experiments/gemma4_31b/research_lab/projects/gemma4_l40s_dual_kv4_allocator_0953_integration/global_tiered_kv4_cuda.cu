#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAGuard.h>
#include <cuda_bf16.h>
#include <torch/extension.h>

#include <cmath>
#include <cstdint>

namespace {

constexpr int kHeadDim = 512;
constexpr int kGroupSize = 64;
constexpr int kGroups = 8;
constexpr int kOutliers = 8;
constexpr int kPackedBytes = 256;
constexpr int kScaleOffset = 256;
constexpr int kIndexOffset = 272;
constexpr int kResidualOffset = 288;
constexpr int kOldVectorBytes = 296;
constexpr int kRecentTokens = 1024;

__device__ __forceinline__ uint8_t encode_e5m2(float value) {
  const uint8_t sign = signbit(value) ? 0x80 : 0;
  float magnitude = fminf(fabsf(value), 57344.0f);
  if (magnitude == 0.0f) {
    return sign;
  }
  if (magnitude < ldexpf(1.0f, -14)) {
    int mantissa = max(0, min(3, __float2int_rn(ldexpf(magnitude, 16))));
    return sign | static_cast<uint8_t>(mantissa);
  }
  int exponent;
  float fraction = frexpf(magnitude, &exponent);
  exponent -= 1;
  int mantissa = __float2int_rn((ldexpf(fraction, 1) - 1.0f) * 4.0f);
  if (mantissa == 4) {
    mantissa = 0;
    ++exponent;
  }
  int encoded_exponent = exponent + 15;
  if (encoded_exponent >= 31) {
    encoded_exponent = 30;
    mantissa = 3;
  }
  return sign |
         static_cast<uint8_t>((encoded_exponent << 2) | mantissa);
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

__device__ __forceinline__ float decode_old_channel(const uint8_t* row,
                                                     int channel) {
  const uint8_t byte = row[channel >> 1];
  const uint8_t nibble = (channel & 1) ? byte >> 4 : byte & 0xf;
  const __nv_bfloat16* scales =
      reinterpret_cast<const __nv_bfloat16*>(row + kScaleOffset);
  float value = static_cast<float>(scales[channel / kGroupSize]) *
                signed_nibble(nibble);
  const uint16_t* indices =
      reinterpret_cast<const uint16_t*>(row + kIndexOffset);
#pragma unroll
  for (int outlier = 0; outlier < kOutliers; ++outlier) {
    if (indices[outlier] == channel) {
      value += decode_e5m2(row[kResidualOffset + outlier]);
    }
  }
  return value;
}

template <typename scalar_t>
__global__ void store_recent_kernel(
    const scalar_t* input, const int64_t* physical_locations,
    const int32_t* recent_locations, uint8_t* recent_cache, int64_t tokens,
    int64_t kv_heads, int64_t physical_capacity, int64_t recent_capacity) {
  const int64_t vector_index = blockIdx.x;
  const int64_t token = vector_index / kv_heads;
  const int64_t head = vector_index % kv_heads;
  if (token >= tokens) {
    return;
  }
  const int64_t physical = physical_locations[token];
  if (physical < 0) {
    return;
  }
  if (physical >= physical_capacity) {
    return;
  }
  const int recent = recent_locations[physical];
  if (recent < 0 || recent >= recent_capacity) {
    return;
  }
  const int channel = threadIdx.x;
  const scalar_t* source =
      input + (token * kv_heads + head) * static_cast<int64_t>(kHeadDim);
  uint8_t* destination =
      recent_cache +
      (static_cast<int64_t>(recent) * kv_heads + head) * kHeadDim;
  destination[channel] = encode_e5m2(static_cast<float>(source[channel]));
}

template <typename scalar_t, bool kFromRecent>
__global__ void pack_old_kernel(
    const scalar_t* input, const int64_t* physical_locations,
    const int32_t* old_locations, const int32_t* recent_locations,
    const uint8_t* recent_cache, uint8_t* old_cache, int64_t tokens,
    int64_t kv_heads, int64_t physical_capacity, int64_t recent_capacity,
    int64_t old_capacity) {
  const int64_t vector_index = blockIdx.x;
  const int64_t token = vector_index / kv_heads;
  const int64_t head = vector_index % kv_heads;
  if (token >= tokens) {
    return;
  }
  const int64_t physical = physical_locations[token];
  if (physical < 0 || physical >= physical_capacity) {
    return;
  }
  const int old_location = old_locations[physical];
  if (old_location < 0 || old_location >= old_capacity) {
    return;
  }
  const int channel = threadIdx.x;
  float value;
  if constexpr (kFromRecent) {
    const int recent_location = recent_locations[physical];
    if (recent_location < 0 || recent_location >= recent_capacity) {
      return;
    }
    const uint8_t* source =
        recent_cache +
        (static_cast<int64_t>(recent_location) * kv_heads + head) * kHeadDim;
    value = decode_e5m2(source[channel]);
  } else {
    const scalar_t* source =
        input + (token * kv_heads + head) * static_cast<int64_t>(kHeadDim);
    value = static_cast<float>(source[channel]);
  }
  uint8_t* row =
      old_cache +
      (static_cast<int64_t>(old_location) * kv_heads + head) *
          kOldVectorBytes;

  __shared__ float values[kHeadDim];
  __shared__ float magnitudes[kHeadDim];
  __shared__ float residuals[kHeadDim];
  __shared__ int8_t quantized[kHeadDim];
  __shared__ __nv_bfloat16 scales[kGroups];
  __shared__ uint16_t selected[kOutliers];
  __shared__ uint8_t residual_codes[kOutliers];
  __shared__ uint8_t chosen[kHeadDim];

  values[channel] = value;
  magnitudes[channel] = fabsf(value);
  chosen[channel] = 0;
  __syncthreads();

  if (channel < kGroups) {
    float maximum = 0.0f;
    float second_maximum = 0.0f;
#pragma unroll
    for (int offset = 0; offset < kGroupSize; ++offset) {
      const float candidate = magnitudes[channel * kGroupSize + offset];
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
  int code = scale == 0.0f ? 0 : __float2int_rn(values[channel] / scale);
  code = max(-7, min(7, code));
  quantized[channel] = static_cast<int8_t>(code);
  residuals[channel] = values[channel] - scale * code;
  __syncthreads();

  if (channel == 0) {
#pragma unroll
    for (int rank = 0; rank < kOutliers; ++rank) {
      int best_channel = 0;
      float best_magnitude = -1.0f;
      for (int candidate = 0; candidate < kHeadDim; ++candidate) {
        const float candidate_magnitude = fabsf(residuals[candidate]);
        if (!chosen[candidate] && candidate_magnitude > best_magnitude) {
          best_magnitude = candidate_magnitude;
          best_channel = candidate;
        }
      }
      selected[rank] = static_cast<uint16_t>(best_channel);
      residual_codes[rank] = encode_e5m2(residuals[best_channel]);
      chosen[best_channel] = 1;
    }
    __nv_bfloat16* stored_scales =
        reinterpret_cast<__nv_bfloat16*>(row + kScaleOffset);
    uint16_t* stored_indices =
        reinterpret_cast<uint16_t*>(row + kIndexOffset);
#pragma unroll
    for (int group = 0; group < kGroups; ++group) {
      stored_scales[group] = scales[group];
      stored_indices[group] = selected[group];
      row[kResidualOffset + group] = residual_codes[group];
    }
  }
  if (channel < kPackedBytes) {
    const uint8_t low = static_cast<uint8_t>(quantized[2 * channel]) & 0xf;
    const uint8_t high =
        static_cast<uint8_t>(quantized[2 * channel + 1]) & 0xf;
    row[channel] = low | (high << 4);
  }
}

template <typename scalar_t>
__global__ void mixed_tier_paged_attention_kernel(
    const scalar_t* query, const uint8_t* recent_k,
    const uint8_t* recent_v, const uint8_t* old_k, const uint8_t* old_v,
    const int32_t* recent_locations, const int32_t* old_locations,
    const int32_t* qo_indptr, const int32_t* kv_indptr,
    const int64_t* kv_indices, scalar_t* output, int64_t batch,
    int64_t query_heads, int64_t kv_heads, int64_t physical_capacity,
    int64_t recent_capacity, int64_t old_capacity, int max_query_len,
    float softmax_scale) {
  const int request = blockIdx.x;
  const int query_head = blockIdx.y;
  const int query_offset = blockIdx.z;
  if (request >= batch || query_head >= query_heads ||
      query_offset >= max_query_len) {
    return;
  }
  const int query_start = qo_indptr[request];
  const int query_stop = qo_indptr[request + 1];
  const int query_index = query_start + query_offset;
  if (query_index >= query_stop) {
    return;
  }
  const int channel = threadIdx.x;
  const int kv_head = query_head / (query_heads / kv_heads);
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
  const int visible_stop = kv_stop - query_count + query_offset + 1;
  const int recent_start = max(kv_start, visible_stop - kRecentTokens);

  for (int cursor = kv_start; cursor < visible_stop; ++cursor) {
    const int64_t physical = kv_indices[cursor];
    if (physical < 0 || physical >= physical_capacity) {
      continue;
    }
    const bool use_recent = cursor >= recent_start;
    const int location =
        use_recent ? recent_locations[physical] : old_locations[physical];
    if ((use_recent && (location < 0 || location >= recent_capacity)) ||
        (!use_recent && (location < 0 || location >= old_capacity))) {
      continue;
    }
    const uint8_t* key_row =
        use_recent
            ? recent_k +
                  (static_cast<int64_t>(location) * kv_heads + kv_head) *
                      kHeadDim
            : old_k +
                  (static_cast<int64_t>(location) * kv_heads + kv_head) *
                      kOldVectorBytes;
    const float key_value =
        use_recent ? decode_e5m2(key_row[channel])
                   : decode_old_channel(key_row, channel);
    reduction[channel] = static_cast<float>(q[channel]) * key_value;
    __syncthreads();
    for (int stride = kHeadDim / 2; stride > 0; stride >>= 1) {
      if (channel < stride) {
        reduction[channel] += reduction[channel + stride];
      }
      __syncthreads();
    }
    if (channel == 0) {
      const float score = reduction[0] * softmax_scale;
      const float next_max = fmaxf(running_max, score);
      const float old_factor =
          isinf(running_max) ? 0.0f : expf(running_max - next_max);
      const float probability = expf(score - next_max);
      running_sum = running_sum * old_factor + probability;
      running_max = next_max;
      update[0] = old_factor;
      update[1] = probability;
      update[2] = running_sum;
    }
    __syncthreads();
    const uint8_t* value_row =
        use_recent
            ? recent_v +
                  (static_cast<int64_t>(location) * kv_heads + kv_head) *
                      kHeadDim
            : old_v +
                  (static_cast<int64_t>(location) * kv_heads + kv_head) *
                      kOldVectorBytes;
    const float value =
        use_recent ? decode_e5m2(value_row[channel])
                   : decode_old_channel(value_row, channel);
    accumulator = accumulator * update[0] + update[1] * value;
    __syncthreads();
  }
  out[channel] = running_sum == 0.0f
                     ? static_cast<scalar_t>(0.0f)
                     : static_cast<scalar_t>(accumulator / running_sum);
}

void check_cuda(const torch::Tensor& tensor) {
  TORCH_CHECK(tensor.is_cuda(), "all tensors must be CUDA tensors");
  TORCH_CHECK(tensor.is_contiguous(), "all tensors must be contiguous");
}

}  // namespace

void tiered_store_recent(torch::Tensor input, torch::Tensor physical_locations,
                         torch::Tensor recent_locations,
                         torch::Tensor recent_cache) {
  check_cuda(input);
  check_cuda(physical_locations);
  check_cuda(recent_locations);
  check_cuda(recent_cache);
  TORCH_CHECK(input.dim() == 3 && input.size(2) == kHeadDim,
              "input must be [tokens, kv_heads, 512]");
  TORCH_CHECK(physical_locations.scalar_type() == torch::kInt64,
              "physical locations must be int64");
  TORCH_CHECK(recent_locations.scalar_type() == torch::kInt32,
              "recent directory must be int32");
  TORCH_CHECK(recent_cache.scalar_type() == torch::kUInt8 &&
                  recent_cache.dim() == 3 &&
                  recent_cache.size(2) == kHeadDim,
              "recent cache must be uint8[slots, kv_heads, 512]");
  c10::cuda::CUDAGuard guard(input.device());
  const int64_t vectors = input.size(0) * input.size(1);
  AT_DISPATCH_FLOATING_TYPES_AND2(
      torch::kHalf, torch::kBFloat16, input.scalar_type(),
      "tiered_store_recent", [&] {
        store_recent_kernel<scalar_t>
            <<<vectors, kHeadDim, 0, at::cuda::getDefaultCUDAStream()>>>(
                input.data_ptr<scalar_t>(),
                physical_locations.data_ptr<int64_t>(),
                recent_locations.data_ptr<int32_t>(),
                recent_cache.data_ptr<uint8_t>(), input.size(0), input.size(1),
                recent_locations.numel(), recent_cache.size(0));
      });
  C10_CUDA_KERNEL_LAUNCH_CHECK();
}

void tiered_pack_old(torch::Tensor input, torch::Tensor physical_locations,
                     torch::Tensor old_locations, torch::Tensor old_cache) {
  check_cuda(input);
  check_cuda(physical_locations);
  check_cuda(old_locations);
  check_cuda(old_cache);
  TORCH_CHECK(input.dim() == 3 && input.size(2) == kHeadDim,
              "input must be [tokens, kv_heads, 512]");
  TORCH_CHECK(physical_locations.scalar_type() == torch::kInt64 &&
                  old_locations.scalar_type() == torch::kInt32,
              "physical/old locations must be int64/int32");
  TORCH_CHECK(old_cache.scalar_type() == torch::kUInt8 &&
                  old_cache.dim() == 3 &&
                  old_cache.size(2) == kOldVectorBytes,
              "old cache must be uint8[slots, kv_heads, 296]");
  c10::cuda::CUDAGuard guard(input.device());
  const int64_t vectors = input.size(0) * input.size(1);
  AT_DISPATCH_FLOATING_TYPES_AND2(
      torch::kHalf, torch::kBFloat16, input.scalar_type(), "tiered_pack_old",
      [&] {
        pack_old_kernel<scalar_t, false>
            <<<vectors, kHeadDim, 0, at::cuda::getDefaultCUDAStream()>>>(
                input.data_ptr<scalar_t>(),
                physical_locations.data_ptr<int64_t>(),
                old_locations.data_ptr<int32_t>(), nullptr, nullptr,
                old_cache.data_ptr<uint8_t>(), input.size(0), input.size(1),
                old_locations.numel(), 0, old_cache.size(0));
      });
  C10_CUDA_KERNEL_LAUNCH_CHECK();
}

void tiered_retire_recent(
    torch::Tensor physical_locations, torch::Tensor old_locations,
    torch::Tensor recent_locations, torch::Tensor recent_cache,
    torch::Tensor old_cache) {
  check_cuda(physical_locations);
  check_cuda(old_locations);
  check_cuda(recent_locations);
  check_cuda(recent_cache);
  check_cuda(old_cache);
  TORCH_CHECK(physical_locations.scalar_type() == torch::kInt64 &&
                  old_locations.scalar_type() == torch::kInt32 &&
                  recent_locations.scalar_type() == torch::kInt32,
              "tier directories have invalid dtype");
  const int64_t tokens = physical_locations.numel();
  const int64_t kv_heads = recent_cache.size(1);
  c10::cuda::CUDAGuard guard(recent_cache.device());
  pack_old_kernel<float, true>
      <<<tokens * kv_heads, kHeadDim, 0,
         at::cuda::getDefaultCUDAStream()>>>(
          nullptr, physical_locations.data_ptr<int64_t>(),
          old_locations.data_ptr<int32_t>(),
          recent_locations.data_ptr<int32_t>(),
          recent_cache.data_ptr<uint8_t>(), old_cache.data_ptr<uint8_t>(),
          tokens, kv_heads, old_locations.numel(), recent_cache.size(0),
          old_cache.size(0));
  C10_CUDA_KERNEL_LAUNCH_CHECK();
}

torch::Tensor tiered_paged_attention(
    torch::Tensor query, torch::Tensor recent_k, torch::Tensor recent_v,
    torch::Tensor old_k, torch::Tensor old_v,
    torch::Tensor recent_locations, torch::Tensor old_locations,
    torch::Tensor qo_indptr, torch::Tensor kv_indptr,
    torch::Tensor kv_indices, int64_t max_query_len, double softmax_scale) {
  for (const auto& tensor :
       {query, recent_k, recent_v, old_k, old_v, recent_locations,
        old_locations, qo_indptr, kv_indptr, kv_indices}) {
    check_cuda(tensor);
  }
  TORCH_CHECK(query.dim() == 3 && query.size(2) == kHeadDim,
              "query must be [queries, query_heads, 512]");
  TORCH_CHECK(recent_k.sizes() == recent_v.sizes() &&
                  recent_k.scalar_type() == torch::kUInt8 &&
                  recent_k.size(2) == kHeadDim,
              "recent K/V must match uint8[slots, kv_heads, 512]");
  TORCH_CHECK(old_k.sizes() == old_v.sizes() &&
                  old_k.scalar_type() == torch::kUInt8 &&
                  old_k.size(2) == kOldVectorBytes,
              "old K/V must match uint8[slots, kv_heads, 296]");
  TORCH_CHECK(query.size(1) % recent_k.size(1) == 0 &&
                  recent_k.size(1) == old_k.size(1),
              "GQA head geometry is invalid");
  TORCH_CHECK(recent_locations.scalar_type() == torch::kInt32 &&
                  old_locations.scalar_type() == torch::kInt32 &&
                  qo_indptr.scalar_type() == torch::kInt32 &&
                  kv_indptr.scalar_type() == torch::kInt32 &&
                  kv_indices.scalar_type() == torch::kInt64,
              "metadata dtypes are invalid");
  auto output = torch::empty_like(query);
  if (query.numel() == 0) {
    return output;
  }
  c10::cuda::CUDAGuard guard(query.device());
  const int64_t batch = qo_indptr.numel() - 1;
  const dim3 grid(batch, query.size(1), max_query_len);
  AT_DISPATCH_FLOATING_TYPES_AND2(
      torch::kHalf, torch::kBFloat16, query.scalar_type(),
      "tiered_paged_attention", [&] {
        mixed_tier_paged_attention_kernel<scalar_t>
            <<<grid, kHeadDim, 0, at::cuda::getDefaultCUDAStream()>>>(
                query.data_ptr<scalar_t>(), recent_k.data_ptr<uint8_t>(),
                recent_v.data_ptr<uint8_t>(), old_k.data_ptr<uint8_t>(),
                old_v.data_ptr<uint8_t>(),
                recent_locations.data_ptr<int32_t>(),
                old_locations.data_ptr<int32_t>(),
                qo_indptr.data_ptr<int32_t>(), kv_indptr.data_ptr<int32_t>(),
                kv_indices.data_ptr<int64_t>(), output.data_ptr<scalar_t>(),
                batch, query.size(1), recent_k.size(1),
                recent_locations.numel(), recent_k.size(0), old_k.size(0),
                max_query_len, static_cast<float>(softmax_scale));
      });
  C10_CUDA_KERNEL_LAUNCH_CHECK();
  return output;
}
