#pragma once

#include <chrono>
#include <cstdint>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

#include <sys/types.h>

namespace desmond {

struct RuntimeStatus {
  bool child_running{false};
  bool runtime_ready{false};
  bool draining{false};
  pid_t pid{-1};
  int last_exit_code{-1};
  std::uint64_t starts{0};
  std::uint64_t unexpected_exits{0};
  std::chrono::steady_clock::time_point started_at{};
  std::chrono::steady_clock::time_point last_health_check{};
};

class RuntimeSupervisor {
 public:
   RuntimeSupervisor(std::vector<std::string> command, std::string health_host,
                     std::uint16_t health_port, std::string health_path,
                     std::chrono::seconds shutdown_grace,
                     bool observe_only = false);
   ~RuntimeSupervisor();
   RuntimeSupervisor(const RuntimeSupervisor &) = delete;
   RuntimeSupervisor &operator=(const RuntimeSupervisor &) = delete;

   bool start();
   void poll();
   void check_health();
   void shutdown();
   [[nodiscard]] RuntimeStatus status() const;

 private:
   bool observe_only_;
   std::vector<std::string> command_;
   std::string health_host_;
   std::uint16_t health_port_;
   std::string health_path_;
   std::chrono::seconds shutdown_grace_;
   mutable std::mutex mutex_;
   RuntimeStatus status_;
};

}  // namespace desmond
