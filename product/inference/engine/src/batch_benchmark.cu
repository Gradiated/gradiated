#include "gradiated/engine/batch_model_runner.h"
#include "gradiated/engine/device_weights.h"
#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/json.h"
#include "gradiated/engine/safetensors.h"
#include "gradiated/engine/weight_plan.h"

#include <chrono>
#include <algorithm>
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
      std::cerr << "usage: gradiated-engine-batch-benchmark MODEL_DIRECTORY FIXTURE_JSON\n";
      return 64;
    }
    const std::string model_directory = argv[1];
    const auto fixture = gradiated::engine::Json::parse(gradiated::engine::read_text_file(argv[2]));
    const auto prompt = integers(fixture.at("input_ids"));
    const auto expected = integers(fixture.at("expected_output_ids"));
    const auto config = gradiated::engine::Gemma4Config::load(model_directory + "/config.json");
    const auto model_weights = gradiated::engine::ShardedSafetensors::open(model_directory);
    gradiated::engine::validate_gemma4_weights(model_weights, config);
    const auto plan = gradiated::engine::WeightPlan::gemma4(config, model_weights);
    const auto weights = gradiated::engine::DeviceWeightArena::load(plan, model_weights);
    std::cout << "mode,batch,context,greedy_parity,decode_steps,seconds,aggregate_tokens_per_second,per_request_tokens_per_second\n";
    for (const int batch : std::vector<int>{1, 2, 4, 8, 16}) {
      constexpr int decode_steps = 16;
      gradiated::engine::Gemma4BatchModelRunner runner(
          config, *weights, batch, static_cast<int>(prompt.size()) + decode_steps + 1);
      std::vector<int> input(batch);
      std::vector<int> prediction;
      for (const int token : prompt) {
        std::fill(input.begin(), input.end(), token);
        prediction = runner.append(input);
      }
      bool parity = true;
      for (const int token : prediction) parity = parity && token == expected.front();
      const auto begin = std::chrono::steady_clock::now();
      for (int step = 0; step < decode_steps; ++step) {
        input = prediction;
        prediction = runner.append(input);
      }
      const double seconds = std::chrono::duration<double>(
          std::chrono::steady_clock::now() - begin).count();
      const double aggregate = static_cast<double>(batch * decode_steps) / seconds;
      std::cout << "short," << batch << ',' << prompt.size() << ',' << (parity ? "true" : "false") << ',' << decode_steps << ','
                << seconds << ',' << aggregate << ',' << aggregate / batch << '\n';
      if (!parity) return 2;
    }
    for (const int batch : std::vector<int>{1, 4, 8, 16}) {
      constexpr int context = 8192;
      constexpr int decode_steps = 8;
      gradiated::engine::Gemma4BatchModelRunner runner(config, *weights, batch, context + decode_steps + 1);
      runner.seed_empty_cache_for_benchmark(context - 1);
      std::vector<int> input(batch, 2);
      auto prediction = runner.append(input);
      const auto begin = std::chrono::steady_clock::now();
      for (int step = 0; step < decode_steps; ++step) {
        input = prediction;
        prediction = runner.append(input);
      }
      const double seconds = std::chrono::duration<double>(
          std::chrono::steady_clock::now() - begin).count();
      const double aggregate = static_cast<double>(batch * decode_steps) / seconds;
      std::cout << "long," << batch << ',' << context << ",n/a," << decode_steps << ','
                << seconds << ',' << aggregate << ',' << aggregate / batch << '\n';
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "batch benchmark failed: " << error.what() << '\n';
    return 1;
  }
}
