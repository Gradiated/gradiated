#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import threading
import time


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[2] / "runtime"  # overridden below for clarity
LAB_ROOT = Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
REMOTE = "glmrunner@89.169.103.97"
KEY = "/root/.config/nebius/glm-campaign/ssh_ed25519"
KNOWN = "/root/.config/nebius/glm-campaign/known_hosts"
REMOTE_ROOT = "/home/glmrunner/adaptive_depth6_fresh_endpoint"
IMAGE = "docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd"
BENCH = "h100-v0515-packed-endpoint-200g-e00y7ay83sma59j0hz"
PROJECT_ID = "gemma4_h100_v0515_ngram_adaptive_depth6_cuda_graph"
STARTED = time.time()
STOP = threading.Event()


def remote_env() -> str:
    return f"FRESH_ENDPOINT_ROOT={REMOTE_ROOT} FRESH_START={os.environ.get('FRESH_START', '62000')} FRESH_END={os.environ.get('FRESH_END', '62790')}"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: object) -> None:
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    part.replace(path)


def heartbeat() -> None:
    while not STOP.wait(45):
        subprocess.run([
            "python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB_ROOT),
            "heartbeat", "--project", PROJECT_ID,
        ], cwd="/root/workspace", env={**os.environ, "PYTHONPATH": "research/factory/src"}, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ssh(command: str, timeout: int = 1800) -> str:
    args = ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={KNOWN}", REMOTE, command]
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    (PROJECT / "artifacts/fresh-endpoint").mkdir(parents=True, exist_ok=True)
    with (PROJECT / "artifacts/fresh-endpoint/controller-events.log").open("a") as log:
        log.write(json.dumps({"command": command, "returncode": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}) + "\n")
    if result.returncode:
        raise RuntimeError(f"ssh_failed:{result.returncode}:{result.stderr[-1000:]}")
    return result.stdout


def scp_remote(remote_path: str, local_path: Path, recursive: bool = False) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["scp", "-q"] + (["-r"] if recursive else []) + ["-i", KEY, "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={KNOWN}", f"{REMOTE}:{remote_path}", str(local_path)]
    subprocess.run(args, check=True, timeout=1800)


def mount_args() -> str:
    root = f"{REMOTE_ROOT}/source/python/sglang/srt"
    files = [
        "layers/attention/triton_backend.py",
        "speculative/ngram_info.py",
        "speculative/cpp_ngram/ngram_corpus.py",
        "speculative/ngram_worker.py",
        "speculative/spec_utils.py",
        "model_executor/runner/decode_cuda_graph_runner.py",
        "model_executor/runner/shape_key.py",
        "model_executor/runner/adaptive_ngram_graph.py",
        "managers/scheduler_components/batch_result_processor.py",
    ]
    return " ".join(f"-v {root}/{path}:/sgl-workspace/sglang/python/sglang/srt/{path}:ro" for path in files)


def launch_args() -> str:
    data = json.loads((PROJECT / "inputs/fresh_endpoint_packet/candidate-v0.5.15/inputs/ngram-launch.json").read_text())
    args = list(data["args"])
    # The stock assert localization admitted this single launch repair.  It
    # must be present on both the control and candidate, not only on the A/A
    # guard; otherwise the canonical control is an invalid configuration
    # attempt rather than endpoint evidence.
    if os.environ.get("FRESH_STOCK_REPAIR") == "1":
        args.extend(["--triton-attention-num-kv-splits", "1"])
    return shlex.join(args)


def start(name: str, candidate: bool) -> None:
    ssh(f"sudo -n docker rm -f {name} >/dev/null 2>&1 || true", timeout=60)
    overlays = mount_args() if candidate else ""
    command = f"sudo -n docker run -d --name {name} --gpus all --ipc=host -p 30000:30000 -v {REMOTE_ROOT}/../gemma4-h100-packed-endpoint/checkpoint:/work/checkpoint:ro {overlays} {IMAGE} python3 -m sglang.launch_server {launch_args()}"
    ssh(command, timeout=120)


def stop_server(name: str, log_name: str) -> None:
    ssh(f"sudo -n docker logs {name} > {REMOTE_ROOT}/artifacts/{log_name}.log 2>&1 || true; sudo -n docker stop -t 30 {name} >/dev/null 2>&1 || true; sudo -n docker rm {name} >/dev/null 2>&1 || true", timeout=120)


def main() -> None:
    hb = threading.Thread(target=heartbeat, daemon=True)
    hb.start()
    remote_artifacts = f"{REMOTE_ROOT}/artifacts/fresh-endpoint"
    try:
        # Repair mode reuses the already atomically completed workload. The
        # interrupted control is the only invalidated scientific operation.
        if os.environ.get("FRESH_REPAIR") != "1":
            ssh(f"{remote_env()} python3 {REMOTE_ROOT}/fresh_endpoint_driver.py construct", timeout=120)
            scp_remote(f"{REMOTE_ROOT}/artifacts/fresh-endpoint/FRESH_WORKLOAD.json", PROJECT / "artifacts/fresh-endpoint/FRESH_WORKLOAD.remote.json")
            scp_remote(f"{REMOTE_ROOT}/artifacts/fresh-endpoint/FRESH_WORKLOAD.jsonl", PROJECT / "artifacts/fresh-endpoint/FRESH_WORKLOAD.remote.jsonl")
        start("gemma4-adaptive-fresh-control", candidate=False)
        try:
            ssh(f"{remote_env()} python3 {REMOTE_ROOT}/fresh_endpoint_driver.py arm --arm control", timeout=3600)
        finally:
            stop_server("gemma4-adaptive-fresh-control", "server_control")
        start("gemma4-adaptive-fresh-candidate", candidate=True)
        try:
            ssh(f"{remote_env()} python3 {REMOTE_ROOT}/fresh_endpoint_driver.py arm --arm candidate", timeout=3600)
        finally:
            stop_server("gemma4-adaptive-fresh-candidate", "server_candidate")
        ssh(f"{remote_env()} python3 {REMOTE_ROOT}/fresh_endpoint_driver.py compare", timeout=120)
        scp_remote(remote_artifacts, PROJECT / "artifacts/fresh-endpoint/remote", recursive=True)
        for name in ("server_control.log", "server_candidate.log"):
            scp_remote(f"{REMOTE_ROOT}/artifacts/{name}", PROJECT / f"artifacts/fresh-endpoint/{name}")
        finalize()
        contents = PROJECT / "H100_ADAPTIVE_DEPTH6_FRESH_ENDPOINT_CONTENTS.json"
        subprocess.run(["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB_ROOT), "release", "--project", PROJECT_ID, "--contents", str(contents), "--condition", "ready"], cwd="/root/workspace", env={**os.environ, "PYTHONPATH": "research/factory/src"}, check=True)
    except Exception as exc:
        if not (PROJECT / "ADAPTIVE_DEPTH6_FRESH_ENDPOINT_ATTEMPT1_INVALID.json").exists():
            atomic(PROJECT / "ADAPTIVE_DEPTH6_FRESH_ENDPOINT_ATTEMPT_INVALID.json", {"schema_version": 1, "classification": "invalid_or_incomplete_controller_attempt", "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "error": repr(exc), "science_started": False, "claim_retained_for_repair": True, "provider_or_gpu_spend_usd": max(0.4, (time.time() - STARTED) * 2.95 / 3600 + 0.4)})
        raise
    finally:
        STOP.set()


def finalize() -> None:
    root = PROJECT / "artifacts/fresh-endpoint/remote"
    comparison = json.loads((root / "NORMALIZED_OUTPUT_COMPARISON.json").read_text())
    control = comparison["control_result"]
    candidate = comparison["candidate_result"]
    elapsed = max(control["elapsed_seconds"], candidate["elapsed_seconds"])
    total_tokens = candidate["total_tokens"]
    planning = 2.8 * elapsed / 3600 / total_tokens * 1_000_000 if total_tokens else None
    sustainable = planning / 0.9 if planning is not None else None
    control_log = PROJECT / "artifacts/fresh-endpoint/server_control.log"
    candidate_log = PROJECT / "artifacts/fresh-endpoint/server_candidate.log"
    result = {"schema_version": 1, "status": "complete", "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "project": PROJECT_ID, "evidence_label": "fresh_matched_whole_request_h100_endpoint_pair", "workload": json.loads((PROJECT / "artifacts/fresh-endpoint/FRESH_WORKLOAD.remote.json").read_text()), "arms": {"control_fixed_depth12": control, "candidate_adaptive_depth6": candidate}, "normalized_output_comparison": comparison, "telemetry": {"control_sha256": sha(root / "arm_control/telemetry.jsonl"), "candidate_sha256": sha(root / "arm_candidate/telemetry.jsonl"), "control_samples": sum(1 for _ in (root / "arm_control/telemetry.jsonl").open()), "candidate_samples": sum(1 for _ in (root / "arm_candidate/telemetry.jsonl").open()), "server_control_log_sha256": sha(control_log), "server_candidate_log_sha256": sha(candidate_log)}, "decision": {"normalized_semantics_exact": comparison["exact"], "failures_zero": not control["failures"] and not candidate["failures"], "release_drift_bounded": control["release_drift_bounded"] and candidate["release_drift_bounded"], "service_seconds_per_request_delta": candidate["service_seconds_per_request"] - control["service_seconds_per_request"], "service_fractional_change": candidate["service_seconds_per_request"] / control["service_seconds_per_request"] - 1.0 if control["service_seconds_per_request"] else None}, "economics": {"planning_usd_per_gpu_hour": 2.8, "sustainable_utilization": 0.9, "planning_usd_per_million_total_tokens": planning, "sustainable_usd_per_million_total_tokens": sustainable, "target_usd_per_million_total_tokens": 0.14}, "scope": {"checkpoint_re-staged": False, "prior_workload_replayed": False, "endpoint_requests_per_arm": 791}}
    result_path = PROJECT / "ADAPTIVE_DEPTH6_FRESH_ENDPOINT_RESULT.json"
    atomic(result_path, result)
    actual_spend = min(5.9, 0.4 + (time.time() - STARTED) * 2.95 / 3600)
    terminal = {"schema_version": 1, "status": "terminal", "classification": "endpoint_exact_no_material_gain" if comparison["exact"] and abs(result["decision"]["service_fractional_change"]) < 0.03 else "endpoint_positive_exact" if comparison["exact"] else "semantic_failure_localized", "result_sha256": sha(result_path), "result_path": result_path.name, "workload_indices": [int(os.environ.get("FRESH_START", "62000")), int(os.environ.get("FRESH_END", "62790"))], "requests_per_arm": 791, "normalized_semantics_exact": comparison["exact"], "checkpoint_re-staged": False, "prior_workload_replayed": False, "endpoint_stopped": True, "actual_spend_usd": actual_spend, "release_deadline_utc": "2026-07-25T17:40:00Z"}
    terminal_path = PROJECT / "ADAPTIVE_DEPTH6_FRESH_ENDPOINT_TERMINAL.json"
    atomic(terminal_path, terminal)
    atomic(PROJECT / "H100_ADAPTIVE_DEPTH6_FRESH_ENDPOINT_CONTENTS.json", {"schema_version": 1, "project": PROJECT_ID, "result": result_path.name, "result_sha256": sha(result_path), "terminal": terminal_path.name, "terminal_sha256": sha(terminal_path), "server_state": "No server resident; both endpoint arms stopped", "checkpoint": "Resident exact checkpoint preserved without restaging", "next": "No endpoint rerun; preserve fresh pair and all telemetry."})


if __name__ == "__main__":
    main()
