#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import threading
import time


PROJECT = "gemma4_h200_local_kv_head8_discriminator"
BENCH = "h200-local-kv8-e00tnyt66qqx2n7qqg"
INSTANCE = "computeinstance-e00tnyt66qqx2n7qqg"
LAB = pathlib.Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS_TOOLS = pathlib.Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
SSH_KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, **kwargs)


def pool(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(
        [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *arguments],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
        capture_output=True,
        check=check,
    )


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--deadline-epoch", type=int, required=True)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    events = args.artifact_root / "outer-events.jsonl"

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(json.dumps({"time": time.time(), "event": event, **fields}, sort_keys=True) + "\n")

    claimed = False
    terminal: dict[str, object] | None = None
    heartbeat_stop = threading.Event()

    def heartbeat() -> None:
        while not heartbeat_stop.wait(45):
            result = pool("heartbeat", "--project", PROJECT, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-1000:])

    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    failure_condition = "ready"
    scientific_started = False
    try:
        claim = pool("claim", "--project", PROJECT, "--bench", BENCH, "--lease-seconds", "600")
        claimed = True
        emit("claimed", stdout=claim.stdout.strip())
        heartbeat_thread.start()

        sys.path.insert(0, str(NEBIUS_TOOLS))
        from placement_control import extract_public_ipv4, get_instance
        from stock_control import run_ssh, scp_from, scp_to

        provider = get_instance(INSTANCE)
        ip = extract_public_ipv4(provider)
        if not ip:
            raise RuntimeError("typed_provider_boundary:no_public_ip")
        identity = None
        for attempt in range(1, 7):
            identity = run_ssh(ip, SSH_KEY, "hostname; nvidia-smi --query-gpu=name,uuid,memory.total --format=csv,noheader; sudo docker --version || true", timeout=60)
            (args.artifact_root / f"remote-identity-attempt-{attempt}.stdout").write_text(identity.stdout)
            (args.artifact_root / f"remote-identity-attempt-{attempt}.stderr").write_text(identity.stderr)
            emit("identity_attempt", attempt=attempt, returncode=identity.returncode)
            if identity.returncode == 0:
                break
            time.sleep(10)
        if identity is None or identity.returncode:
            raise RuntimeError("typed_remote_boundary:ssh_identity_failed")
        prepare = run_ssh(ip, SSH_KEY, "mkdir -p /home/glmrunner/gemma-local-kv8/input /home/glmrunner/gemma-local-kv8/artifacts/component", timeout=60)
        if prepare.returncode:
            raise RuntimeError("typed_remote_boundary:prepare_failed")
        project_root = pathlib.Path(__file__).resolve().parent
        for attempt in range(1, 4):
            scp_to(ip, SSH_KEY, [project_root / "local_kv_head_discriminator.py", project_root / "remote_component.sh"], "/home/glmrunner/gemma-local-kv8/input/")
            emit(
                "worker_bytes_staged",
                attempt=attempt,
                benchmark_sha256=hashlib.sha256((project_root / "local_kv_head_discriminator.py").read_bytes()).hexdigest(),
                launcher_sha256=hashlib.sha256((project_root / "remote_component.sh").read_bytes()).hexdigest(),
            )
            remaining = max(1, args.deadline_epoch - int(time.time()))
            worker = run_ssh(ip, SSH_KEY, "bash /home/glmrunner/gemma-local-kv8/input/remote_component.sh", timeout=remaining)
            (args.artifact_root / f"remote-worker-attempt-{attempt}.stdout").write_text(worker.stdout)
            (args.artifact_root / f"remote-worker-attempt-{attempt}.stderr").write_text(worker.stderr)
            started_check = run_ssh(ip, SSH_KEY, "test -f /home/glmrunner/gemma-local-kv8/artifacts/component/SCIENTIFIC_STARTED", timeout=30)
            terminal_check = run_ssh(ip, SSH_KEY, "test -f /home/glmrunner/gemma-local-kv8/artifacts/component/TERMINAL.json", timeout=30)
            scientific_started = started_check.returncode == 0
            remote_terminal = terminal_check.returncode == 0
            emit("worker_finished", attempt=attempt, returncode=worker.returncode, scientific_started=scientific_started, terminal_present=remote_terminal)
            if worker.returncode == 0 and remote_terminal:
                break
            diagnostic = run_ssh(ip, SSH_KEY, "tail -n 240 /home/glmrunner/gemma-local-kv8/artifacts/component/benchmark.stderr 2>/dev/null; tail -n 120 /home/glmrunner/gemma-local-kv8/artifacts/component/image-pull.stderr 2>/dev/null; sudo journalctl -u docker --no-pager -n 80 2>/dev/null", timeout=60)
            (args.artifact_root / f"remote-diagnostic-attempt-{attempt}.stdout").write_text(diagnostic.stdout)
            (args.artifact_root / f"remote-diagnostic-attempt-{attempt}.stderr").write_text(diagnostic.stderr)
            if scientific_started:
                raise RuntimeError("scientific_runtime_failure")
            if attempt == 3:
                raise RuntimeError("preinvocation_wiring_failure_after_repairs")
            emit("repair_window", attempt=attempt, reason="preinvocation_wiring_failure", seconds=45)
            time.sleep(45)
        retrieved = args.artifact_root / "component"
        retrieved.mkdir()
        archive_partial = args.artifact_root / ".component.tar.gz.partial"
        sidecar = args.artifact_root / "component.tar.gz.sha256"
        scp_from(ip, SSH_KEY, "/home/glmrunner/gemma-local-kv8/component.tar.gz", archive_partial)
        scp_from(ip, SSH_KEY, "/home/glmrunner/gemma-local-kv8/component.tar.gz.sha256", sidecar)
        digest = hashlib.sha256(archive_partial.read_bytes()).hexdigest()
        if digest != sidecar.read_text().split()[0]:
            raise RuntimeError("typed_retrieval_boundary:archive_hash_mismatch")
        archive = args.artifact_root / "component.tar.gz"
        archive_partial.replace(archive)
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(retrieved, filter="data")
        terminal = json.loads((retrieved / "TERMINAL.json").read_text())
        emit("terminal_retrieved", terminal=terminal)
        return 0
    except Exception as error:
        failure_condition = "maintenance" if "provider_boundary" in str(error) or "remote_boundary" in str(error) else "ready"
        emit("outer_error", error_type=type(error).__name__, message=str(error), scientific_started=scientific_started)
        atomic_json(args.artifact_root / "FAILURE.json", {"type": str(error), "scientific_started": scientific_started})
        return 1
    finally:
        heartbeat_stop.set()
        if heartbeat_thread.is_alive():
            heartbeat_thread.join(timeout=5)
        if claimed:
            completed = terminal is not None
            contents = {
                "project": PROJECT,
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4 exact local-attention shapes",
                "checkpoint": "Not staged; the checkpoint-free local-KV-head discriminator does not consume model weights.",
                "image": "Pinned SGLang v0.5.12 image retained on disk after the discriminator." if completed else "Pinned SGLang image may be partially or fully pulled; inspect diagnostics before reuse.",
                "runtime": "Paired exact-shape 16-versus-8 local-KV-head discriminator completed." if completed else "Discriminator ended at a typed boundary; see project-local diagnostics.",
                "caches": "Pinned image and Triton/CUDA compilation caches retained.",
                "server_state": "No server; checkpoint-free component only.",
                "artifacts": "Typed terminal, raw paired rows, kernel trace, source snapshot, and GPU telemetry retrieved project-locally." if completed else "Failure diagnostics retained project-locally.",
                "export": "No export.",
            }
            contents_path = args.artifact_root / "BENCH_CONTENTS.json"
            atomic_json(contents_path, contents)
            release = pool("release", "--project", PROJECT, "--condition", failure_condition, "--contents", str(contents_path), check=False)
            emit("released", condition=failure_condition, returncode=release.returncode, stdout=release.stdout.strip(), stderr=release.stderr[-1000:])


if __name__ == "__main__":
    raise SystemExit(main())
