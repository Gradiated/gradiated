#include "desmond/gpu_metrics.h"

#include "test_support.h"

#include <cstdint>

namespace {

DESMOND_TEST(unavailable_nvml_reports_only_the_availability_gauge) {
  const desmond::GpuMetrics metrics;
  if (metrics.available()) {
    return;
  }

  CHECK(!metrics.error().empty());
  CHECK(metrics.sample().empty());
  CHECK(metrics.prometheus() == "# TYPE desmond_nvml_available gauge\n"
                                "desmond_nvml_available 0\n");
}

DESMOND_TEST(gpu_series_are_grouped_by_family_and_skip_missing_readings) {
  const std::vector<desmond::GpuSample> samples{
      {
          .index = 0,
          .uuid = "GPU-\"0\"",
          .utilization = desmond::GpuUtilization{.gpu_percent = 90, .memory_percent = 40},
          .memory = desmond::GpuMemory{.total_bytes = 100, .used_bytes = 60, .free_bytes = 40},
          .temperature_celsius = 70U,
          .power_milliwatts = 300'000U,
          .total_energy_millijoules = std::uint64_t{5'000},
      },
      {.index = 1, .temperature_celsius = 65U},
  };

  CHECK(desmond::gpu_prometheus(true, samples) ==
        "# TYPE desmond_nvml_available gauge\n"
        "desmond_nvml_available 1\n"
        "# TYPE desmond_gpu_utilization_percent gauge\n"
        "desmond_gpu_utilization_percent{gpu=\"0\",uuid=\"GPU-\\\"0\\\"\"} 90\n"
        "# TYPE desmond_gpu_memory_utilization_percent gauge\n"
        "desmond_gpu_memory_utilization_percent{gpu=\"0\",uuid=\"GPU-\\\"0\\\"\"} 40\n"
        "# TYPE desmond_gpu_memory_total_bytes gauge\n"
        "desmond_gpu_memory_total_bytes{gpu=\"0\",uuid=\"GPU-\\\"0\\\"\"} 100\n"
        "# TYPE desmond_gpu_memory_used_bytes gauge\n"
        "desmond_gpu_memory_used_bytes{gpu=\"0\",uuid=\"GPU-\\\"0\\\"\"} 60\n"
        "# TYPE desmond_gpu_memory_free_bytes gauge\n"
        "desmond_gpu_memory_free_bytes{gpu=\"0\",uuid=\"GPU-\\\"0\\\"\"} 40\n"
        "# TYPE desmond_gpu_temperature_celsius gauge\n"
        "desmond_gpu_temperature_celsius{gpu=\"0\",uuid=\"GPU-\\\"0\\\"\"} 70\n"
        "desmond_gpu_temperature_celsius{gpu=\"1\"} 65\n"
        "# TYPE desmond_gpu_power_milliwatts gauge\n"
        "desmond_gpu_power_milliwatts{gpu=\"0\",uuid=\"GPU-\\\"0\\\"\"} 300000\n"
        "# TYPE desmond_gpu_total_energy_millijoules counter\n"
        "desmond_gpu_total_energy_millijoules{gpu=\"0\",uuid=\"GPU-\\\"0\\\"\"} 5000\n");
}

} // namespace
