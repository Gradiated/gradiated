#pragma once

#include <cstdint>
#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace gradiated::engine {

struct TensorLocation {
  std::string shard_path;
  std::string dtype;
  std::vector<std::uint64_t> shape;
  std::uint64_t file_offset;
  std::uint64_t byte_size;

  [[nodiscard]] std::uint64_t element_count() const;
};

class SafetensorsFile {
 public:
  static SafetensorsFile open(const std::string& path);

  [[nodiscard]] const std::map<std::string, TensorLocation, std::less<>>& tensors() const;
  [[nodiscard]] const TensorLocation& at(std::string_view name) const;

 private:
  std::map<std::string, TensorLocation, std::less<>> tensors_;
};

class ShardedSafetensors {
 public:
  static ShardedSafetensors open(const std::string& model_directory);

  [[nodiscard]] const TensorLocation& at(std::string_view name) const;
  [[nodiscard]] const std::map<std::string, TensorLocation, std::less<>>& tensors() const;
  [[nodiscard]] std::uint64_t parameter_count(std::string_view prefix) const;
  [[nodiscard]] std::uint64_t byte_size(std::string_view prefix) const;

 private:
  std::map<std::string, TensorLocation, std::less<>> tensors_;
};

void validate_gemma4_weights(const ShardedSafetensors& weights, const struct Gemma4Config& config);

}  // namespace gradiated::engine
