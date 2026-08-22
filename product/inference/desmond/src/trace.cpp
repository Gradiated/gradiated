#include "desmond/trace.h"

#include <stdexcept>

namespace desmond {

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

}  // namespace desmond
