#pragma once

#include "desmond/http_client.h"
#include "desmond/json.h"

#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <mutex>
#include <ostream>
#include <string>
#include <string_view>
#include <thread>

namespace desmond {

struct ProfilingUploaderConfig {
  std::string url;
  std::string token;
  std::string deployment_id;
  std::string model_id;
  std::string runtime_revision;
  std::size_t batch_size{200};
  std::size_t queue_capacity{20'000};
  std::chrono::seconds flush_interval{10};
  std::chrono::milliseconds retry_initial{250};
  std::chrono::milliseconds retry_maximum{30'000};
  std::chrono::milliseconds request_timeout{5000};
  std::chrono::seconds stop_flush_deadline{5};
};

struct ProfilingEvent {
  std::string id;
  std::string observed_at;
  std::string event_type;
  std::string properties_json;
};

class ProfilingUploader {
public:
  ProfilingUploader(ProfilingUploaderConfig config, std::ostream &log);
  ~ProfilingUploader();
  ProfilingUploader(const ProfilingUploader &) = delete;
  ProfilingUploader &operator=(const ProfilingUploader &) = delete;

  void enqueue(std::string event_type, std::string properties_json);
  void stop();
  [[nodiscard]] std::string prometheus() const;

private:
  void run();
  [[nodiscard]] HttpResult upload(std::string_view batch_id,
                                  const std::deque<ProfilingEvent> &events,
                                  std::chrono::milliseconds timeout) const;
  void drop_unsent(std::deque<ProfilingEvent> &batch);

  ProfilingUploaderConfig config_;
  std::ostream &log_;
  mutable std::mutex mutex_;
  std::condition_variable condition_;
  std::deque<ProfilingEvent> queue_;
  bool stopping_{false};
  std::chrono::steady_clock::time_point stop_deadline_{};
  std::uint64_t uploaded_{0};
  std::uint64_t failed_batches_{0};
  std::uint64_t dropped_{0};
  std::thread thread_;
};

} // namespace desmond
