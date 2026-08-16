#!/usr/bin/env python3
"""Bounded outer owner: claim heartbeat, immutable staging, run, retrieve, release."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tarfile
import threading
import time

PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
NAME = "gemma4_h200_ngram_grammar_safe_routing_endpoint"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
REMOTE = "/home/glmrunner/gemma4-h200-ngram-grammar-safe-routing"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"

def run(cmd: list[str], **kwargs):
    return subprocess.run(cmd, text=True, capture_output=True, **kwargs)

def pool(*args: str):
    return run(["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args], env={**os.environ, "PYTHONPATH": str(FACTORY)})

def digest(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(16 * 1024 * 1024): h.update(block)
    return h.hexdigest()

def atomic(path: pathlib.Path, value: object) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)

def ssh(ip: str, command: str, timeout: int = 60):
    return run(["ssh", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", f"glmrunner@{ip}", command], timeout=timeout)

def scp_to(ip: str, source: pathlib.Path, target: str, timeout: int = 600):
    return run(["scp", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", str(source), f"glmrunner@{ip}:{target}"], timeout=timeout)

def scp_from(ip: str, source: str, target: pathlib.Path, timeout: int = 600):
    return run(["scp", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", f"glmrunner@{ip}:{source}", str(target)], timeout=timeout)

def main() -> int:
    artifact = PROJECT / "artifacts" / ("grammar-safe-" + time.strftime("%Y%m%dt%H%M%SZ", time.gmtime()))
    artifact.mkdir(parents=True, exist_ok=False)
    claimed = True
    stop = threading.Event()
    def heartbeat():
        while not stop.wait(45):
            pool("heartbeat", "--project", NAME)
    thread = threading.Thread(target=heartbeat, daemon=True)
    try:
        inventory = json.loads((LAB / "runtime/gpus.json").read_text())
        benches = inventory["benches"]
        bench = benches[BENCH] if isinstance(benches, dict) else next(row for row in benches if row["id"] == BENCH)
        sys.path.insert(0, str(NEBIUS))
        from placement_control import extract_public_ipv4, get_instance
        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip: raise RuntimeError("typed_provider_boundary:no_public_ip")
        identity = ssh(ip, "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version")
        (artifact / "remote-identity.stdout").write_text(identity.stdout); (artifact / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode: raise RuntimeError("typed_remote_boundary:ssh_identity_failed")
        thread.start()
        ssh(ip, f"mkdir -p {REMOTE}/input {REMOTE}/artifacts", 60)
        files = ["sitecustomize.py", "token_trace_hook.py", "remote_pair.py", "remote_candidate_only.py", "ROUTING_CONTRACT.json", "inputs/bound/exact_runner.py", "inputs/bound/endpoint_entrypoint.py"]
        for rel in files:
            source = PROJECT / rel; target = f"{REMOTE}/input/{pathlib.Path(rel).name}"
            expected = digest(source)
            check = ssh(ip, f"test -f {shlex.quote(target)} && test \"$(sha256sum {shlex.quote(target)} | awk '{{print $1}}')\" = {expected}")
            if check.returncode:
                partial = f"{target}.{expected}.part"
                transfer = scp_to(ip, source, partial)
                if transfer.returncode: raise RuntimeError(f"typed_transfer_boundary:{rel}:{transfer.stderr[-400:]}")
                final = ssh(ip, f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {expected} && chmod 0444 {shlex.quote(partial)} && mv {shlex.quote(partial)} {shlex.quote(target)}")
                if final.returncode: raise RuntimeError(f"typed_finalize_boundary:{rel}")
        command = f"cd {REMOTE} && timeout --signal=TERM 480 python3 input/remote_candidate_only.py"
        worker = ssh(ip, command, 540)
        (artifact / "worker.stdout").write_text(worker.stdout); (artifact / "worker.stderr").write_text(worker.stderr)
        compact = ssh(ip, f"cd {REMOTE} && tar -czf compact.tar.gz artifacts input/remote_pair.py input/sitecustomize.py && sha256sum compact.tar.gz", 120)
        (artifact / "compact-manifest.stdout").write_text(compact.stdout); (artifact / "compact-manifest.stderr").write_text(compact.stderr)
        archive_part = artifact / ".compact.tar.gz.part"
        if scp_from(ip, f"{REMOTE}/compact.tar.gz", archive_part, 600).returncode: raise RuntimeError("typed_retrieval_boundary:compact")
        archive_part.replace(artifact / "compact.tar.gz")
        with tarfile.open(artifact / "compact.tar.gz", "r:gz") as bundle: bundle.extractall(artifact / "retrieved", filter="data")
        terminal = json.loads((artifact / "retrieved/artifacts/TERMINAL.json").read_text())
        atomic(artifact / "TERMINAL.json", terminal)
        atomic(PROJECT / "LATEST_TERMINAL.json", {"artifact_root": str(artifact.relative_to(PROJECT)), **terminal})
        return 0 if terminal.get("pass") else 72
    except Exception as exc:
        atomic(PROJECT / "EXTERNAL_BLOCKER.json", {"classification": "typed_remote_orchestration_boundary", "error": f"{type(exc).__name__}: {exc}", "artifact_root": str(artifact.relative_to(PROJECT))})
        return 75
    finally:
        stop.set()
        if thread.is_alive(): thread.join(timeout=2)
        if claimed:
            release = pool("release", "--project", NAME, "--condition", "ready")
            (artifact / "release.stdout").write_text(release.stdout); (artifact / "release.stderr").write_text(release.stderr)

if __name__ == "__main__":
    raise SystemExit(main())
