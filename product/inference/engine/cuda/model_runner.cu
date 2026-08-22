#include "gradiated/engine/model_runner.h"

#include "gradiated/engine/cuda_ops.h"
#include "gradiated/engine/device_weights.h"
#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/layer_runner.h"
#include "gradiated/engine/linear.h"

#include <cuda_runtime.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace gradiated::engine {
namespace {

constexpr std::uint64_t alignment = 256;

std::uint64_t align_up(std::uint64_t value) {
  return (value + alignment - 1U) & ~(alignment - 1U);
}

void check(cudaError_t result, const char* operation) {
  if (result != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(result));
  }
}

class Allocation {
 public:
  explicit Allocation(std::uint64_t bytes) { check(cudaMalloc(&pointer_, bytes), "allocate model workspace"); }
  ~Allocation() { cudaFree(pointer_); }
  void* get() { return pointer_; }

 private:
  void* pointer_{nullptr};
};

struct CacheLocation {
  std::uint64_t offset;
  int capacity;
};

}  // namespace

struct Gemma4ModelRunner::Implementation {
  const Gemma4Config& config;
  const DeviceWeightArena& weights;
  int maximum_context;
  int current_position{0};
  int hidden;
  int vocabulary;
  std::vector<CacheLocation> caches;
  std::uint64_t cache_payload_bytes{0};
  Gemma4LayerRunner layers;
  Bf16Linear lm_head;
  Allocation cache_arena;
  Allocation hidden_a;
  Allocation hidden_b;
  Allocation final_hidden;
  Allocation logits;
  Allocation device_token;
  Allocation argmax_workspace;

  static std::uint64_t cache_payload(const Gemma4Config& config, int maximum_context,
                                     std::vector<CacheLocation>* locations) {
    std::uint64_t bytes = 0;
    for (const auto& layer : config.layers) {
      bytes = align_up(bytes);
      const int capacity = layer.attention == AttentionKind::sliding
          ? std::min(maximum_context, static_cast<int>(config.sliding_window))
          : maximum_context;
      locations->push_back({bytes, capacity});
      bytes += 2ULL * capacity * layer.kv_width();
    }
    return align_up(bytes);
  }

  Implementation(const Gemma4Config& model_config, const DeviceWeightArena& device_weights,
                 int max_context)
      : config(model_config),
        weights(device_weights),
        maximum_context(max_context),
        hidden(static_cast<int>(model_config.hidden_size)),
        vocabulary(static_cast<int>(model_config.vocabulary_size)),
        caches(),
        cache_payload_bytes(cache_payload(model_config, max_context, &caches)),
        layers(model_config, device_weights, 1, max_context),
        lm_head(),
        cache_arena(2ULL * cache_payload_bytes),
        hidden_a(2ULL * hidden),
        hidden_b(2ULL * hidden),
        final_hidden(2ULL * hidden),
        logits(2ULL * vocabulary),
        device_token(sizeof(int)),
        argmax_workspace(argmax_bf16_workspace_bytes(vocabulary)) {
    if (max_context <= 0) throw std::runtime_error("invalid model context");
  }

  void* key_cache(std::size_t layer) {
    return static_cast<unsigned char*>(cache_arena.get()) + caches.at(layer).offset;
  }
  void* value_cache(std::size_t layer) {
    return static_cast<unsigned char*>(cache_arena.get()) + cache_payload_bytes + caches.at(layer).offset;
  }
};

Gemma4ModelRunner::Gemma4ModelRunner(const Gemma4Config& config, const DeviceWeightArena& weights,
                                     int maximum_context)
    : implementation_(std::make_unique<Implementation>(config, weights, maximum_context)) {}
Gemma4ModelRunner::~Gemma4ModelRunner() = default;

int Gemma4ModelRunner::append(int token_id) {
  auto& state = *implementation_;
  if (state.current_position >= state.maximum_context) throw std::runtime_error("model context is full");
  embedding_bf16(state.weights.at("token_embedding"), token_id, state.hidden_a.get(), state.vocabulary,
                 state.hidden, std::sqrt(static_cast<float>(state.hidden)), nullptr);
  void* input = state.hidden_a.get();
  void* output = state.hidden_b.get();
  for (std::size_t layer = 0; layer < state.config.layers.size(); ++layer) {
    const auto& cache = state.caches[layer];
    state.layers.run_decode(static_cast<int>(layer), input, output, state.current_position,
                            state.key_cache(layer), state.value_cache(layer), cache.capacity, nullptr);
    std::swap(input, output);
  }
  rms_norm_bf16(input, state.weights.at("final_norm"), state.final_hidden.get(), 1, state.hidden,
                static_cast<float>(state.config.rms_norm_epsilon), nullptr);
  state.lm_head.run(state.final_hidden.get(), state.weights.at("token_embedding"), state.logits.get(),
                    1, state.hidden, state.vocabulary, nullptr);
  argmax_bf16(state.logits.get(), state.vocabulary, static_cast<int*>(state.device_token.get()),
              state.argmax_workspace.get(), nullptr);
  int next_token = 0;
  check(cudaMemcpy(&next_token, state.device_token.get(), sizeof(next_token), cudaMemcpyDeviceToHost),
        "copy greedy token");
  ++state.current_position;
  return next_token;
}

int Gemma4ModelRunner::position() const { return implementation_->current_position; }

}  // namespace gradiated::engine
