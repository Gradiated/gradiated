#pragma once

#include "desmond/mode.h"
#include "desmond/runtime_health.h"

#include <optional>
#include <string_view>

namespace desmond {

enum class DeploymentStatus {
  accepting,
  runtime_unavailable,
  draining,
  metrics_unavailable,
  kv_pressure,
};

[[nodiscard]] bool is_healthy(DeploymentStatus status);
[[nodiscard]] bool accepts_requests(DeploymentStatus status);
[[nodiscard]] std::optional<std::string_view> reason_code(DeploymentStatus status);

[[nodiscard]] DeploymentStatus assess_deployment(RuntimeState runtime, Mode mode,
                                                 std::optional<std::string_view> runtime_metrics,
                                                 double kv_usage_limit);

[[nodiscard]] bool kv_pressure_exceeded(std::string_view prometheus_text, double limit);

} // namespace desmond
