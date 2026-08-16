#!/usr/bin/env python3
from __future__ import annotations

import hashlib
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
REMOTE = "/home/glmrunner/hybrid-ngram-target-runtime-20260726"
ART = ROOT / "artifacts" / "ngram-target-runtime-20260726t0149z"
STATE = ROOT / "NGRAM_TARGET_RUNTIME_OWNER_STATE.json"
DEADLINE = "2026-07-26T02:18:00Z"


def atomic(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True)


def ssh(command: str) -> subprocess.CompletedProcess[str]:
    return run(["ssh", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=20", f"glmrunner@{HOST}", command])


def pool(action: str, condition: str | None = None) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), action, "--project", PROJECT, "--bench", BENCH]
    if condition:
        argv += ["--condition", condition]
    return subprocess.run(argv, env={**os.environ, "PYTHONPATH": "/root/workspace/research/factory/src"}, text=True, capture_output=True)


def save(name: str, result: subprocess.CompletedProcess[str]) -> None:
    (ART / f"{name}.stdout.log").write_text(result.stdout)
    (ART / f"{name}.stderr.log").write_text(result.stderr)


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    def heartbeats() -> None:
        while not stop.wait(60):
            pool("heartbeat")
    threading.Thread(target=heartbeats, daemon=True).start()
    sources = [ROOT / name for name in (
        "sitecustomize.py", "forward_batch_dual_cache_driver.py", "full_model_memory_adapter.py",
        "phase_selective_full_model_remote.py", "forward_batch_activation_component.py")]
    manifest = {source.name: hashlib.sha256(source.read_bytes()).hexdigest() for source in sources}
    atomic(ART / "source_manifest.json", manifest)
    atomic(STATE, {"phase": "materialize_project_snapshot", "deadline_utc": DEADLINE, "artifact_root": str(ART), "bench": BENCH, "science_started": False, "source_manifest": manifest})
    prep = ssh(f"set -eu; mkdir -p {REMOTE}.tmp/source {REMOTE}.tmp/artifact; test -d /home/glmrunner/phase-selective-full-model-v2/checkpoint; rm -rf {REMOTE}; mv {REMOTE}.tmp {REMOTE}")
    save("remote_prepare", prep)
    if prep.returncode:
        atomic(STATE, {"phase":"infrastructure_terminal", "failure":"remote_project_snapshot_failed", "science_started":False, "artifact_root":str(ART), "deadline_utc":DEADLINE})
        pool("release", "maintenance"); stop.set(); return 2
    copied = run(["scp", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes", *map(str, sources), f"glmrunner@{HOST}:{REMOTE}/source/"])
    save("source_copy", copied)
    if copied.returncode:
        atomic(STATE, {"phase":"infrastructure_terminal", "failure":"source_copy_failed", "science_started":False, "artifact_root":str(ART), "deadline_utc":DEADLINE})
        pool("release", "maintenance"); stop.set(); return 2
    atomic(STATE, {"phase":"single_model_ngram_server_launch", "deadline_utc":DEADLINE, "artifact_root":str(ART), "science_started":False, "remote":REMOTE})
    launch = ssh(f"set -eu; if sudo -n docker inspect phase-selective-readmission >/dev/null 2>&1; then sudo -n docker stop phase-selective-readmission >/dev/null || true; sudo -n docker rm phase-selective-readmission >/dev/null || true; fi; sudo -n docker run -d --name phase-selective-readmission --gpus all -p 30000:30000 -v {REMOTE}:/work -v /home/glmrunner/phase-selective-full-model-v2/checkpoint:/models/target:ro -w /work -e PYTHONPATH=/work/source gemma4-dflash-sglang:588d1f7bc942 python3 -m sglang.launch_server --model-path /models/target --tokenizer-path /models/target --revision b9ea41a2887d8607f594846523f94c6cc75ac8a4 --dtype bfloat16 --tp-size 1 --attention-backend triton --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --speculative-algorithm NGRAM --speculative-num-steps 12 --speculative-num-draft-tokens 12 --skip-server-warmup")
    save("server_launch", launch)
    if launch.returncode:
        atomic(STATE, {"phase":"infrastructure_terminal", "failure":"server_launch_failed", "science_started":False, "artifact_root":str(ART), "deadline_utc":DEADLINE})
        pool("release", "maintenance"); stop.set(); return 2
    proof = None
    for _ in range(35):
        proof = ssh(f"set +e; cat {REMOTE}/artifact/adapter_attach.json; cat {REMOTE}/artifact/forward_batch_dual_cache.json; sudo -n docker inspect -f '{{{{.State.Running}}}}' phase-selective-readmission; exit 0")
        save("preload_proof", proof)
        if '"attached": true' in proof.stdout and '"installed": true' in proof.stdout and "true" in proof.stdout:
            break
        time.sleep(3)
    else:
        logs = ssh("sudo -n docker logs phase-selective-readmission 2>&1 || true")
        save("server_raw", logs)
        atomic(STATE, {"phase":"infrastructure_terminal", "failure":"preload_or_server_health_missing", "science_started":False, "artifact_root":str(ART), "deadline_utc":DEADLINE})
        pool("release", "maintenance"); stop.set(); return 2
    atomic(STATE, {"phase":"target_runtime_smoke", "deadline_utc":DEADLINE, "artifact_root":str(ART), "science_started":True, "candidate_cuda_invocation_started":True, "remote":REMOTE})
    worker = ssh(f"set +e; sudo -n docker exec phase-selective-readmission python3 /work/source/forward_batch_activation_component.py; rc=$?; cat {REMOTE}/artifact/forward-batch-activation-c32/TERMINAL.json 2>/dev/null; sudo -n docker logs phase-selective-readmission >{REMOTE}/artifact/server-raw.log 2>&1; exit $rc")
    save("target_runtime", worker)
    retrieved = ssh(f"set +e; cat {REMOTE}/artifact/forward-batch-activation-c32/INVOCATION.json 2>/dev/null; cat {REMOTE}/artifact/forward-batch-activation-c32/TERMINAL.json 2>/dev/null; cat {REMOTE}/artifact/server-raw.log 2>/dev/null; exit 0")
    save("retrieved", retrieved)
    terminal = {"schema_version":1, "classification":"infrastructure_terminal", "scientific_component_consumed":False, "candidate_cuda_invocation_started":True, "artifact_root":str(ART), "worker_exit":worker.returncode, "retrieval_exit":retrieved.returncode, "reason":"target-runtime smoke does not itself provide the required stock/control comparator or full dual-cache decision record", "raw_evidence":{"worker_stdout":str(ART / "target_runtime.stdout.log"), "worker_stderr":str(ART / "target_runtime.stderr.log"), "retrieved":str(ART / "retrieved.stdout.log")}, "deadline_utc":DEADLINE}
    atomic(ART / "TARGET_RUNTIME_SMOKE_TERMINAL.json", terminal)
    atomic(STATE, {"phase":"terminal_retrieved", **terminal})
    pool("release", "maintenance")
    stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
