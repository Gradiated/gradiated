#include "desmond/http.h"
#include "desmond/profiling.h"
#include "desmond/supervisor.h"
#include "desmond/status.h"
#include "desmond/trace.h"

#include <chrono>
#include <atomic>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <unistd.h>
#include <sys/wait.h>

namespace {

void require(const bool condition, const char* message) {
  if (!condition) {
    std::cerr << "FAILED: " << message << '\n';
    std::exit(1);
  }
}

void test_trace_ring() {
  desmond::TraceRing ring(2);
  desmond::TraceEvent first{.request_id_low = 11,
                            .type = desmond::TraceEventType::request_admitted};
  desmond::TraceEvent second{.request_id_low = 12,
                             .type = desmond::TraceEventType::batch_formed};
  require(ring.try_push(first), "first trace push");
  require(ring.try_push(second), "second trace push");
  require(!ring.try_push(first), "full trace ring rejects event");
  require(ring.dropped() == 1, "trace ring counts dropped events");
  desmond::TraceEvent output;
  require(ring.try_pop(output) && output.request_id_low == 11, "trace ring preserves order");
  require(ring.try_pop(output) && output.request_id_low == 12, "trace ring returns second event");
  require(!ring.try_pop(output), "empty trace ring");
}

void test_shared_trace_ring() {
  const std::string path = "/tmp/desmond-shared-trace-" + std::to_string(getpid());
  auto consumer = desmond::SharedTraceRing::create(path, 2);
  auto producer = desmond::SharedTraceRing::open_existing(path);
  const desmond::TraceEvent first{.request_id_low = 21,
                                  .type = desmond::TraceEventType::prefill_batch};
  const desmond::TraceEvent second{.request_id_low = 22,
                                   .type = desmond::TraceEventType::decode_batch};
  require(producer->try_push(first), "first shared trace push");
  require(producer->try_push(second), "second shared trace push");
  require(!producer->try_push(first), "full shared trace ring rejects event");
  require(consumer->dropped() == 1, "shared trace ring counts cross-process drops");
  desmond::TraceEvent output;
  require(consumer->try_pop(output) && output.request_id_low == 21,
          "shared trace ring preserves first event");
  require(consumer->try_pop(output) && output.request_id_low == 22,
          "shared trace ring preserves second event");
  require(!consumer->try_pop(output), "shared trace ring reports empty");
}

void test_shared_trace_ring_cross_process() {
  const std::string path = "/tmp/desmond-shared-trace-fork-" + std::to_string(getpid());
  auto consumer = desmond::SharedTraceRing::create(path, 8);
  const pid_t child = fork();
  require(child >= 0, "fork shared trace producer");
  if (child == 0) {
    try {
      auto producer = desmond::SharedTraceRing::open_existing(path);
      const bool pushed = producer->try_push({
          .request_id_low = 31,
          .type = desmond::TraceEventType::request_finished,
      });
      _exit(pushed ? 0 : 1);
    } catch (...) {
      _exit(2);
    }
  }
  int status = 0;
  require(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0,
          "child writes shared trace event");
  desmond::TraceEvent output;
  require(consumer->try_pop(output) && output.request_id_low == 31,
          "parent reads child trace event");
}

void test_supervisor_lifecycle() {
  desmond::RuntimeSupervisor supervisor({"/bin/sleep", "30"}, "127.0.0.1", 1, "/health",
                                        std::chrono::seconds(1));
  require(supervisor.start(), "supervisor starts child");
  require(supervisor.status().child_running, "child is marked running");
  supervisor.shutdown();
  require(!supervisor.status().child_running, "child stops on shutdown");
}

void test_http_server() {
  desmond::HttpServer server("127.0.0.1", 19091, [](const desmond::HttpRequest& request) {
    return desmond::HttpResponse{request.path == "/ok" ? 200 : 404,
                                 "text/plain; charset=utf-8", "test\n"};
  });
  std::thread thread([&] { server.run(); });
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  const auto response = desmond::http_get("127.0.0.1", 19091, "/ok", std::chrono::seconds(1));
  require(response.transport_ok && response.status == 200 && response.body == "test\n",
          "HTTP server round trip");
  server.stop();
  thread.join();
}

void test_http_stream() {
  desmond::HttpServer server("127.0.0.1", 19092, [](const desmond::HttpRequest&) {
    return desmond::HttpResponse{
        200, "text/event-stream", {}, [](const desmond::HttpChunkWriter& write) {
          require(write("data: one\n\n"), "first HTTP stream write");
          require(write("data: [DONE]\n\n"), "second HTTP stream write");
        }};
  });
  std::thread thread([&] { server.run(); });
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  const auto response = desmond::http_get("127.0.0.1", 19092, "/stream",
                                          std::chrono::seconds(1));
  require(response.transport_ok && response.status == 200 &&
              response.body.find("data: one") != std::string::npos &&
              response.body.find("data: [DONE]") != std::string::npos,
          "HTTP chunked stream round trip");
  server.stop();
  thread.join();
}

void test_http_burst_remains_responsive() {
  desmond::HttpServer server("127.0.0.1", 19093, [](const desmond::HttpRequest&) {
    return desmond::HttpResponse{200, "text/plain; charset=utf-8", "ready\n"};
  });
  std::thread server_thread([&] { server.run(); });
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  std::atomic<int> failures{0};
  std::vector<std::thread> clients;
  for (int worker = 0; worker < 32; ++worker) {
    clients.emplace_back([&] {
      for (int request = 0; request < 16; ++request) {
        const auto response = desmond::http_get(
            "127.0.0.1", 19093, "/health", std::chrono::seconds(2));
        if (!response.transport_ok || response.status != 200) failures.fetch_add(1);
      }
    });
  }
  for (auto& client : clients) client.join();
  const auto final = desmond::http_get(
      "127.0.0.1", 19093, "/metrics", std::chrono::seconds(2));
  require(failures.load() == 0 && final.transport_ok && final.status == 200,
          "HTTP server remains responsive after a connection burst");
  server.stop();
  server_thread.join();
}

void test_profiling_retry_is_idempotent_and_backed_off() {
  std::atomic<int> requests{0};
  std::mutex bodies_mutex;
  std::vector<std::string> bodies;
  desmond::HttpServer server("127.0.0.1", 19094, [&](const desmond::HttpRequest& request) {
    {
      std::lock_guard lock(bodies_mutex);
      bodies.push_back(request.body);
    }
    const int attempt = requests.fetch_add(1) + 1;
    return desmond::HttpResponse{attempt == 1 ? 500 : 204,
                                 "application/json", attempt == 1 ? "{}\n" : ""};
  });
  std::thread server_thread([&] { server.run(); });
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  desmond::ProfilingUploader uploader({
      .host = "127.0.0.1",
      .port = 19094,
      .token = "profiling-test-token-with-at-least-32-characters",
      .deployment_id = "00000000-0000-4000-8000-000000000001",
      .model_id = "test/model",
      .runtime_revision = "test",
      .batch_size = 1,
      .flush_interval = std::chrono::seconds(1),
      .retry_initial = std::chrono::milliseconds(100),
      .retry_maximum = std::chrono::milliseconds(100),
  });
  uploader.enqueue("runtime.test", "{\"value\":1}");
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
  while (requests.load() < 2 && std::chrono::steady_clock::now() < deadline) {
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }
  uploader.stop();
  server.stop();
  server_thread.join();
  require(requests.load() == 2, "profiling uploader retries one failed batch");
  std::lock_guard lock(bodies_mutex);
  require(bodies.size() == 2 && bodies[0] == bodies[1],
          "profiling retry preserves the batch id and body");
}

void test_runtime_pressure_uses_vllm_metrics() {
  const auto pressure = desmond::parse_runtime_pressure(
      "vllm:kv_cache_usage_perc 0.95\n"
      "vllm:num_requests_waiting 2\n"
      "vllm:num_requests_running 4\n",
      0.90);
  require(pressure.kv_pressure, "KV pressure threshold is applied");
}

void test_runtime_pressure_ignores_batch_counters() {
  // The engine owns request admission. Batch counters track engine state, not
  // a capacity limit, so they must not mark the deployment as not accepting.
  // vLLM rejects excess load with HTTP 503 once its own queue limit is hit.
  const auto pressure = desmond::parse_runtime_pressure(
      "vllm:kv_cache_usage_perc 0.10\n"
      "vllm:num_requests_waiting 50\n"
      "vllm:num_requests_running 999\n",
      0.90);
  require(!pressure.kv_pressure, "low KV usage is not pressure");
}

}  // namespace

int main() {
  test_trace_ring();
  test_shared_trace_ring();
  test_shared_trace_ring_cross_process();
  test_supervisor_lifecycle();
  test_http_server();
  test_http_stream();
  test_http_burst_remains_responsive();
  test_profiling_retry_is_idempotent_and_backed_off();
  test_runtime_pressure_uses_vllm_metrics();
  test_runtime_pressure_ignores_batch_counters();
  std::cout << "desmond tests passed\n";
  return 0;
}
