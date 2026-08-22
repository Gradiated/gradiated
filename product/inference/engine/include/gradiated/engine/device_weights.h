#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

namespace gradiated::engine {

class DeviceWeightArena {
 public:
  static std::unique_ptr<DeviceWeightArena> load(const class WeightPlan& plan,
                                                  const class ShardedSafetensors& weights,
                                                  const std::vector<std::string>& segment_names = {});
  ~DeviceWeightArena();

  DeviceWeightArena(const DeviceWeightArena&) = delete;
  DeviceWeightArena& operator=(const DeviceWeightArena&) = delete;

  [[nodiscard]] const void* at(std::string_view name) const;
  [[nodiscard]] std::uint64_t allocated_bytes() const;
  [[nodiscard]] std::uint64_t payload_bytes() const;

 private:
  struct Implementation;
  explicit DeviceWeightArena(std::unique_ptr<Implementation> implementation);
  std::unique_ptr<Implementation> implementation_;
};

}  // namespace gradiated::engine
