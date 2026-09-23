#include "desmond/child_process.h"

#include <signal.h>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cerrno>
#include <stdexcept>
#include <system_error>
#include <thread>

namespace desmond {
namespace {

std::vector<char *> null_terminated(const std::vector<std::string> &values) {
  std::vector<char *> pointers;
  pointers.reserve(values.size() + 1);
  for (const auto &value : values) {
    pointers.push_back(const_cast<char *>(value.c_str()));
  }

  pointers.push_back(nullptr);
  return pointers;
}

ExitStatus decode(const int status) {
  if (WIFSIGNALED(status)) {
    return Signaled{WTERMSIG(status)};
  }

  return Exited{WEXITSTATUS(status)};
}

} // namespace

std::string to_string(const ExitStatus &status) {
  if (const auto *signaled = std::get_if<Signaled>(&status)) {
    return "signal " + std::to_string(signaled->signal);
  }

  return "exit code " + std::to_string(std::get<Exited>(status).code);
}

ChildProcess::ChildProcess(const std::vector<std::string> &command,
                           const std::vector<std::string> &environment) {
  if (command.empty()) {
    throw std::invalid_argument("runtime command is empty");
  }

  const auto arguments = null_terminated(command);
  const auto environment_pointers = null_terminated(environment);

  posix_spawnattr_t attributes;
  posix_spawnattr_init(&attributes);
  posix_spawnattr_setflags(&attributes, POSIX_SPAWN_SETPGROUP);
  posix_spawnattr_setpgroup(&attributes, 0);

  const int result = posix_spawnp(&pid_, arguments[0], nullptr, &attributes, arguments.data(),
                                  environment_pointers.data());
  posix_spawnattr_destroy(&attributes);

  if (result != 0) {
    throw std::system_error(result, std::generic_category(), "failed to start " + command[0]);
  }
}

ChildProcess::~ChildProcess() {
  if (exit_status_) {
    return;
  }

  kill(-pid_, SIGKILL);
  static_cast<void>(reap());
}

pid_t ChildProcess::pid() const {
  return pid_;
}

std::optional<ExitStatus> ChildProcess::try_reap() {
  if (!exit_status_ && leader_exited()) {
    kill(-pid_, SIGKILL);
    static_cast<void>(reap());
  }

  return exit_status_;
}

ExitStatus ChildProcess::terminate(const std::chrono::seconds grace) {
  if (exit_status_) {
    return *exit_status_;
  }

  kill(-pid_, SIGTERM);
  const auto deadline = std::chrono::steady_clock::now() + grace;
  while (!leader_exited() && std::chrono::steady_clock::now() < deadline) {
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }

  kill(-pid_, SIGKILL);
  return reap();
}

// An exited leader stays a zombie until reaped, so its pid, and with it the process group id,
// cannot be reused while the rest of the group is signalled.
bool ChildProcess::leader_exited() const {
  siginfo_t info{};
  return waitid(P_PID, static_cast<id_t>(pid_), &info, WEXITED | WNOHANG | WNOWAIT) == 0 &&
         info.si_pid == pid_;
}

ExitStatus ChildProcess::reap() {
  int status = 0;
  while (waitpid(pid_, &status, 0) < 0 && errno == EINTR) {
  }

  exit_status_ = decode(status);
  return *exit_status_;
}

} // namespace desmond
