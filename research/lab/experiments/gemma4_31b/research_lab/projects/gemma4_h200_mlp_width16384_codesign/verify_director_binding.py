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
profile = bound(BINDING["profile_attribution"])
control = bound(BINDING["control"])
geometry = bound(BINDING["real_weight_geometry"])

assert stack["model"]["id"] == "google/gemma-4-31B-it"
assert stack["model"]["revision"] == "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
assert stack["runtime"]["commit"] == "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
assert stack["workload"]["requests"] == 32
assert stack["workload"]["concurrency"] == 32
assert stack["workload"]["cached_prompt_tokens_total"] == 17120
assert stack["workload"]["fresh_prompt_tokens_total"] == 117728
assert control["service_seconds_per_request"] == BINDING["control"]["service_seconds_per_request"]
fp8 = next(row for row in profile["trace_attribution"]["boundaries"] if row["boundary"] == "fp8_linear")
assert fp8["wall_fraction"] == BINDING["profile_attribution"]["fp8_linear_wall_fraction"]
assert geometry["binding"]["hidden_size"] == 5376
assert geometry["binding"]["gate_up_weight_shape"] == [5376, 43008]
change = BINDING["candidate_change"]
assert change["layer_count"] == 60
assert change["hidden_size"] == 5376
assert change["control_intermediate_size"] * 2 == change["control_packed_gate_up_width"]
assert change["candidate_intermediate_size"] * 2 == change["candidate_packed_gate_up_width"]
assert change["candidate_intermediate_size"] == 16384
assert change["candidate_intermediate_size"] % 128 == 0
assert change["quality_claim_authorized"] is False
print(json.dumps({"binding": "DIRECTOR_BINDING.json", "pass": True}, sort_keys=True))
