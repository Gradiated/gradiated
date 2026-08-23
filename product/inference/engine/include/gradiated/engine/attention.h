#pragma once

#include <cstddef>

struct CUstream_st;
using cudaStream_t = CUstream_st*;

namespace gradiated::engine {

// Q/output: [batch, kv_heads, query_group, head_dimension].
// K/V: [batch, kv_heads, context_length, head_dimension].
// The kernel loads each physical K/V element once per KV-head block and applies it to every
// grouped query, avoiding the 2x/8x HBM amplification of per-query-head implementations.
void grouped_decode_attention_bf16(const void* query, const void* key_cache, const void* value_cache,
                                   void* output, int batch, int kv_heads, int query_group,
                                   int context_length, int head_dimension, cudaStream_t stream);

// Benchmark-only Hopper WMMA prototype for Gemma 4 global attention (D=512, GQA group=8). It
// keeps scores on chip but is intentionally not selected by the model runner; measured evidence
// in DESIGN.md rejects this synchronization-heavy implementation.
void grouped_decode_attention_wmma_bf16(
    const void* query, const void* key_cache, const void* value_cache, void* output,
    int batch, int kv_heads, int query_group, int context_length, int head_dimension,
    cudaStream_t stream);

// Benchmark/prototyping boundary for the Hopper-native global QK tile. Produces BF16 scores in
// [batch, kv_head, query, context] order without softmax. Context must be a multiple of 64.
void grouped_global_qk_wgmma_bf16(const void* query, const void* key_cache, void* scores,
                                  int batch, int kv_heads, int query_group,
                                  int context_length, int head_dimension,
                                  cudaStream_t stream, int tiles_per_block = 1);

// Correctness frontier for one 64-token Hopper global-attention tile. This keeps QK scores and
// probabilities in shared memory and performs both QK and PV with WGMMA.
void grouped_global_attention_wgmma_tile_bf16(
    const void* query, const void* key_cache, const void* value_cache, void* output,
    int batch, int kv_heads, int query_group, int context_length, int head_dimension,
    cudaStream_t stream);

}  // namespace gradiated::engine
