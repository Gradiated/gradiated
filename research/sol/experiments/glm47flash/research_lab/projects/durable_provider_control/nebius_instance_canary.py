#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve()
NEBIUS_DIR = HERE.parents[3] / "campaign_100/nebius"
sys.path.insert(0, str(NEBIUS_DIR))
from awq_smoke_control import DISK_GIB, DISK_HOURLY_RATE_USD, HOURLY_RATE_USD, PLATFORM, PRESET
from placement_control import build_create_command, delete_disk, delete_instance, extract_instance_id, get_instance, list_items, metadata_id, metadata_name, wait_absent


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text()) if path.is_file() else default


def redact(value: str) -> str:
    return re.sub(r"(?i)(authorization|token|secret|password)([=:]\s*)\S+", r"\1\2[REDACTED]", value)[:8000]


def capture(root: Path, stage: str, command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    started = time.time()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired as error:
        result = subprocess.CompletedProcess(command, 124, error.stdout or "", error.stderr or "")
        timed_out = True
    stdout = redact(result.stdout if isinstance(result.stdout, str) else "")
    stderr = redact(result.stderr if isinstance(result.stderr, str) else "")
    payload = {"stage": stage, "command_identity": [Path(command[0]).name, *command[1:4]], "exit_code": result.returncode, "timed_out": timed_out, "stdout": stdout, "stderr": stderr, "sha256": hashlib.sha256((stdout + "\n" + stderr).encode()).hexdigest(), "finished_at_epoch": time.time(), "elapsed_seconds": round(time.time() - started, 3)}
    write_json(root / f"diagnostic-{stage}.json", payload)
    return result


def cleanup(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    instance_id = state.get("instance_id")
    disk_name = state.get("disk_name")
    if instance_id:
        capture(root, "instance-delete", ["/root/.nebius/bin/nebius", "compute", "instance", "delete", "--id", instance_id, "--profile", "glm-campaign", "--format", "json", "--no-progress", "--timeout", "90s"], 100)
        direct_absent = wait_absent(instance_id, time.time() + 150)
    else:
        direct_absent = True
    for disk in list_items("disk"):
        if metadata_name(disk) == disk_name and metadata_id(disk):
            delete_disk(metadata_id(disk))
    instances = list_items("instance")
    disks = list_items("disk")
    inventory_absent = not any(metadata_id(row) == instance_id for row in instances) and not any(metadata_name(row) == disk_name for row in disks)
    return {"direct_resource_absent": direct_absent, "inventory_absent": inventory_absent, "final_instance_count": len(instances), "final_disk_count": len(disks)}


def controller(root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    started = time.time()
    identity = hashlib.sha256(f"instance-canary:{started}".encode()).hexdigest()
    name = f"glm47-durable-instance-{identity[:10]}"
    state_path = root / "controller-state.json"
    state = {"schema_version": 1, "identity_sha256": identity, "name": name, "disk_name": name + "-boot", "instance_id": None, "state": "creating", "heartbeat_at": started, "controller_pid": os.getpid(), "deadline_epoch": started + 300}
    write_json(state_path, state)
    error = None
    try:
        command = build_create_command(name=name, disk_name=state["disk_name"], cloud_init="#cloud-config\n", disk_gib=DISK_GIB, platform=PLATFORM, preset=PRESET, preemptible=True, labels={"glm47_canary": identity[:24]})
        created = capture(root, "instance-create", command, 180)
        if created.returncode:
            raise RuntimeError(f"instance create failed with exit {created.returncode}")
        state["instance_id"] = extract_instance_id(json.loads(created.stdout))
        state.update({"state": "observing", "heartbeat_at": time.time()})
        write_json(state_path, state)
        direct = get_instance(state["instance_id"])
        inventory = list_items("instance")
        state["observed_direct"] = direct is not None
        state["observed_inventory"] = any(metadata_id(row) == state["instance_id"] for row in inventory)
        state["heartbeat_at"] = time.time()
        write_json(state_path, state)
        if not state["observed_direct"] or not state["observed_inventory"]:
            raise RuntimeError("instance was not visible through direct and inventory views")
    except Exception as caught:
        error = f"{type(caught).__name__}: {caught}"
    result = cleanup(root, state)
    terminal = {"schema_version": 1, "kind": "nebius_instance_boot_disk_lifecycle_canary", "identity_sha256": identity, "name": name, "disk_name": state["disk_name"], "instance_id": state["instance_id"], "controller_pid": os.getpid(), "started_at_epoch": started, "finished_at_epoch": time.time(), "exposure_seconds": round(time.time() - started, 3), "combined_hourly_rate_usd": HOURLY_RATE_USD + DISK_HOURLY_RATE_USD, "derived_cost_usd": round((time.time() - started) / 3600 * (HOURLY_RATE_USD + DISK_HOURLY_RATE_USD), 9), "observed_direct": state.get("observed_direct", False), "observed_inventory": state.get("observed_inventory", False), "error": error, **result}
    terminal["pass"] = error is None and terminal["observed_direct"] and terminal["observed_inventory"] and terminal["direct_resource_absent"] and terminal["inventory_absent"] and terminal["derived_cost_usd"] <= 0.10
    write_json(root / "terminal-result.json", terminal)
    state.update({"state": "terminal", "heartbeat_at": time.time()})
    write_json(state_path, state)
    return 0 if terminal["pass"] else 1


def watchdog(root: Path) -> int:
    state_path = root / "controller-state.json"
    until = time.time() + 310
    while time.time() < until:
        state = read_json(state_path, {})
        if (root / "terminal-result.json").exists():
            write_json(root / "watchdog-state.json", {"state": "terminal_observed", "watchdog_pid": os.getpid(), "heartbeat_at": time.time(), "identity_sha256": state.get("identity_sha256")})
            return 0
        if state and time.time() >= state.get("deadline_epoch", 0):
            result = cleanup(root, state)
            write_json(root / "watchdog-state.json", {"state": "deadline_cleanup", "watchdog_pid": os.getpid(), "heartbeat_at": time.time(), "identity_sha256": state.get("identity_sha256"), **result})
            return 0 if result["direct_resource_absent"] and result["inventory_absent"] else 2
        time.sleep(1)
    return 3


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in {"controller", "watchdog"}:
        raise SystemExit("usage: nebius_instance_canary.py {controller|watchdog} RESULT_DIRECTORY")
    raise SystemExit(controller(Path(sys.argv[2]).resolve()) if sys.argv[1] == "controller" else watchdog(Path(sys.argv[2]).resolve()))
