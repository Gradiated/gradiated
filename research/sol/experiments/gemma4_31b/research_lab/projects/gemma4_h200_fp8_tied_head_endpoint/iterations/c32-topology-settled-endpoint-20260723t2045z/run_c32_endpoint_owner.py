#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import datetime as dt
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
SOURCE = PROJECT_ROOT / "iterations/graph-bound-endpoint-20260723t1930z"

spec = importlib.util.spec_from_file_location("prior_owner", SOURCE / "run_graph_endpoint_owner.py")
if spec is None or spec.loader is None:
    raise SystemExit("prior_owner_unavailable")
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)

owner.HERE = HERE
owner.ARTIFACTS = HERE / "artifacts"
owner.REMOTE = "/dev/shm/gemma4-fp8-tied-head-topology-settled"
owner.PRIOR_SPEND_USD = 1.0574816349999998
owner.ABSOLUTE_DEADLINE = dt.datetime(2026, 7, 23, 23, 30, tzinfo=dt.timezone.utc)
owner.PRIOR_FINAL_SHA256 = hashlib.sha256((SOURCE / "artifacts/FINAL_TERMINAL.json").read_bytes()).hexdigest()
owner.PRIOR_ARTIFACT_TREE_SHA256 = owner.tree_sha256(SOURCE / "artifacts")

def validate_inputs() -> None:
    result = subprocess.run([sys.executable, str(PROJECT_ROOT / "verify_director_binding.py")], text=True, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"director_binding_invalid:{result.stderr[-1000:]}")
    decision = HERE / "SETTLED_TOPOLOGY_DECISION.json"
    if hashlib.sha256(decision.read_bytes()).hexdigest() != "0e440a731a4997b4c6ae35884f4e432b789d1f1d82257785f72f424b1935b9be":
        raise RuntimeError("settled_topology_decision_mutated")
    for relative, expected in owner.INPUT_SHA256.items():
        actual = owner.sha256(SOURCE / relative)
        if actual != expected:
            raise RuntimeError(f"project_local_snapshot_invalid:{relative}:{actual}")

def stage(ip: str) -> None:
    prepared = owner.remote(ip, f"rm -rf {owner.REMOTE}.stage && mkdir -p {owner.REMOTE}.stage", 60)
    if prepared.returncode:
        raise RuntimeError(f"remote_stage_prepare_failed:{prepared.stderr[-1000:]}")
    owner.scp_to(ip, SOURCE / "inputs", f"{owner.REMOTE}.stage/input", recursive=True)
    owner.scp_to(ip, HERE / "remote_c32_endpoint.sh", f"{owner.REMOTE}.stage/remote_graph_endpoint.sh")
    finalized = owner.remote(ip, f"rm -rf {owner.REMOTE}.previous && if test -d {owner.REMOTE}; then mv {owner.REMOTE} {owner.REMOTE}.previous; fi && mv {owner.REMOTE}.stage {owner.REMOTE}", 60)
    if finalized.returncode:
        raise RuntimeError(f"remote_stage_finalize_failed:{finalized.stderr[-1000:]}")

owner.validate_inputs = validate_inputs
owner.stage = stage
raise SystemExit(owner.main())
