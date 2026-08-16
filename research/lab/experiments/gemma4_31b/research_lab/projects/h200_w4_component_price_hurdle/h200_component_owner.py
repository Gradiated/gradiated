#!/usr/bin/env python3
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
SOURCE = PROJECT.parent / "h100_w4_background_concurrency_frontier"
DEPENDENCIES = PROJECT.parent
NEBIUS = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0, str(NEBIUS))
import mla_microbench_control as controller
from placement_control import list_items


KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUBLIC_KEY = KEY.with_suffix(".pub")
RATE, DISK_RATE, TIMEOUT = 2.45, 0.0097222, 1800


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_bindings() -> dict[str, bool]:
    bindings = json.loads((PROJECT / "BINDINGS.json").read_text())
    result = {"binding_pass": bindings.get("pass") is True}
    for name, entry in bindings["proven_program"].items():
        result[f"proven_{name}"] = digest(PROJECT / entry["path"]) == entry["sha256"]
    terminal = bindings["comparison"]["h100_terminal"]
    result["h100_terminal"] = digest(PROJECT / terminal["path"]) == terminal["sha256"]
    result["placement"] = bindings["target_hardware"] == {"accelerator_id": "nvidia-h200-sxm", "provider_platform": "gpu-h200-sxm", "provider_preset": "1gpu-16vcpu-200gb", "experimental_rate_usd_per_gpu_hour": RATE, "production_planning_usd_per_gpu_hour": 3.25, "price_hurdle_vs_h100": 1.160714286}
    return result


def trigger(primary: dict[str, object]) -> bool:
    result = primary.get("result", {})
    return bool(primary.get("stage") == "primary" and primary.get("pass") is True and result.get("type") == "gemma4_h200_w4_machete_component_frontier" and result.get("all_actual_consumers_pass") is True and result.get("numerical_sentinel", {}).get("pass") is True and len(result.get("rows", [])) == 12)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output-dir", type=Path, required=True); parser.add_argument("--name", required=True); parser.add_argument("--deadline-epoch", type=float, required=True); args = parser.parse_args()
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=False); now = time.time()
    stage = SOURCE / "remote_frontier_stage.sh"
    dependency_files = (DEPENDENCIES / "h100_w4_marlin_direct_falsifier" / "h100_w4_marlin_tp_single_rank.py", DEPENDENCIES / "h100_w4_marlin_exact_shape_mechanism" / "h100_w4_marlin_falsifier.py", DEPENDENCIES / "h100_w4_marlin_exact_shape_mechanism" / "h100_w4_contract.py")
    files = (PROJECT / "w4_h200_frontier.py", PROJECT / "head_h200_frontier.py", PROJECT / "h200_component_owner.py", PROJECT / "launch_h200_owner.py", PROJECT / "BINDINGS.json", stage, *dependency_files)
    binding_checks = verify_bindings()
    checks = {"durable_owner": bool(os.getenv("INVOCATION_ID")) and os.getenv("SYSTEMD_EXEC_PID") == str(os.getpid()), "name": bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", args.name)), "files": all(path.is_file() for path in files), "keypair": KEY.is_file() and PUBLIC_KEY.is_file(), "inventory": not list_items("instance") and not list_items("disk"), "deadline": 0 < args.deadline_epoch - now <= TIMEOUT, "budget": (RATE + DISK_RATE) * TIMEOUT / 3600 <= 1.5, "bindings": all(binding_checks.values()), "trigger_fixture": trigger({"stage": "primary", "pass": True, "result": {"type": "gemma4_h200_w4_machete_component_frontier", "all_actual_consumers_pass": True, "numerical_sentinel": {"pass": True}, "rows": [{}] * 12}}) and not trigger({"stage": "primary", "pass": False, "result": {}})}
    atomic(output / "PRECREATE_TERMINAL.json", {"schema_version": 1, "type": "h200_w4_component_price_hurdle_precreate", "timestamp": dt.datetime.now(dt.UTC).isoformat(), "checks": checks, "binding_checks": binding_checks, "files": {str(path): digest(path) for path in files}, "pass": all(checks.values())})
    if not all(checks.values()):
        return 1
    controller.PLATFORM = "gpu-h200-sxm"; controller.PRESET = "1gpu-16vcpu-200gb"; controller.DISK_GIB = 100; controller.HOURLY_RATE_USD = RATE; controller.DISK_HOURLY_RATE_USD = DISK_RATE
    atomic(PROJECT / "STATUS.json", {"status": "active", "priority": 340, "researcher_profile": "execution", "summary": "Retained H200 development owner runs a numerical W4 Machete sentinel, matched c96/c128 W4 rows, then actual ParallelLMHead c96/c128 rows.", "next_action": "Attach to this owner; repair the first ordinary remote failure in place, or reconcile retrieved typed rows and authenticated cleanup.", "provider_mutation": "exclusive_durable_owner_only", "authorized_spend_usd": 1.5, "wall_clock_budget_minutes": 45, "provider_exposure_budget_minutes": 30, "compute_budget": "0.50 H200 GPU-hours", "storage_budget": "one 100-GiB provider disk; 2 GiB retrieved artifacts; no model checkpoint transfer", "repair_window_seconds": 600, "bindings": "BINDINGS.json", "active_session": {"mode": "development", "unit": f"{args.name}.service", "unit_manager": "systemd --user", "owner_pid": os.getpid(), "name": args.name, "artifact_root": str(output), "deadline_epoch": args.deadline_epoch, "expected_terminal": "typed H200 W4 numerical sentinel and c96/c128 rows, conditional actual ParallelLMHead c96/c128 rows, authenticated cleanup"}})
    code = controller.run(output, args.name, KEY, PUBLIC_KEY, digest(PROJECT / "BINDINGS.json"), stage, PROJECT / "w4_h200_frontier.py", dependency_files, "h200-w4-primary", max(1, int(args.deadline_epoch - time.time())), IMAGE := json.loads((PROJECT / "BINDINGS.json").read_text())["runtime_image"], stage, PROJECT / "head_h200_frontier.py", (), "h200-head", trigger, repair_window_seconds=600)
    summary = json.loads((output / "summary.json").read_text()) if (output / "summary.json").is_file() else {"outcome": "controller_observability_failure"}
    terminal = PROJECT / "artifacts" / "OWNER_TERMINAL.json"; terminal.parent.mkdir(exist_ok=True); atomic(terminal, {"classification": "h200_w4_component_price_hurdle_owner_terminal", "controller_returncode": code, "controller_summary": summary, "completed_at_utc": dt.datetime.now(dt.UTC).isoformat()})
    atomic(PROJECT / "STATUS.json", {"status": "active", "priority": 340, "researcher_profile": "execution", "summary": "H200 component owner terminal requires scientific reconciliation.", "next_action": "Reconcile typed H200 W4/head c96/c128 rows and authenticated cleanup against exact price hurdles.", "provider_mutation": "forbidden_pending_reconciliation", "authorized_spend_usd": 1.5, "active_session": None, "reconciliation_pending": True, "terminal_artifact": str(terminal), "bindings": "BINDINGS.json"})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
