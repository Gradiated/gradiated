#pragma once

#include <memory>
#include <vector>

namespace gradiated::engine {

// Homogeneous-position batch used to establish the throughput ceiling before ragged scheduling.
class Gemma4BatchModelRunner {
 public:
  Gemma4BatchModelRunner(const struct Gemma4Config& config, const class DeviceWeightArena& weights,
                         int batch, int maximum_context);
  ~Gemma4BatchModelRunner();
  Gemma4BatchModelRunner(const Gemma4BatchModelRunner&) = delete;
  Gemma4BatchModelRunner& operator=(const Gemma4BatchModelRunner&) = delete;

  std::vector<int> append(const std::vector<int>& token_ids);
  // Prefills one stable slot using the shared prefill workspace and returns its greedy next token.
  int prefill_slot(int slot, const std::vector<int>& token_ids, int chunk_tokens = 1024);
  // Continues prefill from an exact token prefix already resident in the slot's hybrid KV cache.
  int prefill_slot_from_prefix(int slot, const std::vector<int>& token_ids,
                               int cached_prefix_tokens, int chunk_tokens = 1024);
  // Decodes compact active rows while retaining each request's stable cache slot.
  std::vector<int> append_ragged(const std::vector<int>& token_ids,
                                 const std::vector<int>& slots);
  void reset_slot(int slot);
  // Performance harness only: fills every allocated KV page with zero and advances logical time.
  void seed_empty_cache_for_benchmark(int position);
  [[nodiscard]] int batch() const;
  [[nodiscard]] int position() const;
  [[nodiscard]] int slot_position(int slot) const;

 private:
  struct Implementation;
  std::unique_ptr<Implementation> implementation_;
};

}  // namespace gradiated::engine
