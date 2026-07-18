#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
MECHANISM = LAB / "projects" / "h100_w4_marlin_exact_shape_mechanism"
NEBIUS = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0, str(NEBIUS))

import mla_microbench_control as controller
from placement_control import list_items


IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUBLIC_KEY = KEY.with_suffix(".pub")
RATE = 2.15
DISK_RATE = 0.0097222


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def trigger(primary: dict[str, object]) -> bool:
    result = primary.get("result", {})
    return bool(
        primary.get("stage") == "primary"
        and primary.get("pass") is True
        and result.get("type") == "gemma4_h100_exact_shape_awq_machete_w4a16"
        and result.get("sentinel", {}).get("pass") is True
        and len(result.get("rows", [])) == 1
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    identity = json.loads(args.identity.read_text())
    packet = json.loads((PROJECT / "artifacts" / "MACHETE_DEVELOPMENT_PACKET.json").read_text())
    files = (
        PROJECT / "PROJECT.md", PROJECT / "assert_identity.py", PROJECT / "remote_sentinel.sh",
        PROJECT / "remote_sweep_profile_head.sh", PROJECT / "h100_w4_marlin_tp_single_rank.py",
        PROJECT / "h100_w4_marlin_owner.py", PROJECT / "launch_owner.py", args.identity,
        MECHANISM / "h100_w4_marlin_falsifier.py", MECHANISM / "h100_w4_contract.py",
        PROJECT / "artifacts" / "MACHETE_DEVELOPMENT_PACKET.json",
        NEBIUS / "mla_microbench_control.py", NEBIUS / "placement_control.py",
    )
    now = time.time()
    checks = {
        "durable_owner": bool(os.getenv("INVOCATION_ID")) and os.getenv("SYSTEMD_EXEC_PID") == str(os.getpid()),
        "name": bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", args.name)),
        "director_identity": identity.get("pass") is True,
        "packet": packet.get("execution_contract", {}).get("entrypoint") == "h100_w4_marlin_tp_single_rank.py" and packet.get("selected_kernel") == "MacheteLinearKernel" and packet.get("execution_contract", {}).get("repair_window_seconds") == 600,
        "terminal_binding": packet.get("terminal_sha256") == sha(PROJECT / packet.get("terminal_binding", "missing")),
        "packet_hashes": packet.get("files") == {
            "h100_w4_marlin_tp_single_rank.py": sha(PROJECT / "h100_w4_marlin_tp_single_rank.py"),
            "h100_w4_marlin_falsifier.py": sha(MECHANISM / "h100_w4_marlin_falsifier.py"),
            "h100_w4_contract.py": sha(MECHANISM / "h100_w4_contract.py"),
            "remote_sentinel.sh": sha(PROJECT / "remote_sentinel.sh"),
            "remote_sweep_profile_head.sh": sha(PROJECT / "remote_sweep_profile_head.sh"),
        },
        "files": all(path.is_file() for path in files),
        "keypair": KEY.is_file() and PUBLIC_KEY.is_file(),
        "inventory": not list_items("instance") and not list_items("disk"),
        "budget": (RATE + DISK_RATE) * 1200 / 3600 <= 1.3,
        "deadline": 0 < args.deadline_epoch - now <= 1200,
        "trigger_evaluator": trigger({"stage": "primary", "pass": True, "result": {"type": "gemma4_h100_exact_shape_awq_machete_w4a16", "sentinel": {"pass": True}, "rows": [{}]}}) and not trigger({"stage": "primary", "pass": False, "result": {"type": "gemma4_h100_exact_shape_awq_machete_w4a16", "sentinel": {"pass": True}, "rows": [{}]}}),
    }
    precreate = {
        "schema_version": 1,
        "type": "h100_w4_marlin_behavioral_precreate",
        "timestamp": dt.datetime.now(dt.UTC).isoformat(),
        "name": args.name,
        "checks": checks,
        "transitive_sha256": {str(path): sha(path) for path in files},
        "pass": all(checks.values()),
    }
    atomic(output / "PRECREATE_TERMINAL.json", precreate)
    if not precreate["pass"]:
        return 1
    controller.PLATFORM = "gpu-h100-sxm"
    controller.PRESET = "1gpu-16vcpu-200gb"
    controller.DISK_GIB = 100
    controller.HOURLY_RATE_USD = RATE
    controller.DISK_HOURLY_RATE_USD = DISK_RATE
    active = {
        "mode": "development",
        "unit": f"{args.name}.service",
        "unit_manager": "systemd --user",
        "owner_pid": os.getpid(),
        "name": args.name,
        "artifact_root": str(output),
        "deadline_epoch": args.deadline_epoch,
        "expected_terminal": "retrieved TP-initialized H100 AWQ-Marlin M8 discovery sentinel; then 24 exact rows and profiles; authenticated cleanup",
    }
    atomic(PROJECT / "STATUS.json", {
        "status": "active", "priority": 250, "researcher_profile": "execution",
        "summary": "Retained H100 W4 Machete development owner running TP-initialized sentinel-first program with a 600-second repair hold.",
        "next_action": "Reconcile retrieved typed terminal after authenticated cleanup.",
        "provider_mutation": "exclusive_durable_owner_only", "authorized_spend_usd": 1.3,
        "wall_clock_budget_minutes": 30, "provider_exposure_budget_minutes": 20,
        "compute_budget": "0.34 H100 GPU-hours plus 2 local CPU-hours",
        "storage_budget": "one 100-GiB provider disk; 1.5 GiB retained plus 768 MiB temporary",
        "active_session": active, "last_result_classification": "durable_h100_w4_marlin_owner_running",
        "terminal_artifact": None,
    })
    code = controller.run(
        output, args.name, KEY, PUBLIC_KEY, sha(args.identity),
        PROJECT / "remote_sentinel.sh", PROJECT / "h100_w4_marlin_tp_single_rank.py",
        (MECHANISM / "h100_w4_marlin_falsifier.py", MECHANISM / "h100_w4_contract.py"), "h100-w4-primary",
        max(1, int(args.deadline_epoch - time.time())), IMAGE,
        PROJECT / "remote_sweep_profile_head.sh", PROJECT / "h100_w4_marlin_tp_single_rank.py",
        (MECHANISM / "h100_w4_marlin_falsifier.py", MECHANISM / "h100_w4_contract.py", PROJECT / "h100_parallel_lm_head.py"),
        "h100-w4-conditional", trigger, repair_window_seconds=600,
    )
    summary_path = output / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {"outcome": "controller_observability_failure"}
    terminal = PROJECT / "artifacts" / "SUMMARY.json"
    terminal.parent.mkdir(parents=True, exist_ok=True)
    atomic(terminal, {
        "classification": "h100_w4_marlin_owner_terminal", "controller_returncode": code,
        "controller_summary": summary, "completed_at_utc": dt.datetime.now(dt.UTC).isoformat(),
    })
    atomic(PROJECT / "STATUS.json", {
        "status": "active", "priority": 250, "researcher_profile": "execution",
        "summary": "H100 W4-Marlin durable owner terminal requires reconciliation.",
        "next_action": "Reconcile typed sentinel/sweep/head disposition and authenticated cleanup.",
        "provider_mutation": "forbidden_pending_reconciliation", "authorized_spend_usd": 1.3,
        "active_session": None, "reconciliation_pending": True, "terminal_artifact": str(terminal),
        "last_result_classification": "h100_w4_marlin_owner_terminal",
    })
    return code


if __name__ == "__main__":
    raise SystemExit(main())
