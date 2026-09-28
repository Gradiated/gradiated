#include "desmond/child_process.h"
#include "desmond/config.h"
#include "desmond/control_api.h"
#include "desmond/deployment_status.h"
#include "desmond/gpu_metrics.h"
#include "desmond/http.h"
#include "desmond/http_client.h"
#include "desmond/json.h"
#include "desmond/profiling.h"
#include "desmond/profiling_events.h"
#include "desmond/runtime_health.h"
#include "desmond/runtime_launch.h"
#include "desmond/runtime_metrics.h"
#include "desmond/status_reporter.h"
#include "desmond/supervised_child.h"
#include "desmond/supervisor_metrics.h"
#include "desmond/trace.h"

#include <signal.h>
#include <unistd.h>

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <thread>
#include <variant>

extern char **environ;

namespace {

using namespace std::chrono_literals;
using Clock = std::chrono::steady_clock;

constexpr int exit_usage = 64;
constexpr int exit_software_error = 70;

constexpr std::size_t trace_ring_capacity = 65'536;
constexpr std::size_t trace_drain_per_tick = 4'096;
constexpr std::size_t trace_final_drain = trace_ring_capacity;
constexpr auto runtime_terminate_grace = 30s;
constexpr auto status_metrics_timeout = 750ms;
constexpr auto scrape_metrics_timeout = 2s;

static_assert(std::atomic<bool>::is_always_lock_free,
              "stop_requested is written from a signal handler");
std::atomic<bool> stop_requested{false};

void request_stop(int) {
  stop_requested.store(true);
}

void install_stop_handlers() {
  struct sigaction action {};
  action.sa_handler = request_stop;
  sigemptyset(&action.sa_mask);
  sigaction(SIGTERM, &action, nullptr);
  sigaction(SIGINT, &action, nullptr);
}

std::optional<std::string_view> process_environment(const std::string_view name) {
  const char *value = std::getenv(std::string(name).c_str());
  if (value == nullptr) {
    return std::nullopt;
  }

  return value;
}

// Containers normally run desmondd as PID 1. Include a per-start nonce so a stale file from an
// unclean container exit cannot silently disable request-level telemetry on restart.
std::string unique_trace_path() {
  const auto start_nonce = Clock::now().time_since_epoch().count();
  return "/dev/shm/desmond-trace-" + std::to_string(getpid()) + '-' + std::to_string(start_nonce);
}

std::unique_ptr<desmond::SharedTraceRing> create_trace_ring(const std::string &path) {
  try {
    return desmond::SharedTraceRing::create(path, trace_ring_capacity);
  } catch (const std::exception &error) {
    std::cerr << "desmond: shared trace ring unavailable: " << error.what() << '\n';
    return nullptr;
  }
}

int exit_code_for_unexpected(const desmond::ExitStatus &status) {
  if (const auto *signaled = std::get_if<desmond::Signaled>(&status)) {
    return 128 + signaled->signal;
  }

  const int code = std::get<desmond::Exited>(status).code;
  return code == 0 ? exit_software_error : code;
}

class Interval {
public:
  explicit Interval(const Clock::duration period) : period_(period), next_(Clock::now()) {}

  bool due(const Clock::time_point now) {
    if (now < next_) {
      return false;
    }

    next_ = now + period_;
    return true;
  }

private:
  Clock::duration period_;
  Clock::time_point next_;
};

class Desmond {
public:
  explicit Desmond(const desmond::DesmondConfig &config)
      : config_(config), health_(config_.health_request(), std::cerr),
        status_metrics_({.url = runtime_url("/metrics"),
                         .timeout = status_metrics_timeout,
                         .log_subject = "runtime metrics fetch"},
                        std::cerr),
        scrape_metrics_({.url = runtime_url("/metrics"),
                         .timeout = scrape_metrics_timeout,
                         .log_subject = "runtime metrics scrape"},
                        std::cerr),
        server_(config_.control.host, config_.control.port,
                [this](const desmond::HttpRequest &request) { return handle(request); }) {
    if (config_.profiling) {
      profiling_.emplace(*config_.profiling, std::cerr);
    } else {
      std::cerr << "desmond: profiling disabled\n";
    }
    if (config_.status) {
      reporter_.emplace(*config_.status, std::cerr);
    } else {
      std::cerr << "desmond: deployment status reporting disabled\n";
    }
    if (!gpu_.available()) {
      std::cerr << "desmond: NVML unavailable at startup: " << gpu_.error() << '\n';
    }

    if (const auto *supervised = std::get_if<desmond::SuperviseRuntime>(&config_.runtime)) {
      start_runtime(*supervised);
    } else {
      record("observer.started", "{}");
    }
  }

  int run() {
    std::thread http_thread([this] { server_.run(); });

    int exit_code = exit_software_error;
    auto final_status = desmond::DeploymentStatus::runtime_unavailable;
    try {
      if (const auto runtime_exit = supervise()) {
        exit_code = exit_code_for_unexpected(*runtime_exit);
      } else {
        exit_code = EXIT_SUCCESS;
        final_status = desmond::DeploymentStatus::draining;
      }
    } catch (const std::exception &error) {
      std::cerr << "desmond: fatal: " << error.what() << '\n';
    }

    shut_down(final_status);
    server_.stop();
    http_thread.join();
    return exit_code;
  }

private:
  std::string runtime_url(const std::string_view path) const {
    return desmond::http_url(config_.runtime_endpoint.host, config_.runtime_endpoint.port, path);
  }

  void start_runtime(const desmond::SuperviseRuntime &runtime) {
    std::optional<std::string> trace_path;
    if (profiling_) {
      trace_path = runtime.trace_path.value_or(unique_trace_path());
      trace_ring_ = create_trace_ring(*trace_path);
    }
    if (!trace_ring_) {
      trace_path.reset();
    }

    const auto launch = desmond::runtime_launch(runtime, environ, trace_path);
    child_.emplace(launch.command, launch.environment);
    record("runtime.started", desmond::JsonObjectWriter().field("pid", child_->pid()).str());
  }

  std::optional<desmond::ExitStatus> supervise() {
    Interval health_check(1s);
    Interval status_report(1s);
    Interval gpu_sample(5s);
    Interval metrics_snapshot(15s);
    bool prior_ready = false;

    while (!stop_requested.load()) {
      drain_trace(trace_drain_per_tick);
      if (auto runtime_exit = reap_unexpected_exit()) {
        return runtime_exit;
      }

      const auto now = Clock::now();
      if (health_check.due(now)) {
        health_.check();
      }

      const auto runtime = health_.state();
      const bool ready = runtime == desmond::RuntimeState::ready;
      if (ready != prior_ready) {
        record("runtime.state", desmond::JsonObjectWriter().field("ready", ready).str());
        prior_ready = ready;
      }

      if (status_report.due(now)) {
        const auto metrics = ready ? status_metrics_.fetch() : std::nullopt;
        if (reporter_) {
          reporter_->update(
              desmond::assess_deployment(runtime, config_.mode(), metrics, config_.kv_usage_limit));
        }
        if (metrics && metrics_snapshot.due(now)) {
          record("runtime.metrics_snapshot",
                 desmond::JsonObjectWriter().field("prometheus_text", *metrics).str());
        }
      }

      if (gpu_sample.due(now)) {
        for (const auto &sample : gpu_.sample()) {
          record("gpu.sample", desmond::gpu_sample_properties(sample));
        }
      }

      std::this_thread::sleep_for(100ms);
    }

    return std::nullopt;
  }

  std::optional<desmond::ExitStatus> reap_unexpected_exit() {
    auto status = child_ ? child_->try_reap() : std::nullopt;
    if (!status) {
      return std::nullopt;
    }

    std::cerr << "desmond: runtime exited unexpectedly with " << desmond::to_string(*status)
              << '\n';
    child_state_ = desmond::ChildState::exited_unexpectedly;
    return status;
  }

  void shut_down(const desmond::DeploymentStatus final_status) {
    health_.start_draining();
    if (reporter_) {
      reporter_->update(final_status);
      reporter_->stop();
    }
    record(config_.mode() == desmond::Mode::supervise ? "runtime.stopping" : "observer.stopping",
           "{}");

    if (child_ && child_state_ == desmond::ChildState::running) {
      const auto status = child_->terminate(runtime_terminate_grace);
      child_state_ = desmond::ChildState::stopped;
      std::cerr << "desmond: runtime stopped with " << desmond::to_string(status) << '\n';
    }

    drain_trace(trace_final_drain);
    if (profiling_) {
      profiling_->stop();
    }
  }

  void record(std::string event_type, std::string properties) {
    if (profiling_) {
      profiling_->enqueue(std::move(event_type), std::move(properties));
    }
  }

  void drain_trace(const std::size_t maximum_events) {
    if (!trace_ring_) {
      return;
    }

    desmond::TraceEvent event;
    std::size_t consumed = 0;
    while (consumed < maximum_events && trace_ring_->try_pop(event)) {
      record(std::string("runtime.") + desmond::trace_event_type_name(event.type),
             desmond::trace_event_properties(event));
      ++consumed;
    }

    consumed_trace_events_ += consumed;
  }

  std::optional<desmond::SupervisedChild> supervised_child() const {
    if (!child_) {
      return std::nullopt;
    }

    return desmond::SupervisedChild{.pid = child_->pid(), .state = child_state_.load()};
  }

  desmond::HttpResponse handle(const desmond::HttpRequest &request) {
    return desmond::handle_control_request(
        request, {
                     .mode = config_.mode(),
                     .runtime = health_.state(),
                     .supervised_child = supervised_child(),
                     .reporter_fresh = reporter_ && reporter_->recently_uploaded(),
                     .identity = config_.identity,
                     .control_token = config_.control_token,
                     .desmond_metrics = [this] { return desmond_metrics(); },
                     .runtime_metrics = [this] { return scrape_metrics_.fetch(); },
                 });
  }

  std::optional<desmond::TraceCounters> trace_counters() const {
    if (!trace_ring_) {
      return std::nullopt;
    }

    return desmond::TraceCounters{
        .consumed = consumed_trace_events_.load(),
        .dropped = trace_ring_->dropped(),
    };
  }

  std::string desmond_metrics() const {
    auto metrics = desmond::supervisor_prometheus({
        .supervised_child = supervised_child(),
        .runtime = health_.state(),
        .identity = config_.identity,
        .profiling_enabled = profiling_.has_value(),
        .trace = trace_counters(),
    });

    metrics += gpu_.prometheus();
    if (profiling_) {
      metrics += profiling_->prometheus();
    }
    if (reporter_) {
      metrics += reporter_->prometheus();
    }

    return metrics;
  }

  const desmond::DesmondConfig &config_;
  desmond::RuntimeHealth health_;
  desmond::RuntimeMetrics status_metrics_;
  desmond::RuntimeMetrics scrape_metrics_;
  desmond::GpuMetrics gpu_;
  desmond::HttpServer server_;
  std::optional<desmond::ProfilingUploader> profiling_;
  std::optional<desmond::StatusReporter> reporter_;
  std::unique_ptr<desmond::SharedTraceRing> trace_ring_;
  std::optional<desmond::ChildProcess> child_;
  std::atomic<desmond::ChildState> child_state_{desmond::ChildState::running};
  std::atomic<std::uint64_t> consumed_trace_events_{0};
};

} // namespace

int main(const int argc, char **argv) {
  try {
    const auto config = desmond::load_config(
        std::span<const char *const>(argv + 1, static_cast<std::size_t>(argc - 1)),
        process_environment);
    install_stop_handlers();

    Desmond desmond(config);
    return desmond.run();
  } catch (const desmond::ConfigError &error) {
    std::cerr << "desmond: " << error.what() << '\n';
    return exit_usage;
  } catch (const std::exception &error) {
    std::cerr << "desmond: fatal: " << error.what() << '\n';
    return exit_software_error;
  }
}
