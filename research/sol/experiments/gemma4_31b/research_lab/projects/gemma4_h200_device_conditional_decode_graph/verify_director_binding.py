#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BINDING = json.loads((HERE / "DIRECTOR_BINDING.json").read_text())


def bound(spec):
    path = (HERE / spec["path"]).resolve()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"]
    return json.loads(path.read_text())


stack = bound(BINDING["stack_binding"])
control = bound(BINDING["control"])
trace = bound(BINDING["current_trace"])
continuous = bound(BINDING["closed_host_continuous_steps"])
scheduler = bound(BINDING["closed_scheduler_snapshot"])

assert stack["model"]["id"] == "google/gemma-4-31B-it"
assert stack["model"]["revision"] == "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
assert stack["runtime"]["commit"] == "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
assert stack["workload"]["requests"] == 32
assert stack["workload"]["concurrency"] == 32
assert stack["workload"]["cached_prompt_tokens_total"] == 17120
assert stack["workload"]["fresh_prompt_tokens_total"] == 117728
assert control["service_seconds_per_request"] == BINDING["control"]["service_seconds_per_request"]
boundaries = {row["boundary"]: row for row in trace["trace_attribution"]["boundaries"]}
assert boundaries["scheduler_gap"]["seconds"] == BINDING["current_trace"]["scheduler_gap_seconds"]
assert boundaries["scheduler_gap"]["wall_fraction"] == BINDING["current_trace"]["scheduler_gap_fraction"]
assert boundaries["launch"]["seconds"] == BINDING["current_trace"]["launch_seconds"]
assert boundaries["launch"]["wall_fraction"] == BINDING["current_trace"]["launch_fraction"]
assert continuous["candidate"]["arm"] == BINDING["closed_host_continuous_steps"]["arm"]
assert continuous["service_seconds_per_request_reduction"] == BINDING["closed_host_continuous_steps"]["reduction_fraction"]
assert continuous["service_seconds_per_request_reduction"] < 0
assert scheduler["classification"] == "close_scheduler_overlap"
assert scheduler["reduction_fraction"] == BINDING["closed_scheduler_snapshot"]["reduction_fraction"]
assert scheduler["reduction_fraction"] < 0
change = BINDING["candidate_change"]
assert change["repeat_tokens"] == 4
assert change["continuation_owner"] == "device"
assert change["full_one_token_serving_body"] is True
assert change["host_continuous_decode_flag"] is False
assert change["schedule_stream_penalty_snapshot"] is False
assert change["credit_synchronization_boundary"] is False
print(json.dumps({"binding": "DIRECTOR_BINDING.json", "pass": True}, sort_keys=True))
