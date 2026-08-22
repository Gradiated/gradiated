#include "gradiated/engine/device_weights.h"

#include "gradiated/engine/safetensors.h"
#include "gradiated/engine/weight_plan.h"

#include <cuda_runtime.h>

#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <unistd.h>

namespace gradiated::engine {
namespace {

constexpr std::uint64_t alignment = 256;
constexpr std::size_t staging_bytes = 64ULL * 1024ULL * 1024ULL;

std::uint64_t align_up(std::uint64_t value) {
  return (value + alignment - 1U) & ~(alignment - 1U);
}

void cuda_check(cudaError_t result, const char* operation) {
  if (result != cudaSuccess) {
    throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(result));
  }
}

class FileDescriptor {
 public:
  explicit FileDescriptor(const std::string& path) : descriptor_(::open(path.c_str(), O_RDONLY | O_CLOEXEC)) {
    if (descriptor_ < 0) throw std::runtime_error("cannot open " + path + ": " + std::strerror(errno));
  }
  ~FileDescriptor() { if (descriptor_ >= 0) ::close(descriptor_); }
  int get() const { return descriptor_; }

 private:
  int descriptor_;
};

void read_exact(int descriptor, void* destination, std::size_t bytes, std::uint64_t offset,
                const std::string& tensor_name) {
  auto* output = static_cast<unsigned char*>(destination);
  std::size_t complete = 0;
  while (complete < bytes) {
    const ssize_t result = ::pread(descriptor, output + complete, bytes - complete,
                                   static_cast<off_t>(offset + complete));
    if (result < 0 && errno == EINTR) continue;
    if (result <= 0) throw std::runtime_error("cannot read tensor " + tensor_name);
    complete += static_cast<std::size_t>(result);
  }
}

}  // namespace

struct DeviceWeightArena::Implementation {
  void* arena{nullptr};
  void* staging{nullptr};
  std::uint64_t allocated{0};
  std::uint64_t payload{0};
  std::map<std::string, const void*, std::less<>> pointers;

  ~Implementation() {
    if (staging != nullptr) cudaFreeHost(staging);
    if (arena != nullptr) cudaFree(arena);
  }
};

DeviceWeightArena::DeviceWeightArena(std::unique_ptr<Implementation> implementation)
    : implementation_(std::move(implementation)) {}
DeviceWeightArena::~DeviceWeightArena() = default;

std::unique_ptr<DeviceWeightArena> DeviceWeightArena::load(
    const WeightPlan& plan, const ShardedSafetensors& weights,
    const std::vector<std::string>& segment_names) {
  std::set<std::string, std::less<>> selected(segment_names.begin(), segment_names.end());
  for (const auto& name : selected) static_cast<void>(plan.at(name));
  auto implementation = std::make_unique<Implementation>();
  std::map<std::string, std::uint64_t, std::less<>> offsets;
  for (const auto& segment : plan.segments()) {
    if (!selected.empty() && !selected.contains(segment.name)) continue;
    implementation->allocated = align_up(implementation->allocated);
    offsets.emplace(segment.name, implementation->allocated);
    implementation->allocated += segment.byte_size;
    implementation->payload += segment.byte_size;
  }
  implementation->allocated = align_up(implementation->allocated);
  if (implementation->allocated == 0) throw std::runtime_error("empty device weight selection");
  cuda_check(cudaMalloc(&implementation->arena, static_cast<std::size_t>(implementation->allocated)),
             "allocate device weight arena");
  cuda_check(cudaHostAlloc(&implementation->staging, staging_bytes, cudaHostAllocPortable),
             "allocate pinned weight staging buffer");

  std::map<std::string, std::unique_ptr<FileDescriptor>, std::less<>> files;
  for (const auto& segment : plan.segments()) {
    const auto selected_offset = offsets.find(segment.name);
    if (selected_offset == offsets.end()) continue;
    auto* segment_destination = static_cast<unsigned char*>(implementation->arena) + selected_offset->second;
    implementation->pointers.emplace(segment.name, segment_destination);
    for (const auto& source : segment.sources) {
      const TensorLocation& tensor = weights.at(source.tensor_name);
      auto file = files.find(tensor.shard_path);
      if (file == files.end()) {
        file = files.emplace(tensor.shard_path, std::make_unique<FileDescriptor>(tensor.shard_path)).first;
      }
      std::uint64_t copied = 0;
      while (copied < source.byte_size) {
        const auto chunk = static_cast<std::size_t>(
            std::min<std::uint64_t>(staging_bytes, source.byte_size - copied));
        read_exact(file->second->get(), implementation->staging, chunk, tensor.file_offset + copied,
                   source.tensor_name);
        cuda_check(cudaMemcpy(segment_destination + source.segment_offset + copied,
                              implementation->staging, chunk, cudaMemcpyHostToDevice),
                   "copy weight to device");
        copied += chunk;
      }
    }
  }
  return std::unique_ptr<DeviceWeightArena>(new DeviceWeightArena(std::move(implementation)));
}

const void* DeviceWeightArena::at(std::string_view name) const {
  const auto iterator = implementation_->pointers.find(name);
  if (iterator == implementation_->pointers.end()) {
    throw std::runtime_error("device weight is not loaded: " + std::string(name));
  }
  return iterator->second;
}

std::uint64_t DeviceWeightArena::allocated_bytes() const { return implementation_->allocated; }
std::uint64_t DeviceWeightArena::payload_bytes() const { return implementation_->payload; }

}  // namespace gradiated::engine
