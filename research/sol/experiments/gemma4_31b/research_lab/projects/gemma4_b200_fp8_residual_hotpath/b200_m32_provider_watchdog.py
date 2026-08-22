#!/usr/bin/env python3
"""Fail-closed Nebius cleanup owner for the bounded M32 B200 bench."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


NEBIUS = "/root/.nebius/bin/nebius"
PROFILE = "glm-campaign"


def nebius(kind: str, action: str, resource_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            NEBIUS,
            "compute",
            kind,
            action,
            "--id",
            resource_id,
            "--profile",
            PROFILE,
            "--format",
            "json",
            "--no-progress",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def absent(kind: str, resource_id: str) -> bool:
    return nebius(kind, "get", resource_id).returncode != 0


def wait_absent(kind: str, resource_id: str, timeout_seconds: int = 180) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if absent(kind, resource_id):
            return True
        time.sleep(5)
    return absent(kind, resource_id)


def main() -> int:
    if len(sys.argv) != 5:
        raise SystemExit(
            "usage: watchdog INSTANCE_ID DISK_ID DEADLINE_EPOCH TERMINAL_PATH"
        )
    instance_id, disk_id, deadline_text, terminal_text = sys.argv[1:]
    deadline_epoch = float(deadline_text)
    terminal_path = Path(terminal_text)

    while time.time() < deadline_epoch:
        if absent("instance", instance_id):
            break
        time.sleep(10)

    if not absent("instance", instance_id):
        nebius("instance", "delete", instance_id)
    instance_absent = wait_absent("instance", instance_id)

    if not absent("disk", disk_id):
        nebius("disk", "delete", disk_id)
    disk_absent = wait_absent("disk", disk_id)

    terminal_path.parent.mkdir(parents=True, exist_ok=True)
    terminal_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "classification": "provider_watchdog_cleanup",
                "instance_id": instance_id,
                "disk_id": disk_id,
                "instance_absent": instance_absent,
                "disk_absent": disk_absent,
                "verified_at_epoch": time.time(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return 0 if instance_absent and disk_absent else 1


if __name__ == "__main__":
    raise SystemExit(main())
