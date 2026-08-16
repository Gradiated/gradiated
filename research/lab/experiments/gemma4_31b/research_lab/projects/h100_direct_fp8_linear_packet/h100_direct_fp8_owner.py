#!/usr/bin/env python3
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
NEBIUS = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0, str(NEBIUS))
import mla_microbench_control as controller
from placement_control import list_items, metadata_name

IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUBLIC_KEY = KEY.with_suffix(".pub")
RATE = 2.15
DISK_RATE = 0.0097222


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def trigger(primary: dict[str, object], deadline: float) -> bool:
    result = primary.get("result") if isinstance(primary, dict) else None
    sentinel = result.get("sentinel") if isinstance(result, dict) else None
    identity = result.get("identity") if isinstance(result, dict) else None
    return bool(
        primary.get("stage") == "primary"
        and primary.get("pass") is True
        and isinstance(result, dict)
        and result.get("type") == "gemma4_h100_exact_shape_direct_cutlass_fp8"
        and isinstance(sentinel, dict)
        and sentinel.get("pass") is True
        and isinstance(identity, dict)
        and identity.get("pass") is True
        and deadline - time.time() >= 420
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
    audit = json.loads((PROJECT / "BEHAVIORAL_AUDIT.json").read_text())
    manifest = json.loads((PROJECT / "STAGED_MANIFEST.json").read_text())
    instances = [metadata_name(item) for item in list_items("instance")]
    disks = [metadata_name(item) for item in list_items("disk")]
    files = {name: PROJECT / name for name in manifest["remote_files"]}
    staged = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}
    checks = {
        "durable_owner": bool(os.getenv("INVOCATION_ID")) and os.getenv("SYSTEMD_EXEC_PID") == str(os.getpid()),
        "lowercase_name": bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", args.name)),
        "identity_assertion": identity.get("pass") is True,
        "behavioral_audit": audit.get("pass") is True,
        "staged_bytes": staged == manifest["remote_files"],
        "empty_inventory": not instances and not disks,
        "keypair": KEY.is_file() and PUBLIC_KEY.is_file(),
        "budget": (RATE + DISK_RATE) * 1200 / 3600 <= 1.3,
        "deadline": 0 < args.deadline_epoch - time.time() <= 1200,
    }
    precreate = {"schema_version": 1, "type": "h100_direct_fp8_typed_precreate", "timestamp": stamp(), "checks": checks, "inventory": {"instances": instances, "disks": disks}, "pass": all(checks.values())}
    atomic(output / "PRECREATE_TERMINAL.json", precreate)
    if not precreate["pass"]:
        return 1
    controller.PLATFORM = "gpu-h100-sxm"
    controller.PRESET = "1gpu-16vcpu-200gb"
    controller.DISK_GIB = 100
    controller.HOURLY_RATE_USD = RATE
    controller.DISK_HOURLY_RATE_USD = DISK_RATE
    controller.conditional_trigger = lambda primary: trigger(primary, args.deadline_epoch)
    active = {"unit": os.getenv("SYSTEMD_UNIT"), "unit_manager": "systemd --user", "owner_pid": os.getpid(), "name": args.name, "artifact_root": str(output), "deadline_epoch": args.deadline_epoch, "expected_terminal": "atomically retrieved H100 M8 sentinel and, only if it passes with seven-minute reserve, 24-row M8/M16/M32/M3679 sweep; authenticated cleanup on every branch"}
    atomic(PROJECT / "STATUS.json", {"status": "active", "priority": 225, "researcher_profile": "execution", "summary": "Durable H100 direct CUTLASS FP8 owner launched.", "next_action": "Reconcile the typed owner terminal.", "provider_mutation": "exclusive_durable_owner_only", "authorized_spend_usd": 1.3, "wall_clock_budget_minutes": 20, "provider_exposure_budget_minutes": 20, "active_session": active, "last_result_classification": "durable_h100_direct_fp8_owner_running", "terminal_artifact": None})
    code = controller.run(output, args.name, KEY, PUBLIC_KEY, hashlib.sha256((PROJECT / "START_PACKET.json").read_bytes()).hexdigest(), PROJECT / "remote_stage.sh", PROJECT / "h100_direct_fp8_kernel.py", tuple(files.values()), "h100-direct-fp8-primary", max(1, int(args.deadline_epoch - time.time())), IMAGE, PROJECT / "remote_stage.sh", PROJECT / "h100_direct_fp8_kernel.py", tuple(files.values()), "h100-direct-fp8-conditional")
    summary = json.loads((output / "summary.json").read_text()) if (output / "summary.json").is_file() else {"outcome": "controller_observability_failure"}
    artifacts = PROJECT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    atomic(artifacts / "SUMMARY.json", {"classification": "h100_direct_fp8_terminal", "controller_returncode": code, "controller_summary": summary, "completed_at_utc": stamp()})
    atomic(PROJECT / "STATUS.json", {"status": "active", "priority": 225, "researcher_profile": "execution", "summary": "Durable H100 direct CUTLASS FP8 owner terminal requires typed reconciliation.", "next_action": "Reconcile typed H100 direct-linear artifacts and authenticated cleanup.", "provider_mutation": "forbidden_pending_reconciliation", "authorized_spend_usd": 1.3, "active_session": None, "reconciliation_pending": True, "terminal_artifact": str(artifacts / "SUMMARY.json"), "last_result_classification": "h100_direct_fp8_owner_terminal"})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
