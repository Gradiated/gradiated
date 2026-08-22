#include "desmond/gpu_metrics.h"

#include <dlfcn.h>

#include <array>
#include <sstream>
#include <utility>

namespace desmond {
namespace {

using NvmlReturn = int;
using NvmlDevice = struct nvmlDevice_st*;
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

std::string escape_label(const std::string& value) {
  std::string escaped;
  escaped.reserve(value.size());
  for (const char character : value) {
    switch (character) {
      case '\\':
        escaped += "\\\\";
        break;
      case '"':
        escaped += "\\\"";
        break;
      case '\n':
        escaped += "\\n";
        break;
      default:
        escaped += character;
    }
  }
  return escaped;
}

}  // namespace

struct GpuMetrics::Impl {
  void* library{nullptr};
  std::string error;
  NvmlReturn (*init)(){nullptr};
  NvmlReturn (*shutdown)(){nullptr};
  NvmlReturn (*device_count)(unsigned int*){nullptr};
  NvmlReturn (*device_handle)(unsigned int, NvmlDevice*){nullptr};
  NvmlReturn (*device_uuid)(NvmlDevice, char*, unsigned int){nullptr};
  NvmlReturn (*device_utilization)(NvmlDevice, NvmlUtilization*){nullptr};
  NvmlReturn (*device_memory)(NvmlDevice, NvmlMemory*){nullptr};
  NvmlReturn (*device_temperature)(NvmlDevice, unsigned int, unsigned int*){nullptr};
  NvmlReturn (*device_power)(NvmlDevice, unsigned int*){nullptr};
  NvmlReturn (*device_energy)(NvmlDevice, unsigned long long*){nullptr};
  bool initialized{false};

  template <typename Function>
  bool load(Function& destination, const char* name, const bool required = true) {
    destination = reinterpret_cast<Function>(dlsym(library, name));
    if (destination == nullptr && required) {
      error = std::string("missing NVML symbol ") + name;
      return false;
    }
    return true;
  }
};

GpuMetrics::GpuMetrics() : impl_(std::make_unique<Impl>()) {
  impl_->library = dlopen("libnvidia-ml.so.1", RTLD_NOW | RTLD_LOCAL);
  if (impl_->library == nullptr) {
    const char* message = dlerror();
    impl_->error = message == nullptr ? "NVML is unavailable" : message;
    return;
  }
  if (!impl_->load(impl_->init, "nvmlInit_v2") ||
      !impl_->load(impl_->shutdown, "nvmlShutdown") ||
      !impl_->load(impl_->device_count, "nvmlDeviceGetCount_v2") ||
      !impl_->load(impl_->device_handle, "nvmlDeviceGetHandleByIndex_v2") ||
      !impl_->load(impl_->device_uuid, "nvmlDeviceGetUUID") ||
      !impl_->load(impl_->device_utilization, "nvmlDeviceGetUtilizationRates") ||
      !impl_->load(impl_->device_memory, "nvmlDeviceGetMemoryInfo") ||
      !impl_->load(impl_->device_temperature, "nvmlDeviceGetTemperature") ||
      !impl_->load(impl_->device_power, "nvmlDeviceGetPowerUsage", false) ||
      !impl_->load(impl_->device_energy, "nvmlDeviceGetTotalEnergyConsumption", false)) {
    return;
  }
  if (impl_->init() != kNvmlSuccess) {
    impl_->error = "nvmlInit_v2 failed";
    return;
  }
  impl_->initialized = true;
}

GpuMetrics::~GpuMetrics() {
  if (impl_ != nullptr) {
    if (impl_->initialized && impl_->shutdown != nullptr) {
      impl_->shutdown();
    }
    if (impl_->library != nullptr) {
      dlclose(impl_->library);
    }
  }
}

GpuMetrics::GpuMetrics(GpuMetrics&&) noexcept = default;
GpuMetrics& GpuMetrics::operator=(GpuMetrics&&) noexcept = default;

bool GpuMetrics::available() const { return impl_->initialized; }
const std::string& GpuMetrics::error() const { return impl_->error; }

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
    GpuSample sample;
    sample.index = index;
    std::array<char, 96> uuid{};
    if (impl_->device_uuid(device, uuid.data(), static_cast<unsigned int>(uuid.size())) ==
        kNvmlSuccess) {
      sample.uuid = uuid.data();
    }
    NvmlUtilization utilization{};
    if (impl_->device_utilization(device, &utilization) == kNvmlSuccess) {
      sample.gpu_utilization_percent = utilization.gpu;
      sample.memory_utilization_percent = utilization.memory;
    }
    NvmlMemory memory{};
    if (impl_->device_memory(device, &memory) == kNvmlSuccess) {
      sample.memory_total_bytes = memory.total;
      sample.memory_used_bytes = memory.used;
      sample.memory_free_bytes = memory.free;
    }
    impl_->device_temperature(device, kNvmlTemperatureGpu, &sample.temperature_celsius);
    if (impl_->device_power != nullptr) {
      impl_->device_power(device, &sample.power_milliwatts);
    }
    if (impl_->device_energy != nullptr) {
      unsigned long long energy = 0;
      if (impl_->device_energy(device, &energy) == kNvmlSuccess) {
        sample.total_energy_millijoules = energy;
      }
    }
    samples.push_back(std::move(sample));
  }
  return samples;
}

std::string GpuMetrics::prometheus() const {
  std::ostringstream output;
  output << "# HELP desmond_nvml_available Whether NVML initialized successfully.\n"
         << "# TYPE desmond_nvml_available gauge\n"
         << "desmond_nvml_available " << (available() ? 1 : 0) << '\n';
  for (const auto& gpu : sample()) {
    const std::string labels = "gpu=\"" + std::to_string(gpu.index) + "\",uuid=\"" +
                               escape_label(gpu.uuid) + "\"";
    output << "desmond_gpu_utilization_percent{" << labels << "} "
           << gpu.gpu_utilization_percent << '\n'
           << "desmond_gpu_memory_utilization_percent{" << labels << "} "
           << gpu.memory_utilization_percent << '\n'
           << "desmond_gpu_memory_total_bytes{" << labels << "} "
           << gpu.memory_total_bytes << '\n'
           << "desmond_gpu_memory_used_bytes{" << labels << "} " << gpu.memory_used_bytes
           << '\n'
           << "desmond_gpu_memory_free_bytes{" << labels << "} " << gpu.memory_free_bytes
           << '\n'
           << "desmond_gpu_temperature_celsius{" << labels << "} "
           << gpu.temperature_celsius << '\n'
           << "desmond_gpu_power_milliwatts{" << labels << "} " << gpu.power_milliwatts
           << '\n'
           << "desmond_gpu_total_energy_millijoules{" << labels << "} "
           << gpu.total_energy_millijoules << '\n';
  }
  return output.str();
}

}  // namespace desmond
