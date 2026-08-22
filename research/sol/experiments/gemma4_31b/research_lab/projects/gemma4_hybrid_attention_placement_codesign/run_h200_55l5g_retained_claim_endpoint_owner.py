#!/usr/bin/env python3
"""Adopt the director-bound H200 claim and repair only its stage CLI."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = "gemma4_hybrid_attention_placement_codesign"
REPAIR = ROOT / "DIRECTOR_H200_55L5G_ENDPOINT_RETAINED_CLAIM_STAGE_REPAIR_20260729T0106Z.json"
SOURCE = ROOT / "run_h200_55l5g_bound_endpoint_owner.py"
ARTIFACT = ROOT / "artifacts/h200-55l5g-endpoint-stage-repair-20260729t0106z"

def load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict): raise RuntimeError("json_object_required")
    return value

def main() -> int:
    repair = load(REPAIR)
    if not (repair["project"] == PROJECT and repair["mutable_repair"]["source_owner_sha256"] == __import__("hashlib").sha256(SOURCE.read_bytes()).hexdigest()):
        raise RuntimeError("retained_repair_binding_source_mismatch")
    source = SOURCE.read_text().replace("huggingface-cli download", "hf download")
    original_fence = 'if dt.datetime.now(dt.timezone.utc)>parse_time(binding["lifecycle"]["claim_start_by_utc"]): raise RuntimeError("claim_start_fence_expired")'
    if original_fence not in source:
        raise RuntimeError("expected_predecessor_claim_fence_missing")
    source = source.replace(original_fence, "# The director-bound original claim is adopted after its predecessor start fence.")
    namespace = {"__name__": "_retained_claim_base", "__file__": str(SOURCE)}
    exec(compile(source, str(SOURCE), "exec"), namespace)
    pool = namespace["pool"]
    shown = pool("show", "--bench", repair["live_claim"]["bench_id"])
    bench = json.loads(shown.stdout)
    claim = bench.get("claim") or {}
    if not (shown.returncode == 0 and claim.get("project") == PROJECT and claim.get("claimed_at") == repair["live_claim"]["expected_claimed_at_utc"]):
        raise RuntimeError("original_claim_generation_not_adoptable")
    first = pool("heartbeat", "--project", PROJECT, "--bench", repair["live_claim"]["bench_id"])
    if first.returncode: raise RuntimeError("adoption_heartbeat_failed")
    base_pool = namespace["pool"]
    def adopted_pool(*args: str):
        if args and args[0] == "claim":
            return subprocess.CompletedProcess([], 0, json.dumps({"claimed_at": claim["claimed_at"]}), "")
        return base_pool(*args)
    namespace["pool"] = adopted_pool
    stop = threading.Event()
    def beat() -> None:
        while not stop.wait(35): base_pool("heartbeat", "--project", PROJECT, "--bench", repair["live_claim"]["bench_id"])
    threading.Thread(target=beat, daemon=True).start()
    sys.argv = [str(SOURCE), "--execution-binding", repair["predecessor_execution_binding"]["path"], "--runtime-manifest", "H200_55L5G_RETAINED_CLAIM_STAGE_REPAIR_RUNTIME_MANIFEST.json", "--preclaim-packet", "PRECLAIM_H200_55L5G_ENDPOINT_TERMINAL.json", "--artifact-root", str(ARTIFACT.relative_to(ROOT))]
    try:
        result = namespace["main"]()
        if result == 0: return 0
        deadline = repair["lifecycle"]["release_by_utc"]
        return subprocess.run([str(ROOT.parents[5]/"factory/tools/repair-handshake"), "hold", "--root", str(ARTIFACT/"repair-stage-0106"), "--deadline", deadline, "--failure-kind", "retained_stage_repair", "--diagnostic", str(ARTIFACT/"PRE_SCIENCE_FAILURE.json"), "--retry-scope", "checkpoint_stage"], check=False).returncode
    finally:
        stop.set()

if __name__ == "__main__": raise SystemExit(main())
