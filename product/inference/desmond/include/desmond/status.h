#pragma once

#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <string>
#include <thread>

namespace desmond {

struct StatusReporterConfig {
  std::string host;
  std::uint16_t port{80};
  std::string path{"/v1/deployment-status"};
  std::string token;
  std::string deployment_id;
  std::string runtime_revision;
  std::uint64_t maximum_concurrency{1};
  std::chrono::seconds interval{1};
};

struct DeploymentStatusSnapshot {
  bool healthy{false};
  bool accepting_requests{false};
  std::string reason_code;
};

struct RuntimePressure {
  bool kv_pressure{false};
  bool queue_pressure{false};
  bool concurrency_pressure{false};
};

class StatusReporter {
 public:
  explicit StatusReporter(StatusReporterConfig config);
  ~StatusReporter();
  StatusReporter(const StatusReporter&) = delete;
  StatusReporter& operator=(const StatusReporter&) = delete;

  [[nodiscard]] bool enabled() const;
  void update(DeploymentStatusSnapshot snapshot);
  void stop();
  [[nodiscard]] std::string prometheus() const;

 private:
  void run();
  bool upload(const DeploymentStatusSnapshot& snapshot);

  StatusReporterConfig config_;
  mutable std::mutex mutex_;
  std::condition_variable condition_;
  DeploymentStatusSnapshot latest_;
  std::thread thread_;
  bool has_value_{false};
  bool stopping_{false};
  std::uint64_t uploaded_{0};
  std::uint64_t failures_{0};
};

[[nodiscard]] RuntimePressure parse_runtime_pressure(
    const std::string& prometheus_text, double kv_usage_limit,
    std::uint64_t waiting_request_limit, std::uint64_t maximum_concurrency);

}  // namespace desmond
