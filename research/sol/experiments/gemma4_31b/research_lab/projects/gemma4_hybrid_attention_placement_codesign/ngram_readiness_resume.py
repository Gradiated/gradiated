#!/usr/bin/env python3
"""Resume the readiness-gated consumer without restarting its live server."""
from __future__ import annotations
import json, os, pathlib, subprocess, sys, threading, time

ROOT = pathlib.Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = "gemma4_hybrid_attention_placement_codesign"
BENCH = "h200-dflash-adapter-e00vyqp7gxsr34wrtz"
KEY = "/root/.config/nebius/glm-campaign/ssh_ed25519"
KNOWN = "/root/.config/nebius/glm-campaign/known_hosts"
HOST = "89.169.109.132"
REMOTE = "/home/glmrunner/hybrid-ngram-readiness-gated-20260726t0343z"
ART = ROOT / "artifacts" / "ngram-readiness-gated-20260726t0343z"
STATE = ROOT / "NGRAM_READINESS_GATED_OWNER_STATE.json"
DEADLINE = "2026-07-26T04:10:00Z"
GRAPH = "Capture cuda graph end"
READY = "The server is fired up and ready to roll!"

def atomic(path, value):
    tmp = path.with_suffix(path.suffix + ".part"); tmp.write_text(json.dumps(value, indent=2, sort_keys=True)+"\n"); os.replace(tmp, path)
def run(args): return subprocess.run(args, text=True, capture_output=True)
def ssh(command): return run(["ssh", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=20", f"glmrunner@{HOST}", command])
def pool(action): return run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), action, "--project", PROJECT, "--bench", BENCH])
def save(name, result):
    (ART / f"{name}.stdout.log").write_text(result.stdout); (ART / f"{name}.stderr.log").write_text(result.stderr)
def main():
    stop=threading.Event()
    def beat():
        while not stop.wait(45): pool("heartbeat")
    threading.Thread(target=beat, daemon=True).start()
    try:
        atomic(STATE, {"phase":"resume_readiness", "deadline_utc":DEADLINE, "artifact_root":str(ART), "science_started":False})
        proof=ssh("set +e; printf 'CONTAINER_RUNNING='; sudo -n docker inspect -f '{{.State.Running}}' phase-selective-readmission; timeout 15s sudo -n docker logs --tail 600 phase-selective-readmission 2>&1 | grep -F 'Capture cuda graph end' | tail -n 1; timeout 15s sudo -n docker logs --tail 600 phase-selective-readmission 2>&1 | grep -F 'The server is fired up and ready to roll!' | tail -n 1; python3 -c \"import socket; s=socket.socket(); s.settimeout(2); r=s.connect_ex(('127.0.0.1',30000)); s.close(); print('TCP_LISTENER='+str(r==0))\"; exit 0")
        save("resume_readiness", proof)
        required=("CONTAINER_RUNNING=true", GRAPH, READY, "TCP_LISTENER=True")
        if proof.returncode or not all(x in proof.stdout for x in required):
            atomic(STATE, {"phase":"typed_readiness_failure", "deadline_utc":DEADLINE, "artifact_root":str(ART), "science_started":False, "diagnostic":str(ART / "resume_readiness.stdout.log")}); return 2
        readiness={"cuda_graph_complete_marker":GRAPH,"server_ready_marker":READY,"live_container":True,"tcp_listener":True,"proof":str(ART / "resume_readiness.stdout.log")}
        atomic(ART / "READINESS.json", readiness)
        atomic(STATE, {"phase":"component_ngram_consumer", "deadline_utc":DEADLINE, "artifact_root":str(ART), "science_started":False,"readiness":readiness})
        worker=ssh(f"set +e; sudo -n docker exec phase-selective-readmission python3 /work/source/forward_batch_activation_component.py; rc=$?; timeout 20s sudo -n docker logs --tail 4000 phase-selective-readmission >{REMOTE}/artifact/server-raw.log 2>&1 || true; cat {REMOTE}/artifact/forward_batch_dual_cache.json 2>/dev/null; cat {REMOTE}/artifact/forward-batch-activation-c32/INVOCATION.json 2>/dev/null; cat {REMOTE}/artifact/forward-batch-activation-c32/TERMINAL.json 2>/dev/null; exit $rc")
        save("target_verify_consumer", worker)
        retrieved=ssh(f"cat {REMOTE}/artifact/forward_batch_dual_cache.json 2>/dev/null; cat {REMOTE}/artifact/forward-batch-activation-c32/INVOCATION.json 2>/dev/null; cat {REMOTE}/artifact/forward-batch-activation-c32/TERMINAL.json 2>/dev/null; cat {REMOTE}/artifact/server-raw.log 2>/dev/null; exit 0")
        save("retrieved", retrieved)
        term=ssh(f"cat {REMOTE}/artifact/forward-batch-activation-c32/TERMINAL.json")
        if term.returncode == 0: (ROOT / "PHASE_SELECTIVE_FULL_MODEL_H200_COMPONENT_TERMINAL.json").write_text(term.stdout)
        atomic(STATE, {"phase":"terminal_retrieved", "deadline_utc":DEADLINE, "artifact_root":str(ART), "worker_returncode":worker.returncode, "terminal_retrieved":term.returncode == 0})
        ssh("sudo -n docker rm -f phase-selective-readmission >/dev/null 2>&1 || true")
        pool("release")
        return 0 if worker.returncode == 0 and term.returncode == 0 else 2
    finally: stop.set()
if __name__ == '__main__': raise SystemExit(main())
