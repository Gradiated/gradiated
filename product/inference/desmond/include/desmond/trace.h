#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>

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

class TraceRing {
 public:
  explicit TraceRing(std::size_t capacity);
  TraceRing(const TraceRing&) = delete;
  TraceRing& operator=(const TraceRing&) = delete;

  [[nodiscard]] bool try_push(const TraceEvent& event) noexcept;
  [[nodiscard]] bool try_pop(TraceEvent& event) noexcept;
  [[nodiscard]] std::size_t capacity() const noexcept;
  [[nodiscard]] std::uint64_t dropped() const noexcept;

 private:
  std::size_t capacity_;
  std::unique_ptr<TraceEvent[]> events_;
  alignas(64) std::atomic<std::uint64_t> head_{0};
  alignas(64) std::atomic<std::uint64_t> tail_{0};
  std::atomic<std::uint64_t> dropped_{0};
};

}  // namespace desmond
