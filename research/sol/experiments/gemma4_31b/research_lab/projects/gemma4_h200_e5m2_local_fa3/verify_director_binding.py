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
source = bound(BINDING["source_binding"])
prior = bound(BINDING["prior_actual_paged_component"])

assert stack["model"]["id"] == "google/gemma-4-31B-it"
assert stack["model"]["revision"] == "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
assert stack["runtime"]["commit"] == "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
assert stack["workload"]["requests"] == 32
assert stack["workload"]["concurrency"] == 32
assert stack["workload"]["cached_prompt_tokens_total"] == 17120
assert stack["workload"]["fresh_prompt_tokens_total"] == 117728
assert control["service_seconds_per_request"] == BINDING["control"]["service_seconds_per_request"]
assert source["status"] == "offline_binding_pass"
assert source["geometry"]["local"]["head_dim"] == 256
assert len(source["geometry"]["local"]["layer_ids"]) == 50
assert source["geometry"]["global"]["head_dim"] == 512
assert prior["classification"] == "component_insufficient_bound"
assert prior["component"]["producer_consumer_reduction_fraction"] == BINDING["prior_actual_paged_component"]["producer_consumer_reduction_fraction"]
assert prior["component"]["consumer_reduction_fraction"] == BINDING["prior_actual_paged_component"]["consumer_reduction_fraction"]
change = BINDING["candidate_change"]
assert change["local_layer_count"] == 50
assert change["local_kv_dtype"] == "torch.float8_e5m2"
assert change["local_page_size"] == 1
assert change["local_window_tokens"] == 1024
assert change["direct_consumer"] is True
assert change["intermediate_e4m3_conversion"] is False
assert change["global_layer_ids"] == [5, 11, 17, 23, 29, 35, 41, 47, 53, 59]
assert change["global_kv_dtype"] == "torch.float8_e5m2"
print(json.dumps({"binding": "DIRECTOR_BINDING.json", "pass": True}, sort_keys=True))
