#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent

parser = argparse.ArgumentParser()
parser.add_argument("--identity", type=Path, required=True)
args = parser.parse_args()
tag = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dt%H%M%sz")
name = f"gemma-l40s-direct-fp8-{tag}"
output = PROJECT / "artifacts" / name
deadline = time.time() + 1560
command = ["systemd-run", "--user", "--unit", name, "--collect", "--property=TimeoutStartSec=40min", "/usr/bin/python3", str(PROJECT / "direct_fp8_owner.py"), "--output-dir", str(output), "--name", name, "--deadline-epoch", str(deadline), "--identity", str(args.identity.resolve())]
run = subprocess.run(command, capture_output=True, text=True, timeout=30)
print(json.dumps({"unit": f"{name}.service", "unit_manager": "systemd --user", "launch_returncode": run.returncode, "launch_stdout": run.stdout[-1000:], "launch_stderr": run.stderr[-1000:], "artifact_root": str(output), "deadline_epoch": deadline, "name": name}, sort_keys=True))
raise SystemExit(run.returncode)
