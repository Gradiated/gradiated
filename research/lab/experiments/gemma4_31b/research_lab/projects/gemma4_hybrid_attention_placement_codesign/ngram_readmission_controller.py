#!/usr/bin/env python3
"""Durable same-claim controller for the repaired NGRAM full-model consumer."""
from __future__ import annotations

import datetime as dt
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
REMOTE = "/home/glmrunner/hybrid-ngram-seqlens-cpu-tensor-20260726t0401z"
ART = ROOT / "artifacts" / "ngram-seqlens-cpu-tensor-20260726t0401z"
STATE = ROOT / "NGRAM_SEQLENS_CPU_TENSOR_OWNER_STATE.json"
DEADLINE = "2026-07-26T04:25:00Z"
SUCCESSOR_REPAIR_ID = "seqlens-cpu-tensor-contract-readmission-20260726t0401z"
SERVER_READY_MARKER = "The server is fired up and ready to roll!"
CUDA_GRAPH_COMPLETE_MARKER = "Capture cuda graph end"


def atomic(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True)


def ssh(command: str) -> subprocess.CompletedProcess[str]:
    return run(["ssh", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=20", f"glmrunner@{HOST}", command])


def pool(action: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), action, "--project", PROJECT, "--bench", BENCH], env={**os.environ, "PYTHONPATH": "/root/workspace/research/factory/src"}, text=True, capture_output=True)


def save(name: str, result: subprocess.CompletedProcess[str]) -> None:
    (ART / f"{name}.stdout.log").write_text(result.stdout)
    (ART / f"{name}.stderr.log").write_text(result.stderr)


def preload_ready(output: str) -> bool:
    return all(
        marker in output
        for marker in (
            '"attached": true',
            '"installed": true',
            "CONTAINER_RUNNING=true",
            CUDA_GRAPH_COMPLETE_MARKER,
            SERVER_READY_MARKER,
            "TCP_LISTENER=True",
        )
    )


def release_bench() -> None:
    ssh("sudo -n docker rm -f phase-selective-readmission >/dev/null 2>&1 || true")
    pool("release")


def repair(reason: str, diagnostic: pathlib.Path, phase: str, *, science_started: bool = False) -> int:
    state = {"phase": phase, "deadline_utc": DEADLINE, "artifact_root": str(ART), "science_started": science_started, "failure": reason, "diagnostic": str(diagnostic)}
    atomic(STATE, state)
    handshake = str(ROOT.parents[5] / "factory" / "tools" / "repair-handshake")
    ready = run([handshake, "ready", "--root", str(ART), "--deadline", DEADLINE, "--failure-kind", "integration", "--diagnostic", str(diagnostic), "--retry-scope", "repair only the repaired NGRAM server/consumer boundary under this unchanged claim", "--repair-id", SUCCESSOR_REPAIR_ID])
    save("repair_ready", ready)
    if ready.returncode:
        release_bench()
        return 2
    deadline = dt.datetime.fromisoformat(DEADLINE.replace("Z", "+00:00"))
    wait_seconds = max(1, int((deadline - dt.datetime.now(dt.timezone.utc)).total_seconds()))
    try:
        waited = subprocess.run(
            [handshake, "wait", "--root", str(ART), "--repair-id", SUCCESSOR_REPAIR_ID],
            text=True,
            capture_output=True,
            timeout=wait_seconds,
        )
        save("repair_wait", waited)
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout or ""
        stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr or ""
        (ART / "repair_wait.stdout.log").write_text(stdout)
        (ART / "repair_wait.stderr.log").write_text(stderr)
        atomic(STATE, {**state, "phase": "repair_deadline_released"})
        release_bench()
        return 2
    if waited.returncode:
        atomic(STATE, {**state, "phase": "repair_wait_failed_released", "repair_wait_returncode": waited.returncode})
        release_bench()
        return 2
    atomic(STATE, {**state, "phase": "repair_requested", "replacement_owner_required": True})
    return 2


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    def heartbeat() -> None:
        while not stop.wait(45):
            pool("heartbeat")
    threading.Thread(target=heartbeat, daemon=True).start()
    sources = [ROOT / n for n in ("sitecustomize.py", "forward_batch_dual_cache_driver.py", "full_model_memory_adapter.py", "phase_selective_full_model_remote.py", "forward_batch_activation_component.py", "exact_consumer_oracle.py", "extend_attention_hybrid_proxy.py", "seq_lens_cpu_contract.py")]
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    atomic(ART / "source_manifest.json", manifest)
    atomic(STATE, {"phase": "materialize_and_launch", "deadline_utc": DEADLINE, "artifact_root": str(ART), "science_started": False, "source_manifest": manifest})
    prep = ssh(f"set -eu; mkdir -p {REMOTE}/source {REMOTE}/artifact; test -d /home/glmrunner/phase-selective-full-model-v2/checkpoint; sudo -n docker rm -f phase-selective-readmission 2>/dev/null || true")
    save("remote_prepare", prep)
    if prep.returncode:
        return repair("remote_prepare_failed", ART / "remote_prepare.stderr.log", "repair_ready")
    copied = run(["scp", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=yes", *map(str, sources), f"glmrunner@{HOST}:{REMOTE}/source/"])
    save("source_copy", copied)
    if copied.returncode:
        return repair("source_copy_failed", ART / "source_copy.stderr.log", "repair_ready")
    launch = ssh(f"set -eu; sudo -n docker run -d --name phase-selective-readmission --gpus all -p 30000:30000 -v {REMOTE}:/work -v /home/glmrunner/phase-selective-full-model-v2/checkpoint:/models/target:ro -w /work -e PYTHONPATH=/work/source gemma4-dflash-sglang:588d1f7bc942 python3 -m sglang.launch_server --model-path /models/target --tokenizer-path /models/target --revision b9ea41a2887d8607f594846523f94c6cc75ac8a4 --dtype bfloat16 --tp-size 1 --attention-backend triton --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --speculative-algorithm NGRAM --speculative-num-steps 12 --speculative-num-draft-tokens 12 --skip-server-warmup")
    save("server_launch", launch)
    if launch.returncode:
        return repair("server_launch_failed", ART / "server_launch.stderr.log", "repair_ready")
    # This is intentionally a TCP-only readiness check.  A generation request
    # is the one admitted component and must not be used as a server probe.
    for _ in range(180):
        proof = ssh(
            f"set +e; cat {REMOTE}/artifact/adapter_attach.json; "
            f"cat {REMOTE}/artifact/forward_batch_dual_cache.json; "
            "printf 'CONTAINER_RUNNING='; "
            "sudo -n docker inspect -f '{{.State.Running}}' phase-selective-readmission; "
            "sudo -n docker logs --tail 600 phase-selective-readmission 2>&1 "
            f"| grep -F '{CUDA_GRAPH_COMPLETE_MARKER}' | tail -n 1; "
            "sudo -n docker logs --tail 600 phase-selective-readmission 2>&1 "
            f"| grep -F '{SERVER_READY_MARKER}' | tail -n 1; "
            "python3 -c \"import socket; s=socket.socket(); s.settimeout(2); r=s.connect_ex(('127.0.0.1',30000)); s.close(); print('TCP_LISTENER='+str(r==0))\"; "
            "exit 0"
        )
        save("preload_proof", proof)
        if preload_ready(proof.stdout):
            break
        time.sleep(3)
    else:
        logs = ssh("sudo -n docker logs phase-selective-readmission 2>&1 || true")
        save("server_raw", logs)
        return repair("preload_or_server_health_missing", ART / "server_raw.stdout.log", "repair_ready")
    readiness = {"cuda_graph_complete_marker": CUDA_GRAPH_COMPLETE_MARKER, "server_ready_marker": SERVER_READY_MARKER, "live_container": True, "tcp_listener": True, "proof": str(ART / "preload_proof.stdout.log")}
    atomic(ART / "READINESS.json", readiness)
    atomic(STATE, {"phase": "component_ngram_consumer", "deadline_utc": DEADLINE, "artifact_root": str(ART), "science_started": False, "candidate_cuda_invocation_started": False, "readiness": readiness, "source_manifest": manifest})
    worker = ssh(f"set +e; sudo -n docker exec phase-selective-readmission python3 /work/source/forward_batch_activation_component.py; rc=$?; sudo -n docker logs phase-selective-readmission >{REMOTE}/artifact/server-raw.log 2>&1; cat {REMOTE}/artifact/forward_batch_dual_cache.json 2>/dev/null; cat {REMOTE}/artifact/forward-batch-activation-c32/INVOCATION.json 2>/dev/null; cat {REMOTE}/artifact/forward-batch-activation-c32/TERMINAL.json 2>/dev/null; exit $rc")
    save("target_verify_consumer", worker)
    retrieval = ssh(f"set +e; cat {REMOTE}/artifact/forward_batch_dual_cache.json 2>/dev/null; cat {REMOTE}/artifact/forward-batch-activation-c32/INVOCATION.json 2>/dev/null; cat {REMOTE}/artifact/forward-batch-activation-c32/TERMINAL.json 2>/dev/null; cat {REMOTE}/artifact/server-raw.log 2>/dev/null; exit 0")
    save("retrieved", retrieval)
    terminal_path = ROOT / "PHASE_SELECTIVE_FULL_MODEL_H200_COMPONENT_TERMINAL.json"
    remote_terminal = ssh(f"cat {REMOTE}/artifact/forward-batch-activation-c32/TERMINAL.json", )
    if remote_terminal.returncode == 0:
        terminal_path.write_text(remote_terminal.stdout)
    else:
        terminal = {"schema_version": 1, "classification": "infrastructure_terminal", "scientific_component_consumed": False, "candidate_cuda_invocation_started": True, "failure": "component_terminal_missing", "raw_evidence": {"consumer": str(ART / "target_verify_consumer.stdout.log"), "retrieved": str(ART / "retrieved.stdout.log")}, "deadline_utc": DEADLINE}
        atomic(terminal_path, terminal)
    if worker.returncode:
        return repair("component_consumer_failed", ART / "retrieved.stdout.log", "repair_ready", science_started=True)
    release_bench()
    return 0 if worker.returncode == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
