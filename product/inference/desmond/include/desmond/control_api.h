#pragma once

#include "desmond/http.h"
#include "desmond/mode.h"
#include "desmond/runtime_health.h"
#include "desmond/runtime_identity.h"
#include "desmond/supervised_child.h"

#include <functional>
#include <optional>
#include <string>
#include <string_view>

namespace desmond {

struct ControlContext {
  Mode mode{Mode::supervise};
  RuntimeState runtime{RuntimeState::unready};
  std::optional<SupervisedChild> supervised_child;
  bool reporter_fresh{false};
  const RuntimeIdentity &identity;
  std::string_view control_token;
  std::function<std::string()> desmond_metrics;
  std::function<std::optional<std::string>()> runtime_metrics;
};

[[nodiscard]] HttpResponse handle_control_request(const HttpRequest &request,
                                                  const ControlContext &context);

} // namespace desmond
