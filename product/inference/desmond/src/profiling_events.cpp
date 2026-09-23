#include "desmond/profiling_events.h"

#include "desmond/json.h"

#include <cstdint>
#include <limits>

namespace desmond {
namespace {

void write_type_fields(JsonObjectWriter &properties, const TraceEvent &event,
                       const bool has_request) {
  switch (event.type) {
  case TraceEventType::request_admitted:
    properties.field("input_tokens", event.value0)
        .field("cached_input_tokens", event.value1)
        .field("slot_id", event.stream_id)
        .field("queue_us", event.graph_execution_id);
    return;
  case TraceEventType::request_finished:
    properties.field("output_tokens", event.value0)
        .field("ttft_us", event.value1)
        .field("slot_id", event.stream_id)
        .field("total_us", event.graph_execution_id);
    return;
  case TraceEventType::batch_formed:
    properties.field("batch_row", event.value0)
        .field("batch_shape_value", event.value1)
        .field("request_context_tokens", event.graph_node_id)
        .field("slot_id", event.stream_id);
    return;
  case TraceEventType::request_failed:
  case TraceEventType::request_cancelled:
    if (event.stream_id != std::numeric_limits<std::uint32_t>::max()) {
      properties.field("slot_id", event.stream_id);
    }
    return;
  case TraceEventType::prefill_batch:
    properties.field("batch_size", event.value0)
        .field("computed_tokens", event.value1)
        .field("duration_us", event.graph_execution_id)
        .field(has_request ? "slot_id" : "execution_flags", event.stream_id);
    return;
  case TraceEventType::decode_batch:
  case TraceEventType::speculative_batch:
    properties.field("batch_size", event.value0)
        .field("maximum_context_tokens", event.value1)
        .field("duration_us", event.graph_execution_id)
        .field("cache_layout", event.stream_id == 1 ? "contiguous" : "fragmented");
    return;
  case TraceEventType::graph_launch:
  case TraceEventType::graph_node:
  case TraceEventType::kernel_launch:
  case TraceEventType::kv_cache_allocate:
  case TraceEventType::kv_cache_release:
  case TraceEventType::allocator_pressure:
  case TraceEventType::runtime_fault:
    break;
  }

  properties.field("value0", event.value0)
      .field("value1", event.value1)
      .field("duration_us", event.graph_execution_id);
}

} // namespace

std::string trace_event_properties(const TraceEvent &event) {
  JsonObjectWriter properties;
  properties.field("monotonic_ns", event.monotonic_ns);

  const bool has_request = event.request_id_high != 0 || event.request_id_low != 0;
  if (has_request) {
    properties.field("request_id_high", std::to_string(event.request_id_high))
        .field("request_id_low", std::to_string(event.request_id_low));
  }
  if (event.batch_id != 0) {
    properties.field("batch_id", std::to_string(event.batch_id));
  }
  if (event.graph_node_id != 0 && event.type != TraceEventType::batch_formed) {
    properties.field("graph_node_id", event.graph_node_id);
  }
  if (event.device_id != 0) {
    properties.field("device_id", event.device_id);
  }

  write_type_fields(properties, event, has_request);

  return properties.str();
}

std::string gpu_sample_properties(const GpuSample &sample) {
  JsonObjectWriter properties;
  properties.field("gpu_index", sample.index).field("gpu_uuid", sample.uuid);

  if (sample.utilization) {
    properties.field("gpu_utilization_percent", sample.utilization->gpu_percent)
        .field("memory_utilization_percent", sample.utilization->memory_percent);
  }
  if (sample.memory) {
    properties.field("memory_total_bytes", sample.memory->total_bytes)
        .field("memory_used_bytes", sample.memory->used_bytes)
        .field("memory_free_bytes", sample.memory->free_bytes);
  }

  properties.field("temperature_celsius", sample.temperature_celsius)
      .field("power_milliwatts", sample.power_milliwatts)
      .field("total_energy_millijoules", sample.total_energy_millijoules);

  return properties.str();
}

} // namespace desmond
