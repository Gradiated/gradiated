#pragma once

#include <string>

namespace desmond {

struct RuntimeIdentity {
  std::string release;
  std::string model;
  std::string model_revision;
};

} // namespace desmond
