#pragma once

#include <memory>

namespace gradiated::engine {

class Gemma4ModelRunner {
 public:
  Gemma4ModelRunner(const struct Gemma4Config& config, const class DeviceWeightArena& weights,
                    int maximum_context);
  ~Gemma4ModelRunner();
  Gemma4ModelRunner(const Gemma4ModelRunner&) = delete;
  Gemma4ModelRunner& operator=(const Gemma4ModelRunner&) = delete;

  // Appends one token to the KV cache and returns the greedy next token.
  int append(int token_id);
  [[nodiscard]] int position() const;

 private:
  struct Implementation;
  std::unique_ptr<Implementation> implementation_;
};

}  // namespace gradiated::engine
