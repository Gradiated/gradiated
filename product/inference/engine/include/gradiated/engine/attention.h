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

}  // namespace gradiated::engine
