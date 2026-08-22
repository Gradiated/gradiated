#include "gradiated/engine/batch_model_runner.h"
#include "gradiated/engine/device_weights.h"
#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/json.h"
#include "gradiated/engine/safetensors.h"
#include "gradiated/engine/weight_plan.h"

#include <cuda_profiler_api.h>
#include <cuda_runtime.h>

#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::vector<int> integers(const gradiated::engine::Json& value) {
  std::vector<int> result;
  result.reserve(value.as_array().size());
  for (const auto& item : value.as_array()) result.push_back(static_cast<int>(item.as_i64()));
  return result;
}

void require_equal(const std::vector<int>& actual, const std::vector<int>& expected,
                   const char* stage) {
  if (actual != expected) {
    std::cerr << stage << " mismatch: actual=";
    for (const int token : actual) std::cerr << token << ',';
    std::cerr << " expected=";
    for (const int token : expected) std::cerr << token << ',';
    std::cerr << '\n';
    throw std::runtime_error("ragged parity failed");
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 3 && argc != 4) {
      std::cerr << "usage: gradiated-engine-ragged-batch-parity MODEL_DIRECTORY FIXTURE_JSON [profile-ragged]\n";
      return 64;
    }
    const std::string model_directory = argv[1];
    const auto fixture = gradiated::engine::Json::parse(gradiated::engine::read_text_file(argv[2]));
    const auto prompt = integers(fixture.at("input_ids"));
    const auto expected = integers(fixture.at("expected_output_ids"));
    if (expected.size() < 4) throw std::runtime_error("fixture needs four expected tokens");
    const auto config = gradiated::engine::Gemma4Config::load(model_directory + "/config.json");
    const auto host_weights = gradiated::engine::ShardedSafetensors::open(model_directory);
    gradiated::engine::validate_gemma4_weights(host_weights, config);
    const auto plan = gradiated::engine::WeightPlan::gemma4(config, host_weights);
    const auto weights = gradiated::engine::DeviceWeightArena::load(plan, host_weights);
    if (argc == 4 && std::string(argv[3]) == "profile-ragged") {
      constexpr int batch = 16;
      constexpr int context = 8192;
      constexpr int decode_steps = 8;
      gradiated::engine::Gemma4BatchModelRunner runner(config, *weights, batch,
                                                       context + decode_steps + 1);
      runner.seed_empty_cache_for_benchmark(context - 1);
      std::vector<int> slots(static_cast<std::size_t>(batch));
      for (int index = 0; index < batch; ++index) {
        slots[static_cast<std::size_t>(index)] = batch - 1 - index;
      }
      std::vector<int> input(static_cast<std::size_t>(batch), 2);
      input = runner.append_ragged(input, slots);
      cudaProfilerStart();
      const auto begin = std::chrono::steady_clock::now();
      for (int step = 0; step < decode_steps; ++step) input = runner.append_ragged(input, slots);
      cudaDeviceSynchronize();
      const double seconds =
          std::chrono::duration<double>(std::chrono::steady_clock::now() - begin).count();
      cudaProfilerStop();
      std::cout << "profile_ragged_tokens_per_second="
                << (static_cast<double>(batch * decode_steps) / seconds) << '\n';
      return 0;
    }
    {
      gradiated::engine::Gemma4BatchModelRunner runner(config, *weights, 4, 512);
      const int slot_zero = runner.prefill_slot(0, prompt, 16);
      const int slot_two = runner.prefill_slot(2, prompt, 16);
      require_equal({slot_zero, slot_two}, {expected[0], expected[0]}, "prefill");

      auto prediction = runner.append_ragged({slot_two, slot_zero}, {2, 0});
      require_equal(prediction, {expected[1], expected[1]}, "equal-position ragged decode");
      prediction = runner.append_ragged({prediction[0]}, {2});
      require_equal(prediction, {expected[2]}, "single-slot advance");
      prediction = runner.append_ragged({expected[1], expected[2]}, {0, 2});
      require_equal(prediction, {expected[2], expected[3]}, "unequal-position ragged decode");
      if (runner.slot_position(0) != static_cast<int>(prompt.size()) + 2 ||
          runner.slot_position(2) != static_cast<int>(prompt.size()) + 3) {
        throw std::runtime_error("slot positions were not advanced independently");
      }

      constexpr int measured_steps = 16;
      std::vector<int> slots{0, 2};
      std::vector<int> inputs{prediction[0], prediction[1]};
      const auto begin = std::chrono::steady_clock::now();
      for (int step = 0; step < measured_steps; ++step) inputs = runner.append_ragged(inputs, slots);
      const double seconds =
          std::chrono::duration<double>(std::chrono::steady_clock::now() - begin).count();
      std::cout << "ragged_parity=true\n"
                << "short_ragged_batch=2\n"
                << "short_ragged_tokens_per_second=" << (2.0 * measured_steps / seconds) << '\n';
    }

    std::cout << "mode,batch,context,seconds,aggregate_tokens_per_second\n";
    for (const int batch : std::vector<int>{1, 4, 8, 16}) {
      constexpr int context = 8192;
      constexpr int decode_steps = 8;
      double homogeneous_seconds = 0.0;
      {
        gradiated::engine::Gemma4BatchModelRunner runner(config, *weights, batch,
                                                         context + decode_steps + 1);
        runner.seed_empty_cache_for_benchmark(context - 1);
        std::vector<int> input(static_cast<std::size_t>(batch), 2);
        auto prediction = runner.append(input);
        const auto begin = std::chrono::steady_clock::now();
        for (int step = 0; step < decode_steps; ++step) {
          input = prediction;
          prediction = runner.append(input);
        }
        homogeneous_seconds =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - begin).count();
      }
      std::cout << "homogeneous," << batch << ',' << context << ',' << homogeneous_seconds << ','
                << (static_cast<double>(batch * decode_steps) / homogeneous_seconds) << '\n';

      double ragged_seconds = 0.0;
      {
        gradiated::engine::Gemma4BatchModelRunner runner(config, *weights, batch,
                                                         context + decode_steps + 1);
        runner.seed_empty_cache_for_benchmark(context - 1);
        std::vector<int> slots(static_cast<std::size_t>(batch));
        for (int index = 0; index < batch; ++index) slots[static_cast<std::size_t>(index)] = batch - 1 - index;
        std::vector<int> input(static_cast<std::size_t>(batch), 2);
        auto prediction = runner.append_ragged(input, slots);
        const auto begin = std::chrono::steady_clock::now();
        for (int step = 0; step < decode_steps; ++step) {
          input = prediction;
          prediction = runner.append_ragged(input, slots);
        }
        ragged_seconds =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - begin).count();
      }
      std::cout << "ragged," << batch << ',' << context << ',' << ragged_seconds << ','
                << (static_cast<double>(batch * decode_steps) / ragged_seconds) << '\n';
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "ragged batch parity failed: " << error.what() << '\n';
    return 1;
  }
}
