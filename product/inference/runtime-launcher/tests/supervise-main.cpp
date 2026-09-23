#include "supervise.h"

#include <charconv>
#include <chrono>
#include <exception>
#include <iostream>
#include <optional>
#include <string_view>

namespace {
constexpr int usage_status = 2;
constexpr std::string_view usage =
    "Usage: supervise-adapter [--grace-seconds N] COMMAND [ARGS...]\n";

std::optional<std::chrono::seconds> parse_seconds(std::string_view text) {
  int seconds = 0;
  const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), seconds);

  if (error != std::errc() || end != text.data() + text.size() || seconds < 0) {
    return std::nullopt;
  }

  return std::chrono::seconds(seconds);
}
} // namespace

int main(int argc, char **argv) {
  auto grace = default_shutdown_grace;
  int command = 1;

  if (argc > 2 && std::string_view(argv[1]) == "--grace-seconds") {
    const auto parsed = parse_seconds(argv[2]);
    if (!parsed) {
      std::cerr << usage;
      return usage_status;
    }

    grace = *parsed;
    command = 3;
  }

  if (command >= argc) {
    std::cerr << usage;
    return usage_status;
  }

  try {
    return supervise(argv + command, grace);
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
