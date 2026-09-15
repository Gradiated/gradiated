#include <signal.h>
#include <unistd.h>

#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>

namespace {
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
    publish_pid(root / "detached");
    wait_for_signal();
  }

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
