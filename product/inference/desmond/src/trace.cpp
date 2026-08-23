#include "desmond/trace.h"

#include <bit>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <new>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>

#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

namespace desmond {

namespace {

constexpr std::uint64_t shared_trace_magic = 0x44534d4f4e445452ULL;
constexpr std::uint32_t shared_trace_version = 1;

struct alignas(64) SharedTraceHeader {
  std::uint64_t magic{};
  std::uint32_t version{};
  std::uint32_t event_bytes{};
  std::uint64_t capacity{};
  alignas(64) std::atomic<std::uint64_t> head{0};
  alignas(64) std::atomic<std::uint64_t> tail{0};
  alignas(64) std::atomic<std::uint64_t> dropped{0};
};

static_assert(std::is_trivially_copyable_v<TraceEvent>);

std::runtime_error system_error(const char* operation) {
  return std::runtime_error(std::string(operation) + ": " + std::strerror(errno));
}

std::size_t mapping_size(const std::size_t capacity) {
  if (capacity < 2 || capacity > 4'194'304 || !std::has_single_bit(capacity)) {
    throw std::invalid_argument("shared trace capacity is out of range");
  }
  return sizeof(SharedTraceHeader) + capacity * sizeof(TraceEvent);
}

SharedTraceHeader* header(void* mapping) {
  return static_cast<SharedTraceHeader*>(mapping);
}

TraceEvent* events(void* mapping) {
  return reinterpret_cast<TraceEvent*>(
      static_cast<unsigned char*>(mapping) + sizeof(SharedTraceHeader));
}

}  // namespace

TraceRing::TraceRing(const std::size_t capacity)
    : capacity_(capacity), events_(std::make_unique<TraceEvent[]>(capacity)) {
  if (capacity < 2) {
    throw std::invalid_argument("trace ring capacity must be at least two");
  }
}

bool TraceRing::try_push(const TraceEvent& event) noexcept {
  const auto head = head_.load(std::memory_order_relaxed);
  const auto tail = tail_.load(std::memory_order_acquire);
  if (head - tail >= capacity_) {
    dropped_.fetch_add(1, std::memory_order_relaxed);
    return false;
  }
  events_[head % capacity_] = event;
  head_.store(head + 1, std::memory_order_release);
  return true;
}

bool TraceRing::try_pop(TraceEvent& event) noexcept {
  const auto tail = tail_.load(std::memory_order_relaxed);
  const auto head = head_.load(std::memory_order_acquire);
  if (tail == head) {
    return false;
  }
  event = events_[tail % capacity_];
  tail_.store(tail + 1, std::memory_order_release);
  return true;
}

std::size_t TraceRing::capacity() const noexcept { return capacity_; }

std::uint64_t TraceRing::dropped() const noexcept {
  return dropped_.load(std::memory_order_relaxed);
}

SharedTraceRing::SharedTraceRing(std::string path, void* mapping,
                                 const std::size_t mapping_bytes,
                                 const bool owner) noexcept
    : path_(std::move(path)), mapping_(mapping), mapping_bytes_(mapping_bytes), owner_(owner) {}

std::unique_ptr<SharedTraceRing> SharedTraceRing::create(std::string path,
                                                        const std::size_t capacity) {
  const std::size_t bytes = mapping_size(capacity);
  const int descriptor = ::open(path.c_str(), O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0600);
  if (descriptor < 0) throw system_error("create shared trace ring");
  if (ftruncate(descriptor, static_cast<off_t>(bytes)) != 0) {
    const int saved_errno = errno;
    close(descriptor);
    unlink(path.c_str());
    errno = saved_errno;
    throw system_error("size shared trace ring");
  }
  void* mapping = mmap(nullptr, bytes, PROT_READ | PROT_WRITE, MAP_SHARED, descriptor, 0);
  const int saved_errno = errno;
  close(descriptor);
  if (mapping == MAP_FAILED) {
    unlink(path.c_str());
    errno = saved_errno;
    throw system_error("map shared trace ring");
  }
  auto* state = new (mapping) SharedTraceHeader{};
  state->magic = shared_trace_magic;
  state->version = shared_trace_version;
  state->event_bytes = sizeof(TraceEvent);
  state->capacity = capacity;
  return std::unique_ptr<SharedTraceRing>(
      new SharedTraceRing(std::move(path), mapping, bytes, true));
}

std::unique_ptr<SharedTraceRing> SharedTraceRing::open_existing(std::string path) {
  const int descriptor = ::open(path.c_str(), O_RDWR | O_CLOEXEC);
  if (descriptor < 0) throw system_error("open shared trace ring");
  struct stat metadata {};
  if (fstat(descriptor, &metadata) != 0) {
    const int saved_errno = errno;
    close(descriptor);
    errno = saved_errno;
    throw system_error("inspect shared trace ring");
  }
  if (metadata.st_size < static_cast<off_t>(sizeof(SharedTraceHeader))) {
    close(descriptor);
    errno = EINVAL;
    throw system_error("inspect shared trace ring");
  }
  const std::size_t bytes = static_cast<std::size_t>(metadata.st_size);
  void* mapping = mmap(nullptr, bytes, PROT_READ | PROT_WRITE, MAP_SHARED, descriptor, 0);
  const int saved_errno = errno;
  close(descriptor);
  if (mapping == MAP_FAILED) {
    errno = saved_errno;
    throw system_error("map existing shared trace ring");
  }
  const auto* state = header(mapping);
  const bool capacity_valid = state->capacity >= 2 && state->capacity <= 4'194'304 &&
      std::has_single_bit(state->capacity);
  const bool valid = capacity_valid && state->magic == shared_trace_magic &&
      state->version == shared_trace_version && state->event_bytes == sizeof(TraceEvent) &&
      mapping_size(static_cast<std::size_t>(state->capacity)) == bytes;
  if (!valid) {
    munmap(mapping, bytes);
    throw std::runtime_error("shared trace ring header is incompatible");
  }
  return std::unique_ptr<SharedTraceRing>(
      new SharedTraceRing(std::move(path), mapping, bytes, false));
}

SharedTraceRing::~SharedTraceRing() {
  if (mapping_ != nullptr) munmap(mapping_, mapping_bytes_);
  if (owner_ && !path_.empty()) unlink(path_.c_str());
}

bool SharedTraceRing::try_push(const TraceEvent& event) noexcept {
  auto* state = header(mapping_);
  const auto head_value = state->head.load(std::memory_order_relaxed);
  const auto tail_value = state->tail.load(std::memory_order_acquire);
  if (head_value - tail_value >= state->capacity) {
    state->dropped.fetch_add(1, std::memory_order_relaxed);
    return false;
  }
  events(mapping_)[head_value & (state->capacity - 1)] = event;
  state->head.store(head_value + 1, std::memory_order_release);
  return true;
}

bool SharedTraceRing::try_pop(TraceEvent& event) noexcept {
  auto* state = header(mapping_);
  const auto tail_value = state->tail.load(std::memory_order_relaxed);
  const auto head_value = state->head.load(std::memory_order_acquire);
  if (tail_value == head_value) return false;
  event = events(mapping_)[tail_value & (state->capacity - 1)];
  state->tail.store(tail_value + 1, std::memory_order_release);
  return true;
}

std::size_t SharedTraceRing::capacity() const noexcept {
  return static_cast<std::size_t>(header(mapping_)->capacity);
}

std::uint64_t SharedTraceRing::dropped() const noexcept {
  return header(mapping_)->dropped.load(std::memory_order_relaxed);
}

const std::string& SharedTraceRing::path() const noexcept { return path_; }

const char* trace_event_type_name(const TraceEventType type) noexcept {
  switch (type) {
    case TraceEventType::request_admitted: return "request.admitted";
    case TraceEventType::request_finished: return "request.finished";
    case TraceEventType::batch_formed: return "batch.formed";
    case TraceEventType::graph_launch: return "graph.launch";
    case TraceEventType::graph_node: return "graph.node";
    case TraceEventType::kernel_launch: return "kernel.launch";
    case TraceEventType::kv_cache_allocate: return "kv_cache.allocate";
    case TraceEventType::kv_cache_release: return "kv_cache.release";
    case TraceEventType::allocator_pressure: return "allocator.pressure";
    case TraceEventType::runtime_fault: return "runtime.fault";
    case TraceEventType::prefill_batch: return "prefill.batch";
    case TraceEventType::decode_batch: return "decode.batch";
    case TraceEventType::speculative_batch: return "speculative.batch";
    case TraceEventType::request_failed: return "request.failed";
    case TraceEventType::request_cancelled: return "request.cancelled";
  }
  return "unknown";
}

}  // namespace desmond
