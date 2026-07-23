#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BINDING = json.loads((HERE / "DIRECTOR_BINDING.json").read_text())
DIRECT = json.loads((HERE / BINDING["dependency_project"] / "DIRECTOR_BINDING.json").resolve().read_text())
PROFILE_PATH = (HERE / BINDING["profile"]["path"]).resolve()
PROFILE = json.loads(PROFILE_PATH.read_text())
SUPPORT_PATH = (HERE / BINDING["backend_support"]["path"]).resolve()

assert hashlib.sha256(PROFILE_PATH.read_bytes()).hexdigest() == BINDING["profile"]["sha256"]
assert hashlib.sha256(SUPPORT_PATH.read_bytes()).hexdigest() == BINDING["backend_support"]["sha256"]
assert DIRECT["model"] == BINDING["model"]
assert DIRECT["checkpoint_index_sha256"] == BINDING["checkpoint_index_sha256"]
assert DIRECT["runtime"] == BINDING["runtime"]
assert DIRECT["workload"] == BINDING["workload"]
boundaries = {row["boundary"]: row["wall_fraction"] for row in PROFILE["boundaries"]}
assert BINDING["profile"]["local_attention_wall_fraction"] == 0.1531203203096733
assert boundaries["attention_kv"] >= BINDING["profile"]["local_attention_wall_fraction"]
assert BINDING["local_geometry"] == {
    "layers": 50,
    "sliding_window_tokens": 1024,
    "query_heads": 32,
    "kv_heads": 16,
    "head_dim": 256,
    "candidate_kv_dtype": "fp8_e4m3",
    "candidate_backend": "fa3",
}
assert BINDING["global_geometry"]["head_dim"] == 512
assert BINDING["global_geometry"]["backend"] == "triton"
print(json.dumps({"pass": True, "binding": "DIRECTOR_BINDING.json"}, sort_keys=True))
