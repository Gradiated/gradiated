#include "desmond/supervisor_metrics.h"

#include "test_support.h"

#include <string>

namespace {

using desmond::ChildState;
using desmond::RuntimeState;
using desmond::testing::contains;

const desmond::RuntimeIdentity identity{
    .release = "release-1",
    .model = "model \"q\" \\ \n",
    .model_revision = "rev",
};

DESMOND_TEST(supervisor_metrics_pin_names_types_and_values) {
  const auto text = desmond::supervisor_prometheus({
      .supervised_child = desmond::SupervisedChild{.pid = 42, .state = ChildState::running},
      .runtime = RuntimeState::ready,
      .identity = identity,
      .profiling_enabled = true,
      .trace = desmond::TraceCounters{.consumed = 7, .dropped = 2},
  });

  CHECK(text == "# TYPE desmond_runtime_running gauge\n"
                "desmond_runtime_running 1\n"
                "# TYPE desmond_runtime_ready gauge\n"
                "desmond_runtime_ready 1\n"
                "# TYPE desmond_runtime_starts_total counter\n"
                "desmond_runtime_starts_total 1\n"
                "# TYPE desmond_runtime_unexpected_exits_total counter\n"
                "desmond_runtime_unexpected_exits_total 0\n"
                "# TYPE desmond_release_info gauge\n"
                "desmond_release_info{release=\"release-1\",model=\"model \\\"q\\\" \\\\ \\n\","
                "model_revision=\"rev\"} 1\n"
                "# TYPE desmond_profiling_enabled gauge\n"
                "desmond_profiling_enabled 1\n"
                "# TYPE desmond_trace_enabled gauge\n"
                "desmond_trace_enabled 1\n"
                "# TYPE desmond_trace_consumed_events_total counter\n"
                "desmond_trace_consumed_events_total 7\n"
                "# TYPE desmond_trace_dropped_events_total counter\n"
                "desmond_trace_dropped_events_total 2\n");
}

DESMOND_TEST(observer_metrics_report_no_runtime_process_or_trace) {
  const auto text = desmond::supervisor_prometheus({
      .supervised_child = std::nullopt,
      .runtime = RuntimeState::draining,
      .identity = identity,
      .profiling_enabled = false,
      .trace = std::nullopt,
  });

  CHECK(contains(text, "desmond_runtime_running 0\n"));
  CHECK(contains(text, "desmond_runtime_ready 0\n"));
  CHECK(contains(text, "desmond_runtime_starts_total 0\n"));
  CHECK(contains(text, "desmond_trace_enabled 0\n"));
  CHECK(contains(text, "desmond_trace_consumed_events_total 0\n"));
}

DESMOND_TEST(unexpected_runtime_exit_is_counted_and_not_running) {
  const auto text = desmond::supervisor_prometheus({
      .supervised_child =
          desmond::SupervisedChild{.pid = 42, .state = ChildState::exited_unexpectedly},
      .runtime = RuntimeState::draining,
      .identity = identity,
  });

  CHECK(contains(text, "desmond_runtime_running 0\n"));
  CHECK(contains(text, "desmond_runtime_unexpected_exits_total 1\n"));
}

} // namespace
