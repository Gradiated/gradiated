#!/usr/bin/env python3
"""Bounded durable controller for the resident ForwardBatch integration."""
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
ART = ROOT / "artifacts" / "forward-batch-dual-cache-20260726t0044z"
STATE = ROOT / "FORWARD_BATCH_DUAL_CACHE_OWNER_STATE.json"
DEADLINE = "2026-07-26T01:15:00Z"

def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n"); os.replace(tmp, path)

def run(command): return subprocess.run(command, text=True, capture_output=True)
def ssh(command): return run(["ssh", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=20", f"glmrunner@{HOST}", command])
def heartbeat():
    return run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), "heartbeat", "--project", PROJECT, "--bench", BENCH])

def main():
    ART.mkdir(parents=True, exist_ok=True); stop = threading.Event()
    def beat():
        while not stop.wait(60): heartbeat()
    threading.Thread(target=beat, daemon=True).start()
    atomic(STATE, {"phase":"strict_resident_health", "bench":BENCH, "claimed_at":"2026-07-26T00:29:34.379002Z", "deadline_utc":DEADLINE, "artifact_root":str(ART)})
    health = ssh("sudo -n docker inspect -f '{{.State.Running}}' phase-selective-readmission; sudo -n docker exec phase-selective-readmission cat /work/artifact/adapter_attach.json")
    (ART/"health.stdout.log").write_text(health.stdout); (ART/"health.stderr.log").write_text(health.stderr)
    if health.returncode or "true" not in health.stdout or '"attached": true' not in health.stdout:
        atomic(STATE, {"phase":"repair_ready", "failure":"resident_health_or_adapter_missing", "diagnostic":str(ART/"health.stderr.log"), "deadline_utc":DEADLINE}); return 2
    atomic(STATE, {"phase":"production_forward_batch_probe", "bench":BENCH, "artifact_root":str(ART), "deadline_utc":DEADLINE})
    copy = run(["scp", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes", str(ROOT/"forward_batch_dual_cache_driver.py"), str(ROOT/"full_model_memory_adapter.py"), f"glmrunner@{HOST}:{REMOTE}/source/"])
    (ART/"copy.stdout.log").write_text(copy.stdout); (ART/"copy.stderr.log").write_text(copy.stderr)
    probe = ssh("sudo -n docker exec phase-selective-readmission python3 /work/source/forward_batch_dual_cache_driver.py; sudo -n docker exec phase-selective-readmission cat /work/artifact/forward_batch_dual_cache.json; test ! -f /work/artifact/forward_batch_driver_attach.json")
    (ART/"probe.stdout.log").write_text(probe.stdout); (ART/"probe.stderr.log").write_text(probe.stderr)
    # The existing process was launched before the required hook existed.  Do
    # not restart it: the director explicitly forbids that on a healthy server.
    diagnosis = {"schema_version":1, "classification":"recoverable_integration_boundary", "scientific_component_consumed":False, "candidate_cuda_invocation_started":False, "science_started":False, "resident_server_preserved":True, "reason":"loaded_server_has_adapter_metadata_but_no_preloaded_ModelRunner.forward ForwardBatch driver", "evidence":{"health_stdout":str(ART/"health.stdout.log"), "probe_stdout":str(ART/"probe.stdout.log"), "probe_exit_code":probe.returncode}, "exact_retry_scope":"start a replacement resident process only if director explicitly authorizes replacing the healthy server; preload sitecustomize.py with forward_batch_dual_cache_driver.py, then run the unconsumed component gates", "deadline_utc":DEADLINE}
    atomic(ROOT/"REPAIR_READY.json", diagnosis); atomic(STATE, {"phase":"repair_ready", **diagnosis})
    # Keep the one bounded owner heartbeating for a hash-bound repair request.
    while time.time() < 1785028500 and not (ROOT/"REPAIR_REQUEST.json").exists(): time.sleep(20)
    stop.set(); return 0

if __name__ == "__main__": raise SystemExit(main())
