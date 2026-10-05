#include "supervise.h"

#include <unistd.h>

#include <charconv>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {
namespace fs = std::filesystem;

constexpr auto host_base_id_path = "/etc/gradiated/base-id";
constexpr std::size_t max_base_id_length = 128;

[[noreturn]] void fail(const std::string &message) {
  throw std::runtime_error(message);
}

unsigned number_environment(const char *name, unsigned maximum) {
  const char *value = std::getenv(name);
  if (!value) {
    fail(std::string("Missing ") + name);
  }

  const std::string_view text(value);
  unsigned result = 0;
  const auto parsed = std::from_chars(text.data(), text.data() + text.size(), result);
  if (parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size() || result == 0 ||
      result > maximum) {
    fail(std::string("Invalid ") + name);
  }
  return result;
}

std::optional<RuntimeHealthPolicy> health_policy() {
  if (!std::getenv("RUNTIME_STARTUP_TIMEOUT_SECONDS")) {
    return std::nullopt;
  }
  return RuntimeHealthPolicy{
      .port = static_cast<unsigned short>(number_environment("RUNTIME_PORT", 65535)),
      .startup_timeout =
          std::chrono::seconds{number_environment("RUNTIME_STARTUP_TIMEOUT_SECONDS", 86400)},
  };
}

std::string read_base_id(const fs::path &path) {
  std::ifstream file(path);
  std::string value;
  if (!std::getline(file, value)) {
    fail("Cannot read base ID: " + path.string());
  }

  if (value.empty() || value.size() > max_base_id_length) {
    fail("Invalid base ID in " + path.string());
  }

  return value;
}

std::string verified_entrypoint(const fs::path &root) {
  const auto bundle_id = read_base_id(root / "base-id");
  const auto host_id = read_base_id(host_base_id_path);
  if (bundle_id != host_id) {
    fail("Bundle base ID " + bundle_id + " does not match host base ID " + host_id);
  }

  const auto entry = root / "entrypoint";
  if (!fs::is_regular_file(fs::symlink_status(entry)) || access(entry.c_str(), X_OK) != 0) {
    fail("Bundle entrypoint must be an executable regular file");
  }

  return entry.string();
}
} // namespace

int main(int argc, char **argv) {
  try {
    if (argc < 2) {
      fail("Usage: runtime-launch RUNTIME_DIRECTORY [-- ARGS...]");
    }

    if (argc > 2 && std::string_view(argv[2]) != "--") {
      fail("Expected -- before runtime arguments");
    }

    const auto root = fs::canonical(argv[1]);
    auto entry = verified_entrypoint(root);
    if (setenv("GRADIATED_RUNTIME_ROOT", root.c_str(), 1) != 0) {
      fail("Cannot set runtime root");
    }

    std::vector<char *> args{entry.data()};
    for (int index = 3; index < argc; ++index) {
      args.push_back(argv[index]);
    }
    args.push_back(nullptr);

    return supervise(args.data(), default_shutdown_grace, health_policy());
  } catch (const std::exception &error) {
    std::cerr << "runtime-launch: " << error.what() << '\n';
    return 1;
  }
}
