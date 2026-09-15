#include "desmond/http.h"

#include <curl/curl.h>

#include <mutex>
#include <string>

namespace desmond {
namespace {
size_t discard_response(char *, size_t size, size_t count, void *userdata) {
  auto &received = *static_cast<size_t *>(userdata);
  if (size != 0 && count > (64 * 1024 - received) / size)
    return 0;
  const auto bytes = size * count;
  received += bytes;
  return bytes;
}
} // namespace

HttpGetResult https_post(const std::string_view url,
                         const std::string_view authorization,
                         const std::string_view body,
                         const std::chrono::milliseconds timeout) {
  HttpGetResult result;
  if (!url.starts_with("https://") ||
      authorization.find_first_of("\r\n") != std::string_view::npos)
    return result;
  static std::once_flag initialized;
  static CURLcode initialized_result = CURLE_FAILED_INIT;
  std::call_once(initialized, [] {
    initialized_result = curl_global_init(CURL_GLOBAL_DEFAULT);
  });
  if (initialized_result != CURLE_OK)
    return result;
  auto *curl = curl_easy_init();
  if (!curl)
    return result;
  const std::string target(url);
  const std::string bearer = "Authorization: " + std::string(authorization);
  curl_slist *headers =
      curl_slist_append(nullptr, "Content-Type: application/json");
  headers = curl_slist_append(headers, bearer.c_str());
  size_t received = 0;
  curl_easy_setopt(curl, CURLOPT_URL, target.c_str());
#if LIBCURL_VERSION_NUM >= 0x075500
  curl_easy_setopt(curl, CURLOPT_PROTOCOLS_STR, "https");
#else
  curl_easy_setopt(curl, CURLOPT_PROTOCOLS, CURLPROTO_HTTPS);
#endif
  curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);
  curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
  curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
  curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS,
                   static_cast<long>(timeout.count()));
  curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT_MS,
                   static_cast<long>(timeout.count()));
  curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
  curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.data());
  curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE_LARGE,
                   static_cast<curl_off_t>(body.size()));
  curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, discard_response);
  curl_easy_setopt(curl, CURLOPT_WRITEDATA, &received);
  if (curl_easy_perform(curl) == CURLE_OK) {
    long status = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
    result.status = static_cast<int>(status);
    result.transport_ok = true;
  }
  curl_slist_free_all(headers);
  curl_easy_cleanup(curl);
  return result;
}
} // namespace desmond
