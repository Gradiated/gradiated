#include "desmond/runtime_launch.h"

#include "test_support.h"

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace {

using desmond::ApiKeyDelivery;
using Strings = std::vector<std::string>;

desmond::RuntimeLaunch launch(const desmond::SuperviseRuntime &runtime,
                              std::vector<const char *> inherited,
                              const std::optional<std::string_view> trace_path = std::nullopt) {
  inherited.push_back(nullptr);
  return desmond::runtime_launch(runtime, inherited.data(), trace_path);
}

const desmond::SuperviseRuntime sleep_runtime{.command = {"sleep", "30"}};

DESMOND_TEST(runtime_launch_withholds_desmond_credentials) {
  const auto launched = launch(
      sleep_runtime, {"PATH=/bin", "DESMOND_CONTROL_TOKEN=a", "DESMOND_CONTROL_TOKEN_FILE=/a",
                      "DESMOND_STATUS_TOKEN=b", "DESMOND_STATUS_TOKEN_FILE=/b",
                      "DESMOND_PROFILING_TOKEN=c", "DESMOND_PROFILING_TOKEN_FILE=/c",
                      "DESMOND_RELEASE=r", "HF_TOKEN=kept"});

  CHECK(launched.command == Strings({"sleep", "30"}));
  CHECK(launched.environment == Strings({"PATH=/bin", "DESMOND_RELEASE=r", "HF_TOKEN=kept"}));
}

DESMOND_TEST(argument_delivery_appends_the_api_key_to_the_command_only) {
  auto runtime = sleep_runtime;
  runtime.api_key = {{.value = "runtime-key", .delivery = ApiKeyDelivery::argument}};

  const auto launched = launch(runtime, {"DESMOND_RUNTIME_API_KEY=runtime-key"});

  CHECK(launched.command == Strings({"sleep", "30", "--api-key", "runtime-key"}));
  CHECK(launched.environment.empty());
}

DESMOND_TEST(environment_delivery_passes_the_api_key_in_the_environment_only) {
  auto runtime = sleep_runtime;
  runtime.api_key = {{.value = "runtime-key", .delivery = ApiKeyDelivery::environment}};

  const auto launched = launch(runtime, {"DESMOND_RUNTIME_API_KEY=runtime-key"});

  CHECK(launched.command == Strings({"sleep", "30"}));
  CHECK(launched.environment == Strings({"DESMOND_RUNTIME_API_KEY=runtime-key"}));
}

DESMOND_TEST(runtime_launch_sets_the_trace_path_only_when_the_ring_exists) {
  const std::vector<const char *> inherited{"DESMOND_TRACE_PATH=/stale"};

  CHECK(launch(sleep_runtime, inherited).environment.empty());
  CHECK(launch(sleep_runtime, inherited, "/dev/shm/ring").environment ==
        Strings({"DESMOND_TRACE_PATH=/dev/shm/ring"}));
}

} // namespace
