#pragma once

#include <sys/types.h>

#include <optional>

namespace desmond {

enum class ChildState { running, stopped, exited_unexpectedly };

struct SupervisedChild {
  pid_t pid{};
  ChildState state{ChildState::running};
};

[[nodiscard]] constexpr bool child_running(const std::optional<SupervisedChild> &child) {
  return child && child->state == ChildState::running;
}

[[nodiscard]] constexpr int runtime_starts(const std::optional<SupervisedChild> &child) {
  return child ? 1 : 0;
}

[[nodiscard]] constexpr int unexpected_exits(const std::optional<SupervisedChild> &child) {
  return child && child->state == ChildState::exited_unexpectedly ? 1 : 0;
}

} // namespace desmond
