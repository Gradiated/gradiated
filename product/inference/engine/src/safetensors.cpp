#include "gradiated/engine/safetensors.h"

#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/json.h"

#include <array>
#include <filesystem>
#include <fstream>
#include <limits>
#include <set>
#include <stdexcept>

namespace gradiated::engine {
namespace {

std::uint64_t checked_multiply(std::uint64_t left, std::uint64_t right, const std::string& context) {
  if (right != 0 && left > std::numeric_limits<std::uint64_t>::max() / right) {
    throw std::runtime_error("integer overflow for " + context);
  }
  return left * right;
}

std::uint64_t dtype_size(std::string_view dtype) {
  if (dtype == "BOOL" || dtype == "I8" || dtype == "U8") return 1;
  if (dtype == "F16" || dtype == "BF16" || dtype == "I16" || dtype == "U16") return 2;
  if (dtype == "F32" || dtype == "I32" || dtype == "U32") return 4;
  if (dtype == "F64" || dtype == "I64" || dtype == "U64") return 8;
  throw std::runtime_error("unsupported safetensors dtype: " + std::string(dtype));
}

std::uint64_t little_endian_u64(const std::array<unsigned char, 8>& bytes) {
  std::uint64_t value = 0;
  for (std::size_t index = 0; index < bytes.size(); ++index) {
    value |= static_cast<std::uint64_t>(bytes[index]) << (index * 8U);
  }
  return value;
}

void expect_shape(const ShardedSafetensors& weights, const std::string& name,
                  std::initializer_list<std::uint64_t> expected) {
  const auto& tensor = weights.at(name);
  const std::vector<std::uint64_t> shape(expected);
  if (tensor.dtype != "BF16" || tensor.shape != shape) {
    throw std::runtime_error("unexpected dtype or shape for " + name);
  }
}

std::string layer_name(std::size_t layer, std::string_view suffix) {
  return "model.language_model.layers." + std::to_string(layer) + "." + std::string(suffix);
}

}  // namespace

std::uint64_t TensorLocation::element_count() const {
  std::uint64_t result = 1;
  for (const std::uint64_t dimension : shape) result = checked_multiply(result, dimension, "tensor shape");
  return result;
}

SafetensorsFile SafetensorsFile::open(const std::string& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open safetensors file " + path);
  std::array<unsigned char, 8> header_size_bytes{};
  input.read(reinterpret_cast<char*>(header_size_bytes.data()),
             static_cast<std::streamsize>(header_size_bytes.size()));
  if (!input) throw std::runtime_error("cannot read safetensors header size from " + path);
  const std::uint64_t header_size = little_endian_u64(header_size_bytes);
  const std::uint64_t file_size = std::filesystem::file_size(path);
  if (header_size == 0 || header_size > file_size - 8ULL || header_size > (1ULL << 30U)) {
    throw std::runtime_error("invalid safetensors header size in " + path);
  }
  std::string header(static_cast<std::size_t>(header_size), '\0');
  input.read(header.data(), static_cast<std::streamsize>(header.size()));
  if (!input) throw std::runtime_error("cannot read safetensors header from " + path);
  const Json metadata = Json::parse(header);
  const std::uint64_t data_base = 8ULL + header_size;

  SafetensorsFile result;
  for (const auto& [name, value] : metadata.as_object()) {
    if (name == "__metadata__") continue;
    const std::string dtype = value.at("dtype").as_string();
    std::vector<std::uint64_t> shape;
    for (const Json& dimension : value.at("shape").as_array()) shape.push_back(dimension.as_u64());
    const auto& offsets = value.at("data_offsets").as_array();
    if (offsets.size() != 2) throw std::runtime_error("invalid offsets for tensor " + name);
    const std::uint64_t begin = offsets[0].as_u64();
    const std::uint64_t end = offsets[1].as_u64();
    if (end < begin || data_base > file_size || end > file_size - data_base) {
      throw std::runtime_error("out-of-range tensor " + name);
    }
    TensorLocation tensor{path, dtype, std::move(shape), data_base + begin, end - begin};
    const std::uint64_t expected_size = checked_multiply(tensor.element_count(), dtype_size(dtype), name);
    if (expected_size != tensor.byte_size) throw std::runtime_error("byte-size mismatch for tensor " + name);
    result.tensors_.emplace(name, std::move(tensor));
  }
  return result;
}

const std::map<std::string, TensorLocation, std::less<>>& SafetensorsFile::tensors() const {
  return tensors_;
}

const TensorLocation& SafetensorsFile::at(std::string_view name) const {
  const auto iterator = tensors_.find(name);
  if (iterator == tensors_.end()) throw std::runtime_error("missing tensor " + std::string(name));
  return iterator->second;
}

ShardedSafetensors ShardedSafetensors::open(const std::string& model_directory) {
  const std::filesystem::path directory(model_directory);
  const auto index_path = directory / "model.safetensors.index.json";
  if (!std::filesystem::exists(index_path)) {
    const auto single_path = directory / "model.safetensors";
    const auto single = SafetensorsFile::open(single_path.string());
    ShardedSafetensors result;
    result.tensors_ = single.tensors();
    return result;
  }
  const Json index = Json::parse(read_text_file(index_path.string()));
  const auto& weight_map = index.at("weight_map").as_object();
  std::set<std::string> shard_names;
  for (const auto& [name, shard] : weight_map) {
    static_cast<void>(name);
    shard_names.insert(shard.as_string());
  }

  ShardedSafetensors result;
  std::map<std::string, SafetensorsFile, std::less<>> shards;
  for (const auto& shard_name : shard_names) {
    shards.emplace(shard_name, SafetensorsFile::open((directory / shard_name).string()));
  }
  for (const auto& [name, shard] : weight_map) {
    const auto shard_iterator = shards.find(shard.as_string());
    if (shard_iterator == shards.end()) throw std::runtime_error("unknown shard for tensor " + name);
    const TensorLocation& tensor = shard_iterator->second.at(name);
    result.tensors_.emplace(name, tensor);
  }
  return result;
}

const TensorLocation& ShardedSafetensors::at(std::string_view name) const {
  const auto iterator = tensors_.find(name);
  if (iterator == tensors_.end()) throw std::runtime_error("missing tensor " + std::string(name));
  return iterator->second;
}

const std::map<std::string, TensorLocation, std::less<>>& ShardedSafetensors::tensors() const {
  return tensors_;
}

std::uint64_t ShardedSafetensors::parameter_count(std::string_view prefix) const {
  std::uint64_t result = 0;
  for (const auto& [name, tensor] : tensors_) {
    if (name.starts_with(prefix)) result += tensor.element_count();
  }
  return result;
}

std::uint64_t ShardedSafetensors::byte_size(std::string_view prefix) const {
  std::uint64_t result = 0;
  for (const auto& [name, tensor] : tensors_) {
    if (name.starts_with(prefix)) result += tensor.byte_size;
  }
  return result;
}

void validate_gemma4_weights(const ShardedSafetensors& weights, const Gemma4Config& config) {
  const std::uint64_t hidden = config.hidden_size;
  const std::uint64_t intermediate = config.intermediate_size;
  expect_shape(weights, "model.language_model.embed_tokens.weight", {config.vocabulary_size, hidden});
  expect_shape(weights, "model.language_model.norm.weight", {hidden});
  for (std::size_t layer = 0; layer < config.layers.size(); ++layer) {
    const auto& attention = config.layers[layer];
    for (const std::string_view norm : {"input_layernorm.weight", "post_attention_layernorm.weight",
                                        "pre_feedforward_layernorm.weight", "post_feedforward_layernorm.weight"}) {
      expect_shape(weights, layer_name(layer, norm), {hidden});
    }
    expect_shape(weights, layer_name(layer, "layer_scalar"), {1});
    expect_shape(weights, layer_name(layer, "mlp.gate_proj.weight"), {intermediate, hidden});
    expect_shape(weights, layer_name(layer, "mlp.up_proj.weight"), {intermediate, hidden});
    expect_shape(weights, layer_name(layer, "mlp.down_proj.weight"), {hidden, intermediate});
    expect_shape(weights, layer_name(layer, "self_attn.q_proj.weight"), {attention.query_width(), hidden});
    expect_shape(weights, layer_name(layer, "self_attn.k_proj.weight"), {attention.kv_width(), hidden});
    if (!attention.key_equals_value) {
      expect_shape(weights, layer_name(layer, "self_attn.v_proj.weight"), {attention.kv_width(), hidden});
    }
    expect_shape(weights, layer_name(layer, "self_attn.o_proj.weight"), {hidden, attention.query_width()});
    expect_shape(weights, layer_name(layer, "self_attn.q_norm.weight"), {attention.head_dimension});
    expect_shape(weights, layer_name(layer, "self_attn.k_norm.weight"), {attention.head_dimension});
  }
  const std::uint64_t actual = weights.parameter_count("model.language_model.");
  const std::uint64_t expected = config.text_parameter_count();
  if (actual != expected) {
    throw std::runtime_error("Gemma 4 text parameter count mismatch: expected " +
                             std::to_string(expected) + ", found " + std::to_string(actual));
  }
}

}  // namespace gradiated::engine
