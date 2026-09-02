#include "desmond/http.h"
#include "desmond/profiling.h"
#include "desmond/trace.h"
#include "gradiated/engine/device_weights.h"
#include "gradiated/engine/gemma4_config.h"
#include "gradiated/engine/json.h"
#include "gradiated/engine/batch_model_runner.h"
#include "gradiated/engine/safetensors.h"
#include "gradiated/engine/weight_plan.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdlib>
#include <deque>
#include <iostream>
#include <iterator>
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
constexpr int default_scheduler_prefill_quantum_tokens = 1024;
constexpr int default_idle_prefill_quantum_tokens = 1024;
// OpenRouter-style bursts arrive over several milliseconds at the node even when the
// upstream scheduler dispatches them together.  Ten milliseconds consistently formed
// complete cohorts in the production c10 trace, while remaining below the measured
// competing-provider TTFT margin.
constexpr int default_short_prefill_batch_window_microseconds = 10000;
constexpr int short_prefill_cohort_tokens = 512;
// Zero preserves the throughput-first full suffix batch. A positive value preempts only at exact
// transformer-layer boundaries, retaining one execution of every prefill layer.
constexpr int default_interleaved_suffix_layer_quantum = 10;
constexpr int default_interleaved_suffix_layer_minimum_decode = 14;
constexpr int maximum_slots = 24;
constexpr int default_speculative_depth = 4;
constexpr int default_speculative_minimum_batch = 8;
constexpr int default_cache_affinity_max_bypasses = 4;
constexpr int default_idle_cache_reserve_slots = 0;

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

bool environment_flag(const char* name, bool fallback = false) {
  const std::string value = environment(name);
  if (value.empty()) return fallback;
  if (value == "1" || value == "true") return true;
  if (value == "0" || value == "false") return false;
  throw std::runtime_error(std::string(name) + " must be 0, 1, false, or true");
}

float environment_float(const char* name, float fallback, float minimum, float maximum) {
  const std::string value = environment(name);
  if (value.empty()) return fallback;
  std::size_t consumed = 0;
  const float parsed = std::stof(value, &consumed);
  if (consumed != value.size() || !std::isfinite(parsed) ||
      parsed < minimum || parsed > maximum) {
    throw std::runtime_error(std::string(name) + " is out of range");
  }
  return parsed;
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

void update_atomic_max(std::atomic<std::uint64_t>& target, std::uint64_t value) {
  std::uint64_t current = target.load(std::memory_order_relaxed);
  while (current < value &&
         !target.compare_exchange_weak(current, value, std::memory_order_relaxed)) {}
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

bool optional_bool(const gradiated::engine::Json& object, const char* field, bool fallback) {
  const auto* value = object.find(field);
  return value == nullptr ? fallback : value->as_bool();
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
  std::atomic<std::uint64_t> cancelled{0};
  std::atomic<std::uint64_t> input_tokens{0};
  std::atomic<std::uint64_t> output_tokens{0};
  std::atomic<std::uint64_t> inference_microseconds{0};
  std::atomic<std::uint64_t> queued{0};
  std::atomic<std::uint64_t> active{0};
  std::atomic<std::uint64_t> decoding{0};
  std::atomic<std::uint64_t> prefix_cache_hits{0};
  std::atomic<std::uint64_t> prefix_tokens_reused{0};
  std::atomic<std::uint64_t> cache_affinity_admissions{0};
  std::atomic<std::uint64_t> cache_affinity_bypassed_requests{0};
  std::atomic<std::uint64_t> prefill_tokens_computed{0};
  std::atomic<std::uint64_t> kv_cache_clones{0};
  std::atomic<std::uint64_t> kv_cache_clone_bytes{0};
  std::atomic<std::uint64_t> suffix_prefill_batches{0};
  std::atomic<std::uint64_t> interleaved_suffix_prefill_batches{0};
  std::atomic<std::uint64_t> suffix_prefill_requests{0};
  std::atomic<std::uint64_t> suffix_prefill_tokens{0};
  std::atomic<std::uint64_t> suffix_prefill_microseconds{0};
  std::atomic<std::uint64_t> maximum_suffix_prefill_microseconds{0};
  std::atomic<std::uint64_t> suffix_prefill_layer_slices{0};
  std::array<std::atomic<std::uint64_t>, maximum_slots + 1> suffix_prefill_batch_calls{};
  std::atomic<std::uint64_t> speculative_cycles{0};
  std::atomic<std::uint64_t> speculative_proposed_tokens{0};
  std::atomic<std::uint64_t> speculative_accepted_tokens{0};
  std::atomic<std::uint64_t> speculative_first_token_rejections{0};
  std::atomic<std::uint64_t> speculative_draft_microseconds{0};
  std::atomic<std::uint64_t> speculative_verify_microseconds{0};
  std::array<std::atomic<std::uint64_t>, maximum_slots + 1> decode_batch_steps{};
  std::atomic<std::uint64_t> contiguous_decode_steps{0};
  std::atomic<std::uint64_t> fragmented_decode_steps{0};
};

struct CompletionResult {
  std::vector<int> output_ids;
  std::uint64_t cached_input_tokens{0};
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
  std::uint64_t request_id{0};
  std::vector<int> input_ids;
  int max_tokens{0};
  int priority{0};
  std::unordered_set<int> stop_ids;
  std::chrono::steady_clock::time_point queued_at;
  std::mutex mutex;
  std::condition_variable condition;
  std::deque<int> emitted_ids;
  std::atomic<bool> cancelled{false};
  std::atomic<std::uint64_t> cached_input_tokens{0};
  std::uint32_t admission_bypasses{0};
  bool done{false};
  std::optional<CompletionResult> result;
  std::string error;
};

class ContinuousScheduler {
 public:
  ContinuousScheduler(const gradiated::engine::Gemma4Config& config,
                      const gradiated::engine::DeviceWeightArena& weights,
                      const gradiated::engine::Fp8WeightArena* fp8_weights,
                      const gradiated::engine::DeviceWeightArena* assistant_weights,
                      const gradiated::engine::Fp8WeightArena* assistant_fp8_weights,
                      RuntimeMetrics& metrics, int speculative_depth,
                      int speculative_minimum_batch,
                      int prefill_quantum_tokens,
                      int idle_prefill_quantum_tokens,
                      int short_prefill_batch_window_microseconds,
                      int interleaved_suffix_layer_quantum,
                      int interleaved_suffix_layer_minimum_decode,
                      int cache_affinity_max_bypasses,
                      int idle_cache_reserve_slots,
                      desmond::SharedTraceRing* trace_ring)
      : runner_(config, weights, maximum_slots, maximum_context, fp8_weights,
                assistant_weights, assistant_fp8_weights),
        slots_(maximum_slots), metrics_(metrics),
        speculative_depth_(speculative_depth),
        speculative_minimum_batch_(speculative_minimum_batch),
        prefill_quantum_tokens_(prefill_quantum_tokens),
        idle_prefill_quantum_tokens_(idle_prefill_quantum_tokens),
        short_prefill_batch_window_microseconds_(short_prefill_batch_window_microseconds),
        interleaved_suffix_layer_quantum_(interleaved_suffix_layer_quantum),
        interleaved_suffix_layer_minimum_decode_(interleaved_suffix_layer_minimum_decode),
        cache_affinity_max_bypasses_(cache_affinity_max_bypasses),
        idle_cache_reserve_slots_(idle_cache_reserve_slots),
        config_layer_count_(config.layers.size()), trace_ring_(trace_ring) {
    // Materialize latency-sensitive cuBLASLt and attention plans before advertising readiness.
    std::vector<int> warmup(2048, 2);
    while (!runner_.prefill_slot_chunk(0, warmup, default_chunk_tokens)) {}
    runner_.reset_slot(0);
    // cuDNN SDPA plans are exact-shape keyed. Build the long-context active quantum and the
    // one-token tail before readiness so a conversation's first cache extension cannot stall
    // every decoder behind graph construction.
    std::vector<int> active_prefill_warmup(
        static_cast<std::size_t>(default_chunk_tokens + prefill_quantum_tokens_ + 1), 2);
    static_cast<void>(runner_.prefill_slot_chunk(
        0, active_prefill_warmup, default_chunk_tokens));
    static_cast<void>(runner_.prefill_slot_chunk(
        0, active_prefill_warmup, prefill_quantum_tokens_));
    static_cast<void>(runner_.prefill_slot_chunk(
        0, active_prefill_warmup, prefill_quantum_tokens_));
    runner_.seed_empty_cache_for_benchmark(1);
    for (int active = 1; active <= maximum_slots; ++active) {
      std::vector<int> tokens(static_cast<std::size_t>(active), 2);
      std::vector<int> slots(static_cast<std::size_t>(active));
      for (int index = 0; index < active; ++index) {
        slots[static_cast<std::size_t>(index)] = index;
      }
      static_cast<void>(runner_.append_ragged(tokens, slots));
    }
    for (int slot = 0; slot < maximum_slots; ++slot) runner_.reset_slot(slot);
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
                            std::unordered_set<int> stop_ids, int priority) {
    auto job = submit(std::move(input_ids), max_tokens, std::move(stop_ids), priority);
    std::unique_lock lock(job->mutex);
    job->condition.wait(lock, [&] { return job->done; });
    if (!job->error.empty()) throw InferenceFailure(job->error);
    return std::move(*job->result);
  }

  std::shared_ptr<CompletionJob> submit(std::vector<int> input_ids, int max_tokens,
                                        std::unordered_set<int> stop_ids, int priority) {
    auto job = std::make_shared<CompletionJob>();
    job->request_id = next_request_id_.fetch_add(1, std::memory_order_relaxed);
    job->input_ids = std::move(input_ids);
    job->max_tokens = max_tokens;
    job->priority = priority;
    job->stop_ids = std::move(stop_ids);
    job->queued_at = std::chrono::steady_clock::now();
    {
      std::lock_guard lock(mutex_);
      if (stopping_) throw std::runtime_error("runtime scheduler is stopping");
      pending_.push_back(job);
      metrics_.queued.fetch_add(1);
    }
    condition_.notify_one();
    return job;
  }

  void cancel(const std::shared_ptr<CompletionJob>& job) {
    job->cancelled.store(true, std::memory_order_release);
    condition_.notify_one();
  }

 private:
  void trace(const desmond::TraceEventType type, const std::uint64_t request_id = 0,
             const std::uint64_t batch_id = 0, const std::uint64_t duration_us = 0,
             const std::uint64_t graph_node_id = 0, const std::uint64_t value0 = 0,
             const std::uint64_t value1 = 0, const std::uint32_t stream_id = 0) noexcept {
    if (trace_ring_ == nullptr) return;
    const auto monotonic_ns = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count());
    static_cast<void>(trace_ring_->try_push({
        .monotonic_ns = monotonic_ns,
        .request_id_low = request_id,
        .batch_id = batch_id,
        .graph_execution_id = duration_us,
        .graph_node_id = graph_node_id,
        .value0 = value0,
        .value1 = value1,
        .stream_id = stream_id,
        .type = type,
    }));
  }

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
    bool speculative_cohort{false};
    std::chrono::steady_clock::time_point last_token_at;
  };

  struct Placement {
    int destination{-1};
    int source{-1};
    std::size_t prefix_tokens{0};
    bool cache_reservation_blocked{false};
  };

  static void emit_token(Slot& slot, int token) {
    slot.output_ids.push_back(token);
    {
      std::lock_guard lock(slot.job->mutex);
      slot.job->emitted_ids.push_back(token);
    }
    slot.job->condition.notify_all();
  }

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
    int active_slots = 0;
    int idle_cached_slots = 0;
    for (int index = 0; index < maximum_slots; ++index) {
      const auto& slot = slots_[static_cast<std::size_t>(index)];
      if (slot.job) {
        ++active_slots;
      } else if (!slot.cached_tokens.empty()) {
        ++idle_cached_slots;
      }
      if (!slot.job && slot.age < oldest) {
        oldest = slot.age;
        placement.destination = index;
      }
    }
    const std::size_t victim_prefix = placement.destination >= 0
        ? slots_[static_cast<std::size_t>(placement.destination)].cached_tokens.size() : 0;
    if (placement.destination >= 0 && active_slots > 0 &&
        idle_cached_slots <= idle_cache_reserve_slots_ &&
        placement.prefix_tokens < victim_prefix) {
      placement.destination = -1;
      placement.cache_reservation_blocked = true;
    }
    return placement;
  }

  void complete_slot(int index, const char* finish_reason) {
    auto& slot = slots_[static_cast<std::size_t>(index)];
    const auto now = std::chrono::steady_clock::now();
    CompletionResult result;
    result.output_ids = std::move(slot.output_ids);
    result.cached_input_tokens = slot.job->cached_input_tokens.load(std::memory_order_acquire);
    result.queue_microseconds = slot.queue_microseconds;
    result.ttft_microseconds = slot.ttft_microseconds;
    result.decode_microseconds = slot.decode_microseconds;
    result.maximum_tpot_microseconds = slot.maximum_tpot_microseconds;
    result.total_microseconds = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::microseconds>(now - slot.job->queued_at).count());
    result.finish_reason = finish_reason;
    trace(desmond::TraceEventType::request_finished, slot.job->request_id, 0,
          result.total_microseconds, 0, result.output_ids.size(), result.ttft_microseconds,
          static_cast<std::uint32_t>(index));
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
    trace(desmond::TraceEventType::request_failed,
          slot.job ? slot.job->request_id : 0, 0, 0, 0, 0, 0,
          static_cast<std::uint32_t>(index));
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

  void cancel_slot(int index) {
    auto& slot = slots_[static_cast<std::size_t>(index)];
    trace(desmond::TraceEventType::request_cancelled,
          slot.job ? slot.job->request_id : 0, 0, 0, 0, 0, 0,
          static_cast<std::uint32_t>(index));
    auto job = std::move(slot.job);
    slot.cached_tokens.clear();
    slot.output_ids.clear();
    runner_.reset_slot(index);
    metrics_.cancelled.fetch_add(1);
    metrics_.active.fetch_sub(1);
    if (slot.decode_ready) metrics_.decoding.fetch_sub(1);
    slot.decode_ready = false;
    {
      std::lock_guard lock(job->mutex);
      job->error = "request cancelled";
      job->done = true;
    }
    job->condition.notify_all();
  }

  bool reap_cancelled() {
    bool reaped = false;
    {
      std::lock_guard lock(mutex_);
      for (auto current = pending_.begin(); current != pending_.end();) {
        if (!(*current)->cancelled.load(std::memory_order_acquire)) {
          ++current;
          continue;
        }
        auto job = std::move(*current);
        current = pending_.erase(current);
        metrics_.queued.fetch_sub(1);
        metrics_.cancelled.fetch_add(1);
        trace(desmond::TraceEventType::request_cancelled, job->request_id,
              0, 0, 0, 0, 0, std::numeric_limits<std::uint32_t>::max());
        {
          std::lock_guard job_lock(job->mutex);
          job->error = "request cancelled";
          job->done = true;
        }
        job->condition.notify_all();
        reaped = true;
      }
    }
    if (!inflight_suffix_slots_.empty()) {
      const bool cohort_cancelled = std::any_of(
          inflight_suffix_slots_.begin(), inflight_suffix_slots_.end(), [&](const int index) {
            const auto& slot = slots_[static_cast<std::size_t>(index)];
            return !slot.job || slot.job->cancelled.load(std::memory_order_acquire);
          });
      if (cohort_cancelled) {
        runner_.abort_suffix_layer_slices();
        inflight_suffix_slots_.clear();
        inflight_suffix_prompts_.clear();
      }
    }
    for (int index = 0; index < maximum_slots; ++index) {
      const auto& slot = slots_[static_cast<std::size_t>(index)];
      if (slot.job && slot.job->cancelled.load(std::memory_order_acquire)) {
        cancel_slot(index);
        reaped = true;
      }
    }
    return reaped;
  }

  bool admit_one() {
    std::shared_ptr<CompletionJob> job;
    Placement placement;
    {
      std::lock_guard lock(mutex_);
      if (pending_.empty()) return false;
      const auto priority_selected = std::min_element(
          pending_.begin(), pending_.end(),
          [](const auto& left, const auto& right) {
            return left->priority < right->priority;
          });
      if (priority_selected != pending_.begin()) {
        std::rotate(pending_.begin(), priority_selected, std::next(priority_selected));
      }
      auto selected = pending_.begin();
      placement = select_slot(**selected);
      const bool may_bypass = placement.cache_reservation_blocked ||
          (cache_affinity_max_bypasses_ > 0 &&
           (*selected)->admission_bypasses <
               static_cast<std::uint32_t>(cache_affinity_max_bypasses_));
      if (may_bypass) {
        for (auto candidate = std::next(selected); candidate != pending_.end(); ++candidate) {
          if ((*candidate)->priority != (*selected)->priority) continue;
          const Placement candidate_placement = select_slot(**candidate);
          if (candidate_placement.destination >= 0 &&
              (placement.destination < 0 ||
               candidate_placement.prefix_tokens > placement.prefix_tokens)) {
            selected = candidate;
            placement = candidate_placement;
          }
        }
      }
      if (placement.destination < 0) return false;
      if (selected != pending_.begin()) {
        metrics_.cache_affinity_admissions.fetch_add(1);
        for (auto bypassed = pending_.begin(); bypassed != selected; ++bypassed) {
          if ((*bypassed)->admission_bypasses <
              static_cast<std::uint32_t>(cache_affinity_max_bypasses_)) {
            ++(*bypassed)->admission_bypasses;
          }
          metrics_.cache_affinity_bypassed_requests.fetch_add(1);
        }
      }
      job = std::move(*selected);
      pending_.erase(selected);
      metrics_.queued.fetch_sub(1);
      slots_[static_cast<std::size_t>(placement.destination)].job = job;
      job->cached_input_tokens.store(static_cast<std::uint64_t>(placement.prefix_tokens),
                                     std::memory_order_release);
    }
    const int index = placement.destination;
    auto& slot = slots_[static_cast<std::size_t>(index)];
    slot.output_ids.clear();
    slot.decode_ready = false;
    slot.speculative_cohort = false;
    slot.inference_begin = std::chrono::steady_clock::now();
    slot.queue_microseconds = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::microseconds>(slot.inference_begin - job->queued_at)
            .count());
    slot.ttft_microseconds = 0;
    slot.decode_microseconds = 0;
    slot.maximum_tpot_microseconds = 0;
    slot.admission_order = ++admission_order_;
    metrics_.active.fetch_add(1);
    trace(desmond::TraceEventType::request_admitted, job->request_id, 0,
          slot.queue_microseconds, 0, job->input_ids.size(), placement.prefix_tokens,
          static_cast<std::uint32_t>(index));
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
        emit_token(slot, cached_prediction);
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

  bool prefill_step(bool force_idle_quantum = false) {
    const bool decode_is_active = std::any_of(
        slots_.begin(), slots_.end(), [](const Slot& candidate) { return candidate.decode_ready; });
    if (!force_idle_quantum && !decode_is_active) {
      std::vector<int> candidates;
      for (int index = 0; index < maximum_slots; ++index) {
        const auto& slot = slots_[static_cast<std::size_t>(index)];
        if (slot.job && !slot.decode_ready) candidates.push_back(index);
      }
      const int maximum_requests = std::max(1, maximum_context / idle_prefill_quantum_tokens_);
      if (candidates.size() >= 2) {
        std::stable_sort(candidates.begin(), candidates.end(), [&](const int left, const int right) {
          const int left_position = runner_.slot_position(left);
          const int right_position = runner_.slot_position(right);
          if (left_position != right_position) return left_position < right_position;
          return slots_[static_cast<std::size_t>(left)].admission_order <
                 slots_[static_cast<std::size_t>(right)].admission_order;
        });
        if (candidates.size() > static_cast<std::size_t>(maximum_requests)) {
          candidates.resize(static_cast<std::size_t>(maximum_requests));
        }
        std::vector<const std::vector<int>*> prompts;
        std::vector<int> before;
        prompts.reserve(candidates.size());
        before.reserve(candidates.size());
        for (const int index : candidates) {
          prompts.push_back(&slots_[static_cast<std::size_t>(index)].job->input_ids);
          before.push_back(runner_.slot_position(index));
        }
        try {
          const auto prefill_begin = std::chrono::steady_clock::now();
          const auto predictions = runner_.prefill_slots_chunks(
              candidates, prompts, idle_prefill_quantum_tokens_);
          const auto end = std::chrono::steady_clock::now();
          const auto prefill_microseconds = static_cast<std::uint64_t>(
              std::chrono::duration_cast<std::chrono::microseconds>(end - prefill_begin).count());
          std::uint64_t computed_tokens = 0;
          const std::uint64_t prefill_batch_id = ++batch_id_;
          for (std::size_t row = 0; row < candidates.size(); ++row) {
            const int index = candidates[row];
            auto& slot = slots_[static_cast<std::size_t>(index)];
            const int resident = runner_.slot_position(index);
            const int advanced = resident - before[row];
            computed_tokens += static_cast<std::uint64_t>(advanced);
            metrics_.prefill_tokens_computed.fetch_add(static_cast<std::uint64_t>(advanced));
            slot.cached_tokens.assign(slot.job->input_ids.begin(),
                                      slot.job->input_ids.begin() + resident);
            trace(desmond::TraceEventType::batch_formed, slot.job->request_id,
                  prefill_batch_id, 0, static_cast<std::uint64_t>(resident), row,
                  static_cast<std::uint64_t>(advanced), static_cast<std::uint32_t>(index));
            if (!predictions[row]) continue;
            slot.token_to_append = *predictions[row];
            emit_token(slot, *predictions[row]);
            slot.decode_ready = true;
            slot.ttft_microseconds = static_cast<std::uint64_t>(
                std::chrono::duration_cast<std::chrono::microseconds>(
                    end - slot.job->queued_at).count());
            slot.last_token_at = end;
            metrics_.decoding.fetch_add(1);
            if (slot.job->stop_ids.contains(*predictions[row])) {
              complete_slot(index, "stop");
            } else if (slot.job->max_tokens == 1) {
              complete_slot(index, "length");
            }
          }
          trace(desmond::TraceEventType::prefill_batch, 0, prefill_batch_id,
                prefill_microseconds, config_layer_count_, candidates.size(), computed_tokens, 0);
        } catch (const std::exception& error) {
          for (const int index : candidates) {
            if (slots_[static_cast<std::size_t>(index)].job) fail_slot(index, error.what());
          }
        }
        return true;
      }
    }
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
      const int quantum = force_idle_quantum || !decode_is_active
          ? idle_prefill_quantum_tokens_
          : prefill_quantum_tokens_;
      const auto prefill_begin = std::chrono::steady_clock::now();
      const auto prediction = runner_.prefill_slot_chunk(
          selected, slot.job->input_ids, quantum);
      const auto end = std::chrono::steady_clock::now();
      const int resident = runner_.slot_position(selected);
      const auto prefill_microseconds = static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::microseconds>(end - prefill_begin).count());
      trace(desmond::TraceEventType::prefill_batch, slot.job->request_id, ++batch_id_,
            prefill_microseconds, static_cast<std::uint64_t>(resident), 1,
            static_cast<std::uint64_t>(resident - before),
            static_cast<std::uint32_t>(selected));
      metrics_.prefill_tokens_computed.fetch_add(static_cast<std::uint64_t>(resident - before));
      slot.cached_tokens.assign(slot.job->input_ids.begin(),
                                slot.job->input_ids.begin() + resident);
      if (!prediction) return true;

      slot.token_to_append = *prediction;
      emit_token(slot, *prediction);
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
    metrics_.decode_batch_steps.at(indices.size()).fetch_add(1);
    bool contiguous = true;
    for (std::size_t row = 1; row < slots.size(); ++row) {
      contiguous &= slots[row] == slots.front() + static_cast<int>(row);
    }
    if (contiguous) {
      metrics_.contiguous_decode_steps.fetch_add(1);
    } else {
      metrics_.fragmented_decode_steps.fetch_add(1);
    }
    int maximum_decode_context = 0;
    for (const int slot : slots) {
      maximum_decode_context = std::max(maximum_decode_context, runner_.slot_position(slot));
    }
    const std::uint64_t decode_batch_id = ++batch_id_;
    const auto decode_begin = std::chrono::steady_clock::now();
    for (std::size_t row = 0; row < indices.size(); ++row) {
      const auto& slot = slots_[static_cast<std::size_t>(indices[row])];
      trace(desmond::TraceEventType::batch_formed, slot.job->request_id, decode_batch_id,
            0, static_cast<std::uint64_t>(runner_.slot_position(slots[row])), row,
            static_cast<std::uint64_t>(maximum_decode_context),
            static_cast<std::uint32_t>(slots[row]));
    }
    const bool continuing_speculative_cohort = std::any_of(
        indices.begin(), indices.end(), [&](int index) {
          return slots_[static_cast<std::size_t>(index)].speculative_cohort;
        });
    if (runner_.has_assistant() &&
        (indices.size() >= static_cast<std::size_t>(speculative_minimum_batch_) ||
         continuing_speculative_cohort)) {
      try {
        // Starting speculation is batch-size gated, but once a cohort has paid that decision,
        // keep accelerating its shrinking tail. Falling back as soon as one request finishes
        // turned synchronized 16-way traffic into 14--20 slow single-token decode steps.
        for (const int index : indices) {
          slots_[static_cast<std::size_t>(index)].speculative_cohort = true;
        }
        // Keep ragged contexts monotonic so the target verifier can split the cohort into
        // narrower global-attention GEMMs instead of padding every request to the longest one.
        std::vector<std::size_t> order(indices.size());
        for (std::size_t row = 0; row < order.size(); ++row) order[row] = row;
        std::stable_sort(order.begin(), order.end(), [&](std::size_t left, std::size_t right) {
          return runner_.slot_position(slots[left]) < runner_.slot_position(slots[right]);
        });
        std::vector<int> sorted_indices;
        std::vector<int> sorted_slots;
        sorted_indices.reserve(indices.size());
        sorted_slots.reserve(slots.size());
        for (const std::size_t row : order) {
          sorted_indices.push_back(indices[row]);
          sorted_slots.push_back(slots[row]);
        }
        indices = std::move(sorted_indices);
        slots = std::move(sorted_slots);
        std::vector<int> last_tokens;
        std::vector<int> target_first;
        std::vector<int> acceptance_caps;
        last_tokens.reserve(indices.size());
        target_first.reserve(indices.size());
        acceptance_caps.reserve(indices.size());
        for (const int index : indices) {
          const auto& slot = slots_[static_cast<std::size_t>(index)];
          if (slot.cached_tokens.empty()) {
            throw std::runtime_error("assistant request has no resident token");
          }
          last_tokens.push_back(slot.cached_tokens.back());
          target_first.push_back(slot.token_to_append);
        }
        const auto draft_begin = std::chrono::steady_clock::now();
        const auto proposals = runner_.draft_four(
            last_tokens, slots, target_first, speculative_depth_);
        const auto draft_end = std::chrono::steady_clock::now();
        for (std::size_t row = 0; row < indices.size(); ++row) {
          const auto& slot = slots_[static_cast<std::size_t>(indices[row])];
          int cap = std::min<int>(speculative_depth_, slot.job->max_tokens -
              static_cast<int>(slot.output_ids.size()));
          for (int candidate = 1; candidate < cap; ++candidate) {
            if (slot.job->stop_ids.contains(
                    proposals[row][static_cast<std::size_t>(candidate)])) {
              cap = candidate + 1;
              break;
            }
          }
          acceptance_caps.push_back(cap);
        }
        const auto verification = runner_.verify_greedy_proposals(
            proposals, target_first, slots, acceptance_caps);
        const auto verify_end = std::chrono::steady_clock::now();
        metrics_.speculative_draft_microseconds.fetch_add(
            static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(
                draft_end - draft_begin).count()));
        metrics_.speculative_verify_microseconds.fetch_add(
            static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(
                verify_end - draft_end).count()));
        metrics_.speculative_cycles.fetch_add(1);
        metrics_.speculative_proposed_tokens.fetch_add(
            static_cast<std::uint64_t>(speculative_depth_) * indices.size());
        for (const int accepted : verification.accepted_tokens) {
          metrics_.speculative_accepted_tokens.fetch_add(
              static_cast<std::uint64_t>(accepted));
          if (accepted == 0) metrics_.speculative_first_token_rejections.fetch_add(1);
        }

        std::vector<int> fallback_rows;
        std::vector<int> fallback_slots;
        std::vector<int> fallback_tokens;
        for (std::size_t row = 0; row < indices.size(); ++row) {
          if (verification.accepted_tokens[row] != 0) continue;
          fallback_rows.push_back(static_cast<int>(row));
          fallback_slots.push_back(slots[row]);
          fallback_tokens.push_back(target_first[row]);
        }
        std::vector<int> fallback_next;
        if (!fallback_rows.empty()) {
          fallback_next = runner_.append_ragged(fallback_tokens, fallback_slots);
        }

        const auto token_time = std::chrono::steady_clock::now();
        trace(desmond::TraceEventType::speculative_batch, 0, decode_batch_id,
              static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(
                  token_time - decode_begin).count()),
              static_cast<std::uint64_t>(speculative_depth_), indices.size(),
              static_cast<std::uint64_t>(maximum_decode_context), contiguous ? 1U : 2U);
        std::size_t fallback_index = 0;
        for (std::size_t row = 0; row < indices.size(); ++row) {
          const int index = indices[row];
          auto& slot = slots_[static_cast<std::size_t>(index)];
          const int accepted = verification.accepted_tokens[row];
          int newly_emitted = 0;
          bool stopped = false;
          if (accepted == 0) {
            slot.cached_tokens.push_back(slot.token_to_append);
            slot.token_to_append = fallback_next.at(fallback_index++);
            emit_token(slot, slot.token_to_append);
            newly_emitted = 1;
          } else {
            for (int candidate = 0; candidate < accepted; ++candidate) {
              slot.cached_tokens.push_back(
                  proposals[row][static_cast<std::size_t>(candidate)]);
              if (candidate == 0) continue;  // Already emitted before this cycle.
              const int token = proposals[row][static_cast<std::size_t>(candidate)];
              emit_token(slot, token);
              ++newly_emitted;
              if (slot.job->stop_ids.contains(token)) {
                stopped = true;
                break;
              }
            }
            if (!stopped) {
              slot.token_to_append = verification.next_tokens[row];
              emit_token(slot, slot.token_to_append);
              ++newly_emitted;
            }
          }
          const auto cycle = static_cast<std::uint64_t>(
              std::chrono::duration_cast<std::chrono::microseconds>(token_time - slot.last_token_at)
                  .count());
          const auto tpot = cycle / static_cast<std::uint64_t>(std::max(1, newly_emitted));
          slot.decode_microseconds += cycle;
          slot.maximum_tpot_microseconds = std::max(slot.maximum_tpot_microseconds, tpot);
          slot.last_token_at = token_time;
          if (stopped || slot.job->stop_ids.contains(slot.token_to_append)) {
            complete_slot(index, "stop");
          } else if (slot.output_ids.size() >= static_cast<std::size_t>(slot.job->max_tokens)) {
            complete_slot(index, "length");
          }
        }
      } catch (const std::exception& error) {
        for (const int index : indices) {
          if (slots_[static_cast<std::size_t>(index)].job) fail_slot(index, error.what());
        }
      }
      return true;
    }
    try {
      const auto predictions = runner_.append_ragged(tokens, slots);
      const auto token_time = std::chrono::steady_clock::now();
      trace(desmond::TraceEventType::decode_batch, 0, decode_batch_id,
            static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(
                token_time - decode_begin).count()),
            0, indices.size(), static_cast<std::uint64_t>(maximum_decode_context),
            contiguous ? 1U : 2U);
      for (std::size_t row = 0; row < indices.size(); ++row) {
        const int index = indices[row];
        auto& slot = slots_[static_cast<std::size_t>(index)];
        slot.cached_tokens.push_back(slot.token_to_append);
        slot.token_to_append = predictions[row];
        emit_token(slot, slot.token_to_append);
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

  bool drain_short_prefill_cohort() {
    const bool resuming_layer_slices = !inflight_suffix_slots_.empty();
    const int decoding = static_cast<int>(std::count_if(
        slots_.begin(), slots_.end(), [](const Slot& slot) { return slot.decode_ready; }));
    const bool has_decoding = decoding > 0;
    const bool decode_pressure = decoding >= interleaved_suffix_layer_minimum_decode_;
    std::vector<int> cohort_slots = inflight_suffix_slots_;
    std::vector<const std::vector<int>*> cohort_prompts = inflight_suffix_prompts_;
    std::vector<int> cohort_tokens;
    if (!resuming_layer_slices) {
      for (int index = 0; index < maximum_slots; ++index) {
        const auto& slot = slots_[static_cast<std::size_t>(index)];
        if (!slot.job || slot.decode_ready) continue;
        const int remaining = static_cast<int>(slot.job->input_ids.size()) -
                              runner_.slot_position(index);
        if (remaining <= 0 || remaining > short_prefill_cohort_tokens) continue;
        cohort_slots.push_back(index);
        cohort_prompts.push_back(&slot.job->input_ids);
        cohort_tokens.push_back(remaining);
      }
      if (cohort_slots.size() < 2) return false;
      std::vector<std::size_t> order(cohort_slots.size());
      for (std::size_t index = 0; index < order.size(); ++index) order[index] = index;
      std::stable_sort(order.begin(), order.end(), [&](std::size_t left, std::size_t right) {
        return runner_.slot_position(cohort_slots[left]) <
               runner_.slot_position(cohort_slots[right]);
      });
      std::vector<int> sorted_slots;
      std::vector<const std::vector<int>*> sorted_prompts;
      std::vector<int> sorted_tokens;
      sorted_slots.reserve(order.size());
      sorted_prompts.reserve(order.size());
      sorted_tokens.reserve(order.size());
      for (const std::size_t index : order) {
        sorted_slots.push_back(cohort_slots[index]);
        sorted_prompts.push_back(cohort_prompts[index]);
        sorted_tokens.push_back(cohort_tokens[index]);
      }
      cohort_slots = std::move(sorted_slots);
      cohort_prompts = std::move(sorted_prompts);
      cohort_tokens = std::move(sorted_tokens);
    }
    try {
      const auto prefill_begin = std::chrono::steady_clock::now();
      std::vector<std::optional<int>> predictions(cohort_slots.size());
      const bool use_layer_slices = resuming_layer_slices ||
          (decode_pressure && interleaved_suffix_layer_quantum_ > 0);
      bool complete = true;
      if (use_layer_slices) {
        if (!resuming_layer_slices) {
          inflight_suffix_slots_ = cohort_slots;
          inflight_suffix_prompts_ = cohort_prompts;
        }
        const int layers = decode_pressure
            ? interleaved_suffix_layer_quantum_
            : static_cast<int>(config_layer_count_);
        const auto result = runner_.prefill_slots_suffix_layer_slice(
            cohort_slots, cohort_prompts, layers);
        metrics_.suffix_prefill_layer_slices.fetch_add(1);
        complete = result.complete;
        if (complete) {
          for (std::size_t request = 0; request < result.predictions.size(); ++request) {
            predictions[request] = result.predictions[request];
          }
        }
      } else {
        const auto full_predictions = runner_.prefill_slots_suffix(cohort_slots, cohort_prompts);
        for (std::size_t request = 0; request < full_predictions.size(); ++request) {
          predictions[request] = full_predictions[request];
        }
      }
      const auto prediction_time = std::chrono::steady_clock::now();
      const auto prefill_microseconds = static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::microseconds>(
              prediction_time - prefill_begin).count());
      std::uint64_t computed_tokens = 0;
      for (const int tokens : cohort_tokens) {
        computed_tokens += static_cast<std::uint64_t>(tokens);
      }
      const std::uint64_t prefill_batch_id = ++batch_id_;
      for (std::size_t row = 0; row < cohort_slots.size(); ++row) {
        const auto& slot = slots_[static_cast<std::size_t>(cohort_slots[row])];
        trace(desmond::TraceEventType::batch_formed,
              slot.job ? slot.job->request_id : 0, prefill_batch_id, 0,
              static_cast<std::uint64_t>(runner_.slot_position(cohort_slots[row])), row,
              row < cohort_tokens.size() ? static_cast<std::uint64_t>(cohort_tokens[row]) : 0,
              static_cast<std::uint32_t>(cohort_slots[row]));
      }
      trace(desmond::TraceEventType::prefill_batch, 0, prefill_batch_id, prefill_microseconds,
            complete ? config_layer_count_ : 0, cohort_slots.size(), computed_tokens,
            static_cast<std::uint32_t>((has_decoding ? 1 : 0) |
                                       (resuming_layer_slices ? 2 : 0)));
      metrics_.suffix_prefill_microseconds.fetch_add(prefill_microseconds);
      update_atomic_max(metrics_.maximum_suffix_prefill_microseconds, prefill_microseconds);
      if (!resuming_layer_slices) {
        metrics_.suffix_prefill_batches.fetch_add(1);
        if (has_decoding) metrics_.interleaved_suffix_prefill_batches.fetch_add(1);
        metrics_.suffix_prefill_requests.fetch_add(cohort_slots.size());
        metrics_.suffix_prefill_batch_calls.at(cohort_slots.size()).fetch_add(1);
        for (const int tokens : cohort_tokens) {
          metrics_.prefill_tokens_computed.fetch_add(static_cast<std::uint64_t>(tokens));
          metrics_.suffix_prefill_tokens.fetch_add(static_cast<std::uint64_t>(tokens));
        }
      }
      if (!complete) return true;
      inflight_suffix_slots_.clear();
      inflight_suffix_prompts_.clear();
      for (std::size_t request = 0; request < cohort_slots.size(); ++request) {
        const int index = cohort_slots[request];
        auto& slot = slots_[static_cast<std::size_t>(index)];
        const int resident = runner_.slot_position(index);
        slot.cached_tokens.assign(slot.job->input_ids.begin(),
                                  slot.job->input_ids.begin() + resident);
        if (!predictions[request]) continue;
        slot.token_to_append = *predictions[request];
        emit_token(slot, *predictions[request]);
        slot.decode_ready = true;
        slot.ttft_microseconds = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(
                prediction_time - slot.job->queued_at).count());
        slot.last_token_at = prediction_time;
        metrics_.decoding.fetch_add(1);
        if (slot.job->stop_ids.contains(*predictions[request])) {
          complete_slot(index, "stop");
        } else if (slot.job->max_tokens == 1) {
          complete_slot(index, "length");
        }
      }
    } catch (const std::exception& error) {
      runner_.abort_suffix_layer_slices();
      inflight_suffix_slots_.clear();
      inflight_suffix_prompts_.clear();
      for (const int index : cohort_slots) {
        if (slots_[static_cast<std::size_t>(index)].job) fail_slot(index, error.what());
      }
      return true;
    }
    const auto release_time = std::chrono::steady_clock::now();
    for (const int index : cohort_slots) {
      auto& slot = slots_[static_cast<std::size_t>(index)];
      if (!slot.job || !slot.decode_ready) continue;
      slot.ttft_microseconds = static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::microseconds>(
              release_time - slot.job->queued_at).count());
      slot.last_token_at = release_time;
    }
    return true;
  }

  bool wait_for_short_prefill_cohort() {
    if (!inflight_suffix_slots_.empty()) return false;
    if (short_prefill_batch_window_microseconds_ <= 0) return false;
    std::optional<std::chrono::steady_clock::time_point> oldest;
    for (int index = 0; index < maximum_slots; ++index) {
      const auto& slot = slots_[static_cast<std::size_t>(index)];
      if (!slot.job) continue;
      if (slot.decode_ready) return false;
      const int remaining = static_cast<int>(slot.job->input_ids.size()) -
                            runner_.slot_position(index);
      if (remaining <= 0 || remaining > short_prefill_cohort_tokens) return false;
      if (!oldest || slot.job->queued_at < *oldest) oldest = slot.job->queued_at;
    }
    if (!oldest) return false;
    const auto deadline = *oldest +
        std::chrono::microseconds(short_prefill_batch_window_microseconds_);
    if (std::chrono::steady_clock::now() >= deadline) return false;
    std::unique_lock lock(mutex_);
    condition_.wait_until(lock, deadline, [&] { return stopping_ || !pending_.empty(); });
    return !pending_.empty();
  }

  void run() {
    while (true) {
      bool worked = false;
      if (reap_cancelled()) worked = true;
      while (admit_one()) worked = true;
      if (wait_for_short_prefill_cohort()) continue;
      if (drain_short_prefill_cohort()) worked = true;
      if (decode_step()) worked = true;
      if (inflight_suffix_slots_.empty() && prefill_step()) worked = true;
      if (worked) continue;
      std::unique_lock lock(mutex_);
      condition_.wait(lock, [&] { return stopping_ || !pending_.empty(); });
      if (stopping_ && pending_.empty() && !has_active()) return;
    }
  }

  gradiated::engine::Gemma4BatchModelRunner runner_;
  std::vector<Slot> slots_;
  RuntimeMetrics& metrics_;
  int speculative_depth_;
  int speculative_minimum_batch_;
  int prefill_quantum_tokens_;
  int idle_prefill_quantum_tokens_;
  int short_prefill_batch_window_microseconds_;
  int interleaved_suffix_layer_quantum_;
  int interleaved_suffix_layer_minimum_decode_;
  int cache_affinity_max_bypasses_;
  int idle_cache_reserve_slots_;
  const std::size_t config_layer_count_;
  desmond::SharedTraceRing* trace_ring_;
  std::vector<int> inflight_suffix_slots_;
  std::vector<const std::vector<int>*> inflight_suffix_prompts_;
  std::mutex mutex_;
  std::condition_variable condition_;
  std::deque<std::shared_ptr<CompletionJob>> pending_;
  bool stopping_{false};
  std::uint64_t age_{0};
  std::uint64_t admission_order_{0};
  std::atomic<std::uint64_t> next_request_id_{1};
  std::uint64_t batch_id_{0};
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
    std::unique_ptr<gradiated::engine::Fp8WeightArena> fp8_weights;
    const std::string fp8_decode = environment("GRADIATED_FP8_DECODE", "off");
    if (fp8_decode == "tensor") {
      const float weight_scale_multiplier = environment_float(
          "GRADIATED_FP8_WEIGHT_SCALE_MULTIPLIER", 1.0F, 0.0F, 1.0F);
      if (weight_scale_multiplier == 0.0F) {
        throw std::runtime_error("GRADIATED_FP8_WEIGHT_SCALE_MULTIPLIER must be positive");
      }
      fp8_weights = gradiated::engine::Fp8WeightArena::quantize(
          plan, *weights, gradiated::engine::Fp8Scaling::tensor,
          weight_scale_multiplier);
      if (environment("GRADIATED_INT4_LM_HEAD_ORACLE", "0") == "1") {
        const int block_width = environment_integer(
            "GRADIATED_INT4_LM_HEAD_ORACLE_BLOCK", 128, 32, 256);
        if (block_width != 32 && block_width != 64 &&
            block_width != 128 && block_width != 256) {
          throw std::runtime_error(
              "GRADIATED_INT4_LM_HEAD_ORACLE_BLOCK must be 32, 64, 128, or 256");
        }
        fp8_weights->roundtrip_int4(
            "token_embedding", static_cast<int>(config.vocabulary_size),
            static_cast<int>(config.hidden_size), block_width);
      }
    } else if (fp8_decode != "off") {
      throw std::runtime_error("GRADIATED_FP8_DECODE must be off or tensor");
    }
    std::unique_ptr<gradiated::engine::DeviceWeightArena> assistant_weights;
    std::unique_ptr<gradiated::engine::Fp8WeightArena> assistant_fp8_weights;
    const std::string assistant_directory = environment("GRADIATED_ASSISTANT_MODEL_PATH");
    if (!assistant_directory.empty()) {
      if (!fp8_weights) {
        throw std::runtime_error("the native assistant requires FP8 target verification");
      }
      const auto assistant_host =
          gradiated::engine::ShardedSafetensors::open(assistant_directory);
      const auto assistant_plan =
          gradiated::engine::WeightPlan::gemma4_assistant(assistant_host);
      assistant_weights = gradiated::engine::DeviceWeightArena::load(
          assistant_plan, assistant_host);
      const std::string assistant_fp8_mode = environment("GRADIATED_ASSISTANT_FP8_MODE", "off");
      if (assistant_fp8_mode == "lm_head" || assistant_fp8_mode == "all") {
        assistant_fp8_weights = gradiated::engine::Fp8WeightArena::quantize(
            assistant_plan, *assistant_weights, gradiated::engine::Fp8Scaling::tensor);
      } else if (assistant_fp8_mode != "off") {
        throw std::runtime_error(
            "GRADIATED_ASSISTANT_FP8_MODE must be off, lm_head or all");
      }
    }

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
    const int short_prefill_batch_window_microseconds = environment_integer(
        "GRADIATED_SHORT_PREFILL_BATCH_WINDOW_US",
        default_short_prefill_batch_window_microseconds, 0, 20000);
    const int interleaved_suffix_layer_quantum = environment_integer(
        "GRADIATED_INTERLEAVED_SUFFIX_LAYER_QUANTUM",
        default_interleaved_suffix_layer_quantum, 0,
        static_cast<int>(config.layers.size()));
    const int interleaved_suffix_layer_minimum_decode = environment_integer(
        "GRADIATED_INTERLEAVED_SUFFIX_LAYER_MIN_DECODE",
        default_interleaved_suffix_layer_minimum_decode, 1, maximum_slots);
    const int speculative_depth = environment_integer(
        "GRADIATED_SPECULATIVE_DEPTH", default_speculative_depth, 1, 8);
    const int speculative_minimum_batch = environment_integer(
        "GRADIATED_SPECULATIVE_MIN_BATCH", default_speculative_minimum_batch, 1,
        maximum_slots);
    const int cache_affinity_max_bypasses = environment_integer(
        "GRADIATED_CACHE_AFFINITY_MAX_BYPASSES", default_cache_affinity_max_bypasses,
        0, 1024);
    const int idle_cache_reserve_slots = environment_integer(
        "GRADIATED_IDLE_CACHE_RESERVE_SLOTS", default_idle_cache_reserve_slots,
        0, maximum_slots - 1);
    const bool ignore_model_eos = environment_flag("GRADIATED_IGNORE_MODEL_EOS");
    std::unique_ptr<desmond::SharedTraceRing> trace_ring;
    const std::string trace_path = environment("DESMOND_TRACE_PATH");
    if (!trace_path.empty()) {
      try {
        trace_ring = desmond::SharedTraceRing::open_existing(trace_path);
      } catch (const std::exception& error) {
        std::cerr << "native runtime: shared trace ring unavailable: " << error.what() << '\n';
      }
    }
    RuntimeMetrics metrics;
    ContinuousScheduler scheduler(config, *weights, fp8_weights.get(), assistant_weights.get(),
                                  assistant_fp8_weights.get(),
                                  metrics, speculative_depth, speculative_minimum_batch,
                                  prefill_quantum_tokens,
                                  idle_prefill_quantum_tokens,
                                  short_prefill_batch_window_microseconds,
                                  interleaved_suffix_layer_quantum,
                                  interleaved_suffix_layer_minimum_decode,
                                  cache_affinity_max_bypasses,
                                  idle_cache_reserve_slots,
                                  trace_ring.get());

    desmond::HttpServer server(bind_host, bind_port, [&](const desmond::HttpRequest& request) {
      if (request.method == "GET" && request.path == "/health") {
        return desmond::HttpResponse{200, "text/plain; charset=utf-8", "ready\n"};
      }
      if (request.method == "GET" && request.path == "/metrics") {
        std::ostringstream body;
        body << "gradiated_native_requests_total " << metrics.requests.load() << '\n'
             << "gradiated_native_failures_total " << metrics.failures.load() << '\n'
             << "gradiated_native_cancelled_requests_total " << metrics.cancelled.load() << '\n'
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
             << "gradiated_native_cache_affinity_admissions_total "
             << metrics.cache_affinity_admissions.load() << '\n'
             << "gradiated_native_cache_affinity_bypassed_requests_total "
             << metrics.cache_affinity_bypassed_requests.load() << '\n'
             << "gradiated_native_prefill_tokens_computed_total "
             << metrics.prefill_tokens_computed.load() << '\n'
             << "gradiated_native_kv_cache_clones_total " << metrics.kv_cache_clones.load() << '\n'
             << "gradiated_native_kv_cache_clone_bytes_total "
             << metrics.kv_cache_clone_bytes.load() << '\n'
             << "gradiated_native_suffix_prefill_batches_total "
             << metrics.suffix_prefill_batches.load() << '\n'
             << "gradiated_native_interleaved_suffix_prefill_batches_total "
             << metrics.interleaved_suffix_prefill_batches.load() << '\n'
             << "gradiated_native_suffix_prefill_requests_total "
             << metrics.suffix_prefill_requests.load() << '\n'
             << "gradiated_native_suffix_prefill_tokens_total "
             << metrics.suffix_prefill_tokens.load() << '\n'
             << "gradiated_native_suffix_prefill_seconds_total "
             << static_cast<double>(metrics.suffix_prefill_microseconds.load()) / 1000000.0
             << '\n'
             << "gradiated_native_suffix_prefill_max_seconds "
             << static_cast<double>(metrics.maximum_suffix_prefill_microseconds.load()) / 1000000.0
             << '\n'
             << "gradiated_native_suffix_prefill_layer_slices_total "
             << metrics.suffix_prefill_layer_slices.load() << '\n'
             << "gradiated_native_speculative_cycles_total "
             << metrics.speculative_cycles.load() << '\n'
             << "gradiated_native_speculative_proposed_tokens_total "
             << metrics.speculative_proposed_tokens.load() << '\n'
             << "gradiated_native_speculative_accepted_tokens_total "
             << metrics.speculative_accepted_tokens.load() << '\n'
             << "gradiated_native_speculative_first_token_rejections_total "
             << metrics.speculative_first_token_rejections.load() << '\n'
             << "gradiated_native_speculative_draft_seconds_total "
             << static_cast<double>(metrics.speculative_draft_microseconds.load()) / 1000000.0
             << '\n'
             << "gradiated_native_speculative_verify_seconds_total "
             << static_cast<double>(metrics.speculative_verify_microseconds.load()) / 1000000.0
             << '\n'
             << "gradiated_native_contiguous_decode_steps_total "
             << metrics.contiguous_decode_steps.load() << '\n'
             << "gradiated_native_fragmented_decode_steps_total "
             << metrics.fragmented_decode_steps.load() << '\n'
             << "gradiated_native_fp8_decode " << (fp8_weights ? 1 : 0) << '\n'
             << "gradiated_native_prefill_quantum_tokens " << prefill_quantum_tokens << '\n'
             << "gradiated_native_idle_prefill_quantum_tokens "
             << idle_prefill_quantum_tokens << '\n';
        for (int batch = 1; batch <= maximum_slots; ++batch) {
          body << "gradiated_native_decode_batch_steps_total{batch=\"" << batch << "\"} "
               << metrics.decode_batch_steps[static_cast<std::size_t>(batch)].load() << '\n'
               << "gradiated_native_suffix_prefill_batch_calls_total{batch=\"" << batch
               << "\"} "
               << metrics.suffix_prefill_batch_calls[static_cast<std::size_t>(batch)].load()
               << '\n';
        }
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
        if (!ignore_model_eos) {
          stop_ids.insert(config.eos_token_ids.begin(), config.eos_token_ids.end());
        }
        if (const auto* value = body.find("stop_token_ids")) {
          for (const int token : integer_array(*value, "stop_token_ids")) stop_ids.insert(token);
        }
        const bool stream = optional_bool(body, "stream", false);
        const int priority = optional_integer(body, "priority", 0);

        if (stream) {
          auto job = scheduler.submit(input_ids, max_tokens, std::move(stop_ids), priority);
          return desmond::HttpResponse{
              200, "text/event-stream", {},
              [job, &scheduler, input_tokens = input_ids.size()](
                  const desmond::HttpChunkWriter& write) {
                std::size_t emitted_tokens = 0;
                while (true) {
                  std::optional<int> token;
                  std::optional<CompletionResult> result;
                  std::string error;
                  {
                    std::unique_lock lock(job->mutex);
                    job->condition.wait(lock, [&] {
                      return !job->emitted_ids.empty() || job->done;
                    });
                    if (!job->emitted_ids.empty()) {
                      token = job->emitted_ids.front();
                      job->emitted_ids.pop_front();
                    } else if (job->done) {
                      error = job->error;
                      if (job->result) result = std::move(*job->result);
                    }
                  }
                  if (token) {
                    ++emitted_tokens;
                    const auto cached_input_tokens =
                        job->cached_input_tokens.load(std::memory_order_acquire);
                    std::ostringstream event;
                    event << "data: {\"token_id\":" << *token
                          << ",\"usage\":{\"input_tokens\":" << input_tokens
                          << ",\"cached_input_tokens\":" << cached_input_tokens
                          << ",\"output_tokens\":" << emitted_tokens << "}}\n\n";
                    if (!write(event.str())) {
                      scheduler.cancel(job);
                      return;
                    }
                    continue;
                  }
                  if (!error.empty() || !result) return;
                  std::ostringstream terminal;
                  terminal << "data: {\"finish_reason\":"
                           << desmond::json_string(result->finish_reason)
                           << ",\"usage\":{\"input_tokens\":" << input_tokens
                           << ",\"cached_input_tokens\":"
                           << result->cached_input_tokens
                           << ",\"output_tokens\":" << result->output_ids.size()
                           << "}}\n\n";
                  if (!write(terminal.str()) || !write("data: [DONE]\n\n")) {
                    scheduler.cancel(job);
                  }
                  return;
                }
              }};
        }

        auto result = scheduler.complete(input_ids, max_tokens, std::move(stop_ids), priority);
        std::ostringstream response;
        response << "{\"output_ids\":" << token_array_json(result.output_ids)
                 << ",\"usage\":{\"input_tokens\":" << input_ids.size()
                 << ",\"cached_input_tokens\":" << result.cached_input_tokens
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
              << " idle_prefill_quantum_tokens=" << idle_prefill_quantum_tokens
              << " short_prefill_batch_window_us="
              << short_prefill_batch_window_microseconds
              << " interleaved_suffix_layer_quantum="
              << interleaved_suffix_layer_quantum
              << " interleaved_suffix_layer_min_decode="
              << interleaved_suffix_layer_minimum_decode
              << " cache_affinity_max_bypasses=" << cache_affinity_max_bypasses
              << " idle_cache_reserve_slots=" << idle_cache_reserve_slots
              << " fp8_decode=" << fp8_decode
              << " ignore_model_eos=" << (ignore_model_eos ? "true" : "false")
              << " assistant=" << (assistant_weights ? "enabled" : "off") << '\n';
    server.run();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "native runtime failed: " << error.what() << '\n';
    return 70;
  }
}
