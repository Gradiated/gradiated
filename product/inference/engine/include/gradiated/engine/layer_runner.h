#pragma once

#include <memory>

struct CUstream_st;
using cudaStream_t = CUstream_st*;

namespace gradiated::engine {

class Gemma4LayerRunner {
 public:
  Gemma4LayerRunner(const struct Gemma4Config& config, const class DeviceWeightArena& weights,
                    int maximum_tokens, int maximum_context = 8192, int maximum_batch = 1);
  ~Gemma4LayerRunner();
  Gemma4LayerRunner(const Gemma4LayerRunner&) = delete;
  Gemma4LayerRunner& operator=(const Gemma4LayerRunner&) = delete;

  // Runs one isolated decoder layer for a single sequence and returns the last token.
  // This parity primitive becomes the decode path once K/V storage is externalized.
  void run_last(int layer_index, const void* hidden_states, void* output, int tokens, cudaStream_t stream);
  void run_decode(int layer_index, const void* hidden_state, void* output, int position,
                  void* key_cache, void* value_cache, int cache_capacity, cudaStream_t stream);
  void run_decode_batch(int layer_index, const void* hidden_states, void* output, int batch,
                        int position, void* key_cache, void* value_cache, int cache_capacity,
                        cudaStream_t stream);
  void run_prefill(int layer_index, const void* hidden_states, void* output, int tokens,
                   void* key_cache, void* value_cache, int cache_capacity, cudaStream_t stream);
  void run_prefill_chunk(int layer_index, const void* hidden_states, void* output, int tokens,
                         int position_start, void* key_cache, void* value_cache,
                         int cache_capacity, cudaStream_t stream);

 private:
  struct Implementation;
  std::unique_ptr<Implementation> implementation_;
};

}  // namespace gradiated::engine
