#!/usr/bin/env python3
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
tag = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dt%H%M%sz")
name = f"gemma-h100-direct-fp8-{tag}"
output = PROJECT / "artifacts" / name
deadline = time.time() + 1200
identity = PROJECT / "artifacts" / "DIRECTOR_IDENTITY_ASSERTION.json"
command = [
    "systemd-run", "--user", f"--unit={name}", "--collect",
    "--property=TimeoutStartSec=25min", "/usr/bin/python3",
    str(PROJECT / "h100_direct_fp8_owner.py"), "--output-dir", str(output),
    "--name", name, "--deadline-epoch", str(deadline), "--identity", str(identity),
]
run = subprocess.run(command, capture_output=True, text=True, timeout=30)
print(json.dumps({
    "unit": f"{name}.service", "unit_manager": "systemd --user",
    "launch_returncode": run.returncode, "launch_stdout": run.stdout[-1000:],
    "launch_stderr": run.stderr[-1000:], "artifact_root": str(output),
    "deadline_epoch": deadline, "name": name,
}, sort_keys=True))
raise SystemExit(run.returncode)
