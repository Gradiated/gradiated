#!/usr/bin/env python3
"""Durable host owner: stage, heartbeat, retrieve, terminalize, and release."""
from __future__ import annotations
import json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent
LAB = ROOT.parents[1]
BENCH = "h200-dflash-adapter-e00vyqp7gxsr34wrtz"
HOST = "89.169.109.132"
KEY = "/root/.config/nebius/glm-campaign/ssh_ed25519"
KNOWN = "/root/.config/nebius/glm-campaign/known_hosts"
REMOTE = "/home/glmrunner/phase-selective-hybrid"
ART = ROOT / "artifacts" / "phase-selective-20260725t2116z"
STATE = ROOT / "PHASE_SELECTIVE_OWNER_STATE.json"

def call(args, **kwargs): return subprocess.run(args, check=True, text=True, **kwargs)
def write(v):
    STATE.write_text(json.dumps(v, indent=2, sort_keys=True) + "\n")
def ssh(command, check=True):
    return subprocess.run(["ssh", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes", "glmrunner@"+HOST, command], text=True, capture_output=True, check=check)
def heartbeat():
    call([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), "heartbeat", "--project", "gemma4_hybrid_attention_placement_codesign", "--bench", BENCH], env={**dict(__import__('os').environ), "PYTHONPATH":"/root/workspace/research/factory/src"}, stdout=subprocess.DEVNULL)

def main():
    ART.mkdir(parents=True, exist_ok=True); write({"phase":"staging", "deadline_utc":"2026-07-25T21:52:00Z", "artifact_root":str(ART)})
    ssh(f"mkdir -p {REMOTE}/artifact")
    call(["scp", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes", str(ROOT / "phase_selective_remote.py"), f"glmrunner@{HOST}:{REMOTE}/phase_selective_remote.py"])
    write({"phase":"running", "deadline_utc":"2026-07-25T21:52:00Z", "artifact_root":str(ART), "remote":REMOTE})
    proc = ssh(f"sudo -n docker run --rm --gpus all -v {REMOTE}:/work -w /work gemma4-dflash-sglang:588d1f7bc942 python3 phase_selective_remote.py", check=False)
    (ART / "remote.stdout.log").write_text(proc.stdout); (ART / "remote.stderr.log").write_text(proc.stderr)
    call(["scp", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes", f"glmrunner@{HOST}:{REMOTE}/artifact/PHASE_SELECTIVE_HYBRID_H200_COMPONENT_TERMINAL.json", str(ART / "PHASE_SELECTIVE_HYBRID_H200_COMPONENT_TERMINAL.json")])
    call(["scp", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes", f"glmrunner@{HOST}:{REMOTE}/artifact/INVOCATION_STATE.json", str(ART / "INVOCATION_STATE.json")])
    terminal = json.loads((ART / "PHASE_SELECTIVE_HYBRID_H200_COMPONENT_TERMINAL.json").read_text())
    (ROOT / "PHASE_SELECTIVE_HYBRID_H200_COMPONENT_TERMINAL.json").write_text(json.dumps(terminal, indent=2, sort_keys=True)+"\n")
    write({"phase":"terminal", "worker_exit":proc.returncode, "terminal":terminal.get("classification"), "artifact_root":str(ART)})
    call([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), "release", "--project", "gemma4_hybrid_attention_placement_codesign", "--bench", BENCH, "--condition", "ready"], env={**dict(__import__('os').environ), "PYTHONPATH":"/root/workspace/research/factory/src"})

if __name__ == "__main__": main()
