#include "desmond/http.h"
#include "desmond/supervisor.h"
#include "desmond/trace.h"

#include <chrono>
#include <cstdlib>
#include <iostream>
#include <thread>

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

}  // namespace

int main() {
  test_trace_ring();
  test_supervisor_lifecycle();
  test_http_server();
  test_http_stream();
  std::cout << "desmond tests passed\n";
  return 0;
}
