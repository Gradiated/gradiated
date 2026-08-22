#include "gradiated/engine/layer_runner.h"

#include "gradiated/engine/cuda_ops.h"
#include "gradiated/engine/device_weights.h"
#include "gradiated/engine/gemm_attention.h"
#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/linear.h"
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
  int hidden;
  int intermediate;
  float epsilon;
  Bf16Linear linear;
  Gemma4QkvPostprocessor qkv_postprocessor;
  GemmGroupedDecodeAttention attention;
  Allocation normalized;
  Allocation packed_qkv;
  Allocation queries;
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
                 int max_tokens, int max_context)
      : config(model_config),
        weights(device_weights),
        maximum_tokens(max_tokens),
        maximum_context(max_context),
        hidden(static_cast<int>(model_config.hidden_size)),
        intermediate(static_cast<int>(model_config.intermediate_size)),
        epsilon(static_cast<float>(model_config.rms_norm_epsilon)),
        linear(),
        qkv_postprocessor(std::max(max_tokens, max_context)),
        attention(1, 16, 8, std::max(max_tokens, max_context)),
        normalized(2ULL * max_tokens * hidden),
        packed_qkv(2ULL * max_tokens * 18432),
        queries(2ULL * max_tokens * 16384),
        key_cache(2ULL * 4096 * max_tokens),
        value_cache(2ULL * 4096 * max_tokens),
        attention_output(2ULL * 16384),
        projected_attention(2ULL * hidden),
        first_residual(2ULL * hidden),
        pre_mlp(2ULL * hidden),
        gate_up(4ULL * intermediate),
        activated(2ULL * intermediate),
        down(2ULL * hidden) {
    if (max_tokens <= 0 || max_context <= 0) {
      throw std::runtime_error("invalid layer runner shape");
    }
  }

  void finish(int selected_layer, const void* residual, const void* query, void* output,
              const void* keys, const void* values, int context, int cache_capacity,
              cudaStream_t stream) {
    const auto& layer = config.layers.at(static_cast<std::size_t>(selected_layer));
    const int query_width = static_cast<int>(layer.query_width());
    const int head_dimension = static_cast<int>(layer.head_dimension);
    const int kv_heads = static_cast<int>(layer.kv_heads);
    const int query_group = static_cast<int>(layer.query_heads / layer.kv_heads);
    const std::string prefix = "layer." + std::to_string(selected_layer) + ".";
    const auto weight = [&](const char* suffix) { return weights.at(prefix + suffix); };
    attention.run(query, keys, values, attention_output.get(), 1, kv_heads, query_group,
                  context, head_dimension, stream, cache_capacity);
    linear.run(attention_output.get(), weight("o"), projected_attention.get(),
               1, query_width, hidden, stream);
    rms_norm_add_bf16(projected_attention.get(), weight("post_attention_norm"), residual,
                      first_residual.get(), 1, hidden, epsilon, stream);
    rms_norm_bf16(first_residual.get(), weight("pre_mlp_norm"), pre_mlp.get(),
                  1, hidden, epsilon, stream);
    linear.run(pre_mlp.get(), weight("gate_up"), gate_up.get(), 1, hidden, 2 * intermediate, stream);
    const auto* up = static_cast<const unsigned char*>(gate_up.get()) + 2ULL * intermediate;
    gelu_tanh_gate_bf16(gate_up.get(), up, activated.get(), intermediate, stream);
    linear.run(activated.get(), weight("down"), down.get(), 1, intermediate, hidden, stream);
    rms_norm_add_bf16(down.get(), weight("post_mlp_norm"), first_residual.get(), output,
                      1, hidden, epsilon, stream);
    scale_bf16(output, weight("scalar"), hidden, stream);
  }
};

Gemma4LayerRunner::Gemma4LayerRunner(const Gemma4Config& config, const DeviceWeightArena& weights,
                                     int maximum_tokens, int maximum_context)
    : implementation_(std::make_unique<Implementation>(config, weights, maximum_tokens, maximum_context)) {}
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
  state.finish(layer_index, last_hidden, last_query, output, state.key_cache.get(), state.value_cache.get(),
               tokens, tokens, stream);
}

void Gemma4LayerRunner::run_decode(int layer_index, const void* hidden_state, void* output,
                                   int position, void* key_cache, void* value_cache,
                                   int cache_capacity, cudaStream_t stream) {
  auto& state = *implementation_;
  if (position < 0 || position >= cache_capacity || cache_capacity > state.maximum_context) {
    throw std::runtime_error("invalid decode position");
  }
  const auto& layer = state.config.layers.at(static_cast<std::size_t>(layer_index));
  if (layer.attention == AttentionKind::sliding && position >= static_cast<int>(state.config.sliding_window)) {
    throw std::runtime_error("sliding KV ring is not implemented yet");
  }
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
  state.qkv_postprocessor.run(state.packed_qkv.get(), weight("q_norm"), weight("k_norm"),
      state.queries.get(), key_cache, value_cache, 1, query_heads, kv_heads, head_dimension,
      layer.key_equals_value, position, cache_capacity, state.epsilon, stream);
  state.finish(layer_index, hidden_state, state.queries.get(), output, key_cache, value_cache,
               position + 1, cache_capacity, stream);
}

}  // namespace gradiated::engine
