#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import os
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
RUNNER = PROJECT / "packet/h100_matched_runner.py"
POSITIVE = PROJECT / "artifacts/h100-repair2-20260725t0709z/repair-consumer/retry/SERVER.log"
NEGATIVE = Path(__file__).with_name("negative_SERVER.log")
os.environ["UPSTREAM_REBASE_ROOT"] = str(PROJECT / "packet")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


spec = importlib.util.spec_from_file_location("h100_matched_runner", RUNNER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
positive = module.parse_h100_fit_log(POSITIVE.read_text())
try:
    module.parse_h100_fit_log(NEGATIVE.read_text())
except RuntimeError as exc:
    negative_error = str(exc)
else:
    raise AssertionError("negative fixture was accepted")

assert negative_error == "fit_log_field_missing:post_graph_available_gib"
assert positive["graph_gib"] == 1.06
assert positive["post_graph_available_gib"] == 10.63
assert positive["full_pool_tokens"] == 97361
assert positive["swa_pool_tokens"] == 77888
assert all(positive["gates"].values())
result = {
    "schema_version": 1,
    "runner": str(RUNNER.relative_to(PROJECT)),
    "positive_source": str(POSITIVE.relative_to(PROJECT)),
    "positive_source_sha256": sha256(POSITIVE),
    "positive": positive,
    "negative_fixture": str(NEGATIVE.relative_to(PROJECT)),
    "negative_fixture_sha256": sha256(NEGATIVE),
    "negative_result": {"accepted": False, "error": negative_error},
    "result": "pass",
}
print(json.dumps(result, sort_keys=True, indent=2))
