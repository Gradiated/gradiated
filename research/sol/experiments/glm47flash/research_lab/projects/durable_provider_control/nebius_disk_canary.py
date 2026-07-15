#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


NEBIUS = "/root/.nebius/bin/nebius"
PROFILE = "glm-campaign"
PROJECT_ID = "project-e00h1vhmpr00vbmfd5k7pg"


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def command(args: list[str], *, check: bool = True) -> tuple[int, Any]:
    process = subprocess.run(
        [NEBIUS, *args, "--profile", PROFILE, "--format", "json", "--no-progress", "--timeout", "90s"],
        capture_output=True,
        text=True,
        timeout=100,
    )
    payload = json.loads(process.stdout) if process.stdout.strip() else None
    if check and process.returncode:
        raise RuntimeError(f"Nebius command failed: {' '.join(args[:3])}; exit={process.returncode}")
    return process.returncode, payload


def item_id(payload: Any) -> str | None:
    if isinstance(payload, dict):
        metadata = payload.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("id"), str):
            return metadata["id"]
        for value in payload.values():
            found = item_id(value)
            if found:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = item_id(value)
            if found:
                return found
    return None


def inventory(name: str) -> list[dict[str, Any]]:
    _, payload = command(["compute", "disk", "list", "--parent-id", PROJECT_ID, "--all"])
    rows = payload.get("items", []) if isinstance(payload, dict) else payload
    return [
        row for row in rows if isinstance(row, dict)
        and ((row.get("metadata") or {}).get("name") == name)
    ]


def run(root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    started = time.time()
    identity = hashlib.sha256(f"nebius-disk-canary:{started}".encode()).hexdigest()
    name = f"glm47-durable-canary-{identity[:12]}"
    state = root / "controller-state.json"
    terminal = root / "terminal-result.json"
    write_json(state, {"schema_version": 1, "identity_sha256": identity, "name": name, "state": "creating", "heartbeat_at": started, "controller_pid": os.getpid()})
    disk_id: str | None = None
    error: str | None = None
    observed_direct = False
    observed_inventory = False
    delete_requested = False
    try:
        _, created = command([
            "compute", "disk", "create", "--parent-id", PROJECT_ID, "--name", name,
            "--size-gibibytes", "1", "--type", "network_hdd",
            "--labels", f"glm47_durable_canary={identity[:32]}",
        ])
        disk_id = item_id(created)
        if disk_id is None:
            raise RuntimeError("create response has no disk identifier")
        write_json(state, {"schema_version": 1, "identity_sha256": identity, "name": name, "disk_id": disk_id, "state": "observing", "heartbeat_at": time.time(), "controller_pid": os.getpid()})
        code, direct = command(["compute", "disk", "get", "--id", disk_id], check=False)
        observed_direct = code == 0 and item_id(direct) == disk_id
        observed_inventory = any(item_id(row) == disk_id for row in inventory(name))
        if not observed_direct or not observed_inventory:
            raise RuntimeError("created disk is not visible through both provider views")
    except Exception as caught:
        error = f"{type(caught).__name__}: {caught}"
    finally:
        if disk_id:
            delete_requested = True
            command(["compute", "disk", "delete", "--id", disk_id], check=False)
        deadline = time.time() + 180
        direct_absent = disk_id is None
        inventory_absent = disk_id is None
        while disk_id and time.time() < deadline:
            direct_absent = command(["compute", "disk", "get", "--id", disk_id], check=False)[0] != 0
            inventory_absent = not any(item_id(row) == disk_id for row in inventory(name))
            if direct_absent and inventory_absent:
                break
            time.sleep(3)
        result = {
            "schema_version": 1,
            "kind": "nebius_disk_lifecycle_canary",
            "identity_sha256": identity,
            "name": name,
            "disk_id": disk_id,
            "controller_pid": os.getpid(),
            "started_at_epoch": started,
            "finished_at_epoch": time.time(),
            "observed_direct": observed_direct,
            "observed_inventory": observed_inventory,
            "delete_requested": delete_requested,
            "direct_resource_absent": direct_absent,
            "inventory_absent": inventory_absent,
            "error": error,
            "pass": error is None and observed_direct and observed_inventory and delete_requested and direct_absent and inventory_absent,
        }
        write_json(terminal, result)
        write_json(state, {"schema_version": 1, "identity_sha256": identity, "name": name, "disk_id": disk_id, "state": "terminal", "heartbeat_at": time.time(), "controller_pid": os.getpid()})
    return 0 if read_pass(terminal) else 1


def read_pass(path: Path) -> bool:
    return json.loads(path.read_text()).get("pass") is True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: nebius_disk_canary.py RESULT_DIRECTORY")
    raise SystemExit(run(Path(sys.argv[1]).resolve()))
