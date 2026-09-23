#pragma once

#include "desmond/runtime_health.h"
#include "desmond/runtime_identity.h"
#include "desmond/supervised_child.h"

#include <cstdint>
#include <optional>
#include <string>

namespace desmond {

struct TraceCounters {
  std::uint64_t consumed{};
  std::uint64_t dropped{};
};

struct SupervisorMetrics {
  std::optional<SupervisedChild> supervised_child;
  RuntimeState runtime{RuntimeState::unready};
  const RuntimeIdentity &identity;
  bool profiling_enabled{false};
  std::optional<TraceCounters> trace;
};

[[nodiscard]] std::string supervisor_prometheus(const SupervisorMetrics &metrics);

} // namespace desmond
