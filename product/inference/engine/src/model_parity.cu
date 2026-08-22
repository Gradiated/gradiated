#include "gradiated/engine/device_weights.h"
#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/json.h"
#include "gradiated/engine/model_runner.h"
#include "gradiated/engine/safetensors.h"
#include "gradiated/engine/weight_plan.h"

#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::vector<int> integers(const gradiated::engine::Json& value) {
  std::vector<int> result;
  for (const auto& item : value.as_array()) result.push_back(static_cast<int>(item.as_i64()));
  return result;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 3) {
      std::cerr << "usage: gradiated-engine-model-parity MODEL_DIRECTORY FIXTURE_JSON\n";
      return 64;
    }
    const std::string model_directory = argv[1];
    const auto fixture = gradiated::engine::Json::parse(gradiated::engine::read_text_file(argv[2]));
    const auto input_ids = integers(fixture.at("input_ids"));
    const auto expected_ids = integers(fixture.at("expected_output_ids"));
    const auto config = gradiated::engine::Gemma4Config::load(model_directory + "/config.json");
    const auto model_weights = gradiated::engine::ShardedSafetensors::open(model_directory);
    gradiated::engine::validate_gemma4_weights(model_weights, config);
    const auto plan = gradiated::engine::WeightPlan::gemma4(config, model_weights);
    const auto load_begin = std::chrono::steady_clock::now();
    const auto weights = gradiated::engine::DeviceWeightArena::load(plan, model_weights);
    const double load_seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - load_begin).count();
    gradiated::engine::Gemma4ModelRunner runner(config, *weights,
                                                static_cast<int>(input_ids.size() + expected_ids.size() + 1));
    const auto inference_begin = std::chrono::steady_clock::now();
    int prediction = -1;
    for (const int token : input_ids) prediction = runner.append(token);
    int matches = 0;
    for (std::size_t index = 0; index < expected_ids.size(); ++index) {
      const bool match = prediction == expected_ids[index];
      if (match) ++matches;
      std::cout << "generation_index=" << index << " expected=" << expected_ids[index]
                << " actual=" << prediction << " match=" << (match ? "true" : "false") << '\n';
      if (index + 1 < expected_ids.size()) prediction = runner.append(expected_ids[index]);
    }
    const double inference_seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - inference_begin).count();
    std::cout << "weight_load_seconds=" << load_seconds << '\n'
              << "evaluated_tokens=" << input_ids.size() + expected_ids.size() - 1 << '\n'
              << "inference_seconds=" << inference_seconds << '\n'
              << "tokens_per_second="
              << static_cast<double>(input_ids.size() + expected_ids.size() - 1) / inference_seconds << '\n'
              << "greedy_matches=" << matches << '/' << expected_ids.size() << '\n';
    return matches == static_cast<int>(expected_ids.size()) ? 0 : 2;
  } catch (const std::exception& error) {
    std::cerr << "model parity failed: " << error.what() << '\n';
    return 1;
  }
}
