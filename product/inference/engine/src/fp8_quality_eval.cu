#include "gradiated/engine/batch_model_runner.h"
#include "gradiated/engine/device_weights.h"
#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/json.h"
#include "gradiated/engine/safetensors.h"
#include "gradiated/engine/weight_plan.h"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <numeric>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr int maximum_context = 8192;
constexpr int default_evaluated_tokens = 32;

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

float environment_weight_scale_multiplier() {
  const char* value = std::getenv("GRADIATED_FP8_WEIGHT_SCALE_MULTIPLIER");
  if (value == nullptr || *value == '\0') return 1.0F;
  const std::string text(value);
  std::size_t consumed = 0;
  const float parsed = std::stof(text, &consumed);
  if (consumed != text.size() || parsed <= 0.0F || parsed > 1.0F) {
    throw std::runtime_error(
        "GRADIATED_FP8_WEIGHT_SCALE_MULTIPLIER must be in (0, 1]");
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

std::vector<std::vector<int>> load_references(
    const std::string& path, const std::vector<Prompt>& prompts, int evaluated_tokens) {
  std::ifstream input(path);
  if (!input) throw std::runtime_error("cannot read quality references " + path);
  std::map<std::pair<std::string, std::size_t>, std::vector<int>> by_prompt;
  std::string line;
  while (std::getline(input, line)) {
    if (line.empty()) continue;
    const auto record = gradiated::engine::Json::parse(line);
    const std::string& identifier = record.at("id").as_string();
    const std::size_t input_tokens =
        static_cast<std::size_t>(record.at("input_tokens").as_i64());
    auto tokens = integers(record.at("reference_ids"));
    if (tokens.size() < static_cast<std::size_t>(evaluated_tokens)) {
      throw std::runtime_error("quality reference is too short: " + identifier);
    }
    tokens.resize(static_cast<std::size_t>(evaluated_tokens));
    const auto key = std::make_pair(identifier, input_tokens);
    const auto existing = by_prompt.find(key);
    if (existing == by_prompt.end()) {
      by_prompt.emplace(key, std::move(tokens));
    } else if (existing->second != tokens) {
      throw std::runtime_error("quality artifact has conflicting references: " + identifier);
    }
  }
  if (!input.eof()) throw std::runtime_error("cannot finish quality references " + path);

  std::vector<std::vector<int>> references;
  references.reserve(prompts.size());
  for (const auto& prompt : prompts) {
    const auto reference = by_prompt.find(
        std::make_pair(prompt.identifier, prompt.input_ids.size()));
    if (reference == by_prompt.end()) {
      throw std::runtime_error("missing quality reference: " + prompt.identifier);
    }
    references.push_back(reference->second);
    std::cout << "loaded_reference_prompt=" << prompt.identifier
              << " input_tokens=" << prompt.input_ids.size() << std::endl;
  }
  return references;
}

std::vector<int> through_eos(const std::vector<int>& tokens) {
  const auto end = std::find_if(tokens.begin(), tokens.end(), [](int token) {
    return token == 1 || token == 106;
  });
  return end == tokens.end() ? tokens : std::vector<int>(tokens.begin(), end + 1);
}

std::string json_string(std::string_view value) {
  std::string result;
  result.reserve(value.size() + 2);
  result.push_back('"');
  constexpr char hexadecimal[] = "0123456789abcdef";
  for (const unsigned char character : value) {
    switch (character) {
      case '"': result += "\\\""; break;
      case '\\': result += "\\\\"; break;
      case '\b': result += "\\b"; break;
      case '\f': result += "\\f"; break;
      case '\n': result += "\\n"; break;
      case '\r': result += "\\r"; break;
      case '\t': result += "\\t"; break;
      default:
        if (character < 0x20U) {
          result += "\\u00";
          result.push_back(hexadecimal[character >> 4U]);
          result.push_back(hexadecimal[character & 0x0fU]);
        } else {
          result.push_back(static_cast<char>(character));
        }
    }
  }
  result.push_back('"');
  return result;
}

void write_token_array(std::ostream& output, const std::vector<int>& tokens) {
  output << '[';
  for (std::size_t index = 0; index < tokens.size(); ++index) {
    if (index != 0) output << ',';
    output << tokens[index];
  }
  output << ']';
}

void append_quality_artifact(
    const std::string& path, std::string_view scaling, float weight_scale_multiplier,
    std::string_view precision_case,
    const std::vector<Prompt>& prompts, const std::vector<std::vector<int>>& references,
    const std::vector<std::vector<int>>& candidates) {
  std::ofstream output(path, std::ios::app);
  if (!output) throw std::runtime_error("cannot append quality artifact " + path);
  for (std::size_t index = 0; index < prompts.size(); ++index) {
    output << "{\"id\":" << json_string(prompts[index].identifier)
           << ",\"scaling\":" << json_string(scaling)
           << ",\"weight_scale_multiplier\":" << weight_scale_multiplier
           << ",\"bf16_layers\":" << json_string(precision_case)
           << ",\"input_tokens\":" << prompts[index].input_ids.size()
           << ",\"reference_ids\":";
    write_token_array(output, references[index]);
    output << ",\"candidate_ids\":";
    write_token_array(output, candidates[index]);
    output << "}\n";
  }
  if (!output) throw std::runtime_error("cannot write quality artifact " + path);
}

std::size_t edit_distance(const std::vector<int>& left, const std::vector<int>& right) {
  std::vector<std::size_t> previous(right.size() + 1);
  std::vector<std::size_t> current(right.size() + 1);
  for (std::size_t index = 0; index <= right.size(); ++index) previous[index] = index;
  for (std::size_t left_index = 1; left_index <= left.size(); ++left_index) {
    current[0] = left_index;
    for (std::size_t right_index = 1; right_index <= right.size(); ++right_index) {
      const std::size_t substitution = previous[right_index - 1] +
          (left[left_index - 1] == right[right_index - 1] ? 0U : 1U);
      current[right_index] = std::min({previous[right_index] + 1,
                                       current[right_index - 1] + 1,
                                       substitution});
    }
    std::swap(previous, current);
  }
  return previous.back();
}

gradiated::engine::Fp8Scaling parse_scaling(const std::string& value) {
  if (value == "tensor") return gradiated::engine::Fp8Scaling::tensor;
  if (value == "channel") return gradiated::engine::Fp8Scaling::channel;
  if (value == "block-128") return gradiated::engine::Fp8Scaling::block_128;
  throw std::runtime_error("scaling must be bf16, tensor, channel, or block-128");
}

std::vector<float> weight_scale_cases(bool bf16_candidate) {
  if (bf16_candidate) return {1.0F};
  const char* configured = std::getenv("GRADIATED_QUALITY_WEIGHT_SCALE_CASES");
  if (configured == nullptr || *configured == '\0') {
    return {environment_weight_scale_multiplier()};
  }

  std::vector<float> cases;
  const std::string_view specification(configured);
  std::size_t begin = 0;
  while (begin < specification.size()) {
    const std::size_t end = specification.find(',', begin);
    const std::string item(specification.substr(
        begin, end == std::string_view::npos ? specification.size() - begin : end - begin));
    std::size_t consumed = 0;
    const float parsed = std::stof(item, &consumed);
    if (consumed != item.size() || parsed <= 0.0F || parsed > 1.0F) {
      throw std::runtime_error(
          "GRADIATED_QUALITY_WEIGHT_SCALE_CASES entries must be in (0, 1]");
    }
    cases.push_back(parsed);
    if (end == std::string_view::npos) break;
    begin = end + 1;
  }
  if (cases.empty()) {
    throw std::runtime_error("GRADIATED_QUALITY_WEIGHT_SCALE_CASES is empty");
  }
  return cases;
}

std::vector<std::string> precision_cases() {
  const char* configured = std::getenv("GRADIATED_QUALITY_BF16_LAYER_CASES");
  if (configured == nullptr || *configured == '\0') {
    const char* selected = std::getenv("GRADIATED_FP8_BF16_LAYERS");
    return {selected == nullptr || *selected == '\0' ? "none" : selected};
  }

  std::vector<std::string> cases;
  const std::string_view specification(configured);
  std::size_t begin = 0;
  while (begin < specification.size()) {
    const std::size_t end = specification.find(';', begin);
    const std::string_view item = specification.substr(
        begin, end == std::string_view::npos ? specification.size() - begin : end - begin);
    if (item.empty()) {
      throw std::runtime_error(
          "GRADIATED_QUALITY_BF16_LAYER_CASES contains an empty case");
    }
    cases.emplace_back(item);
    if (end == std::string_view::npos) break;
    begin = end + 1;
  }
  return cases;
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
    const int configured_evaluated_tokens = environment_non_negative_integer(
        "GRADIATED_QUALITY_EVALUATED_TOKENS");
    const int evaluated_tokens = configured_evaluated_tokens == 0
        ? default_evaluated_tokens : configured_evaluated_tokens;
    if (evaluated_tokens > 512) {
      throw std::runtime_error("GRADIATED_QUALITY_EVALUATED_TOKENS must not exceed 512");
    }
    const bool free_running = std::getenv("GRADIATED_QUALITY_FREE_RUNNING") != nullptr;
    const char* artifact_environment = std::getenv("GRADIATED_QUALITY_OUTPUT_JSONL");
    const std::string artifact_path = artifact_environment == nullptr
        ? std::string{} : std::string(artifact_environment);
    if (!artifact_path.empty()) {
      std::ofstream reset(artifact_path, std::ios::trunc);
      if (!reset) throw std::runtime_error("cannot create quality artifact " + artifact_path);
    }
    const int suffix_tokens = environment_non_negative_integer(
        "GRADIATED_QUALITY_SUFFIX_TOKENS");
    const int quality_batch = std::max(
        1, environment_non_negative_integer("GRADIATED_QUALITY_BATCH"));
    if (quality_batch > 16) {
      throw std::runtime_error("GRADIATED_QUALITY_BATCH must not exceed 16");
    }
    const int reference_batch = std::max(
        1, environment_non_negative_integer("GRADIATED_QUALITY_REFERENCE_BATCH"));
    if (reference_batch > 16) {
      throw std::runtime_error("GRADIATED_QUALITY_REFERENCE_BATCH must not exceed 16");
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

    const char* reference_environment = std::getenv("GRADIATED_QUALITY_REFERENCE_JSONL");
    std::vector<std::vector<int>> references;
    if (reference_environment != nullptr && *reference_environment != '\0') {
      references = load_references(reference_environment, prompts, evaluated_tokens);
    } else {
      references.resize(prompts.size());
      unsetenv("GRADIATED_FP8_GLOBAL_K");
      unsetenv("GRADIATED_FP8_GLOBAL_KV");
      unsetenv("GRADIATED_INT8_GLOBAL_K");
      unsetenv("GRADIATED_INT8_GLOBAL_KV");
      unsetenv("GRADIATED_INT8_GLOBAL_KV_ORACLE");
      gradiated::engine::Gemma4BatchModelRunner bf16_runner(
          config, *weights, reference_batch, maximum_context);
      for (std::size_t group_start = 0; group_start < prompts.size();
           group_start += static_cast<std::size_t>(reference_batch)) {
        const int group_size = std::min(
            reference_batch, static_cast<int>(prompts.size() - group_start));
        std::vector<int> slots(static_cast<std::size_t>(group_size));
        std::vector<int> predictions(static_cast<std::size_t>(group_size));
        for (int row = 0; row < group_size; ++row) {
          slots[static_cast<std::size_t>(row)] = row;
          const auto& prompt = prompts[group_start + static_cast<std::size_t>(row)];
          references[group_start + static_cast<std::size_t>(row)].reserve(evaluated_tokens);
          predictions[static_cast<std::size_t>(row)] =
              bf16_runner.prefill_slot(row, prompt.input_ids, 1024);
        }
        for (int step = 0; step < evaluated_tokens; ++step) {
          for (int row = 0; row < group_size; ++row) {
            references[group_start + static_cast<std::size_t>(row)].push_back(
                predictions[static_cast<std::size_t>(row)]);
          }
          if (step + 1 != evaluated_tokens) {
            predictions = bf16_runner.append_ragged(predictions, slots);
          }
        }
        for (int row = 0; row < group_size; ++row) {
          const auto& prompt = prompts[group_start + static_cast<std::size_t>(row)];
          std::cout << "reference_prompt=" << prompt.identifier
                    << " input_tokens=" << prompt.input_ids.size() << std::endl;
        }
      }
    }

    if (std::getenv("GRADIATED_FP8_GLOBAL_K_EVAL") != nullptr) {
      setenv("GRADIATED_FP8_GLOBAL_K", "1", 1);
    }
    if (std::getenv("GRADIATED_FP8_GLOBAL_KV_EVAL") != nullptr) {
      setenv("GRADIATED_FP8_GLOBAL_KV", "1", 1);
    }
    if (std::getenv("GRADIATED_INT8_GLOBAL_KV_ORACLE_EVAL") != nullptr) {
      setenv("GRADIATED_INT8_GLOBAL_KV_ORACLE", "1", 1);
    }
    if (std::getenv("GRADIATED_INT8_GLOBAL_KV_EVAL") != nullptr) {
      setenv("GRADIATED_INT8_GLOBAL_KV", "1", 1);
    } else if (std::getenv("GRADIATED_INT8_GLOBAL_K_EVAL") != nullptr) {
      setenv("GRADIATED_INT8_GLOBAL_K", "1", 1);
    }
    const auto cases = precision_cases();
    for (const float weight_scale_multiplier : weight_scale_cases(bf16_candidate)) {
      const auto fp8_weights = bf16_candidate
          ? std::unique_ptr<gradiated::engine::Fp8WeightArena>{}
          : gradiated::engine::Fp8WeightArena::quantize(
                plan, *weights, scaling,
                scaling == gradiated::engine::Fp8Scaling::tensor
                    ? weight_scale_multiplier : 1.0F);
    for (const auto& precision_case : cases) {
      if (precision_case == "none") {
        unsetenv("GRADIATED_FP8_BF16_LAYERS");
      } else {
        setenv("GRADIATED_FP8_BF16_LAYERS", precision_case.c_str(), 1);
      }
      std::uint64_t total_predictions = 0;
      std::uint64_t matching_predictions = 0;
      std::uint64_t exact_prompts = 0;
      std::uint64_t prompt_count = 0;
      std::vector<std::vector<int>> candidate_sequences(prompts.size());
      const auto begin = std::chrono::steady_clock::now();
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
            candidate_sequences[group_start + static_cast<std::size_t>(row)].push_back(
                predictions[static_cast<std::size_t>(row)]);
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
          predictions = fp8_runner.append_ragged(
              free_running ? predictions : reference_tokens, slots);
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
      std::vector<double> edit_similarities;
      std::uint64_t eos_exact_prompts = 0;
      edit_similarities.reserve(prompts.size());
      for (std::size_t prompt_index = 0; prompt_index < prompts.size(); ++prompt_index) {
        const auto reference = through_eos(references[prompt_index]);
        const auto candidate = through_eos(candidate_sequences[prompt_index]);
        const std::size_t denominator = std::max(reference.size(), candidate.size());
        const double similarity = denominator == 0 ? 1.0 :
            1.0 - static_cast<double>(edit_distance(reference, candidate)) / denominator;
        edit_similarities.push_back(similarity);
        eos_exact_prompts += reference == candidate ? 1U : 0U;
        std::cout << "prompt_edit=" << prompts[prompt_index].identifier
                  << " reference_tokens=" << reference.size()
                  << " candidate_tokens=" << candidate.size()
                  << " similarity=" << similarity << '\n';
      }
      std::sort(edit_similarities.begin(), edit_similarities.end());
      const double mean_edit_similarity = std::accumulate(
          edit_similarities.begin(), edit_similarities.end(), 0.0) /
          edit_similarities.size();
      std::cout << "bf16_layers=" << precision_case << '\n'
                << "scaling=" << argv[3] << '\n'
                << "weight_scale_multiplier=" << weight_scale_multiplier << '\n'
                << "prompts=" << prompt_count << '\n'
                << "exact_prompts=" << exact_prompts << '\n'
                << "matching_predictions=" << matching_predictions << '\n'
                << "total_predictions=" << total_predictions << '\n'
                << "quality_suffix_tokens=" << suffix_tokens << '\n'
                << "quality_batch=" << quality_batch << '\n'
                << "reference_batch=" << reference_batch << '\n'
                << "free_running=" << (free_running ? "true" : "false") << '\n'
                << "eos_exact_prompts=" << eos_exact_prompts << '\n'
                << "mean_token_edit_similarity=" << mean_edit_similarity << '\n'
                << "minimum_token_edit_similarity=" << edit_similarities.front() << '\n'
                << "teacher_forced_greedy_agreement="
                << static_cast<double>(matching_predictions) / total_predictions << '\n'
                << "evaluation_seconds=" << seconds << '\n';
      if (!artifact_path.empty()) {
        append_quality_artifact(
            artifact_path, argv[3], weight_scale_multiplier, precision_case, prompts,
            references, candidate_sequences);
      }
    }
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "FP8 quality evaluation failed: " << error.what() << '\n';
    return 1;
  }
}
