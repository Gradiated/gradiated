#pragma once

#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/safetensors.h"
#include "gradiated/engine/weight_plan.h"

#include <string>

namespace gradiated::engine {

struct Gemma4Model {
  Gemma4Config config;
  ShardedSafetensors weights;
  WeightPlan plan;

  static Gemma4Model open(const std::string& model_directory);
};

}  // namespace gradiated::engine
