#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <vector>

namespace gradiated::engine {

struct GreedyVerificationResult {
  // Number of proposed tokens accepted for each request.  The returned next_tokens are the
  // target replacement at the first rejection, or the bonus token when every proposal matched.
  std::vector<int> accepted_tokens;
  std::vector<int> next_tokens;
};

struct LayerSlicedSuffixPrefillResult {
  bool complete{false};
  std::vector<int> predictions;
};

// Homogeneous-position batch used to establish the throughput ceiling before ragged scheduling.
class Gemma4BatchModelRunner {
 public:
  Gemma4BatchModelRunner(const struct Gemma4Config& config, const class DeviceWeightArena& weights,
                         int batch, int maximum_context,
                         const class Fp8WeightArena* fp8_weights = nullptr,
                         const class DeviceWeightArena* assistant_weights = nullptr,
                         const class Fp8WeightArena* assistant_fp8_weights = nullptr);
  ~Gemma4BatchModelRunner();
  Gemma4BatchModelRunner(const Gemma4BatchModelRunner&) = delete;
  Gemma4BatchModelRunner& operator=(const Gemma4BatchModelRunner&) = delete;

  std::vector<int> append(const std::vector<int>& token_ids);
  // Prefills one stable slot using the shared prefill workspace and returns its greedy next token.
  int prefill_slot(int slot, const std::vector<int>& token_ids, int chunk_tokens = 1024);
  // Continues prefill from an exact token prefix already resident in the slot's hybrid KV cache.
  int prefill_slot_from_prefix(int slot, const std::vector<int>& token_ids,
                               int cached_prefix_tokens, int chunk_tokens = 1024);
  // Advances a slot's prefill by at most chunk_tokens. Returns the greedy next token only when
  // the complete prompt is resident, allowing a scheduler to bound interruption of active decode.
  std::optional<int> prefill_slot_chunk(int slot, const std::vector<int>& token_ids,
                                        int chunk_tokens);
  // Extends several stable slots to the ends of their prompts with one shared projection batch.
  std::vector<int> prefill_slots_suffix(
      const std::vector<int>& slots,
      const std::vector<const std::vector<int>*>& token_ids);
  // Runs a full suffix cohort through at most maximum_layers more transformer layers. Dedicated
  // hidden-state storage survives intervening decode waves, so preemption does not repeat any
  // model layer or alter the token graph.
  LayerSlicedSuffixPrefillResult prefill_slots_suffix_layer_slice(
      const std::vector<int>& slots,
      const std::vector<const std::vector<int>*>& token_ids,
      int maximum_layers);
  void abort_suffix_layer_slices();
  [[nodiscard]] bool has_suffix_layer_slices() const;
  // Copies the exact hybrid KV state and logical position between stable slots on device.
  std::uint64_t clone_slot(int source_slot, int destination_slot);
  // Decodes compact active rows while retaining each request's stable cache slot.
  std::vector<int> append_ragged(const std::vector<int>& token_ids,
                                 const std::vector<int>& slots);
  // Verifies four-token draft continuations in one target pass. Cache positions are committed
  // only through each accepted prefix; rejected sliding-ring rows are restored exactly and
  // stale global-cache tail rows remain unreachable.
  GreedyVerificationResult verify_greedy_proposals(
      const std::vector<std::vector<int>>& proposals,
      const std::vector<int>& target_first_tokens,
      const std::vector<int>& slots,
      const std::vector<int>& maximum_accepted_tokens = {});
  [[nodiscard]] bool has_assistant() const;
  std::vector<std::vector<int>> draft_four(
      const std::vector<int>& last_tokens, const std::vector<int>& slots,
      const std::vector<int>& forced_first_tokens = {}, int depth = 4);
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
