#include "gradiated/engine/layer_runner.h"

#include "gradiated/engine/attention.h"
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
#include <charconv>
#include <cstdlib>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

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

std::vector<bool> bf16_layer_selection(const char* environment_name,
                                       std::size_t layer_count) {
  std::vector<bool> selected(layer_count, false);
  const char* configured = std::getenv(environment_name);
  if (configured == nullptr || *configured == '\0') return selected;

  const std::string_view specification(configured);
  std::size_t begin = 0;
  while (begin < specification.size()) {
    const std::size_t end = specification.find(',', begin);
    const std::string_view item = specification.substr(
        begin, end == std::string_view::npos ? specification.size() - begin : end - begin);
    if (item.empty()) {
      throw std::runtime_error(std::string(environment_name) +
                               " contains an empty layer index");
    }
    int layer = -1;
    const auto parsed = std::from_chars(item.data(), item.data() + item.size(), layer);
    if (parsed.ec != std::errc{} || parsed.ptr != item.data() + item.size() ||
        layer < 0 || static_cast<std::size_t>(layer) >= layer_count) {
      throw std::runtime_error(
          std::string(environment_name) + " contains an invalid layer index: " +
          std::string(item));
    }
    selected[static_cast<std::size_t>(layer)] = true;
    if (end == std::string_view::npos) break;
    begin = end + 1;
  }
  return selected;
}

}  // namespace

struct Gemma4LayerRunner::Implementation {
  const Gemma4Config& config;
  const DeviceWeightArena& weights;
  const Fp8WeightArena* fp8_weights;
  const std::vector<bool> bf16_layers;
  const std::vector<bool> bf16_attention_layers;
  const std::vector<bool> bf16_mlp_layers;
  const std::vector<bool> bf16_qkv_layers;
  const std::vector<bool> bf16_o_layers;
  const std::vector<bool> bf16_gate_up_layers;
  const std::vector<bool> bf16_down_layers;
  int maximum_tokens;
  int maximum_context;
  int maximum_batch;
  int maximum_fp8_rows;
  int hidden;
  int intermediate;
  float epsilon;
  Bf16Linear linear;
  Fp8Linear fp8_linear;
  Gemma4QkvPostprocessor qkv_postprocessor;
  GemmGroupedDecodeAttention attention;
  CudnnPrefillAttention sliding_prefill_attention;
  GemmCausalPrefillAttention global_prefill_attention;
  Allocation normalized;
  Allocation packed_qkv;
  Allocation queries;
  Allocation fp8_queries;
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
  Allocation fp8_input;
  Allocation fp8_input_scales;
  Allocation prefill_positions;
  Allocation prefill_cache_pointers;

  Implementation(const Gemma4Config& model_config, const DeviceWeightArena& device_weights,
                 int max_tokens, int max_context, int max_batch,
                 const Fp8WeightArena* decode_weights)
      : config(model_config),
        weights(device_weights),
        fp8_weights(decode_weights),
        bf16_layers(bf16_layer_selection(
            "GRADIATED_FP8_BF16_LAYERS", model_config.layers.size())),
        bf16_attention_layers(bf16_layer_selection(
            "GRADIATED_FP8_BF16_ATTENTION_LAYERS", model_config.layers.size())),
        bf16_mlp_layers(bf16_layer_selection(
            "GRADIATED_FP8_BF16_MLP_LAYERS", model_config.layers.size())),
        bf16_qkv_layers(bf16_layer_selection(
            "GRADIATED_FP8_BF16_QKV_LAYERS", model_config.layers.size())),
        bf16_o_layers(bf16_layer_selection(
            "GRADIATED_FP8_BF16_O_LAYERS", model_config.layers.size())),
        bf16_gate_up_layers(bf16_layer_selection(
            "GRADIATED_FP8_BF16_GATE_UP_LAYERS", model_config.layers.size())),
        bf16_down_layers(bf16_layer_selection(
            "GRADIATED_FP8_BF16_DOWN_LAYERS", model_config.layers.size())),
        maximum_tokens(max_tokens),
        maximum_context(max_context),
        maximum_batch(max_batch),
        maximum_fp8_rows(std::max(max_tokens, 8 * max_batch)),
        hidden(static_cast<int>(model_config.hidden_size)),
        intermediate(static_cast<int>(model_config.intermediate_size)),
        epsilon(static_cast<float>(model_config.rms_norm_epsilon)),
        linear(),
        fp8_linear(decode_weights == nullptr ? Fp8Scaling::tensor : decode_weights->scaling()),
        qkv_postprocessor(std::max(max_tokens, max_context)),
        attention(max_batch, 16, 8, std::max(max_tokens, max_context)),
        sliding_prefill_attention(),
        global_prefill_attention(max_tokens, 32, max_batch),
        normalized(2ULL * std::max(max_tokens, max_batch) * hidden),
        packed_qkv(2ULL * std::max(max_tokens, max_batch) * 18432),
        queries(2ULL * std::max(max_tokens, max_batch) * 16384),
        fp8_queries(static_cast<std::uint64_t>(max_batch) * 16384),
        queries_head_major(2ULL * std::max(max_tokens, max_batch) * 16384),
        // Also serves as the batched global-attention output arena, whose query width (8192)
        // exceeds the global K/V width (4096).
        key_cache(2ULL * std::max<std::uint64_t>(
            8192ULL * max_tokens,
            4096ULL * (max_tokens + static_cast<std::uint64_t>(max_batch) *
                (model_config.sliding_window - 1ULL)))),
        value_cache(2ULL * std::max<std::uint64_t>(
            4096ULL * max_tokens,
            4096ULL * (max_tokens + static_cast<std::uint64_t>(max_batch) *
                (model_config.sliding_window - 1ULL)))),
        attention_output(2ULL * std::max(max_tokens, max_batch) * 16384),
        projected_attention(2ULL * std::max(max_tokens, max_batch) * hidden),
        first_residual(2ULL * std::max(max_tokens, max_batch) * hidden),
        pre_mlp(2ULL * std::max(max_tokens, max_batch) * hidden),
        gate_up(4ULL * std::max(max_tokens, max_batch) * intermediate),
        activated(2ULL * std::max(max_tokens, max_batch) * intermediate),
        down(2ULL * std::max(max_tokens, max_batch) * hidden),
        fp8_input(static_cast<std::uint64_t>(std::max(max_tokens, 8 * max_batch)) *
                  std::max({hidden, intermediate, 18432})),
        fp8_input_scales(sizeof(float) *
                         static_cast<std::uint64_t>(std::max(max_tokens, 8 * max_batch)) *
                         ((std::max({hidden, intermediate, 18432}) + 127) / 128)),
        prefill_positions(sizeof(int) * static_cast<std::uint64_t>(max_batch)),
        prefill_cache_pointers(2ULL * sizeof(void*) * static_cast<std::uint64_t>(max_batch)) {
    if (max_tokens <= 0 || max_context <= 0 || max_batch <= 0) {
      throw std::runtime_error("invalid layer runner shape");
    }
  }

  bool uses_fp8_qkv(int layer_index) const {
    return fp8_weights != nullptr &&
           !bf16_layers.at(static_cast<std::size_t>(layer_index)) &&
           !bf16_attention_layers.at(static_cast<std::size_t>(layer_index)) &&
           !bf16_qkv_layers.at(static_cast<std::size_t>(layer_index));
  }

  bool uses_fp8_o(int layer_index) const {
    return fp8_weights != nullptr &&
           !bf16_layers.at(static_cast<std::size_t>(layer_index)) &&
           !bf16_attention_layers.at(static_cast<std::size_t>(layer_index)) &&
           !bf16_o_layers.at(static_cast<std::size_t>(layer_index));
  }

  bool uses_fp8_gate_up(int layer_index) const {
    return fp8_weights != nullptr &&
           !bf16_layers.at(static_cast<std::size_t>(layer_index)) &&
           !bf16_mlp_layers.at(static_cast<std::size_t>(layer_index)) &&
           !bf16_gate_up_layers.at(static_cast<std::size_t>(layer_index));
  }

  bool uses_fp8_down(int layer_index) const {
    return fp8_weights != nullptr &&
           !bf16_layers.at(static_cast<std::size_t>(layer_index)) &&
           !bf16_mlp_layers.at(static_cast<std::size_t>(layer_index)) &&
           !bf16_down_layers.at(static_cast<std::size_t>(layer_index));
  }

  void run_decode_linear(bool use_fp8, const void* input, std::string_view weight_name,
                         void* output,
                         int rows, int input_width, int output_width, cudaStream_t stream) {
    if (!use_fp8) {
      linear.run(input, weights.at(weight_name), output, rows, input_width, output_width, stream);
      return;
    }
    auto* scales = static_cast<float*>(fp8_input_scales.get());
    if (fp8_weights->scaling() == Fp8Scaling::tensor) {
      quantize_bf16_to_fp8_e4m3(input, fp8_input.get(), scales,
                                static_cast<std::size_t>(rows) * input_width, stream);
    } else if (fp8_weights->scaling() == Fp8Scaling::channel) {
      quantize_bf16_rows_to_fp8_e4m3(input, fp8_input.get(), scales, rows, input_width, stream);
    } else {
      quantize_bf16_activation_to_fp8_block_128(
          input, fp8_input.get(), scales, rows, input_width, stream);
    }
    fp8_linear.run(fp8_input.get(), scales, fp8_weights->at(weight_name),
                   fp8_weights->scale(weight_name), output, rows, input_width, output_width, stream);
  }

  void project(int selected_layer, const void* residual, const void* attention_states,
               void* output, int rows, bool fp8_decode, cudaStream_t stream) {
    const auto& layer = config.layers.at(static_cast<std::size_t>(selected_layer));
    const int query_width = static_cast<int>(layer.query_width());
    const std::string prefix = "layer." + std::to_string(selected_layer) + ".";
    const auto weight = [&](const char* suffix) { return weights.at(prefix + suffix); };
    const bool o_fp8 = fp8_decode && uses_fp8_o(selected_layer);
    const bool gate_up_fp8 = fp8_decode && uses_fp8_gate_up(selected_layer);
    const bool down_fp8 = fp8_decode && uses_fp8_down(selected_layer);
    if (o_fp8) {
      run_decode_linear(true, attention_states, prefix + "o",
                        projected_attention.get(), rows, query_width, hidden, stream);
    } else {
      linear.run(attention_states, weight("o"), projected_attention.get(),
                 rows, query_width, hidden, stream);
    }
    rms_norm_add_and_norm_bf16(projected_attention.get(), weight("post_attention_norm"), residual,
                               weight("pre_mlp_norm"), first_residual.get(), pre_mlp.get(),
                               rows, hidden, epsilon, stream);
    if (gate_up_fp8) {
      run_decode_linear(true, pre_mlp.get(), prefix + "gate_up", gate_up.get(),
                        rows, hidden, 2 * intermediate, stream);
    } else {
      linear.run(pre_mlp.get(), weight("gate_up"), gate_up.get(),
                 rows, hidden, 2 * intermediate, stream);
    }
    gelu_tanh_gate_rows_bf16(gate_up.get(), activated.get(), rows, intermediate, stream);
    if (down_fp8) {
      run_decode_linear(true, activated.get(), prefix + "down", down.get(),
                        rows, intermediate, hidden, stream);
    } else {
      linear.run(activated.get(), weight("down"), down.get(), rows, intermediate, hidden, stream);
    }
    rms_norm_add_scale_bf16(down.get(), weight("post_mlp_norm"), first_residual.get(),
                            weight("scalar"), output, rows, hidden, epsilon, stream);
  }

  void finish(int selected_layer, const void* residual, const void* query, void* output, int batch,
              const void* keys, const void* values, int context, int cache_capacity,
              bool fp8_decode, cudaStream_t stream) {
    const auto& layer = config.layers.at(static_cast<std::size_t>(selected_layer));
    const int head_dimension = static_cast<int>(layer.head_dimension);
    const int kv_heads = static_cast<int>(layer.kv_heads);
    const int query_group = static_cast<int>(layer.query_heads / layer.kv_heads);
    attention.run(query, keys, values, attention_output.get(), batch, kv_heads, query_group,
                  context, head_dimension, stream, cache_capacity);
    project(selected_layer, residual, attention_output.get(), output, batch, fp8_decode, stream);
  }

  void finish_ragged(int selected_layer, const void* residual, const void* query, void* output,
                     const int* positions, const int* slots, int batch, int maximum_slots,
                     int maximum_context_length, const void* keys, const void* values,
                     const void* fp8_keys, const void* fp8_values, int cache_capacity,
                     bool fp8_decode,
                     int contiguous_slot_start,
                     cudaStream_t stream) {
    const auto& layer = config.layers.at(static_cast<std::size_t>(selected_layer));
    const int head_dimension = static_cast<int>(layer.head_dimension);
    const int kv_heads = static_cast<int>(layer.kv_heads);
    const int query_group = static_cast<int>(layer.query_heads / layer.kv_heads);
    if (fp8_keys != nullptr && fp8_values != nullptr && contiguous_slot_start >= 0 &&
        layer.attention == AttentionKind::global) {
      attention.run_ragged_contiguous_fp8_kv(
          fp8_queries.get(), fp8_keys, fp8_values, attention_output.get(), positions, batch,
          kv_heads, query_group, maximum_context_length, head_dimension,
          contiguous_slot_start, stream, cache_capacity);
    } else if (fp8_keys != nullptr && contiguous_slot_start >= 0 &&
        layer.attention == AttentionKind::global) {
      attention.run_ragged_contiguous_fp8_keys(
          fp8_queries.get(), fp8_keys, values, attention_output.get(), positions, batch,
          kv_heads, query_group, maximum_context_length, head_dimension,
          contiguous_slot_start, stream, cache_capacity);
    } else if (contiguous_slot_start >= 0) {
      attention.run_ragged_contiguous(
          query, keys, values, attention_output.get(), positions, batch, kv_heads, query_group,
          maximum_context_length, head_dimension, contiguous_slot_start, stream, cache_capacity);
    } else {
      attention.run_ragged(query, keys, values, attention_output.get(), positions, slots, batch,
                           maximum_slots, kv_heads, query_group, maximum_context_length,
                           head_dimension, stream, cache_capacity);
    }
    project(selected_layer, residual, attention_output.get(), output, batch, fp8_decode, stream);
  }
};

Gemma4LayerRunner::Gemma4LayerRunner(const Gemma4Config& config, const DeviceWeightArena& weights,
                                     int maximum_tokens, int maximum_context, int maximum_batch,
                                     const Fp8WeightArena* fp8_weights)
    : implementation_(std::make_unique<Implementation>(config, weights, maximum_tokens,
                                                        maximum_context, maximum_batch,
                                                        fp8_weights)) {}
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
               tokens, tokens, false, stream);
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
  state.run_decode_linear(state.uses_fp8_qkv(layer_index), state.normalized.get(),
                          prefix + "qkv", state.packed_qkv.get(), 1, state.hidden,
                          packed_width, stream);
  state.qkv_postprocessor.run_decode_batch(state.packed_qkv.get(), weight("q_norm"), weight("k_norm"),
      state.queries.get(), key_cache, value_cache, 1, query_heads, kv_heads, head_dimension,
      layer.key_equals_value, position, cache_capacity, state.epsilon, stream);
  state.finish(layer_index, hidden_state, state.queries.get(), output, 1, key_cache, value_cache,
               std::min(position + 1, cache_capacity), cache_capacity, true, stream);
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
  state.run_decode_linear(state.uses_fp8_qkv(layer_index), state.normalized.get(),
                          prefix + "qkv", state.packed_qkv.get(), batch, state.hidden,
                          packed_width, stream);
  state.qkv_postprocessor.run_decode_batch(state.packed_qkv.get(), weight("q_norm"), weight("k_norm"),
      state.queries.get(), key_cache, value_cache, batch, query_heads, kv_heads, head_dimension,
      layer.key_equals_value, position, cache_capacity, state.epsilon, stream);
  state.finish(layer_index, hidden_states, state.queries.get(), output, batch, key_cache, value_cache,
               std::min(position + 1, cache_capacity), cache_capacity, true, stream);
}

void Gemma4LayerRunner::run_decode_ragged(
    int layer_index, const void* hidden_states, void* output, const int* positions,
    const int* slots, int batch, int maximum_slots, int maximum_context_length,
    void* key_cache, void* value_cache, void* fp8_key_cache, void* fp8_value_cache,
    int cache_capacity, int contiguous_slot_start, cudaStream_t stream) {
  auto& state = *implementation_;
  if (batch <= 0 || batch > state.maximum_batch || maximum_slots < batch ||
      maximum_context_length <= 0 || maximum_context_length > cache_capacity ||
      cache_capacity > state.maximum_context || positions == nullptr || slots == nullptr ||
      key_cache == nullptr || value_cache == nullptr) {
    throw std::runtime_error("invalid ragged decode shape");
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
  rms_norm_bf16(hidden_states, weight("input_norm"), state.normalized.get(), batch, state.hidden,
                state.epsilon, stream);
  state.run_decode_linear(state.uses_fp8_qkv(layer_index), state.normalized.get(),
                          prefix + "qkv", state.packed_qkv.get(), batch, state.hidden,
                          packed_width, stream);
  state.qkv_postprocessor.run_decode_ragged(
      state.packed_qkv.get(), weight("q_norm"), weight("k_norm"), state.queries.get(),
      key_cache, value_cache, positions, slots, batch, maximum_slots, query_heads, kv_heads,
      head_dimension, layer.key_equals_value, cache_capacity, state.epsilon, stream);
  const bool use_fp8_key_cache = fp8_key_cache != nullptr &&
                                 state.uses_fp8_qkv(layer_index);
  if (use_fp8_key_cache) {
    if (layer.attention != AttentionKind::global) {
      throw std::runtime_error("FP8 K cache supplied for a non-global layer");
    }
    quantize_global_decode_qk_fp8(
        state.queries.get(), key_cache, state.fp8_queries.get(), fp8_key_cache,
        positions, slots, batch, maximum_slots, query_heads, kv_heads,
        head_dimension, cache_capacity, stream);
    if (fp8_value_cache != nullptr) {
      quantize_grouped_global_decode_values_wgmma_fp8(
          value_cache, fp8_value_cache, positions, slots, batch, maximum_slots,
          kv_heads, cache_capacity, head_dimension, stream);
    }
  }
  state.finish_ragged(layer_index, hidden_states, state.queries.get(), output, positions, slots,
                      batch, maximum_slots, maximum_context_length, key_cache, value_cache,
                      use_fp8_key_cache ? fp8_key_cache : nullptr,
                      use_fp8_key_cache ? fp8_value_cache : nullptr, cache_capacity, true,
                      contiguous_slot_start, stream);
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
  state.project(layer_index, hidden_states, attention_states, output, tokens, false, stream);
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
  state.project(layer_index, hidden_states, attention_states, output, tokens, false, stream);
}

void Gemma4LayerRunner::run_prefill_chunks(
    int layer_index, const void* hidden_states, void* output,
    const std::vector<int>& token_counts, const std::vector<int>& position_starts,
    const std::vector<void*>& key_caches, const std::vector<void*>& value_caches,
    const std::vector<int>& cache_capacities, cudaStream_t stream,
    bool fp8_projections, const void* speculative_backup_keys,
    const void* speculative_backup_values, const int* prepared_positions,
    void* const* prepared_cache_pointers) {
  auto& state = *implementation_;
  const std::size_t requests = token_counts.size();
  if (requests == 0 || position_starts.size() != requests || key_caches.size() != requests ||
      value_caches.size() != requests || cache_capacities.size() != requests) {
    throw std::runtime_error("invalid batched prefill metadata");
  }
  int total_tokens = 0;
  for (std::size_t request = 0; request < requests; ++request) {
    const int tokens = token_counts[request];
    const int position = position_starts[request];
    const int capacity = cache_capacities[request];
    if (tokens <= 0 || position < 0 || position + tokens > state.maximum_context ||
        capacity <= 0 || capacity > state.maximum_context || key_caches[request] == nullptr ||
        value_caches[request] == nullptr) {
      throw std::runtime_error("invalid batched prefill request shape");
    }
    total_tokens += tokens;
  }
  if (total_tokens > state.maximum_tokens) {
    throw std::runtime_error("batched prefill exceeds projection workspace");
  }
  if (fp8_projections && (state.fp8_weights == nullptr ||
                          total_tokens > state.maximum_fp8_rows)) {
    throw std::runtime_error("FP8 prefill exceeds quantization workspace");
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
  const bool layer_fp8 = fp8_projections && state.uses_fp8_qkv(layer_index);
  rms_norm_bf16(hidden_states, weight("input_norm"), state.normalized.get(), total_tokens,
                state.hidden, state.epsilon, stream);
  if (layer_fp8) {
    state.run_decode_linear(true, state.normalized.get(), prefix + "qkv",
                            state.packed_qkv.get(), total_tokens, state.hidden,
                            packed_width, stream);
  } else {
    state.linear.run(state.normalized.get(), weight("qkv"), state.packed_qkv.get(),
                     total_tokens, state.hidden, packed_width, stream);
  }

  bool uniform_shape = true;
  const int uniform_tokens = token_counts.front();
  const int uniform_prior = std::min(
      position_starts.front(), static_cast<int>(state.config.sliding_window) - 1);
  const int uniform_capacity = cache_capacities.front();
  bool uniform_prior_shape = true;
  for (std::size_t request = 1; request < requests; ++request) {
    uniform_shape = uniform_shape && token_counts[request] == uniform_tokens &&
                    cache_capacities[request] == uniform_capacity;
    uniform_prior_shape = uniform_prior_shape &&
        std::min(position_starts[request],
                 static_cast<int>(state.config.sliding_window) - 1) == uniform_prior;
  }
  const bool speculative_sliding_gemm = fp8_projections && uniform_tokens <= 8;
  const bool uniform_sliding = layer.attention == AttentionKind::sliding &&
                               uniform_shape && uniform_prior_shape &&
                               ((speculative_sliding_gemm && requests >= 2) ||
                                (requests >= 8 && uniform_tokens >= 128));
  if (uniform_sliding) {
    const int staging_tokens = uniform_prior + uniform_tokens;
    if (staging_tokens > state.maximum_tokens) {
      throw std::runtime_error("uniform sliding prefill staging exceeds workspace");
    }
    std::vector<const void*> cache_pointers(2 * requests);
    for (std::size_t request = 0; request < requests; ++request) {
      cache_pointers[request] = key_caches[request];
      cache_pointers[requests + request] = value_caches[request];
    }
    const bool can_use_prepared_metadata = prepared_positions != nullptr &&
        prepared_cache_pointers != nullptr && speculative_sliding_gemm &&
        std::getenv("GRADIATED_DISABLE_RING_SPECULATION") == nullptr &&
        ((speculative_backup_keys != nullptr && speculative_backup_values != nullptr &&
          uniform_prior == uniform_capacity - 1) ||
         std::all_of(position_starts.begin(), position_starts.end(),
                     [&](int position) {
                       return position + uniform_tokens <= uniform_capacity;
                     }));
    if (!can_use_prepared_metadata) {
      check(cudaMemcpyAsync(state.prefill_positions.get(), position_starts.data(),
                            requests * sizeof(int), cudaMemcpyHostToDevice, stream),
            "copy uniform prefill positions");
      check(cudaMemcpyAsync(state.prefill_cache_pointers.get(), cache_pointers.data(),
                            cache_pointers.size() * sizeof(void*), cudaMemcpyHostToDevice, stream),
            "copy uniform prefill cache pointers");
    }
    const auto* device_positions = can_use_prepared_metadata
        ? prepared_positions : static_cast<const int*>(state.prefill_positions.get());
    auto* pointer_base = can_use_prepared_metadata
        ? prepared_cache_pointers : static_cast<void**>(state.prefill_cache_pointers.get());
    auto* device_key_caches = reinterpret_cast<const void* const*>(pointer_base);
    auto* device_value_caches = reinterpret_cast<const void* const*>(pointer_base + requests);
    const bool direct_wrapped_speculation = speculative_sliding_gemm &&
        speculative_backup_keys != nullptr && speculative_backup_values != nullptr &&
        uniform_prior == uniform_capacity - 1 &&
        std::getenv("GRADIATED_DISABLE_RING_SPECULATION") == nullptr;
    if (direct_wrapped_speculation) {
      state.qkv_postprocessor.run_prefill_uniform_direct(
          state.packed_qkv.get(), weight("q_norm"), weight("k_norm"), state.queries.get(),
          pointer_base, pointer_base + requests, device_positions,
          static_cast<int>(requests), uniform_tokens, query_heads, kv_heads, head_dimension,
          layer.key_equals_value, uniform_capacity, state.epsilon, stream);
      token_to_head_batch_bf16(state.queries.get(), state.queries_head_major.get(),
                               static_cast<int>(requests), uniform_tokens, query_heads,
                               head_dimension, stream);
      state.global_prefill_attention.run_uniform_ring_batch(
          state.queries_head_major.get(), device_key_caches, device_value_caches,
          speculative_backup_keys, speculative_backup_values, state.attention_output.get(),
          device_positions, static_cast<int>(requests), query_heads, kv_heads,
          uniform_tokens, uniform_capacity, head_dimension, stream);
      head_to_token_batch_bf16(state.attention_output.get(), state.queries.get(),
                               static_cast<int>(requests), uniform_tokens, query_heads,
                               head_dimension, stream);
      state.project(layer_index, hidden_states, state.queries.get(), output,
                    total_tokens, fp8_projections, stream);
      return;
    }
    const bool direct_unwrapped_speculation = speculative_sliding_gemm &&
        std::all_of(position_starts.begin(), position_starts.end(),
                    [&](int position) { return position + uniform_tokens <= uniform_capacity; });
    if (direct_unwrapped_speculation) {
      // Before the first ring wrap, physical and logical KV order are identical. Write the
      // proposal span into the real cache and attend there directly; this avoids materializing
      // roughly 13 GiB of retained KV data across Gemma 4's 50 sliding layers per verify pass.
      state.qkv_postprocessor.run_prefill_uniform_direct(
          state.packed_qkv.get(), weight("q_norm"), weight("k_norm"), state.queries.get(),
          pointer_base, pointer_base + requests, device_positions,
          static_cast<int>(requests), uniform_tokens, query_heads, kv_heads, head_dimension,
          layer.key_equals_value, uniform_capacity, state.epsilon, stream);
      token_to_head_batch_bf16(state.queries.get(), state.queries_head_major.get(),
                               static_cast<int>(requests), uniform_tokens, query_heads,
                               head_dimension, stream);
      const int maximum_kv_tokens = *std::max_element(
          position_starts.begin(), position_starts.end()) + uniform_tokens;
      state.global_prefill_attention.run_uniform_batch(
          state.queries_head_major.get(), device_key_caches, device_value_caches,
          state.attention_output.get(), device_positions, static_cast<int>(requests),
          query_heads, kv_heads, uniform_tokens, maximum_kv_tokens, uniform_capacity,
          head_dimension, stream);
      head_to_token_batch_bf16(state.attention_output.get(), state.queries.get(),
                               static_cast<int>(requests), uniform_tokens, query_heads,
                               head_dimension, stream);
      state.project(layer_index, hidden_states, state.queries.get(), output,
                    total_tokens, fp8_projections, stream);
      return;
    }
    if (uniform_prior > 0) {
      gather_kv_rings_bf16(device_key_caches, device_value_caches,
                            state.key_cache.get(), state.value_cache.get(), device_positions,
                            static_cast<int>(requests), kv_heads, uniform_prior, head_dimension,
                            uniform_capacity, staging_tokens, stream);
    }
    state.qkv_postprocessor.run_prefill_uniform(
        state.packed_qkv.get(), weight("q_norm"), weight("k_norm"), state.queries.get(),
        state.key_cache.get(), state.value_cache.get(), device_positions,
        static_cast<int>(requests), uniform_tokens, query_heads, kv_heads, head_dimension,
        layer.key_equals_value, uniform_prior, staging_tokens, state.epsilon, stream);
    const void* attention_states = state.attention_output.get();
    if (speculative_sliding_gemm) {
      // cuDNN's small-query SDPA plans are either unavailable or launch-bound for q=4. The
      // pointer-batched tensor-core QK/PV path treats the retained ring as an ordinary causal
      // context and covers every request with two GEMM launches.
      token_to_head_batch_bf16(state.queries.get(), state.queries_head_major.get(),
                               static_cast<int>(requests), uniform_tokens, query_heads,
                               head_dimension, stream);
      std::vector<const void*> staged_pointers(2 * requests);
      const std::uint64_t request_elements = static_cast<std::uint64_t>(kv_heads) *
          staging_tokens * head_dimension;
      for (std::size_t request = 0; request < requests; ++request) {
        staged_pointers[request] = static_cast<const unsigned char*>(state.key_cache.get()) +
                                   2ULL * request * request_elements;
        staged_pointers[requests + request] =
            static_cast<const unsigned char*>(state.value_cache.get()) +
            2ULL * request * request_elements;
      }
      std::vector<int> local_positions(requests, uniform_prior);
      check(cudaMemcpyAsync(state.prefill_positions.get(), local_positions.data(),
                            requests * sizeof(int), cudaMemcpyHostToDevice, stream),
            "copy speculative local positions");
      check(cudaMemcpyAsync(state.prefill_cache_pointers.get(), staged_pointers.data(),
                            staged_pointers.size() * sizeof(void*), cudaMemcpyHostToDevice,
                            stream), "copy speculative staged cache pointers");
      state.global_prefill_attention.run_uniform_batch(
          state.queries_head_major.get(),
          reinterpret_cast<const void* const*>(pointer_base),
          reinterpret_cast<const void* const*>(pointer_base + requests),
          state.attention_output.get(),
          static_cast<const int*>(state.prefill_positions.get()),
          static_cast<int>(requests), query_heads, kv_heads, uniform_tokens, staging_tokens,
          staging_tokens, head_dimension, stream);
      head_to_token_batch_bf16(state.attention_output.get(), state.queries.get(),
                               static_cast<int>(requests), uniform_tokens, query_heads,
                               head_dimension, stream);
      attention_states = state.queries.get();
      // Restore destination pointers and logical positions for the ring commit below.
      check(cudaMemcpyAsync(state.prefill_positions.get(), position_starts.data(),
                            requests * sizeof(int), cudaMemcpyHostToDevice, stream),
            "restore speculative logical positions");
      check(cudaMemcpyAsync(state.prefill_cache_pointers.get(), cache_pointers.data(),
                            cache_pointers.size() * sizeof(void*), cudaMemcpyHostToDevice,
                            stream), "restore speculative destination pointers");
    } else {
      state.sliding_prefill_attention.run(
          state.queries.get(), state.key_cache.get(), state.value_cache.get(),
          state.attention_output.get(), static_cast<int>(requests), query_heads, kv_heads,
          uniform_tokens, staging_tokens, staging_tokens, head_dimension,
          static_cast<int>(state.config.sliding_window), stream);
    }
    copy_kv_spans_to_rings_bf16(
        state.key_cache.get(), state.value_cache.get(),
        reinterpret_cast<void* const*>(pointer_base),
        reinterpret_cast<void* const*>(pointer_base + requests), device_positions,
        static_cast<int>(requests), kv_heads, uniform_tokens, head_dimension, staging_tokens,
        uniform_prior, uniform_capacity, stream);
    state.project(layer_index, hidden_states, attention_states, output,
                  total_tokens, fp8_projections, stream);
    return;
  }

  if (layer.attention == AttentionKind::global && uniform_shape) {
    std::vector<const void*> cache_pointers(2 * requests);
    for (std::size_t request = 0; request < requests; ++request) {
      cache_pointers[request] = key_caches[request];
      cache_pointers[requests + request] = value_caches[request];
    }
    if (prepared_positions == nullptr || prepared_cache_pointers == nullptr) {
      check(cudaMemcpyAsync(state.prefill_positions.get(), position_starts.data(),
                            requests * sizeof(int), cudaMemcpyHostToDevice, stream),
            "copy uniform global prefill positions");
      check(cudaMemcpyAsync(state.prefill_cache_pointers.get(), cache_pointers.data(),
                            cache_pointers.size() * sizeof(void*), cudaMemcpyHostToDevice, stream),
            "copy uniform global prefill cache pointers");
    }
    const auto* device_positions = prepared_positions != nullptr
        ? prepared_positions : static_cast<const int*>(state.prefill_positions.get());
    auto* pointer_base = prepared_cache_pointers != nullptr
        ? prepared_cache_pointers : static_cast<void**>(state.prefill_cache_pointers.get());
    state.qkv_postprocessor.run_prefill_uniform_direct(
        state.packed_qkv.get(), weight("q_norm"), weight("k_norm"), state.queries.get(),
        pointer_base, pointer_base + requests, device_positions,
        static_cast<int>(requests), uniform_tokens, query_heads, kv_heads, head_dimension,
        layer.key_equals_value, uniform_capacity, state.epsilon, stream);
    token_to_head_batch_bf16(state.queries.get(), state.queries_head_major.get(),
                             static_cast<int>(requests), uniform_tokens, query_heads,
                             head_dimension, stream);
    const bool sorted_positions = std::is_sorted(position_starts.begin(), position_starts.end());
    const std::uint64_t cache_request_bytes = 2ULL * kv_heads * uniform_capacity *
                                              head_dimension;
    bool contiguous_caches = true;
    for (std::size_t request = 1; request < requests; ++request) {
      contiguous_caches = contiguous_caches &&
          static_cast<const unsigned char*>(key_caches[request]) ==
              static_cast<const unsigned char*>(key_caches.front()) +
                  request * cache_request_bytes &&
          static_cast<const unsigned char*>(value_caches[request]) ==
              static_cast<const unsigned char*>(value_caches.front()) +
                  request * cache_request_bytes;
    }
    const bool split_contexts = requests >= 4 && sorted_positions &&
                                position_starts.back() - position_starts.front() > 512;
    const std::size_t split = split_contexts ? (requests + 1) / 2 : requests;
    const auto run_group = [&](std::size_t begin, std::size_t end) {
      if (begin == end) return;
      int group_maximum_kv_tokens = 0;
      for (std::size_t request = begin; request < end; ++request) {
        group_maximum_kv_tokens = std::max(
            group_maximum_kv_tokens, position_starts[request] + uniform_tokens);
      }
      if (fp8_projections && uniform_tokens <= 8) {
        // Tiny changes in M select radically different Lt QK kernels (6,004 tokens reaches
        // ~4 TB/s while 6,005 falls below 0.5 TB/s). The cache tail is zero-initialized and the
        // causal softmax masks it, so a 64-token bucket changes work only, never probabilities.
        group_maximum_kv_tokens = std::min(
            uniform_capacity, ((group_maximum_kv_tokens + 63) / 64) * 64);
      }
      const std::uint64_t request_elements =
          static_cast<std::uint64_t>(query_heads) * uniform_tokens * head_dimension;
      const auto* grouped_queries =
          static_cast<const unsigned char*>(state.queries_head_major.get()) +
          2ULL * begin * request_elements;
      auto* grouped_output = static_cast<unsigned char*>(state.key_cache.get()) +
                             2ULL * begin * request_elements;
      if (contiguous_caches) {
        state.global_prefill_attention.run_uniform_contiguous_batch(
            grouped_queries, key_caches[begin], value_caches[begin], grouped_output,
            device_positions + begin, static_cast<int>(end - begin), query_heads,
            kv_heads, uniform_tokens, group_maximum_kv_tokens, uniform_capacity,
            head_dimension, stream);
      } else {
        state.global_prefill_attention.run_uniform_batch(
            grouped_queries, reinterpret_cast<const void* const*>(pointer_base + begin),
            reinterpret_cast<const void* const*>(pointer_base + requests + begin),
            grouped_output, device_positions + begin, static_cast<int>(end - begin),
            query_heads, kv_heads, uniform_tokens, group_maximum_kv_tokens,
            uniform_capacity, head_dimension, stream);
      }
    };
    run_group(0, split);
    run_group(split, requests);
    head_to_token_batch_bf16(state.key_cache.get(), state.attention_output.get(),
                             static_cast<int>(requests), uniform_tokens, query_heads,
                             head_dimension, stream);
    state.project(layer_index, hidden_states, state.attention_output.get(), output,
                  total_tokens, fp8_projections, stream);
    return;
  }

  int row_offset = 0;
  for (std::size_t request = 0; request < requests; ++request) {
    const int tokens = token_counts[request];
    const int position_start = position_starts[request];
    const int cache_capacity = cache_capacities[request];
    const auto* packed = static_cast<const unsigned char*>(state.packed_qkv.get()) +
                         2ULL * row_offset * packed_width;
    auto* queries = static_cast<unsigned char*>(state.queries.get()) +
                    2ULL * row_offset * query_width;
    auto* attention_output = static_cast<unsigned char*>(state.attention_output.get()) +
                             2ULL * row_offset * query_width;
    if (layer.attention == AttentionKind::sliding) {
      const int prior = std::min(
          position_start, static_cast<int>(state.config.sliding_window) - 1);
      const int staging_tokens = prior + tokens;
      if (staging_tokens > state.maximum_tokens) {
        throw std::runtime_error("batched sliding prefill staging exceeds workspace");
      }
      gather_kv_ring_bf16(key_caches[request], state.key_cache.get(), kv_heads, prior,
                          head_dimension, cache_capacity, staging_tokens,
                          position_start - prior, stream);
      gather_kv_ring_bf16(value_caches[request], state.value_cache.get(), kv_heads, prior,
                          head_dimension, cache_capacity, staging_tokens,
                          position_start - prior, stream);
      state.qkv_postprocessor.run_positioned(
          packed, weight("q_norm"), weight("k_norm"), queries, state.key_cache.get(),
          state.value_cache.get(), tokens, query_heads, kv_heads, head_dimension,
          layer.key_equals_value, position_start, prior, staging_tokens, state.epsilon, stream);
      state.sliding_prefill_attention.run(
          queries, state.key_cache.get(), state.value_cache.get(), attention_output, 1,
          query_heads, kv_heads, tokens, staging_tokens, staging_tokens, head_dimension,
          static_cast<int>(state.config.sliding_window), stream);
      copy_kv_span_to_ring_bf16(
          state.key_cache.get(), key_caches[request], kv_heads, tokens, head_dimension,
          staging_tokens, prior, cache_capacity, position_start, stream);
      copy_kv_span_to_ring_bf16(
          state.value_cache.get(), value_caches[request], kv_heads, tokens, head_dimension,
          staging_tokens, prior, cache_capacity, position_start, stream);
    } else {
      state.qkv_postprocessor.run_positioned(
          packed, weight("q_norm"), weight("k_norm"), queries, key_caches[request],
          value_caches[request], tokens, query_heads, kv_heads, head_dimension,
          layer.key_equals_value, position_start, position_start, cache_capacity,
          state.epsilon, stream);
      token_to_head_bf16(queries, state.queries_head_major.get(), tokens, query_heads,
                         head_dimension, stream);
      state.global_prefill_attention.run(
          state.queries_head_major.get(), key_caches[request], value_caches[request],
          state.key_cache.get(), query_heads, kv_heads, tokens, position_start + tokens,
          cache_capacity, position_start, head_dimension, stream);
      head_to_token_bf16(state.key_cache.get(), attention_output, tokens, query_heads,
                         head_dimension, stream);
    }
    row_offset += tokens;
  }
  state.project(layer_index, hidden_states, state.attention_output.get(), output,
                total_tokens, fp8_projections, stream);
}

}  // namespace gradiated::engine
