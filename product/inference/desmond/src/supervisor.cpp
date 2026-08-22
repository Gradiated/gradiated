#include "desmond/supervisor.h"

#include "desmond/http.h"

#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>

#include <thread>

namespace desmond {

RuntimeSupervisor::RuntimeSupervisor(std::vector<std::string> command, std::string health_host,
                                     const std::uint16_t health_port, std::string health_path,
                                     const std::chrono::seconds shutdown_grace)
    : command_(std::move(command)),
      health_host_(std::move(health_host)),
      health_port_(health_port),
      health_path_(std::move(health_path)),
      shutdown_grace_(shutdown_grace) {}

RuntimeSupervisor::~RuntimeSupervisor() { shutdown(); }

bool RuntimeSupervisor::start() {
  if (command_.empty()) {
    return false;
  }
  std::vector<char*> arguments;
  arguments.reserve(command_.size() + 1);
  for (auto& part : command_) {
    arguments.push_back(part.data());
  }
  arguments.push_back(nullptr);

  const pid_t child = fork();
  if (child < 0) {
    return false;
  }
  if (child == 0) {
    setpgid(0, 0);
    execvp(arguments[0], arguments.data());
    _exit(127);
  }
  setpgid(child, child);
  std::lock_guard lock(mutex_);
  status_.child_running = true;
  status_.runtime_ready = false;
  status_.draining = false;
  status_.pid = child;
  status_.starts += 1;
  status_.started_at = std::chrono::steady_clock::now();
  return true;
}

void RuntimeSupervisor::poll() {
  pid_t pid = -1;
  {
    std::lock_guard lock(mutex_);
    if (!status_.child_running) {
      return;
    }
    pid = status_.pid;
  }
  int child_status = 0;
  const pid_t result = waitpid(pid, &child_status, WNOHANG);
  if (result != pid) {
    return;
  }
  std::lock_guard lock(mutex_);
  status_.child_running = false;
  status_.runtime_ready = false;
  status_.pid = -1;
  if (WIFEXITED(child_status)) {
    status_.last_exit_code = WEXITSTATUS(child_status);
  } else if (WIFSIGNALED(child_status)) {
    status_.last_exit_code = 128 + WTERMSIG(child_status);
  }
  if (!status_.draining) {
    status_.unexpected_exits += 1;
  }
}

void RuntimeSupervisor::check_health() {
  bool running = false;
  {
    std::lock_guard lock(mutex_);
    running = status_.child_running;
  }
  bool ready = false;
  if (running) {
    const auto health = http_get(health_host_, health_port_, health_path_, std::chrono::seconds(2));
    ready = health.transport_ok && health.status >= 200 && health.status < 300;
  }
  std::lock_guard lock(mutex_);
  status_.runtime_ready = ready;
  status_.last_health_check = std::chrono::steady_clock::now();
}

void RuntimeSupervisor::shutdown() {
  pid_t pid = -1;
  {
    std::lock_guard lock(mutex_);
    if (!status_.child_running) {
      return;
    }
    status_.draining = true;
    status_.runtime_ready = false;
    pid = status_.pid;
  }
  kill(-pid, SIGTERM);
  const auto deadline = std::chrono::steady_clock::now() + shutdown_grace_;
  int child_status = 0;
  while (std::chrono::steady_clock::now() < deadline) {
    if (waitpid(pid, &child_status, WNOHANG) == pid) {
      std::lock_guard lock(mutex_);
      status_.child_running = false;
      status_.pid = -1;
      return;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  kill(-pid, SIGKILL);
  waitpid(pid, &child_status, 0);
  std::lock_guard lock(mutex_);
  status_.child_running = false;
  status_.pid = -1;
}

RuntimeStatus RuntimeSupervisor::status() const {
  std::lock_guard lock(mutex_);
  return status_;
}

}  // namespace desmond
