#include "desmond/control_api.h"

#include "desmond/json.h"

#include <algorithm>

namespace desmond {
namespace {

constexpr const char *plain_text = "text/plain; charset=utf-8";

bool constant_time_equal(const std::string_view left, const std::string_view right) {
  unsigned char difference = left.size() == right.size() ? 0 : 1;
  for (std::size_t index = 0; index < std::max(left.size(), right.size()); ++index) {
    const auto a = index < left.size() ? static_cast<unsigned char>(left[index]) : 0U;
    const auto b = index < right.size() ? static_cast<unsigned char>(right[index]) : 0U;
    difference = static_cast<unsigned char>(difference | (a ^ b));
  }

  return difference == 0;
}

bool authorized(const HttpRequest &request, const std::string_view control_token) {
  if (control_token.empty()) {
    return true;
  }

  return constant_time_equal(request.authorization, "Bearer " + std::string(control_token));
}

bool control_ready(const ControlContext &context) {
  const bool observing = context.mode == Mode::observe;
  return context.runtime == RuntimeState::ready && (!observing || context.reporter_fresh);
}

HttpResponse metrics(const ControlContext &context) {
  auto body = context.desmond_metrics();
  if (const auto upstream = context.runtime_metrics()) {
    body += "\n# runtime metrics\n" + *upstream;
  }

  return {200, "text/plain; version=0.0.4; charset=utf-8", std::move(body)};
}

HttpResponse status(const ControlContext &context) {
  const auto &child = context.supervised_child;
  const bool running = child_running(child);

  JsonObjectWriter body;
  body.field("child_running", running)
      .field("runtime_ready", context.runtime == RuntimeState::ready)
      .field("draining", context.runtime == RuntimeState::draining);
  if (running) {
    body.field("pid", child->pid);
  }

  body.field("starts", runtime_starts(child))
      .field("unexpected_exits", unexpected_exits(child))
      .field("release", context.identity.release)
      .field("model", context.identity.model)
      .field("model_revision", context.identity.model_revision);

  return {200, "application/json", body.str() + "\n"};
}

} // namespace

HttpResponse handle_control_request(const HttpRequest &request, const ControlContext &context) {
  if (request.method != "GET") {
    return {405, plain_text, "method not allowed\n"};
  }

  if (request.path == "/health/live") {
    return {200, plain_text, "ok\n"};
  }
  if (request.path == "/health/ready" || request.path == "/health") {
    const bool ready = control_ready(context);
    return {ready ? 200 : 503, plain_text, ready ? "ready\n" : "not ready\n"};
  }
  if (request.path == "/metrics") {
    return metrics(context);
  }
  if (request.path == "/v1/desmond/status") {
    if (!authorized(request, context.control_token)) {
      return {401, "application/json", "{\"error\":\"unauthorized\"}\n"};
    }

    return status(context);
  }

  return {404, plain_text, "not found\n"};
}

} // namespace desmond
