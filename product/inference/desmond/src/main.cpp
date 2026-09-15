#include "desmond/gpu_metrics.h"
#include "desmond/http.h"
#include "desmond/profiling.h"
#include "desmond/status.h"
#include "desmond/supervisor.h"
#include "desmond/trace.h"

#include <signal.h>

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <unistd.h>

namespace {

std::atomic<bool> stop_requested{false};

void handle_signal(int) { stop_requested.store(true, std::memory_order_relaxed); }

std::string environment(const char* name, const char* fallback) {
  const char* value = std::getenv(name);
  return value == nullptr || *value == '\0' ? fallback : value;
}

std::string token_from_environment(const char *name, const char *file_name) {
  const auto path = environment(file_name, "");
  if (path.empty())
    return environment(name, "");
  std::ifstream file(path);
  std::string token;
  if (!file || !std::getline(file, token) || token.empty() ||
      token.size() > 4096) {
    throw std::runtime_error("could not read token file");
  }
  if (!token.empty() && token.back() == '\r')
    token.pop_back();
  return token;
}

std::uint16_t environment_port(const char* name, const std::uint16_t fallback) {
  const char* value = std::getenv(name);
  if (value == nullptr || *value == '\0') {
    return fallback;
  }
  const auto parsed = std::stoul(value);
  if (parsed == 0 || parsed > 65535) {
    throw std::runtime_error(std::string("invalid port in ") + name);
  }
  return static_cast<std::uint16_t>(parsed);
}

std::uint64_t environment_u64(const char* name, const std::uint64_t fallback) {
  const char* value = std::getenv(name);
  if (value == nullptr || *value == '\0') return fallback;
  const auto parsed = std::stoull(value);
  if (parsed == 0) throw std::runtime_error(std::string("invalid value in ") + name);
  return parsed;
}

double environment_double(const char* name, const double fallback) {
  const char* value = std::getenv(name);
  if (value == nullptr || *value == '\0') return fallback;
  const auto parsed = std::stod(value);
  if (parsed <= 0.0 || parsed > 1.0) {
    throw std::runtime_error(std::string("invalid value in ") + name);
  }
  return parsed;
}

std::string unique_trace_path() {
  const auto start_nonce = std::chrono::steady_clock::now().time_since_epoch().count();
  return "/dev/shm/desmond-trace-" + std::to_string(getpid()) + '-' +
         std::to_string(start_nonce);
}

std::string json_escape(const std::string& value) {
  std::string result;
  for (const char character : value) {
    switch (character) {
      case '\\': result += "\\\\"; break;
      case '"': result += "\\\""; break;
      case '\n': result += "\\n"; break;
      default: result += character;
    }
  }
  return result;
}

std::string trace_properties(const desmond::TraceEvent& event) {
  std::ostringstream properties;
  properties << "{\"monotonic_ns\":" << event.monotonic_ns;
  if (event.request_id_high != 0 || event.request_id_low != 0) {
    properties << ",\"request_id_high\":"
               << desmond::json_string(std::to_string(event.request_id_high))
               << ",\"request_id_low\":"
               << desmond::json_string(std::to_string(event.request_id_low));
  }
  if (event.batch_id != 0) {
    properties << ",\"batch_id\":" << desmond::json_string(std::to_string(event.batch_id));
  }
  if (event.graph_node_id != 0) properties << ",\"graph_node_id\":" << event.graph_node_id;
  if (event.device_id != 0) properties << ",\"device_id\":" << event.device_id;
  switch (event.type) {
    case desmond::TraceEventType::request_admitted:
      properties << ",\"input_tokens\":" << event.value0
                 << ",\"cached_input_tokens\":" << event.value1
                 << ",\"slot_id\":" << event.stream_id
                 << ",\"queue_us\":" << event.graph_execution_id;
      break;
    case desmond::TraceEventType::request_finished:
      properties << ",\"output_tokens\":" << event.value0
                 << ",\"ttft_us\":" << event.value1
                 << ",\"slot_id\":" << event.stream_id
                 << ",\"total_us\":" << event.graph_execution_id;
      break;
    case desmond::TraceEventType::batch_formed:
      properties << ",\"batch_row\":" << event.value0
                 << ",\"batch_shape_value\":" << event.value1
                 << ",\"request_context_tokens\":" << event.graph_node_id
                 << ",\"slot_id\":" << event.stream_id;
      break;
    case desmond::TraceEventType::request_failed:
    case desmond::TraceEventType::request_cancelled:
      if (event.stream_id != std::numeric_limits<std::uint32_t>::max()) {
        properties << ",\"slot_id\":" << event.stream_id;
      }
      break;
    case desmond::TraceEventType::prefill_batch:
      properties << ",\"batch_size\":" << event.value0
                 << ",\"computed_tokens\":" << event.value1
                 << ",\"duration_us\":" << event.graph_execution_id;
      if (event.request_id_high != 0 || event.request_id_low != 0) {
        properties << ",\"slot_id\":" << event.stream_id;
      } else {
        properties << ",\"execution_flags\":" << event.stream_id;
      }
      break;
    case desmond::TraceEventType::decode_batch:
    case desmond::TraceEventType::speculative_batch:
      properties << ",\"batch_size\":" << event.value0
                 << ",\"maximum_context_tokens\":" << event.value1
                 << ",\"duration_us\":" << event.graph_execution_id
                 << ",\"cache_layout\":"
                 << desmond::json_string(event.stream_id == 1 ? "contiguous" : "fragmented");
      break;
    default:
      properties << ",\"value0\":" << event.value0 << ",\"value1\":" << event.value1
                 << ",\"duration_us\":" << event.graph_execution_id;
      break;
  }
  properties << '}';
  return properties.str();
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const bool observe_only = argc == 2 && std::string(argv[1]) == "--observe";
    int command_start = observe_only ? argc : 1;
    if (argc > 1 && std::string(argv[1]) == "--") {
      command_start = 2;
    }
    if (!observe_only && argc <= command_start) {
      std::cerr << "usage: desmondd --observe | -- <runtime> [arguments...]\n";
      return 64;
    }
    std::vector<std::string> command;
    for (int index = command_start; index < argc; ++index) {
      command.emplace_back(argv[index]);
    }
    const std::string runtime_api_key = environment("DESMOND_RUNTIME_API_KEY", "");
    const std::string runtime_api_key_mode = environment("DESMOND_RUNTIME_API_KEY_MODE", "argument");
    if (!observe_only && !runtime_api_key.empty() &&
        runtime_api_key_mode == "argument") {
      command.emplace_back("--api-key");
      command.push_back(runtime_api_key);
    } else if (runtime_api_key_mode != "argument" &&
               runtime_api_key_mode != "environment") {
      throw std::runtime_error("DESMOND_RUNTIME_API_KEY_MODE must be argument or environment");
    }

    const std::string control_host = environment("DESMOND_CONTROL_HOST", "0.0.0.0");
    const auto control_port = environment_port("DESMOND_CONTROL_PORT", 9090);
    const std::string runtime_host = environment("DESMOND_RUNTIME_HOST", "127.0.0.1");
    const auto runtime_port = environment_port("DESMOND_RUNTIME_PORT", 30000);
    const std::string runtime_health_path = environment("DESMOND_RUNTIME_HEALTH_PATH", "/health");
    const std::string release = environment("DESMOND_RELEASE", "unknown");
    const std::string model = environment("DESMOND_MODEL", "unknown");
    const std::string model_revision = environment("DESMOND_MODEL_REVISION", "unknown");
    const std::string control_token = token_from_environment(
        "DESMOND_CONTROL_TOKEN", "DESMOND_CONTROL_TOKEN_FILE");
    const std::string deployment_id = environment("DESMOND_DEPLOYMENT_ID", "");

    desmond::ProfilingUploader profiling({
        .host = environment("DESMOND_PROFILING_HOST", ""),
        .port = environment_port("DESMOND_PROFILING_PORT", 80),
        .path = environment("DESMOND_PROFILING_PATH", "/v1/profiling-events"),
        .token = environment("DESMOND_PROFILING_TOKEN", ""),
        .deployment_id = deployment_id,
        .model_id = model,
        .runtime_revision = release,
    });
    const auto maximum_concurrency =
        environment_u64("DESMOND_MAXIMUM_CONCURRENCY", 1);
    const auto kv_usage_limit = environment_double("DESMOND_KV_USAGE_LIMIT", 0.90);
    const auto waiting_request_limit = environment_u64(
        "DESMOND_WAITING_REQUEST_LIMIT", maximum_concurrency);
    desmond::StatusReporter status_reporter({
        .host = environment("DESMOND_STATUS_HOST", ""),
        .port = environment_port("DESMOND_STATUS_PORT", 80),
        .path = environment("DESMOND_STATUS_PATH", "/v1/deployment-status"),
        .token = token_from_environment("DESMOND_STATUS_TOKEN",
                                        "DESMOND_STATUS_TOKEN_FILE"),
        .deployment_id = deployment_id,
        .runtime_revision = release,
        .maximum_concurrency = maximum_concurrency,
        .interval = std::chrono::seconds(1),
        .url = environment("DESMOND_STATUS_URL", ""),
    });
    if (observe_only && (!status_reporter.enabled() || release == "unknown" ||
                         model == "unknown")) {
      throw std::runtime_error("observer requires deployment identity and "
                               "status reporting configuration");
    }

    std::unique_ptr<desmond::SharedTraceRing> trace_ring;
    // Containers normally run desmondd as PID 1. Include a per-start nonce so a stale file from
    // an unclean container exit cannot silently disable request-level telemetry on restart.
    const std::string default_trace_path = unique_trace_path();
    const std::string trace_path = environment("DESMOND_TRACE_PATH", default_trace_path.c_str());
    try {
      if (!observe_only) {
        trace_ring = desmond::SharedTraceRing::create(trace_path, 65'536);
        if (setenv("DESMOND_TRACE_PATH", trace_path.c_str(), 1) != 0) {
          throw std::runtime_error("failed to export DESMOND_TRACE_PATH");
        }
      }
    } catch (const std::exception& error) {
      unsetenv("DESMOND_TRACE_PATH");
      std::cerr << "desmond: shared trace ring unavailable: " << error.what() << '\n';
      trace_ring.reset();
    }
    std::atomic<std::uint64_t> consumed_trace_events{0};

    signal(SIGTERM, handle_signal);
    signal(SIGINT, handle_signal);

    desmond::GpuMetrics gpu_metrics;
    if (!gpu_metrics.available()) {
      std::cerr << "desmond: NVML unavailable at startup: " << gpu_metrics.error() << '\n';
    }
    desmond::RuntimeSupervisor supervisor(
        command, runtime_host, runtime_port, runtime_health_path,
        std::chrono::seconds(30), observe_only);
    if (!supervisor.start()) {
      std::cerr << "desmond: failed to start runtime\n";
      return 70;
    }

    desmond::HttpServer server(control_host, control_port, [&](const desmond::HttpRequest& request) {
      const auto status = supervisor.status();
      const bool ready = status.runtime_ready && !status.draining &&
                         (!observe_only || status_reporter.recently_uploaded());
      if (request.method != "GET") {
        return desmond::HttpResponse{405, "text/plain; charset=utf-8", "method not allowed\n"};
      }
      if (request.path == "/health/live") {
        return desmond::HttpResponse{200, "text/plain; charset=utf-8", "ok\n"};
      }
      if (request.path == "/health/ready" || request.path == "/health") {
        return desmond::HttpResponse{ready ? 200 : 503,
                                     "text/plain; charset=utf-8",
                                     ready ? "ready\n" : "not ready\n"};
      }
      if (request.path == "/metrics") {
        std::ostringstream metrics;
        metrics << "# HELP desmond_runtime_running Whether the supervised runtime process is running.\n"
                << "# TYPE desmond_runtime_running gauge\n"
                << "desmond_runtime_running " << (status.child_running ? 1 : 0) << '\n'
                << "# HELP desmond_runtime_ready Whether the runtime health endpoint is ready.\n"
                << "# TYPE desmond_runtime_ready gauge\n"
                << "desmond_runtime_ready " << (status.runtime_ready ? 1 : 0) << '\n'
                << "desmond_runtime_starts_total " << status.starts << '\n'
                << "desmond_runtime_unexpected_exits_total " << status.unexpected_exits << '\n'
                << "desmond_release_info{release=\"" << json_escape(release)
                << "\",model=\"" << json_escape(model) << "\",model_revision=\""
                << json_escape(model_revision) << "\"} 1\n"
                << gpu_metrics.prometheus()
                << profiling.prometheus()
                << status_reporter.prometheus()
                << "desmond_trace_enabled " << (trace_ring ? 1 : 0) << '\n'
                << "desmond_trace_consumed_events_total "
                << consumed_trace_events.load(std::memory_order_relaxed) << '\n'
                << "desmond_trace_dropped_events_total "
                << (trace_ring ? trace_ring->dropped() : 0) << '\n';
        const auto upstream = desmond::http_get(runtime_host, runtime_port, "/metrics",
                                                std::chrono::seconds(2));
        if (upstream.transport_ok && upstream.status == 200) {
          metrics << "\n# SGLang runtime metrics\n" << upstream.body;
        }
        return desmond::HttpResponse{200, "text/plain; version=0.0.4; charset=utf-8", metrics.str()};
      }
      if (request.path == "/v1/desmond/status") {
        if (!control_token.empty() && request.authorization != "Bearer " + control_token) {
          return desmond::HttpResponse{401, "application/json", "{\"error\":\"unauthorized\"}\n"};
        }
        std::ostringstream body;
        body << "{\"child_running\":" << (status.child_running ? "true" : "false")
             << ",\"runtime_ready\":" << (status.runtime_ready ? "true" : "false")
             << ",\"draining\":" << (status.draining ? "true" : "false")
             << ",\"pid\":" << status.pid << ",\"starts\":" << status.starts
             << ",\"unexpected_exits\":" << status.unexpected_exits
             << ",\"release\":\"" << json_escape(release) << "\",\"model\":\""
             << json_escape(model) << "\",\"model_revision\":\""
             << json_escape(model_revision) << "\"}\n";
        return desmond::HttpResponse{200, "application/json", body.str()};
      }
      return desmond::HttpResponse{404, "text/plain; charset=utf-8", "not found\n"};
    });

    std::thread http_thread([&] {
      try {
        server.run();
      } catch (const std::exception& error) {
        std::cerr << "desmond: HTTP server failed: " << error.what() << '\n';
        stop_requested.store(true, std::memory_order_relaxed);
      }
    });

    auto next_health = std::chrono::steady_clock::now();
    auto next_status = std::chrono::steady_clock::now();
    auto next_gpu_profile = std::chrono::steady_clock::now();
    auto next_runtime_profile = std::chrono::steady_clock::now();
    bool prior_ready = false;
    const auto drain_trace = [&](const std::size_t maximum_events) {
      if (!trace_ring) return;
      desmond::TraceEvent event;
      std::size_t consumed = 0;
      while (consumed < maximum_events && trace_ring->try_pop(event)) {
        profiling.enqueue(std::string("runtime.") + desmond::trace_event_type_name(event.type),
                          trace_properties(event));
        ++consumed;
      }
      consumed_trace_events.fetch_add(consumed, std::memory_order_relaxed);
    };
    profiling.enqueue(observe_only ? "observer.started" : "runtime.started",
                      "{\"pid\":" + std::to_string(supervisor.status().pid) +
                          "}");
    while (!stop_requested.load(std::memory_order_relaxed)) {
      drain_trace(4'096);
      supervisor.poll();
      const auto status = supervisor.status();
      if (!observe_only && !status.child_running) {
        std::cerr << "desmond: runtime exited with code " << status.last_exit_code << '\n';
        stop_requested.store(true, std::memory_order_relaxed);
        break;
      }
      if (std::chrono::steady_clock::now() >= next_health) {
        supervisor.check_health();
        next_health = std::chrono::steady_clock::now() + std::chrono::seconds(1);
      }
      const auto current = supervisor.status();
      if (current.runtime_ready != prior_ready) {
        profiling.enqueue("runtime.state", std::string("{\"ready\":") +
                                               (current.runtime_ready ? "true}" : "false}"));
        prior_ready = current.runtime_ready;
      }
      if (std::chrono::steady_clock::now() >= next_status) {
        desmond::RuntimePressure pressure;
        bool metrics_available = false;
        if (current.runtime_ready) {
          const auto runtime_metrics = desmond::http_get(
              runtime_host, runtime_port, "/metrics", std::chrono::milliseconds(750));
          if (runtime_metrics.transport_ok && runtime_metrics.status == 200) {
            metrics_available = true;
            pressure = desmond::parse_runtime_pressure(
                runtime_metrics.body, kv_usage_limit, waiting_request_limit,
                maximum_concurrency);
          }
        }
        desmond::DeploymentStatusSnapshot snapshot;
        snapshot.healthy = current.child_running && current.runtime_ready;
        snapshot.accepting_requests =
            snapshot.healthy && !current.draining &&
            (!observe_only || metrics_available) && !pressure.kv_pressure &&
            !pressure.queue_pressure && !pressure.concurrency_pressure;
        if (!snapshot.healthy) {
          snapshot.reason_code = "runtime_unavailable";
        } else if (current.draining) {
          snapshot.reason_code = "draining";
        } else if (observe_only && !metrics_available) {
          snapshot.reason_code = "metrics_unavailable";
        } else if (pressure.kv_pressure) {
          snapshot.reason_code = "kv_pressure";
        } else if (pressure.queue_pressure) {
          snapshot.reason_code = "queue_pressure";
        } else if (pressure.concurrency_pressure) {
          snapshot.reason_code = "concurrency_full";
        }
        status_reporter.update(std::move(snapshot));
        next_status = std::chrono::steady_clock::now() + std::chrono::seconds(1);
      }
      if (std::chrono::steady_clock::now() >= next_gpu_profile) {
        for (const auto& gpu : gpu_metrics.sample()) {
          std::ostringstream properties;
          properties << "{\"gpu_index\":" << gpu.index
                     << ",\"gpu_uuid\":" << desmond::json_string(gpu.uuid)
                     << ",\"gpu_utilization_percent\":" << gpu.gpu_utilization_percent
                     << ",\"memory_utilization_percent\":" << gpu.memory_utilization_percent
                     << ",\"memory_total_bytes\":" << gpu.memory_total_bytes
                     << ",\"memory_used_bytes\":" << gpu.memory_used_bytes
                     << ",\"memory_free_bytes\":" << gpu.memory_free_bytes
                     << ",\"temperature_celsius\":" << gpu.temperature_celsius
                     << ",\"power_milliwatts\":" << gpu.power_milliwatts
                     << ",\"total_energy_millijoules\":" << gpu.total_energy_millijoules
                     << '}';
          profiling.enqueue("gpu.sample", properties.str());
        }
        next_gpu_profile = std::chrono::steady_clock::now() + std::chrono::seconds(5);
      }
      if (current.runtime_ready && std::chrono::steady_clock::now() >= next_runtime_profile) {
        const auto runtime_metrics = desmond::http_get(runtime_host, runtime_port, "/metrics",
                                                       std::chrono::seconds(2));
        if (runtime_metrics.transport_ok && runtime_metrics.status == 200) {
          profiling.enqueue("runtime.metrics_snapshot",
                            "{\"prometheus_text\":" +
                                desmond::json_string(runtime_metrics.body) + "}");
        }
        next_runtime_profile = std::chrono::steady_clock::now() + std::chrono::seconds(15);
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    profiling.enqueue(observe_only ? "observer.stopping" : "runtime.stopping",
                      "{}");
    supervisor.shutdown();
    status_reporter.update({.healthy = false,
                            .accepting_requests = false,
                            .reason_code = "draining"});
    drain_trace(65'536);
    profiling.stop();
    status_reporter.stop();
    server.stop();
    http_thread.join();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "desmond: fatal: " << error.what() << '\n';
    return 70;
  }
}
