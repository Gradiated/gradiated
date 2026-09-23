#include "desmond/gpu_metrics.h"

#include "desmond/prometheus.h"

#include <dlfcn.h>

#include <array>
#include <sstream>
#include <utility>

namespace desmond {
namespace {

using NvmlReturn = int;
using NvmlDevice = struct nvmlDevice_st *;
constexpr NvmlReturn kNvmlSuccess = 0;
constexpr unsigned int kNvmlTemperatureGpu = 0;

struct NvmlUtilization {
  unsigned int gpu;
  unsigned int memory;
};

struct NvmlMemory {
  unsigned long long total;
  unsigned long long free;
  unsigned long long used;
};

} // namespace

struct GpuMetrics::Impl {
  void *library{nullptr};
  std::string error;
  NvmlReturn (*init)(){nullptr};
  NvmlReturn (*shutdown)(){nullptr};
  NvmlReturn (*device_count)(unsigned int *){nullptr};
  NvmlReturn (*device_handle)(unsigned int, NvmlDevice *){nullptr};
  NvmlReturn (*device_uuid)(NvmlDevice, char *, unsigned int){nullptr};
  NvmlReturn (*device_utilization)(NvmlDevice, NvmlUtilization *){nullptr};
  NvmlReturn (*device_memory)(NvmlDevice, NvmlMemory *){nullptr};
  NvmlReturn (*device_temperature)(NvmlDevice, unsigned int, unsigned int *){nullptr};
  NvmlReturn (*device_power)(NvmlDevice, unsigned int *){nullptr};
  NvmlReturn (*device_energy)(NvmlDevice, unsigned long long *){nullptr};
  bool initialized{false};

  template <typename Function> void load_optional(Function &destination, const char *name) {
    destination = reinterpret_cast<Function>(dlsym(library, name));
  }

  template <typename Function> bool require(Function &destination, const char *name) {
    load_optional(destination, name);
    if (destination == nullptr) {
      error = std::string("missing NVML symbol ") + name;
      return false;
    }

    return true;
  }
};

GpuMetrics::GpuMetrics() : impl_(std::make_unique<Impl>()) {
  impl_->library = dlopen("libnvidia-ml.so.1", RTLD_NOW | RTLD_LOCAL);
  if (impl_->library == nullptr) {
    const char *message = dlerror();
    impl_->error = message == nullptr ? "NVML is unavailable" : message;
    return;
  }

  if (!impl_->require(impl_->init, "nvmlInit_v2") ||
      !impl_->require(impl_->shutdown, "nvmlShutdown") ||
      !impl_->require(impl_->device_count, "nvmlDeviceGetCount_v2") ||
      !impl_->require(impl_->device_handle, "nvmlDeviceGetHandleByIndex_v2") ||
      !impl_->require(impl_->device_uuid, "nvmlDeviceGetUUID") ||
      !impl_->require(impl_->device_utilization, "nvmlDeviceGetUtilizationRates") ||
      !impl_->require(impl_->device_memory, "nvmlDeviceGetMemoryInfo") ||
      !impl_->require(impl_->device_temperature, "nvmlDeviceGetTemperature")) {
    return;
  }

  impl_->load_optional(impl_->device_power, "nvmlDeviceGetPowerUsage");
  impl_->load_optional(impl_->device_energy, "nvmlDeviceGetTotalEnergyConsumption");

  if (impl_->init() != kNvmlSuccess) {
    impl_->error = "nvmlInit_v2 failed";
    return;
  }

  impl_->initialized = true;
}

GpuMetrics::~GpuMetrics() {
  if (impl_->initialized && impl_->shutdown != nullptr) {
    impl_->shutdown();
  }
  if (impl_->library != nullptr) {
    dlclose(impl_->library);
  }
}

bool GpuMetrics::available() const {
  return impl_->initialized;
}

const std::string &GpuMetrics::error() const {
  return impl_->error;
}

std::vector<GpuSample> GpuMetrics::sample() const {
  std::vector<GpuSample> samples;
  if (!available()) {
    return samples;
  }

  unsigned int count = 0;
  if (impl_->device_count(&count) != kNvmlSuccess) {
    return samples;
  }

  samples.reserve(count);
  for (unsigned int index = 0; index < count; ++index) {
    NvmlDevice device = nullptr;
    if (impl_->device_handle(index, &device) != kNvmlSuccess) {
      continue;
    }

    GpuSample sample{.index = index};
    std::array<char, 96> uuid{};
    if (impl_->device_uuid(device, uuid.data(), static_cast<unsigned int>(uuid.size())) ==
        kNvmlSuccess) {
      sample.uuid = uuid.data();
    }

    NvmlUtilization utilization{};
    if (impl_->device_utilization(device, &utilization) == kNvmlSuccess) {
      sample.utilization = GpuUtilization{utilization.gpu, utilization.memory};
    }

    NvmlMemory memory{};
    if (impl_->device_memory(device, &memory) == kNvmlSuccess) {
      sample.memory = GpuMemory{memory.total, memory.used, memory.free};
    }

    unsigned int temperature = 0;
    if (impl_->device_temperature(device, kNvmlTemperatureGpu, &temperature) == kNvmlSuccess) {
      sample.temperature_celsius = temperature;
    }

    unsigned int power = 0;
    if (impl_->device_power != nullptr && impl_->device_power(device, &power) == kNvmlSuccess) {
      sample.power_milliwatts = power;
    }

    unsigned long long energy = 0;
    if (impl_->device_energy != nullptr && impl_->device_energy(device, &energy) == kNvmlSuccess) {
      sample.total_energy_millijoules = energy;
    }

    samples.push_back(std::move(sample));
  }

  return samples;
}

std::string GpuMetrics::prometheus() const {
  return gpu_prometheus(available(), sample());
}

std::string gpu_prometheus(const bool nvml_available, const std::vector<GpuSample> &samples) {
  using prometheus::MetricType;
  std::ostringstream output;
  prometheus::write_metric(output, "desmond_nvml_available", MetricType::gauge,
                           nvml_available ? 1 : 0);

  const auto family = [&](const char *name, const MetricType type, const auto &reading) {
    if (samples.empty()) {
      return;
    }

    prometheus::write_type(output, name, type);
    for (const auto &gpu : samples) {
      const auto value = reading(gpu);
      if (!value) {
        continue;
      }

      output << name << "{gpu=\"" << gpu.index << '"';
      if (gpu.uuid) {
        output << ",uuid=\"" << prometheus::label_value(*gpu.uuid) << '"';
      }
      output << "} " << *value << '\n';
    }
  };

  family("desmond_gpu_utilization_percent", MetricType::gauge, [](const GpuSample &gpu) {
    return gpu.utilization ? std::optional(gpu.utilization->gpu_percent) : std::nullopt;
  });
  family("desmond_gpu_memory_utilization_percent", MetricType::gauge, [](const GpuSample &gpu) {
    return gpu.utilization ? std::optional(gpu.utilization->memory_percent) : std::nullopt;
  });
  family("desmond_gpu_memory_total_bytes", MetricType::gauge, [](const GpuSample &gpu) {
    return gpu.memory ? std::optional(gpu.memory->total_bytes) : std::nullopt;
  });
  family("desmond_gpu_memory_used_bytes", MetricType::gauge, [](const GpuSample &gpu) {
    return gpu.memory ? std::optional(gpu.memory->used_bytes) : std::nullopt;
  });
  family("desmond_gpu_memory_free_bytes", MetricType::gauge, [](const GpuSample &gpu) {
    return gpu.memory ? std::optional(gpu.memory->free_bytes) : std::nullopt;
  });
  family("desmond_gpu_temperature_celsius", MetricType::gauge,
         [](const GpuSample &gpu) { return gpu.temperature_celsius; });
  family("desmond_gpu_power_milliwatts", MetricType::gauge,
         [](const GpuSample &gpu) { return gpu.power_milliwatts; });
  family("desmond_gpu_total_energy_millijoules", MetricType::counter,
         [](const GpuSample &gpu) { return gpu.total_energy_millijoules; });

  return output.str();
}

} // namespace desmond
