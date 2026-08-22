#include "desmond/http.h"

#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <sstream>
#include <stdexcept>
#include <thread>

namespace desmond {
namespace {

std::string status_text(const int status) {
  switch (status) {
    case 400:
      return "Bad Request";
    case 200:
      return "OK";
    case 401:
      return "Unauthorized";
    case 404:
      return "Not Found";
    case 405:
      return "Method Not Allowed";
    case 503:
      return "Service Unavailable";
    default:
      return "Internal Server Error";
  }
}

std::string trim(std::string value) {
  while (!value.empty() && (value.back() == '\r' || value.back() == '\n' || value.back() == ' ')) {
    value.pop_back();
  }
  const auto first = value.find_first_not_of(' ');
  return first == std::string::npos ? std::string{} : value.substr(first);
}

HttpRequest parse_request(const std::string& raw) {
  HttpRequest request;
  std::istringstream stream(raw);
  std::string line;
  if (std::getline(stream, line)) {
    std::istringstream first_line(line);
    first_line >> request.method >> request.path;
  }
  while (std::getline(stream, line)) {
    if (line == "\r" || line.empty()) break;
    const auto separator = line.find(':');
    if (separator == std::string::npos) {
      continue;
    }
    std::string name = line.substr(0, separator);
    std::transform(name.begin(), name.end(), name.begin(), [](const unsigned char character) {
      return static_cast<char>(std::tolower(character));
    });
    if (name == "authorization") {
      request.authorization = trim(line.substr(separator + 1));
    }
  }
  const auto body_offset = raw.find("\r\n\r\n");
  if (body_offset != std::string::npos) request.body = raw.substr(body_offset + 4);
  return request;
}

std::size_t content_length(const std::string& headers) {
  std::istringstream stream(headers);
  std::string line;
  while (std::getline(stream, line)) {
    const auto separator = line.find(':');
    if (separator == std::string::npos) continue;
    std::string name = line.substr(0, separator);
    std::transform(name.begin(), name.end(), name.begin(), [](const unsigned char character) {
      return static_cast<char>(std::tolower(character));
    });
    if (name != "content-length") continue;
    const std::string value = trim(line.substr(separator + 1));
    std::size_t consumed = 0;
    const unsigned long long parsed = std::stoull(value, &consumed);
    if (consumed != value.size()) throw std::runtime_error("invalid Content-Length");
    return static_cast<std::size_t>(parsed);
  }
  return 0;
}

bool send_all(const int fd, const std::string& data) {
  std::size_t sent = 0;
  while (sent < data.size()) {
    const auto result = send(fd, data.data() + sent, data.size() - sent, MSG_NOSIGNAL);
    if (result <= 0) {
      return false;
    }
    sent += static_cast<std::size_t>(result);
  }
  return true;
}

}  // namespace

HttpServer::HttpServer(std::string host, const std::uint16_t port, HttpHandler handler)
    : host_(std::move(host)), port_(port), handler_(std::move(handler)) {}

HttpServer::~HttpServer() { stop(); }

void HttpServer::run() {
  listen_fd_ = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (listen_fd_ < 0) {
    throw std::runtime_error("failed to create HTTP socket");
  }
  int enabled = 1;
  setsockopt(listen_fd_, SOL_SOCKET, SO_REUSEADDR, &enabled, sizeof(enabled));
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_port = htons(port_);
  if (inet_pton(AF_INET, host_.c_str(), &address.sin_addr) != 1) {
    throw std::runtime_error("Desmond HTTP bind host must be an IPv4 address");
  }
  if (bind(listen_fd_, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0) {
    throw std::runtime_error(std::string("failed to bind HTTP socket: ") + std::strerror(errno));
  }
  if (listen(listen_fd_, 64) != 0) {
    throw std::runtime_error("failed to listen on HTTP socket");
  }

  while (!stopping_.load(std::memory_order_relaxed)) {
    pollfd descriptor{listen_fd_, POLLIN, 0};
    const int poll_result = poll(&descriptor, 1, 500);
    if (poll_result <= 0 || (descriptor.revents & POLLIN) == 0) {
      continue;
    }
    const int client = accept4(listen_fd_, nullptr, nullptr, SOCK_CLOEXEC);
    if (client < 0) {
      continue;
    }
    {
      std::lock_guard lock(clients_mutex_);
      ++active_clients_;
    }
    std::thread([this, client] {
      handle_client(client);
      {
        std::lock_guard lock(clients_mutex_);
        --active_clients_;
      }
      clients_condition_.notify_all();
    }).detach();
  }
  std::unique_lock lock(clients_mutex_);
  clients_condition_.wait(lock, [&] { return active_clients_ == 0; });
}

void HttpServer::handle_client(const int client) {
  constexpr std::size_t maximum_header_bytes = 64 * 1024;
  constexpr std::size_t maximum_body_bytes = 1024 * 1024;
  timeval timeout{30, 0};
  setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
  setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
  HttpResponse response;
  try {
    std::string raw;
    std::array<char, 16384> buffer{};
    std::size_t header_end = std::string::npos;
    std::size_t expected_bytes = 0;
    while (true) {
      const auto received = recv(client, buffer.data(), buffer.size(), 0);
      if (received <= 0) throw std::runtime_error("incomplete request");
      raw.append(buffer.data(), static_cast<std::size_t>(received));
      if (header_end == std::string::npos) {
        header_end = raw.find("\r\n\r\n");
        if (header_end == std::string::npos) {
          if (raw.size() > maximum_header_bytes) throw std::runtime_error("request headers too large");
          continue;
        }
        const std::size_t body_bytes = content_length(raw.substr(0, header_end + 2));
        if (body_bytes > maximum_body_bytes) throw std::runtime_error("request body too large");
        expected_bytes = header_end + 4 + body_bytes;
      }
      if (raw.size() >= expected_bytes) break;
    }
    raw.resize(expected_bytes);
    response = handler_(parse_request(raw));
  } catch (const std::exception& error) {
    response = {400, "text/plain; charset=utf-8", std::string("bad request: ") + error.what() + "\n"};
  }
  std::ostringstream headers;
  headers << "HTTP/1.1 " << response.status << ' ' << status_text(response.status) << "\r\n"
          << "Content-Type: " << response.content_type << "\r\n"
          << "Content-Length: " << response.body.size() << "\r\n"
          << "Connection: close\r\n\r\n";
  send_all(client, headers.str() + response.body);
  close(client);
}

void HttpServer::stop() {
  stopping_.store(true, std::memory_order_relaxed);
  if (listen_fd_ >= 0) {
    shutdown(listen_fd_, SHUT_RDWR);
    close(listen_fd_);
    listen_fd_ = -1;
  }
}

HttpGetResult http_get(const std::string_view host, const std::uint16_t port,
                       const std::string_view path, const std::chrono::milliseconds timeout) {
  HttpGetResult result;
  addrinfo hints{};
  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_STREAM;
  addrinfo* addresses = nullptr;
  const std::string host_string(host);
  const std::string port_string = std::to_string(port);
  if (getaddrinfo(host_string.c_str(), port_string.c_str(), &hints, &addresses) != 0) {
    return result;
  }
  const int fd = socket(addresses->ai_family, addresses->ai_socktype | SOCK_CLOEXEC,
                        addresses->ai_protocol);
  if (fd < 0) {
    freeaddrinfo(addresses);
    return result;
  }
  timeval socket_timeout{};
  socket_timeout.tv_sec = static_cast<time_t>(timeout.count() / 1000);
  socket_timeout.tv_usec = static_cast<suseconds_t>((timeout.count() % 1000) * 1000);
  setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &socket_timeout, sizeof(socket_timeout));
  setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &socket_timeout, sizeof(socket_timeout));
  if (connect(fd, addresses->ai_addr, addresses->ai_addrlen) != 0) {
    close(fd);
    freeaddrinfo(addresses);
    return result;
  }
  freeaddrinfo(addresses);
  const std::string request = "GET " + std::string(path) + " HTTP/1.1\r\nHost: " + host_string +
                              "\r\nConnection: close\r\n\r\n";
  if (!send_all(fd, request)) {
    close(fd);
    return result;
  }
  std::string response;
  std::array<char, 16384> buffer{};
  while (response.size() < 8 * 1024 * 1024) {
    const auto received = recv(fd, buffer.data(), buffer.size(), 0);
    if (received == 0) {
      break;
    }
    if (received < 0) {
      close(fd);
      return result;
    }
    response.append(buffer.data(), static_cast<std::size_t>(received));
  }
  close(fd);
  const auto first_space = response.find(' ');
  if (first_space == std::string::npos || response.size() < first_space + 4) {
    return result;
  }
  try {
    result.status = std::stoi(response.substr(first_space + 1, 3));
  } catch (...) {
    return result;
  }
  const auto body_offset = response.find("\r\n\r\n");
  if (body_offset != std::string::npos) {
    result.body = response.substr(body_offset + 4);
  }
  result.transport_ok = true;
  return result;
}

HttpGetResult http_post(const std::string_view host, const std::uint16_t port,
                        const std::string_view path, const std::string_view authorization,
                        const std::string_view body, const std::chrono::milliseconds timeout) {
  HttpGetResult result;
  addrinfo hints{};
  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_STREAM;
  addrinfo* addresses = nullptr;
  const std::string host_string(host);
  const std::string port_string = std::to_string(port);
  if (getaddrinfo(host_string.c_str(), port_string.c_str(), &hints, &addresses) != 0) {
    return result;
  }
  const int fd = socket(addresses->ai_family, addresses->ai_socktype | SOCK_CLOEXEC,
                        addresses->ai_protocol);
  if (fd < 0) {
    freeaddrinfo(addresses);
    return result;
  }
  timeval socket_timeout{};
  socket_timeout.tv_sec = static_cast<time_t>(timeout.count() / 1000);
  socket_timeout.tv_usec = static_cast<suseconds_t>((timeout.count() % 1000) * 1000);
  setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &socket_timeout, sizeof(socket_timeout));
  setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &socket_timeout, sizeof(socket_timeout));
  if (connect(fd, addresses->ai_addr, addresses->ai_addrlen) != 0) {
    close(fd);
    freeaddrinfo(addresses);
    return result;
  }
  freeaddrinfo(addresses);
  std::ostringstream request;
  request << "POST " << path << " HTTP/1.1\r\nHost: " << host_string
          << "\r\nAuthorization: " << authorization
          << "\r\nContent-Type: application/json\r\nContent-Length: " << body.size()
          << "\r\nConnection: close\r\n\r\n" << body;
  if (!send_all(fd, request.str())) {
    close(fd);
    return result;
  }
  std::array<char, 8192> buffer{};
  const auto received = recv(fd, buffer.data(), buffer.size() - 1, 0);
  close(fd);
  if (received <= 0) return result;
  const std::string response(buffer.data(), static_cast<std::size_t>(received));
  const auto first_space = response.find(' ');
  if (first_space == std::string::npos || response.size() < first_space + 4) return result;
  try {
    result.status = std::stoi(response.substr(first_space + 1, 3));
  } catch (...) {
    return result;
  }
  result.transport_ok = true;
  return result;
}

}  // namespace desmond
