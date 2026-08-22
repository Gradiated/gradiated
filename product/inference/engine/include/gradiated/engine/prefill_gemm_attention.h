#pragma once

#include <memory>

struct CUstream_st;
using cudaStream_t = CUstream_st*;

namespace gradiated::engine {

// Tensor-core causal prefill for Gemma's D=512 global GQA layers. Q and output are head-major
// [Hq, S, D]; K and V are head-major [Hkv, S, D]. The BF16 score arena is reused across layers.
class GemmCausalPrefillAttention {
 public:
  GemmCausalPrefillAttention(int maximum_tokens, int maximum_query_heads);
  ~GemmCausalPrefillAttention();
  GemmCausalPrefillAttention(const GemmCausalPrefillAttention&) = delete;
  GemmCausalPrefillAttention& operator=(const GemmCausalPrefillAttention&) = delete;

  void run(const void* query, const void* key, const void* value, void* output,
           int query_heads, int kv_heads, int query_tokens, int kv_tokens, int kv_capacity,
           int query_position_start, int head_dimension, cudaStream_t stream);

 private:
  struct Implementation;
  std::unique_ptr<Implementation> implementation_;
};

}  // namespace gradiated::engine
