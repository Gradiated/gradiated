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


ring_binding = bound(BINDING["ring_binding"])
ring_terminal = bound(BINDING["ring_terminal"])
ring = bound(BINDING["ring_endpoint"])
fa3 = bound(BINDING["prior_fa3_component"])
rejection = bound(BINDING["stock_e5m2_rejection"])

assert ring_binding["bench_id"] == BINDING["bench_id"]
assert ring_binding["candidate_change"]["local_kv_dtype"] == "fp8_e5m2"
assert ring_binding["candidate_change"]["local_layout"] == "per_request_contiguous_circular_ring"
assert ring_terminal["classification"] == "retain_ring"
assert ring["transition_proof"]["pass"] is True
assert ring["candidate"]["service_seconds_per_request"] == BINDING["ring_endpoint"]["candidate_seconds_per_request"]
assert fa3["component_pass"] is True
assert fa3["consumer_reduction_fraction"] == BINDING["prior_fa3_component"]["consumer_reduction_fraction"]
assert fa3["producer_consumer_reduction_fraction"] == BINDING["prior_fa3_component"]["producer_consumer_reduction_fraction"]
assert rejection["classification"] == "direct_e5m2_fa3_unsupported"
assert rejection["scientific_invocation_started"] is True
change = BINDING["candidate_change"]
assert change["phase"] == "decode"
assert change["batch_size"] == 32
assert change["local_layer_count"] == 50
assert change["local_window_tokens"] == 1024
assert change["query_heads"] == 32
assert change["kv_heads"] == 16
assert change["head_dim"] == 256
assert change["kv_dtype"] == "fp8_e5m2"
assert change["kv_layout"] == "per_request_contiguous_circular_ring"
assert change["full_cache_conversion"] == "forbidden"
print(json.dumps({"binding": "DIRECTOR_BINDING.json", "pass": True}, sort_keys=True))
