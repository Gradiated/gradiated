#include "desmond/runtime_metrics.h"

#include <utility>
#include <variant>

namespace desmond {

RuntimeMetrics::RuntimeMetrics(RuntimeMetricsSource source, std::ostream &log)
    : url_(std::move(source.url)), timeout_(source.timeout),
      failure_log_(std::move(source.log_subject), log) {}

std::optional<std::string> RuntimeMetrics::fetch() {
  auto result =
      http_request({.url = url_, .timeout = timeout_, .max_response_bytes = 8 * 1024 * 1024});
  {
    std::lock_guard lock(log_mutex_);
    failure_log_.record(result);
  }

  if (!succeeded(result)) {
    return std::nullopt;
  }

  return std::move(std::get<HttpReply>(result).body);
}

} // namespace desmond
