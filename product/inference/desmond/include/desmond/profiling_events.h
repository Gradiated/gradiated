#pragma once

#include "desmond/gpu_metrics.h"
#include "desmond/trace.h"

#include <string>

namespace desmond {

[[nodiscard]] std::string trace_event_properties(const TraceEvent &event);
[[nodiscard]] std::string gpu_sample_properties(const GpuSample &sample);

} // namespace desmond
