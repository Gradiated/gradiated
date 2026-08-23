#include "desmond/profiling.h"

#include "desmond/http.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <iomanip>
#include <random>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace desmond {

std::string json_string(const std::string_view value) {
  std::string output{"\""};
  output.reserve(value.size() + 2);
  for (const unsigned char character : value) {
    switch (character) {
      case '"': output += "\\\""; break;
      case '\\': output += "\\\\"; break;
      case '\b': output += "\\b"; break;
      case '\f': output += "\\f"; break;
      case '\n': output += "\\n"; break;
      case '\r': output += "\\r"; break;
      case '\t': output += "\\t"; break;
      default:
        if (character < 0x20) {
          std::array<char, 7> escaped{};
          std::snprintf(escaped.data(), escaped.size(), "\\u%04x", character);
          output += escaped.data();
        } else {
          output += static_cast<char>(character);
        }
    }
  }
  output += '"';
  return output;
}

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
    if (index == 4 || index == 6 || index == 8 || index == 10) output << '-';
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
  output << std::put_time(&utc, "%Y-%m-%dT%H:%M:%S") << '.' << std::setfill('0')
         << std::setw(6) << microseconds << 'Z';
  return output.str();
}

ProfilingUploader::ProfilingUploader(ProfilingUploaderConfig config)
    : config_(std::move(config)) {
  if (enabled()) {
    if (config_.batch_size == 0 || config_.batch_size > config_.queue_capacity ||
        config_.retry_initial <= std::chrono::milliseconds::zero() ||
        config_.retry_maximum < config_.retry_initial) {
      throw std::invalid_argument("invalid profiling uploader queue or retry configuration");
    }
    thread_ = std::thread([this] { run(); });
  }
}

ProfilingUploader::~ProfilingUploader() { stop(); }

bool ProfilingUploader::enabled() const {
  return !config_.host.empty() && !config_.token.empty() && !config_.deployment_id.empty();
}

void ProfilingUploader::enqueue(std::string event_type, std::string properties_json) {
  if (!enabled()) return;
  std::lock_guard lock(mutex_);
  if (queue_.size() >= config_.queue_capacity) {
    ++dropped_;
    return;
  }
  queue_.push_back({uuid_v4(), utc_now(), std::move(event_type), std::move(properties_json)});
  condition_.notify_one();
}

void ProfilingUploader::stop() {
  {
    std::lock_guard lock(mutex_);
    if (stopping_) return;
    stopping_ = true;
  }
  condition_.notify_all();
  if (thread_.joinable()) thread_.join();
}

void ProfilingUploader::run() {
  std::deque<ProfilingEvent> batch;
  std::string batch_id;
  auto retry_delay = config_.retry_initial;
  while (true) {
    if (batch.empty()) {
      std::unique_lock lock(mutex_);
      condition_.wait_for(lock, config_.flush_interval, [this] {
        return stopping_ || queue_.size() >= config_.batch_size;
      });
      if (queue_.empty() && stopping_) return;
      const auto count = std::min(config_.batch_size, queue_.size());
      for (std::size_t index = 0; index < count; ++index) {
        batch.push_back(std::move(queue_.front()));
        queue_.pop_front();
      }
      batch_id = uuid_v4();
    }
    if (batch.empty()) continue;
    if (upload(batch_id, batch)) {
      std::lock_guard lock(mutex_);
      uploaded_ += batch.size();
      batch.clear();
      batch_id.clear();
      retry_delay = config_.retry_initial;
    } else {
      {
        std::lock_guard lock(mutex_);
        ++failed_batches_;
        if (stopping_) return;
      }
      std::unique_lock lock(mutex_);
      condition_.wait_for(lock, retry_delay, [this] { return stopping_; });
      if (stopping_) return;
      retry_delay = std::min(retry_delay * 2, config_.retry_maximum);
    }
  }
}

bool ProfilingUploader::upload(const std::string_view batch_id,
                               const std::deque<ProfilingEvent>& events) {
  std::ostringstream body;
  body << "{\"schema_version\":1,\"batch_id\":" << json_string(batch_id)
       << ",\"deployment_id\":" << json_string(config_.deployment_id)
       << ",\"model_id\":" << json_string(config_.model_id)
       << ",\"runtime_revision\":" << json_string(config_.runtime_revision)
       << ",\"events\":[";
  bool first = true;
  for (const auto& event : events) {
    if (!first) body << ',';
    first = false;
    body << "{\"id\":" << json_string(event.id)
         << ",\"observed_at\":" << json_string(event.observed_at)
         << ",\"event_type\":" << json_string(event.event_type)
         << ",\"properties\":" << event.properties_json << '}';
  }
  body << "]}";
  const auto response = http_post(config_.host, config_.port, config_.path,
                                  "Bearer " + config_.token, body.str(),
                                  std::chrono::seconds(5));
  return response.transport_ok && response.status >= 200 && response.status < 300;
}

std::string ProfilingUploader::prometheus() const {
  std::lock_guard lock(mutex_);
  std::ostringstream output;
  output << "desmond_profiling_enabled " << (enabled() ? 1 : 0) << '\n'
         << "desmond_profiling_queue_events " << queue_.size() << '\n'
         << "desmond_profiling_uploaded_events_total " << uploaded_ << '\n'
         << "desmond_profiling_failed_batches_total " << failed_batches_ << '\n'
         << "desmond_profiling_dropped_events_total " << dropped_ << '\n';
  return output.str();
}

}  // namespace desmond
