#pragma once

#include <cstdint>
#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace gradiated::engine {

struct WeightSource {
  std::string tensor_name;
  std::uint64_t segment_offset;
  std::uint64_t byte_size;
};

struct WeightSegment {
  std::string name;
  std::vector<std::uint64_t> shape;
  std::uint64_t arena_offset;
  std::uint64_t byte_size;
  std::vector<WeightSource> sources;
};

class WeightPlan {
 public:
  static WeightPlan gemma4(const struct Gemma4Config& config,
                           const class ShardedSafetensors& weights);
  static WeightPlan gemma4_assistant(const class ShardedSafetensors& weights);

  [[nodiscard]] const WeightSegment& at(std::string_view name) const;
  [[nodiscard]] const std::vector<WeightSegment>& segments() const;
  [[nodiscard]] std::uint64_t arena_bytes() const;

 private:
  std::vector<WeightSegment> segments_;
  std::map<std::string, std::size_t, std::less<>> by_name_;
  std::uint64_t arena_bytes_{0};
};

}  // namespace gradiated::engine
