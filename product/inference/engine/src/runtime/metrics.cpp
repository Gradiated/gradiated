#include "runtime/metrics.h"

#include "runtime/decimal.h"
#include "runtime/settings.h"

#include <sstream>
#include <string_view>

namespace gradiated::engine {
namespace {

enum class Unit { count, seconds };

struct Series {
  std::string_view name;
  Counter RuntimeMetrics::*value;
  Unit unit{Unit::count};
};

constexpr std::array series{
    Series{"gradiated_native_requests_total", &RuntimeMetrics::requests},
    Series{"gradiated_native_invalid_requests_total", &RuntimeMetrics::invalid_requests},
    Series{"gradiated_native_failures_total", &RuntimeMetrics::failures},
    Series{"gradiated_native_cancelled_requests_total", &RuntimeMetrics::cancelled},
    Series{"gradiated_native_input_tokens_total", &RuntimeMetrics::input_tokens},
    Series{"gradiated_native_output_tokens_total", &RuntimeMetrics::output_tokens},
    Series{"gradiated_native_inference_seconds_total", &RuntimeMetrics::inference_microseconds, Unit::seconds},
    Series{"gradiated_native_queued_requests", &RuntimeMetrics::queued},
    Series{"gradiated_native_active_requests", &RuntimeMetrics::active},
    Series{"gradiated_native_decoding_requests", &RuntimeMetrics::decoding},
    Series{"gradiated_native_prefix_cache_hits_total", &RuntimeMetrics::prefix_cache_hits},
    Series{"gradiated_native_prefix_tokens_reused_total", &RuntimeMetrics::prefix_tokens_reused},
    Series{"gradiated_native_cache_affinity_admissions_total", &RuntimeMetrics::cache_affinity_admissions},
    Series{"gradiated_native_cache_affinity_bypassed_requests_total",
           &RuntimeMetrics::cache_affinity_bypassed_requests},
    Series{"gradiated_native_prefill_tokens_computed_total", &RuntimeMetrics::prefill_tokens_computed},
    Series{"gradiated_native_kv_cache_clones_total", &RuntimeMetrics::kv_cache_clones},
    Series{"gradiated_native_kv_cache_clone_bytes_total", &RuntimeMetrics::kv_cache_clone_bytes},
    Series{"gradiated_native_suffix_prefill_batches_total", &RuntimeMetrics::suffix_prefill_batches},
    Series{"gradiated_native_interleaved_suffix_prefill_batches_total",
           &RuntimeMetrics::interleaved_suffix_prefill_batches},
    Series{"gradiated_native_suffix_prefill_requests_total", &RuntimeMetrics::suffix_prefill_requests},
    Series{"gradiated_native_suffix_prefill_tokens_total", &RuntimeMetrics::suffix_prefill_tokens},
    Series{"gradiated_native_suffix_prefill_seconds_total", &RuntimeMetrics::suffix_prefill_microseconds,
           Unit::seconds},
    Series{"gradiated_native_suffix_prefill_max_seconds", &RuntimeMetrics::maximum_suffix_prefill_microseconds,
           Unit::seconds},
    Series{"gradiated_native_suffix_prefill_layer_slices_total", &RuntimeMetrics::suffix_prefill_layer_slices},
    Series{"gradiated_native_speculative_cycles_total", &RuntimeMetrics::speculative_cycles},
    Series{"gradiated_native_speculative_proposed_tokens_total", &RuntimeMetrics::speculative_proposed_tokens},
    Series{"gradiated_native_speculative_accepted_tokens_total", &RuntimeMetrics::speculative_accepted_tokens},
    Series{"gradiated_native_speculative_first_token_rejections_total",
           &RuntimeMetrics::speculative_first_token_rejections},
    Series{"gradiated_native_speculative_draft_seconds_total", &RuntimeMetrics::speculative_draft_microseconds,
           Unit::seconds},
    Series{"gradiated_native_speculative_verify_seconds_total", &RuntimeMetrics::speculative_verify_microseconds,
           Unit::seconds},
    Series{"gradiated_native_contiguous_decode_steps_total", &RuntimeMetrics::contiguous_decode_steps},
    Series{"gradiated_native_fragmented_decode_steps_total", &RuntimeMetrics::fragmented_decode_steps},
};

}  // namespace

void update_maximum(Counter& target, std::uint64_t value) {
  std::uint64_t current = target.load(std::memory_order_relaxed);
  while (current < value && !target.compare_exchange_weak(current, value, std::memory_order_relaxed)) {}
}

std::string render_metrics(const RuntimeMetrics& metrics, const RuntimeSettings& settings) {
  std::ostringstream body;
  for (const Series& entry : series) {
    const std::uint64_t value = (metrics.*entry.value).load();
    body << entry.name << ' ';
    if (entry.unit == Unit::seconds) {
      write_decimal(body, value, 6);
    } else {
      body << value;
    }
    body << '\n';
  }

  body << "gradiated_native_fp8_decode " << (settings.fp8_decode ? 1 : 0) << '\n'
       << "gradiated_native_prefill_quantum_tokens " << settings.scheduler.prefill_quantum_tokens << '\n'
       << "gradiated_native_idle_prefill_quantum_tokens " << settings.scheduler.idle_prefill_quantum_tokens << '\n';

  for (std::size_t batch = 1; batch <= maximum_slots; ++batch) {
    body << "gradiated_native_decode_batch_steps_total{batch=\"" << batch << "\"} "
         << metrics.decode_batch_steps[batch].load() << '\n'
         << "gradiated_native_suffix_prefill_batch_calls_total{batch=\"" << batch << "\"} "
         << metrics.suffix_prefill_batch_calls[batch].load() << '\n';
  }
  return body.str();
}

}  // namespace gradiated::engine
