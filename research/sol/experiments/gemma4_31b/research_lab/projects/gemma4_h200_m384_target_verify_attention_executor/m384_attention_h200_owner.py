#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[6] / "research" / "factory" / "src"))
LAB = ROOT.parent.parent
PROJECT = "gemma4_h200_m384_target_verify_attention_executor"
BENCH = "h200-downproj-computeinstance-e00qft1sf416qp6knw"


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(tmp.read_text())
    os.replace(tmp, path)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", required=True)
    parser.add_argument("--artifact-root", required=True)
    args = parser.parse_args()
    binding = ROOT / args.binding
    artifact = (ROOT / args.artifact_root).resolve()
    artifact.mkdir(parents=True, exist_ok=True)
    ready = artifact / "OWNER_READY"
    state = artifact / "OWNER_PROGRESS.json"
    now = dt.datetime.now(dt.UTC)
    deadline = dt.datetime(2026, 7, 30, 10, 49, tzinfo=dt.UTC)
    if now >= deadline:
        atomic_json(state, {"phase": "expired_before_claim", "deadline_utc": deadline.isoformat().replace("+00:00", "Z")})
        return 30
    bound = json.loads(binding.read_text())
    files = [ROOT / name for name in ("m384_grouped_attention_sm90a.cu", "m384_attention_h200_runner.py", "m384_attention_h200_owner.py")]
    atomic_json(ready, {"phase": "owner_dynamic_entry", "binding_sha256": sha(binding), "file_hashes": {item.name: sha(item) for item in files}, "at_utc": now.isoformat().replace("+00:00", "Z")})
    claim = run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), "claim", "--project", PROJECT, "--bench", BENCH, "--lease-seconds", "2220"], timeout=30)
    if claim.returncode:
        atomic_json(state, {"phase": "claim_failed", "stdout": claim.stdout, "stderr": claim.stderr, "exit_code": claim.returncode})
        return 31
    claim_row = json.loads(claim.stdout)
    claimed_at = claim_row["claim"]["claimed_at"]
    atomic_json(state, {"phase": "claimed", "claimed_at": claimed_at, "deadline_utc": "2026-07-30T10:49:00Z", "bench": BENCH})
    identity = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
    if not identity.is_file():
        atomic_json(state, {"phase": "retained_repair", "classification": "local_ssh_identity_missing", "claimed_at": claimed_at})
        return 32
    # Stage only immutable bytes under this project; the runner refuses an
    # absent producer capture rather than generating tensors.
    remote = "glmrunner@89.169.99.32"
    remote_root = "/home/glmrunner/m384-attention"
    remote_mkdir = run(["ssh", "-i", str(identity), "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts", remote, f"mkdir -p {remote_root}/out"], timeout=30)
    if remote_mkdir.returncode:
        atomic_json(state, {"phase": "retained_repair", "classification": "remote_stage_root_failed", "stdout": remote_mkdir.stdout[-4000:], "stderr": remote_mkdir.stderr[-4000:], "claimed_at": claimed_at})
        return 33
    stage = run(["scp", "-i", str(identity), "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts", *map(str, files[:-1]), f"{remote}:{remote_root}/"], timeout=120)
    if stage.returncode:
        atomic_json(state, {"phase": "retained_repair", "classification": "remote_stage_failed", "stdout": stage.stdout[-4000:], "stderr": stage.stderr[-4000:], "claimed_at": claimed_at})
        return 34
    heartbeat = run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), "heartbeat", "--project", PROJECT, "--bench", BENCH, "--expected-claimed-at", claimed_at], timeout=20)
    command = "mkdir -p /home/glmrunner/m384-attention/out && sudo -n docker run --rm --gpus all -v /home/glmrunner/m384-attention:/work -w /work docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6 python3 m384_attention_h200_runner.py --packet /work/producer_packet.json --source /work/m384_grouped_attention_sm90a.cu --output /work/out/TERMINAL.json"
    worker = run(["ssh", "-i", str(identity), "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts", remote, command], timeout=max(1, int((deadline - dt.datetime.now(dt.UTC)).total_seconds())))
    terminal_local = artifact / "REMOTE_WORKER_CAPTURE.json"
    atomic_json(terminal_local, {"exit_code": worker.returncode, "stdout": worker.stdout[-8000:], "stderr": worker.stderr[-8000:], "claimed_at": claimed_at, "heartbeat_exit_code": heartbeat.returncode})
    retrieved = run(["scp", "-i", str(identity), "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts", f"{remote}:{remote_root}/out/TERMINAL.json", str(artifact / "REMOTE_TERMINAL.json")], timeout=30)
    terminal_path = artifact / "REMOTE_TERMINAL.json"
    classification = "remote_terminal_unretrieved"
    if retrieved.returncode == 0 and terminal_path.is_file():
        classification = json.loads(terminal_path.read_text()).get("classification", "remote_terminal_unclassified")
    repair_ready = ROOT / "REPAIR_READY.json"
    atomic_json(repair_ready, {"schema_version": 1, "repair_id": "m384-producer-capture-1", "classification": classification, "retry_scope": "stage_provenance_bound_producer_capture_and_rerun_component_only", "deadline_utc": "2026-07-30T10:49:00Z", "worker_capture_sha256": sha(terminal_local)})
    # Retain the warm claim and keep heartbeats alive while a same-contract
    # repair request is possible.  The absolute release fence is the only
    # fallback release path for this non-terminal integration boundary.
    request = ROOT / "REPAIR_REQUEST.json"
    while dt.datetime.now(dt.UTC) < deadline:
        beat = run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), "heartbeat", "--project", PROJECT, "--bench", BENCH, "--expected-claimed-at", claimed_at], timeout=20)
        atomic_json(state, {"phase": "retained_repair", "classification": classification, "claimed_at": claimed_at, "worker_capture": str(terminal_local), "remote_terminal": str(terminal_path), "heartbeat_exit_code": beat.returncode, "repair_request_present": request.is_file(), "deadline_utc": "2026-07-30T10:49:00Z"})
        if request.is_file():
            atomic_json(state, {"phase": "repair_request_requires_director_rebind", "classification": classification, "claimed_at": claimed_at, "request_sha256": sha(request)})
        time.sleep(20)
    contents = artifact / "RELEASE_CONTENTS.json"
    atomic_json(contents, {"state": "m384_attention_component_repair_boundary", "artifacts": f"Remote terminal {terminal_path.name}; source and runner staged; no synthetic Q/K/V generated.", "scientific_terminal": "No interpretable component result; producer capture unavailable or exact consumer adapter repair pending."})
    release = run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), "release", "--project", PROJECT, "--bench", BENCH, "--expected-claimed-at", claimed_at, "--condition", "maintenance", "--contents", str(contents)], timeout=30)
    atomic_json(state, {"phase": "released_absolute_deadline", "classification": classification, "claimed_at": claimed_at, "release_exit_code": release.returncode, "release_stdout": release.stdout, "release_stderr": release.stderr})
    return 0 if release.returncode == 0 else 35


if __name__ == "__main__":
    raise SystemExit(main())
