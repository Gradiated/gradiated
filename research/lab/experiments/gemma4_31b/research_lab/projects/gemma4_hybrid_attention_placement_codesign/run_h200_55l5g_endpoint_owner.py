#!/usr/bin/env python3
"""Durable controller for one later permanent-55L/5G H200 endpoint pair."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = "gemma4_hybrid_attention_placement_codesign"
REBIND = ROOT / "DIRECTOR_HYBRID_55L5G_RETIRED_BENCH_REBIND_20260727T0139Z.json"
EXTENSION_REQUEST = ROOT / "DIRECTOR_HYBRID_55L5G_LIFECYCLE_EXTENSION_REQUEST_20260727T0208Z.json"
PAIR = ROOT / "run_h200_55l5g_endpoint_pair.py"
SOURCE = ROOT / "extend_attention_hybrid_proxy.py"
TERMINAL = "HYBRID_55L5G_CURRENT_H200_ENDPOINT_TERMINAL.json"


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"json_object_required:{path}")
    return value


def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args],
        text=True, capture_output=True, check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT.parents[5] / "factory" / "src")},
    )


def read_inventory() -> dict[str, Any]:
    return load(LAB / "runtime" / "gpus.json")


def rows(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    value = inventory.get("benches", [])
    return list(value.values()) if isinstance(value, dict) else value


def rebind_contract() -> dict[str, Any]:
    value = load(REBIND)
    if not (
        value.get("project") == PROJECT
        and value.get("decision") == "repair_owner_for_future_live_bench_offline"
        and value.get("future_provider_gate", {}).get("create_allowed_in_this_turn") is False
        and value.get("budget", {}).get("cumulative_authorized_spend_usd") == 8.5
    ):
        raise RuntimeError("retired_bench_rebind_contract_invalid")
    return value


def extension_contract() -> dict[str, Any]:
    value = load(EXTENSION_REQUEST)
    if not (
        value.get("project") == PROJECT
        and value.get("decision") == "request_exact_reservation_before_watchdog_extension_and_claim"
        and value.get("reservation", {}).get("requested_cumulative_authorized_usd") == 10.0
        and value.get("reservation", {}).get("claim_allowed") is False
        and value.get("feasibility", {}).get("requested_deadline_utc") == "2026-07-27T03:10:00Z"
    ):
        raise RuntimeError("lifecycle_extension_request_contract_invalid")
    return value


def live_binding(path: Path, inventory: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    value, repair, extension = load(path), rebind_contract(), extension_contract()
    retired = repair["retired_bench"]
    bench = value.get("bench", {})
    lifecycle = value.get("lifecycle", {})
    watchdog = lifecycle.get("watchdog", {})
    resource = bench.get("resource", {})
    release_by = dt.datetime.fromisoformat(str(lifecycle.get("release_by_utc", "")).replace("Z", "+00:00"))
    required = ("id", "provider", "accelerator", "checkpoint_path", "checkpoint_manifest_digest", "image", "claim_generation")
    missing = [key for key in required if not bench.get(key)]
    if missing:
        raise RuntimeError(f"later_binding_missing_bench_fields:{','.join(missing)}")
    if not all(resource.get(key) for key in ("instance_id", "disk_id", "public_ipv4", "ssh_user", "known_hosts_namespace", "ssh_ed25519_fingerprint")):
        raise RuntimeError("later_binding_missing_ssh_identity")
    matched = next((row for row in rows(inventory) if row.get("id") == bench["id"]), None)
    identity_keys = ("instance_id", "disk_id", "public_ipv4", "ssh_user", "known_hosts_namespace", "ssh_ed25519_fingerprint")
    same_identity = matched and all(matched.get("resource", {}).get(key) == resource.get(key) for key in identity_keys)
    valid = (
        value.get("project") == PROJECT and value.get("claim_allowed") is True
        and value.get("reservation", {}).get("authorized_usd") == 10.0
        and value.get("reservation", {}).get("prior_actual_usd") == 6.3140021221
        and value.get("candidate_source_sha256") == digest(SOURCE)
        and value.get("owner_sha256") == digest(Path(__file__)) and value.get("pair_sha256") == digest(PAIR)
        and bench["id"] != retired["bench_id"] and resource["instance_id"] != retired["instance_id"]
        and resource["disk_id"] != retired["disk_id"] and matched is not None and same_identity
        and matched.get("status") == "available" and matched.get("claim") is None
        and matched.get("accelerator") == bench["accelerator"] == "nvidia-h200-sxm"
        and matched.get("provider") == bench["provider"] == "nebius"
        and lifecycle.get("watchdog_verified") is True
        and watchdog.get("deadline_utc") == extension["feasibility"]["requested_deadline_utc"]
        and matched.get("lifecycle", {}).get("watchdog") == watchdog.get("inventory_identity")
        and release_by > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=8)
        and str(matched.get("lifecycle", {}).get("deadline_utc", "")) >= lifecycle["release_by_utc"]
        and value.get("stock_launch_command") and value.get("candidate_activation_command") and value.get("pair_command")
    )
    if not valid:
        raise RuntimeError("later_live_nonretired_claim_binding_required")
    return value, matched


def heartbeat(stop: threading.Event, artifact: Path, bench_id: str) -> None:
    while not stop.wait(40):
        result = pool("heartbeat", "--project", PROJECT, "--bench", bench_id)
        atomic(artifact / "OWNER_HEARTBEAT.json", {"at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "returncode": result.returncode, "stderr": result.stderr[-1000:]})


def update_status(**changes: Any) -> None:
    status = load(ROOT / "STATUS.json")
    status.update(changes)
    atomic(ROOT / "STATUS.json", status)


def claim_time(output: str) -> str | None:
    match = re.search(r'"claimed_at"\s*:\s*"([^"]+)"', output)
    return match.group(1) if match else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--later-binding", type=Path, help="required future director claim binding")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    rebind_contract()
    if args.later_binding is None:
        print("later_live_nonretired_claim_binding_required", file=sys.stderr)
        return 2
    binding, bench = live_binding(args.later_binding, read_inventory())
    if args.preflight_only:
        print(json.dumps({"preflight": "pass", "bench_id": bench["id"], "claim_generation": binding["bench"]["claim_generation"]}, sort_keys=True))
        return 0
    artifact = (args.artifact_root or ROOT / "artifacts" / f"h200-55l5g-endpoint-{int(time.time())}").resolve()
    artifact.mkdir(parents=True, exist_ok=False)
    bench_id = bench["id"]
    claim = pool("claim", "--project", PROJECT, "--bench", bench_id)
    (artifact / "claim.stdout.log").write_text(claim.stdout)
    (artifact / "claim.stderr.log").write_text(claim.stderr)
    if claim.returncode:
        atomic(artifact / TERMINAL, {"classification": "atomic_claim_failed", "science_consumed": False, "candidate_cuda_invocation_started": False})
        return 2
    expected_claimed_at = claim_time(claim.stdout)
    update_status(active_session={
        "artifact_root": str(artifact), "bench_id": bench_id,
        "expected_claimed_at_utc": expected_claimed_at, "deadline_utc": binding["lifecycle"]["release_by_utc"],
        "expected_terminal": TERMINAL, "forward_progress": "claim complete; stock/candidate endpoint pair underway",
        "unit": os.environ["DETACHED_OWNER_STATE"], "pid": os.getpid(), "unit_manager": "pid",
    })
    stop = threading.Event()
    threading.Thread(target=heartbeat, args=(stop, artifact, bench_id), daemon=True).start()
    try:
        command = ["bash", "-lc", " && ".join(str(binding[key]) for key in ("stock_launch_command", "candidate_activation_command", "pair_command"))]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=float(binding["operation_timeout_seconds"]))
        (artifact / "owner.stdout.log").write_text(result.stdout)
        (artifact / "owner.stderr.log").write_text(result.stderr)
        terminal = load(Path(binding["retrieved_terminal_path"]))
        atomic(ROOT / TERMINAL, terminal)
        if terminal.get("classification") != "scientific_terminal":
            atomic(ROOT / "REPAIR_READY.json", {"schema_version": 1, "phase": "retained_repair", "failure": "invalid_or_unretrieved_endpoint_terminal", "science_consumed": False, "artifact_root": str(artifact), "expected_claimed_at_utc": expected_claimed_at})
            return 72
        contents = artifact / "BENCH_CONTENTS.json"
        atomic(contents, {"schema_version": 1, "project": PROJECT, "artifact": str(artifact), "expected_claimed_at_utc": expected_claimed_at, "server_state": "No experiment server or worker remains; checkpoint and pinned image retained."})
        released = pool("release", "--project", PROJECT, "--bench", bench_id, "--expected-claimed-at", expected_claimed_at or "", "--condition", "ready", "--contents", str(contents))
        (artifact / "release.stdout.log").write_text(released.stdout)
        (artifact / "release.stderr.log").write_text(released.stderr)
        update_status(active_session=None)
        return 0 if released.returncode == 0 else 72
    finally:
        stop.set()


if __name__ == "__main__":
    raise SystemExit(main())
