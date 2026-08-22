#include "gradiated/engine/weight_plan.h"

#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/safetensors.h"

#include <set>
#include <stdexcept>

namespace gradiated::engine {
namespace {

constexpr std::uint64_t alignment = 256;

std::uint64_t align_up(std::uint64_t value) {
  return (value + alignment - 1U) & ~(alignment - 1U);
}

std::string layer_name(std::size_t layer, std::string_view suffix) {
  return "model.language_model.layers." + std::to_string(layer) + "." + std::string(suffix);
}

}  // namespace

WeightPlan WeightPlan::gemma4(const Gemma4Config& config, const ShardedSafetensors& weights) {
  WeightPlan result;
  std::set<std::string> used;
  std::uint64_t offset = 0;
  const auto add = [&](std::string name, std::vector<std::uint64_t> shape,
                       std::initializer_list<std::string> source_names) {
    WeightSegment segment{.name = std::move(name),
                          .shape = std::move(shape),
                          .arena_offset = align_up(offset),
                          .byte_size = 0,
                          .sources = {}};
    for (const std::string& source_name : source_names) {
      const TensorLocation& source = weights.at(source_name);
      if (source.dtype != "BF16") throw std::runtime_error("execution weights must be BF16: " + source_name);
      if (!used.insert(source_name).second) throw std::runtime_error("weight source used twice: " + source_name);
      segment.sources.push_back({source_name, segment.byte_size, source.byte_size});
      segment.byte_size += source.byte_size;
    }
    std::uint64_t elements = 1;
    for (const std::uint64_t dimension : segment.shape) elements *= dimension;
    if (elements * 2ULL != segment.byte_size) {
      throw std::runtime_error("packed execution shape does not match source bytes: " + segment.name);
    }
    offset = segment.arena_offset + segment.byte_size;
    result.by_name_.emplace(segment.name, result.segments_.size());
    result.segments_.push_back(std::move(segment));
  };

  const std::uint64_t hidden = config.hidden_size;
  const std::uint64_t intermediate = config.intermediate_size;
  add("token_embedding", {config.vocabulary_size, hidden},
      {"model.language_model.embed_tokens.weight"});
  for (std::size_t layer = 0; layer < config.layers.size(); ++layer) {
    const auto& attention = config.layers[layer];
    const std::string prefix = "layer." + std::to_string(layer) + ".";
    add(prefix + "input_norm", {hidden}, {layer_name(layer, "input_layernorm.weight")});
    add(prefix + "q_norm", {attention.head_dimension}, {layer_name(layer, "self_attn.q_norm.weight")});
    add(prefix + "k_norm", {attention.head_dimension}, {layer_name(layer, "self_attn.k_norm.weight")});
    if (attention.key_equals_value) {
      add(prefix + "qkv", {attention.query_width() + attention.kv_width(), hidden},
          {layer_name(layer, "self_attn.q_proj.weight"), layer_name(layer, "self_attn.k_proj.weight")});
    } else {
      add(prefix + "qkv", {attention.query_width() + 2ULL * attention.kv_width(), hidden},
          {layer_name(layer, "self_attn.q_proj.weight"), layer_name(layer, "self_attn.k_proj.weight"),
           layer_name(layer, "self_attn.v_proj.weight")});
    }
    add(prefix + "o", {hidden, attention.query_width()}, {layer_name(layer, "self_attn.o_proj.weight")});
    add(prefix + "post_attention_norm", {hidden}, {layer_name(layer, "post_attention_layernorm.weight")});
    add(prefix + "pre_mlp_norm", {hidden}, {layer_name(layer, "pre_feedforward_layernorm.weight")});
    add(prefix + "gate_up", {2ULL * intermediate, hidden},
        {layer_name(layer, "mlp.gate_proj.weight"), layer_name(layer, "mlp.up_proj.weight")});
    add(prefix + "down", {hidden, intermediate}, {layer_name(layer, "mlp.down_proj.weight")});
    add(prefix + "post_mlp_norm", {hidden}, {layer_name(layer, "post_feedforward_layernorm.weight")});
    add(prefix + "scalar", {1}, {layer_name(layer, "layer_scalar")});
  }
  add("final_norm", {hidden}, {"model.language_model.norm.weight"});
  for (const auto& [name, tensor] : weights.tensors()) {
    static_cast<void>(tensor);
    if (name.starts_with("model.language_model.") && !used.contains(name)) {
      throw std::runtime_error("text tensor absent from execution plan: " + name);
    }
  }
  result.arena_bytes_ = align_up(offset);
  return result;
}

const WeightSegment& WeightPlan::at(std::string_view name) const {
  const auto iterator = by_name_.find(name);
  if (iterator == by_name_.end()) throw std::runtime_error("missing execution weight " + std::string(name));
  return segments_[iterator->second];
}

const std::vector<WeightSegment>& WeightPlan::segments() const { return segments_; }
std::uint64_t WeightPlan::arena_bytes() const { return arena_bytes_; }

}  // namespace gradiated::engine
