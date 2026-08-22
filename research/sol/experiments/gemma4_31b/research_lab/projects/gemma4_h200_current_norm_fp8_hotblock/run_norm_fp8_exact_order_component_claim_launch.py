#!/usr/bin/env python3
"""Atomically claim, then hand the exact generation to a durable owner."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
LAB = HERE.parents[1]
PROJECT = "gemma4_h200_current_norm_fp8_hotblock"
POOL = ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
DETACHED = "/root/workspace/research/factory/tools/detached-owner"


def atomic(path: pathlib.Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    json.loads(part.read_text()); os.replace(part, path)


def command(args: list[str], timeout: int = 60) -> str:
    done = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if done.returncode: raise RuntimeError(done.stderr[-1200:] or done.stdout[-1200:])
    return done.stdout


def release_claim(bench_id: str, claimed_at: str, root: pathlib.Path, reason: str) -> None:
    contents = root / "PRE_ADOPTION_RELEASE.json"
    atomic(contents, {"project": PROJECT, "claim_generation": claimed_at, "reason": reason})
    command([*POOL, "release", "--project", PROJECT, "--bench", bench_id, "--expected-claimed-at", claimed_at, "--condition", "maintenance", "--contents", str(contents)])


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--execution-spec", type=pathlib.Path, required=True); parser.add_argument("--artifact-root", type=pathlib.Path, required=True); args = parser.parse_args()
    spec, root = json.loads(args.execution_spec.read_text()), args.artifact_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    fence = dt.datetime.fromisoformat(spec["lifecycle"]["claim_start_by_utc"].replace("Z", "+00:00"))
    if dt.datetime.now(dt.timezone.utc) > fence: raise RuntimeError("director_claim_start_fence_expired")
    if spec["project"] != PROJECT or spec["bench"]["required_state"] != "available": raise RuntimeError("unexpected_director_binding")
    for identity in spec["immutable_inputs"].values():
        if isinstance(identity, dict) and "path" in identity:
            path = HERE / identity["path"]
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != identity["sha256"]: raise RuntimeError(f"repairable_binding_metadata_digest_mismatch:{identity['path']}")
    bench_id, claimed_at, adopted = spec["bench"]["id"], None, False
    try:
        command([*POOL, "claim", "--project", PROJECT, "--bench", bench_id, "--lease-seconds", "2400"])
        shown = json.loads(command([*POOL, "show", "--bench", bench_id])); claim = shown.get("claim") or {}
        if claim.get("project") != PROJECT or not claim.get("claimed_at"): raise RuntimeError("claim_not_observed_after_atomic_claim")
        claimed_at = claim["claimed_at"]
        binding = {"schema_version": 1, "execution_spec": str(args.execution_spec.resolve()), "execution_spec_sha256": hashlib.sha256(args.execution_spec.read_bytes()).hexdigest(), "claimed_at": claimed_at, "bench": shown, "artifact_root": str(root), "absolute_release_deadline_utc": spec["lifecycle"]["absolute_release_deadline_utc"], "maximum_claim_seconds": spec["lifecycle"]["maximum_claim_seconds"]}
        binding_path, ready_file, state = root / "EXECUTION_BINDING.json", root / "OWNER_READY.json", root / "DETACHED_OWNER.json"
        atomic(binding_path, binding)
        launched = json.loads(command([DETACHED, "start", "--unit-manager", "pid", "--state", str(state), "--log", str(root / "OWNER.log"), "--cwd", str(HERE), "--ready-file", str(ready_file), "--stabilize-seconds", "30", "--", sys.executable, str(HERE / "run_norm_fp8_exact_order_component_owner.py"), "--binding", str(binding_path), "--ready-file", str(ready_file)], 45))
        if not launched.get("live") or not launched.get("ready"): raise RuntimeError("durable_owner_did_not_cross_runtime_gate")
        adopted = True
        status_path = HERE / "STATUS.json"; status = json.loads(status_path.read_text())
        status["active_session"] = {"artifact_root": str(root), "deadline_utc": binding["absolute_release_deadline_utc"], "expected_terminal": "TERMINAL.json", "forward_progress": "owner_adopted; immutable_staging_pending", "pid": launched["pid"], "start_ticks": launched["start_ticks"], "unit": str(state), "unit_manager": "pid"}
        atomic(status_path, status)
        print(json.dumps({"claimed_at": claimed_at, "owner_state": str(state), "pid": launched["pid"]}, sort_keys=True))
        return 0
    except Exception as error:
        if claimed_at and not adopted:
            release_claim(bench_id, claimed_at, root, f"pre_owner_adoption:{error}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
