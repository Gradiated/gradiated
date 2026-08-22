#include "desmond/http.h"
#include "desmond/profiling.h"
#include "gradiated/engine/device_weights.h"
#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/json.h"
#include "gradiated/engine/batch_model_runner.h"
#include "gradiated/engine/safetensors.h"
#include "gradiated/engine/weight_plan.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <deque>
#include <iostream>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_set>
#include <vector>

namespace {

constexpr int maximum_context = 8192;
constexpr int default_chunk_tokens = 1024;
constexpr int default_scheduler_prefill_quantum_tokens = 128;
constexpr int default_idle_prefill_quantum_tokens = 1024;
constexpr int maximum_slots = 16;

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

int environment_integer(const char* name, int fallback, int minimum, int maximum) {
  const std::string value = environment(name);
  if (value.empty()) return fallback;
  std::size_t consumed = 0;
  const long long parsed = std::stoll(value, &consumed);
  if (consumed != value.size() || parsed < minimum || parsed > maximum) {
    throw std::runtime_error(std::string(name) + " is out of range");
  }
  return static_cast<int>(parsed);
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
  std::atomic<std::uint64_t> active{0};
  std::atomic<std::uint64_t> decoding{0};
  std::atomic<std::uint64_t> prefix_cache_hits{0};
  std::atomic<std::uint64_t> prefix_tokens_reused{0};
  std::atomic<std::uint64_t> prefill_tokens_computed{0};
  std::atomic<std::uint64_t> kv_cache_clones{0};
  std::atomic<std::uint64_t> kv_cache_clone_bytes{0};
};

struct CompletionResult {
  std::vector<int> output_ids;
  std::uint64_t queue_microseconds{0};
  std::uint64_t ttft_microseconds{0};
  std::uint64_t decode_microseconds{0};
  std::uint64_t maximum_tpot_microseconds{0};
  std::uint64_t total_microseconds{0};
  std::string finish_reason;
};

class InferenceFailure : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

struct CompletionJob {
  std::vector<int> input_ids;
  int max_tokens{0};
  std::unordered_set<int> stop_ids;
  std::chrono::steady_clock::time_point queued_at;
  std::mutex mutex;
  std::condition_variable condition;
  bool done{false};
  std::optional<CompletionResult> result;
  std::string error;
};

class ContinuousScheduler {
 public:
  ContinuousScheduler(const gradiated::engine::Gemma4Config& config,
                      const gradiated::engine::DeviceWeightArena& weights,
                      RuntimeMetrics& metrics, int prefill_quantum_tokens,
                      int idle_prefill_quantum_tokens)
      : runner_(config, weights, maximum_slots, maximum_context),
        slots_(maximum_slots), metrics_(metrics),
        prefill_quantum_tokens_(prefill_quantum_tokens),
        idle_prefill_quantum_tokens_(idle_prefill_quantum_tokens) {
    // Materialize latency-sensitive cuBLASLt and attention plans before advertising readiness.
    std::vector<int> warmup(2048, 2);
    while (!runner_.prefill_slot_chunk(0, warmup, default_chunk_tokens)) {}
    runner_.reset_slot(0);
    worker_ = std::thread([this] { run(); });
  }

  ~ContinuousScheduler() {
    {
      std::lock_guard lock(mutex_);
      stopping_ = true;
    }
    condition_.notify_all();
    worker_.join();
  }

  CompletionResult complete(std::vector<int> input_ids, int max_tokens,
                            std::unordered_set<int> stop_ids) {
    auto job = std::make_shared<CompletionJob>();
    job->input_ids = std::move(input_ids);
    job->max_tokens = max_tokens;
    job->stop_ids = std::move(stop_ids);
    job->queued_at = std::chrono::steady_clock::now();
    {
      std::lock_guard lock(mutex_);
      if (stopping_) throw std::runtime_error("runtime scheduler is stopping");
      pending_.push_back(job);
      metrics_.queued.fetch_add(1);
    }
    condition_.notify_one();
    std::unique_lock lock(job->mutex);
    job->condition.wait(lock, [&] { return job->done; });
    if (!job->error.empty()) throw InferenceFailure(job->error);
    return std::move(*job->result);
  }

 private:
  struct Slot {
    std::shared_ptr<CompletionJob> job;
    std::vector<int> cached_tokens;
    std::vector<int> output_ids;
    int token_to_append{0};
    std::chrono::steady_clock::time_point inference_begin;
    std::uint64_t queue_microseconds{0};
    std::uint64_t ttft_microseconds{0};
    std::uint64_t decode_microseconds{0};
    std::uint64_t maximum_tpot_microseconds{0};
    std::uint64_t age{0};
    std::uint64_t admission_order{0};
    bool decode_ready{false};
    std::chrono::steady_clock::time_point last_token_at;
  };

  struct Placement {
    int destination{-1};
    int source{-1};
    std::size_t prefix_tokens{0};
  };

  static bool starts_with(const std::vector<int>& input, const std::vector<int>& prefix) {
    return !prefix.empty() && prefix.size() <= input.size() &&
           std::equal(prefix.begin(), prefix.end(), input.begin());
  }

  Placement select_slot(const CompletionJob& job) const {
    Placement placement;
    std::size_t longest_prefix = 0;
    for (int index = 0; index < maximum_slots; ++index) {
      const auto& slot = slots_[static_cast<std::size_t>(index)];
      if (!starts_with(job.input_ids, slot.cached_tokens)) continue;
      if (slot.cached_tokens.size() > longest_prefix ||
          (slot.cached_tokens.size() == longest_prefix && placement.source >= 0 &&
           slots_[static_cast<std::size_t>(placement.source)].job && !slot.job)) {
        placement.source = index;
        longest_prefix = slot.cached_tokens.size();
      }
    }
    placement.prefix_tokens = longest_prefix;
    if (placement.source >= 0 &&
        !slots_[static_cast<std::size_t>(placement.source)].job) {
      placement.destination = placement.source;
      return placement;
    }
    for (int index = 0; index < maximum_slots; ++index) {
      const auto& slot = slots_[static_cast<std::size_t>(index)];
      if (!slot.job && slot.cached_tokens.empty()) {
        placement.destination = index;
        return placement;
      }
    }
    std::uint64_t oldest = std::numeric_limits<std::uint64_t>::max();
    for (int index = 0; index < maximum_slots; ++index) {
      const auto& slot = slots_[static_cast<std::size_t>(index)];
      if (!slot.job && slot.age < oldest) {
        oldest = slot.age;
        placement.destination = index;
      }
    }
    return placement;
  }

  void complete_slot(int index, const char* finish_reason) {
    auto& slot = slots_[static_cast<std::size_t>(index)];
    const auto now = std::chrono::steady_clock::now();
    CompletionResult result;
    result.output_ids = std::move(slot.output_ids);
    result.queue_microseconds = slot.queue_microseconds;
    result.ttft_microseconds = slot.ttft_microseconds;
    result.decode_microseconds = slot.decode_microseconds;
    result.maximum_tpot_microseconds = slot.maximum_tpot_microseconds;
    result.total_microseconds = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::microseconds>(now - slot.job->queued_at).count());
    result.finish_reason = finish_reason;
    metrics_.input_tokens.fetch_add(slot.job->input_ids.size());
    metrics_.output_tokens.fetch_add(result.output_ids.size());
    metrics_.inference_microseconds.fetch_add(result.total_microseconds);
    metrics_.active.fetch_sub(1);
    if (slot.decode_ready) metrics_.decoding.fetch_sub(1);
    auto job = std::move(slot.job);
    slot.decode_ready = false;
    slot.age = ++age_;
    {
      std::lock_guard lock(job->mutex);
      job->result = std::move(result);
      job->done = true;
    }
    job->condition.notify_one();
  }

  void fail_slot(int index, const std::string& error) {
    auto& slot = slots_[static_cast<std::size_t>(index)];
    auto job = std::move(slot.job);
    slot.cached_tokens.clear();
    slot.output_ids.clear();
    runner_.reset_slot(index);
    metrics_.failures.fetch_add(1);
    metrics_.active.fetch_sub(1);
    if (slot.decode_ready) metrics_.decoding.fetch_sub(1);
    slot.decode_ready = false;
    {
      std::lock_guard lock(job->mutex);
      job->error = error;
      job->done = true;
    }
    job->condition.notify_one();
  }

  bool admit_one() {
    std::shared_ptr<CompletionJob> job;
    Placement placement;
    {
      std::lock_guard lock(mutex_);
      if (pending_.empty()) return false;
      placement = select_slot(*pending_.front());
      if (placement.destination < 0) return false;
      job = std::move(pending_.front());
      pending_.pop_front();
      metrics_.queued.fetch_sub(1);
      slots_[static_cast<std::size_t>(placement.destination)].job = job;
    }
    const int index = placement.destination;
    auto& slot = slots_[static_cast<std::size_t>(index)];
    slot.output_ids.clear();
    slot.decode_ready = false;
    slot.inference_begin = std::chrono::steady_clock::now();
    slot.queue_microseconds = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::microseconds>(slot.inference_begin - job->queued_at)
            .count());
    slot.ttft_microseconds = 0;
    slot.decode_microseconds = 0;
    slot.maximum_tpot_microseconds = 0;
    slot.admission_order = ++admission_order_;
    metrics_.active.fetch_add(1);
    try {
      int cached_prediction = 0;
      if (placement.source >= 0) {
        cached_prediction = slots_[static_cast<std::size_t>(placement.source)].token_to_append;
      }
      if (placement.source >= 0 && placement.source != index) {
        const auto& source = slots_[static_cast<std::size_t>(placement.source)];
        const std::uint64_t copied_bytes = runner_.clone_slot(placement.source, index);
        slot.cached_tokens = source.cached_tokens;
        metrics_.kv_cache_clones.fetch_add(1);
        metrics_.kv_cache_clone_bytes.fetch_add(copied_bytes);
      } else if (placement.source < 0) {
        runner_.reset_slot(index);
        slot.cached_tokens.clear();
      }
      if (placement.source >= 0) {
        metrics_.prefix_cache_hits.fetch_add(1);
        metrics_.prefix_tokens_reused.fetch_add(
            static_cast<std::uint64_t>(placement.prefix_tokens));
      }
      if (placement.prefix_tokens == job->input_ids.size()) {
        const auto token_time = std::chrono::steady_clock::now();
        slot.token_to_append = cached_prediction;
        slot.output_ids.push_back(cached_prediction);
        slot.decode_ready = true;
        slot.ttft_microseconds = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(
                token_time - job->queued_at).count());
        slot.last_token_at = token_time;
        metrics_.decoding.fetch_add(1);
        if (job->stop_ids.contains(cached_prediction)) {
          complete_slot(index, "stop");
        } else if (job->max_tokens == 1) {
          complete_slot(index, "length");
        }
      }
    } catch (const std::exception& error) {
      fail_slot(index, error.what());
    }
    return true;
  }

  bool prefill_step() {
    int selected = -1;
    std::uint64_t oldest = std::numeric_limits<std::uint64_t>::max();
    for (int index = 0; index < maximum_slots; ++index) {
      const auto& slot = slots_[static_cast<std::size_t>(index)];
      if (slot.job && !slot.decode_ready && slot.admission_order < oldest) {
        oldest = slot.admission_order;
        selected = index;
      }
    }
    if (selected < 0) return false;
    auto& slot = slots_[static_cast<std::size_t>(selected)];
    try {
      const int before = runner_.slot_position(selected);
      const bool decode_is_active = std::any_of(
          slots_.begin(), slots_.end(), [](const Slot& candidate) { return candidate.decode_ready; });
      const int quantum = decode_is_active
          ? prefill_quantum_tokens_ : idle_prefill_quantum_tokens_;
      const auto prediction = runner_.prefill_slot_chunk(
          selected, slot.job->input_ids, quantum);
      const auto end = std::chrono::steady_clock::now();
      const int resident = runner_.slot_position(selected);
      metrics_.prefill_tokens_computed.fetch_add(static_cast<std::uint64_t>(resident - before));
      slot.cached_tokens.assign(slot.job->input_ids.begin(),
                                slot.job->input_ids.begin() + resident);
      if (!prediction) return true;

      slot.token_to_append = *prediction;
      slot.output_ids.push_back(*prediction);
      slot.decode_ready = true;
      slot.ttft_microseconds = static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::microseconds>(end - slot.job->queued_at).count());
      slot.last_token_at = end;
      metrics_.decoding.fetch_add(1);
      if (slot.job->stop_ids.contains(*prediction)) {
        complete_slot(selected, "stop");
      } else if (slot.job->max_tokens == 1) {
        complete_slot(selected, "length");
      }
    } catch (const std::exception& error) {
      fail_slot(selected, error.what());
    }
    return true;
  }

  bool decode_step() {
    std::vector<int> indices;
    std::vector<int> slots;
    std::vector<int> tokens;
    for (int index = 0; index < maximum_slots; ++index) {
      const auto& slot = slots_[static_cast<std::size_t>(index)];
      if (!slot.job || !slot.decode_ready) continue;
      indices.push_back(index);
      slots.push_back(index);
      tokens.push_back(slot.token_to_append);
    }
    if (indices.empty()) return false;
    try {
      const auto predictions = runner_.append_ragged(tokens, slots);
      const auto token_time = std::chrono::steady_clock::now();
      for (std::size_t row = 0; row < indices.size(); ++row) {
        const int index = indices[row];
        auto& slot = slots_[static_cast<std::size_t>(index)];
        slot.cached_tokens.push_back(slot.token_to_append);
        slot.token_to_append = predictions[row];
        slot.output_ids.push_back(slot.token_to_append);
        const auto tpot = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(token_time - slot.last_token_at)
                .count());
        slot.decode_microseconds += tpot;
        slot.maximum_tpot_microseconds = std::max(slot.maximum_tpot_microseconds, tpot);
        slot.last_token_at = token_time;
        if (slot.job->stop_ids.contains(slot.token_to_append)) {
          complete_slot(index, "stop");
        } else if (slot.output_ids.size() >= static_cast<std::size_t>(slot.job->max_tokens)) {
          complete_slot(index, "length");
        }
      }
    } catch (const std::exception& error) {
      for (const int index : indices) fail_slot(index, error.what());
    }
    return true;
  }

  bool has_active() const {
    return std::any_of(slots_.begin(), slots_.end(), [](const Slot& slot) { return slot.job != nullptr; });
  }

  void run() {
    while (true) {
      bool worked = false;
      while (admit_one()) worked = true;
      if (decode_step()) worked = true;
      if (prefill_step()) worked = true;
      if (worked) continue;
      std::unique_lock lock(mutex_);
      condition_.wait(lock, [&] { return stopping_ || !pending_.empty(); });
      if (stopping_ && pending_.empty() && !has_active()) return;
    }
  }

  gradiated::engine::Gemma4BatchModelRunner runner_;
  std::vector<Slot> slots_;
  RuntimeMetrics& metrics_;
  int prefill_quantum_tokens_;
  int idle_prefill_quantum_tokens_;
  std::mutex mutex_;
  std::condition_variable condition_;
  std::deque<std::shared_ptr<CompletionJob>> pending_;
  bool stopping_{false};
  std::uint64_t age_{0};
  std::uint64_t admission_order_{0};
  std::thread worker_;
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

    const std::string configured_key = environment(
        "GRADIATED_RUNTIME_API_KEY", environment("DESMOND_RUNTIME_API_KEY"));
    const std::string expected_authorization = configured_key.empty() ? std::string{} : "Bearer " + configured_key;
    const std::string bind_host = environment("GRADIATED_RUNTIME_HOST", "0.0.0.0");
    const std::uint16_t bind_port = environment_port("GRADIATED_RUNTIME_PORT", 30000);
    const int prefill_quantum_tokens = environment_integer(
        "GRADIATED_PREFILL_QUANTUM_TOKENS", default_scheduler_prefill_quantum_tokens,
        1, maximum_context);
    const int idle_prefill_quantum_tokens = environment_integer(
        "GRADIATED_IDLE_PREFILL_QUANTUM_TOKENS", default_idle_prefill_quantum_tokens,
        1, maximum_context);
    RuntimeMetrics metrics;
    ContinuousScheduler scheduler(config, *weights, metrics, prefill_quantum_tokens,
                                  idle_prefill_quantum_tokens);

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
             << "gradiated_native_queued_requests " << metrics.queued.load() << '\n'
             << "gradiated_native_active_requests " << metrics.active.load() << '\n'
             << "gradiated_native_decoding_requests " << metrics.decoding.load() << '\n'
             << "gradiated_native_prefix_cache_hits_total " << metrics.prefix_cache_hits.load() << '\n'
             << "gradiated_native_prefix_tokens_reused_total "
             << metrics.prefix_tokens_reused.load() << '\n'
             << "gradiated_native_prefill_tokens_computed_total "
             << metrics.prefill_tokens_computed.load() << '\n'
             << "gradiated_native_kv_cache_clones_total " << metrics.kv_cache_clones.load() << '\n'
             << "gradiated_native_kv_cache_clone_bytes_total "
             << metrics.kv_cache_clone_bytes.load() << '\n';
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

        auto result = scheduler.complete(input_ids, max_tokens, std::move(stop_ids));
        std::ostringstream response;
        response << "{\"output_ids\":" << token_array_json(result.output_ids)
                 << ",\"usage\":{\"input_tokens\":" << input_ids.size()
                 << ",\"output_tokens\":" << result.output_ids.size() << "}"
                 << ",\"timing\":{\"queue_ms\":"
                 << static_cast<double>(result.queue_microseconds) / 1000.0
                 << ",\"ttft_ms\":" << static_cast<double>(result.ttft_microseconds) / 1000.0
                 << ",\"mean_tpot_ms\":"
                 << (result.output_ids.size() > 1
                         ? static_cast<double>(result.decode_microseconds) /
                               (1000.0 * static_cast<double>(result.output_ids.size() - 1))
                         : 0.0)
                 << ",\"max_tpot_ms\":"
                 << static_cast<double>(result.maximum_tpot_microseconds) / 1000.0
                 << ",\"total_ms\":" << static_cast<double>(result.total_microseconds) / 1000.0
                 << "},\"finish_reason\":" << desmond::json_string(result.finish_reason)
                 << "}\n";
        return desmond::HttpResponse{200, "application/json", response.str()};
      } catch (const InferenceFailure& error) {
        return desmond::HttpResponse{503, "application/json",
                                     "{\"error\":\"inference_failure\",\"message\":" +
                                         desmond::json_string(error.what()) + "}\n"};
      } catch (const std::exception& error) {
        metrics.failures.fetch_add(1);
        return desmond::HttpResponse{400, "application/json",
                                     "{\"error\":\"invalid_request\",\"message\":" +
                                         desmond::json_string(error.what()) + "}\n"};
      }
    });
    std::cout << "gradiated native runtime ready on " << bind_host << ':' << bind_port
              << " active_prefill_quantum_tokens=" << prefill_quantum_tokens
              << " idle_prefill_quantum_tokens=" << idle_prefill_quantum_tokens << '\n';
    server.run();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "native runtime failed: " << error.what() << '\n';
    return 70;
  }
}
