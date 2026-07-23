#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BINDING = json.loads((HERE / "DIRECTOR_BINDING.json").read_text())


def load_bound(spec):
    path = (HERE / spec["path"]).resolve()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"]
    return json.loads(path.read_text())


stack = load_bound(BINDING["authoritative_stack"])
negative = load_bound(BINDING["uniform_e4m3_negative"])
source = load_bound(BINDING["hybrid_source_binding"])
control_path = (HERE / stack["control"]["path"]).resolve()

assert hashlib.sha256(control_path.read_bytes()).hexdigest() == stack["control"]["sha256"]
assert stack["model"] == "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4"
assert stack["runtime"]["commit"] == "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
assert stack["workload"] == {
    "requests": 32,
    "concurrency": 32,
    "prompt_tokens_per_request": 4214,
    "completion_tokens_per_request": 358,
    "cached_prompt_tokens_total": 17120,
    "fresh_prompt_tokens_total": 117728,
}
assert negative["classification"] == "close"
assert negative["candidate_service_seconds_per_request"] == BINDING["uniform_e4m3_negative"]["service_seconds_per_request"]
assert negative["persisted_e5m2_control_seconds_per_request"] == stack["control"]["service_seconds_per_request"]
assert source["status"] == "offline_binding_pass"
assert source["geometry"]["local"]["head_dim"] == 256
assert len(source["geometry"]["local"]["layer_ids"]) == 50
assert source["geometry"]["global"]["head_dim"] == 512
assert source["geometry"]["global"]["layer_ids"] == BINDING["candidate_change"]["global_layer_ids"]
assert BINDING["candidate_change"]["local_kv_cache_dtype"] == "fp8_e4m3"
assert BINDING["candidate_change"]["global_kv_cache_dtype"] == "fp8_e5m2"
print(json.dumps({"binding": "DIRECTOR_BINDING.json", "pass": True}, sort_keys=True))
