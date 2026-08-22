#include "gradiated/engine/device_weights.h"
#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/safetensors.h"
#include "gradiated/engine/weight_plan.h"

#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char** argv) {
  try {
    if (argc < 2) {
      std::cerr << "usage: gradiated-engine-load MODEL_DIRECTORY [SEGMENT ...]\n";
      return 64;
    }
    const std::string directory = argv[1];
    std::vector<std::string> segments;
    for (int index = 2; index < argc; ++index) segments.emplace_back(argv[index]);
    const auto config = gradiated::engine::Gemma4Config::load(directory + "/config.json");
    const auto weights = gradiated::engine::ShardedSafetensors::open(directory);
    gradiated::engine::validate_gemma4_weights(weights, config);
    const auto plan = gradiated::engine::WeightPlan::gemma4(config, weights);
    const auto begin = std::chrono::steady_clock::now();
    const auto arena = gradiated::engine::DeviceWeightArena::load(plan, weights, segments);
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - begin).count();
    std::cout << "allocated_bytes=" << arena->allocated_bytes() << '\n'
              << "payload_bytes=" << arena->payload_bytes() << '\n'
              << "load_seconds=" << seconds << '\n'
              << "payload_gb_per_second=" << (static_cast<double>(arena->payload_bytes()) / 1e9 / seconds) << '\n'
              << "validation=ok\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "gradiated-engine-load: " << error.what() << '\n';
    return 1;
  }
}
