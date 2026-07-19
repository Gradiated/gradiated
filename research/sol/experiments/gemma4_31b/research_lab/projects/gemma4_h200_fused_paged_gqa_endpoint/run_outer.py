#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import tarfile
import threading
import time


PROJECT = "gemma4_h200_fused_paged_gqa_endpoint"
BENCH = "h200-paged-gqa-e00ar2p5bk4a8qgqa9"
LAB = pathlib.Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS_TOOLS = pathlib.Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
SSH_KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, **kwargs)


def pool(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(
        [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *arguments],
        env={**__import__("os").environ, "PYTHONPATH": str(FACTORY)},
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
    try:
        claim = pool("claim", "--project", PROJECT, "--bench", BENCH, "--lease-seconds", "600")
        claimed = True
        emit("claimed", stdout=claim.stdout.strip())
        heartbeat_thread.start()

        sys.path.insert(0, str(NEBIUS_TOOLS))
        from placement_control import extract_public_ipv4, get_instance
        from stock_control import run_ssh, scp_from, scp_to

        provider = get_instance("computeinstance-e00ar2p5bk4a8qgqa9")
        ip = extract_public_ipv4(provider)
        if not ip:
            raise RuntimeError("typed_provider_boundary:no_public_ip")
        identity = run_ssh(
            ip,
            SSH_KEY,
            "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version || true",
            timeout=60,
        )
        (args.artifact_root / "remote-identity.stdout").write_text(identity.stdout)
        (args.artifact_root / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_remote_boundary:ssh_identity_failed")
        prepare = run_ssh(ip, SSH_KEY, "mkdir -p /home/glmrunner/gemma-paged-gqa/input /home/glmrunner/gemma-paged-gqa/artifacts/component", timeout=60)
        if prepare.returncode:
            raise RuntimeError("typed_remote_boundary:prepare_failed")
        project_root = pathlib.Path(__file__).resolve().parent
        scp_to(ip, SSH_KEY, [project_root / "paged_gqa_discriminator.py", project_root / "remote_component.sh"], "/home/glmrunner/gemma-paged-gqa/input/")
        remote_command = "bash /home/glmrunner/gemma-paged-gqa/input/remote_component.sh"
        remaining = max(1, args.deadline_epoch - int(time.time()))
        worker = run_ssh(ip, SSH_KEY, remote_command, timeout=remaining)
        (args.artifact_root / "remote-worker.stdout").write_text(worker.stdout)
        (args.artifact_root / "remote-worker.stderr").write_text(worker.stderr)
        remote_started = run_ssh(ip, SSH_KEY, "test -f /home/glmrunner/gemma-paged-gqa/artifacts/component/SCIENTIFIC_STARTED", timeout=30).returncode == 0
        remote_terminal = run_ssh(ip, SSH_KEY, "test -f /home/glmrunner/gemma-paged-gqa/artifacts/component/TERMINAL.json", timeout=30).returncode == 0
        emit("worker_finished", returncode=worker.returncode, scientific_started=remote_started, terminal_present=remote_terminal)
        if worker.returncode or not remote_terminal:
            boundary = "scientific_runtime_failure" if remote_started else "preinvocation_wiring_failure"
            atomic_json(args.artifact_root / "FAILURE.json", {"type": boundary, "returncode": worker.returncode, "scientific_started": remote_started, "terminal_present": remote_terminal})
            raise RuntimeError(boundary)
        retrieved = args.artifact_root / "component"
        retrieved.mkdir()
        archive_partial = args.artifact_root / ".component.tar.gz.partial"
        sidecar = args.artifact_root / "component.tar.gz.sha256"
        scp_from(ip, SSH_KEY, "/home/glmrunner/gemma-paged-gqa/component.tar.gz", archive_partial)
        scp_from(ip, SSH_KEY, "/home/glmrunner/gemma-paged-gqa/component.tar.gz.sha256", sidecar)
        digest = hashlib.sha256(archive_partial.read_bytes()).hexdigest()
        if digest != sidecar.read_text().split()[0]:
            raise RuntimeError("typed_retrieval_boundary:archive_hash_mismatch")
        archive = args.artifact_root / "component.tar.gz"
        archive_partial.replace(archive)
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(retrieved, filter="data")
        terminal = json.loads((retrieved / "TERMINAL.json").read_text())
        emit("terminal_retrieved", terminal=terminal)
        if terminal.get("pass") is True:
            raise RuntimeError("unexpected_component_pass_requires_conditional_endpoint")
        return 0
    except Exception as error:
        emit("outer_error", error_type=type(error).__name__, message=str(error))
        return 1
    finally:
        heartbeat_stop.set()
        if heartbeat_thread.is_alive():
            heartbeat_thread.join(timeout=5)
        if claimed:
            contents = {
                "project": PROJECT,
                "model": "google/gemma-4-31B-it exact attention shapes",
                "checkpoint": "Project-local immutable checkpoint snapshot was not staged because the component did not promote.",
                "image": "Pinned SGLang v0.5.12 image pulled and retained.",
                "runtime": "Checkpoint-free exact-shape stock versus direct grouped paged native-GQA component discriminator completed.",
                "caches": "Pinned image plus Triton compilation cache retained on the boot disk.",
                "server_state": "No server; conditional endpoint not started.",
                "artifacts": "Component terminal and raw timing/oracle/telemetry retrieved project-locally.",
            }
            contents_path = args.artifact_root / "BENCH_CONTENTS.json"
            atomic_json(contents_path, contents)
            release = pool("release", "--project", PROJECT, "--condition", "ready", "--contents", str(contents_path), check=False)
            emit("released", returncode=release.returncode, stdout=release.stdout.strip(), stderr=release.stderr[-1000:])


if __name__ == "__main__":
    raise SystemExit(main())
