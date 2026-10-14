#include "supervise.h"

#include <curl/curl.h>

#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <cerrno>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <iostream>
#include <memory>
#include <new>
#include <optional>
#include <stdexcept>
#include <system_error>
#include <unordered_set>

namespace {
constexpr std::array shutdown_signals{SIGTERM, SIGINT, SIGHUP};
constexpr int parent_death_signal = SIGUSR1;
constexpr auto children_path = "/proc/thread-self/children";
constexpr timespec reap_interval{.tv_sec = 0, .tv_nsec = 50'000'000};

class RuntimeHealth {
public:
  explicit RuntimeHealth(RuntimeHealthPolicy policy)
      : startup_deadline_(std::chrono::steady_clock::now() + policy.startup_timeout),
        url_("http://127.0.0.1:" + std::to_string(policy.port) + "/health"),
        curl_(curl_easy_init(), curl_easy_cleanup) {
    if (!curl_) {
      throw std::runtime_error("Cannot initialize runtime health check");
    }

    curl_easy_setopt(curl_.get(), CURLOPT_URL, url_.c_str());
    curl_easy_setopt(curl_.get(), CURLOPT_PROXY, "");
    curl_easy_setopt(curl_.get(), CURLOPT_TIMEOUT_MS, 2000L);
    curl_easy_setopt(curl_.get(), CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(
        curl_.get(), CURLOPT_WRITEFUNCTION,
        +[](char *, std::size_t size, std::size_t count, void *) { return size * count; });
  }

  bool alive() {
    const auto now = std::chrono::steady_clock::now();
    if (now < next_check_) {
      return true;
    }
    next_check_ = now + std::chrono::seconds{5};

    const auto result = curl_easy_perform(curl_.get());
    long status = 0;
    curl_easy_getinfo(curl_.get(), CURLINFO_RESPONSE_CODE, &status);
    if (result == CURLE_OK && status >= 200 && status < 300) {
      ready_ = true;
      failures_ = 0;
      return true;
    }

    return ready_ ? ++failures_ < 3 : std::chrono::steady_clock::now() < startup_deadline_;
  }

private:
  std::chrono::steady_clock::time_point startup_deadline_;
  std::chrono::steady_clock::time_point next_check_{};
  std::string url_;
  std::unique_ptr<CURL, decltype(&curl_easy_cleanup)> curl_;
  bool ready_ = false;
  unsigned failures_ = 0;
};

struct FileCloser {
  void operator()(FILE *file) const {
    std::fclose(file);
  }
};

using File = std::unique_ptr<FILE, FileCloser>;

struct Shutdown {
  std::chrono::steady_clock::time_point deadline;
  std::unordered_set<pid_t> terminated{};
  std::unordered_set<pid_t> killed{};
  bool reported_unreadable_children = false;
};

[[noreturn]] void system_failure(const char *operation) {
  throw std::system_error(errno, std::generic_category(), operation);
}

sigset_t supervisor_signals() {
  sigset_t signals;
  sigemptyset(&signals);
  sigaddset(&signals, SIGCHLD);
  sigaddset(&signals, parent_death_signal);
  for (int signal : shutdown_signals) {
    sigaddset(&signals, signal);
  }

  return signals;
}

void reset_disposition(int signal) {
  struct sigaction action {};
  action.sa_handler = SIG_DFL;
  sigemptyset(&action.sa_mask);

  if (sigaction(signal, &action, nullptr) != 0) {
    system_failure("Cannot reset signal disposition");
  }
}

// POSIX lets an ignored signal be discarded even while blocked, and an
// inherited SIG_IGN for SIGCHLD makes the kernel reap the runtime and lose its
// status. The runtime inherits the reset dispositions.
sigset_t block_supervisor_signals(const sigset_t &signals) {
  reset_disposition(SIGCHLD);
  reset_disposition(parent_death_signal);
  for (int signal : shutdown_signals) {
    reset_disposition(signal);
  }

  sigset_t previous;
  if (sigprocmask(SIG_BLOCK, &signals, &previous) != 0) {
    system_failure("Cannot block supervisor signals");
  }

  return previous;
}

sigset_t runtime_signal_mask(sigset_t inherited) {
  sigdelset(&inherited, parent_death_signal);
  for (int signal : shutdown_signals) {
    sigdelset(&inherited, signal);
  }

  return inherited;
}

// The launcher is single-threaded, so the child may use dprintf before exec.
pid_t start_runtime(char *const argv[], const sigset_t &mask) {
  const pid_t pid = fork();
  if (pid < 0) {
    system_failure("Cannot start runtime process");
  }

  if (pid == 0) {
    if (setsid() < 0 || sigprocmask(SIG_SETMASK, &mask, nullptr) != 0) {
      dprintf(STDERR_FILENO, "runtime-launch: Cannot prepare runtime process: %s\n",
              std::strerror(errno));
      _exit(126);
    }

    execv(argv[0], argv);
    const int error = errno;
    dprintf(STDERR_FILENO, "runtime-launch: Cannot execute %s: %s\n", argv[0],
            std::strerror(error));
    _exit(127);
  }

  return pid;
}

int exit_code(int wait_status) {
  return WIFEXITED(wait_status) ? WEXITSTATUS(wait_status) : 128 + WTERMSIG(wait_status);
}

// fopen reports its failure through errno; std::ifstream does not.
File open_child_list() {
  return File(std::fopen(children_path, "r"));
}

void require_child_list() {
  if (!open_child_list()) {
    system_failure("Cannot read the child process list");
  }
}

// A lost record only repeats a signal, which is safer than letting the
// supervisor throw while descendants remain.
bool first_signal(std::unordered_set<pid_t> &signaled, pid_t pid) noexcept {
  try {
    return signaled.insert(pid).second;
  } catch (const std::bad_alloc &) {
    return true;
  }
}

// These are our unreaped children, so their PIDs cannot be reused between
// enumeration and signaling. Orphans are adopted here even after setsid().
void signal_children(Shutdown &shutdown, int termination_signal) {
  const bool force = std::chrono::steady_clock::now() >= shutdown.deadline;
  const int signal = force ? SIGKILL : termination_signal;
  auto &signaled = force ? shutdown.killed : shutdown.terminated;

  const File children = open_child_list();
  if (!children) {
    const int error = errno;
    if (!shutdown.reported_unreadable_children) {
      std::cerr << "runtime-launch: Cannot list child processes: " << std::strerror(error) << '\n';
      shutdown.reported_unreadable_children = true;
    }

    return;
  }

  pid_t pid;
  while (std::fscanf(children.get(), "%d", &pid) == 1) {
    if (!first_signal(signaled, pid)) {
      continue;
    }

    if (kill(pid, signal) == 0 || errno == ESRCH) {
      continue;
    }

    const int error = errno;
    std::cerr << "runtime-launch: Cannot signal child " << pid << ": " << std::strerror(error)
              << '\n';
  }
}

// Adopted orphans raise no SIGCHLD, so a shutdown also wakes on a timer to
// find and signal them.
std::optional<int> wait_for_shutdown_signal(const sigset_t &signals, bool shutting_down,
                                            bool monitoring) {
  constexpr timespec health_tick{.tv_sec = 1, .tv_nsec = 0};
  const int signal = shutting_down ? sigtimedwait(&signals, nullptr, &reap_interval)
                     : monitoring  ? sigtimedwait(&signals, nullptr, &health_tick)
                                   : sigwaitinfo(&signals, nullptr);

  if (signal != parent_death_signal &&
      std::ranges::find(shutdown_signals, signal) == shutdown_signals.end()) {
    return std::nullopt;
  }

  return signal;
}

int supervise_runtime(char *const argv[], std::chrono::seconds grace, const sigset_t &inherited,
                      std::optional<RuntimeHealthPolicy> policy) {
  if (prctl(PR_SET_CHILD_SUBREAPER, 1) != 0) {
    system_failure("Cannot enable child subreaper");
  }

  require_child_list();

  const sigset_t signals = supervisor_signals();
  block_supervisor_signals(signals);
  std::optional<RuntimeHealth> health;
  if (policy) {
    health.emplace(*policy);
  }
  const pid_t leader = start_runtime(argv, runtime_signal_mask(inherited));

  std::optional<int> leader_status;
  std::optional<int> received_signal;
  std::optional<Shutdown> shutdown;

  // Past this point nothing throws: the supervisor must not return while
  // descendants remain.
  for (;;) {
    int status = 0;
    pid_t pid;
    while ((pid = waitpid(-1, &status, WNOHANG)) > 0) {
      if (shutdown) {
        shutdown->terminated.erase(pid);
        shutdown->killed.erase(pid);
      }

      if (pid == leader) {
        leader_status = exit_code(status);
      }
    }

    if (pid < 0 && errno == ECHILD) {
      // Returning only here keeps a task stuck in an uninterruptible kernel
      // wait from being reported as safely stopped.
      return received_signal ? 128 + *received_signal : *leader_status;
    }

    if (!shutdown && !received_signal && !leader_status && health && !health->alive()) {
      std::cerr << "runtime-launch: Runtime failed liveness; killing its process tree\n";
      received_signal = SIGKILL;
      shutdown = Shutdown{.deadline = std::chrono::steady_clock::now()};
    }

    if (!shutdown && (received_signal || leader_status)) {
      shutdown = Shutdown{.deadline = std::chrono::steady_clock::now() + grace};
    }

    if (received_signal == parent_death_signal) {
      shutdown->deadline = std::chrono::steady_clock::now();
    }

    if (shutdown) {
      signal_children(*shutdown, received_signal.value_or(SIGTERM));
    }

    const auto signal = wait_for_shutdown_signal(signals, shutdown.has_value(), health.has_value());
    if (signal && (!received_signal || *signal == parent_death_signal)) {
      received_signal = signal;
    }
  }
}

} // namespace

int supervise(char *const argv[], std::chrono::seconds grace,
              std::optional<RuntimeHealthPolicy> health) {
  if (health && curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
    throw std::runtime_error("Cannot initialize runtime health client");
  }
  const sigset_t signals = supervisor_signals();
  const sigset_t inherited = block_supervisor_signals(signals);
  const pid_t parent = getpid();
  const pid_t guardian = fork();
  if (guardian < 0) {
    system_failure("Cannot start runtime guardian");
  }

  if (guardian == 0) {
    // Host cleanup can kill the launcher's process group. Keep the
    // guardian outside that group so it can finish reaping detached workers.
    if (setsid() < 0 || prctl(PR_SET_PDEATHSIG, parent_death_signal) != 0) {
      _exit(126);
    }
    if (getppid() != parent) {
      _exit(137);
    }

    try {
      _exit(supervise_runtime(argv, grace, inherited, health));
    } catch (const std::exception &error) {
      std::cerr << "runtime-launch: " << error.what() << '\n';
      _exit(1);
    }
  }

  for (;;) {
    int status = 0;
    const pid_t waited = waitpid(guardian, &status, WNOHANG);
    if (waited == guardian) {
      return exit_code(status);
    }
    const int signal = sigwaitinfo(&signals, nullptr);
    if (std::ranges::find(shutdown_signals, signal) != shutdown_signals.end()) {
      kill(guardian, signal);
    }
  }
}
