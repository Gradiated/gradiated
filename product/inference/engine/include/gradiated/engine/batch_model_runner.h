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
  // Performance harness only: fills every allocated KV page with zero and advances logical time.
  void seed_empty_cache_for_benchmark(int position);
  [[nodiscard]] int batch() const;
  [[nodiscard]] int position() const;

 private:
  struct Implementation;
  std::unique_ptr<Implementation> implementation_;
};

}  // namespace gradiated::engine
