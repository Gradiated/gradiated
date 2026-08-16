#!/usr/bin/env python3
"""Single bounded owner for the final Gemma tool-consumer gate."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import threading
import time

import run_production_quality_recovery_outer as base

LAB = base.LAB
PROJECT = base.PROJECT
FACTORY = base.FACTORY
PROJECT_NAME = base.PROJECT_NAME
BENCH = base.BENCH
REMOTE = base.REMOTE
IMAGE = base.IMAGE
MODEL = base.MODEL
RATE = base.RATE


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--artifact-root", type=pathlib.Path, required=True); ap.add_argument("--absolute-deadline-epoch", type=int, required=True); ap.add_argument("--unit", required=True); args = ap.parse_args()
    if not os.getenv("INVOCATION_ID"): raise RuntimeError("durable_user_systemd_owner_required")
    root = args.artifact_root.resolve(); root.mkdir(parents=True, exist_ok=False); events = root / "events.jsonl"
    status_path = PROJECT / "STATUS.json"; status = json.loads(status_path.read_text()); claimed = False; scientific_started = False; terminal = None; started = time.time(); stop_hb = threading.Event(); ip = None

    def event(name: str, **fields: object) -> None:
        with events.open("a") as f: f.write(json.dumps({"timestamp": now(), "event": name, **fields}, sort_keys=True) + "\n")

    status["active_session"] = {"unit": args.unit, "unit_manager": "user", "pid": os.getpid(), "artifact_root": str(root), "deadline_utc": dt.datetime.fromtimestamp(args.absolute_deadline_epoch, dt.timezone.utc).isoformat().replace("+00:00", "Z"), "expected_terminal": "TERMINAL.json", "started_at_utc": now(), "forward_progress": "claim_pending"}
    base.atomic(status_path, status)

    def heartbeat() -> None:
        while not stop_hb.wait(45):
            result = base.pool("heartbeat", "--project", PROJECT_NAME, check=False); event("heartbeat", returncode=result.returncode)

    hb = threading.Thread(target=heartbeat, daemon=True)
    try:
        inventory = json.loads((LAB / "runtime/gpus.json").read_text()); benches = inventory["benches"]; bench = benches.get(BENCH) if isinstance(benches, dict) else next(x for x in benches if x["id"] == BENCH)
        if bench.get("status") != "available": raise RuntimeError("bench_not_available")
        if time.time() + 15 * 60 >= args.absolute_deadline_epoch: raise RuntimeError("retrieval_reserve_deadline")
        claim = base.pool("claim", "--project", PROJECT_NAME, "--bench", BENCH, "--lease-seconds", str(min(3300, args.absolute_deadline_epoch - int(time.time()))))
        claimed = True; event("claimed", claim=json.loads(claim.stdout)); status["active_session"]["forward_progress"] = "bench_claimed"; base.atomic(status_path, status); hb.start()
        sys.path.insert(0, str(base.TOOLS)); from placement_control import extract_public_ipv4, get_instance
        provider = get_instance(bench["resource"]["instance_id"]); ip = extract_public_ipv4(provider)
        if not ip: raise RuntimeError("public_ip_unavailable")
        ident = base.remote(ip, "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader", 90); (root / "remote-identity.stdout").write_text(ident.stdout); (root / "remote-identity.stderr").write_text(ident.stderr)
        if ident.returncode: raise RuntimeError("remote_identity_failed")
        check = base.remote(ip, f"test \"$(sha256sum {REMOTE}/checkpoint/model.safetensors.index.json | awk '{{print $1}}')\" = d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2 && sudo docker image inspect {IMAGE} >/dev/null", 180)
        if check.returncode: raise RuntimeError("resident_identity_failed")
        status["active_session"]["forward_progress"] = "resident_identity_verified"; base.atomic(status_path, status)
        base.remote(ip, f"mkdir -p {REMOTE}/quality-input {REMOTE}/quality-artifacts/tool-bridge-run", 60)
        stage = [PROJECT / "tool_bridge_worker.py", PROJECT / "tool_bridge_bindings.json", PROJECT / "assets/requests/taubench_requests.jsonl", PROJECT.parent / "gemma4_h200_qkv_epilogue_fusion/proven_v0513_endpoint_entrypoint.py"]
        for source in stage: base.upload(ip, source, f"{REMOTE}/quality-input/{source.name}")
        staged = base.remote(ip, f"sha256sum {REMOTE}/quality-input/tool_bridge_worker.py {REMOTE}/quality-input/tool_bridge_bindings.json {REMOTE}/quality-input/taubench_requests.jsonl", 90); (root / "staged-hashes.txt").write_text(staged.stdout + staged.stderr)
        if staged.returncode: raise RuntimeError("staged_hash_check_failed")
        status["active_session"]["forward_progress"] = "consumer_staged"; base.atomic(status_path, status)
        worker_timeout = max(60, args.absolute_deadline_epoch - int(time.time()) - 600)
        worker = base.remote(ip, f"timeout --signal=TERM {worker_timeout} python3 {REMOTE}/quality-input/tool_bridge_worker.py --artifact-root {REMOTE}/quality-artifacts/tool-bridge-run", worker_timeout + 60)
        (root / "worker.stdout").write_text(worker.stdout); (root / "worker.stderr").write_text(worker.stderr); event("worker_complete", returncode=worker.returncode)
        retrieved = root / "remote-tool-bridge"; base.retrieve(ip, f"{REMOTE}/quality-artifacts/tool-bridge-run", retrieved, recursive=True, timeout=1200)
        marker = retrieved / "INVOCATION_STATE.json"; scientific_started = marker.exists() and json.loads(marker.read_text()).get("bf16_scientific_started", False)
        if (retrieved / "SENTINEL_TERMINAL.json").is_file(): terminal = json.loads((retrieved / "SENTINEL_TERMINAL.json").read_text())
        else: terminal = {"schema_version": 1, "classification": "consumer_terminal_missing", "pass": False, "scientific_invocation_started": scientific_started}
        terminal["provider_exposure_seconds"] = time.time() - started; terminal["provider_spend_usd"] = terminal["provider_exposure_seconds"] * RATE / 3600; terminal["project_cumulative_spend_usd"] = 1.753897390753883 + terminal["provider_spend_usd"]
        base.atomic(root / "TERMINAL.json", terminal); event("terminal_persisted", classification=terminal.get("parser_mode", terminal.get("classification")), passed=terminal.get("gate_pass", terminal.get("pass")))
        return 0 if terminal.get("gate_pass", terminal.get("pass")) else 1
    except Exception as exc:
        terminal = {"schema_version": 1, "classification": "owner_failure", "pass": False, "error": {"type": type(exc).__name__, "message": str(exc)[:4000]}, "scientific_invocation_started": scientific_started, "provider_exposure_seconds": time.time() - started if claimed else 0}
        terminal["provider_spend_usd"] = terminal["provider_exposure_seconds"] * RATE / 3600; base.atomic(root / "TERMINAL.json", terminal); event("outer_error", error=str(exc)); return 1
    finally:
        stop_hb.set()
        if hb.is_alive(): hb.join(timeout=5)
        if claimed:
            contents = root / "BENCH_CONTENTS.json"; base.atomic(contents, {"project": PROJECT_NAME, "model": MODEL, "checkpoint": f"Exact immutable checkpoint retained at {REMOTE}/checkpoint.", "image": f"SGLang v0.5.13 image {IMAGE}.", "runtime": "Final Gemma tool-consumer sentinel terminal retrieved project-locally.", "caches": "SGLang v0.5.13 and CUDA graph caches retained.", "server_state": "No tool-gate server retained; checkpoint/image/caches retained.", "artifacts": "Sentinel raw/normalized responses and existing TauBench rescoring retrieved project-locally."})
            release = base.pool("release", "--project", PROJECT_NAME, "--condition", "ready", "--contents", str(contents), check=False); event("released", returncode=release.returncode)
        status = json.loads(status_path.read_text()); status["active_session"] = None; base.atomic(status_path, status)


if __name__ == "__main__": raise SystemExit(main())
