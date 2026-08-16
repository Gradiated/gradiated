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
closed_component = bound(BINDING["closed_two_segment_component"])
closed_terminal = bound(BINDING["closed_two_segment_terminal"])

assert ring_binding["bench_id"] == BINDING["bench_id"]
assert ring_binding["candidate_change"]["local_kv_dtype"] == "fp8_e5m2"
assert ring_binding["candidate_change"]["local_layout"] == "per_request_contiguous_circular_ring"
assert ring_terminal["classification"] == "retain_ring"
assert ring["classification"] == "retain_ring"
assert ring["pass"] is True
assert ring["candidate_service_seconds_per_request"] == BINDING["ring_endpoint"]["candidate_seconds_per_request"]
assert ring["accounting_pass"] is True
assert ring["transition_proof"]["pass"] is True
assert ring["candidate_path_proof"]["pass"] is True
assert closed_component["status"] == "component_semantic_or_nonpositive_reject"
assert closed_component["path_proof"]["candidate_invocations_per_consumer"] == BINDING["closed_two_segment_component"]["candidate_invocations_per_consumer"]
assert closed_component["timing"]["candidate"]["median_ms"] == BINDING["closed_two_segment_component"]["candidate_median_ms"]
assert closed_component["timing"]["control"]["median_ms"] == BINDING["closed_two_segment_component"]["control_median_ms"]
assert closed_component["timing"]["reduction_fraction"]["point"] == BINDING["closed_two_segment_component"]["point_reduction_fraction"]
assert closed_component["semantic_pass"] is False
assert closed_terminal["status"] == "component_nonpositive_reject"

change = BINDING["candidate_change"]
assert change["phase"] == "decode"
assert change["batch_size"] == 32
assert change["local_layer_count"] == 50
assert change["local_window_tokens"] == 1024
assert change["query_heads"] == 32
assert change["kv_heads"] == 16
assert change["head_dim"] == 256
assert change["query_dtype"] == "bfloat16"
assert change["kv_dtype"] == "fp8_e5m2"
assert change["kv_layout"] == "per_request_mirrored_contiguous_ring"
assert change["producer"] == "write_each_local_kv_token_to_both_mirror_positions"
assert change["candidate_consumer"] == "single_invocation_fa3_v3_direct_e5m2_load_dequant"
assert change["global_attention"] == "unchanged_paged_e5m2_triton"
assert change["full_cache_conversion"] == "forbidden"
print(json.dumps({"binding": "DIRECTOR_BINDING.json", "pass": True}, sort_keys=True))
