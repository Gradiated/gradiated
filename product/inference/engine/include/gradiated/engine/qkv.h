#pragma once

#include <memory>

struct CUstream_st;
using cudaStream_t = CUstream_st*;

namespace gradiated::engine {

class Gemma4QkvPostprocessor {
 public:
  explicit Gemma4QkvPostprocessor(int maximum_positions);
  ~Gemma4QkvPostprocessor();
  Gemma4QkvPostprocessor(const Gemma4QkvPostprocessor&) = delete;
  Gemma4QkvPostprocessor& operator=(const Gemma4QkvPostprocessor&) = delete;

  void run(const void* packed_qkv, const void* query_norm_weight, const void* key_norm_weight,
           void* queries, void* key_cache, void* value_cache, int tokens, int query_heads,
           int kv_heads, int head_dimension, bool key_equals_value, int position_start,
           int cache_capacity, float epsilon, cudaStream_t stream);
  void run_positioned(const void* packed_qkv, const void* query_norm_weight,
                      const void* key_norm_weight, void* queries, void* key_cache,
                      void* value_cache, int tokens, int query_heads, int kv_heads,
                      int head_dimension, bool key_equals_value, int position_start,
                      int cache_position_start, int cache_capacity, float epsilon,
                      cudaStream_t stream);
  void run_decode_batch(const void* packed_qkv, const void* query_norm_weight,
                        const void* key_norm_weight, void* queries, void* key_cache,
                        void* value_cache, int batch, int query_heads, int kv_heads,
                        int head_dimension, bool key_equals_value, int position,
                        int cache_capacity, float epsilon, cudaStream_t stream);

 private:
  struct Implementation;
  std::unique_ptr<Implementation> implementation_;
};

}  // namespace gradiated::engine
