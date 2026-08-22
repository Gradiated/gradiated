#!/usr/bin/env python3
"""Adopt the retained H200 claim and continue from its healthy stock server."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = "gemma4_hybrid_attention_placement_codesign"
REPAIR = ROOT / "DIRECTOR_H200_55L5G_ENDPOINT_RETAINED_STOCK_HEALTH_REPAIR_20260729T0128Z.json"
EXTENSION = ROOT / "DIRECTOR_H200_55L5G_ENDPOINT_RETAINED_STOCK_HEALTH_REPAIR_START_EXTENSION_20260729T0139Z.json"
ARTIFACT = ROOT / "artifacts/h200-55l5g-endpoint-stock-health-repair-20260729t0128z"
TERMINAL = "HYBRID_55L5G_CURRENT_H200_ENDPOINT_TERMINAL.json"

def load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict): raise RuntimeError("json_object_required")
    return value

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True); stream.write("\n"); temporary = Path(stream.name)
    json.loads(temporary.read_text()); temporary.replace(path)

def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args], text=True, capture_output=True, env={**os.environ, "PYTHONPATH": str(ROOT.parents[5] / "factory" / "src")})

def call(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)

def status_update(**changes: object) -> None:
    value = load(ROOT / "STATUS.json"); value.update(changes); atomic(ROOT / "STATUS.json", value)

def main() -> int:
    repair, extension = load(REPAIR), load(EXTENSION)
    if not (repair["project"] == PROJECT and sha(ROOT / repair["mutable_repair"]["source_owner"]) == repair["mutable_repair"]["source_owner_sha256"] and extension["retained_stock_health_repair_binding"]["sha256"] == sha(REPAIR)):
        raise RuntimeError("stock_repair_binding_mismatch")
    shown = pool("show", "--bench", repair["live_claim"]["bench_id"])
    bench = json.loads(shown.stdout); claim = bench.get("claim") or {}; expected = repair["live_claim"]["expected_claimed_at_utc"]
    if not (shown.returncode == 0 and claim.get("project") == PROJECT and claim.get("claimed_at") == expected): raise RuntimeError("retained_claim_generation_mismatch")
    heartbeat = pool("heartbeat", "--project", PROJECT, "--bench", bench["id"])
    if heartbeat.returncode: raise RuntimeError("retained_claim_heartbeat_failed")
    artifact = ARTIFACT.resolve(); artifact.mkdir(parents=True, exist_ok=True)
    key, known = bench["resource"]["identity_file"], bench["resource"]["known_hosts_namespace"]
    host = f'{bench["resource"]["ssh_user"]}@{bench["resource"]["public_ipv4"]}'
    ssh = ["/usr/bin/ssh", "-i", key, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known}", host]
    scp = ["/usr/bin/scp", "-i", key, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known}"]
    state = call([*ssh, "sudo -n docker inspect --format '{{json .State}}' hybrid-55l5g"], 30)
    try: running = json.loads(state.stdout).get("Running") is True
    except json.JSONDecodeError: running = False
    health = call([*ssh, "curl -fsS http://127.0.0.1:30000/health"], 30)
    if not (state.returncode == 0 and running and health.returncode == 0):
        atomic(artifact / "PRE_SCIENCE_FAILURE.json", {"classification":"recoverable_stock_health_failure", "science_consumed":False, "state":state.stdout[-4000:], "stderr":state.stderr[-4000:], "health_stderr":health.stderr[-4000:]})
        return 72
    stop = threading.Event()
    def beat() -> None:
        while not stop.wait(35): pool("heartbeat", "--project", PROJECT, "--bench", bench["id"])
    threading.Thread(target=beat, daemon=True).start()
    owner_state = os.environ.get("DETACHED_OWNER_STATE", str(artifact.parent / (artifact.name + "-controller") / "OWNER_STATE.json"))
    status_update(active_session={"artifact_root":str(artifact), "bench_id":bench["id"], "expected_claimed_at_utc":expected, "deadline_utc":extension["lifecycle"]["owner_deadline_utc"], "expected_terminal":TERMINAL, "forward_progress":"healthy stock server adopted; stock then candidate c32 pair", "unit":owner_state, "pid":os.getpid(), "unit_manager":"pid"})
    try:
        execution = load(ROOT / repair["predecessor_execution_binding"]["path"]); packet = load(ROOT / execution["packet_manifest_path"])
        remote, checkpoint = execution["runtime_destinations"]["remote_root"], execution["runtime_destinations"]["checkpoint"]
        pair, workload, candidate = ROOT / "run_h200_55l5g_endpoint_pair.py", ROOT / packet["pair_contract"]["workload_path"], ROOT / execution["candidate_source"]["path"]
        for source in (pair, workload, candidate):
            copied = call([*scp, str(source), f"{host}:{remote}/packet/{source.name}"], 180)
            if copied.returncode: raise RuntimeError(f"packet_copy_failed:{source.name}")
        runner = "import json,sys;from pathlib import Path;import run_h200_55l5g_endpoint_pair as p;w=json.loads(Path('/work/qualified_c32_workload.json').read_text());print(json.dumps(p.run_arm(sys.argv[1],sys.argv[2],w,900)))"
        atomic(artifact / "STOCK_REQUEST_START.json", {"science_started":True, "arm":"stock", "submitted_after":"State.Running true and /health", "workload_sha256":sha(workload)})
        stock_call = call([*ssh, f"cd {remote}/packet && sudo -n docker exec hybrid-55l5g python3 -c {json.dumps(runner)} stock http://127.0.0.1:30000"], 1800)
        stock_log = call([*ssh, "sudo -n docker logs hybrid-55l5g 2>&1 | /usr/bin/tail -n 400"], 60)
        if stock_call.returncode: raise RuntimeError("stock_request_driver_failed")
        stock = json.loads(stock_call.stdout.strip().splitlines()[-1]); stock["server_log_tail"] = stock_log.stdout[-12000:]
        atomic(artifact / "STOCK_ARM.json", stock)
        if not (stock["complete_requests"] == 32 and stock["failures"] == 0):
            atomic(artifact / "PRE_SCIENCE_FAILURE.json", {"classification":"invalid_stock_arm", "science_consumed":False, "stock":stock}); return 72
        replaced = call([*ssh, "sudo -n docker rm -f hybrid-55l5g"], 60)
        if replaced.returncode: raise RuntimeError("stock_container_replacement_failed")
        launch = f"sudo -n docker run -d --name hybrid-55l5g --gpus all -p 30000:30000 -v {checkpoint}:/models/target:ro -v {remote}/packet:/work -v {remote}/packet/{candidate.name}:/usr/local/lib/python3.11/site-packages/sglang/srt/layers/attention/triton_ops/extend_attention.py:ro {execution['runtime_destinations']['image']} python3 -m sglang.launch_server --model-path /models/target --tokenizer-path /models/target --dtype bfloat16 --tp-size 1 --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32"
        if call([*ssh, launch], 180).returncode: raise RuntimeError("candidate_launch_failed")
        ready = call([*ssh, "curl -fsS http://127.0.0.1:30000/health"], 600)
        proof = call([*ssh, "sudo -n docker exec hybrid-55l5g sha256sum /usr/local/lib/python3.11/site-packages/sglang/srt/layers/attention/triton_ops/extend_attention.py"], 60)
        if ready.returncode or execution["candidate_source"]["sha256"] not in proof.stdout: raise RuntimeError("candidate_readiness_or_path_proof_failed")
        atomic(artifact / "CANDIDATE_REQUEST_START.json", {"science_started":True, "candidate_cuda_invocation_started":False, "arm":"permanent_55local_5global", "stock_terminal":str(artifact / "STOCK_ARM.json")})
        candidate_call = call([*ssh, f"cd {remote}/packet && sudo -n docker exec hybrid-55l5g python3 -c {json.dumps(runner)} permanent_55local_5global http://127.0.0.1:30000"], 1800)
        candidate_log = call([*ssh, "sudo -n docker logs hybrid-55l5g 2>&1 | /usr/bin/tail -n 400"], 60)
        if candidate_call.returncode: raise RuntimeError("candidate_request_driver_failed")
        candidate_result = json.loads(candidate_call.stdout.strip().splitlines()[-1]); candidate_result["server_log_tail"] = candidate_log.stdout[-12000:]
        atomic(artifact / "CANDIDATE_ARM.json", candidate_result)
        valid = candidate_result["complete_requests"] == 32 and candidate_result["failures"] == 0
        terminal = {"schema_version":1, "classification":"scientific_terminal" if valid else "invalid_endpoint_pair", "science_consumed":valid, "candidate_cuda_invocation_started":valid, "quality_preservation_claimed":False, "workload":execution["pair_contract"], "control":stock, "candidate":candidate_result, "service_time_delta_seconds_per_request":candidate_result["service_seconds_per_request"]-stock["service_seconds_per_request"] if valid else None}
        atomic(artifact / TERMINAL, terminal); atomic(ROOT / TERMINAL, terminal)
        return 0 if valid else 72
    except Exception as error:
        atomic(artifact / "OWNER_EXCEPTION.json", {"classification":"recoverable_pre_science_or_unknown", "science_consumed":False, "exception":repr(error)})
        return 72
    finally: stop.set()

if __name__ == "__main__": raise SystemExit(main())
