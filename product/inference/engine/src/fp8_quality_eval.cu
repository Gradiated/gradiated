#include "gradiated/engine/batch_model_runner.h"
#include "gradiated/engine/device_weights.h"
#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/json.h"
#include "gradiated/engine/safetensors.h"
#include "gradiated/engine/weight_plan.h"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr int maximum_context = 8192;
constexpr int evaluated_tokens = 32;

int environment_non_negative_integer(const char* name) {
  const char* value = std::getenv(name);
  if (value == nullptr || *value == '\0') return 0;
  const std::string text(value);
  std::size_t consumed = 0;
  const int parsed = std::stoi(text, &consumed);
  if (consumed != text.size() || parsed < 0) {
    throw std::runtime_error(std::string(name) + " must be a non-negative integer");
  }
  return parsed;
}

struct Prompt {
  std::string identifier;
  std::vector<int> input_ids;
};

std::vector<int> integers(const gradiated::engine::Json& value) {
  std::vector<int> result;
  result.reserve(value.as_array().size());
  for (const auto& item : value.as_array()) result.push_back(static_cast<int>(item.as_i64()));
  return result;
}

gradiated::engine::Fp8Scaling parse_scaling(const std::string& value) {
  if (value == "tensor") return gradiated::engine::Fp8Scaling::tensor;
  if (value == "channel") return gradiated::engine::Fp8Scaling::channel;
  if (value == "block-128") return gradiated::engine::Fp8Scaling::block_128;
  throw std::runtime_error("scaling must be bf16, tensor, channel, or block-128");
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 4) {
      std::cerr << "usage: gradiated-engine-fp8-quality-eval MODEL_DIRECTORY PROMPTS_JSON "
                   "bf16|tensor|channel|block-128\n";
      return 64;
    }
    const bool bf16_candidate = std::string(argv[3]) == "bf16";
    const int suffix_tokens = environment_non_negative_integer(
        "GRADIATED_QUALITY_SUFFIX_TOKENS");
    const int quality_batch = std::max(
        1, environment_non_negative_integer("GRADIATED_QUALITY_BATCH"));
    if (quality_batch > 16) {
      throw std::runtime_error("GRADIATED_QUALITY_BATCH must not exceed 16");
    }
    const auto scaling = bf16_candidate
        ? gradiated::engine::Fp8Scaling::tensor : parse_scaling(argv[3]);
    const std::string model_directory = argv[1];
    const auto fixture = gradiated::engine::Json::parse(
        gradiated::engine::read_text_file(argv[2]));
    const auto config = gradiated::engine::Gemma4Config::load(model_directory + "/config.json");
    const auto host_weights = gradiated::engine::ShardedSafetensors::open(model_directory);
    gradiated::engine::validate_gemma4_weights(host_weights, config);
    const auto plan = gradiated::engine::WeightPlan::gemma4(config, host_weights);
    const auto weights = gradiated::engine::DeviceWeightArena::load(plan, host_weights);

    std::vector<Prompt> prompts;
    for (const auto& item : fixture.at("prompts").as_array()) {
      Prompt prompt{item.at("id").as_string(), integers(item.at("input_ids"))};
      if (prompt.input_ids.empty() ||
          prompt.input_ids.size() + evaluated_tokens >=
              static_cast<std::size_t>(maximum_context)) {
        throw std::runtime_error("quality prompt does not fit context: " + prompt.identifier);
      }
      prompts.push_back(std::move(prompt));
    }

    std::vector<std::vector<int>> references(prompts.size());
    {
      unsetenv("GRADIATED_FP8_GLOBAL_K");
      gradiated::engine::Gemma4BatchModelRunner bf16_runner(
          config, *weights, 1, maximum_context);
      for (std::size_t prompt_index = 0; prompt_index < prompts.size(); ++prompt_index) {
        const auto& prompt = prompts[prompt_index];
        auto& reference = references[prompt_index];
        reference.reserve(evaluated_tokens);
        int prediction = bf16_runner.prefill_slot(0, prompt.input_ids, 1024);
        for (int step = 0; step < evaluated_tokens; ++step) {
          reference.push_back(prediction);
          if (step + 1 != evaluated_tokens) {
            prediction = bf16_runner.append_ragged({prediction}, {0})[0];
          }
        }
        std::cout << "reference_prompt=" << prompt.identifier
                  << " input_tokens=" << prompt.input_ids.size() << std::endl;
      }
    }

    const auto fp8_weights = bf16_candidate
        ? std::unique_ptr<gradiated::engine::Fp8WeightArena>{}
        : gradiated::engine::Fp8WeightArena::quantize(plan, *weights, scaling);

    std::uint64_t total_predictions = 0;
    std::uint64_t matching_predictions = 0;
    std::uint64_t exact_prompts = 0;
    std::uint64_t prompt_count = 0;
    const auto begin = std::chrono::steady_clock::now();
    if (std::getenv("GRADIATED_FP8_GLOBAL_K_EVAL") != nullptr) {
      setenv("GRADIATED_FP8_GLOBAL_K", "1", 1);
    }
    gradiated::engine::Gemma4BatchModelRunner fp8_runner(
        config, *weights, quality_batch, maximum_context, fp8_weights.get());
    for (std::size_t group_start = 0; group_start < prompts.size();
         group_start += static_cast<std::size_t>(quality_batch)) {
      const int group_size = std::min(
          quality_batch, static_cast<int>(prompts.size() - group_start));
      std::vector<int> slots(static_cast<std::size_t>(group_size));
      std::vector<int> predictions(static_cast<std::size_t>(group_size));
      std::vector<const std::vector<int>*> prompt_pointers(
          static_cast<std::size_t>(group_size));
      for (int row = 0; row < group_size; ++row) {
        slots[static_cast<std::size_t>(row)] = row;
        const auto& prompt = prompts[group_start + static_cast<std::size_t>(row)];
        prompt_pointers[static_cast<std::size_t>(row)] = &prompt.input_ids;
        if (suffix_tokens > 0) {
          const int prefix_tokens = static_cast<int>(prompt.input_ids.size()) - suffix_tokens;
          if (prefix_tokens <= 0) {
            throw std::runtime_error("quality suffix consumes complete prompt: " +
                                     prompt.identifier);
          }
          const std::vector<int> prefix(prompt.input_ids.begin(),
                                        prompt.input_ids.begin() + prefix_tokens);
          static_cast<void>(fp8_runner.prefill_slot(row, prefix, 1024));
        } else {
          predictions[static_cast<std::size_t>(row)] =
              fp8_runner.prefill_slot(row, prompt.input_ids, 1024);
        }
      }
      if (suffix_tokens > 0) {
        predictions = fp8_runner.prefill_slots_suffix(slots, prompt_pointers);
      }
      std::vector<int> prompt_matches(static_cast<std::size_t>(group_size), 0);
      std::vector<int> matching_prefix(static_cast<std::size_t>(group_size), 0);
      std::vector<bool> prefix_intact(static_cast<std::size_t>(group_size), true);
      for (int step = 0; step < evaluated_tokens; ++step) {
        std::vector<int> reference_tokens(static_cast<std::size_t>(group_size));
        for (int row = 0; row < group_size; ++row) {
          const int reference = references[group_start + static_cast<std::size_t>(row)]
                                           [static_cast<std::size_t>(step)];
          reference_tokens[static_cast<std::size_t>(row)] = reference;
          const bool match = reference == predictions[static_cast<std::size_t>(row)];
          prompt_matches[static_cast<std::size_t>(row)] += match ? 1 : 0;
          if (prefix_intact[static_cast<std::size_t>(row)] && match) {
            ++matching_prefix[static_cast<std::size_t>(row)];
          } else {
            prefix_intact[static_cast<std::size_t>(row)] = false;
          }
          ++total_predictions;
          matching_predictions += match ? 1U : 0U;
        }
        if (step + 1 != evaluated_tokens) {
          predictions = fp8_runner.append_ragged(reference_tokens, slots);
        }
      }
      for (int row = 0; row < group_size; ++row) {
        const auto& prompt = prompts[group_start + static_cast<std::size_t>(row)];
        if (prompt_matches[static_cast<std::size_t>(row)] == evaluated_tokens) {
          ++exact_prompts;
        }
        ++prompt_count;
        std::cout << "prompt=" << prompt.identifier
                  << " input_tokens=" << prompt.input_ids.size()
                  << " agreement=" << prompt_matches[static_cast<std::size_t>(row)] << '/'
                  << evaluated_tokens
                  << " matching_prefix=" << matching_prefix[static_cast<std::size_t>(row)]
                  << std::endl;
      }
    }
    const double seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - begin).count();
    std::cout << "scaling=" << argv[3] << '\n'
              << "prompts=" << prompt_count << '\n'
              << "exact_prompts=" << exact_prompts << '\n'
              << "matching_predictions=" << matching_predictions << '\n'
              << "total_predictions=" << total_predictions << '\n'
              << "quality_suffix_tokens=" << suffix_tokens << '\n'
              << "quality_batch=" << quality_batch << '\n'
              << "teacher_forced_greedy_agreement="
              << static_cast<double>(matching_predictions) / total_predictions << '\n'
              << "evaluation_seconds=" << seconds << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "FP8 quality evaluation failed: " << error.what() << '\n';
    return 1;
  }
}
