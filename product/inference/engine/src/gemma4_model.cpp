#include "gradiated/engine/gemma4_model.h"

namespace gradiated::engine {

Gemma4Model Gemma4Model::open(const std::string& model_directory) {
  auto config = Gemma4Config::load(model_directory + "/config.json");
  auto weights = ShardedSafetensors::open(model_directory);
  auto plan = WeightPlan::gemma4(config, weights);

  return {.config = std::move(config), .weights = std::move(weights), .plan = std::move(plan)};
}

}  // namespace gradiated::engine
