#pragma once

#include "desmond/http_client.h"

#include <mutex>
#include <ostream>
#include <string>

namespace desmond {

enum class RuntimeState { unready, ready, draining };

class RuntimeHealth {
public:
  RuntimeHealth(std::string health_url, std::ostream &log);

  void check();
  void start_draining();
  [[nodiscard]] RuntimeState state() const;

private:
  std::string health_url_;
  HttpFailureLog failure_log_;
  mutable std::mutex mutex_;
  RuntimeState state_{RuntimeState::unready};
};

} // namespace desmond
