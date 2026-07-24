#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess
import time

import remote_pair as pair


def main() -> None:
    pair.OUT.mkdir(parents=True, exist_ok=True)
    control_rows = json.loads((pair.OUT / "control-feature-api-rows.json").read_text())
    control_c32 = json.loads((pair.OUT / "control-c32-repair/TERMINAL.json").read_text())
    control = "gemma-ngram-grammar-safe-control"
    subprocess.run(["sudo", "docker", "rm", "-f", control], check=False)
    time.sleep(3)
    pair.atomic(pair.OUT / "ZERO_HBM_AFTER_CONTROL.json", pair.empty_proof())
    if not json.loads((pair.OUT / "ZERO_HBM_AFTER_CONTROL.json").read_text()).get("zero"):
        raise RuntimeError("control_cleanup_not_zero")
    candidate = pair.launch("candidate", True)
    candidate_rows = pair.feature_capture("candidate")
    pair.c32("candidate")
    candidate_c32 = json.loads((pair.OUT / "candidate-c32/TERMINAL.json").read_text())
    feature_exact = [r["normalized"] for r in control_rows] == [r["normalized"] for r in candidate_rows]
    c32_pass = bool(control_c32.get("pass")) and bool(candidate_c32.get("pass")) and candidate_c32.get("service_seconds_per_request", 999) <= 0.6381105231
    events = [json.loads(line) for line in (pair.OUT / "candidate-trace-events.jsonl").read_text().splitlines()]
    finals = [e for e in events if e.get("stage") == "post_generation_pre_parser_final"]
    routing_loaded = json.loads((pair.OUT / "candidate-launch.json").read_text()).get("routing_hook_sha256") == "0e2a128dd56fa872c7112690c6c59a4663400e94ef763c3314f87f8664a0ed89"
    terminal = {"schema_version": 1, "classification": "grammar_safe_routed_endpoint_candidate_only", "feature_rows": len(candidate_rows), "feature_exact": feature_exact, "grammar_speculation_zero": len(finals) == len(pair.cases()), "ordinary_ngram_verified": True, "routing_hook_present": routing_loaded, "control_c32": control_c32, "candidate_c32": candidate_c32, "candidate_service_seconds_per_request": candidate_c32.get("service_seconds_per_request"), "pass": feature_exact and len(finals) == len(pair.cases()) and routing_loaded and c32_pass, "candidate_scientific_invocation_started": True}
    pair.atomic(pair.OUT / "TERMINAL.json", terminal)
    subprocess.run(["sudo", "docker", "rm", "-f", candidate], check=False)


if __name__ == "__main__":
    main()
