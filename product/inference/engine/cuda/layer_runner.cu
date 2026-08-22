#include "gradiated/engine/layer_runner.h"

#include "gradiated/engine/cuda_ops.h"
#include "gradiated/engine/device_weights.h"
#include "gradiated/engine/gemm_attention.h"
#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/linear.h"
#include "gradiated/engine/prefill_attention.h"
#include "gradiated/engine/prefill_gemm_attention.h"
#include "gradiated/engine/qkv.h"

#include <cuda_runtime.h>

#include <algorithm>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>

namespace gradiated::engine {
namespace {

void check(cudaError_t result, const char* operation) {
  if (result != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(result));
  }
}

class Allocation {
 public:
  explicit Allocation(std::uint64_t bytes) { check(cudaMalloc(&pointer_, bytes), "allocate layer workspace"); }
  ~Allocation() { cudaFree(pointer_); }
  void* get() { return pointer_; }

 private:
  void* pointer_{nullptr};
};

}  // namespace

struct Gemma4LayerRunner::Implementation {
  const Gemma4Config& config;
  const DeviceWeightArena& weights;
  int maximum_tokens;
  int maximum_context;
  int maximum_batch;
  int hidden;
  int intermediate;
  float epsilon;
  Bf16Linear linear;
  Gemma4QkvPostprocessor qkv_postprocessor;
  GemmGroupedDecodeAttention attention;
  CudnnPrefillAttention sliding_prefill_attention;
  GemmCausalPrefillAttention global_prefill_attention;
  Allocation normalized;
  Allocation packed_qkv;
  Allocation queries;
  Allocation queries_head_major;
  Allocation key_cache;
  Allocation value_cache;
  Allocation attention_output;
  Allocation projected_attention;
  Allocation first_residual;
  Allocation pre_mlp;
  Allocation gate_up;
  Allocation activated;
  Allocation down;

  Implementation(const Gemma4Config& model_config, const DeviceWeightArena& device_weights,
                 int max_tokens, int max_context, int max_batch)
      : config(model_config),
        weights(device_weights),
        maximum_tokens(max_tokens),
        maximum_context(max_context),
        maximum_batch(max_batch),
        hidden(static_cast<int>(model_config.hidden_size)),
        intermediate(static_cast<int>(model_config.intermediate_size)),
        epsilon(static_cast<float>(model_config.rms_norm_epsilon)),
        linear(),
        qkv_postprocessor(std::max(max_tokens, max_context)),
        attention(max_batch, 16, 8, std::max(max_tokens, max_context)),
        sliding_prefill_attention(),
        global_prefill_attention(max_tokens, 32),
        normalized(2ULL * std::max(max_tokens, max_batch) * hidden),
        packed_qkv(2ULL * std::max(max_tokens, max_batch) * 18432),
        queries(2ULL * std::max(max_tokens, max_batch) * 16384),
        queries_head_major(2ULL * std::max(max_tokens, max_batch) * 16384),
        key_cache(2ULL * 4096 * max_tokens),
        value_cache(2ULL * 4096 * max_tokens),
        attention_output(2ULL * std::max(max_tokens, max_batch) * 16384),
        projected_attention(2ULL * std::max(max_tokens, max_batch) * hidden),
        first_residual(2ULL * std::max(max_tokens, max_batch) * hidden),
        pre_mlp(2ULL * std::max(max_tokens, max_batch) * hidden),
        gate_up(4ULL * std::max(max_tokens, max_batch) * intermediate),
        activated(2ULL * std::max(max_tokens, max_batch) * intermediate),
        down(2ULL * std::max(max_tokens, max_batch) * hidden) {
    if (max_tokens <= 0 || max_context <= 0 || max_batch <= 0) {
      throw std::runtime_error("invalid layer runner shape");
    }
  }

  void project(int selected_layer, const void* residual, const void* attention_states,
               void* output, int rows, cudaStream_t stream) {
    const auto& layer = config.layers.at(static_cast<std::size_t>(selected_layer));
    const int query_width = static_cast<int>(layer.query_width());
    const std::string prefix = "layer." + std::to_string(selected_layer) + ".";
    const auto weight = [&](const char* suffix) { return weights.at(prefix + suffix); };
    linear.run(attention_states, weight("o"), projected_attention.get(),
               rows, query_width, hidden, stream);
    rms_norm_add_bf16(projected_attention.get(), weight("post_attention_norm"), residual,
                      first_residual.get(), rows, hidden, epsilon, stream);
    rms_norm_bf16(first_residual.get(), weight("pre_mlp_norm"), pre_mlp.get(),
                  rows, hidden, epsilon, stream);
    linear.run(pre_mlp.get(), weight("gate_up"), gate_up.get(), rows, hidden, 2 * intermediate, stream);
    gelu_tanh_gate_rows_bf16(gate_up.get(), activated.get(), rows, intermediate, stream);
    linear.run(activated.get(), weight("down"), down.get(), rows, intermediate, hidden, stream);
    rms_norm_add_bf16(down.get(), weight("post_mlp_norm"), first_residual.get(), output,
                      rows, hidden, epsilon, stream);
    scale_bf16(output, weight("scalar"), static_cast<std::size_t>(rows) * hidden, stream);
  }

  void finish(int selected_layer, const void* residual, const void* query, void* output, int batch,
              const void* keys, const void* values, int context, int cache_capacity,
              cudaStream_t stream) {
    const auto& layer = config.layers.at(static_cast<std::size_t>(selected_layer));
    const int head_dimension = static_cast<int>(layer.head_dimension);
    const int kv_heads = static_cast<int>(layer.kv_heads);
    const int query_group = static_cast<int>(layer.query_heads / layer.kv_heads);
    attention.run(query, keys, values, attention_output.get(), batch, kv_heads, query_group,
                  context, head_dimension, stream, cache_capacity);
    project(selected_layer, residual, attention_output.get(), output, batch, stream);
  }
};

Gemma4LayerRunner::Gemma4LayerRunner(const Gemma4Config& config, const DeviceWeightArena& weights,
                                     int maximum_tokens, int maximum_context, int maximum_batch)
    : implementation_(std::make_unique<Implementation>(config, weights, maximum_tokens,
                                                        maximum_context, maximum_batch)) {}
Gemma4LayerRunner::~Gemma4LayerRunner() = default;

void Gemma4LayerRunner::run_last(int layer_index, const void* hidden_states, void* output,
                                 int tokens, cudaStream_t stream) {
  auto& state = *implementation_;
  if (tokens <= 0 || tokens > state.maximum_tokens) throw std::runtime_error("layer token count exceeds workspace");
  const auto& layer = state.config.layers.at(static_cast<std::size_t>(layer_index));
  const int query_heads = static_cast<int>(layer.query_heads);
  const int kv_heads = static_cast<int>(layer.kv_heads);
  const int head_dimension = static_cast<int>(layer.head_dimension);
  const int query_width = static_cast<int>(layer.query_width());
  const int packed_width = query_width + static_cast<int>(layer.kv_width()) * (layer.key_equals_value ? 1 : 2);
  const std::string prefix = "layer." + std::to_string(layer_index) + ".";
  const auto weight = [&](const char* suffix) { return state.weights.at(prefix + suffix); };
  rms_norm_bf16(hidden_states, weight("input_norm"), state.normalized.get(), tokens, state.hidden,
                state.epsilon, stream);
  state.linear.run(state.normalized.get(), weight("qkv"), state.packed_qkv.get(), tokens,
                   state.hidden, packed_width, stream);
  state.qkv_postprocessor.run(state.packed_qkv.get(), weight("q_norm"), weight("k_norm"),
      state.queries.get(), state.key_cache.get(), state.value_cache.get(), tokens, query_heads,
      kv_heads, head_dimension, layer.key_equals_value, 0, tokens, state.epsilon, stream);
  const auto* last_query = static_cast<const unsigned char*>(state.queries.get()) +
                           2ULL * (tokens - 1) * query_width;
  const auto* last_hidden = static_cast<const unsigned char*>(hidden_states) +
                            2ULL * (tokens - 1) * state.hidden;
  state.finish(layer_index, last_hidden, last_query, output, 1, state.key_cache.get(), state.value_cache.get(),
               tokens, tokens, stream);
}

void Gemma4LayerRunner::run_decode(int layer_index, const void* hidden_state, void* output,
                                   int position, void* key_cache, void* value_cache,
                                   int cache_capacity, cudaStream_t stream) {
  auto& state = *implementation_;
  if (position < 0 || position >= state.maximum_context || cache_capacity > state.maximum_context) {
    throw std::runtime_error("invalid decode position");
  }
  const auto& layer = state.config.layers.at(static_cast<std::size_t>(layer_index));
  const int query_heads = static_cast<int>(layer.query_heads);
  const int kv_heads = static_cast<int>(layer.kv_heads);
  const int head_dimension = static_cast<int>(layer.head_dimension);
  const int query_width = static_cast<int>(layer.query_width());
  const int packed_width = query_width + static_cast<int>(layer.kv_width()) * (layer.key_equals_value ? 1 : 2);
  const std::string prefix = "layer." + std::to_string(layer_index) + ".";
  const auto weight = [&](const char* suffix) { return state.weights.at(prefix + suffix); };
  rms_norm_bf16(hidden_state, weight("input_norm"), state.normalized.get(), 1, state.hidden,
                state.epsilon, stream);
  state.linear.run(state.normalized.get(), weight("qkv"), state.packed_qkv.get(),
                   1, state.hidden, packed_width, stream);
  state.qkv_postprocessor.run_decode_batch(state.packed_qkv.get(), weight("q_norm"), weight("k_norm"),
      state.queries.get(), key_cache, value_cache, 1, query_heads, kv_heads, head_dimension,
      layer.key_equals_value, position, cache_capacity, state.epsilon, stream);
  state.finish(layer_index, hidden_state, state.queries.get(), output, 1, key_cache, value_cache,
               std::min(position + 1, cache_capacity), cache_capacity, stream);
}

void Gemma4LayerRunner::run_decode_batch(int layer_index, const void* hidden_states, void* output,
                                         int batch, int position, void* key_cache, void* value_cache,
                                         int cache_capacity, cudaStream_t stream) {
  auto& state = *implementation_;
  if (batch <= 0 || batch > state.maximum_batch || position < 0 || position >= state.maximum_context ||
      cache_capacity > state.maximum_context) {
    throw std::runtime_error("invalid batched decode shape");
  }
  const auto& layer = state.config.layers.at(static_cast<std::size_t>(layer_index));
  const int query_heads = static_cast<int>(layer.query_heads);
  const int kv_heads = static_cast<int>(layer.kv_heads);
  const int head_dimension = static_cast<int>(layer.head_dimension);
  const int query_width = static_cast<int>(layer.query_width());
  const int packed_width = query_width + static_cast<int>(layer.kv_width()) * (layer.key_equals_value ? 1 : 2);
  const std::string prefix = "layer." + std::to_string(layer_index) + ".";
  const auto weight = [&](const char* suffix) { return state.weights.at(prefix + suffix); };
  rms_norm_bf16(hidden_states, weight("input_norm"), state.normalized.get(), batch, state.hidden,
                state.epsilon, stream);
  state.linear.run(state.normalized.get(), weight("qkv"), state.packed_qkv.get(),
                   batch, state.hidden, packed_width, stream);
  state.qkv_postprocessor.run_decode_batch(state.packed_qkv.get(), weight("q_norm"), weight("k_norm"),
      state.queries.get(), key_cache, value_cache, batch, query_heads, kv_heads, head_dimension,
      layer.key_equals_value, position, cache_capacity, state.epsilon, stream);
  state.finish(layer_index, hidden_states, state.queries.get(), output, batch, key_cache, value_cache,
               std::min(position + 1, cache_capacity), cache_capacity, stream);
}

void Gemma4LayerRunner::run_prefill(int layer_index, const void* hidden_states, void* output,
                                    int tokens, void* key_cache, void* value_cache,
                                    int cache_capacity, cudaStream_t stream) {
  auto& state = *implementation_;
  if (tokens <= 0 || tokens > state.maximum_tokens || key_cache == nullptr || value_cache == nullptr ||
      cache_capacity <= 0 || cache_capacity > state.maximum_context) {
    throw std::runtime_error("invalid prefill shape");
  }
  const auto& layer = state.config.layers.at(static_cast<std::size_t>(layer_index));
  const int query_heads = static_cast<int>(layer.query_heads);
  const int kv_heads = static_cast<int>(layer.kv_heads);
  const int head_dimension = static_cast<int>(layer.head_dimension);
  const int query_width = static_cast<int>(layer.query_width());
  const int packed_width = query_width + static_cast<int>(layer.kv_width()) *
      (layer.key_equals_value ? 1 : 2);
  const std::string prefix = "layer." + std::to_string(layer_index) + ".";
  const auto weight = [&](const char* suffix) { return state.weights.at(prefix + suffix); };
  rms_norm_bf16(hidden_states, weight("input_norm"), state.normalized.get(), tokens, state.hidden,
                state.epsilon, stream);
  state.linear.run(state.normalized.get(), weight("qkv"), state.packed_qkv.get(), tokens,
                   state.hidden, packed_width, stream);
  state.qkv_postprocessor.run(state.packed_qkv.get(), weight("q_norm"), weight("k_norm"),
      state.queries.get(), state.key_cache.get(), state.value_cache.get(), tokens, query_heads,
      kv_heads, head_dimension, layer.key_equals_value, 0, tokens, state.epsilon, stream);
  copy_kv_to_cache_bf16(state.key_cache.get(), key_cache, kv_heads, tokens, head_dimension,
                        cache_capacity, 0, stream);
  copy_kv_to_cache_bf16(state.value_cache.get(), value_cache, kv_heads, tokens, head_dimension,
                        cache_capacity, 0, stream);

  const void* attention_states = state.attention_output.get();
  if (layer.attention == AttentionKind::sliding) {
    state.sliding_prefill_attention.run(
        state.queries.get(), state.key_cache.get(), state.value_cache.get(),
        state.attention_output.get(), 1, query_heads, kv_heads, tokens, tokens, tokens,
        head_dimension, static_cast<int>(state.config.sliding_window), stream);
  } else {
    token_to_head_bf16(state.queries.get(), state.queries_head_major.get(), tokens,
                       query_heads, head_dimension, stream);
    state.global_prefill_attention.run(
        state.queries_head_major.get(), state.key_cache.get(), state.value_cache.get(),
        state.attention_output.get(), query_heads, kv_heads, tokens, tokens, tokens, 0,
        head_dimension, stream);
    head_to_token_bf16(state.attention_output.get(), state.queries.get(), tokens,
                       query_heads, head_dimension, stream);
    attention_states = state.queries.get();
  }
  state.project(layer_index, hidden_states, attention_states, output, tokens, stream);
}

void Gemma4LayerRunner::run_prefill_chunk(int layer_index, const void* hidden_states, void* output,
                                          int tokens, int position_start, void* key_cache,
                                          void* value_cache, int cache_capacity,
                                          cudaStream_t stream) {
  auto& state = *implementation_;
  if (tokens <= 0 || position_start < 0 || position_start + tokens > state.maximum_context ||
      tokens > state.maximum_tokens || key_cache == nullptr || value_cache == nullptr ||
      cache_capacity <= 0 || cache_capacity > state.maximum_context) {
    throw std::runtime_error("invalid prefill chunk shape");
  }
  const auto& layer = state.config.layers.at(static_cast<std::size_t>(layer_index));
  const int query_heads = static_cast<int>(layer.query_heads);
  const int kv_heads = static_cast<int>(layer.kv_heads);
  const int head_dimension = static_cast<int>(layer.head_dimension);
  const int query_width = static_cast<int>(layer.query_width());
  const int packed_width = query_width + static_cast<int>(layer.kv_width()) *
      (layer.key_equals_value ? 1 : 2);
  const std::string prefix = "layer." + std::to_string(layer_index) + ".";
  const auto weight = [&](const char* suffix) { return state.weights.at(prefix + suffix); };
  rms_norm_bf16(hidden_states, weight("input_norm"), state.normalized.get(), tokens, state.hidden,
                state.epsilon, stream);
  state.linear.run(state.normalized.get(), weight("qkv"), state.packed_qkv.get(), tokens,
                   state.hidden, packed_width, stream);

  const void* attention_states = state.attention_output.get();
  if (layer.attention == AttentionKind::sliding) {
    const int prior = std::min(position_start,
        static_cast<int>(state.config.sliding_window) - 1);
    const int staging_tokens = prior + tokens;
    if (staging_tokens > state.maximum_tokens) {
      throw std::runtime_error("sliding prefill staging exceeds workspace");
    }
    gather_kv_ring_bf16(key_cache, state.key_cache.get(), kv_heads, prior, head_dimension,
                        cache_capacity, staging_tokens, position_start - prior, stream);
    gather_kv_ring_bf16(value_cache, state.value_cache.get(), kv_heads, prior, head_dimension,
                        cache_capacity, staging_tokens, position_start - prior, stream);
    state.qkv_postprocessor.run_positioned(
        state.packed_qkv.get(), weight("q_norm"), weight("k_norm"), state.queries.get(),
        state.key_cache.get(), state.value_cache.get(), tokens, query_heads, kv_heads,
        head_dimension, layer.key_equals_value, position_start, prior, staging_tokens,
        state.epsilon, stream);
    state.sliding_prefill_attention.run(
        state.queries.get(), state.key_cache.get(), state.value_cache.get(),
        state.attention_output.get(), 1, query_heads, kv_heads, tokens, staging_tokens,
        staging_tokens, head_dimension, static_cast<int>(state.config.sliding_window), stream);
    copy_kv_span_to_ring_bf16(state.key_cache.get(), key_cache, kv_heads, tokens, head_dimension,
                              staging_tokens, prior, cache_capacity, position_start, stream);
    copy_kv_span_to_ring_bf16(state.value_cache.get(), value_cache, kv_heads, tokens, head_dimension,
                              staging_tokens, prior, cache_capacity, position_start, stream);
  } else {
    state.qkv_postprocessor.run_positioned(
        state.packed_qkv.get(), weight("q_norm"), weight("k_norm"), state.queries.get(),
        key_cache, value_cache, tokens, query_heads, kv_heads, head_dimension,
        layer.key_equals_value, position_start, position_start, cache_capacity,
        state.epsilon, stream);
    token_to_head_bf16(state.queries.get(), state.queries_head_major.get(), tokens,
                       query_heads, head_dimension, stream);
    state.global_prefill_attention.run(
        state.queries_head_major.get(), key_cache, value_cache, state.attention_output.get(),
        query_heads, kv_heads, tokens, position_start + tokens, cache_capacity,
        position_start, head_dimension, stream);
    head_to_token_bf16(state.attention_output.get(), state.queries.get(), tokens,
                       query_heads, head_dimension, stream);
    attention_states = state.queries.get();
  }
  state.project(layer_index, hidden_states, attention_states, output, tokens, stream);
}

}  // namespace gradiated::engine
