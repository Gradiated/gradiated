#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/json.h"
#include "gradiated/engine/safetensors.h"

#include <array>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

void check(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}

class TemporaryDirectory {
 public:
  TemporaryDirectory() {
    const auto suffix = std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("gradiated-engine-test-" + std::to_string(suffix));
    std::filesystem::create_directory(path_);
  }
  ~TemporaryDirectory() { std::filesystem::remove_all(path_); }
  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

void write_text(const std::filesystem::path& path, const std::string& text) {
  std::ofstream output(path, std::ios::binary);
  output << text;
  if (!output) throw std::runtime_error("test write failed");
}

void test_json() {
  const auto json = gradiated::engine::Json::parse(
      R"({"integer":42,"float":1e-6,"unicode":"\u20ac","array":[true,null]})");
  check(json.at("integer").as_u64() == 42, "integer parsing");
  check(json.at("float").as_double() == 1e-6, "float parsing");
  check(json.at("unicode").as_string() == "\xe2\x82\xac", "unicode parsing");
  check(json.at("array").as_array()[0].as_bool(), "array parsing");
  check(json.at("array").as_array()[1].is_null(), "null parsing");
}

void test_safetensors() {
  TemporaryDirectory temporary;
  std::string header = R"({"x":{"dtype":"BF16","shape":[2,3],"data_offsets":[0,12]}})";
  while (header.size() % 8 != 0) header.push_back(' ');
  const auto path = temporary.path() / "weights.safetensors";
  std::ofstream output(path, std::ios::binary);
  const std::uint64_t size = header.size();
  for (unsigned index = 0; index < 8; ++index) {
    output.put(static_cast<char>((size >> (index * 8U)) & 0xffU));
  }
  output.write(header.data(), static_cast<std::streamsize>(header.size()));
  const std::array<char, 12> data{};
  output.write(data.data(), static_cast<std::streamsize>(data.size()));
  output.close();

  const auto file = gradiated::engine::SafetensorsFile::open(path.string());
  const auto& tensor = file.at("x");
  check(tensor.dtype == "BF16", "safetensors dtype");
  check(tensor.shape == std::vector<std::uint64_t>({2, 3}), "safetensors shape");
  check(tensor.byte_size == 12, "safetensors byte size");
  check(tensor.file_offset == 8 + header.size(), "safetensors file offset");
}

void test_gemma_config() {
  TemporaryDirectory temporary;
  const std::string config = R"({
    "model_type":"gemma4",
    "text_config":{
      "model_type":"gemma4_text","tie_word_embeddings":true,"attention_bias":false,
      "hidden_size_per_layer_input":0,"num_kv_shared_layers":0,
      "hidden_size":8,"intermediate_size":16,"num_hidden_layers":2,"vocab_size":32,
      "sliding_window":4,"max_position_embeddings":128,"rms_norm_eps":1e-6,
      "final_logit_softcapping":30,"num_attention_heads":2,"num_key_value_heads":1,
      "head_dim":4,"num_global_key_value_heads":1,"global_head_dim":8,
      "attention_k_eq_v":true,"layer_types":["sliding_attention","full_attention"],
      "rope_parameters":{
        "sliding_attention":{"rope_theta":10000,"rope_type":"default"},
        "full_attention":{"rope_theta":1000000,"rope_type":"proportional","partial_rotary_factor":0.25}
      }
    }
  })";
  const auto path = temporary.path() / "config.json";
  write_text(path, config);
  const auto parsed = gradiated::engine::Gemma4Config::load(path.string());
  check(parsed.layers.size() == 2, "layer count");
  check(parsed.layers[0].query_width() == 8, "sliding query width");
  check(parsed.layers[0].kv_width() == 4, "sliding kv width");
  check(parsed.layers[0].rotary_dimension == 4, "sliding rotary dimension");
  check(parsed.layers[1].query_width() == 16, "global query width");
  check(parsed.layers[1].kv_width() == 8, "global kv width");
  check(parsed.layers[1].rotary_dimension == 2, "partial global rotary dimension");
  check(parsed.layers[1].key_equals_value, "global K=V");
}

}  // namespace

int main() {
  try {
    test_json();
    test_safetensors();
    test_gemma_config();
    std::cout << "all model tests passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "model test failed: " << error.what() << '\n';
    return 1;
  }
}
