#pragma once

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <ostream>
#include <string>
#include <string_view>
#include <variant>

namespace desmond {

enum class HttpMethod { get, post };

struct HttpRequestSpec {
  HttpMethod method{HttpMethod::get};
  std::string url;
  std::optional<std::string> authorization;
  std::string body;
  std::chrono::milliseconds timeout{2000};
  std::size_t max_response_bytes{64 * 1024};
};

struct HttpReply {
  int status{};
  std::string body;
};

enum class TransportError {
  invalid_request,
  resolve,
  connect,
  timeout,
  tls,
  malformed_response,
  response_too_large,
  transfer,
};

using HttpResult = std::variant<HttpReply, TransportError>;

[[nodiscard]] const char *to_string(TransportError error);
[[nodiscard]] std::string http_url(std::string_view host, std::uint16_t port,
                                   std::string_view path);
[[nodiscard]] HttpResult http_request(const HttpRequestSpec &spec);
[[nodiscard]] bool succeeded(const HttpResult &result);

class HttpFailureLog {
public:
  HttpFailureLog(std::string subject, std::ostream &output);

  void record(const HttpResult &result);

private:
  std::string subject_;
  std::ostream &output_;
  bool failing_{false};
};

} // namespace desmond
