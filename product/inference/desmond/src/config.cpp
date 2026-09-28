#include "desmond/config.h"

#include "desmond/http_client.h"

#include <arpa/inet.h>
#include <netinet/in.h>

#include <charconv>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <utility>

namespace desmond {
namespace {

constexpr std::size_t maximum_token_bytes = 4096;

std::optional<std::string> value_of(const Environment &environment, const std::string_view name) {
  const auto value = environment(name);
  if (!value || value->empty()) {
    return std::nullopt;
  }

  return std::string(*value);
}

std::string text(const Environment &environment, const std::string_view name,
                 const std::string_view fallback) {
  return value_of(environment, name).value_or(std::string(fallback));
}

std::string named(const std::string_view name, const std::string_view problem) {
  return std::string(name) + ' ' + std::string(problem);
}

std::string ipv4_address(const Environment &environment, const std::string_view name,
                         const std::string_view fallback) {
  auto address = text(environment, name, fallback);
  in_addr parsed{};
  if (inet_pton(AF_INET, address.c_str(), &parsed) != 1) {
    throw ConfigError(named(name, "must be an IPv4 address"));
  }

  return address;
}

std::string url_path(const Environment &environment, const std::string_view name,
                     const std::string_view fallback) {
  auto path = text(environment, name, fallback);
  if (!path.starts_with('/')) {
    throw ConfigError(named(name, "must start with /"));
  }

  return path;
}

std::uint16_t port(const Environment &environment, const std::string_view name,
                   const std::uint16_t fallback) {
  const auto value = value_of(environment, name);
  if (!value) {
    return fallback;
  }

  std::uint32_t parsed = 0;
  const auto [end, error] = std::from_chars(value->data(), value->data() + value->size(), parsed);
  if (error != std::errc{} || end != value->data() + value->size() || parsed == 0 ||
      parsed > 65535) {
    throw ConfigError(named(name, "must be an integer from 1 to 65535"));
  }

  return static_cast<std::uint16_t>(parsed);
}

double fraction(const Environment &environment, const std::string_view name,
                const double fallback) {
  const auto value = value_of(environment, name);
  if (!value) {
    return fallback;
  }

  char *end = nullptr;
  const double parsed = std::strtod(value->c_str(), &end);
  if (end != value->c_str() + value->size() || !std::isfinite(parsed) || parsed <= 0.0 ||
      parsed > 1.0) {
    throw ConfigError(named(name, "must be a number greater than 0 and at most 1"));
  }

  return parsed;
}

std::string read_token(const Environment &environment, const std::string_view name,
                       const std::string_view file_name) {
  const auto path = value_of(environment, file_name);
  if (!path) {
    return text(environment, name, "");
  }

  std::ifstream file(*path);
  std::string token;
  if (!file || !std::getline(file, token)) {
    throw ConfigError(named(file_name, "could not be read"));
  }

  if (token.ends_with('\r')) {
    token.pop_back();
  }
  if (token.empty()) {
    throw ConfigError(named(file_name, "holds an empty token"));
  }
  if (token.size() > maximum_token_bytes) {
    throw ConfigError(named(file_name, "holds a token over 4096 bytes"));
  }

  return token;
}

ApiKeyDelivery api_key_delivery(const Environment &environment) {
  const auto mode = text(environment, "DESMOND_RUNTIME_API_KEY_MODE", "argument");
  if (mode == "argument") {
    return ApiKeyDelivery::argument;
  }
  if (mode == "environment") {
    return ApiKeyDelivery::environment;
  }

  throw ConfigError("DESMOND_RUNTIME_API_KEY_MODE must be argument or environment");
}

std::optional<RuntimeApiKey> runtime_api_key(const Environment &environment) {
  auto value = value_of(environment, "DESMOND_RUNTIME_API_KEY");
  const auto delivery = api_key_delivery(environment);
  if (!value) {
    return std::nullopt;
  }

  return RuntimeApiKey{.value = std::move(*value), .delivery = delivery};
}

SuperviseRuntime supervise_runtime(const std::span<const char *const> command,
                                   const Environment &environment) {
  return {
      .command = {command.begin(), command.end()},
      .api_key = runtime_api_key(environment),
      .trace_path = value_of(environment, "DESMOND_TRACE_PATH"),
  };
}

std::variant<SuperviseRuntime, ObserveRuntime>
runtime_mode(const std::span<const char *const> arguments, const Environment &environment) {
  if (arguments.size() == 1 && std::string_view(arguments[0]) == "--observe") {
    return ObserveRuntime{};
  }
  if (arguments.size() >= 2 && std::string_view(arguments[0]) == "--") {
    return supervise_runtime(arguments.subspan(1), environment);
  }

  throw ConfigError("usage: desmondd --observe | -- <runtime> [arguments...]");
}

std::optional<std::string> status_url(const Environment &environment) {
  const auto port_number = port(environment, "DESMOND_STATUS_PORT", 80);
  if (const auto url = value_of(environment, "DESMOND_STATUS_URL")) {
    if (!url->starts_with("https://")) {
      throw ConfigError("DESMOND_STATUS_URL must use https");
    }

    return url;
  }

  const auto host = value_of(environment, "DESMOND_STATUS_HOST");
  if (!host) {
    return std::nullopt;
  }

  return http_url(*host, port_number,
                  url_path(environment, "DESMOND_STATUS_PATH", "/v1/deployment-status"));
}

std::string required_token(std::string token, const std::string_view feature,
                           const std::string_view name, const std::string_view file_name) {
  if (token.empty()) {
    throw ConfigError(std::string(feature) + " requires " + std::string(name) + " or " +
                      std::string(file_name));
  }

  return token;
}

std::string required(const Environment &environment, const std::string_view feature,
                     const std::string_view name) {
  auto value = value_of(environment, name);
  if (!value) {
    throw ConfigError(std::string(feature) + " requires " + std::string(name));
  }

  return std::move(*value);
}

std::optional<StatusReporterConfig> status_config(const Environment &environment) {
  constexpr std::string_view feature = "deployment status reporting";
  const auto url = status_url(environment);
  auto token = read_token(environment, "DESMOND_STATUS_TOKEN", "DESMOND_STATUS_TOKEN_FILE");
  if (!url) {
    return std::nullopt;
  }

  return StatusReporterConfig{
      .url = *url,
      .token = required_token(std::move(token), feature, "DESMOND_STATUS_TOKEN",
                              "DESMOND_STATUS_TOKEN_FILE"),
      .deployment_id = required(environment, feature, "DESMOND_DEPLOYMENT_ID"),
      .runtime_revision = required(environment, feature, "DESMOND_RELEASE"),
  };
}

std::optional<ProfilingUploaderConfig> profiling_config(const Environment &environment) {
  constexpr std::string_view feature = "profiling";
  const auto port_number = port(environment, "DESMOND_PROFILING_PORT", 80);
  const auto host = value_of(environment, "DESMOND_PROFILING_HOST");
  auto token = read_token(environment, "DESMOND_PROFILING_TOKEN", "DESMOND_PROFILING_TOKEN_FILE");
  if (!host) {
    return std::nullopt;
  }

  return ProfilingUploaderConfig{
      .url = http_url(*host, port_number,
                      url_path(environment, "DESMOND_PROFILING_PATH", "/v1/profiling-events")),
      .token = required_token(std::move(token), feature, "DESMOND_PROFILING_TOKEN",
                              "DESMOND_PROFILING_TOKEN_FILE"),
      .deployment_id = required(environment, feature, "DESMOND_DEPLOYMENT_ID"),
      .model_id = required(environment, feature, "DESMOND_MODEL"),
      .runtime_revision = required(environment, feature, "DESMOND_RELEASE"),
  };
}

} // namespace

Mode DesmondConfig::mode() const {
  return std::holds_alternative<ObserveRuntime>(runtime) ? Mode::observe : Mode::supervise;
}

HttpRequestSpec DesmondConfig::health_request() const {
  if (ingress_port) {
    return {.url = http_url("127.0.0.1", *ingress_port,
                            "/alloc/" + status->deployment_id + runtime_health_path),
            .authorization = "Bearer " + control_token};
  }
  return {.url = http_url(runtime_endpoint.host, runtime_endpoint.port, runtime_health_path)};
}

DesmondConfig load_config(const std::span<const char *const> arguments,
                          const Environment &environment) {
  DesmondConfig config{
      .runtime = runtime_mode(arguments, environment),
      .control = {ipv4_address(environment, "DESMOND_CONTROL_HOST", "0.0.0.0"),
                  port(environment, "DESMOND_CONTROL_PORT", 9090)},
      .runtime_endpoint = {text(environment, "DESMOND_RUNTIME_HOST", "127.0.0.1"),
                           port(environment, "DESMOND_RUNTIME_PORT", 30000)},
      .runtime_health_path = url_path(environment, "DESMOND_RUNTIME_HEALTH_PATH", "/health"),
      .identity = {text(environment, "DESMOND_RELEASE", "unknown"),
                   text(environment, "DESMOND_MODEL", "unknown"),
                   text(environment, "DESMOND_MODEL_REVISION", "unknown")},
      .control_token =
          read_token(environment, "DESMOND_CONTROL_TOKEN", "DESMOND_CONTROL_TOKEN_FILE"),
      .kv_usage_limit = fraction(environment, "DESMOND_KV_USAGE_LIMIT", 0.90),
  };

  config.status = status_config(environment);
  config.profiling = profiling_config(environment);

  if (config.mode() == Mode::observe) {
    if (!config.status) {
      throw ConfigError("--observe requires DESMOND_STATUS_URL or DESMOND_STATUS_HOST");
    }
    if (!value_of(environment, "DESMOND_MODEL")) {
      throw ConfigError("--observe requires DESMOND_MODEL");
    }
  }

  if (value_of(environment, "DESMOND_INGRESS_PORT")) {
    if (config.mode() != Mode::observe || !config.status || config.control_token.empty()) {
      throw ConfigError(
          "DESMOND_INGRESS_PORT requires observe mode, status reporting and a control token");
    }
    config.ingress_port = port(environment, "DESMOND_INGRESS_PORT", 8888);
  }

  return config;
}

} // namespace desmond
