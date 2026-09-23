#include "desmond/runtime_launch.h"

namespace desmond {
namespace {

constexpr std::string_view api_key_variable = "DESMOND_RUNTIME_API_KEY";
constexpr std::string_view trace_path_variable = "DESMOND_TRACE_PATH";

bool withheld_from_runtime(const std::string_view name) {
  const bool desmond_credential = name.starts_with("DESMOND_") &&
                                  (name.ends_with("_TOKEN") || name.ends_with("_TOKEN_FILE"));
  return desmond_credential || name == api_key_variable || name == trace_path_variable;
}

std::string assignment(const std::string_view name, const std::string_view value) {
  return std::string(name) + '=' + std::string(value);
}

} // namespace

RuntimeLaunch runtime_launch(const SuperviseRuntime &runtime,
                             const char *const *inherited_environment,
                             const std::optional<std::string_view> trace_path) {
  RuntimeLaunch launch{.command = runtime.command, .environment = {}};
  for (const char *const *entry = inherited_environment; *entry != nullptr; ++entry) {
    const std::string_view variable(*entry);
    if (!withheld_from_runtime(variable.substr(0, variable.find('=')))) {
      launch.environment.emplace_back(variable);
    }
  }

  if (runtime.api_key) {
    switch (runtime.api_key->delivery) {
    case ApiKeyDelivery::argument:
      launch.command.emplace_back("--api-key");
      launch.command.push_back(runtime.api_key->value);
      break;
    case ApiKeyDelivery::environment:
      launch.environment.push_back(assignment(api_key_variable, runtime.api_key->value));
      break;
    }
  }
  if (trace_path) {
    launch.environment.push_back(assignment(trace_path_variable, *trace_path));
  }

  return launch;
}

} // namespace desmond
