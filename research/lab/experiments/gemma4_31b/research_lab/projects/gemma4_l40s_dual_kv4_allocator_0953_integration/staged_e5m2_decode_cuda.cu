#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAGuard.h>
#include <cuda_bf16.h>
#include <torch/extension.h>

#include <cmath>
#include <cstdint>

namespace {

__device__ __forceinline__ int signed_nibble(uint8_t nibble) {
  int value = static_cast<int>(nibble & 0xf);
  return value >= 8 ? value - 16 : value;
}

__device__ __forceinline__ float decode_e5m2(uint8_t code) {
  const float sign = (code & 0x80) ? -1.0f : 1.0f;
  const int exponent = (code >> 2) & 0x1f;
  const int mantissa = code & 0x3;
  return exponent == 0
             ? sign * ldexpf(static_cast<float>(mantissa), -16)
             : sign * ldexpf(1.0f + 0.25f * mantissa, exponent - 15);
}

__device__ __forceinline__ uint8_t encode_e5m2(float value) {
  if (!isfinite(value)) return 0x7c;
  const uint8_t sign = signbit(value) ? 0x80 : 0;
  float magnitude = fminf(fabsf(value), 57344.0f);
  if (magnitude == 0.0f) return sign;
  if (magnitude < ldexpf(1.0f, -14)) {
    return sign | static_cast<uint8_t>(
                      max(0, min(3, __float2int_rn(ldexpf(magnitude, 16)))));
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
  return sign | static_cast<uint8_t>((encoded_exponent << 2) | mantissa);
}

template <int HeadDim, int ScaleOffset, int IndexOffset, int ResidualOffset,
          int VectorBytes, int Outliers, typename Index>
__device__ __forceinline__ float decode_kv4(
    const uint8_t* row, int channel) {
  const uint8_t packed = row[channel >> 1];
  const uint8_t nibble = (channel & 1) ? packed >> 4 : packed & 0xf;
  const auto* scales =
      reinterpret_cast<const __nv_bfloat16*>(row + ScaleOffset);
  float value = __bfloat162float(scales[channel / 64]) *
                signed_nibble(nibble);
  const auto* indices = reinterpret_cast<const Index*>(row + IndexOffset);
#pragma unroll
  for (int rank = 0; rank < Outliers; ++rank) {
    if (static_cast<int>(indices[rank]) == channel) {
      value += decode_e5m2(row[ResidualOffset + rank]);
    }
  }
  return value;
}

__global__ void decode_local_kernel(
    const uint8_t* packed, uint8_t* output, int64_t vectors) {
  const int64_t vector = blockIdx.x;
  if (vector >= vectors) return;
  const int channel = threadIdx.x;
  const uint8_t* row = packed + vector * 144;
  output[vector * 256 + channel] =
      encode_e5m2(decode_kv4<256, 128, 136, 140, 144, 4, uint8_t>(
          row, channel));
}

__global__ void decode_global_kernel(
    const uint8_t* recent, const uint8_t* old,
    const int32_t* recent_locations, const int32_t* old_locations,
    uint8_t* output, int64_t physical_capacity, int64_t kv_heads,
    int64_t recent_capacity, int64_t old_capacity) {
  const int64_t vector = blockIdx.x;
  const int64_t physical = vector / kv_heads;
  const int64_t head = vector % kv_heads;
  if (physical >= physical_capacity) return;
  const int channel = threadIdx.x;
  const int recent_slot = recent_locations[physical];
  const int old_slot = old_locations[physical];
  uint8_t code = 0;
  if (recent_slot >= 0 && recent_slot < recent_capacity) {
    code = recent[(static_cast<int64_t>(recent_slot) * kv_heads + head) *
                      512 +
                  channel];
  } else if (old_slot >= 0 && old_slot < old_capacity) {
    const uint8_t* row =
        old + (static_cast<int64_t>(old_slot) * kv_heads + head) * 296;
    code = encode_e5m2(
        decode_kv4<512, 256, 272, 288, 296, 8, uint16_t>(row, channel));
  }
  output[vector * 512 + channel] = code;
}

void check(const torch::Tensor& tensor) {
  TORCH_CHECK(tensor.is_cuda() && tensor.is_contiguous(),
              "all tensors must be contiguous CUDA tensors");
}

}  // namespace

void decode_local_kv4(torch::Tensor packed, torch::Tensor output) {
  check(packed);
  check(output);
  TORCH_CHECK(packed.scalar_type() == torch::kUInt8 && packed.dim() == 3 &&
                  packed.size(2) == 144,
              "packed local cache must be uint8[slots,heads,144]");
  TORCH_CHECK(output.dim() == 3 && output.element_size() == 1 &&
                  output.size(0) == packed.size(0) &&
                  output.size(1) == packed.size(1) &&
                  output.size(2) == 256,
              "local scratch must be one-byte[slots,heads,256]");
  c10::cuda::CUDAGuard guard(packed.device());
  const int64_t vectors = packed.size(0) * packed.size(1);
  decode_local_kernel<<<vectors, 256, 0, at::cuda::getDefaultCUDAStream()>>>(
      packed.data_ptr<uint8_t>(),
      reinterpret_cast<uint8_t*>(output.data_ptr()), vectors);
  C10_CUDA_KERNEL_LAUNCH_CHECK();
}

void decode_global_tiered_kv4(
    torch::Tensor recent, torch::Tensor old,
    torch::Tensor recent_locations, torch::Tensor old_locations,
    torch::Tensor output) {
  for (const auto& tensor :
       {recent, old, recent_locations, old_locations, output}) {
    check(tensor);
  }
  TORCH_CHECK(recent.scalar_type() == torch::kUInt8 &&
                  recent.dim() == 3 && recent.size(2) == 512,
              "recent cache must be uint8[slots,heads,512]");
  TORCH_CHECK(old.scalar_type() == torch::kUInt8 && old.dim() == 3 &&
                  old.size(1) == recent.size(1) && old.size(2) == 296,
              "old cache must be uint8[slots,heads,296]");
  TORCH_CHECK(recent_locations.scalar_type() == torch::kInt32 &&
                  old_locations.scalar_type() == torch::kInt32 &&
                  recent_locations.sizes() == old_locations.sizes(),
              "tier directories must be matching int32 vectors");
  TORCH_CHECK(output.dim() == 3 && output.element_size() == 1 &&
                  output.size(0) == recent_locations.numel() &&
                  output.size(1) == recent.size(1) &&
                  output.size(2) == 512,
              "global scratch must be one-byte[physical,heads,512]");
  c10::cuda::CUDAGuard guard(recent.device());
  const int64_t vectors = output.size(0) * output.size(1);
  decode_global_kernel<<<vectors, 512, 0,
                         at::cuda::getDefaultCUDAStream()>>>(
      recent.data_ptr<uint8_t>(), old.data_ptr<uint8_t>(),
      recent_locations.data_ptr<int32_t>(), old_locations.data_ptr<int32_t>(),
      reinterpret_cast<uint8_t*>(output.data_ptr()), output.size(0),
      output.size(1), recent.size(0), old.size(0));
  C10_CUDA_KERNEL_LAUNCH_CHECK();
}
