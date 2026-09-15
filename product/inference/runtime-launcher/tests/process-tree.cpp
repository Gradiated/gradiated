#include <signal.h>
#include <unistd.h>
#include <fstream>
#include <string>
#include <cstdlib>

int main(int argc, char** argv) {
  if (argc != 3) return 1;
  std::string root = argv[1], mode = argv[2];
  pid_t ordinary = fork();
  if (ordinary < 0) return 2;
  if (ordinary == 0) { for (;;) pause(); }
  pid_t detached = fork();
  if (detached < 0) return 2;
  if (detached == 0) {
    if (setsid() < 0) _exit(2);
    if (mode == "stubborn") signal(SIGTERM, SIG_IGN);
    // Include a double-forked descendant whose intermediate parent exits.
    pid_t grandchild = fork();
    if (grandchild < 0) _exit(2);
    if (grandchild > 0) _exit(0);
    std::ofstream(root + "/detached") << getpid();
    for (;;) pause();
  }
  std::ofstream(root + "/ordinary") << ordinary;
  std::ofstream(root + "/leader") << getpid();
  for (int i = 0; i < 100 && !std::ifstream(root + "/detached").good(); ++i) usleep(10000);
  if (mode == "exit") return 37;
  if (mode == "crash") kill(getpid(), SIGKILL);
  for (;;) pause();
}
