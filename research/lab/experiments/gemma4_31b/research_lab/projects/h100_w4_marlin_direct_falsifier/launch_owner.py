#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import subprocess
import time
from pathlib import Path


PROJECT = Path(__file__).resolve().parent


def main() -> int:
    tag = dt.datetime.now(dt.UTC).strftime("%Y%m%dt%H%M%sz")
    name = f"gemma-h100-w4-machete-{tag}"
    output = PROJECT / "artifacts" / name
    deadline = time.time() + 1200
    command = [
        "systemd-run", "--user", f"--unit={name}", "--collect", "--property=TimeoutStartSec=23min",
        "/usr/bin/python3", str(PROJECT / "h100_w4_marlin_owner.py"), "--output-dir", str(output),
        "--name", name, "--deadline-epoch", str(deadline),
        "--identity", str(PROJECT / "artifacts" / "DIRECTOR_IDENTITY_RERUN.json"),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    print(json.dumps({
        "unit": f"{name}.service", "unit_manager": "systemd --user", "launch_returncode": result.returncode,
        "launch_stdout": result.stdout[-1000:], "launch_stderr": result.stderr[-1000:],
        "artifact_root": str(output), "deadline_epoch": deadline, "name": name,
    }, sort_keys=True))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
