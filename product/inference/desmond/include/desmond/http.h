#pragma once

#include <atomic>
#include <chrono>
#include <functional>
#include <string>
#include <string_view>

namespace desmond {

struct HttpRequest {
  std::string method;
  std::string path;
  std::string authorization;
};

struct HttpResponse {
  int status{200};
  std::string content_type{"text/plain; charset=utf-8"};
  std::string body;
};

using HttpHandler = std::function<HttpResponse(const HttpRequest&)>;

class HttpServer {
 public:
  HttpServer(std::string host, std::uint16_t port, HttpHandler handler);
  ~HttpServer();
  HttpServer(const HttpServer&) = delete;
  HttpServer& operator=(const HttpServer&) = delete;

  void run();
  void stop();

 private:
  std::string host_;
  std::uint16_t port_;
  HttpHandler handler_;
  std::atomic<bool> stopping_{false};
  int listen_fd_{-1};
};

struct HttpGetResult {
  bool transport_ok{false};
  int status{0};
  std::string body;
};

[[nodiscard]] HttpGetResult http_get(std::string_view host, std::uint16_t port,
                                     std::string_view path,
                                     std::chrono::milliseconds timeout);
[[nodiscard]] HttpGetResult http_post(std::string_view host, std::uint16_t port,
                                      std::string_view path,
                                      std::string_view authorization,
                                      std::string_view body,
                                      std::chrono::milliseconds timeout);

}  // namespace desmond
