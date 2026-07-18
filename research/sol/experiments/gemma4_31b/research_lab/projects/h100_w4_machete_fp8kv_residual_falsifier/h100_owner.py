#!/usr/bin/env python3
"""Durable development owner for the admitted H100 residual measurement."""
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
PUB = KEY.with_suffix(".pub")
RATE = 2.15
DISK_RATE = .0097222
EXPECTED = {
    "w4_terminal": (PROJECT.parent / "h100_w4_marlin_direct_falsifier/artifacts/RECONCILED_MACHETE_TERMINAL.json", "65f103eb84a94d8f985d7df072b24597cdb36532bd8f9b95b08860748f15beff"),
    "head_terminal": (PROJECT.parent / "h100_parallel_lm_head_single_stage/artifacts/gemma-h100-head-dev-20260717t1953z/RECONCILED_TERMINAL.json", "02948d57a0ced4a1215a0de38c42f7fda1bebd23fe540320371efe4d67624c56"),
    "mechanism": (PROJECT.parent / "h100_hybrid_attention_kernel_mechanism/MECHANISM.json", "3960c453e88b1a12e01351d2062dbaa7f8a800e63fe6674e997ddbbcfeebdda1"),
    "global_route_packet": (PROJECT / "GLOBAL_ROUTE_PACKET.json", "21317ff72ffe09a86412ec780b501a7703b0f6ef92f67037ea17afc442a20b7a"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def status(value: dict) -> None:
    atomic(PROJECT / "STATUS.json", value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    hashes = {name: {"path": str(path), "expected": expected, "actual": digest(path) if path.is_file() else None}
              for name, (path, expected) in EXPECTED.items()}
    inventory = {"instances": [metadata_name(item) for item in list_items("instance")],
                 "disks": [metadata_name(item) for item in list_items("disk")]}
    checks = {
        "durable_owner": bool(os.getenv("INVOCATION_ID")) and os.getenv("SYSTEMD_EXEC_PID") == str(os.getpid()),
        "lowercase_name": bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", args.name)),
        "artifact_binding": all(row["actual"] == row["expected"] for row in hashes.values()),
        "empty_inventory": not inventory["instances"] and not inventory["disks"],
        "inputs": all(path.is_file() for path in (PROJECT / "paged_residual.py", PROJECT / "remote_stage.sh", PROJECT / "GLOBAL_ROUTE_PACKET.json")),
        "global_route_packet": json.loads((PROJECT / "GLOBAL_ROUTE_PACKET.json").read_text()).get("pass") is True,
        "keypair": KEY.is_file() and PUB.is_file(),
        "deadline": 0 < args.deadline_epoch - time.time() <= 1500,
        "budget": (RATE + DISK_RATE) * 1500 / 3600 <= 1.5,
    }
    binding = {"schema_version": 1, "type": "h100_w4_residual_identity_binding", "hashes": hashes,
               "checks": checks, "inventory": inventory, "pass": all(checks.values())}
    atomic(out / "BINDINGS.json", binding)
    if not binding["pass"]:
        status({"status":"active","priority":280,"researcher_profile":"deep","summary":"Provider create denied by a typed mutable pre-create gate.","next_action":"Interpret BINDINGS.json typed blocker.","provider_mutation":"denied_typed_precreate","active_session":None,"last_result_classification":"typed_precreate_blocker","terminal_artifact":str(out / "BINDINGS.json")})
        return 1
    controller.PLATFORM = "gpu-h100-sxm"; controller.PRESET = "1gpu-16vcpu-200gb"; controller.DISK_GIB = 100
    controller.HOURLY_RATE_USD = RATE; controller.DISK_HOURLY_RATE_USD = DISK_RATE
    active = {"mode":"development","unit":os.getenv("SYSTEMD_UNIT") or f"{args.name}.service","unit_manager":"systemd --user","owner_pid":os.getpid(),
              "name":args.name,"artifact_root":str(out),"deadline_epoch":args.deadline_epoch,"repair_window_seconds":600,
              "resource_identity":"pending authenticated H100 SXM instance bind","watchdog":"pending bind",
              "expected_terminal":"M1 nonzero global BF16 sentinel followed by atomically retrieved valid global c32 BF16/FP8 rows and residual decision, or typed development failure with authenticated cleanup",
              "forward_progress":"GLOBAL_ROUTE_PACKET and identity binding passed; shared controller entering one retained create/bootstrap/session"}
    status({"status":"active","priority":280,"researcher_profile":"deep","summary":"One retained H100 development owner is running the M1 sentinel and corrected global c32 residual experiment.","next_action":"Attach to this development owner for ordinary repair or reconcile its typed terminal.","provider_mutation":"exclusive_durable_owner_only","authorized_spend_usd":1.5,"wall_clock_budget_minutes":40,"provider_exposure_budget_minutes":25,"compute_budget":"0.42 H100 GPU-hours plus 3 local CPU-hours","active_session":active,"last_result_classification":"durable_h100_global_route_development_running"})
    route_packet = PROJECT / "GLOBAL_ROUTE_PACKET.json"
    code = controller.run(out, args.name, KEY, PUB, digest(route_packet), PROJECT / "remote_stage.sh", PROJECT / "paged_residual.py", (out / "BINDINGS.json", route_packet), "h100-w4-fp8kv-global-c32", max(1, int(args.deadline_epoch - time.time())), IMAGE, repair_window_seconds=600)
    summary = json.loads((out / "summary.json").read_text()) if (out / "summary.json").exists() else {"outcome":"controller_observability_failure"}
    atomic(out / "OWNER_TERMINAL.json", {"controller_returncode":code,"summary":summary,"completed_at_utc":dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z")})
    status({"status":"active","priority":280,"researcher_profile":"deep","summary":"Durable development owner reached a terminal; typed science and cleanup require reconciliation.","next_action":"Reconcile OWNER_TERMINAL.json and retrieved stage archive.","provider_mutation":"forbidden_pending_reconciliation","active_session":None,"reconciliation_pending":True,"terminal_artifact":str(out / "OWNER_TERMINAL.json"),"last_result_classification":"h100_global_route_owner_terminal"})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
