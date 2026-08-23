#pragma once

#include <memory>
#include <vector>

struct CUstream_st;
using cudaStream_t = CUstream_st*;

namespace gradiated::engine {

class Gemma4LayerRunner {
 public:
  Gemma4LayerRunner(const struct Gemma4Config& config, const class DeviceWeightArena& weights,
                    int maximum_tokens, int maximum_context = 8192, int maximum_batch = 1,
                    const class Fp8WeightArena* fp8_weights = nullptr);
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
  void run_decode_ragged(int layer_index, const void* hidden_states, void* output,
                         const int* positions, const int* slots, int batch, int maximum_slots,
                         int maximum_context_length, void* key_cache, void* value_cache,
                         void* fp8_key_cache, int cache_capacity, int contiguous_slot_start,
                         cudaStream_t stream);
  void run_prefill(int layer_index, const void* hidden_states, void* output, int tokens,
                   void* key_cache, void* value_cache, int cache_capacity, cudaStream_t stream);
  void run_prefill_chunk(int layer_index, const void* hidden_states, void* output, int tokens,
                         int position_start, void* key_cache, void* value_cache,
                         int cache_capacity, cudaStream_t stream);
  // Runs variable cached suffixes as one projection batch while preserving independent attention
  // and KV-cache ownership for each request.
  void run_prefill_chunks(int layer_index, const void* hidden_states, void* output,
                          const std::vector<int>& token_counts,
                          const std::vector<int>& position_starts,
                          const std::vector<void*>& key_caches,
                          const std::vector<void*>& value_caches,
                          const std::vector<int>& cache_capacities, cudaStream_t stream,
                          bool fp8_projections = false);

 private:
  struct Implementation;
  std::unique_ptr<Implementation> implementation_;
};

}  // namespace gradiated::engine
