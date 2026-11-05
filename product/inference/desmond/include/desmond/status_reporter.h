#pragma once

#include "desmond/deployment_status.h"
#include "desmond/http_client.h"

#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <optional>
#include <ostream>
#include <string>
#include <thread>

namespace desmond {

struct StatusReporterConfig {
  std::string url;
  std::string token;
  std::string deployment_id;
  std::string runtime_revision;
  // The runtime's concurrent request limit; the gateway weights routing by it.
  std::optional<std::uint32_t> active_requests;
  std::chrono::seconds interval{1};
  std::chrono::milliseconds request_timeout{2000};
};

class StatusReporter {
public:
  StatusReporter(StatusReporterConfig config, std::ostream &log);
  ~StatusReporter();
  StatusReporter(const StatusReporter &) = delete;
  StatusReporter &operator=(const StatusReporter &) = delete;

  [[nodiscard]] bool recently_uploaded() const;
  void update(DeploymentStatus status);
  void stop();
  [[nodiscard]] std::string prometheus() const;

private:
  void run();
  [[nodiscard]] HttpResult upload(DeploymentStatus status) const;

  StatusReporterConfig config_;
  std::ostream &log_;
  mutable std::mutex mutex_;
  std::condition_variable condition_;
  std::optional<DeploymentStatus> latest_;
  std::uint64_t latest_generation_{0};
  std::uint64_t delivered_generation_{0};
  bool stopping_{false};
  std::chrono::steady_clock::time_point last_uploaded_{};
  std::uint64_t uploaded_{0};
  std::uint64_t failures_{0};
  std::thread thread_;
};

} // namespace desmond
