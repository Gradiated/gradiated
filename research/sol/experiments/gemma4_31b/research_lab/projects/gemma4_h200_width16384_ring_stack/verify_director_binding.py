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


mlp_binding = bound(BINDING["mlp_binding"])
ring_binding = bound(BINDING["ring_binding"])
mlp = bound(BINDING["mlp_endpoint"])
ring_terminal = bound(BINDING["ring_terminal"])
ring = bound(BINDING["ring_endpoint"])

assert mlp_binding["stack_binding"]["sha256"] == ring_binding["stack_binding"]["sha256"]
assert mlp_binding["bench_id"] == BINDING["bench_id"] == ring_binding["bench_id"]
assert mlp["classification"] == "frontier_nomination"
assert mlp["candidate_seconds_per_request"] == BINDING["mlp_endpoint"]["service_seconds_per_request"]
assert mlp["quality_unsafe"] is True
assert mlp["path_proof"]["layers"] == 60
assert ring_terminal["classification"] == "retain_ring"
assert ring["pass"] is True
assert ring["candidate"]["service_seconds_per_request"] == BINDING["ring_endpoint"]["candidate_seconds_per_request"]
assert ring["reduction_fraction"] == BINDING["ring_endpoint"]["reduction_fraction"]
assert ring["transition_proof"]["pass"] is True
change = BINDING["candidate_change"]
assert change["mlp_intermediate_size"] == 16384
assert change["mlp_layer_count"] == 60
assert change["local_ring_layer_count"] == 50
assert change["local_kv_dtype"] == "fp8_e5m2"
assert change["local_window_tokens"] == 1024
assert change["quality_claim_authorized"] is False
print(json.dumps({"binding": "DIRECTOR_BINDING.json", "pass": True}, sort_keys=True))
