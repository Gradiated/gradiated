#include "gradiated/engine/batch_model_runner.h"

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
std::uint64_t align_up(std::uint64_t value) { return (value + alignment - 1U) & ~(alignment - 1U); }

void check(cudaError_t result, const char* operation) {
  if (result != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(result));
  }
}

class Allocation {
 public:
  explicit Allocation(std::uint64_t bytes) { check(cudaMalloc(&pointer_, bytes), "allocate batch workspace"); }
  ~Allocation() { cudaFree(pointer_); }
  void* get() { return pointer_; }
 private:
  void* pointer_{nullptr};
};

struct CacheLocation { std::uint64_t offset; int capacity; };

}  // namespace

struct Gemma4BatchModelRunner::Implementation {
  const Gemma4Config& config;
  const DeviceWeightArena& weights;
  int batch_size;
  int maximum_context;
  int current_position{0};
  int hidden;
  int vocabulary;
  std::vector<CacheLocation> caches;
  std::uint64_t cache_payload_bytes;
  Gemma4LayerRunner layers;
  Bf16Linear lm_head;
  Allocation cache_arena;
  Allocation hidden_a;
  Allocation hidden_b;
  Allocation final_hidden;
  Allocation logits;
  Allocation device_input_tokens;
  Allocation device_output_tokens;
  Allocation argmax_workspace;

  static std::uint64_t cache_payload(const Gemma4Config& config, int batch, int maximum_context,
                                     std::vector<CacheLocation>* locations) {
    std::uint64_t bytes = 0;
    for (const auto& layer : config.layers) {
      bytes = align_up(bytes);
      const int capacity = layer.attention == AttentionKind::sliding
          ? std::min(maximum_context, static_cast<int>(config.sliding_window)) : maximum_context;
      locations->push_back({bytes, capacity});
      bytes += 2ULL * batch * capacity * layer.kv_width();
    }
    return align_up(bytes);
  }

  Implementation(const Gemma4Config& model_config, const DeviceWeightArena& device_weights,
                 int requested_batch, int max_context)
      : config(model_config), weights(device_weights), batch_size(requested_batch),
        maximum_context(max_context), hidden(static_cast<int>(model_config.hidden_size)),
        vocabulary(static_cast<int>(model_config.vocabulary_size)), caches(),
        cache_payload_bytes(cache_payload(model_config, requested_batch, max_context, &caches)),
        layers(model_config, device_weights, 1, max_context, requested_batch), lm_head(),
        cache_arena(2ULL * cache_payload_bytes), hidden_a(2ULL * requested_batch * hidden),
        hidden_b(2ULL * requested_batch * hidden), final_hidden(2ULL * requested_batch * hidden),
        logits(2ULL * requested_batch * vocabulary), device_input_tokens(sizeof(int) * requested_batch),
        device_output_tokens(sizeof(int) * requested_batch),
        argmax_workspace(argmax_bf16_workspace_bytes(vocabulary) * requested_batch) {
    if (requested_batch <= 0 || max_context <= 0) throw std::runtime_error("invalid batch model shape");
  }

  void* key_cache(std::size_t layer) {
    return static_cast<unsigned char*>(cache_arena.get()) + caches.at(layer).offset;
  }
  void* value_cache(std::size_t layer) {
    return static_cast<unsigned char*>(cache_arena.get()) + cache_payload_bytes + caches.at(layer).offset;
  }
};

Gemma4BatchModelRunner::Gemma4BatchModelRunner(const Gemma4Config& config,
                                               const DeviceWeightArena& weights,
                                               int batch, int maximum_context)
    : implementation_(std::make_unique<Implementation>(config, weights, batch, maximum_context)) {}
Gemma4BatchModelRunner::~Gemma4BatchModelRunner() = default;

std::vector<int> Gemma4BatchModelRunner::append(const std::vector<int>& token_ids) {
  auto& state = *implementation_;
  if (token_ids.size() != static_cast<std::size_t>(state.batch_size)) {
    throw std::runtime_error("token batch has the wrong size");
  }
  if (state.current_position >= state.maximum_context) throw std::runtime_error("batch context is full");
  check(cudaMemcpy(state.device_input_tokens.get(), token_ids.data(), token_ids.size() * sizeof(int),
                   cudaMemcpyHostToDevice), "copy batch input tokens");
  embedding_batch_bf16(state.weights.at("token_embedding"),
      static_cast<const int*>(state.device_input_tokens.get()), state.hidden_a.get(), state.batch_size,
      state.vocabulary, state.hidden, std::sqrt(static_cast<float>(state.hidden)), nullptr);
  void* input = state.hidden_a.get();
  void* output = state.hidden_b.get();
  for (std::size_t layer = 0; layer < state.config.layers.size(); ++layer) {
    const auto& cache = state.caches[layer];
    state.layers.run_decode_batch(static_cast<int>(layer), input, output, state.batch_size,
        state.current_position, state.key_cache(layer), state.value_cache(layer), cache.capacity, nullptr);
    std::swap(input, output);
  }
  rms_norm_bf16(input, state.weights.at("final_norm"), state.final_hidden.get(), state.batch_size,
                state.hidden, static_cast<float>(state.config.rms_norm_epsilon), nullptr);
  state.lm_head.run(state.final_hidden.get(), state.weights.at("token_embedding"), state.logits.get(),
                    state.batch_size, state.hidden, state.vocabulary, nullptr);
  const std::size_t one_workspace = argmax_bf16_workspace_bytes(state.vocabulary);
  for (int row = 0; row < state.batch_size; ++row) {
    const auto* row_logits = static_cast<const unsigned char*>(state.logits.get()) +
                             2ULL * row * state.vocabulary;
    auto* row_output = static_cast<int*>(state.device_output_tokens.get()) + row;
    auto* row_workspace = static_cast<unsigned char*>(state.argmax_workspace.get()) + row * one_workspace;
    argmax_bf16(row_logits, state.vocabulary, row_output, row_workspace, nullptr);
  }
  std::vector<int> result(state.batch_size);
  check(cudaMemcpy(result.data(), state.device_output_tokens.get(), result.size() * sizeof(int),
                   cudaMemcpyDeviceToHost), "copy batch output tokens");
  ++state.current_position;
  return result;
}

void Gemma4BatchModelRunner::seed_empty_cache_for_benchmark(int position) {
  auto& state = *implementation_;
  if (position < 0 || position >= state.maximum_context) {
    throw std::runtime_error("invalid benchmark cache position");
  }
  check(cudaMemset(state.cache_arena.get(), 0, static_cast<std::size_t>(2ULL * state.cache_payload_bytes)),
        "zero benchmark KV cache");
  state.current_position = position;
}

int Gemma4BatchModelRunner::batch() const { return implementation_->batch_size; }
int Gemma4BatchModelRunner::position() const { return implementation_->current_position; }

}  // namespace gradiated::engine
