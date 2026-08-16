#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


NAME = "gemma4_h200_v0513_fp8_qkv_residual_profile"
LAB = pathlib.Path("/root/workspace/research/lab/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
REMOTE = "/home/glmrunner/gemma4-h200-v0513-fp8-qkv-residual-profile"
ATTENTION_SHA256 = "4e11a14e2dc149789a4b4350e02de3d3283ad88fc259d6417f05a734fc1451d8"


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, **kwargs)


def pool(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *arguments],
        env={**os.environ, "PYTHONPATH": str(FACTORY)}, capture_output=True, check=check,
    )


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def scp_to(ip: str, source: pathlib.Path, destination: str, timeout: int = 180) -> None:
    result = run([
        "scp", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", str(source), f"glmrunner@{ip}:{destination}",
    ], capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"typed_transfer_boundary:{source.name}:{result.stderr[-1000:]}")


def scp_from(ip: str, source: str, destination: pathlib.Path, timeout: int = 300) -> None:
    result = run([
        "scp", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", f"glmrunner@{ip}:{source}", str(destination),
    ], capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"typed_retrieval_boundary:{source}:{result.stderr[-1000:]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--absolute-deadline-epoch", type=int, required=True)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    events = args.artifact_root / "outer-events.jsonl"

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(json.dumps({"epoch": time.time(), "event": event, **fields}, sort_keys=True) + "\n")
            handle.flush()

    status = json.loads((PROJECT / "STATUS.json").read_text())
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = benches[args.bench] if isinstance(benches, dict) else next(row for row in benches if row["id"] == args.bench)
    if bench["accelerator"] != "nvidia-h200-sxm":
        raise RuntimeError("typed_pool_boundary:bench_not_h200")
    rate = float(bench["hourly_cost_usd"])
    prior_spend = float(status["measured_project_spend_usd"])
    budget_deadline = int(time.time() + (8.0 - prior_spend) * 3600 / rate)
    deadline = min(args.absolute_deadline_epoch, budget_deadline)
    started = time.time()
    claimed = False
    stop = threading.Event()
    terminal: dict[str, object] = {}
    release_condition = "ready"

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-500:])

    thread = threading.Thread(target=heartbeat, daemon=True)
    ip: str | None = None
    try:
        lease = max(600, deadline - int(time.time()))
        claim = pool("claim", "--project", NAME, "--bench", args.bench, "--lease-seconds", str(lease))
        claimed = True
        emit("claimed", claim=json.loads(claim.stdout))
        thread.start()
        sys.path.insert(0, str(NEBIUS))
        from placement_control import extract_public_ipv4, get_instance
        from stock_control import run_ssh

        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip:
            raise RuntimeError("typed_provider_boundary:no_public_ip")
        identity = run_ssh(ip, KEY, "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version", timeout=60)
        (args.artifact_root / "remote-identity.stdout").write_text(identity.stdout)
        (args.artifact_root / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_remote_boundary:ssh_identity_failed")
        prepare = run_ssh(ip, KEY, f"mkdir -p {REMOTE}/input {REMOTE}/global-ncu-artifacts", timeout=60)
        if prepare.returncode:
            raise RuntimeError("typed_remote_boundary:prepare_failed")

        sources = {
            "remote_global_ncu.sh": PROJECT / "remote_global_ncu.sh",
            "ncu_exact_request.py": PROJECT / "ncu_exact_request.py",
            "sitecustomize.py": PROJECT / "residual_sitecustomize.py",
            "attention_intervention.py": PROJECT / "intervention/attention_deferred_local_kv.py",
        }
        if sha256(sources["attention_intervention.py"]) != ATTENTION_SHA256:
            raise RuntimeError("retained_attention_identity_mismatch")
        for remote_name, source in sources.items():
            digest = sha256(source)
            partial = f"{REMOTE}/input/.{remote_name}.{digest}.part"
            scp_to(ip, source, partial)
            finalized = run_ssh(ip, KEY, f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {digest} && chmod 0444 {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {REMOTE}/input/{remote_name}", timeout=60)
            if finalized.returncode:
                raise RuntimeError(f"typed_transfer_boundary:finalize:{remote_name}")
            emit("staged", name=remote_name, sha256=digest)

        timeout = max(600, deadline - int(time.time()) - 300)
        worker = run_ssh(ip, KEY, f"timeout --signal=TERM {timeout} bash {REMOTE}/input/remote_global_ncu.sh", timeout=timeout + 60)
        (args.artifact_root / "worker.stdout").write_text(worker.stdout)
        (args.artifact_root / "worker.stderr").write_text(worker.stderr)
        emit("worker_returned", returncode=worker.returncode)
        remote_terminal = run_ssh(ip, KEY, f"cat {REMOTE}/global-ncu-artifacts/TERMINAL.json", timeout=30)
        if remote_terminal.returncode or not remote_terminal.stdout.strip():
            raise RuntimeError("typed_retrieval_boundary:terminal_missing")
        worker_terminal = json.loads(remote_terminal.stdout)
        atomic(args.artifact_root / "REMOTE_WORKER_TERMINAL.json", worker_terminal)
        partial = args.artifact_root / ".global-ncu-compact.tar.gz.part"
        sidecar = args.artifact_root / "global-ncu-compact.tar.gz.sha256"
        scp_from(ip, f"{REMOTE}/global-ncu-compact.tar.gz", partial)
        scp_from(ip, f"{REMOTE}/global-ncu-compact.tar.gz.sha256", sidecar, 60)
        if sha256(partial) != sidecar.read_text().split()[0]:
            raise RuntimeError("typed_retrieval_boundary:compact_hash_mismatch")
        archive = args.artifact_root / "global-ncu-compact.tar.gz"
        os.replace(partial, archive)
        destination = args.artifact_root / "global_ncu"
        destination.mkdir()
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(destination, filter="data")
        exposure = time.time() - started
        terminal = {
            "schema_version": 1, "status": "terminal", "pass": worker.returncode == 0 and worker_terminal.get("classification") == "ncu_complete",
            "classification": worker_terminal.get("classification", "ncu_owner_boundary"), "worker_terminal": worker_terminal,
            "provider_exposure_seconds": exposure, "provider_spend_usd": exposure * rate / 3600,
            "cumulative_provider_spend_usd": prior_spend + exposure * rate / 3600,
        }
        atomic(args.artifact_root / "TERMINAL.json", terminal)
        emit("terminal", classification=terminal["classification"])
        return 0 if terminal["pass"] else 1
    except Exception as error:
        if "ssh_identity" in str(error) or "no_public_ip" in str(error):
            release_condition = "maintenance"
        exposure = time.time() - started if claimed else 0
        terminal = {"schema_version": 1, "status": "terminal", "pass": False, "classification": "typed_external_or_owner_boundary", "error": {"type": type(error).__name__, "message": str(error)}, "provider_exposure_seconds": exposure, "provider_spend_usd": exposure * rate / 3600 if claimed else 0, "cumulative_provider_spend_usd": prior_spend + exposure * rate / 3600 if claimed else prior_spend}
        atomic(args.artifact_root / "TERMINAL.json", terminal)
        emit("outer_error", message=str(error))
        return 1
    finally:
        stop.set()
        if thread.is_alive():
            thread.join(timeout=5)
        if claimed:
            contents = {"project": NAME, "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4", "checkpoint": f"Exact immutable checkpoint retained at {REMOTE}/checkpoint.", "image": "Pinned SGLang v0.5.13 image retained.", "runtime": f"Global attention NCU terminal: {terminal.get('classification', 'owner_boundary')}.", "caches": "Dynamic-FP8, QKV, Triton, NCU, and CUDA graph caches retained.", "server_state": "Diagnostic server stopped after NCU report flush.", "artifacts": f"NCU compact evidence retrieved under {args.artifact_root}."}
            atomic(args.artifact_root / "BENCH_CONTENTS.json", contents)
            release = pool("release", "--project", NAME, "--condition", release_condition, "--contents", str(args.artifact_root / "BENCH_CONTENTS.json"), check=False)
            emit("released", returncode=release.returncode, stderr=release.stderr[-500:])


if __name__ == "__main__":
    raise SystemExit(main())
