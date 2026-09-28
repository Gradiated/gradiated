#include "desmond/config.h"

#include "test_support.h"

#include <fstream>
#include <functional>
#include <map>
#include <string>
#include <vector>

namespace {

using namespace std::chrono_literals;
using desmond::testing::contains;
using desmond::testing::TempDirectory;

using Variables = std::map<std::string, std::string, std::less<>>;
using Arguments = std::vector<const char *>;

const Arguments supervise_sleep{"--", "sleep", "30"};

desmond::DesmondConfig load(const Arguments &arguments, const Variables &variables = {}) {
  return desmond::load_config(arguments, [&](const std::string_view name) {
    const auto found = variables.find(name);
    return found == variables.end() ? std::nullopt : std::optional<std::string_view>(found->second);
  });
}

std::string config_error(const Arguments &arguments, const Variables &variables = {}) {
  try {
    static_cast<void>(load(arguments, variables));
  } catch (const desmond::ConfigError &error) {
    return error.what();
  }
  return {};
}

const Variables profiling_variables{{"DESMOND_PROFILING_HOST", "10.0.0.2"},
                                    {"DESMOND_PROFILING_TOKEN", "profiling-token"},
                                    {"DESMOND_DEPLOYMENT_ID", "deployment"},
                                    {"DESMOND_RELEASE", "release-1"},
                                    {"DESMOND_MODEL", "test/model"}};

Variables observer_variables() {
  return {
      {"DESMOND_DEPLOYMENT_ID", "00000000-0000-4000-8000-000000000001"},
      {"DESMOND_RELEASE", "release-1"},
      {"DESMOND_MODEL", "test/model"},
      {"DESMOND_STATUS_URL", "https://status.example/v1/deployment-status"},
      {"DESMOND_STATUS_TOKEN", "status-token"},
  };
}

std::string write_file(const TempDirectory &directory, const std::string &contents) {
  const auto path = directory.file("token");
  std::ofstream(path) << contents;
  return path;
}

DESMOND_TEST(config_defaults) {
  const auto config = load(supervise_sleep);

  CHECK(config.mode() == desmond::Mode::supervise);
  CHECK(config.control.host == "0.0.0.0" && config.control.port == 9090);
  CHECK(config.runtime_endpoint.host == "127.0.0.1" && config.runtime_endpoint.port == 30000);
  CHECK(config.runtime_health_path == "/health");
  CHECK(config.identity.release == "unknown" && config.identity.model == "unknown" &&
        config.identity.model_revision == "unknown");
  CHECK(config.control_token.empty());
  CHECK(config.kv_usage_limit == 0.90);
  CHECK(!config.status && !config.profiling);
  const auto &runtime = std::get<desmond::SuperviseRuntime>(config.runtime);
  CHECK(runtime.command == std::vector<std::string>({"sleep", "30"}));
  CHECK(!runtime.api_key && !runtime.trace_path);
}

DESMOND_TEST(ingress_health_uses_the_local_allocation_route_and_private_token) {
  auto variables = observer_variables();
  variables["DESMOND_INGRESS_PORT"] = "8888";
  CHECK(contains(config_error({"--observe"}, variables), "control token"));
  variables["DESMOND_CONTROL_TOKEN"] = "synthetic-runtime-token";
  const auto config = load({"--observe"}, variables);
  const auto request = config.health_request();
  CHECK(request.url == "http://127.0.0.1:8888/alloc/00000000-0000-4000-8000-000000000001/health");
  CHECK(request.authorization == "Bearer synthetic-runtime-token");
  CHECK(config.runtime_endpoint.port == 30000);
  variables["DESMOND_INGRESS_PORT"] = "0";
  CHECK(contains(config_error({"--observe"}, variables), "DESMOND_INGRESS_PORT"));
}

DESMOND_TEST(config_treats_empty_variables_as_unset) {
  const auto config = load(supervise_sleep, {{"DESMOND_CONTROL_PORT", ""}, {"DESMOND_MODEL", ""}});

  CHECK(config.control.port == 9090);
  CHECK(config.identity.model == "unknown");
}

DESMOND_TEST(config_accepts_only_observe_or_a_runtime_command) {
  const auto observe = load({"--observe"}, observer_variables());

  CHECK(observe.mode() == desmond::Mode::observe);
  for (const auto &arguments : std::vector<Arguments>{
           {}, {"--"}, {"--observe", "extra"}, {"sleep", "30"}, {"--supervise"}}) {
    CHECK(contains(config_error(arguments), "usage: desmondd"));
  }
}

DESMOND_TEST(config_rejects_invalid_ports_with_the_variable_name) {
  for (const char *name : {"DESMOND_CONTROL_PORT", "DESMOND_RUNTIME_PORT", "DESMOND_STATUS_PORT",
                           "DESMOND_PROFILING_PORT"}) {
    for (const char *value : {"80abc", "0", "65536", "-1", " 80", "port", "99999999999"}) {
      CHECK(contains(config_error(supervise_sleep, {{name, value}}), name));
    }
  }

  CHECK(load(supervise_sleep, {{"DESMOND_CONTROL_PORT", "65535"}}).control.port == 65535);
}

DESMOND_TEST(config_rejects_invalid_kv_usage_limits) {
  for (const char *value : {"nan", "inf", "0", "-0.5", "1.01", "0.9x", "abc"}) {
    CHECK(contains(config_error(supervise_sleep, {{"DESMOND_KV_USAGE_LIMIT", value}}),
                   "DESMOND_KV_USAGE_LIMIT"));
  }

  CHECK(load(supervise_sleep, {{"DESMOND_KV_USAGE_LIMIT", "1"}}).kv_usage_limit == 1.0);
  CHECK(load(supervise_sleep, {{"DESMOND_KV_USAGE_LIMIT", "0.5"}}).kv_usage_limit == 0.5);
}

DESMOND_TEST(config_reads_the_first_token_line_and_strips_a_carriage_return) {
  const TempDirectory directory;
  const auto path = write_file(directory, "file-token\r\nignored\n");

  const auto config = load(
      supervise_sleep, {{"DESMOND_CONTROL_TOKEN", "inline"}, {"DESMOND_CONTROL_TOKEN_FILE", path}});

  CHECK(config.control_token == "file-token");
  CHECK(load(supervise_sleep, {{"DESMOND_CONTROL_TOKEN", "inline"}}).control_token == "inline");
}

DESMOND_TEST(config_rejects_unusable_token_files_with_the_variable_name) {
  const TempDirectory directory;

  for (const auto &contents :
       std::vector<std::string>{"", "\n", "\r\n", "\r", std::string(4097, 't')}) {
    const auto path = write_file(directory, contents);
    for (const char *name : {"DESMOND_CONTROL_TOKEN_FILE", "DESMOND_STATUS_TOKEN_FILE",
                             "DESMOND_PROFILING_TOKEN_FILE"}) {
      CHECK(contains(config_error(supervise_sleep, {{name, path}}), name));
    }
  }
  CHECK(contains(
      config_error(supervise_sleep, {{"DESMOND_CONTROL_TOKEN_FILE", directory.file("missing")}}),
      "DESMOND_CONTROL_TOKEN_FILE"));
}

DESMOND_TEST(config_rejects_an_unknown_api_key_mode_for_a_supervised_runtime) {
  auto observed = observer_variables();
  observed["DESMOND_RUNTIME_API_KEY_MODE"] = "header";

  CHECK(contains(config_error(supervise_sleep, {{"DESMOND_RUNTIME_API_KEY_MODE", "header"}}),
                 "DESMOND_RUNTIME_API_KEY_MODE"));
  CHECK(load({"--observe"}, observed).mode() == desmond::Mode::observe);
}

DESMOND_TEST(supervised_runtime_reads_the_api_key_delivery_and_trace_path) {
  const auto config = load(supervise_sleep, {{"DESMOND_RUNTIME_API_KEY", "runtime-key"},
                                             {"DESMOND_RUNTIME_API_KEY_MODE", "environment"},
                                             {"DESMOND_TRACE_PATH", "/dev/shm/custom"}});

  const auto &runtime = std::get<desmond::SuperviseRuntime>(config.runtime);
  CHECK(runtime.command == std::vector<std::string>({"sleep", "30"}));
  REQUIRE(runtime.api_key);
  CHECK(runtime.api_key->value == "runtime-key");
  CHECK(runtime.api_key->delivery == desmond::ApiKeyDelivery::environment);
  CHECK(runtime.trace_path == "/dev/shm/custom");
}

DESMOND_TEST(supervised_runtime_delivers_the_api_key_as_an_argument_by_default) {
  const auto config = load(supervise_sleep, {{"DESMOND_RUNTIME_API_KEY", "runtime-key"}});

  const auto &runtime = std::get<desmond::SuperviseRuntime>(config.runtime);
  REQUIRE(runtime.api_key);
  CHECK(runtime.api_key->delivery == desmond::ApiKeyDelivery::argument);
}

DESMOND_TEST(config_rejects_a_control_host_that_is_not_an_ipv4_address) {
  for (const char *value : {"localhost", "::1", "10.0.0", "10.0.0.256", " 10.0.0.1"}) {
    CHECK(contains(config_error(supervise_sleep, {{"DESMOND_CONTROL_HOST", value}}),
                   "DESMOND_CONTROL_HOST must be an IPv4 address"));
  }

  CHECK(load(supervise_sleep, {{"DESMOND_CONTROL_HOST", "127.0.0.1"}}).control.host == "127.0.0.1");
}

DESMOND_TEST(config_rejects_url_paths_without_a_leading_slash) {
  auto variables = profiling_variables;
  variables["DESMOND_STATUS_HOST"] = "10.0.0.1";
  variables["DESMOND_STATUS_TOKEN"] = "status-token";
  REQUIRE(load(supervise_sleep, variables).status);

  for (const char *name :
       {"DESMOND_RUNTIME_HEALTH_PATH", "DESMOND_STATUS_PATH", "DESMOND_PROFILING_PATH"}) {
    auto invalid = variables;
    invalid[name] = "health";

    CHECK(
        contains(config_error(supervise_sleep, invalid), std::string(name) + " must start with /"));
  }
}

DESMOND_TEST(status_config_uses_the_https_url_before_the_host) {
  auto variables = observer_variables();
  variables["DESMOND_STATUS_HOST"] = "10.0.0.1";

  const auto config = load(supervise_sleep, variables);

  REQUIRE(config.status);
  CHECK(config.status->url == "https://status.example/v1/deployment-status");
  CHECK(config.status->token == "status-token");
  CHECK(config.status->deployment_id == "00000000-0000-4000-8000-000000000001");
  CHECK(config.status->runtime_revision == "release-1");
}

DESMOND_TEST(status_config_builds_a_private_http_url_from_host_port_and_path) {
  auto variables = observer_variables();
  variables.erase("DESMOND_STATUS_URL");
  variables["DESMOND_STATUS_HOST"] = "10.0.0.1";
  variables["DESMOND_STATUS_PORT"] = "8080";
  variables["DESMOND_STATUS_PATH"] = "/status";

  const auto config = load(supervise_sleep, variables);

  REQUIRE(config.status);
  CHECK(config.status->url == "http://10.0.0.1:8080/status");
}

DESMOND_TEST(status_url_must_use_https) {
  auto variables = observer_variables();
  variables["DESMOND_STATUS_URL"] = "http://status.example/v1/deployment-status";

  CHECK(contains(config_error(supervise_sleep, variables), "DESMOND_STATUS_URL"));
}

DESMOND_TEST(status_config_is_absent_without_an_endpoint) {
  auto without_endpoint = observer_variables();
  without_endpoint.erase("DESMOND_STATUS_URL");

  CHECK(!load(supervise_sleep, without_endpoint).status);
}

DESMOND_TEST(status_endpoint_without_token_or_deployment_is_rejected) {
  auto without_token = observer_variables();
  without_token.erase("DESMOND_STATUS_TOKEN");

  CHECK(contains(config_error(supervise_sleep, without_token), "DESMOND_STATUS_TOKEN_FILE"));
  for (const char *missing : {"DESMOND_DEPLOYMENT_ID", "DESMOND_RELEASE"}) {
    auto partial = observer_variables();
    partial.erase(missing);
    CHECK(contains(config_error(supervise_sleep, partial),
                   std::string("deployment status reporting requires ") + missing));
  }
}

DESMOND_TEST(profiling_config_builds_the_ingest_url_and_identity) {
  const auto config = load(supervise_sleep, profiling_variables);

  REQUIRE(config.profiling);
  CHECK(config.profiling->url == "http://10.0.0.2:80/v1/profiling-events");
  CHECK(config.profiling->token == "profiling-token");
  CHECK(config.profiling->model_id == "test/model");
  CHECK(config.profiling->runtime_revision == "release-1");
}

DESMOND_TEST(profiling_config_reads_the_token_file) {
  const TempDirectory directory;
  auto variables = profiling_variables;
  variables.erase("DESMOND_PROFILING_TOKEN");
  variables["DESMOND_PROFILING_TOKEN_FILE"] = write_file(directory, "file-token\n");

  const auto config = load(supervise_sleep, variables);

  REQUIRE(config.profiling);
  CHECK(config.profiling->token == "file-token");
}

DESMOND_TEST(profiling_is_absent_without_a_host_and_rejected_when_partial) {
  auto without_host = profiling_variables;
  without_host.erase("DESMOND_PROFILING_HOST");
  auto without_token = profiling_variables;
  without_token.erase("DESMOND_PROFILING_TOKEN");

  CHECK(!load(supervise_sleep, without_host).profiling);
  CHECK(contains(config_error(supervise_sleep, without_token), "DESMOND_PROFILING_TOKEN"));
  for (const char *missing : {"DESMOND_DEPLOYMENT_ID", "DESMOND_RELEASE", "DESMOND_MODEL"}) {
    auto partial = profiling_variables;
    partial.erase(missing);
    CHECK(contains(config_error(supervise_sleep, partial),
                   std::string("profiling requires ") + missing));
  }
}

DESMOND_TEST(observe_mode_requires_status_reporting_and_identity) {
  auto without_status = observer_variables();
  without_status.erase("DESMOND_STATUS_URL");

  CHECK(contains(config_error({"--observe"}, without_status), "--observe requires"));
  for (const char *missing : {"DESMOND_RELEASE", "DESMOND_MODEL"}) {
    auto partial = observer_variables();
    partial.erase(missing);
    CHECK(contains(config_error({"--observe"}, partial), missing));
  }
}

} // namespace
