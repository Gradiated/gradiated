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
PACKET = PROJECT.parent / "h100_direct_fp8_linear_packet"
NEBIUS = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0, str(NEBIUS))
import mla_microbench_control as controller
from placement_control import list_items, metadata_name

IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUBLIC_KEY = KEY.with_suffix(".pub")
RATE = 2.15
DISK_RATE = 0.0097222
DIRECTOR_ASSERTION_SHA256 = "391855de1e4b59dc397e9d05b85d42cc9b0aabdb6e242b7c0d475082c864e0df"
PACKET_FILES = (
    PACKET / "START_PACKET.json",
    PACKET / "BEHAVIORAL_AUDIT.json",
    PACKET / "STAGED_MANIFEST.json",
    PACKET / "SOURCE_MANIFEST.json",
    PACKET / "h100_contract.py",
    PACKET / "h100_direct_fp8_kernel.py",
    PACKET / "remote_stage.sh",
)
LIFECYCLE_FILES = (
    PROJECT / "PROJECT.md",
    PROJECT / "assert_identity.py",
    PROJECT / "h100_direct_fp8_owner.py",
    PROJECT / "launch_owner.py",
    NEBIUS / "mla_microbench_control.py",
    NEBIUS / "placement_control.py",
)


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    packet = json.loads((PACKET / "START_PACKET.json").read_text())
    audit = json.loads((PACKET / "BEHAVIORAL_AUDIT.json").read_text())
    manifest = json.loads((PACKET / "STAGED_MANIFEST.json").read_text())
    all_files = (*PACKET_FILES, *LIFECYCLE_FILES, args.identity)
    hashes = {str(path): sha(path) for path in all_files}
    instances = [metadata_name(item) for item in list_items("instance")]
    disks = [metadata_name(item) for item in list_items("disk")]
    remote = manifest["remote_files"]
    shared = manifest["shared_lifecycle"]
    representative = {
        "stage": "primary",
        "pass": True,
        "result": {
            "type": "gemma4_h100_exact_shape_direct_cutlass_fp8",
            "sentinel": {"pass": True},
            "identity": {"pass": True},
        },
    }
    checks = {
        "durable_owner": bool(os.getenv("INVOCATION_ID")) and os.getenv("SYSTEMD_EXEC_PID") == str(os.getpid()),
        "lowercase_name": bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", args.name)),
        "director_identity_pass_and_bound": identity.get("pass") is True and sha(args.identity) == DIRECTOR_ASSERTION_SHA256,
        "packet_and_behavioral_audit_pass": packet.get("pass") is True and audit.get("pass") is True,
        "packet_remote_bytes": all(sha(PACKET / name) == expected for name, expected in remote.items()),
        "shared_lifecycle_bytes": sha(NEBIUS / "mla_microbench_control.py") == shared["mla_microbench_control.py"] and sha(NEBIUS / "placement_control.py") == shared["placement_control.py"],
        "complete_transitive_files": all(path.is_file() for path in all_files),
        "trigger_real_evaluator": trigger(representative, time.time() + 421) and not trigger(representative, time.time() + 419),
        "authenticated_empty_inventory": not instances and not disks,
        "keypair": KEY.is_file() and PUBLIC_KEY.is_file(),
        "writable_artifact_root": os.access(output, os.W_OK),
        "budget": (RATE + DISK_RATE) * 1200 / 3600 <= 1.30,
        "deadline": 0 < args.deadline_epoch - time.time() <= 1200,
    }
    precreate = {
        "schema_version": 1,
        "type": "h100_direct_fp8_final_behavioral_transitive_precreate",
        "timestamp": stamp(),
        "name": args.name,
        "checks": checks,
        "inventory": {"instances": instances, "disks": disks},
        "transitive_sha256": hashes,
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
        "unit": os.getenv("SYSTEMD_UNIT"),
        "unit_manager": "systemd --user",
        "owner_pid": os.getpid(),
        "name": args.name,
        "artifact_root": str(output),
        "deadline_epoch": args.deadline_epoch,
        "expected_terminal": "atomically retrieved H100 sliding-QKV M8 sentinel, then only on its typed pass a 24-row sweep; authenticated cleanup on every branch",
    }
    atomic(PROJECT / "STATUS.json", {
        "status": "active", "priority": 240, "researcher_profile": "execution",
        "summary": "Durable H100 raw CUTLASS FP8 sentinel-first owner is running.",
        "next_action": "Reconcile the typed owner terminal after cleanup.",
        "provider_mutation": "exclusive_durable_owner_only", "authorized_spend_usd": 1.3,
        "wall_clock_budget_minutes": 25, "provider_exposure_budget_minutes": 20,
        "compute_budget": "0.34 H100 GPU-hours plus 2 local CPU-hours",
        "storage_budget": "one 100-GiB provider disk; 768 MiB retained plus 384 MiB temporary local",
        "allocation_limit": 1, "repair_limit": 0, "active_session": active,
        "last_result_classification": "durable_h100_direct_fp8_owner_running", "terminal_artifact": None,
    })
    inputs = (PACKET / "STAGED_MANIFEST.json", PACKET / "SOURCE_MANIFEST.json", PACKET / "h100_contract.py")
    code = controller.run(
        output_dir=output,
        name=args.name,
        key=KEY,
        public_key=PUBLIC_KEY,
        spec_hash=sha(PACKET / "START_PACKET.json"),
        remote_script=PACKET / "remote_stage.sh",
        benchmark_script=PACKET / "h100_direct_fp8_kernel.py",
        input_files=inputs,
        artifact_basename="h100-direct-fp8-primary",
        absolute_timeout_seconds=max(1, int(args.deadline_epoch - time.time())),
        runtime_image=IMAGE,
        conditional_remote_script=PACKET / "remote_stage.sh",
        conditional_benchmark_script=PACKET / "h100_direct_fp8_kernel.py",
        conditional_input_files=inputs,
        conditional_artifact_basename="h100-direct-fp8-conditional",
        trigger_evaluator=lambda primary: trigger(primary, args.deadline_epoch),
    )
    summary = json.loads((output / "summary.json").read_text()) if (output / "summary.json").is_file() else {"outcome": "controller_observability_failure"}
    artifacts = PROJECT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    terminal = artifacts / "SUMMARY.json"
    atomic(terminal, {"classification": "h100_direct_fp8_owner_terminal", "controller_returncode": code, "controller_summary": summary, "completed_at_utc": stamp()})
    atomic(PROJECT / "STATUS.json", {
        "status": "active", "priority": 240, "researcher_profile": "execution",
        "summary": "Durable H100 raw CUTLASS FP8 owner terminal requires typed reconciliation.",
        "next_action": "Reconcile retrieved sentinel/sweep artifacts and authenticated cleanup.",
        "provider_mutation": "forbidden_pending_reconciliation", "authorized_spend_usd": 1.3,
        "active_session": None, "reconciliation_pending": True,
        "terminal_artifact": str(terminal), "last_result_classification": "h100_direct_fp8_owner_terminal",
    })
    return code


if __name__ == "__main__":
    raise SystemExit(main())
