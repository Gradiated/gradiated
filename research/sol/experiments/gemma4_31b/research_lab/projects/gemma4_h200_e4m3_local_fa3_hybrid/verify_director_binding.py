#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BINDING = json.loads((HERE / "DIRECTOR_BINDING.json").read_text())

mixed_path = (HERE / BINDING["mixed_dependency_binding"]["path"]).resolve()
mixed = json.loads(mixed_path.read_text())
stack_path = (mixed_path.parent / mixed["authoritative_stack"]["path"]).resolve()
stack = json.loads(stack_path.read_text())
source_path = (HERE / BINDING["original_source_binding"]["path"]).resolve()
profile_path = (HERE / BINDING["profile"]["path"]).resolve()
source = json.loads(source_path.read_text())
profile = json.loads(profile_path.read_text())

assert hashlib.sha256(source_path.read_bytes()).hexdigest() == BINDING["original_source_binding"]["sha256"]
assert hashlib.sha256(profile_path.read_bytes()).hexdigest() == BINDING["profile"]["sha256"]
assert stack["model"] == "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4"
assert stack["runtime"]["commit"] == "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
assert stack["workload"]["requests"] == 32
assert stack["workload"]["concurrency"] == 32
assert source["status"] == "offline_binding_pass"
assert source["geometry"]["local"]["head_dim"] == 256
assert len(source["geometry"]["local"]["layer_ids"]) == 50
assert source["geometry"]["global"]["head_dim"] == 512
assert source["geometry"]["global"]["layer_ids"] == BINDING["candidate_change"]["global_layer_ids"]
assert BINDING["candidate_change"]["local_kv_cache_dtype"] == mixed["candidate_change"]["local_kv_cache_dtype"]
assert BINDING["candidate_change"]["global_kv_cache_dtype"] == mixed["candidate_change"]["global_kv_cache_dtype"]
boundaries = {row["boundary"]: row["wall_fraction"] for row in profile["boundaries"]}
assert boundaries["attention_kv"] >= BINDING["profile"]["local_attention_wall_fraction"]
print(json.dumps({"binding": "DIRECTOR_BINDING.json", "pass": True}, sort_keys=True))
