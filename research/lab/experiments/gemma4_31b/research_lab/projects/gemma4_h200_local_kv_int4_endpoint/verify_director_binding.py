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
source = bound(BINDING["current_source_geometry"])
local = bound(BINDING["local_wall_attribution"])

assert stack["model"]["id"] == "google/gemma-4-31B-it"
assert stack["model"]["revision"] == "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
assert stack["runtime"]["commit"] == "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
assert stack["workload"]["requests"] == 32
assert stack["workload"]["concurrency"] == 32
assert stack["workload"]["cached_prompt_tokens_total"] == 17120
assert stack["workload"]["fresh_prompt_tokens_total"] == 117728
assert control["service_seconds_per_request"] == BINDING["control"]["service_seconds_per_request"]
boundaries = {row["boundary"]: row for row in trace["trace_attribution"]["boundaries"]}
assert boundaries["attention_kv"]["wall_fraction"] == BINDING["current_trace"]["attention_kv_fraction"]
assert source["status"] == "frozen"
op = source["operation"]
assert op["phase"] == "decode"
assert op["batch_size"] == 32
assert op["context_tokens"] == 1024
assert op["page_size"] == 1
assert op["kv_dtype"] == "torch.float8_e5m2"
assert op["local_geometry"] == [32, 16, 256]
assert len(op["local_layers"]) == 50
assert op["global_layers"] == [5, 11, 17, 23, 29, 35, 41, 47, 53, 59]
assert local["physical_hypothesis"]["measured_local_wall_fraction"] == BINDING["local_wall_attribution"]["measured_local_wall_fraction"]
change = BINDING["candidate_change"]
assert change["packed_dtype"] == "symmetric_signed_int4_-7_7"
assert change["values_per_byte"] == 2
assert change["group_size"] == 64
assert change["scale_dtype"] == "fp16"
assert change["bytes_reduction_fraction_vs_e5m2"] == 0.46875
assert change["local_head_dim"] == 256
assert change["global_kv_dtype"] == "torch.float8_e5m2"
print(json.dumps({"binding": "DIRECTOR_BINDING.json", "pass": True}, sort_keys=True))
