#include "desmond/http_client.h"

#include <curl/curl.h>

#include <memory>
#include <utility>

namespace desmond {
namespace {

struct CurlDeleter {
  void operator()(CURL *handle) const {
    curl_easy_cleanup(handle);
  }
};

struct HeaderListDeleter {
  void operator()(curl_slist *list) const {
    curl_slist_free_all(list);
  }
};

using CurlHandle = std::unique_ptr<CURL, CurlDeleter>;
using HeaderList = std::unique_ptr<curl_slist, HeaderListDeleter>;

struct ResponseBuffer {
  std::string body;
  std::size_t limit{};
  bool overflowed{false};
};

std::size_t collect_response(char *data, const std::size_t size, const std::size_t count,
                             void *user_data) {
  auto &response = *static_cast<ResponseBuffer *>(user_data);
  const auto bytes = size * count;
  if (bytes > response.limit - response.body.size()) {
    response.overflowed = true;
    return 0;
  }

  response.body.append(data, bytes);
  return bytes;
}

bool append_header(HeaderList &headers, const std::string &header) {
  curl_slist *appended = curl_slist_append(headers.get(), header.c_str());
  if (appended == nullptr) {
    return false;
  }

  static_cast<void>(headers.release());
  headers.reset(appended);
  return true;
}

bool curl_ready() {
  static const CURLcode initialized = curl_global_init(CURL_GLOBAL_DEFAULT);
  return initialized == CURLE_OK;
}

std::optional<const char *> allowed_protocol(const std::string_view url) {
  if (url.starts_with("https://")) {
    return "https";
  }
  if (url.starts_with("http://")) {
    return "http";
  }

  return std::nullopt;
}

TransportError transport_error(const CURLcode code) {
  switch (code) {
  case CURLE_COULDNT_RESOLVE_HOST:
    return TransportError::resolve;
  case CURLE_COULDNT_CONNECT:
    return TransportError::connect;
  case CURLE_OPERATION_TIMEDOUT:
    return TransportError::timeout;
  case CURLE_PEER_FAILED_VERIFICATION:
  case CURLE_SSL_CONNECT_ERROR:
  case CURLE_SSL_CERTPROBLEM:
  case CURLE_SSL_CIPHER:
  case CURLE_SSL_CACERT_BADFILE:
  case CURLE_SSL_ENGINE_NOTFOUND:
  case CURLE_SSL_ENGINE_SETFAILED:
  case CURLE_SSL_ENGINE_INITFAILED:
  case CURLE_SSL_SHUTDOWN_FAILED:
  case CURLE_SSL_CRL_BADFILE:
  case CURLE_SSL_ISSUER_ERROR:
  case CURLE_SSL_PINNEDPUBKEYNOTMATCH:
  case CURLE_SSL_INVALIDCERTSTATUS:
    return TransportError::tls;
  case CURLE_WEIRD_SERVER_REPLY:
  case CURLE_UNSUPPORTED_PROTOCOL:
    return TransportError::malformed_response;
  default:
    return TransportError::transfer;
  }
}

} // namespace

const char *to_string(const TransportError error) {
  switch (error) {
  case TransportError::invalid_request:
    return "invalid_request";
  case TransportError::resolve:
    return "resolve";
  case TransportError::connect:
    return "connect";
  case TransportError::timeout:
    return "timeout";
  case TransportError::tls:
    return "tls";
  case TransportError::malformed_response:
    return "malformed_response";
  case TransportError::response_too_large:
    return "response_too_large";
  case TransportError::transfer:
    return "transfer";
  }

  return "transfer";
}

std::string http_url(const std::string_view host, const std::uint16_t port,
                     const std::string_view path) {
  return "http://" + std::string(host) + ':' + std::to_string(port) + std::string(path);
}

HttpResult http_request(const HttpRequestSpec &spec) {
  const auto protocol = allowed_protocol(spec.url);
  const bool header_injection =
      spec.authorization && spec.authorization->find_first_of("\r\n") != std::string::npos;
  if (!protocol || header_injection) {
    return TransportError::invalid_request;
  }

  if (!curl_ready()) {
    return TransportError::transfer;
  }

  CurlHandle curl(curl_easy_init());
  if (!curl) {
    return TransportError::transfer;
  }

  HeaderList headers;
  const bool post = spec.method == HttpMethod::post;
  if (spec.authorization && !append_header(headers, "Authorization: " + *spec.authorization)) {
    return TransportError::transfer;
  }
  if (post && (!append_header(headers, "Content-Type: application/json") ||
               !append_header(headers, "Expect:"))) {
    return TransportError::transfer;
  }

  ResponseBuffer response{.limit = spec.max_response_bytes};
  auto *handle = curl.get();

  // Only the URL's own scheme is allowed, TLS peers and hostnames are verified, proxy variables
  // are ignored and redirects are refused, so a bearer token reaches only the configured endpoint.
  curl_easy_setopt(handle, CURLOPT_URL, spec.url.c_str());
#if LIBCURL_VERSION_NUM >= 0x075500
  curl_easy_setopt(handle, CURLOPT_PROTOCOLS_STR, *protocol);
#else
  curl_easy_setopt(handle, CURLOPT_PROTOCOLS,
                   spec.url.starts_with("https://") ? CURLPROTO_HTTPS : CURLPROTO_HTTP);
#endif
  curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 0L);
  curl_easy_setopt(handle, CURLOPT_SSL_VERIFYPEER, 1L);
  curl_easy_setopt(handle, CURLOPT_SSL_VERIFYHOST, 2L);
  curl_easy_setopt(handle, CURLOPT_PROXY, "");
  curl_easy_setopt(handle, CURLOPT_NOSIGNAL, 1L);
  curl_easy_setopt(handle, CURLOPT_TIMEOUT_MS, static_cast<long>(spec.timeout.count()));
  curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT_MS, static_cast<long>(spec.timeout.count()));
  curl_easy_setopt(handle, CURLOPT_HTTPHEADER, headers.get());
  curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, collect_response);
  curl_easy_setopt(handle, CURLOPT_WRITEDATA, &response);
  if (post) {
    curl_easy_setopt(handle, CURLOPT_POSTFIELDS, spec.body.data());
    curl_easy_setopt(handle, CURLOPT_POSTFIELDSIZE_LARGE,
                     static_cast<curl_off_t>(spec.body.size()));
  }

  const CURLcode code = curl_easy_perform(handle);
  if (response.overflowed) {
    return TransportError::response_too_large;
  }
  if (code != CURLE_OK) {
    return transport_error(code);
  }

  long status = 0;
  curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &status);
  return HttpReply{static_cast<int>(status), std::move(response.body)};
}

bool succeeded(const HttpResult &result) {
  const auto *reply = std::get_if<HttpReply>(&result);
  return reply != nullptr && reply->status >= 200 && reply->status < 300;
}

HttpFailureLog::HttpFailureLog(std::string subject, std::ostream &output)
    : subject_(std::move(subject)), output_(output) {}

void HttpFailureLog::record(const HttpResult &result) {
  const bool failed = !succeeded(result);
  if (failed == failing_) {
    return;
  }

  failing_ = failed;
  if (!failed) {
    output_ << "desmond: " << subject_ << " recovered\n";
    return;
  }

  output_ << "desmond: " << subject_ << " failed cause=";
  if (const auto *reply = std::get_if<HttpReply>(&result)) {
    output_ << "http_status=" << reply->status << '\n';
  } else {
    output_ << to_string(std::get<TransportError>(result)) << '\n';
  }
}

} // namespace desmond
