#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace desmond {

struct GpuUtilization {
  unsigned int gpu_percent{};
  unsigned int memory_percent{};
};

struct GpuMemory {
  std::uint64_t total_bytes{};
  std::uint64_t used_bytes{};
  std::uint64_t free_bytes{};
};

struct GpuSample {
  unsigned int index{};
  std::optional<std::string> uuid;
  std::optional<GpuUtilization> utilization;
  std::optional<GpuMemory> memory;
  std::optional<unsigned int> temperature_celsius;
  std::optional<unsigned int> power_milliwatts;
  std::optional<std::uint64_t> total_energy_millijoules;
};

class GpuMetrics {
public:
  GpuMetrics();
  ~GpuMetrics();
  GpuMetrics(const GpuMetrics &) = delete;
  GpuMetrics &operator=(const GpuMetrics &) = delete;

  [[nodiscard]] bool available() const;
  [[nodiscard]] const std::string &error() const;
  [[nodiscard]] std::vector<GpuSample> sample() const;
  [[nodiscard]] std::string prometheus() const;

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

[[nodiscard]] std::string gpu_prometheus(bool nvml_available,
                                         const std::vector<GpuSample> &samples);

} // namespace desmond
