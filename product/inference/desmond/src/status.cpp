#include "desmond/status.h"

#include "desmond/http.h"
#include "desmond/profiling.h"

#include <algorithm>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace desmond {
namespace {

bool metric_at_or_above(const std::string& text, const std::string& name,
                        const double limit) {
  std::istringstream lines(text);
  std::string line;
  while (std::getline(lines, line)) {
    if (line.empty() || line.front() == '#') continue;
    const auto separator = line.find_first_of(" {\t");
    if (separator == std::string::npos || line.substr(0, separator) != name) continue;
    const auto value_offset = line.find_last_of(" \t");
    if (value_offset == std::string::npos) continue;
    try {
      if (std::stod(line.substr(value_offset + 1)) >= limit) return true;
    } catch (...) {
      continue;
    }
  }
  return false;
}

}  // namespace

StatusReporter::StatusReporter(StatusReporterConfig config)
    : config_(std::move(config)) {
  if (enabled()) {
    if (config_.interval <= std::chrono::seconds::zero()) {
      throw std::invalid_argument("invalid deployment status reporter configuration");
    }
    thread_ = std::thread([this] { run(); });
  }
}

StatusReporter::~StatusReporter() { stop(); }

bool StatusReporter::enabled() const {
  return (!config_.url.empty() || !config_.host.empty()) &&
         !config_.token.empty() && !config_.deployment_id.empty() &&
         !config_.runtime_revision.empty();
}

bool StatusReporter::recently_uploaded() const {
  std::lock_guard lock(mutex_);
  return uploaded_ > 0 && std::chrono::steady_clock::now() - last_uploaded_ <
                              std::chrono::seconds(10);
}

void StatusReporter::update(DeploymentStatusSnapshot snapshot) {
  if (!enabled()) return;
  {
    std::lock_guard lock(mutex_);
    latest_ = std::move(snapshot);
    has_value_ = true;
  }
  condition_.notify_one();
}

void StatusReporter::stop() {
  {
    std::lock_guard lock(mutex_);
    if (stopping_) return;
    stopping_ = true;
  }
  condition_.notify_all();
  if (thread_.joinable()) thread_.join();
}

void StatusReporter::run() {
  bool upload_failed = false;
  auto next_upload = std::chrono::steady_clock::now();
  while (true) {
    DeploymentStatusSnapshot snapshot;
    {
      std::unique_lock lock(mutex_);
      condition_.wait_until(lock, next_upload, [this] { return stopping_; });
      if (stopping_) return;
      if (!has_value_) {
        next_upload = std::chrono::steady_clock::now() + config_.interval;
        continue;
      }
      snapshot = latest_;
    }
    const bool sent = upload(snapshot);
    if (!sent && !upload_failed) {
      std::cerr << "desmond: status upload failed http_status="
                << last_http_status_ << '\n';
    } else if (sent && upload_failed) {
      std::cerr << "desmond: status upload recovered\n";
    }
    upload_failed = !sent;
    {
      std::lock_guard lock(mutex_);
      if (sent) {
        ++uploaded_;
        last_uploaded_ = std::chrono::steady_clock::now();
      } else {
        ++failures_;
      }
    }
    next_upload = std::chrono::steady_clock::now() + config_.interval;
  }
}

bool StatusReporter::upload(const DeploymentStatusSnapshot& snapshot) {
  std::ostringstream body;
  body << "{\"schema_version\":1,\"deployment_id\":"
       << json_string(config_.deployment_id) << ",\"runtime_revision\":"
       << json_string(config_.runtime_revision) << ",\"healthy\":"
       << (snapshot.healthy ? "true" : "false")
       << ",\"accepting_requests\":"
       << (snapshot.accepting_requests ? "true" : "false")
       << ",\"reason_code\":";
  if (snapshot.reason_code.empty()) {
    body << "null";
  } else {
    body << json_string(snapshot.reason_code);
  }
  body << '}';
  const auto response =
      config_.url.empty() ? http_post(config_.host, config_.port, config_.path,
                                      "Bearer " + config_.token, body.str(),
                                      std::chrono::milliseconds(750))
                          : https_post(config_.url, "Bearer " + config_.token,
                                       body.str(), std::chrono::seconds(2));
  last_http_status_ = response.transport_ok ? response.status : 0;
  return response.transport_ok && response.status == 204;
}

std::string StatusReporter::prometheus() const {
  std::lock_guard lock(mutex_);
  std::ostringstream output;
  output << "desmond_status_uploaded_total " << uploaded_ << '\n'
         << "desmond_status_failures_total " << failures_ << '\n';
  return output.str();
}

RuntimePressure parse_runtime_pressure(const std::string& prometheus_text,
                                       const double kv_usage_limit) {
  RuntimePressure pressure;
  pressure.kv_pressure =
      metric_at_or_above(prometheus_text, "vllm:kv_cache_usage_perc", kv_usage_limit) ||
      metric_at_or_above(prometheus_text, "vllm_kv_cache_usage_perc", kv_usage_limit) ||
      metric_at_or_above(prometheus_text, "vllm:gpu_cache_usage_perc", kv_usage_limit) ||
      metric_at_or_above(prometheus_text, "vllm_gpu_cache_usage_perc", kv_usage_limit);
  return pressure;
}

}  // namespace desmond
