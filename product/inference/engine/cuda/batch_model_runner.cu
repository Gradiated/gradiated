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
  std::vector<int> slot_positions;
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
  Allocation device_positions;
  Allocation device_slots;
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
        vocabulary(static_cast<int>(model_config.vocabulary_size)),
        slot_positions(static_cast<std::size_t>(requested_batch), 0), caches(),
        cache_payload_bytes(cache_payload(model_config, requested_batch, max_context, &caches)),
        layers(model_config, device_weights, max_context, max_context, requested_batch), lm_head(),
        cache_arena(2ULL * cache_payload_bytes),
        hidden_a(2ULL * std::max(requested_batch, max_context) * hidden),
        hidden_b(2ULL * std::max(requested_batch, max_context) * hidden),
        final_hidden(2ULL * requested_batch * hidden),
        logits(2ULL * requested_batch * vocabulary),
        device_input_tokens(sizeof(int) * std::max(requested_batch, max_context)),
        device_output_tokens(sizeof(int) * requested_batch),
        device_positions(sizeof(int) * requested_batch), device_slots(sizeof(int) * requested_batch),
        argmax_workspace(argmax_bf16_workspace_bytes(vocabulary) * requested_batch) {
    if (requested_batch <= 0 || max_context <= 0) throw std::runtime_error("invalid batch model shape");
  }

  void* key_cache(std::size_t layer) {
    return static_cast<unsigned char*>(cache_arena.get()) + caches.at(layer).offset;
  }
  void* value_cache(std::size_t layer) {
    return static_cast<unsigned char*>(cache_arena.get()) + cache_payload_bytes + caches.at(layer).offset;
  }
  void* slot_key_cache(std::size_t layer, int slot) {
    return static_cast<unsigned char*>(key_cache(layer)) +
           2ULL * slot * caches.at(layer).capacity * config.layers.at(layer).kv_width();
  }
  void* slot_value_cache(std::size_t layer, int slot) {
    return static_cast<unsigned char*>(value_cache(layer)) +
           2ULL * slot * caches.at(layer).capacity * config.layers.at(layer).kv_width();
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
  std::fill(state.slot_positions.begin(), state.slot_positions.end(), state.current_position);
  return result;
}

int Gemma4BatchModelRunner::prefill_slot(int slot, const std::vector<int>& token_ids,
                                         int chunk_tokens) {
  auto& state = *implementation_;
  if (slot < 0 || slot >= state.batch_size || token_ids.empty() ||
      token_ids.size() > static_cast<std::size_t>(state.maximum_context) || chunk_tokens <= 0 ||
      chunk_tokens > state.maximum_context) {
    throw std::runtime_error("invalid slot prefill shape");
  }
  for (const int token_id : token_ids) {
    if (token_id < 0 || token_id >= state.vocabulary) {
      throw std::runtime_error("slot prompt contains an invalid token id");
    }
  }
  void* final_input = nullptr;
  int final_chunk_tokens = 0;
  for (int position = 0; position < static_cast<int>(token_ids.size()); position += chunk_tokens) {
    const int tokens = std::min(chunk_tokens, static_cast<int>(token_ids.size()) - position);
    check(cudaMemcpy(state.device_input_tokens.get(), token_ids.data() + position,
                     static_cast<std::size_t>(tokens) * sizeof(int), cudaMemcpyHostToDevice),
          "copy slot prompt tokens");
    embedding_batch_bf16(state.weights.at("token_embedding"),
        static_cast<const int*>(state.device_input_tokens.get()), state.hidden_a.get(), tokens,
        state.vocabulary, state.hidden, std::sqrt(static_cast<float>(state.hidden)), nullptr);
    void* input = state.hidden_a.get();
    void* output = state.hidden_b.get();
    for (std::size_t layer = 0; layer < state.config.layers.size(); ++layer) {
      const auto& cache = state.caches[layer];
      state.layers.run_prefill_chunk(static_cast<int>(layer), input, output, tokens, position,
                                     state.slot_key_cache(layer, slot),
                                     state.slot_value_cache(layer, slot), cache.capacity, nullptr);
      std::swap(input, output);
    }
    final_input = input;
    final_chunk_tokens = tokens;
  }
  const auto* last_hidden = static_cast<const unsigned char*>(final_input) +
                            2ULL * (final_chunk_tokens - 1) * state.hidden;
  rms_norm_bf16(last_hidden, state.weights.at("final_norm"), state.final_hidden.get(), 1,
                state.hidden, static_cast<float>(state.config.rms_norm_epsilon), nullptr);
  state.lm_head.run(state.final_hidden.get(), state.weights.at("token_embedding"), state.logits.get(),
                    1, state.hidden, state.vocabulary, nullptr);
  argmax_bf16(state.logits.get(), state.vocabulary,
              static_cast<int*>(state.device_output_tokens.get()), state.argmax_workspace.get(), nullptr);
  int prediction = 0;
  check(cudaMemcpy(&prediction, state.device_output_tokens.get(), sizeof(prediction),
                   cudaMemcpyDeviceToHost), "copy slot prefill token");
  state.slot_positions.at(static_cast<std::size_t>(slot)) = static_cast<int>(token_ids.size());
  return prediction;
}

std::vector<int> Gemma4BatchModelRunner::append_ragged(
    const std::vector<int>& token_ids, const std::vector<int>& slots) {
  auto& state = *implementation_;
  const int active = static_cast<int>(token_ids.size());
  if (active <= 0 || active > state.batch_size || slots.size() != token_ids.size()) {
    throw std::runtime_error("invalid ragged token batch");
  }
  std::vector<bool> seen(static_cast<std::size_t>(state.batch_size), false);
  std::vector<int> positions(static_cast<std::size_t>(active));
  int maximum_position = 0;
  for (int row = 0; row < active; ++row) {
    const int slot = slots[static_cast<std::size_t>(row)];
    const int token = token_ids[static_cast<std::size_t>(row)];
    if (slot < 0 || slot >= state.batch_size || seen[static_cast<std::size_t>(slot)] ||
        token < 0 || token >= state.vocabulary) {
      throw std::runtime_error("invalid or repeated ragged slot");
    }
    seen[static_cast<std::size_t>(slot)] = true;
    const int position = state.slot_positions[static_cast<std::size_t>(slot)];
    if (position <= 0 || position >= state.maximum_context) {
      throw std::runtime_error("ragged slot is empty or full");
    }
    positions[static_cast<std::size_t>(row)] = position;
    maximum_position = std::max(maximum_position, position);
  }
  check(cudaMemcpy(state.device_input_tokens.get(), token_ids.data(),
                   static_cast<std::size_t>(active) * sizeof(int), cudaMemcpyHostToDevice),
        "copy ragged input tokens");
  check(cudaMemcpy(state.device_positions.get(), positions.data(),
                   static_cast<std::size_t>(active) * sizeof(int), cudaMemcpyHostToDevice),
        "copy ragged positions");
  check(cudaMemcpy(state.device_slots.get(), slots.data(),
                   static_cast<std::size_t>(active) * sizeof(int), cudaMemcpyHostToDevice),
        "copy ragged slots");
  embedding_batch_bf16(state.weights.at("token_embedding"),
      static_cast<const int*>(state.device_input_tokens.get()), state.hidden_a.get(), active,
      state.vocabulary, state.hidden, std::sqrt(static_cast<float>(state.hidden)), nullptr);
  void* input = state.hidden_a.get();
  void* output = state.hidden_b.get();
  for (std::size_t layer = 0; layer < state.config.layers.size(); ++layer) {
    const auto& cache = state.caches[layer];
    const int context = std::min(maximum_position + 1, cache.capacity);
    state.layers.run_decode_ragged(
        static_cast<int>(layer), input, output, static_cast<const int*>(state.device_positions.get()),
        static_cast<const int*>(state.device_slots.get()), active, state.batch_size, context,
        state.key_cache(layer), state.value_cache(layer), cache.capacity, nullptr);
    std::swap(input, output);
  }
  rms_norm_bf16(input, state.weights.at("final_norm"), state.final_hidden.get(), active,
                state.hidden, static_cast<float>(state.config.rms_norm_epsilon), nullptr);
  state.lm_head.run(state.final_hidden.get(), state.weights.at("token_embedding"), state.logits.get(),
                    active, state.hidden, state.vocabulary, nullptr);
  const std::size_t one_workspace = argmax_bf16_workspace_bytes(state.vocabulary);
  for (int row = 0; row < active; ++row) {
    const auto* row_logits = static_cast<const unsigned char*>(state.logits.get()) +
                             2ULL * row * state.vocabulary;
    auto* row_output = static_cast<int*>(state.device_output_tokens.get()) + row;
    auto* row_workspace = static_cast<unsigned char*>(state.argmax_workspace.get()) +
                          static_cast<std::size_t>(row) * one_workspace;
    argmax_bf16(row_logits, state.vocabulary, row_output, row_workspace, nullptr);
  }
  std::vector<int> result(static_cast<std::size_t>(active));
  check(cudaMemcpy(result.data(), state.device_output_tokens.get(),
                   result.size() * sizeof(int), cudaMemcpyDeviceToHost),
        "copy ragged output tokens");
  for (const int slot : slots) ++state.slot_positions[static_cast<std::size_t>(slot)];
  return result;
}

void Gemma4BatchModelRunner::reset_slot(int slot) {
  auto& state = *implementation_;
  if (slot < 0 || slot >= state.batch_size) throw std::runtime_error("invalid cache slot");
  state.slot_positions[static_cast<std::size_t>(slot)] = 0;
}

void Gemma4BatchModelRunner::seed_empty_cache_for_benchmark(int position) {
  auto& state = *implementation_;
  if (position < 0 || position >= state.maximum_context) {
    throw std::runtime_error("invalid benchmark cache position");
  }
  check(cudaMemset(state.cache_arena.get(), 0, static_cast<std::size_t>(2ULL * state.cache_payload_bytes)),
        "zero benchmark KV cache");
  state.current_position = position;
  std::fill(state.slot_positions.begin(), state.slot_positions.end(), position);
}

int Gemma4BatchModelRunner::batch() const { return implementation_->batch_size; }
int Gemma4BatchModelRunner::position() const { return implementation_->current_position; }
int Gemma4BatchModelRunner::slot_position(int slot) const {
  if (slot < 0 || slot >= implementation_->batch_size) throw std::runtime_error("invalid cache slot");
  return implementation_->slot_positions[static_cast<std::size_t>(slot)];
}

}  // namespace gradiated::engine
