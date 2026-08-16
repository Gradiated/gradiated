#!/usr/bin/env python3
"""Durable retained-development owner for the c128 decode discriminator."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
SHARED = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0, str(SHARED))
import mla_microbench_control as controller
from placement_control import list_items, metadata_name


IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUBLIC_KEY = KEY.with_suffix(".pub")
RATE = 2.15
DISK_RATE = 0.01215275


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def set_status(value: dict) -> None:
    atomic(PROJECT / "STATUS.json", value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    inventory = {
        "instances": [metadata_name(item) for item in list_items("instance")],
        "disks": [metadata_name(item) for item in list_items("disk")],
    }
    inputs = (PROJECT / "decode_residual.py", PROJECT / "remote_stage.sh", PROJECT / "BINDINGS.json")
    maximum_seconds = max(0, args.deadline_epoch - time.time())
    checks = {
        "durable_owner": bool(os.getenv("INVOCATION_ID")) and os.getenv("SYSTEMD_EXEC_PID") == str(os.getpid()),
        "lowercase_name": bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", args.name)),
        "empty_inventory": not inventory["instances"] and not inventory["disks"],
        "inputs": all(path.is_file() for path in inputs),
        "bound_project": json.loads((PROJECT / "BINDINGS.json").read_text()).get("pass") is True,
        "keypair": KEY.is_file() and PUBLIC_KEY.is_file(),
        "deadline": 0 < maximum_seconds <= 2700,
        "budget": (RATE + DISK_RATE) * maximum_seconds / 3600 <= 1.8,
    }
    binding = {
        "schema_version": 1,
        "type": "h100_c128_decode_residual_precreate",
        "checks": checks,
        "inventory": inventory,
        "inputs": {path.name: digest(path) for path in inputs},
        "pass": all(checks.values()),
    }
    atomic(output / "PRECREATE.json", binding)
    if not binding["pass"]:
        set_status({
            "status": "active", "priority": 360, "researcher_profile": "deep",
            "summary": "Provider create denied by the grouped mutable pre-create gate.",
            "next_action": "Interpret PRECREATE.json and repair only an ordinary local defect in place.",
            "provider_mutation": "denied_typed_precreate", "authorized_spend_usd": 1.8,
            "active_session": None, "last_result_classification": "typed_precreate_blocker",
            "terminal_artifact": str(output / "PRECREATE.json"),
        })
        return 1
    controller.PLATFORM = "gpu-h100-sxm"
    controller.PRESET = "1gpu-16vcpu-200gb"
    controller.DISK_GIB = 100
    controller.HOURLY_RATE_USD = RATE
    controller.DISK_HOURLY_RATE_USD = DISK_RATE
    active = {
        "mode": "development",
        "unit": os.getenv("SYSTEMD_UNIT") or f"{args.name}.service",
        "unit_manager": "systemd --user",
        "owner_pid": os.getpid(),
        "name": args.name,
        "artifact_root": str(output),
        "deadline_epoch": args.deadline_epoch,
        "repair_window_seconds": 600,
        "resource_identity": "pending authenticated H100 SXM instance bind",
        "watchdog": "shared controller will bind an independent named-instance cleanup watchdog after create",
        "expected_terminal": "valid c128 FP8-KV/local-global-attention/scheduler-launch discriminator, or typed failure plus authenticated zero-resource cleanup",
        "forward_progress": "grouped pre-create identity, spend, inventory, controller, and program gates passed; entering create/bootstrap",
    }
    set_status({
        "status": "active", "priority": 360, "researcher_profile": "deep",
        "summary": "One retained H100 development owner is running the c128 decode residual discriminator.",
        "next_action": "Attach for ordinary repair if the first typed stage fails; otherwise reconcile measurement and cleanup.",
        "provider_mutation": "exclusive_durable_owner_only", "authorized_spend_usd": 1.8,
        "wall_clock_budget_minutes": 75, "provider_exposure_budget_minutes": 45,
        "compute_budget": "4 CPU-hours; 0.75 H100 GPU-hours", "active_session": active,
        "last_result_classification": "durable_h100_c128_decode_discriminator_running",
    })
    code = controller.run(
        output,
        args.name,
        KEY,
        PUBLIC_KEY,
        digest(PROJECT / "BINDINGS.json"),
        PROJECT / "remote_stage.sh",
        PROJECT / "decode_residual.py",
        (PROJECT / "BINDINGS.json", output / "PRECREATE.json"),
        "h100-w4-decode-residual-c128",
        max(1, int(args.deadline_epoch - time.time())),
        IMAGE,
        repair_window_seconds=600,
    )
    summary = json.loads((output / "summary.json").read_text()) if (output / "summary.json").is_file() else {"outcome": "controller_observability_failure"}
    atomic(output / "OWNER_TERMINAL.json", {
        "controller_returncode": code,
        "summary": summary,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    })
    set_status({
        "status": "active", "priority": 360, "researcher_profile": "deep",
        "summary": "The retained development owner reached a terminal; science and cleanup require reconciliation.",
        "next_action": "Reconcile OWNER_TERMINAL.json and the retrieved c128 stage archive.",
        "provider_mutation": "forbidden_pending_reconciliation", "authorized_spend_usd": 1.8,
        "active_session": None, "reconciliation_pending": True,
        "terminal_artifact": str(output / "OWNER_TERMINAL.json"),
        "last_result_classification": "h100_c128_decode_owner_terminal",
    })
    return code


if __name__ == "__main__":
    raise SystemExit(main())
