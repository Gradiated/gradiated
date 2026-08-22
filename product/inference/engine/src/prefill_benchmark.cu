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

double run(gradiated::engine::Gemma4ModelRunner& runner, const std::vector<int>& prompt) {
  const auto begin = std::chrono::steady_clock::now();
  const int prediction = runner.prefill(prompt);
  const double seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - begin).count();
  if (prediction < 0) throw std::runtime_error("invalid greedy prediction");
  return seconds;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 3) {
      std::cerr << "usage: gradiated-engine-prefill-benchmark MODEL_DIRECTORY FIXTURE_JSON\n";
      return 64;
    }
    const std::string model_directory = argv[1];
    const auto fixture = gradiated::engine::Json::parse(gradiated::engine::read_text_file(argv[2]));
    const auto seed = integers(fixture.at("input_ids"));
    if (seed.empty()) throw std::runtime_error("fixture prompt is empty");
    const auto config = gradiated::engine::Gemma4Config::load(model_directory + "/config.json");
    const auto model_weights = gradiated::engine::ShardedSafetensors::open(model_directory);
    gradiated::engine::validate_gemma4_weights(model_weights, config);
    const auto plan = gradiated::engine::WeightPlan::gemma4(config, model_weights);
    const auto weights = gradiated::engine::DeviceWeightArena::load(plan, model_weights);
    constexpr int maximum_tokens = 8192;
    gradiated::engine::Gemma4ModelRunner runner(config, *weights, maximum_tokens + 1);

    std::cout << "tokens,cold_seconds,cold_tokens_per_second,warm_seconds,warm_tokens_per_second\n";
    for (const int tokens : std::vector<int>{27, 128, 512, 1024, 2048, 4096, 8192}) {
      std::vector<int> prompt;
      prompt.reserve(tokens);
      for (int index = 0; index < tokens; ++index) {
        prompt.push_back(seed[static_cast<std::size_t>(index) % seed.size()]);
      }
      runner.reset_sequence();
      const double cold = run(runner, prompt);
      runner.reset_sequence();
      const double warm = run(runner, prompt);
      std::cout << tokens << ',' << cold << ',' << tokens / cold << ','
                << warm << ',' << tokens / warm << '\n';
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "prefill benchmark failed: " << error.what() << '\n';
    return 1;
  }
}
