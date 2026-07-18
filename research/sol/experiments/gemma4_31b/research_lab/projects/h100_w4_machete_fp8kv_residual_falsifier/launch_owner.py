#!/usr/bin/env python3
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
tag = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dt%H%M%sz")
name = f"gemma-h100-w4-fp8kv-{tag}"
out = PROJECT / "artifacts" / name
deadline = time.time() + 1500
command = ["systemd-run", "--user", f"--unit={name}", "--collect", "--property=TimeoutStartSec=40min", "/usr/bin/python3", str(PROJECT / "h100_owner.py"), "--output-dir", str(out), "--name", name, "--deadline-epoch", str(deadline)]
run = subprocess.run(command, capture_output=True, text=True, timeout=30)
print(json.dumps({"unit":f"{name}.service","unit_manager":"systemd --user","launch_returncode":run.returncode,"stdout":run.stdout[-1000:],"stderr":run.stderr[-1000:],"artifact_root":str(out),"deadline_epoch":deadline,"name":name}, sort_keys=True))
raise SystemExit(run.returncode)
