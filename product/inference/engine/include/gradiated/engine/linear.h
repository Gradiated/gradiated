#pragma once

#include <cstddef>
#include <memory>

struct CUstream_st;
using cudaStream_t = CUstream_st*;

namespace gradiated::engine {

class Bf16Linear {
 public:
  explicit Bf16Linear(std::size_t workspace_bytes = 64ULL * 1024ULL * 1024ULL);
  ~Bf16Linear();
  Bf16Linear(const Bf16Linear&) = delete;
  Bf16Linear& operator=(const Bf16Linear&) = delete;

  void run(const void* input, const void* row_major_weight, void* output,
           int rows, int input_width, int output_width, cudaStream_t stream);

 private:
  struct Implementation;
  std::unique_ptr<Implementation> implementation_;
};

// Hopper TN FP8 tensor-core matmul with BF16 output. The row-major public contract remains
// output[M,N] = input[M,K] * weight[N,K]^T.
enum class Fp8Scaling { tensor, channel, block_128 };

class Fp8Linear {
 public:
  explicit Fp8Linear(Fp8Scaling scaling = Fp8Scaling::tensor,
                     std::size_t workspace_bytes = 64ULL * 1024ULL * 1024ULL);
  ~Fp8Linear();
  Fp8Linear(const Fp8Linear&) = delete;
  Fp8Linear& operator=(const Fp8Linear&) = delete;

  void run(const void* fp8_input, const float* input_scale,
           const void* fp8_row_major_weight, const float* weight_scale, void* bf16_output,
           int rows, int input_width, int output_width, cudaStream_t stream);

 private:
  struct Implementation;
  std::unique_ptr<Implementation> implementation_;
};

// Computes a tensor amax, stores scale=amax/448, and emits E4M3 bytes. Scale remains device-side.
void quantize_bf16_to_fp8_e4m3(const void* input, void* output, float* scale,
                               std::size_t elements, cudaStream_t stream,
                               float scale_multiplier = 1.0F);
void quantize_bf16_rows_to_fp8_e4m3(const void* input, void* output, float* scales,
                                    int rows, int width, cudaStream_t stream);

[[nodiscard]] std::size_t fp8_weight_block_scale_elements(int output_width, int input_width);
[[nodiscard]] std::size_t fp8_activation_block_scale_elements(int rows, int input_width);
// Weights use one scale per 128x128 tile; activations use one per row and 128 K values. These
// layouts are the native Hopper cuBLASLt A=BLK128x128/B=VEC128 contract.
void quantize_bf16_weight_to_fp8_block_128(const void* input, void* output, float* scales,
                                           int output_width, int input_width,
                                           cudaStream_t stream);
void quantize_bf16_activation_to_fp8_block_128(const void* input, void* output, float* scales,
                                               int rows, int input_width,
                                               cudaStream_t stream);

}  // namespace gradiated::engine
