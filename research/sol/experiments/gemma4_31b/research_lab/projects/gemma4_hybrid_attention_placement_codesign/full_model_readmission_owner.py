#!/usr/bin/env python3
"""Durable claim controller for the one-model readmitted component path."""
from __future__ import annotations

import json, os, pathlib, subprocess, sys, threading, time

ROOT = pathlib.Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = "gemma4_hybrid_attention_placement_codesign"
BENCH = "h200-dflash-adapter-e00vyqp7gxsr34wrtz"
KEY = "/root/.config/nebius/glm-campaign/ssh_ed25519"
KNOWN = "/root/.config/nebius/glm-campaign/known_hosts"
HOST = "89.169.109.132"
REMOTE = "/home/glmrunner/phase-selective-full-model-readmission-20260726"
ART = ROOT / "artifacts" / "full-model-readmission-20260726t0029z"
STATE = ROOT / "FULL_MODEL_READMISSION_OWNER_STATE.json"
DEADLINE = "2026-07-26T01:15:00Z"

def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)

def pool(action, condition=None):
    command = [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), action,
               "--project", PROJECT, "--bench", BENCH]
    if condition: command += ["--condition", condition]
    return subprocess.run(command, env={**os.environ, "PYTHONPATH": "/root/workspace/research/factory/src"},
                          text=True, capture_output=True)

def ssh(command):
    return subprocess.run(["ssh", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}",
                           "-o", "StrictHostKeyChecking=yes", f"glmrunner@{HOST}", command],
                          text=True, capture_output=True)

def scp(*paths):
    return subprocess.run(["scp", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}",
                           "-o", "StrictHostKeyChecking=yes", *map(str, paths)], text=True, capture_output=True)

def main():
    ART.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    def heartbeat():
        while not stop.wait(90): pool("heartbeat")
    threading.Thread(target=heartbeat, daemon=True).start()
    atomic(STATE, {"phase": "materialize_source", "deadline_utc": DEADLINE, "artifact_root": str(ART),
                   "claimed_at": "2026-07-26T00:29:34.379002Z", "bench": BENCH})
    prep = ssh(f"set -eu; mkdir -p {REMOTE}/artifact {REMOTE}/source; test -d /home/glmrunner/phase-selective-full-model-v2/checkpoint; ln -sfn /home/glmrunner/phase-selective-full-model-v2/checkpoint {REMOTE}/checkpoint")
    (ART / "materialize.stdout.log").write_text(prep.stdout); (ART / "materialize.stderr.log").write_text(prep.stderr)
    if prep.returncode:
        atomic(STATE, {"phase": "repair_ready", "failure": "remote_materialization_failed", "diagnostic": str(ART / "materialize.stderr.log"), "deadline_utc": DEADLINE}); return 2
    sources = [ROOT / name for name in ("sitecustomize.py", "full_model_memory_adapter.py", "phase_selective_full_model_remote.py", "phase_dispatcher.py")]
    copy = scp(*sources, f"glmrunner@{HOST}:{REMOTE}/source/")
    (ART / "source_copy.stdout.log").write_text(copy.stdout); (ART / "source_copy.stderr.log").write_text(copy.stderr)
    if copy.returncode:
        atomic(STATE, {"phase": "repair_ready", "failure": "source_transfer_failed", "diagnostic": str(ART / "source_copy.stderr.log"), "deadline_utc": DEADLINE}); return 2
    atomic(STATE, {"phase": "single_model_server_launch", "deadline_utc": DEADLINE, "artifact_root": str(ART), "remote": REMOTE})
    launch = ssh(f"set -eu; if sudo -n docker inspect phase-selective-readmission >/dev/null 2>&1; then running=$(sudo -n docker inspect -f '{{{{.State.Running}}}}' phase-selective-readmission); if [ \"$running\" = true ]; then echo name_in_use_running >&2; exit 17; fi; sudo -n docker rm phase-selective-readmission >/dev/null; fi; sudo -n docker run -d --name phase-selective-readmission --gpus all -p 30000:30000 -v {REMOTE}:/work -v /home/glmrunner/phase-selective-full-model-v2/checkpoint:/models/target:ro -w /work -e PYTHONPATH=/work/source gemma4-dflash-sglang:588d1f7bc942 python3 -m sglang.launch_server --model-path /models/target --tokenizer-path /models/target --revision b9ea41a2887d8607f594846523f94c6cc75ac8a4 --dtype bfloat16 --tp-size 1 --attention-backend triton --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --skip-server-warmup")
    (ART / "launch.stdout.log").write_text(launch.stdout); (ART / "launch.stderr.log").write_text(launch.stderr)
    if launch.returncode:
        atomic(STATE, {"phase": "repair_ready", "failure": "single_model_server_launch_failed", "diagnostic": str(ART / "launch.stderr.log"), "deadline_utc": DEADLINE}); return 2
    for _ in range(40):
        probe = ssh(f"test -f {REMOTE}/artifact/adapter_attach.json && cat {REMOTE}/artifact/adapter_attach.json; sudo -n docker inspect -f '{{{{.State.Running}}}}' phase-selective-readmission")
        if probe.returncode == 0 and '"attached": true' in probe.stdout:
            atomic(STATE, {"phase": "adapter_attached_driver_required", "deadline_utc": DEADLINE, "artifact_root": str(ART), "remote": REMOTE, "adapter_proof": probe.stdout.strip(), "next": "repair handshake: implement only bound production ForwardBatch dual-cache component driver"})
            # No release: source attachment is real, but no TARGET_VERIFY driver exists yet.
            return 0
        time.sleep(3)
    logs = ssh("sudo -n docker logs phase-selective-readmission 2>&1 || true")
    (ART / "server.log").write_text(logs.stdout)
    atomic(STATE, {"phase": "repair_ready", "failure": "adapter_attach_or_server_health_missing", "diagnostic": str(ART / "server.log"), "deadline_utc": DEADLINE})
    return 2

if __name__ == "__main__": raise SystemExit(main())
