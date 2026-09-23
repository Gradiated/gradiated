#include "desmond/profiling.h"

#include "desmond/http_client.h"
#include "desmond/json.h"
#include "desmond/prometheus.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <iomanip>
#include <iterator>
#include <random>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace desmond {
namespace {

std::string uuid_v4() {
  thread_local std::mt19937_64 generator(std::random_device{}());

  std::array<unsigned char, 16> bytes{};
  for (std::size_t index = 0; index < bytes.size(); index += 8) {
    const auto value = generator();
    for (std::size_t offset = 0; offset < 8; ++offset) {
      bytes[index + offset] = static_cast<unsigned char>((value >> (offset * 8)) & 0xffU);
    }
  }
  bytes[6] = static_cast<unsigned char>((bytes[6] & 0x0fU) | 0x40U);
  bytes[8] = static_cast<unsigned char>((bytes[8] & 0x3fU) | 0x80U);

  std::ostringstream output;
  output << std::hex << std::setfill('0');
  for (std::size_t index = 0; index < bytes.size(); ++index) {
    if (index == 4 || index == 6 || index == 8 || index == 10) {
      output << '-';
    }

    output << std::setw(2) << static_cast<unsigned int>(bytes[index]);
  }

  return output.str();
}

std::string utc_now() {
  const auto now = std::chrono::system_clock::now();
  const auto seconds = std::chrono::time_point_cast<std::chrono::seconds>(now);
  const auto microseconds =
      std::chrono::duration_cast<std::chrono::microseconds>(now - seconds).count();
  const std::time_t time = std::chrono::system_clock::to_time_t(now);
  std::tm utc{};
  gmtime_r(&time, &utc);

  std::ostringstream output;
  output << std::put_time(&utc, "%Y-%m-%dT%H:%M:%S") << '.' << std::setfill('0') << std::setw(6)
         << microseconds << 'Z';
  return output.str();
}

} // namespace

ProfilingUploader::ProfilingUploader(ProfilingUploaderConfig config, std::ostream &log)
    : config_(std::move(config)), log_(log) {
  if (config_.batch_size == 0 || config_.batch_size > config_.queue_capacity ||
      config_.retry_initial <= std::chrono::milliseconds::zero() ||
      config_.retry_maximum < config_.retry_initial) {
    throw std::invalid_argument("invalid profiling uploader queue or retry configuration");
  }

  thread_ = std::thread([this] { run(); });
}

ProfilingUploader::~ProfilingUploader() {
  stop();
}

void ProfilingUploader::enqueue(std::string event_type, std::string properties_json) {
  std::lock_guard lock(mutex_);
  if (stopping_ || queue_.size() >= config_.queue_capacity) {
    ++dropped_;
    return;
  }

  queue_.push_back({uuid_v4(), utc_now(), std::move(event_type), std::move(properties_json)});
  if (queue_.size() >= config_.batch_size) {
    condition_.notify_one();
  }
}

void ProfilingUploader::stop() {
  {
    std::lock_guard lock(mutex_);
    if (stopping_) {
      return;
    }

    stopping_ = true;
    stop_deadline_ = std::chrono::steady_clock::now() + config_.stop_flush_deadline;
  }

  condition_.notify_all();
  if (thread_.joinable()) {
    thread_.join();
  }

  std::lock_guard lock(mutex_);
  if (dropped_ > 0) {
    log_ << "desmond: profiling dropped " << dropped_ << " events\n";
  }
}

void ProfilingUploader::run() {
  HttpFailureLog failure_log("profiling upload", log_);
  std::deque<ProfilingEvent> batch;
  std::string batch_id;
  auto retry_delay = config_.retry_initial;

  while (true) {
    auto timeout = config_.request_timeout;
    {
      std::unique_lock lock(mutex_);
      if (batch.empty()) {
        condition_.wait_for(lock, config_.flush_interval,
                            [this] { return stopping_ || queue_.size() >= config_.batch_size; });
        if (queue_.empty()) {
          if (stopping_) {
            return;
          }

          continue;
        }

        const auto count = std::min(config_.batch_size, queue_.size());
        std::move(queue_.begin(), queue_.begin() + static_cast<std::ptrdiff_t>(count),
                  std::back_inserter(batch));
        queue_.erase(queue_.begin(), queue_.begin() + static_cast<std::ptrdiff_t>(count));
        batch_id = uuid_v4();
      }

      if (stopping_) {
        const auto remaining = std::chrono::ceil<std::chrono::milliseconds>(
            stop_deadline_ - std::chrono::steady_clock::now());
        if (remaining <= std::chrono::milliseconds::zero()) {
          drop_unsent(batch);
          return;
        }

        timeout = std::min(timeout, remaining);
      }
    }

    const auto result = upload(batch_id, batch, timeout);
    const bool delivered = succeeded(result);
    failure_log.record(result);

    std::unique_lock lock(mutex_);
    if (delivered) {
      uploaded_ += batch.size();
      batch.clear();
      retry_delay = config_.retry_initial;
      continue;
    }

    ++failed_batches_;
    if (stopping_) {
      drop_unsent(batch);
      return;
    }

    condition_.wait_for(lock, retry_delay, [this] { return stopping_; });
    retry_delay = std::min(retry_delay * 2, config_.retry_maximum);
  }
}

void ProfilingUploader::drop_unsent(std::deque<ProfilingEvent> &batch) {
  dropped_ += batch.size() + queue_.size();
  batch.clear();
  queue_.clear();
}

HttpResult ProfilingUploader::upload(const std::string_view batch_id,
                                     const std::deque<ProfilingEvent> &events,
                                     const std::chrono::milliseconds timeout) const {
  std::string rendered_events{"["};
  for (const auto &event : events) {
    if (rendered_events.size() > 1) {
      rendered_events += ',';
    }

    rendered_events += JsonObjectWriter()
                           .field("id", event.id)
                           .field("observed_at", event.observed_at)
                           .field("event_type", event.event_type)
                           .raw_field("properties", event.properties_json)
                           .str();
  }
  rendered_events += ']';

  const auto body = JsonObjectWriter()
                        .field("schema_version", 1)
                        .field("batch_id", batch_id)
                        .field("deployment_id", config_.deployment_id)
                        .field("model_id", config_.model_id)
                        .field("runtime_revision", config_.runtime_revision)
                        .raw_field("events", rendered_events)
                        .str();

  return http_request({
      .method = HttpMethod::post,
      .url = config_.url,
      .authorization = "Bearer " + config_.token,
      .body = body,
      .timeout = timeout,
  });
}

std::string ProfilingUploader::prometheus() const {
  std::lock_guard lock(mutex_);
  using prometheus::MetricType;
  std::ostringstream output;
  prometheus::write_metric(output, "desmond_profiling_queue_events", MetricType::gauge,
                           queue_.size());
  prometheus::write_metric(output, "desmond_profiling_uploaded_events_total", MetricType::counter,
                           uploaded_);
  prometheus::write_metric(output, "desmond_profiling_failed_batches_total", MetricType::counter,
                           failed_batches_);
  prometheus::write_metric(output, "desmond_profiling_dropped_events_total", MetricType::counter,
                           dropped_);
  return output.str();
}

} // namespace desmond
