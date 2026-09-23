#include "desmond/child_process.h"

#include "test_support.h"

#include <signal.h>
#include <unistd.h>

#include <chrono>
#include <fstream>
#include <string>

namespace {

using namespace std::chrono_literals;
using desmond::testing::eventually;
using desmond::testing::TempDirectory;
using desmond::testing::throws;

bool exited_with(const std::optional<desmond::ExitStatus> &status, const int code) {
  const auto *exited = status ? std::get_if<desmond::Exited>(&*status) : nullptr;
  return exited != nullptr && exited->code == code;
}

bool signaled_with(const std::optional<desmond::ExitStatus> &status, const int signal_number) {
  const auto *signaled = status ? std::get_if<desmond::Signaled>(&*status) : nullptr;
  return signaled != nullptr && signaled->signal == signal_number;
}

desmond::ChildProcess shell(const std::string &script) {
  return {{"/bin/sh", "-c", script}, {"PATH=/usr/bin:/bin"}};
}

std::optional<desmond::ExitStatus> wait_for_exit(desmond::ChildProcess &child) {
  std::optional<desmond::ExitStatus> status;
  CHECK(eventually([&] { return (status = child.try_reap()).has_value(); }));
  return status;
}

pid_t read_pid(const std::string &path) {
  pid_t pid = 0;
  CHECK(eventually([&] { return static_cast<bool>(std::ifstream(path) >> pid); }));
  return pid;
}

bool process_gone(const pid_t pid) {
  return eventually([&] { return kill(pid, 0) != 0; });
}

DESMOND_TEST(child_exit_code_is_reported) {
  auto child = shell("exit 3");

  CHECK(exited_with(wait_for_exit(child), 3));
  CHECK(exited_with(child.try_reap(), 3));
}

DESMOND_TEST(child_killed_by_a_signal_is_reported) {
  auto child = shell("kill -SEGV $$");

  CHECK(signaled_with(wait_for_exit(child), SIGSEGV));
}

DESMOND_TEST(running_child_is_not_reaped) {
  auto child = shell("sleep 30");

  CHECK(child.pid() > 0);
  CHECK(!child.try_reap());
}

DESMOND_TEST(terminate_stops_a_child_with_sigterm) {
  auto child = shell("exec sleep 30");

  CHECK(signaled_with(child.terminate(5s), SIGTERM));
}

DESMOND_TEST(terminate_kills_a_child_that_ignores_sigterm_after_the_grace) {
  const TempDirectory directory;
  const auto marker = directory.file("trapped");
  auto child = shell("trap '' TERM; touch " + marker + "; sleep 30");
  CHECK(eventually([&] { return access(marker.c_str(), F_OK) == 0; }));

  const auto started = std::chrono::steady_clock::now();
  const auto status = child.terminate(1s);
  const auto elapsed = std::chrono::steady_clock::now() - started;

  CHECK(signaled_with(status, SIGKILL));
  CHECK(elapsed >= 1s && elapsed < 3s);
}

DESMOND_TEST(terminate_kills_the_rest_of_the_process_group) {
  const TempDirectory directory;
  const auto pid_file = directory.file("grandchild");
  auto child = shell("(trap '' TERM; exec sleep 30) & echo $! > " + pid_file + "; wait");
  const auto grandchild = read_pid(pid_file);

  static_cast<void>(child.terminate(5s));

  CHECK(process_gone(grandchild));
}

DESMOND_TEST(reaping_an_exited_leader_kills_the_rest_of_the_process_group) {
  const TempDirectory directory;
  const auto pid_file = directory.file("grandchild");
  auto child = shell("sleep 30 & echo $! > " + pid_file + "; sleep 0.2; exit 4");
  const auto grandchild = read_pid(pid_file);

  CHECK(exited_with(wait_for_exit(child), 4));
  CHECK(process_gone(grandchild));
}

DESMOND_TEST(missing_runtime_binary_fails_to_spawn) {
  CHECK(throws([] { desmond::ChildProcess child({"/nonexistent/desmond-runtime"}, {}); }));
  CHECK(throws([] { desmond::ChildProcess child({}, {}); }));
}

DESMOND_TEST(child_receives_exactly_the_given_environment) {
  const TempDirectory directory;
  const auto output = directory.file("environment");
  auto child = shell("env > " + output);

  CHECK(exited_with(wait_for_exit(child), 0));
  std::ifstream file(output);
  const std::string contents((std::istreambuf_iterator<char>(file)), {});
  CHECK(contents.find("PATH=/usr/bin:/bin") != std::string::npos);
  CHECK(contents.find("HOME=") == std::string::npos);
}

DESMOND_TEST(exit_status_describes_code_or_signal) {
  CHECK(desmond::to_string(desmond::Exited{3}) == "exit code 3");
  CHECK(desmond::to_string(desmond::Signaled{9}) == "signal 9");
}

} // namespace
