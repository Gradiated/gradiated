#include "supervise.h"

#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <csignal>
#include <fstream>
#include <stdexcept>
#include <system_error>
#include <thread>
#include <unordered_set>

namespace {
constexpr auto shutdown_grace = std::chrono::seconds(25);
constexpr auto reap_interval = std::chrono::milliseconds(50);
volatile sig_atomic_t stop_signal = 0;

[[noreturn]] void system_failure(const char *operation) {
  throw std::system_error(errno, std::generic_category(), operation);
}
void on_signal(int signal) {
  stop_signal = signal;
}

// These are our unreaped children, so their PIDs cannot be reused between
// enumeration and signaling. Orphans are adopted here even after setsid().
void signal_children(int signal, std::unordered_set<pid_t> &signaled) {
  std::ifstream children("/proc/self/task/" + std::to_string(getpid()) + "/children");
  if (!children) {
    throw std::runtime_error("Cannot read child process list");
  }
  pid_t pid;
  while (children >> pid) {
    if (!signaled.insert(pid).second) {
      continue;
    }
    if (kill(pid, signal) != 0 && errno != ESRCH) {
      system_failure("Cannot signal child process");
    }
  }
}
} // namespace

int supervise(char *const argv[]) {
  if (prctl(PR_SET_CHILD_SUBREAPER, 1) != 0) {
    system_failure("Cannot enable child subreaper");
  }
  sigset_t signals, previous;
  sigemptyset(&signals);
  for (int signal : {SIGTERM, SIGINT, SIGHUP}) {
    sigaddset(&signals, signal);
  }
  if (sigprocmask(SIG_BLOCK, &signals, &previous) != 0) {
    system_failure("Cannot block shutdown signals");
  }
  struct sigaction action {};
  action.sa_handler = on_signal;
  sigemptyset(&action.sa_mask);
  for (int signal : {SIGTERM, SIGINT, SIGHUP}) {
    if (sigaction(signal, &action, nullptr) != 0) {
      system_failure("Cannot install shutdown handler");
    }
  }
  const pid_t leader = fork();
  if (leader < 0) {
    system_failure("Cannot start runtime process");
  }
  if (leader == 0) {
    for (int signal : {SIGTERM, SIGINT, SIGHUP}) {
      std::signal(signal, SIG_DFL);
    }
    if (setsid() < 0 || sigprocmask(SIG_SETMASK, &previous, nullptr) != 0) {
      _exit(126);
    }
    execv(argv[0], argv);
    _exit(127);
  }
  if (sigprocmask(SIG_SETMASK, &previous, nullptr) != 0) {
    const int error = errno;
    kill(leader, SIGKILL);
    while (waitpid(leader, nullptr, 0) < 0 && errno == EINTR) {
    }
    throw std::system_error(error, std::generic_category(), "Cannot restore signal mask");
  }
  bool stopping = false;
  bool leader_exited = false;
  int result = 1;
  std::unordered_set<pid_t> terminated, killed;
  auto deadline = std::chrono::steady_clock::time_point::max();
  for (;;) {
    int status;
    pid_t pid;
    while ((pid = waitpid(-1, &status, WNOHANG)) > 0) {
      terminated.erase(pid);
      killed.erase(pid);
      if (pid == leader) {
        leader_exited = true;
        result = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
      }
    }
    if (pid < 0 && errno == ECHILD) {
      return stop_signal ? 128 + stop_signal : result;
    }
    if (pid < 0 && errno != EINTR) {
      system_failure("Cannot reap runtime process");
    }
    if (!stopping && (stop_signal || leader_exited)) {
      stopping = true;
      deadline = std::chrono::steady_clock::now() + shutdown_grace;
    }
    if (stopping) {
      const bool force = std::chrono::steady_clock::now() >= deadline;
      signal_children(force ? SIGKILL : (stop_signal ? stop_signal : SIGTERM),
                      force ? killed : terminated);
    }
    // Keep reaping until no descendants remain. A task stuck in an
    // uninterruptible kernel wait must not be reported as safely stopped.
    std::this_thread::sleep_for(reap_interval);
  }
}
