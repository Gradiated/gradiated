#include "desmond/runtime_metrics.h"

#include "test_support.h"

#include <chrono>
#include <cstdint>
#include <sstream>

namespace {

using namespace std::chrono_literals;
using desmond::testing::closed_port;
using desmond::testing::local_url;
using desmond::testing::respond_with;
using desmond::testing::TestHttpServer;

desmond::RuntimeMetricsSource source(const std::uint16_t port) {
  return {
      .url = local_url(port, "/metrics"),
      .timeout = 1s,
      .log_subject = "runtime metrics fetch",
  };
}

DESMOND_TEST(runtime_metrics_returns_the_exposition_body) {
  const TestHttpServer runtime(respond_with(200, "vllm:num_requests_running 0\n"));
  std::ostringstream log;
  desmond::RuntimeMetrics metrics(source(runtime.port()), log);

  CHECK(metrics.fetch() == "vllm:num_requests_running 0\n");
  CHECK(log.str().empty());
}

DESMOND_TEST(failed_runtime_metrics_fetch_is_empty_and_logs_the_status) {
  const TestHttpServer runtime(respond_with(503, "loading"));
  std::ostringstream log;
  desmond::RuntimeMetrics metrics(source(runtime.port()), log);

  CHECK(!metrics.fetch());
  CHECK(!metrics.fetch());
  CHECK(log.str() == "desmond: runtime metrics fetch failed cause=http_status=503\n");
}

DESMOND_TEST(unreachable_runtime_metrics_logs_connect) {
  std::ostringstream log;
  desmond::RuntimeMetrics metrics(source(closed_port()), log);

  CHECK(!metrics.fetch());
  CHECK(log.str() == "desmond: runtime metrics fetch failed cause=connect\n");
}

} // namespace
