#include "gradiated/engine/batch_model_runner.h"

#include "gradiated/engine/assistant_runner.h"
#include "gradiated/engine/cuda_ops.h"
#include "gradiated/engine/device_weights.h"
#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/layer_runner.h"
#include "gradiated/engine/linear.h"

#include <cuda_runtime.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace gradiated::engine {
namespace {

constexpr std::uint64_t alignment = 256;
constexpr int speculative_depth = 4;
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
  struct DecodeGraph {
    cudaGraph_t graph{};
    cudaGraphExec_t executable{};

    ~DecodeGraph() {
      if (executable != nullptr) cudaGraphExecDestroy(executable);
      if (graph != nullptr) cudaGraphDestroy(graph);
    }
  };

  const Gemma4Config& config;
  const DeviceWeightArena& weights;
  const Fp8WeightArena* fp8_weights;
  const DeviceWeightArena* assistant_weights;
  int batch_size;
  int maximum_context;
  int current_position{0};
  int hidden;
  int vocabulary;
  int shared_sliding_layer{-1};
  int shared_global_layer{-1};
  std::vector<int> slot_positions;
  std::vector<CacheLocation> caches;
  std::uint64_t cache_payload_bytes;
  std::vector<std::uint64_t> speculative_backup_offsets;
  std::uint64_t speculative_backup_payload_bytes;
  Gemma4LayerRunner layers;
  Bf16Linear lm_head;
  Fp8Linear fp8_lm_head;
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
  Allocation fp8_final_hidden;
  Allocation fp8_final_scales;
  Allocation target_hidden_slots;
  Allocation speculative_backup_arena;
  Allocation device_cache_pointers;
  cudaStream_t decode_stream{};
  std::unique_ptr<Gemma4AssistantRunner> assistant;
  std::map<std::pair<int, int>, std::unique_ptr<DecodeGraph>> decode_graphs;

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

  static std::uint64_t speculative_backup_payload(
      const Gemma4Config& config, int batch, std::vector<std::uint64_t>* offsets) {
    std::uint64_t bytes = 0;
    for (const auto& layer : config.layers) {
      if (layer.attention != AttentionKind::sliding) {
        offsets->push_back(std::numeric_limits<std::uint64_t>::max());
        continue;
      }
      bytes = align_up(bytes);
      offsets->push_back(bytes);
      bytes += 2ULL * batch * speculative_depth * layer.kv_width();
    }
    return align_up(bytes);
  }

  Implementation(const Gemma4Config& model_config, const DeviceWeightArena& device_weights,
                 int requested_batch, int max_context, const Fp8WeightArena* decode_weights,
                 const DeviceWeightArena* draft_weights)
      : config(model_config), weights(device_weights), fp8_weights(decode_weights),
        assistant_weights(draft_weights),
        batch_size(requested_batch),
        maximum_context(max_context), hidden(static_cast<int>(model_config.hidden_size)),
        vocabulary(static_cast<int>(model_config.vocabulary_size)),
        slot_positions(static_cast<std::size_t>(requested_batch), 0), caches(),
        cache_payload_bytes(cache_payload(model_config, requested_batch, max_context, &caches)),
        speculative_backup_offsets(),
        speculative_backup_payload_bytes(speculative_backup_payload(
            model_config, requested_batch, &speculative_backup_offsets)),
        layers(model_config, device_weights, max_context, max_context, requested_batch,
               decode_weights), lm_head(),
        fp8_lm_head(decode_weights == nullptr ? Fp8Scaling::tensor : decode_weights->scaling()),
        cache_arena(2ULL * cache_payload_bytes),
        hidden_a(2ULL * std::max(requested_batch, max_context) * hidden),
        hidden_b(2ULL * std::max(requested_batch, max_context) * hidden),
        final_hidden(2ULL * speculative_depth * requested_batch * hidden),
        logits(2ULL * speculative_depth * requested_batch * vocabulary),
        device_input_tokens(sizeof(int) * std::max(requested_batch, max_context)),
        device_output_tokens(sizeof(int) * speculative_depth * requested_batch),
        device_positions(sizeof(int) * requested_batch), device_slots(sizeof(int) * requested_batch),
        argmax_workspace(argmax_bf16_workspace_bytes(vocabulary) * speculative_depth *
                         requested_batch),
        fp8_final_hidden(static_cast<std::uint64_t>(speculative_depth) * requested_batch * hidden),
        fp8_final_scales(sizeof(float) * static_cast<std::uint64_t>(speculative_depth) *
                         requested_batch *
                         ((hidden + 127) / 128)),
        target_hidden_slots(2ULL * requested_batch * hidden),
        speculative_backup_arena(2ULL * speculative_backup_payload_bytes),
        device_cache_pointers(2ULL * sizeof(void*) * requested_batch) {
    if (requested_batch <= 0 || max_context <= 0) throw std::runtime_error("invalid batch model shape");
    check(cudaStreamCreateWithFlags(&decode_stream, cudaStreamNonBlocking),
          "create decode stream");
    for (std::size_t layer = 0; layer < config.layers.size(); ++layer) {
      if (config.layers[layer].attention == AttentionKind::sliding) {
        shared_sliding_layer = static_cast<int>(layer);
      } else {
        shared_global_layer = static_cast<int>(layer);
      }
    }
    if (draft_weights != nullptr) {
      if (shared_sliding_layer < 0 || shared_global_layer < 0) {
        throw std::runtime_error("target does not expose both assistant KV types");
      }
      assistant = std::make_unique<Gemma4AssistantRunner>(
          *draft_weights, requested_batch, max_context);
    }
    // Global batched suffix attention pads shorter requests to one GEMM width. Zeroing once makes
    // every unread cache tail finite; masked probabilities then contribute exactly zero in PV.
    check(cudaMemset(cache_arena.get(), 0, static_cast<std::size_t>(2ULL * cache_payload_bytes)),
          "initialize KV cache arena");
  }

  ~Implementation() {
    decode_graphs.clear();
    if (decode_stream != nullptr) cudaStreamDestroy(decode_stream);
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
  void* speculative_key_backup(std::size_t layer) {
    return static_cast<unsigned char*>(speculative_backup_arena.get()) +
           speculative_backup_offsets.at(layer);
  }
  void* speculative_value_backup(std::size_t layer) {
    return static_cast<unsigned char*>(speculative_backup_arena.get()) +
           speculative_backup_payload_bytes + speculative_backup_offsets.at(layer);
  }

  void run_decode_lm_head(const void* input, void* output, int rows, cudaStream_t stream) {
    if (fp8_weights == nullptr) {
      lm_head.run(input, weights.at("token_embedding"), output,
                  rows, hidden, vocabulary, stream);
      return;
    }
    auto* scales = static_cast<float*>(fp8_final_scales.get());
    if (fp8_weights->scaling() == Fp8Scaling::tensor) {
      quantize_bf16_to_fp8_e4m3(input, fp8_final_hidden.get(), scales,
                                static_cast<std::size_t>(rows) * hidden, stream);
    } else if (fp8_weights->scaling() == Fp8Scaling::channel) {
      quantize_bf16_rows_to_fp8_e4m3(input, fp8_final_hidden.get(), scales,
                                     rows, hidden, stream);
    } else {
      quantize_bf16_activation_to_fp8_block_128(input, fp8_final_hidden.get(), scales,
                                                rows, hidden, stream);
    }
    fp8_lm_head.run(fp8_final_hidden.get(), scales, fp8_weights->at("token_embedding"),
                    fp8_weights->scale("token_embedding"), output,
                    rows, hidden, vocabulary, stream);
  }

  void enqueue_ragged_decode(int active, int maximum_context_length) {
    embedding_batch_bf16(weights.at("token_embedding"),
        static_cast<const int*>(device_input_tokens.get()), hidden_a.get(), active,
        vocabulary, hidden, std::sqrt(static_cast<float>(hidden)), decode_stream);
    void* input = hidden_a.get();
    void* output = hidden_b.get();
    for (std::size_t layer = 0; layer < config.layers.size(); ++layer) {
      const auto& cache = caches[layer];
      const int context = std::min(maximum_context_length, cache.capacity);
      layers.run_decode_ragged(
          static_cast<int>(layer), input, output,
          static_cast<const int*>(device_positions.get()),
          static_cast<const int*>(device_slots.get()), active, batch_size, context,
          key_cache(layer), value_cache(layer), cache.capacity, decode_stream);
      std::swap(input, output);
    }
    rms_norm_bf16(input, weights.at("final_norm"), final_hidden.get(), active, hidden,
                  static_cast<float>(config.rms_norm_epsilon), decode_stream);
    scatter_rows_bf16(final_hidden.get(), static_cast<const int*>(device_slots.get()),
                      target_hidden_slots.get(), active, hidden, decode_stream);
    run_decode_lm_head(final_hidden.get(), logits.get(), active, decode_stream);
    const std::size_t one_workspace = argmax_bf16_workspace_bytes(vocabulary);
    for (int row = 0; row < active; ++row) {
      const auto* row_logits = static_cast<const unsigned char*>(logits.get()) +
                               2ULL * row * vocabulary;
      auto* row_output = static_cast<int*>(device_output_tokens.get()) + row;
      auto* row_workspace = static_cast<unsigned char*>(argmax_workspace.get()) +
                            static_cast<std::size_t>(row) * one_workspace;
      argmax_bf16(row_logits, vocabulary, row_output, row_workspace, decode_stream);
    }
  }

  DecodeGraph& capture_decode_graph(int active, int maximum_context_length) {
    auto captured = std::make_unique<DecodeGraph>();
    check(cudaStreamBeginCapture(decode_stream, cudaStreamCaptureModeThreadLocal),
          "begin ragged decode graph capture");
    enqueue_ragged_decode(active, maximum_context_length);
    check(cudaStreamEndCapture(decode_stream, &captured->graph),
          "end ragged decode graph capture");
    check(cudaGraphInstantiate(&captured->executable, captured->graph, 0),
          "instantiate ragged decode graph");
    DecodeGraph& result = *captured;
    decode_graphs.emplace(std::make_pair(active, maximum_context_length), std::move(captured));
    return result;
  }
};

Gemma4BatchModelRunner::Gemma4BatchModelRunner(const Gemma4Config& config,
                                               const DeviceWeightArena& weights,
                                               int batch, int maximum_context,
                                               const Fp8WeightArena* fp8_weights,
                                               const DeviceWeightArena* assistant_weights)
    : implementation_(std::make_unique<Implementation>(config, weights, batch, maximum_context,
                                                        fp8_weights, assistant_weights)) {}
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
  state.run_decode_lm_head(state.final_hidden.get(), state.logits.get(), state.batch_size, nullptr);
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
  reset_slot(slot);
  return prefill_slot_from_prefix(slot, token_ids, 0, chunk_tokens);
}

int Gemma4BatchModelRunner::prefill_slot_from_prefix(
    int slot, const std::vector<int>& token_ids, int cached_prefix_tokens, int chunk_tokens) {
  auto& state = *implementation_;
  if (slot < 0 || slot >= state.batch_size || token_ids.empty() ||
      token_ids.size() > static_cast<std::size_t>(state.maximum_context) || chunk_tokens <= 0 ||
      chunk_tokens > state.maximum_context || cached_prefix_tokens < 0 ||
      cached_prefix_tokens >= static_cast<int>(token_ids.size()) ||
      state.slot_positions.at(static_cast<std::size_t>(slot)) != cached_prefix_tokens) {
    throw std::runtime_error("invalid slot prefill shape");
  }
  std::optional<int> prediction;
  while (!prediction) prediction = prefill_slot_chunk(slot, token_ids, chunk_tokens);
  return *prediction;
}

std::optional<int> Gemma4BatchModelRunner::prefill_slot_chunk(
    int slot, const std::vector<int>& token_ids, int chunk_tokens) {
  auto& state = *implementation_;
  if (slot < 0 || slot >= state.batch_size || token_ids.empty() ||
      token_ids.size() > static_cast<std::size_t>(state.maximum_context) || chunk_tokens <= 0 ||
      chunk_tokens > state.maximum_context) {
    throw std::runtime_error("invalid slot prefill chunk shape");
  }
  const int position = state.slot_positions.at(static_cast<std::size_t>(slot));
  if (position < 0 || position >= static_cast<int>(token_ids.size())) {
    throw std::runtime_error("slot prefill chunk does not extend resident context");
  }
  const int tokens = std::min(chunk_tokens, static_cast<int>(token_ids.size()) - position);
  for (int index = position; index < position + tokens; ++index) {
    const int token_id = token_ids[static_cast<std::size_t>(index)];
    if (token_id < 0 || token_id >= state.vocabulary) {
      throw std::runtime_error("slot prompt contains an invalid token id");
    }
  }
  check(cudaMemcpy(state.device_input_tokens.get(), token_ids.data() + position,
                   static_cast<std::size_t>(tokens) * sizeof(int), cudaMemcpyHostToDevice),
        "copy slot prompt chunk tokens");
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
  state.slot_positions.at(static_cast<std::size_t>(slot)) = position + tokens;
  if (position + tokens != static_cast<int>(token_ids.size())) return std::nullopt;

  const auto* last_hidden = static_cast<const unsigned char*>(input) +
                            2ULL * (tokens - 1) * state.hidden;
  rms_norm_bf16(last_hidden, state.weights.at("final_norm"), state.final_hidden.get(), 1,
                state.hidden, static_cast<float>(state.config.rms_norm_epsilon), nullptr);
  check(cudaMemcpy(state.device_slots.get(), &slot, sizeof(slot), cudaMemcpyHostToDevice),
        "copy prefill hidden slot");
  scatter_rows_bf16(state.final_hidden.get(), static_cast<const int*>(state.device_slots.get()),
                    state.target_hidden_slots.get(), 1, state.hidden, nullptr);
  state.lm_head.run(state.final_hidden.get(), state.weights.at("token_embedding"), state.logits.get(),
                    1, state.hidden, state.vocabulary, nullptr);
  argmax_bf16(state.logits.get(), state.vocabulary,
              static_cast<int*>(state.device_output_tokens.get()), state.argmax_workspace.get(), nullptr);
  int prediction = 0;
  check(cudaMemcpy(&prediction, state.device_output_tokens.get(), sizeof(prediction),
                   cudaMemcpyDeviceToHost), "copy slot prefill token");
  return prediction;
}

std::vector<int> Gemma4BatchModelRunner::prefill_slots_suffix(
    const std::vector<int>& slots,
    const std::vector<const std::vector<int>*>& token_ids) {
  auto& state = *implementation_;
  const int requests = static_cast<int>(slots.size());
  if (requests <= 0 || requests > state.batch_size || token_ids.size() != slots.size()) {
    throw std::runtime_error("invalid batched suffix prefill shape");
  }
  std::vector<bool> seen(static_cast<std::size_t>(state.batch_size), false);
  std::vector<int> counts(static_cast<std::size_t>(requests));
  std::vector<int> positions(static_cast<std::size_t>(requests));
  std::vector<int> last_rows(static_cast<std::size_t>(requests));
  std::vector<int> packed_tokens;
  for (int request = 0; request < requests; ++request) {
    const int slot = slots[static_cast<std::size_t>(request)];
    const auto* prompt = token_ids[static_cast<std::size_t>(request)];
    if (slot < 0 || slot >= state.batch_size || seen[static_cast<std::size_t>(slot)] ||
        prompt == nullptr || prompt->empty() ||
        prompt->size() > static_cast<std::size_t>(state.maximum_context)) {
      throw std::runtime_error("invalid batched suffix prefill request");
    }
    seen[static_cast<std::size_t>(slot)] = true;
    const int position = state.slot_positions[static_cast<std::size_t>(slot)];
    const int count = static_cast<int>(prompt->size()) - position;
    if (position < 0 || count <= 0) {
      throw std::runtime_error("batched suffix does not extend resident context");
    }
    positions[static_cast<std::size_t>(request)] = position;
    counts[static_cast<std::size_t>(request)] = count;
    for (int index = position; index < static_cast<int>(prompt->size()); ++index) {
      const int token = (*prompt)[static_cast<std::size_t>(index)];
      if (token < 0 || token >= state.vocabulary) {
        throw std::runtime_error("batched suffix contains an invalid token id");
      }
      packed_tokens.push_back(token);
    }
    last_rows[static_cast<std::size_t>(request)] =
        static_cast<int>(packed_tokens.size()) - 1;
  }
  if (packed_tokens.size() > static_cast<std::size_t>(state.maximum_context)) {
    throw std::runtime_error("batched suffix exceeds shared projection workspace");
  }

  check(cudaMemcpy(state.device_input_tokens.get(), packed_tokens.data(),
                   packed_tokens.size() * sizeof(int), cudaMemcpyHostToDevice),
        "copy batched suffix tokens");
  embedding_batch_bf16(
      state.weights.at("token_embedding"),
      static_cast<const int*>(state.device_input_tokens.get()), state.hidden_a.get(),
      static_cast<int>(packed_tokens.size()), state.vocabulary, state.hidden,
      std::sqrt(static_cast<float>(state.hidden)), nullptr);
  void* input = state.hidden_a.get();
  void* output = state.hidden_b.get();
  for (std::size_t layer = 0; layer < state.config.layers.size(); ++layer) {
    std::vector<void*> key_caches;
    std::vector<void*> value_caches;
    std::vector<int> capacities(static_cast<std::size_t>(requests), state.caches[layer].capacity);
    key_caches.reserve(static_cast<std::size_t>(requests));
    value_caches.reserve(static_cast<std::size_t>(requests));
    for (const int slot : slots) {
      key_caches.push_back(state.slot_key_cache(layer, slot));
      value_caches.push_back(state.slot_value_cache(layer, slot));
    }
    state.layers.run_prefill_chunks(static_cast<int>(layer), input, output, counts, positions,
                                    key_caches, value_caches, capacities, nullptr);
    std::swap(input, output);
  }
  check(cudaMemcpy(state.device_positions.get(), last_rows.data(),
                   last_rows.size() * sizeof(int), cudaMemcpyHostToDevice),
        "copy batched suffix final rows");
  gather_rows_bf16(input, static_cast<const int*>(state.device_positions.get()), output,
                   requests, state.hidden, nullptr);
  rms_norm_bf16(output, state.weights.at("final_norm"), state.final_hidden.get(), requests,
                state.hidden, static_cast<float>(state.config.rms_norm_epsilon), nullptr);
  check(cudaMemcpy(state.device_slots.get(), slots.data(), slots.size() * sizeof(int),
                   cudaMemcpyHostToDevice), "copy suffix hidden slots");
  scatter_rows_bf16(state.final_hidden.get(), static_cast<const int*>(state.device_slots.get()),
                    state.target_hidden_slots.get(), requests, state.hidden, nullptr);
  state.lm_head.run(state.final_hidden.get(), state.weights.at("token_embedding"),
                    state.logits.get(), requests, state.hidden, state.vocabulary, nullptr);
  const std::size_t one_workspace = argmax_bf16_workspace_bytes(state.vocabulary);
  for (int row = 0; row < requests; ++row) {
    const auto* row_logits = static_cast<const unsigned char*>(state.logits.get()) +
                             2ULL * row * state.vocabulary;
    auto* row_output = static_cast<int*>(state.device_output_tokens.get()) + row;
    auto* row_workspace = static_cast<unsigned char*>(state.argmax_workspace.get()) +
                          static_cast<std::size_t>(row) * one_workspace;
    argmax_bf16(row_logits, state.vocabulary, row_output, row_workspace, nullptr);
  }
  std::vector<int> predictions(static_cast<std::size_t>(requests));
  check(cudaMemcpy(predictions.data(), state.device_output_tokens.get(),
                   predictions.size() * sizeof(int), cudaMemcpyDeviceToHost),
        "copy batched suffix predictions");
  for (int request = 0; request < requests; ++request) {
    state.slot_positions[static_cast<std::size_t>(slots[static_cast<std::size_t>(request)])] =
        static_cast<int>(token_ids[static_cast<std::size_t>(request)]->size());
  }
  return predictions;
}

std::uint64_t Gemma4BatchModelRunner::clone_slot(int source_slot, int destination_slot) {
  auto& state = *implementation_;
  if (source_slot < 0 || source_slot >= state.batch_size || destination_slot < 0 ||
      destination_slot >= state.batch_size || source_slot == destination_slot) {
    throw std::runtime_error("invalid cache slot clone");
  }
  const int position = state.slot_positions.at(static_cast<std::size_t>(source_slot));
  if (position <= 0 || position >= state.maximum_context) {
    throw std::runtime_error("source cache slot is empty or full");
  }
  std::uint64_t copied_bytes = 0;
  for (std::size_t layer = 0; layer < state.config.layers.size(); ++layer) {
    const auto& cache = state.caches[layer];
    const int resident_tokens = std::min(position, cache.capacity);
    const std::size_t bytes = 2ULL * static_cast<std::size_t>(resident_tokens) *
                              state.config.layers[layer].kv_width();
    clone_kv_cache_prefix_bf16(
        state.slot_key_cache(layer, source_slot), state.slot_value_cache(layer, source_slot),
        state.slot_key_cache(layer, destination_slot),
        state.slot_value_cache(layer, destination_slot),
        static_cast<int>(state.config.layers[layer].kv_heads), resident_tokens,
        static_cast<int>(state.config.layers[layer].head_dimension), cache.capacity, nullptr);
    copied_bytes += 2ULL * bytes;
  }
  check(cudaMemcpy(
            static_cast<unsigned char*>(state.target_hidden_slots.get()) +
                2ULL * destination_slot * state.hidden,
            static_cast<unsigned char*>(state.target_hidden_slots.get()) +
                2ULL * source_slot * state.hidden,
            2ULL * state.hidden, cudaMemcpyDeviceToDevice),
        "clone slot target hidden state");
  check(cudaDeviceSynchronize(), "synchronize slot cache clone");
  state.slot_positions.at(static_cast<std::size_t>(destination_slot)) = position;
  return copied_bytes;
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
  check(cudaMemcpyAsync(state.device_input_tokens.get(), token_ids.data(),
                   static_cast<std::size_t>(active) * sizeof(int), cudaMemcpyHostToDevice,
                   state.decode_stream),
        "copy ragged input tokens");
  check(cudaMemcpyAsync(state.device_positions.get(), positions.data(),
                   static_cast<std::size_t>(active) * sizeof(int), cudaMemcpyHostToDevice,
                   state.decode_stream),
        "copy ragged positions");
  check(cudaMemcpyAsync(state.device_slots.get(), slots.data(),
                   static_cast<std::size_t>(active) * sizeof(int), cudaMemcpyHostToDevice,
                   state.decode_stream),
        "copy ragged slots");
  // A 256-token context bucket allows the captured launch graph to survive ordinary decode
  // steps. Per-row positions still mask every invalid score, so padding changes work, not math.
  constexpr int context_bucket = 256;
  const int maximum_context_length = std::min(
      state.maximum_context,
      ((maximum_position + 1 + context_bucket - 1) / context_bucket) * context_bucket);
  const auto graph_key = std::make_pair(active, maximum_context_length);
  const auto existing = state.decode_graphs.find(graph_key);
  const bool needs_capture = existing == state.decode_graphs.end();
  if (needs_capture) {
    state.enqueue_ragged_decode(active, maximum_context_length);
  } else {
    check(cudaGraphLaunch(existing->second->executable, state.decode_stream),
          "launch ragged decode graph");
  }
  std::vector<int> result(static_cast<std::size_t>(active));
  check(cudaMemcpyAsync(result.data(), state.device_output_tokens.get(),
                   result.size() * sizeof(int), cudaMemcpyDeviceToHost, state.decode_stream),
        "copy ragged output tokens");
  check(cudaStreamSynchronize(state.decode_stream), "synchronize ragged decode");
  if (needs_capture) {
    static_cast<void>(state.capture_decode_graph(active, maximum_context_length));
  }
  for (const int slot : slots) ++state.slot_positions[static_cast<std::size_t>(slot)];
  return result;
}

GreedyVerificationResult Gemma4BatchModelRunner::verify_greedy_proposals(
    const std::vector<std::vector<int>>& proposals,
    const std::vector<int>& target_first_tokens, const std::vector<int>& slots,
    const std::vector<int>& maximum_accepted_tokens) {
  auto& state = *implementation_;
  const int requests = static_cast<int>(proposals.size());
  const int depth = requests == 0 ? 0 : static_cast<int>(proposals.front().size());
  if (state.fp8_weights == nullptr || requests <= 0 || requests > state.batch_size ||
      depth <= 0 || depth > speculative_depth ||
      target_first_tokens.size() != proposals.size() || slots.size() != proposals.size()) {
    throw std::runtime_error("invalid greedy verification batch");
  }
  if (!maximum_accepted_tokens.empty() && maximum_accepted_tokens.size() != proposals.size()) {
    throw std::runtime_error("speculative acceptance caps do not match request count");
  }
  std::vector<bool> seen(static_cast<std::size_t>(state.batch_size), false);
  std::vector<int> positions(static_cast<std::size_t>(requests));
  std::vector<int> counts(static_cast<std::size_t>(requests), depth);
  std::vector<int> capacities(static_cast<std::size_t>(requests));
  std::vector<int> packed_tokens;
  packed_tokens.reserve(static_cast<std::size_t>(requests * depth));
  for (int request = 0; request < requests; ++request) {
    const int slot = slots[static_cast<std::size_t>(request)];
    if (slot < 0 || slot >= state.batch_size || seen[static_cast<std::size_t>(slot)] ||
        static_cast<int>(proposals[static_cast<std::size_t>(request)].size()) != depth) {
      throw std::runtime_error("invalid or repeated speculative slot");
    }
    seen[static_cast<std::size_t>(slot)] = true;
    const int position = state.slot_positions[static_cast<std::size_t>(slot)];
    if (position <= 0 || position + depth > state.maximum_context) {
      throw std::runtime_error("speculative slot is empty or lacks context capacity");
    }
    positions[static_cast<std::size_t>(request)] = position;
    for (const int token : proposals[static_cast<std::size_t>(request)]) {
      if (token < 0 || token >= state.vocabulary) {
        throw std::runtime_error("speculative proposal contains an invalid token");
      }
      packed_tokens.push_back(token);
    }
  }

  check(cudaMemcpy(state.device_input_tokens.get(), packed_tokens.data(),
                   packed_tokens.size() * sizeof(int), cudaMemcpyHostToDevice),
        "copy speculative proposal tokens");
  check(cudaMemcpy(state.device_positions.get(), positions.data(),
                   positions.size() * sizeof(int), cudaMemcpyHostToDevice),
        "copy speculative positions");
  embedding_batch_bf16(
      state.weights.at("token_embedding"),
      static_cast<const int*>(state.device_input_tokens.get()), state.hidden_a.get(),
      static_cast<int>(packed_tokens.size()), state.vocabulary, state.hidden,
      std::sqrt(static_cast<float>(state.hidden)), nullptr);
  void* input = state.hidden_a.get();
  void* output = state.hidden_b.get();
  std::vector<void*> key_caches(static_cast<std::size_t>(requests));
  std::vector<void*> value_caches(static_cast<std::size_t>(requests));
  for (std::size_t layer = 0; layer < state.config.layers.size(); ++layer) {
    std::fill(capacities.begin(), capacities.end(), state.caches[layer].capacity);
    for (int request = 0; request < requests; ++request) {
      const int slot = slots[static_cast<std::size_t>(request)];
      key_caches[static_cast<std::size_t>(request)] = state.slot_key_cache(layer, slot);
      value_caches[static_cast<std::size_t>(request)] = state.slot_value_cache(layer, slot);
    }
    if (state.config.layers[layer].attention == AttentionKind::sliding) {
      std::vector<void*> pointers;
      pointers.reserve(static_cast<std::size_t>(2 * requests));
      pointers.insert(pointers.end(), key_caches.begin(), key_caches.end());
      pointers.insert(pointers.end(), value_caches.begin(), value_caches.end());
      check(cudaMemcpy(state.device_cache_pointers.get(), pointers.data(),
                       pointers.size() * sizeof(void*), cudaMemcpyHostToDevice),
            "copy speculative cache pointers for backup");
      auto** pointer_base = static_cast<void**>(state.device_cache_pointers.get());
      backup_kv_ring_spans_bf16(
          reinterpret_cast<const void* const*>(pointer_base),
          reinterpret_cast<const void* const*>(pointer_base + requests),
          state.speculative_key_backup(layer), state.speculative_value_backup(layer),
          static_cast<const int*>(state.device_positions.get()), requests,
          static_cast<int>(state.config.layers[layer].kv_heads), depth,
          static_cast<int>(state.config.layers[layer].head_dimension),
          state.caches[layer].capacity, nullptr);
    }
    state.layers.run_prefill_chunks(
        static_cast<int>(layer), input, output, counts, positions, key_caches, value_caches,
        capacities, nullptr, true);
    std::swap(input, output);
  }

  const int rows = requests * depth;
  rms_norm_bf16(input, state.weights.at("final_norm"), state.final_hidden.get(), rows,
                state.hidden, static_cast<float>(state.config.rms_norm_epsilon), nullptr);
  state.run_decode_lm_head(state.final_hidden.get(), state.logits.get(), rows, nullptr);
  const std::size_t one_workspace = argmax_bf16_workspace_bytes(state.vocabulary);
  for (int row = 0; row < rows; ++row) {
    const auto* row_logits = static_cast<const unsigned char*>(state.logits.get()) +
                             2ULL * row * state.vocabulary;
    auto* row_output = static_cast<int*>(state.device_output_tokens.get()) + row;
    auto* row_workspace = static_cast<unsigned char*>(state.argmax_workspace.get()) +
                          static_cast<std::size_t>(row) * one_workspace;
    argmax_bf16(row_logits, state.vocabulary, row_output, row_workspace, nullptr);
  }
  std::vector<int> target_predictions(static_cast<std::size_t>(rows));
  check(cudaMemcpy(target_predictions.data(), state.device_output_tokens.get(),
                   target_predictions.size() * sizeof(int), cudaMemcpyDeviceToHost),
        "copy speculative target predictions");

  GreedyVerificationResult result;
  result.accepted_tokens.resize(static_cast<std::size_t>(requests));
  result.next_tokens.resize(static_cast<std::size_t>(requests));
  for (int request = 0; request < requests; ++request) {
    int accepted = 0;
    const int row_start = request * depth;
    const int acceptance_cap = maximum_accepted_tokens.empty()
        ? depth
        : std::clamp(maximum_accepted_tokens[static_cast<std::size_t>(request)],
                     0, depth);
    while (accepted < acceptance_cap) {
      const int expected = accepted == 0
          ? target_first_tokens[static_cast<std::size_t>(request)]
          : target_predictions[static_cast<std::size_t>(row_start + accepted - 1)];
      if (proposals[static_cast<std::size_t>(request)][static_cast<std::size_t>(accepted)] !=
          expected) {
        break;
      }
      ++accepted;
    }
    result.accepted_tokens[static_cast<std::size_t>(request)] = accepted;
    result.next_tokens[static_cast<std::size_t>(request)] = accepted == 0
        ? target_first_tokens[static_cast<std::size_t>(request)]
        : target_predictions[static_cast<std::size_t>(row_start + accepted - 1)];
  }

  std::vector<int> hidden_rows;
  std::vector<int> hidden_slots;
  for (int request = 0; request < requests; ++request) {
    const int accepted = result.accepted_tokens[static_cast<std::size_t>(request)];
    if (accepted == 0) continue;
    hidden_rows.push_back(request * depth + accepted - 1);
    hidden_slots.push_back(slots[static_cast<std::size_t>(request)]);
  }
  if (!hidden_rows.empty()) {
    check(cudaMemcpy(state.device_positions.get(), hidden_rows.data(),
                     hidden_rows.size() * sizeof(int), cudaMemcpyHostToDevice),
          "copy accepted hidden rows");
    check(cudaMemcpy(state.device_slots.get(), hidden_slots.data(),
                     hidden_slots.size() * sizeof(int), cudaMemcpyHostToDevice),
          "copy accepted hidden slots");
    gather_rows_bf16(state.final_hidden.get(),
                     static_cast<const int*>(state.device_positions.get()), state.hidden_a.get(),
                     static_cast<int>(hidden_rows.size()), state.hidden, nullptr);
    scatter_rows_bf16(state.hidden_a.get(), static_cast<const int*>(state.device_slots.get()),
                      state.target_hidden_slots.get(), static_cast<int>(hidden_rows.size()),
                      state.hidden, nullptr);
  }

  check(cudaMemcpy(state.device_positions.get(), positions.data(),
                   positions.size() * sizeof(int), cudaMemcpyHostToDevice),
        "restore speculative positions for rollback");
  check(cudaMemcpy(state.device_slots.get(), result.accepted_tokens.data(),
                   result.accepted_tokens.size() * sizeof(int), cudaMemcpyHostToDevice),
        "copy speculative accepted lengths");
  for (std::size_t layer = 0; layer < state.config.layers.size(); ++layer) {
    if (state.config.layers[layer].attention != AttentionKind::sliding) continue;
    for (int request = 0; request < requests; ++request) {
      const int slot = slots[static_cast<std::size_t>(request)];
      key_caches[static_cast<std::size_t>(request)] = state.slot_key_cache(layer, slot);
      value_caches[static_cast<std::size_t>(request)] = state.slot_value_cache(layer, slot);
    }
    std::vector<void*> pointers;
    pointers.reserve(static_cast<std::size_t>(2 * requests));
    pointers.insert(pointers.end(), key_caches.begin(), key_caches.end());
    pointers.insert(pointers.end(), value_caches.begin(), value_caches.end());
    check(cudaMemcpy(state.device_cache_pointers.get(), pointers.data(),
                     pointers.size() * sizeof(void*), cudaMemcpyHostToDevice),
          "copy speculative cache pointers for restore");
    auto** pointer_base = static_cast<void**>(state.device_cache_pointers.get());
    restore_kv_ring_suffixes_bf16(
        state.speculative_key_backup(layer), state.speculative_value_backup(layer), pointer_base,
        pointer_base + requests, static_cast<const int*>(state.device_positions.get()),
        static_cast<const int*>(state.device_slots.get()), requests,
        static_cast<int>(state.config.layers[layer].kv_heads), depth,
        static_cast<int>(state.config.layers[layer].head_dimension),
        state.caches[layer].capacity, nullptr);
  }
  check(cudaDeviceSynchronize(), "synchronize speculative verification");
  for (int request = 0; request < requests; ++request) {
    state.slot_positions[static_cast<std::size_t>(slots[static_cast<std::size_t>(request)])] +=
        result.accepted_tokens[static_cast<std::size_t>(request)];
  }
  return result;
}

std::vector<std::vector<int>> Gemma4BatchModelRunner::draft_four(
    const std::vector<int>& last_tokens, const std::vector<int>& slots,
    const std::vector<int>& forced_first_tokens, int depth) {
  auto& state = *implementation_;
  if (!state.assistant || last_tokens.size() != slots.size() || last_tokens.empty()) {
    throw std::runtime_error("assistant is not configured or draft batch is invalid");
  }
  std::vector<int> context_positions;
  context_positions.reserve(slots.size());
  for (const int slot : slots) {
    if (slot < 0 || slot >= state.batch_size ||
        state.slot_positions[static_cast<std::size_t>(slot)] <= 0) {
      throw std::runtime_error("assistant slot is empty or invalid");
    }
    context_positions.push_back(state.slot_positions[static_cast<std::size_t>(slot)] - 1);
  }
  const std::size_t sliding = static_cast<std::size_t>(state.shared_sliding_layer);
  const std::size_t global = static_cast<std::size_t>(state.shared_global_layer);
  return state.assistant->draft_four(
      state.weights.at("token_embedding"), state.target_hidden_slots.get(), last_tokens,
      context_positions, slots, forced_first_tokens, state.batch_size, depth,
      state.key_cache(sliding),
      state.value_cache(sliding), state.caches[sliding].capacity, state.key_cache(global),
      state.value_cache(global), state.caches[global].capacity);
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
bool Gemma4BatchModelRunner::has_assistant() const {
  return implementation_->assistant != nullptr;
}
int Gemma4BatchModelRunner::position() const { return implementation_->current_position; }
int Gemma4BatchModelRunner::slot_position(int slot) const {
  if (slot < 0 || slot >= implementation_->batch_size) throw std::runtime_error("invalid cache slot");
  return implementation_->slot_positions[static_cast<std::size_t>(slot)];
}

}  // namespace gradiated::engine
