#include "desmond/runtime_health.h"

#include <utility>

namespace desmond {

RuntimeHealth::RuntimeHealth(HttpRequestSpec request, std::ostream &log)
    : request_(std::move(request)), failure_log_("runtime health check", log) {}

void RuntimeHealth::check() {
  const auto result = http_request(request_);
  failure_log_.record(result);

  std::lock_guard lock(mutex_);
  if (state_ != RuntimeState::draining) {
    state_ = succeeded(result) ? RuntimeState::ready : RuntimeState::unready;
  }
}

void RuntimeHealth::start_draining() {
  std::lock_guard lock(mutex_);
  state_ = RuntimeState::draining;
}

RuntimeState RuntimeHealth::state() const {
  std::lock_guard lock(mutex_);
  return state_;
}

} // namespace desmond
