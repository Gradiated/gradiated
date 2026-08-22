#pragma once

#include <memory>

struct CUstream_st;
using cudaStream_t = CUstream_st*;

namespace gradiated::engine {

// Tensor-core causal prefill for Gemma's D=512 global GQA layers. Q and output are head-major
// [Hq, S, D]; K and V are head-major [Hkv, S, D]. The BF16 score arena is reused across layers.
class GemmCausalPrefillAttention {
 public:
  GemmCausalPrefillAttention(int maximum_tokens, int maximum_query_heads,
                             int maximum_requests = 1);
  ~GemmCausalPrefillAttention();
  GemmCausalPrefillAttention(const GemmCausalPrefillAttention&) = delete;
  GemmCausalPrefillAttention& operator=(const GemmCausalPrefillAttention&) = delete;

  void run(const void* query, const void* key, const void* value, void* output,
           int query_heads, int kv_heads, int query_tokens, int kv_tokens, int kv_capacity,
           int query_position_start, int head_dimension, cudaStream_t stream);
  // Equal query lengths with independent context positions and KV allocations. Pointer arrays
  // live on device; one batched QK/PV pair covers every request and physical KV head.
  void run_uniform_batch(const void* query, const void* const* device_key_caches,
                         const void* const* device_value_caches, void* output,
                         const int* device_position_starts, int requests, int query_heads,
                         int kv_heads, int query_tokens, int maximum_kv_tokens,
                         int kv_capacity, int head_dimension, cudaStream_t stream);

 private:
  struct Implementation;
  std::unique_ptr<Implementation> implementation_;
};

}  // namespace gradiated::engine
