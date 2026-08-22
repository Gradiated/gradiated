#include "desmond/http.h"
#include "desmond/profiling.h"
#include "gradiated/engine/device_weights.h"
#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/json.h"
#include "gradiated/engine/model_runner.h"
#include "gradiated/engine/safetensors.h"
#include "gradiated/engine/weight_plan.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

namespace {

constexpr int maximum_context = 8192;
constexpr int default_chunk_tokens = 1024;

std::string environment(const char* name, const std::string& fallback = {}) {
  const char* value = std::getenv(name);
  return value == nullptr ? fallback : std::string(value);
}

std::uint16_t environment_port(const char* name, std::uint16_t fallback) {
  const std::string value = environment(name);
  if (value.empty()) return fallback;
  const int parsed = std::stoi(value);
  if (parsed <= 0 || parsed > 65535) throw std::runtime_error(std::string(name) + " is not a valid port");
  return static_cast<std::uint16_t>(parsed);
}

bool constant_time_equal(const std::string& left, const std::string& right) {
  std::size_t difference = left.size() ^ right.size();
  const std::size_t length = std::max(left.size(), right.size());
  for (std::size_t index = 0; index < length; ++index) {
    const unsigned char a = index < left.size() ? static_cast<unsigned char>(left[index]) : 0U;
    const unsigned char b = index < right.size() ? static_cast<unsigned char>(right[index]) : 0U;
    difference |= static_cast<std::size_t>(a ^ b);
  }
  return difference == 0;
}

std::vector<int> integer_array(const gradiated::engine::Json& value, const char* field) {
  std::vector<int> result;
  result.reserve(value.as_array().size());
  for (const auto& item : value.as_array()) {
    const auto parsed = item.as_i64();
    if (parsed < 0 || parsed > 262143) throw std::runtime_error(std::string(field) + " has an invalid token id");
    result.push_back(static_cast<int>(parsed));
  }
  return result;
}

int optional_integer(const gradiated::engine::Json& object, const char* field, int fallback) {
  const auto* value = object.find(field);
  if (value == nullptr) return fallback;
  const auto parsed = value->as_i64();
  if (parsed < 0 || parsed > 1000000) throw std::runtime_error(std::string(field) + " is out of range");
  return static_cast<int>(parsed);
}

std::string token_array_json(const std::vector<int>& tokens) {
  std::ostringstream output;
  output << '[';
  for (std::size_t index = 0; index < tokens.size(); ++index) {
    if (index != 0) output << ',';
    output << tokens[index];
  }
  output << ']';
  return output.str();
}

struct RuntimeMetrics {
  std::atomic<std::uint64_t> requests{0};
  std::atomic<std::uint64_t> failures{0};
  std::atomic<std::uint64_t> input_tokens{0};
  std::atomic<std::uint64_t> output_tokens{0};
  std::atomic<std::uint64_t> inference_microseconds{0};
  std::atomic<std::uint64_t> queued{0};
};

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 2) {
      std::cerr << "usage: gradiated-engine-runtime MODEL_DIRECTORY\n";
      return 64;
    }
    const std::string model_directory = argv[1];
    const auto config = gradiated::engine::Gemma4Config::load(model_directory + "/config.json");
    const auto host_weights = gradiated::engine::ShardedSafetensors::open(model_directory);
    gradiated::engine::validate_gemma4_weights(host_weights, config);
    const auto plan = gradiated::engine::WeightPlan::gemma4(config, host_weights);
    const auto weights = gradiated::engine::DeviceWeightArena::load(plan, host_weights);
    gradiated::engine::Gemma4ModelRunner runner(config, *weights, maximum_context);

    // Build the latency-relevant 1,024-token linear and SDPA plans before readiness.
    std::vector<int> warmup(2048, 2);
    (void)runner.prefill_chunked(warmup, default_chunk_tokens);
    runner.reset_sequence();

    const std::string configured_key = environment(
        "GRADIATED_RUNTIME_API_KEY", environment("DESMOND_RUNTIME_API_KEY"));
    const std::string expected_authorization = configured_key.empty() ? std::string{} : "Bearer " + configured_key;
    const std::string bind_host = environment("GRADIATED_RUNTIME_HOST", "0.0.0.0");
    const std::uint16_t bind_port = environment_port("GRADIATED_RUNTIME_PORT", 30000);
    std::mutex engine_mutex;
    RuntimeMetrics metrics;

    desmond::HttpServer server(bind_host, bind_port, [&](const desmond::HttpRequest& request) {
      if (request.method == "GET" && request.path == "/health") {
        return desmond::HttpResponse{200, "text/plain; charset=utf-8", "ready\n"};
      }
      if (request.method == "GET" && request.path == "/metrics") {
        std::ostringstream body;
        body << "gradiated_native_requests_total " << metrics.requests.load() << '\n'
             << "gradiated_native_failures_total " << metrics.failures.load() << '\n'
             << "gradiated_native_input_tokens_total " << metrics.input_tokens.load() << '\n'
             << "gradiated_native_output_tokens_total " << metrics.output_tokens.load() << '\n'
             << "gradiated_native_inference_seconds_total "
             << static_cast<double>(metrics.inference_microseconds.load()) / 1000000.0 << '\n'
             << "gradiated_native_queued_requests " << metrics.queued.load() << '\n';
        return desmond::HttpResponse{200, "text/plain; version=0.0.4; charset=utf-8", body.str()};
      }
      if (request.method != "POST" || request.path != "/v1/token-completions") {
        return desmond::HttpResponse{404, "application/json", "{\"error\":\"not_found\"}\n"};
      }
      if (!expected_authorization.empty() &&
          !constant_time_equal(request.authorization, expected_authorization)) {
        return desmond::HttpResponse{401, "application/json", "{\"error\":\"unauthorized\"}\n"};
      }

      metrics.requests.fetch_add(1);
      try {
        const auto body = gradiated::engine::Json::parse(request.body);
        const auto input_ids = integer_array(body.at("input_ids"), "input_ids");
        if (input_ids.empty()) throw std::runtime_error("input_ids must not be empty");
        const int max_tokens = optional_integer(body, "max_tokens", 128);
        if (max_tokens <= 0 || max_tokens > maximum_context - static_cast<int>(input_ids.size())) {
          throw std::runtime_error("max_tokens exceeds the remaining context");
        }
        std::unordered_set<int> stop_ids;
        if (const auto* value = body.find("stop_token_ids")) {
          for (const int token : integer_array(*value, "stop_token_ids")) stop_ids.insert(token);
        }

        metrics.queued.fetch_add(1);
        const auto queue_begin = std::chrono::steady_clock::now();
        std::unique_lock lock(engine_mutex);
        const auto inference_begin = std::chrono::steady_clock::now();
        const auto queue_microseconds = std::chrono::duration_cast<std::chrono::microseconds>(
            inference_begin - queue_begin).count();
        metrics.queued.fetch_sub(1);
        runner.reset_sequence();
        int prediction = runner.prefill_chunked(input_ids, default_chunk_tokens);
        const auto prefill_end = std::chrono::steady_clock::now();
        std::vector<int> output_ids;
        output_ids.reserve(static_cast<std::size_t>(max_tokens));
        for (int index = 0; index < max_tokens; ++index) {
          output_ids.push_back(prediction);
          if (stop_ids.contains(prediction) || index + 1 == max_tokens) break;
          prediction = runner.append(prediction);
        }
        const auto inference_end = std::chrono::steady_clock::now();
        const auto prefill_microseconds = std::chrono::duration_cast<std::chrono::microseconds>(
            prefill_end - inference_begin).count();
        const auto total_microseconds = std::chrono::duration_cast<std::chrono::microseconds>(
            inference_end - inference_begin).count();
        metrics.input_tokens.fetch_add(input_ids.size());
        metrics.output_tokens.fetch_add(output_ids.size());
        metrics.inference_microseconds.fetch_add(static_cast<std::uint64_t>(total_microseconds));
        std::ostringstream response;
        response << "{\"output_ids\":" << token_array_json(output_ids)
                 << ",\"usage\":{\"input_tokens\":" << input_ids.size()
                 << ",\"output_tokens\":" << output_ids.size() << "}"
                 << ",\"timing\":{\"queue_ms\":" << static_cast<double>(queue_microseconds) / 1000.0
                 << ",\"prefill_ms\":" << static_cast<double>(prefill_microseconds) / 1000.0
                 << ",\"total_ms\":" << static_cast<double>(total_microseconds) / 1000.0
                 << "},\"finish_reason\":\""
                 << (output_ids.size() == static_cast<std::size_t>(max_tokens) ? "length" : "stop")
                 << "\"}\n";
        return desmond::HttpResponse{200, "application/json", response.str()};
      } catch (const std::exception& error) {
        metrics.failures.fetch_add(1);
        return desmond::HttpResponse{400, "application/json",
                                     "{\"error\":\"invalid_request\",\"message\":" +
                                         desmond::json_string(error.what()) + "}\n"};
      }
    });
    std::cout << "gradiated native runtime ready on " << bind_host << ':' << bind_port << '\n';
    server.run();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "native runtime failed: " << error.what() << '\n';
    return 70;
  }
}
