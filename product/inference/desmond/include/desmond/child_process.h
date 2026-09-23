#pragma once

#include <chrono>
#include <optional>
#include <string>
#include <variant>
#include <vector>

#include <sys/types.h>

namespace desmond {

struct Exited {
  int code{};
};

struct Signaled {
  int signal{};
};

using ExitStatus = std::variant<Exited, Signaled>;

[[nodiscard]] std::string to_string(const ExitStatus &status);

class ChildProcess {
public:
  ChildProcess(const std::vector<std::string> &command,
               const std::vector<std::string> &environment);
  ~ChildProcess();
  ChildProcess(const ChildProcess &) = delete;
  ChildProcess &operator=(const ChildProcess &) = delete;

  [[nodiscard]] pid_t pid() const;
  [[nodiscard]] std::optional<ExitStatus> try_reap();
  ExitStatus terminate(std::chrono::seconds grace);

private:
  [[nodiscard]] bool leader_exited() const;
  ExitStatus reap();

  pid_t pid_{};
  std::optional<ExitStatus> exit_status_;
};

} // namespace desmond
