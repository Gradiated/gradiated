#include "desmond/deployment_status.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <string>

namespace desmond {
namespace {

constexpr std::array<std::string_view, 4> kv_usage_metrics{
    "vllm:kv_cache_usage_perc",
    "vllm_kv_cache_usage_perc",
    "vllm:gpu_cache_usage_perc",
    "vllm_gpu_cache_usage_perc",
};

std::size_t end_of_labels(const std::string_view line, const std::size_t open_brace) {
  bool quoted = false;
  for (std::size_t index = open_brace + 1; index < line.size(); ++index) {
    if (quoted && line[index] == '\\') {
      ++index;
    } else if (line[index] == '"') {
      quoted = !quoted;
    } else if (!quoted && line[index] == '}') {
      return index + 1;
    }
  }

  return std::string_view::npos;
}

std::optional<double> sample_value(const std::string_view line) {
  const auto name_end = line.find_first_of(" \t{");
  if (name_end == std::string_view::npos) {
    return std::nullopt;
  }

  const auto after_name = line[name_end] == '{' ? end_of_labels(line, name_end) : name_end;
  const auto value_start = line.find_first_not_of(" \t", after_name);
  if (after_name == std::string_view::npos || value_start == std::string_view::npos) {
    return std::nullopt;
  }

  const auto value_end = std::min(line.find_first_of(" \t", value_start), line.size());
  const std::string token(line.substr(value_start, value_end - value_start));
  char *parsed_end = nullptr;
  const double value = std::strtod(token.c_str(), &parsed_end);
  if (parsed_end != token.c_str() + token.size() || !std::isfinite(value)) {
    return std::nullopt;
  }

  return value;
}

bool is_kv_usage_sample(const std::string_view line) {
  const auto name = line.substr(0, line.find_first_of(" \t{"));
  return std::find(kv_usage_metrics.begin(), kv_usage_metrics.end(), name) !=
         kv_usage_metrics.end();
}

} // namespace

bool is_healthy(const DeploymentStatus status) {
  switch (status) {
  case DeploymentStatus::runtime_unavailable:
  case DeploymentStatus::draining:
    return false;
  case DeploymentStatus::accepting:
  case DeploymentStatus::metrics_unavailable:
  case DeploymentStatus::kv_pressure:
    return true;
  }

  return false;
}

bool accepts_requests(const DeploymentStatus status) {
  return status == DeploymentStatus::accepting;
}

std::optional<std::string_view> reason_code(const DeploymentStatus status) {
  switch (status) {
  case DeploymentStatus::accepting:
    return std::nullopt;
  case DeploymentStatus::runtime_unavailable:
    return "runtime_unavailable";
  case DeploymentStatus::draining:
    return "draining";
  case DeploymentStatus::metrics_unavailable:
    return "metrics_unavailable";
  case DeploymentStatus::kv_pressure:
    return "kv_pressure";
  }

  return "runtime_unavailable";
}

DeploymentStatus assess_deployment(const RuntimeState runtime, const Mode mode,
                                   const std::optional<std::string_view> runtime_metrics,
                                   const double kv_usage_limit) {
  switch (runtime) {
  case RuntimeState::unready:
    return DeploymentStatus::runtime_unavailable;
  case RuntimeState::draining:
    return DeploymentStatus::draining;
  case RuntimeState::ready:
    break;
  }

  if (!runtime_metrics) {
    return mode == Mode::observe ? DeploymentStatus::metrics_unavailable
                                 : DeploymentStatus::accepting;
  }
  if (kv_pressure_exceeded(*runtime_metrics, kv_usage_limit)) {
    return DeploymentStatus::kv_pressure;
  }

  return DeploymentStatus::accepting;
}

bool kv_pressure_exceeded(const std::string_view prometheus_text, const double limit) {
  std::size_t offset = 0;
  while (offset < prometheus_text.size()) {
    const auto line_end = std::min(prometheus_text.find('\n', offset), prometheus_text.size());
    const auto line = prometheus_text.substr(offset, line_end - offset);
    offset = line_end + 1;

    if (!is_kv_usage_sample(line)) {
      continue;
    }

    const auto value = sample_value(line);
    if (value && *value >= limit) {
      return true;
    }
  }

  return false;
}

} // namespace desmond
