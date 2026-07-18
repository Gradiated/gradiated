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
NEBIUS = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0, str(NEBIUS))
import mla_microbench_control as controller
from placement_control import list_items, metadata_name

IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUBLIC_KEY = KEY.with_suffix(".pub")
RATE = 0.8581222
DISK_RATE = 0.0097222
FILES = tuple(PROJECT / name for name in ("fp8_actual.py", "w4_actual.py", "remote_stage.sh", "assert_identity.py")) + (NEBIUS / "mla_microbench_control.py",)


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic(path: Path, value: object) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def w4_trigger(primary: dict[str, object], deadline: float, audit: dict[str, object]) -> bool:
    result = primary.get("result")
    trigger = result.get("W4_RESIDUAL_TRIGGER") if isinstance(result, dict) else None
    hashes = audit.get("staged_files", {})
    return bool(primary.get("stage") == "primary" and primary.get("pass") is True and primary.get("all_actual_consumers_pass") is True and isinstance(trigger, dict) and trigger.get("pass") is True and deadline - time.time() >= 600 and all(hashes.get(path.name) == sha(path) for path in FILES))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    audit = json.loads(args.audit.read_text())
    identity = json.loads(args.identity.read_text())
    instances = [metadata_name(item) for item in list_items("instance")]
    disks = [metadata_name(item) for item in list_items("disk")]
    checks = {
        "durable_owner": bool(os.getenv("INVOCATION_ID")) and os.getenv("SYSTEMD_EXEC_PID") == str(os.getpid()),
        "rfc1123_name": bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", args.name)),
        "director_identity_pass": identity.get("pass") is True,
        "final_audit_pass": audit.get("pass") is True,
        "staged_bytes_match_audit": all(audit.get("staged_files", {}).get(path.name) == sha(path) for path in FILES),
        "inventory_empty": not instances and not disks,
        "keypair_present": KEY.is_file() and PUBLIC_KEY.is_file(),
        "placement_rate_and_cap": RATE == 0.8581222 and (RATE + DISK_RATE) * 2100 / 3600 <= 0.57,
        "provider_deadline": 0 < args.deadline_epoch - time.time() <= 2100,
    }
    terminal = {"schema_version": 1, "type": "l40s_online_fp8_typed_precreate", "timestamp": stamp(), "name": args.name, "inventory": {"instances": instances, "disks": disks}, "checks": checks, "pass": all(checks.values())}
    atomic(output / "PRECREATE_TERMINAL.json", terminal)
    if not terminal["pass"]:
        return 1
    controller.PLATFORM = "gpu-l40s-a"
    controller.PRESET = "1gpu-8vcpu-32gb"
    controller.DISK_GIB = 100
    controller.HOURLY_RATE_USD = RATE
    controller.DISK_HOURLY_RATE_USD = DISK_RATE
    controller.conditional_trigger = lambda primary: w4_trigger(primary, args.deadline_epoch, audit)
    atomic(PROJECT / "STATUS.json", {"status": "active", "summary": "Durable L40S owner controls primary FP8 and only typed-triggered same-session W4.", "provider_mutation": "exclusive_durable_owner", "authorized_spend_usd": 0.57, "active_session": {"unit": os.getenv("SYSTEMD_UNIT"), "unit_manager": "systemd --user", "owner_pid": os.getpid(), "name": args.name, "artifact_root": str(output), "deadline_epoch": args.deadline_epoch, "expected_terminal": "FP8/W4 typed stage rows or typed provider execution failure with authenticated cleanup"}, "last_result_classification": "durable_l40s_online_fp8_owner_running", "terminal_artifact": None})
    code = controller.run(output, args.name, KEY, PUBLIC_KEY, sha(PROJECT / "PROJECT.md"), PROJECT / "remote_stage.sh", PROJECT / "fp8_actual.py", (), "l40s-online-fp8", max(1, int(args.deadline_epoch - time.time())), IMAGE, PROJECT / "remote_stage.sh", PROJECT / "w4_actual.py", (PROJECT / "fp8_actual.py",), "l40s-w4-marlin")
    summary = json.loads((output / "summary.json").read_text()) if (output / "summary.json").exists() else {"outcome": "controller_observability_failure"}
    atomic(PROJECT / "artifacts" / "SUMMARY.json", {"classification": "l40s_online_fp8_actual_consumer_terminal", "controller_returncode": code, "controller_summary": summary, "completed_at_utc": stamp()})
    atomic(PROJECT / "STATUS.json", {"status": "complete", "summary": "Durable L40S owner terminal; reconcile typed artifacts.", "active_session": None, "terminal_artifact": str(PROJECT / "artifacts" / "SUMMARY.json"), "last_result_classification": "l40s_online_fp8_actual_consumer_terminal"})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
