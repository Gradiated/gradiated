#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess

PROJECT = pathlib.Path(__file__).resolve().parent
DETACHED = pathlib.Path("/root/workspace/research/factory/tools/detached-owner")
STATE = PROJECT / "ENDPOINT_OWNER_CONTROLLER.json"
LOG = PROJECT / "artifacts/graph-safe-endpoint-owner.log"

def atomic(path, value):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)

def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([str(DETACHED), "start", "--state", str(STATE), "--log", str(LOG), "--cwd", str(PROJECT), "--unit-manager", "pid", "python3", str(PROJECT / "graph_safe_endpoint_owner.py")], text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr[-1000:])
    owner = json.loads(STATE.read_text())
    status = json.loads((PROJECT / "STATUS.json").read_text())
    status["active_session"] = {"artifact_root": "artifacts/graph-safe-endpoint-*", "bench_id": "h200-dflash-adapter-e00vyqp7gxsr34wrtz", "deadline_utc": "2026-07-25T21:47:00Z", "expected_terminal": "GROUPED_LM_HEAD_GRAPH_SAFE_ENDPOINT_TERMINAL.json", "forward_progress": "durable endpoint owner launched before atomic claim", "unit": str(STATE), "pid": owner["pid"], "start_ticks": owner["start_ticks"], "unit_manager": "pid"}
    atomic(PROJECT / "STATUS.json", status)
    print(result.stdout.strip())

if __name__ == "__main__": main()
