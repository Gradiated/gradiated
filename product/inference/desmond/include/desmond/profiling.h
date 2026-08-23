#pragma once

#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <mutex>
#include <string>
#include <string_view>
#include <thread>

namespace desmond {

struct ProfilingUploaderConfig {
  std::string host;
  std::uint16_t port{80};
  std::string path{"/v1/profiling-events"};
  std::string token;
  std::string deployment_id;
  std::string model_id;
  std::string runtime_revision;
  std::size_t batch_size{200};
  std::size_t queue_capacity{20'000};
  std::chrono::seconds flush_interval{10};
  std::chrono::milliseconds retry_initial{250};
  std::chrono::milliseconds retry_maximum{30'000};
};

struct ProfilingEvent {
  std::string id;
  std::string observed_at;
  std::string event_type;
  std::string properties_json;
};

class ProfilingUploader {
 public:
  explicit ProfilingUploader(ProfilingUploaderConfig config);
  ~ProfilingUploader();
  ProfilingUploader(const ProfilingUploader&) = delete;
  ProfilingUploader& operator=(const ProfilingUploader&) = delete;

  [[nodiscard]] bool enabled() const;
  void enqueue(std::string event_type, std::string properties_json);
  void stop();
  [[nodiscard]] std::string prometheus() const;

 private:
  void run();
  bool upload(std::string_view batch_id, const std::deque<ProfilingEvent>& events);

  ProfilingUploaderConfig config_;
  mutable std::mutex mutex_;
  std::condition_variable condition_;
  std::deque<ProfilingEvent> queue_;
  std::thread thread_;
  bool stopping_{false};
  std::uint64_t uploaded_{0};
  std::uint64_t failed_batches_{0};
  std::uint64_t dropped_{0};
};

[[nodiscard]] std::string uuid_v4();
[[nodiscard]] std::string utc_now();
[[nodiscard]] std::string json_string(std::string_view value);

}  // namespace desmond
