#include "desmond/status_reporter.h"

#include "desmond/json.h"
#include "desmond/prometheus.h"

#include <sstream>
#include <stdexcept>
#include <utility>

namespace desmond {
namespace {

constexpr std::chrono::seconds upload_freshness{10};

} // namespace

StatusReporter::StatusReporter(StatusReporterConfig config, std::ostream &log)
    : config_(std::move(config)), log_(log) {
  if (config_.interval <= std::chrono::seconds::zero()) {
    throw std::invalid_argument("deployment status interval must be positive");
  }

  thread_ = std::thread([this] { run(); });
}

StatusReporter::~StatusReporter() {
  stop();
}

bool StatusReporter::recently_uploaded() const {
  std::lock_guard lock(mutex_);
  return uploaded_ > 0 && std::chrono::steady_clock::now() - last_uploaded_ < upload_freshness;
}

void StatusReporter::update(const DeploymentStatus status) {
  std::lock_guard lock(mutex_);
  latest_ = status;
  ++latest_generation_;
}

void StatusReporter::stop() {
  {
    std::lock_guard lock(mutex_);
    if (stopping_) {
      return;
    }

    stopping_ = true;
  }

  condition_.notify_all();
  if (thread_.joinable()) {
    thread_.join();
  }
}

void StatusReporter::run() {
  HttpFailureLog failure_log("status upload", log_);
  auto next_upload = std::chrono::steady_clock::now();

  while (true) {
    std::optional<DeploymentStatus> status;
    std::uint64_t generation = 0;
    bool final_upload = false;
    {
      std::unique_lock lock(mutex_);
      condition_.wait_until(lock, next_upload, [this] { return stopping_; });

      final_upload = stopping_;
      if (final_upload && latest_generation_ == delivered_generation_) {
        return;
      }

      status = latest_;
      generation = latest_generation_;
    }

    if (status) {
      const auto result = upload(*status);
      const bool delivered = succeeded(result);
      failure_log.record(result);

      std::lock_guard lock(mutex_);
      if (delivered) {
        ++uploaded_;
        last_uploaded_ = std::chrono::steady_clock::now();
        delivered_generation_ = generation;
      } else {
        ++failures_;
      }
    }

    if (final_upload) {
      return;
    }

    next_upload = std::chrono::steady_clock::now() + config_.interval;
  }
}

HttpResult StatusReporter::upload(const DeploymentStatus status) const {
  const auto reason = reason_code(status);
  const auto body = JsonObjectWriter()
                        .field("schema_version", 1)
                        .field("deployment_id", config_.deployment_id)
                        .field("runtime_revision", config_.runtime_revision)
                        .field("healthy", is_healthy(status))
                        .field("accepting_requests", accepts_requests(status))
                        .raw_field("reason_code", reason ? json_string(*reason) : "null")
                        .str();

  return http_request({
      .method = HttpMethod::post,
      .url = config_.url,
      .authorization = "Bearer " + config_.token,
      .body = body,
      .timeout = config_.request_timeout,
  });
}

std::string StatusReporter::prometheus() const {
  std::lock_guard lock(mutex_);
  std::ostringstream output;
  prometheus::write_metric(output, "desmond_status_uploaded_total", prometheus::MetricType::counter,
                           uploaded_);
  prometheus::write_metric(output, "desmond_status_failures_total", prometheus::MetricType::counter,
                           failures_);
  return output.str();
}

} // namespace desmond
