#!/usr/bin/env python3
"""Launch the controller only after the bound queue gates pass."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess

from run_bench_owner import PROJECT, check_gates


DETACHED = pathlib.Path("/root/workspace/research/factory/tools/detached-owner")
STATE = PROJECT / "OWNER_CONTROLLER.json"
LOG = PROJECT / "artifacts/owner-controller.log"


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> None:
    check_gates()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            str(DETACHED),
            "start",
            "--state",
            str(STATE),
            "--log",
            str(LOG),
            "--cwd",
            str(PROJECT),
            "--unit-manager",
            "pid",
            "python3",
            str(PROJECT / "run_bench_owner.py"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"detached_owner_start_failed:{result.stderr[-1000:]}")
    owner = json.loads(STATE.read_text())
    status = json.loads((PROJECT / "STATUS.json").read_text())
    if status.get("status") == "complete" or (
        PROJECT / "PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json"
    ).exists():
        print(json.dumps(owner, sort_keys=True))
        return
    status["active_session"] = {
        "artifact_root": "artifacts",
        "bench_id": "h200-dflash-adapter-e00vyqp7gxsr34wrtz",
        "deadline_utc": "2026-07-25T21:45:00Z",
        "expected_terminal": "PERSISTENT_GROUPED_LM_HEAD_TERMINAL.json",
        "forward_progress": "durable controller started after queue and lifecycle gates",
        "unit": str(STATE),
        "pid": owner["pid"],
        "start_ticks": owner["start_ticks"],
        "unit_manager": "pid",
    }
    atomic(PROJECT / "STATUS.json", status)
    print(json.dumps(owner, sort_keys=True))


if __name__ == "__main__":
    main()
