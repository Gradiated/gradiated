#!/usr/bin/env python3
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

p = Path(__file__).resolve().parent
tag = dt.datetime.now(dt.UTC).strftime('%Y%m%dt%H%M%sz')
name = f'gemma-h200-w4-endpoint-{tag}'
out = p / 'artifacts' / name
deadline = time.time() + 3650
run = subprocess.run(['systemd-run', '--user', '--collect', f'--unit={name}', '--property=TimeoutStartSec=100min', '/usr/bin/python3', str(p / 'h200_endpoint_owner.py'), '--output-dir', str(out), '--name', name, '--deadline-epoch', str(deadline)], capture_output=True, text=True, timeout=30)
print(json.dumps({'unit': f'{name}.service', 'unit_manager': 'user', 'launch_returncode': run.returncode, 'launch_stdout': run.stdout[-1000:], 'launch_stderr': run.stderr[-1000:], 'artifact_root': str(out), 'deadline_epoch': deadline, 'name': name}, sort_keys=True))
raise SystemExit(run.returncode)
