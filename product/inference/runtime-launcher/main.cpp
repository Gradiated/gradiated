#include "supervise.h"

#include <unistd.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
void require(bool ok, const char* message) {
  if (!ok) throw std::runtime_error(message);
}
std::string read_id(const fs::path& path) {
  std::ifstream file(path);
  std::string value;
  std::getline(file, value);
  require(file.good() || file.eof(), "Cannot read base ID");
  require(!value.empty() && value.size() <= 128, "Invalid base ID");
  return value;
}
int main(int argc, char** argv) {
  try {
    require(argc >= 2, "Usage: runtime-launch RUNTIME_DIRECTORY [-- ARGS...]");
    require(argc == 2 || std::string(argv[2]) == "--", "Expected -- before runtime arguments");
    const auto root = fs::canonical(argv[1]);
    require(read_id(root / "base-id") == read_id("/etc/gradiated/base-id"),
            "Bundle base ID mismatch");
    const auto entry = root / "entrypoint";
    require(fs::is_regular_file(fs::symlink_status(entry)) && access(entry.c_str(), X_OK) == 0,
            "Bundle entrypoint must be an executable regular file");
    require(setenv("GRADIATED_RUNTIME_ROOT", root.c_str(), 1) == 0, "Cannot set runtime root");
    std::vector<char*> args{const_cast<char*>(entry.c_str())};
    for (int index = 3; index < argc; ++index) args.push_back(argv[index]);
    args.push_back(nullptr);
    return supervise(args.data());
  } catch (const std::exception& error) {
    std::cerr << "runtime-launch: " << error.what() << '\n';
    return 1;
  }
}
