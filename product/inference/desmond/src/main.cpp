#include "desmond/gpu_metrics.h"
#include "desmond/http.h"
#include "desmond/profiling.h"
#include "desmond/supervisor.h"

#include <signal.h>

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace {

std::atomic<bool> stop_requested{false};

void handle_signal(int) { stop_requested.store(true, std::memory_order_relaxed); }

std::string environment(const char* name, const char* fallback) {
  const char* value = std::getenv(name);
  return value == nullptr || *value == '\0' ? fallback : value;
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

}  // namespace

int main(int argc, char** argv) {
  try {
    int command_start = 1;
    if (argc > 1 && std::string(argv[1]) == "--") {
      command_start = 2;
    }
    if (argc <= command_start) {
      std::cerr << "usage: desmondd -- <runtime> [arguments...]\n";
      return 64;
    }
    std::vector<std::string> command;
    for (int index = command_start; index < argc; ++index) {
      command.emplace_back(argv[index]);
    }
    const std::string runtime_api_key = environment("DESMOND_RUNTIME_API_KEY", "");
    const std::string runtime_api_key_mode = environment("DESMOND_RUNTIME_API_KEY_MODE", "argument");
    if (!runtime_api_key.empty() && runtime_api_key_mode == "argument") {
      command.emplace_back("--api-key");
      command.push_back(runtime_api_key);
    } else if (runtime_api_key_mode != "argument" && runtime_api_key_mode != "environment") {
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
    const std::string control_token = environment("DESMOND_CONTROL_TOKEN", "");
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

    signal(SIGTERM, handle_signal);
    signal(SIGINT, handle_signal);

    desmond::GpuMetrics gpu_metrics;
    if (!gpu_metrics.available()) {
      std::cerr << "desmond: NVML unavailable at startup: " << gpu_metrics.error() << '\n';
    }
    desmond::RuntimeSupervisor supervisor(command, runtime_host, runtime_port,
                                          runtime_health_path, std::chrono::seconds(30));
    if (!supervisor.start()) {
      std::cerr << "desmond: failed to start runtime\n";
      return 70;
    }

    desmond::HttpServer server(control_host, control_port, [&](const desmond::HttpRequest& request) {
      const auto status = supervisor.status();
      if (request.method != "GET") {
        return desmond::HttpResponse{405, "text/plain; charset=utf-8", "method not allowed\n"};
      }
      if (request.path == "/health/live") {
        return desmond::HttpResponse{200, "text/plain; charset=utf-8", "ok\n"};
      }
      if (request.path == "/health/ready" || request.path == "/health") {
        return desmond::HttpResponse{status.runtime_ready && !status.draining ? 200 : 503,
                                     "text/plain; charset=utf-8",
                                     status.runtime_ready && !status.draining ? "ready\n" : "not ready\n"};
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
                << profiling.prometheus();
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
    auto next_gpu_profile = std::chrono::steady_clock::now();
    auto next_runtime_profile = std::chrono::steady_clock::now();
    bool prior_ready = false;
    profiling.enqueue("runtime.started", "{\"pid\":" +
                                            std::to_string(supervisor.status().pid) + "}");
    while (!stop_requested.load(std::memory_order_relaxed)) {
      supervisor.poll();
      const auto status = supervisor.status();
      if (!status.child_running) {
        std::cerr << "desmond: runtime exited with code " << status.last_exit_code << '\n';
        stop_requested.store(true, std::memory_order_relaxed);
        break;
      }
      if (std::chrono::steady_clock::now() >= next_health) {
        supervisor.check_health();
        next_health = std::chrono::steady_clock::now() + std::chrono::seconds(2);
      }
      const auto current = supervisor.status();
      if (current.runtime_ready != prior_ready) {
        profiling.enqueue("runtime.state", std::string("{\"ready\":") +
                                               (current.runtime_ready ? "true}" : "false}"));
        prior_ready = current.runtime_ready;
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

    profiling.enqueue("runtime.stopping", "{}");
    supervisor.shutdown();
    profiling.stop();
    server.stop();
    http_thread.join();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "desmond: fatal: " << error.what() << '\n';
    return 70;
  }
}
