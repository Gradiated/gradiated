#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>

namespace desmond {

enum class TraceEventType : std::uint16_t {
  request_admitted = 1,
  request_finished = 2,
  batch_formed = 3,
  graph_launch = 4,
  graph_node = 5,
  kernel_launch = 6,
  kv_cache_allocate = 7,
  kv_cache_release = 8,
  allocator_pressure = 9,
  runtime_fault = 10,
  prefill_batch = 11,
  decode_batch = 12,
  speculative_batch = 13,
  request_failed = 14,
  request_cancelled = 15,
};

struct TraceEvent {
  std::uint64_t monotonic_ns{};
  std::uint64_t request_id_high{};
  std::uint64_t request_id_low{};
  std::uint64_t batch_id{};
  std::uint64_t graph_execution_id{};
  std::uint64_t graph_node_id{};
  std::uint64_t value0{};
  std::uint64_t value1{};
  std::uint32_t stream_id{};
  std::uint16_t device_id{};
  TraceEventType type{};
};

// Fixed-size single-producer/single-consumer ring shared between desmondd and its
// supervised runtime. The producer never allocates, locks, or performs I/O on the
// inference path; a full ring drops the event instead of applying backpressure.
class SharedTraceRing {
public:
  static std::unique_ptr<SharedTraceRing> create(std::string path, std::size_t capacity);
  static std::unique_ptr<SharedTraceRing> open_existing(std::string path);
  ~SharedTraceRing();
  SharedTraceRing(const SharedTraceRing &) = delete;
  SharedTraceRing &operator=(const SharedTraceRing &) = delete;

  [[nodiscard]] bool try_push(const TraceEvent &event) noexcept;
  [[nodiscard]] bool try_pop(TraceEvent &event) noexcept;
  [[nodiscard]] std::uint64_t dropped() const noexcept;

private:
  SharedTraceRing(std::string path, void *mapping, std::size_t mapping_bytes,
                  std::uint64_t capacity, bool owner) noexcept;

  std::string path_;
  void *mapping_;
  std::size_t mapping_bytes_;
  std::uint64_t mask_;
  bool owner_;
};

[[nodiscard]] const char *trace_event_type_name(TraceEventType type) noexcept;

} // namespace desmond
