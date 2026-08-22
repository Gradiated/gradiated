#pragma once

#include <cstddef>
#include <memory>

struct CUstream_st;
using cudaStream_t = CUstream_st*;

namespace gradiated::engine {

class GemmGroupedDecodeAttention {
 public:
  GemmGroupedDecodeAttention(int maximum_batch, int maximum_kv_heads,
                             int maximum_query_group, int maximum_context);
  ~GemmGroupedDecodeAttention();
  GemmGroupedDecodeAttention(const GemmGroupedDecodeAttention&) = delete;
  GemmGroupedDecodeAttention& operator=(const GemmGroupedDecodeAttention&) = delete;

  void run(const void* query, const void* key_cache, const void* value_cache, void* output,
           int batch, int kv_heads, int query_group, int context_length,
           int head_dimension, cudaStream_t stream, int cache_capacity = 0);
  // Compact query/output rows attend to stable cache slots with independent absolute positions.
  // positions and slots are device arrays. Invalid tail scores are zeroed before PV.
  void run_ragged(const void* query, const void* key_cache, const void* value_cache,
                  void* output, const int* positions, const int* slots, int batch,
                  int maximum_slots, int kv_heads, int query_group, int maximum_context_length,
                  int head_dimension, cudaStream_t stream, int cache_capacity);

 private:
  struct Implementation;
  std::unique_ptr<Implementation> implementation_;
};

}  // namespace gradiated::engine
