#pragma once

#include "desmond/config.h"

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace desmond {

struct RuntimeLaunch {
  std::vector<std::string> command;
  std::vector<std::string> environment;
};

[[nodiscard]] RuntimeLaunch runtime_launch(const SuperviseRuntime &runtime,
                                           const char *const *inherited_environment,
                                           std::optional<std::string_view> trace_path);

} // namespace desmond
