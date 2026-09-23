#pragma once

#include "desmond/http_client.h"

#include <chrono>
#include <mutex>
#include <optional>
#include <ostream>
#include <string>

namespace desmond {

struct RuntimeMetricsSource {
  std::string url;
  std::chrono::milliseconds timeout;
  std::string log_subject;
};

class RuntimeMetrics {
public:
  RuntimeMetrics(RuntimeMetricsSource source, std::ostream &log);

  [[nodiscard]] std::optional<std::string> fetch();

private:
  std::string url_;
  std::chrono::milliseconds timeout_;
  std::mutex log_mutex_;
  HttpFailureLog failure_log_;
};

} // namespace desmond
