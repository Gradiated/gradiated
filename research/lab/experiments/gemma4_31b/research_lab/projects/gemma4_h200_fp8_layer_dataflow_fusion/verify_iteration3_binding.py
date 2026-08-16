#!/usr/bin/env python3
import hashlib
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
BINDING = json.loads((HERE / "ITERATION3_BINDING.json").read_text())


def bound(spec):
    path = (HERE / spec["path"]).resolve()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"]
    return path, json.loads(path.read_text()) if path.suffix == ".json" else None


_, stack = bound(BINDING["stack_binding"])
_, attribution = bound(BINDING["profile_attribution"])
sqlite_path, _ = bound(BINDING["profile_sqlite"])
_, control = bound(BINDING["control"])

assert stack["model"]["id"] == "google/gemma-4-31B-it"
assert stack["model"]["revision"] == "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
assert stack["runtime"]["commit"] == "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
assert stack["workload"] == {
    "concurrency": 32,
    "requests": 32,
    "prompt_tokens_per_request": 4214,
    "completion_tokens_per_request": 358,
    "cached_prompt_tokens_total": 17120,
    "fresh_prompt_tokens_total": 117728,
}
assert control["service_seconds_per_request"] == BINDING["control"]["service_seconds_per_request"]
assert any(row["boundary"] == "fp8_linear" for row in attribution["boundaries"])

db = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
row = db.execute(
    """select count(*), sum(k.end-k.start)/1e9
       from CUPTI_ACTIVITY_KIND_KERNEL k
       join StringIds s on s.id=k.shortName
       where s.value='per_token_quant_fp8_small_batch_kernel'"""
).fetchone()
assert row[0] == BINDING["profile_sqlite"]["per_token_quant_calls"]
assert abs(row[1] - BINDING["profile_sqlite"]["per_token_quant_total_seconds"]) < 1e-6
assert BINDING["profile_sqlite"]["predicted_candidate_calls"] == row[0] // 2
print(json.dumps({"binding": "ITERATION3_BINDING.json", "pass": True}, sort_keys=True))
