#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/safetensors.h"
#include "gradiated/engine/weight_plan.h"

#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc, char** argv) {
  try {
    if (argc != 2) {
      std::cerr << "usage: gradiated-engine-inspect MODEL_DIRECTORY\n";
      return 64;
    }
    const std::string directory = argv[1];
    const auto config = gradiated::engine::Gemma4Config::load(directory + "/config.json");
    const auto weights = gradiated::engine::ShardedSafetensors::open(directory);
    gradiated::engine::validate_gemma4_weights(weights, config);
    const auto plan = gradiated::engine::WeightPlan::gemma4(config, weights);

    std::size_t sliding_layers = 0;
    for (const auto& layer : config.layers) {
      if (layer.attention == gradiated::engine::AttentionKind::sliding) ++sliding_layers;
    }
    const std::uint64_t global_layers = config.layers.size() - sliding_layers;
    std::cout << "model=gemma4_text\n"
              << "layers=" << config.layer_count << " sliding_layers=" << sliding_layers
              << " global_layers=" << global_layers << '\n'
              << "hidden_size=" << config.hidden_size
              << " intermediate_size=" << config.intermediate_size
              << " vocabulary_size=" << config.vocabulary_size << '\n'
              << "text_parameters=" << config.text_parameter_count() << '\n'
              << "text_weight_bytes=" << weights.byte_size("model.language_model.") << '\n'
              << "execution_segments=" << plan.segments().size() << '\n'
              << "execution_arena_bytes=" << plan.arena_bytes() << '\n'
              << "bf16_kv_bytes_per_uncapped_token=" << config.full_kv_bytes_per_token() << '\n'
              << "bf16_sliding_kv_bytes_per_sequence="
              << config.resident_sliding_kv_bytes_per_sequence() << '\n'
              << "validation=ok\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "gradiated-engine-inspect: " << error.what() << '\n';
    return 1;
  }
}
