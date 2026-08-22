#pragma once

#include <cstddef>

struct CUstream_st;
using cudaStream_t = CUstream_st*;

namespace gradiated::engine {

void rms_norm_bf16(const void* input, const void* weight, void* output,
                   std::size_t rows, std::size_t width, float epsilon, cudaStream_t stream);
void rms_norm_add_bf16(const void* input, const void* weight, const void* residual, void* output,
                       std::size_t rows, std::size_t width, float epsilon, cudaStream_t stream);
void rms_norm_add_and_norm_bf16(const void* input, const void* weight, const void* residual,
                                const void* next_weight, void* residual_output,
                                void* normalized_output, std::size_t rows, std::size_t width,
                                float epsilon, cudaStream_t stream);
void rms_norm_add_scale_bf16(const void* input, const void* weight, const void* residual,
                             const void* scalar, void* output, std::size_t rows,
                             std::size_t width, float epsilon, cudaStream_t stream);
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
void token_to_head_bf16(const void* input, void* output, int tokens, int heads,
                        int head_dimension, cudaStream_t stream);
void head_to_token_bf16(const void* input, void* output, int tokens, int heads,
                        int head_dimension, cudaStream_t stream);
void copy_kv_to_cache_bf16(const void* source, void* destination, int heads, int tokens,
                           int head_dimension, int destination_capacity, int position_start,
                           cudaStream_t stream);
void gather_kv_ring_bf16(const void* source, void* destination, int heads, int retained_tokens,
                         int head_dimension, int source_capacity, int destination_capacity,
                         int logical_position_start, cudaStream_t stream);
void copy_kv_span_to_ring_bf16(const void* source, void* destination, int heads, int tokens,
                               int head_dimension, int source_capacity, int source_position_start,
                               int destination_capacity, int logical_position_start,
                               cudaStream_t stream);
std::size_t argmax_bf16_workspace_bytes(int elements);
void argmax_bf16(const void* values, int elements, int* device_output,
                 void* workspace, cudaStream_t stream);

}  // namespace gradiated::engine
