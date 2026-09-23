#pragma once

#include "desmond/mode.h"
#include "desmond/profiling.h"
#include "desmond/runtime_identity.h"
#include "desmond/status_reporter.h"

#include <cstdint>
#include <functional>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

namespace desmond {

using Environment = std::function<std::optional<std::string_view>(std::string_view name)>;

class ConfigError : public std::runtime_error {
public:
  using std::runtime_error::runtime_error;
};

enum class ApiKeyDelivery { argument, environment };

struct RuntimeApiKey {
  std::string value;
  ApiKeyDelivery delivery{ApiKeyDelivery::argument};
};

struct SuperviseRuntime {
  std::vector<std::string> command;
  std::optional<RuntimeApiKey> api_key;
  std::optional<std::string> trace_path;
};

struct ObserveRuntime {};

struct Endpoint {
  std::string host;
  std::uint16_t port{};
};

struct DesmondConfig {
  std::variant<SuperviseRuntime, ObserveRuntime> runtime;
  Endpoint control;
  Endpoint runtime_endpoint;
  std::string runtime_health_path;
  RuntimeIdentity identity;
  std::string control_token;
  double kv_usage_limit{};
  std::optional<StatusReporterConfig> status;
  std::optional<ProfilingUploaderConfig> profiling;

  [[nodiscard]] Mode mode() const;
};

[[nodiscard]] DesmondConfig load_config(std::span<const char *const> arguments,
                                        const Environment &environment);

} // namespace desmond
