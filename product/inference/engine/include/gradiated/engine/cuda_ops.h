#pragma once

#include <cstddef>

struct CUstream_st;
using cudaStream_t = CUstream_st*;

namespace gradiated::engine {

void rms_norm_bf16(const void* input, const void* weight, void* output,
                   std::size_t rows, std::size_t width, float epsilon, cudaStream_t stream);
void rms_norm_add_bf16(const void* input, const void* weight, const void* residual, void* output,
                       std::size_t rows, std::size_t width, float epsilon, cudaStream_t stream);
void scale_bf16(void* values, const void* scalar, std::size_t elements, cudaStream_t stream);
void gelu_tanh_gate_bf16(const void* gate, const void* up, void* output,
                         std::size_t elements, cudaStream_t stream);
void gelu_tanh_gate_rows_bf16(const void* packed_gate_up, void* output,
                              int rows, int width, cudaStream_t stream);
void embedding_bf16(const void* embedding_weight, int token_id, void* output,
                    int vocabulary_size, int hidden_size, float scale, cudaStream_t stream);
void embedding_batch_bf16(const void* embedding_weight, const int* device_token_ids,
                          void* output, int batch, int vocabulary_size, int hidden_size,
                          float scale, cudaStream_t stream);
std::size_t argmax_bf16_workspace_bytes(int elements);
void argmax_bf16(const void* values, int elements, int* device_output,
                 void* workspace, cudaStream_t stream);

}  // namespace gradiated::engine
