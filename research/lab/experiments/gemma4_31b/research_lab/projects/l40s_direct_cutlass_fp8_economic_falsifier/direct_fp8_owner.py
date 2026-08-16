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
PACKET = PROJECT.parent / "exact_shape_fp8_w4_direct_kernel_packet"
NEBIUS = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0, str(NEBIUS))
import mla_microbench_control as controller
from placement_control import list_items, metadata_name

IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUBLIC_KEY = KEY.with_suffix(".pub")
RATE = 0.7492
DISK_RATE = 0.0097222
FILES = (PROJECT / "PROJECT.md", PROJECT / "assert_identity.py", PROJECT / "direct_fp8_owner.py", PROJECT / "launch_owner.py", PACKET / "START_PACKET.json", PACKET / "FINAL_STAGED_PROGRAM_AUDIT.json", PACKET / "STAGED_MANIFEST.json", PACKET / "SOURCE_MANIFEST.json", PACKET / "direct_fp8_kernel.py", PACKET / "remote_stage.sh", NEBIUS / "mla_microbench_control.py", NEBIUS / "placement_control.py")


def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def atomic(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def trigger(primary, deadline):
    result = primary.get("result") if isinstance(primary, dict) else None
    sentinel = result.get("sentinel") if isinstance(result, dict) else None
    identity = result.get("identity") if isinstance(result, dict) else None
    return bool(primary.get("stage") == "primary" and primary.get("pass") is True and isinstance(result, dict) and result.get("type") == "gemma4_exact_shape_direct_cutlass_fp8" and isinstance(sentinel, dict) and sentinel.get("pass") is True and isinstance(identity, dict) and identity.get("pass") is True and deadline - time.time() >= 720)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=False)
    identity = json.loads(args.identity.read_text())
    instances = [metadata_name(x) for x in list_items("instance")]
    disks = [metadata_name(x) for x in list_items("disk")]
    hashes = {str(path): sha(path) for path in FILES}
    manifest = json.loads((PACKET / "STAGED_MANIFEST.json").read_text())
    remote_expected = manifest["remote_files"]
    lifecycle_expected = manifest["shared_lifecycle"]
    checks = {
        "durable_owner": bool(os.getenv("INVOCATION_ID")) and os.getenv("SYSTEMD_EXEC_PID") == str(os.getpid()),
        "rfc1123_name": bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", args.name)),
        "director_identity_pass": identity.get("pass") is True,
        "packet_audit_pass": json.loads((PACKET / "FINAL_STAGED_PROGRAM_AUDIT.json").read_text()).get("pass") is True,
        "packet_manifest_hashes": hashes[str(PACKET / "direct_fp8_kernel.py")] == remote_expected["direct_fp8_kernel.py"] and hashes[str(PACKET / "remote_stage.sh")] == remote_expected["remote_stage.sh"] and hashes[str(PACKET / "SOURCE_MANIFEST.json")] == remote_expected["SOURCE_MANIFEST.json"],
        "shared_lifecycle_hashes": hashes[str(NEBIUS / "mla_microbench_control.py")] == lifecycle_expected["mla_microbench_control.py"] and hashes[str(NEBIUS / "placement_control.py")] == lifecycle_expected["placement_control.py"],
        "inventory_empty": not instances and not disks,
        "keypair_present": KEY.is_file() and PUBLIC_KEY.is_file(),
        "writable_artifact_root": os.access(output, os.W_OK),
        "deadline_and_budget": 0 < args.deadline_epoch - time.time() <= 2280 and (RATE + DISK_RATE) * 1560 / 3600 <= 0.42,
    }
    precreate = {"schema_version": 1, "type": "l40s_direct_cutlass_fp8_final_transitive_precreate", "timestamp": stamp(), "name": args.name, "inventory": {"instances": instances, "disks": disks}, "transitive_sha256": hashes, "checks": checks, "pass": all(checks.values())}
    atomic(output / "PRECREATE_TERMINAL.json", precreate)
    if not precreate["pass"]: return 1
    controller.PLATFORM = "gpu-l40s-a"; controller.PRESET = "1gpu-8vcpu-32gb"; controller.DISK_GIB = 100; controller.HOURLY_RATE_USD = RATE; controller.DISK_HOURLY_RATE_USD = DISK_RATE
    controller.conditional_trigger = lambda primary: trigger(primary, args.deadline_epoch)
    active = {"unit": os.getenv("SYSTEMD_UNIT"), "unit_manager": "systemd --user", "owner_pid": os.getpid(), "name": args.name, "artifact_root": str(output), "deadline_epoch": args.deadline_epoch, "expected_terminal": "retrieved primary/sweep typed artifacts or typed provider failure with authenticated cleanup"}
    atomic(PROJECT / "STATUS.json", {"status": "active", "priority": 230, "researcher_profile": "execution", "summary": "Durable owner launched for the L40S direct CUTLASS FP8 sentinel-first falsifier.", "next_action": "Reconcile the durable owner terminal.", "provider_mutation": "exclusive_durable_owner_only", "authorized_spend_usd": 0.42, "wall_clock_budget_minutes": 38, "provider_exposure_budget_minutes": 26, "active_session": active, "last_result_classification": "durable_l40s_direct_cutlass_fp8_owner_running", "terminal_artifact": None})
    code = controller.run(output, args.name, KEY, PUBLIC_KEY, sha(PROJECT / "PROJECT.md"), PACKET / "remote_stage.sh", PACKET / "direct_fp8_kernel.py", (PACKET / "STAGED_MANIFEST.json", PACKET / "SOURCE_MANIFEST.json"), "direct-fp8-primary", max(1, int(args.deadline_epoch - time.time())), IMAGE, PACKET / "remote_stage.sh", PACKET / "direct_fp8_kernel.py", (PACKET / "STAGED_MANIFEST.json", PACKET / "SOURCE_MANIFEST.json"), "direct-fp8-conditional")
    summary = json.loads((output / "summary.json").read_text()) if (output / "summary.json").exists() else {"outcome": "controller_observability_failure"}
    atomic(PROJECT / "artifacts" / "SUMMARY.json", {"classification": "l40s_direct_cutlass_fp8_terminal", "controller_returncode": code, "controller_summary": summary, "completed_at_utc": stamp()})
    atomic(PROJECT / "STATUS.json", {"status": "complete", "priority": 230, "researcher_profile": "execution", "summary": "Durable L40S direct CUTLASS FP8 owner terminal; reconcile retrieved artifacts.", "active_session": None, "last_result_classification": "l40s_direct_cutlass_fp8_terminal", "terminal_artifact": str(PROJECT / "artifacts" / "SUMMARY.json")})
    return code


if __name__ == "__main__": raise SystemExit(main())
