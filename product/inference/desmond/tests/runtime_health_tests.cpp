#include "desmond/runtime_health.h"

#include "test_support.h"

#include <sstream>

namespace {

using desmond::RuntimeState;
using desmond::testing::closed_port;
using desmond::testing::local_url;
using desmond::testing::RecordingServer;

DESMOND_TEST(runtime_is_ready_only_while_the_health_endpoint_succeeds) {
  RecordingServer runtime;
  std::ostringstream log;
  desmond::RuntimeHealth health(local_url(runtime.port(), "/health"), log);

  health.check();
  const auto healthy = health.state();
  runtime.respond_with(503);
  health.check();

  CHECK(healthy == RuntimeState::ready);
  CHECK(health.state() == RuntimeState::unready);
}

DESMOND_TEST(runtime_health_logs_each_transition_with_its_cause) {
  RecordingServer runtime;
  runtime.respond_in_sequence({503, 503, 200});
  std::ostringstream log;
  desmond::RuntimeHealth health(local_url(runtime.port(), "/health"), log);

  for (int check = 0; check < 3; ++check) {
    health.check();
  }

  CHECK(log.str() == "desmond: runtime health check failed cause=http_status=503\n"
                     "desmond: runtime health check recovered\n");
}

DESMOND_TEST(unreachable_health_endpoint_is_not_ready_and_logs_connect) {
  std::ostringstream log;
  desmond::RuntimeHealth health(local_url(closed_port(), "/health"), log);

  health.check();

  CHECK(health.state() == RuntimeState::unready);
  CHECK(log.str() == "desmond: runtime health check failed cause=connect\n");
}

DESMOND_TEST(draining_runtime_is_never_ready) {
  RecordingServer runtime;
  std::ostringstream log;
  desmond::RuntimeHealth health(local_url(runtime.port(), "/health"), log);
  health.check();

  health.start_draining();
  health.check();

  CHECK(health.state() == RuntimeState::draining);
}

} // namespace
