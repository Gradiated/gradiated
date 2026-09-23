#include "desmond/supervisor_metrics.h"

#include "desmond/prometheus.h"

#include <sstream>

namespace desmond {

std::string supervisor_prometheus(const SupervisorMetrics &metrics) {
  using prometheus::MetricType;
  const auto &child = metrics.supervised_child;
  const auto &identity = metrics.identity;
  const auto trace = metrics.trace.value_or(TraceCounters{});

  std::ostringstream output;
  prometheus::write_metric(output, "desmond_runtime_running", MetricType::gauge,
                           child_running(child) ? 1 : 0);
  prometheus::write_metric(output, "desmond_runtime_ready", MetricType::gauge,
                           metrics.runtime == RuntimeState::ready ? 1 : 0);
  prometheus::write_metric(output, "desmond_runtime_starts_total", MetricType::counter,
                           runtime_starts(child));
  prometheus::write_metric(output, "desmond_runtime_unexpected_exits_total", MetricType::counter,
                           unexpected_exits(child));

  prometheus::write_type(output, "desmond_release_info", MetricType::gauge);
  output << "desmond_release_info{release=\"" << prometheus::label_value(identity.release)
         << "\",model=\"" << prometheus::label_value(identity.model) << "\",model_revision=\""
         << prometheus::label_value(identity.model_revision) << "\"} 1\n";

  prometheus::write_metric(output, "desmond_profiling_enabled", MetricType::gauge,
                           metrics.profiling_enabled ? 1 : 0);
  prometheus::write_metric(output, "desmond_trace_enabled", MetricType::gauge,
                           metrics.trace ? 1 : 0);
  prometheus::write_metric(output, "desmond_trace_consumed_events_total", MetricType::counter,
                           trace.consumed);
  prometheus::write_metric(output, "desmond_trace_dropped_events_total", MetricType::counter,
                           trace.dropped);
  return output.str();
}

} // namespace desmond
