#include "desmond/http_client.h"

#include "test_support.h"

#include <chrono>
#include <cstdint>
#include <sstream>
#include <string>
#include <thread>
#include <variant>

namespace {

using namespace std::chrono_literals;
using desmond::testing::closed_port;
using desmond::testing::local_url;
using desmond::testing::RecordingServer;
using desmond::testing::respond_with;
using desmond::testing::ScriptedListener;
using desmond::testing::TestHttpServer;

desmond::HttpResult get(const std::string &url, const std::chrono::milliseconds timeout = 1s) {
  return desmond::http_request({.url = url, .timeout = timeout});
}

bool failed_with(const desmond::HttpResult &result, const desmond::TransportError error) {
  const auto *actual = std::get_if<desmond::TransportError>(&result);
  return actual != nullptr && *actual == error;
}

const desmond::HttpReply *reply_of(const desmond::HttpResult &result) {
  return std::get_if<desmond::HttpReply>(&result);
}

DESMOND_TEST(get_returns_status_and_body) {
  const TestHttpServer server(respond_with(503, "not ready\n"));

  const auto result = get(local_url(server.port(), "/health"));

  const auto *reply = reply_of(result);
  CHECK(reply != nullptr && reply->status == 503 && reply->body == "not ready\n");
}

DESMOND_TEST(closed_port_is_a_connect_error) {
  CHECK(failed_with(get(local_url(closed_port())), desmond::TransportError::connect));
}

DESMOND_TEST(listener_that_never_replies_is_a_timeout) {
  const desmond::testing::ListeningSocket silent;

  const auto started = std::chrono::steady_clock::now();
  const auto result = get(local_url(silent.port()), 200ms);

  CHECK(failed_with(result, desmond::TransportError::timeout));
  CHECK(std::chrono::steady_clock::now() - started < 1s);
}

DESMOND_TEST(non_http_reply_is_malformed) {
  const ScriptedListener listener("garbage\r\n\r\n");

  CHECK(failed_with(get(local_url(listener.port())), desmond::TransportError::malformed_response));
}

DESMOND_TEST(reply_over_the_limit_is_response_too_large) {
  const TestHttpServer server(respond_with(200, std::string(4096, 'x')));

  const auto result = desmond::http_request(
      {.url = local_url(server.port()), .timeout = 1s, .max_response_bytes = 1024});

  CHECK(failed_with(result, desmond::TransportError::response_too_large));
}

DESMOND_TEST(chunked_reply_is_decoded) {
  const TestHttpServer server([](const desmond::HttpRequest &) {
    return desmond::HttpResponse{
        200, "text/event-stream", {}, [](const desmond::HttpChunkWriter &write) {
          static_cast<void>(write("data: one\n\n"));
          static_cast<void>(write("data: [DONE]\n\n"));
        }};
  });

  const auto result = get(local_url(server.port()));

  const auto *reply = reply_of(result);

  CHECK(reply != nullptr && reply->body == "data: one\n\ndata: [DONE]\n\n");
}

DESMOND_TEST(large_reply_arrives_whole) {
  const std::string body(3 * 1024 * 1024, 'b');
  const TestHttpServer server(respond_with(200, body));

  const auto result = desmond::http_request(
      {.url = local_url(server.port()), .timeout = 5s, .max_response_bytes = 4 * 1024 * 1024});

  const auto *reply = reply_of(result);
  CHECK(reply != nullptr && reply->body == body);
}

DESMOND_TEST(post_sends_authorization_and_json_body) {
  RecordingServer server;
  server.respond_with(202);
  const std::string body = "{\"a\":\"" + std::string(4096, 'x') + "\"}";

  const auto result = desmond::http_request({
      .method = desmond::HttpMethod::post,
      .url = local_url(server.port(), "/v1/ingest"),
      .authorization = "Bearer token",
      .body = body,
  });

  const auto *reply = reply_of(result);
  CHECK(reply != nullptr && reply->status == 202);
  const auto requests = server.log().requests();
  REQUIRE(requests.size() == 1);
  CHECK(requests[0].method == "POST");
  CHECK(requests[0].path == "/v1/ingest");
  CHECK(requests[0].authorization == "Bearer token");
  CHECK(requests[0].body == body);
}

DESMOND_TEST(line_break_in_authorization_is_an_invalid_request) {
  const RecordingServer ingest;

  const auto result = desmond::http_request({
      .method = desmond::HttpMethod::post,
      .url = local_url(ingest.port()),
      .authorization = "Bearer token\r\nX-Injected: 1",
  });

  CHECK(failed_with(result, desmond::TransportError::invalid_request));
  CHECK(ingest.log().size() == 0);
}

DESMOND_TEST(url_without_http_scheme_is_an_invalid_request) {
  CHECK(failed_with(get("ftp://127.0.0.1/"), desmond::TransportError::invalid_request));
  CHECK(failed_with(get("file:///etc/passwd"), desmond::TransportError::invalid_request));
}

DESMOND_TEST(https_to_a_plain_http_listener_never_succeeds) {
  const ScriptedListener listener("HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n");

  const auto result = get(local_url(listener.port(), "/", "https"));

  CHECK(failed_with(result, desmond::TransportError::tls) ||
        failed_with(result, desmond::TransportError::malformed_response));
}

DESMOND_TEST(redirects_are_not_followed) {
  const RecordingServer target;
  const ScriptedListener redirect("HTTP/1.1 302 Found\r\nLocation: " + local_url(target.port()) +
                                  "\r\nContent-Length: 0\r\n\r\n");

  const auto result = get(local_url(redirect.port()));

  const auto *reply = reply_of(result);

  CHECK(reply != nullptr && reply->status == 302);
  CHECK(target.log().size() == 0);
}

DESMOND_TEST(transport_errors_have_stable_names) {
  CHECK(std::string(desmond::to_string(desmond::TransportError::response_too_large)) ==
        "response_too_large");
  CHECK(std::string(desmond::to_string(desmond::TransportError::tls)) == "tls");
}

DESMOND_TEST(only_2xx_replies_succeed) {
  CHECK(desmond::succeeded(desmond::HttpReply{200, ""}));
  CHECK(desmond::succeeded(desmond::HttpReply{204, ""}));
  CHECK(!desmond::succeeded(desmond::HttpReply{302, ""}));
  CHECK(!desmond::succeeded(desmond::HttpReply{503, ""}));
  CHECK(!desmond::succeeded(desmond::TransportError::connect));
}

DESMOND_TEST(failure_log_records_only_transitions_with_bounded_causes) {
  std::ostringstream output;
  desmond::HttpFailureLog log("status upload", output);

  log.record(desmond::HttpReply{204, ""});
  log.record(desmond::TransportError::timeout);
  log.record(desmond::HttpReply{503, "secret body"});
  log.record(desmond::HttpReply{200, ""});
  log.record(desmond::HttpReply{503, "secret body"});

  CHECK(output.str() == "desmond: status upload failed cause=timeout\n"
                        "desmond: status upload recovered\n"
                        "desmond: status upload failed cause=http_status=503\n");
}

} // namespace
