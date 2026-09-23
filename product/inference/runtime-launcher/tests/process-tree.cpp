#include <fcntl.h>
#include <signal.h>
#include <unistd.h>

#include <array>
#include <cerrno>
#include <filesystem>
#include <fstream>
#include <span>
#include <string>
#include <system_error>

namespace {
constexpr std::array shutdown_signals{SIGTERM, SIGINT, SIGHUP};
constexpr std::array stubborn_signals{SIGINT, SIGHUP};
int signal_record = -1;

void write_signal_and_exit(int signal) {
  char text[3];
  int length = 0;
  if (signal >= 10) {
    text[length++] = static_cast<char>('0' + signal / 10);
  }
  text[length++] = static_cast<char>('0' + signal % 10);
  text[length++] = '\n';

  if (write(signal_record, text, length) != length) {
    _exit(3);
  }
  _exit(0);
}

void record_signals(const std::filesystem::path &path, std::span<const int> signals) {
  signal_record = open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
  if (signal_record < 0) {
    throw std::system_error(errno, std::generic_category(), "Cannot open signal record");
  }

  struct sigaction action {};
  action.sa_handler = write_signal_and_exit;
  sigemptyset(&action.sa_mask);
  for (int signal : shutdown_signals) {
    sigaddset(&action.sa_mask, signal);
  }
  for (int signal : signals) {
    if (sigaction(signal, &action, nullptr) != 0) {
      throw std::system_error(errno, std::generic_category(), "Cannot install signal handler");
    }
  }
}

void publish_pid(const std::filesystem::path &path) {
  const auto temporary = path.string() + ".tmp";
  std::ofstream file;
  file.exceptions(std::ios::failbit | std::ios::badbit);
  file.open(temporary);
  file << getpid() << '\n';
  file.close();
  std::filesystem::rename(temporary, path);
}

[[noreturn]] void wait_for_signal() {
  for (;;) {
    pause();
  }
}
} // namespace

int main(int argc, char **argv) {
  if (argc != 3) {
    return 1;
  }

  const std::filesystem::path root = argv[1];
  const std::string mode = argv[2];

  const pid_t ordinary = fork();
  if (ordinary < 0) {
    return 2;
  }

  if (ordinary == 0) {
    record_signals(root / "ordinary.signal", shutdown_signals);
    publish_pid(root / "ordinary");
    wait_for_signal();
  }

  const pid_t detached = fork();
  if (detached < 0) {
    return 2;
  }

  if (detached == 0) {
    if (setsid() < 0) {
      _exit(2);
    }

    if (mode == "stubborn") {
      signal(SIGTERM, SIG_IGN);
    }

    // A double fork tests adoption after the intermediate parent exits.
    const pid_t grandchild = fork();
    if (grandchild < 0) {
      _exit(2);
    }

    if (grandchild > 0) {
      _exit(0);
    }

    record_signals(root / "detached.signal", mode == "stubborn"
                                                 ? std::span<const int>(stubborn_signals)
                                                 : std::span<const int>(shutdown_signals));
    publish_pid(root / "detached");
    wait_for_signal();
  }

  record_signals(root / "leader.signal", shutdown_signals);
  publish_pid(root / "leader");

  for (int attempt = 0; attempt < 500; ++attempt) {
    if (std::filesystem::exists(root / "ordinary") && std::filesystem::exists(root / "detached")) {
      publish_pid(root / "ready");
      if (mode == "exit") {
        return 37;
      }

      if (mode == "crash") {
        kill(getpid(), SIGKILL);
      }

      wait_for_signal();
    }
    usleep(10000);
  }

  return 2;
}
