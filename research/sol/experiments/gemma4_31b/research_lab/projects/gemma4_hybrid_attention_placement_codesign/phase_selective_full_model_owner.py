#!/usr/bin/env python3
"""Bounded durable controller for the admitted full-model phase-selective gate."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = "gemma4_hybrid_attention_placement_codesign"
BENCH = "h200-dflash-adapter-e00vyqp7gxsr34wrtz"
KEY = "/root/.config/nebius/glm-campaign/ssh_ed25519"
KNOWN = "/root/.config/nebius/glm-campaign/known_hosts"
HOST = "89.169.109.132"
REMOTE = "/home/glmrunner/phase-selective-full-model-v2"
ART = ROOT / "artifacts" / "phase-selective-full-model-20260725t2138z"
STATE = ROOT / "PHASE_SELECTIVE_FULL_MODEL_OWNER_STATE.json"
DEADLINE = "2026-07-26T01:10:00Z"

def atomic(path: pathlib.Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)

def pool(action: str) -> None:
    env = {**os.environ, "PYTHONPATH": "/root/workspace/research/factory/src"}
    subprocess.run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), action,
                    "--project", PROJECT, "--bench", BENCH], env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def ssh(command: str, **kw):
    return subprocess.run(["ssh", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}",
                           "-o", "StrictHostKeyChecking=yes", f"glmrunner@{HOST}", command],
                          text=True, capture_output=True, **kw)

def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    def beat():
        while not stop.wait(120):
            try: pool("heartbeat")
            except Exception: pass
    threading.Thread(target=beat, daemon=True).start()
    atomic(STATE, {"phase": "pre_science_materialization", "deadline_utc": DEADLINE,
                   "artifact_root": str(ART), "bench": BENCH})
    # Snapshot every admitted mutable source and checkpoint name under this project before invocation.
    prep = ssh("set -eu; rm -rf /home/glmrunner/phase-selective-full-model-v2.tmp; "
               "mkdir -p /home/glmrunner/phase-selective-full-model-v2.tmp/checkpoint /home/glmrunner/phase-selective-full-model-v2.tmp/artifact; "
               "for f in config.json model.safetensors.index.json tokenizer.json tokenizer_config.json processor_config.json chat_template.jinja model-00001-of-00002.safetensors model-00002-of-00002.safetensors; do "
               "cp --reflink=auto --preserve=mode,timestamps /home/glmrunner/gemma4-persistent-grouped-lm-head/checkpoint/$f /home/glmrunner/phase-selective-full-model-v2.tmp/checkpoint/$f; done; "
               "mv /home/glmrunner/phase-selective-full-model-v2.tmp /home/glmrunner/phase-selective-full-model-v2", check=False)
    (ART / "materialize.stdout.log").write_text(prep.stdout); (ART / "materialize.stderr.log").write_text(prep.stderr)
    if prep.returncode:
        atomic(STATE, {"phase":"repair_ready", "deadline_utc":DEADLINE, "artifact_root":str(ART),
                       "failure":"remote_project_snapshot_failed", "exit_code":prep.returncode})
        return 2
    subprocess.run(["scp", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes",
                    str(ROOT / "phase_selective_full_model_remote.py"), f"glmrunner@{HOST}:{REMOTE}/phase_selective_full_model_remote.py"], check=True)
    atomic(STATE, {"phase":"full_model_invocation", "deadline_utc":DEADLINE, "artifact_root":str(ART), "remote":REMOTE})
    run = ssh(f"sudo -n docker run --rm --gpus all -v {REMOTE}:/work -w /work gemma4-dflash-sglang:588d1f7bc942 python3 phase_selective_full_model_remote.py", check=False)
    (ART / "remote.stdout.log").write_text(run.stdout); (ART / "remote.stderr.log").write_text(run.stderr)
    get = ssh(f"test -f {REMOTE}/artifact/PHASE_SELECTIVE_FULL_MODEL_H200_COMPONENT_TERMINAL.json", check=False)
    if get.returncode == 0:
        subprocess.run(["scp", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes",
                        f"glmrunner@{HOST}:{REMOTE}/artifact/PHASE_SELECTIVE_FULL_MODEL_H200_COMPONENT_TERMINAL.json", str(ROOT / "PHASE_SELECTIVE_FULL_MODEL_H200_COMPONENT_TERMINAL.json")], check=True)
        terminal = json.loads((ROOT / "PHASE_SELECTIVE_FULL_MODEL_H200_COMPONENT_TERMINAL.json").read_text())
        atomic(STATE, {"phase":"terminal", "deadline_utc":DEADLINE, "artifact_root":str(ART), "terminal":terminal})
        pool("release")
        stop.set(); return 0
    atomic(STATE, {"phase":"repair_ready", "deadline_utc":DEADLINE, "artifact_root":str(ART),
                   "failure":"full_model_remote_no_terminal", "worker_exit":run.returncode,
                   "diagnostics":[str(ART / "remote.stdout.log"), str(ART / "remote.stderr.log")]})
    stop.set(); return 2

if __name__ == "__main__":
    raise SystemExit(main())
