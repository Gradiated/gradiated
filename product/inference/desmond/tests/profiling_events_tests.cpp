#include "desmond/profiling_events.h"

#include "test_support.h"

#include <cstdint>
#include <limits>
#include <string>

namespace {

using desmond::TraceEventType;

constexpr std::uint32_t no_slot = std::numeric_limits<std::uint32_t>::max();

desmond::TraceEvent event_of(const TraceEventType type, const std::uint64_t request_low = 0,
                             const std::uint32_t stream_id = 3) {
  return {
      .monotonic_ns = 1000,
      .request_id_high = 0,
      .request_id_low = request_low,
      .batch_id = 0,
      .graph_execution_id = 40,
      .graph_node_id = 0,
      .value0 = 10,
      .value1 = 20,
      .stream_id = stream_id,
      .device_id = 0,
      .type = type,
  };
}

std::string properties(const desmond::TraceEvent &event) {
  return desmond::trace_event_properties(event);
}

DESMOND_TEST(request_admitted_maps_tokens_slot_and_queue_time) {
  CHECK(properties(event_of(TraceEventType::request_admitted, 7)) ==
        "{\"monotonic_ns\":1000,\"request_id_high\":\"0\",\"request_id_low\":\"7\","
        "\"input_tokens\":10,\"cached_input_tokens\":20,\"slot_id\":3,\"queue_us\":40}");
}

DESMOND_TEST(request_finished_maps_output_ttft_slot_and_total_time) {
  CHECK(properties(event_of(TraceEventType::request_finished, 7)) ==
        "{\"monotonic_ns\":1000,\"request_id_high\":\"0\",\"request_id_low\":\"7\","
        "\"output_tokens\":10,\"ttft_us\":20,\"slot_id\":3,\"total_us\":40}");
}

DESMOND_TEST(batch_formed_maps_row_shape_context_and_slot) {
  auto event = event_of(TraceEventType::batch_formed, 7);
  event.batch_id = 99;
  event.graph_node_id = 512;

  CHECK(properties(event) ==
        "{\"monotonic_ns\":1000,\"request_id_high\":\"0\",\"request_id_low\":\"7\","
        "\"batch_id\":\"99\",\"batch_row\":10,\"batch_shape_value\":20,"
        "\"request_context_tokens\":512,\"slot_id\":3}");
}

DESMOND_TEST(failed_and_cancelled_requests_include_a_slot_only_when_assigned) {
  for (const auto type : {TraceEventType::request_failed, TraceEventType::request_cancelled}) {
    CHECK(
        properties(event_of(type, 7)) ==
        "{\"monotonic_ns\":1000,\"request_id_high\":\"0\",\"request_id_low\":\"7\",\"slot_id\":3}");
    CHECK(properties(event_of(type, 7, no_slot)) ==
          "{\"monotonic_ns\":1000,\"request_id_high\":\"0\",\"request_id_low\":\"7\"}");
  }
}

DESMOND_TEST(prefill_batch_uses_slot_for_a_request_and_flags_otherwise) {
  CHECK(properties(event_of(TraceEventType::prefill_batch, 7)) ==
        "{\"monotonic_ns\":1000,\"request_id_high\":\"0\",\"request_id_low\":\"7\","
        "\"batch_size\":10,\"computed_tokens\":20,\"duration_us\":40,\"slot_id\":3}");
  CHECK(properties(event_of(TraceEventType::prefill_batch)) ==
        "{\"monotonic_ns\":1000,\"batch_size\":10,\"computed_tokens\":20,\"duration_us\":40,"
        "\"execution_flags\":3}");
}

DESMOND_TEST(decode_and_speculative_batches_name_the_cache_layout) {
  for (const auto type : {TraceEventType::decode_batch, TraceEventType::speculative_batch}) {
    CHECK(properties(event_of(type, 0, 1)) ==
          "{\"monotonic_ns\":1000,\"batch_size\":10,\"maximum_context_tokens\":20,"
          "\"duration_us\":40,\"cache_layout\":\"contiguous\"}");
    CHECK(properties(event_of(type, 0, 0)) ==
          "{\"monotonic_ns\":1000,\"batch_size\":10,\"maximum_context_tokens\":20,"
          "\"duration_us\":40,\"cache_layout\":\"fragmented\"}");
  }
}

DESMOND_TEST(other_event_types_keep_raw_values) {
  auto event = event_of(TraceEventType::kv_cache_allocate);
  event.device_id = 2;

  CHECK(properties(event) ==
        "{\"monotonic_ns\":1000,\"device_id\":2,\"value0\":10,\"value1\":20,\"duration_us\":40}");
}

DESMOND_TEST(unknown_event_types_from_the_ring_keep_raw_values) {
  const auto event = event_of(static_cast<TraceEventType>(999));

  CHECK(properties(event) ==
        "{\"monotonic_ns\":1000,\"value0\":10,\"value1\":20,\"duration_us\":40}");
}

DESMOND_TEST(large_request_and_batch_ids_are_json_strings) {
  auto event = event_of(TraceEventType::request_failed, UINT64_MAX, no_slot);
  event.request_id_high = UINT64_MAX;
  event.batch_id = UINT64_MAX;

  CHECK(properties(event) ==
        "{\"monotonic_ns\":1000,\"request_id_high\":\"18446744073709551615\","
        "\"request_id_low\":\"18446744073709551615\",\"batch_id\":\"18446744073709551615\"}");
}

DESMOND_TEST(gpu_sample_with_every_reading) {
  const desmond::GpuSample sample{
      .index = 1,
      .uuid = "GPU-1",
      .utilization = desmond::GpuUtilization{.gpu_percent = 90, .memory_percent = 40},
      .memory = desmond::GpuMemory{.total_bytes = 100, .used_bytes = 60, .free_bytes = 40},
      .temperature_celsius = 70U,
      .power_milliwatts = 300'000U,
      .total_energy_millijoules = std::uint64_t{5'000},
  };

  CHECK(desmond::gpu_sample_properties(sample) ==
        "{\"gpu_index\":1,\"gpu_uuid\":\"GPU-1\",\"gpu_utilization_percent\":90,"
        "\"memory_utilization_percent\":40,\"memory_total_bytes\":100,\"memory_used_bytes\":60,"
        "\"memory_free_bytes\":40,\"temperature_celsius\":70,\"power_milliwatts\":300000,"
        "\"total_energy_millijoules\":5000}");
}

DESMOND_TEST(gpu_sample_without_readings_has_only_the_index) {
  CHECK(desmond::gpu_sample_properties({.index = 3}) == "{\"gpu_index\":3}");
}

} // namespace
