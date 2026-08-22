#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace desmond {

struct GpuSample {
  unsigned int index{};
  std::string uuid;
  unsigned int gpu_utilization_percent{};
  unsigned int memory_utilization_percent{};
  std::uint64_t memory_total_bytes{};
  std::uint64_t memory_used_bytes{};
  std::uint64_t memory_free_bytes{};
  unsigned int temperature_celsius{};
  unsigned int power_milliwatts{};
  std::uint64_t total_energy_millijoules{};
};

class GpuMetrics {
 public:
  GpuMetrics();
  ~GpuMetrics();
  GpuMetrics(const GpuMetrics&) = delete;
  GpuMetrics& operator=(const GpuMetrics&) = delete;
  GpuMetrics(GpuMetrics&&) noexcept;
  GpuMetrics& operator=(GpuMetrics&&) noexcept;

  [[nodiscard]] bool available() const;
  [[nodiscard]] const std::string& error() const;
  [[nodiscard]] std::vector<GpuSample> sample() const;
  [[nodiscard]] std::string prometheus() const;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace desmond
