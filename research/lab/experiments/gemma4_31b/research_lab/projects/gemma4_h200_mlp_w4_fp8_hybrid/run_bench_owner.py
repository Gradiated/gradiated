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


NAME = "gemma4_h200_mlp_w4_fp8_hybrid"
LAB = pathlib.Path("/root/workspace/research/lab/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path(
    "/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius"
)
KEY_CANDIDATES = (
    pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519"),
    pathlib.Path("/root/.config/gradiated/providers/gcore/id_ed25519"),
)
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
REMOTE = "/home/glmrunner/gemma4-h200-mlp-w4-hybrid"
MAX_CLAIM_SECONDS = 120 * 60


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, **kwargs)


def pool(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            "-m",
            "grad_research.gpu_pool",
            "--lab",
            str(LAB),
            *arguments,
        ],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
        capture_output=True,
        check=check,
    )


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--absolute-deadline-epoch", type=int, required=True)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((PROJECT / "GPU_INPUT_MANIFEST.json").read_text())
    if manifest.get("pass") is not True:
        raise RuntimeError("project_local_manifest_invalid")
    component = PROJECT / manifest["representation"]["component_snapshot"]["path"]
    if sha256(component) != manifest["representation"]["component_snapshot"]["sha256"]:
        raise RuntimeError("component_snapshot_hash_mismatch")
    for section in ("checkpoint",):
        for row in manifest["representation"][section]:
            path = PROJECT / row["path"]
            if path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
                raise RuntimeError(f"project_local_snapshot_invalid:{row['path']}")
    deadline = min(
        args.absolute_deadline_epoch, int(time.time()) + MAX_CLAIM_SECONDS
    )
    started = time.time()
    stop = threading.Event()
    claimed = False
    events = args.artifact_root / "outer-events.jsonl"

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(
                json.dumps(
                    {"epoch": time.time(), "event": event, **fields}, sort_keys=True
                )
                + "\n"
            )

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-500:])

    thread = threading.Thread(target=heartbeat, daemon=True)
    key = KEY_CANDIDATES[0]
    terminal: dict[str, object] = {}
    release_condition = "ready"
    try:
        lease = max(600, deadline - int(time.time()))
        claim = pool(
            "claim",
            "--project",
            NAME,
            "--bench",
            args.bench,
            "--lease-seconds",
            str(lease),
        )
        claimed = True
        emit("claimed", result=json.loads(claim.stdout))
        thread.start()
        sys.path.insert(0, str(NEBIUS))
        from placement_control import extract_public_ipv4, get_instance
        from stock_control import run_ssh

        inventory = json.loads((LAB / "runtime/gpus.json").read_text())
        benches = inventory["benches"]
        bench = benches[args.bench]
        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip:
            raise RuntimeError("typed_provider_boundary:no_public_ip")
        identity = None
        for candidate in KEY_CANDIDATES:
            if candidate.is_file():
                attempt = run_ssh(
                    ip,
                    candidate,
                    "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version",
                    timeout=60,
                )
                identity = attempt
                if attempt.returncode == 0:
                    key = candidate
                    break
        if identity is None or identity.returncode:
            raise RuntimeError("typed_remote_boundary:ssh_identity_failed")
        (args.artifact_root / "remote-identity.stdout").write_text(identity.stdout)
        (args.artifact_root / "remote-identity.stderr").write_text(identity.stderr)
        prepared = run_ssh(
            ip,
            key,
            f"mkdir -p {REMOTE}/input/stack {REMOTE}/w4 {REMOTE}/artifacts",
            timeout=60,
        )
        if prepared.returncode:
            raise RuntimeError("typed_remote_boundary:prepare_failed")

        def ssh(command: str, timeout: int) -> subprocess.CompletedProcess[str]:
            return run_ssh(ip, key, command, timeout=timeout)

        def scp(source: pathlib.Path, destination: str, timeout: int) -> None:
            expected = sha256(source)
            matched = ssh(
                f"test -f {shlex.quote(destination)} && test \"$(sha256sum {shlex.quote(destination)} | awk '{{print $1}}')\" = {expected}",
                min(timeout, 1800),
            )
            if matched.returncode == 0:
                emit("input_matched", name=source.name, sha256=expected)
                return
            partial = f"{destination}.{expected}.part"
            result = run(
                [
                    "scp",
                    "-i",
                    str(key),
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-o",
                    f"UserKnownHostsFile={KNOWN_HOSTS}",
                    str(source),
                    f"glmrunner@{ip}:{partial}",
                ],
                capture_output=True,
                timeout=timeout,
            )
            if result.returncode:
                raise RuntimeError(
                    f"typed_transfer_boundary:scp_failed:{source.name}:{result.stderr[-1000:]}"
                )
            finalized = ssh(
                f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {expected} && chmod 0444 {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {shlex.quote(destination)}",
                min(timeout, 1800),
            )
            if finalized.returncode:
                raise RuntimeError(
                    f"typed_transfer_boundary:finalize_failed:{source.name}"
                )
            emit(
                "input_transferred",
                name=source.name,
                bytes=source.stat().st_size,
                sha256=expected,
            )

        programs = (
            "hybrid_component.py",
            "hybrid_quant_patch.py",
            "sitecustomize.py",
            "build_hybrid_checkpoint.py",
            "remote_hybrid.sh",
            "GPU_INPUT_MANIFEST.json",
        )
        for name in programs:
            scp(PROJECT / name, f"{REMOTE}/input/{name}", deadline - int(time.time()))
        scp(component, f"{REMOTE}/input/{component.name}", deadline - int(time.time()))
        for source in sorted((PROJECT / "inputs" / "stack").iterdir()):
            if source.is_file():
                scp(
                    source,
                    f"{REMOTE}/input/stack/{source.name}",
                    deadline - int(time.time()),
                )
        for row in manifest["representation"]["checkpoint"]:
            source = PROJECT / row["path"]
            scp(source, f"{REMOTE}/w4/{source.name}", deadline - int(time.time()))
        ssh(f"chmod 0555 {REMOTE}/input/remote_hybrid.sh", 60)
        worker = ssh(
            f"bash {REMOTE}/input/remote_hybrid.sh",
            max(600, deadline - int(time.time())),
        )
        (args.artifact_root / "remote.stdout").write_text(worker.stdout)
        (args.artifact_root / "remote.stderr").write_text(worker.stderr)
        emit("worker_returned", returncode=worker.returncode)

        def retrieve(remote: str, local: pathlib.Path, timeout: int = 600) -> bool:
            result = run(
                [
                    "scp",
                    "-i",
                    str(key),
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-o",
                    f"UserKnownHostsFile={KNOWN_HOSTS}",
                    f"glmrunner@{ip}:{remote}",
                    str(local),
                ],
                capture_output=True,
                timeout=timeout,
            )
            return result.returncode == 0

        archive = args.artifact_root / "hybrid-compact.tar.gz"
        retrieve(f"{REMOTE}/hybrid-compact.tar.gz", archive)
        for name in ("WORKER_TERMINAL.json", "INVOCATION_STATE.json"):
            retrieve(f"{REMOTE}/artifacts/{name}", args.artifact_root / name)
        if archive.is_file():
            with tarfile.open(archive) as handle:
                handle.extractall(args.artifact_root / "result")
        invocation = (
            json.loads((args.artifact_root / "INVOCATION_STATE.json").read_text())
            if (args.artifact_root / "INVOCATION_STATE.json").is_file()
            else None
        )
        worker_terminal = (
            json.loads((args.artifact_root / "WORKER_TERMINAL.json").read_text())
            if (args.artifact_root / "WORKER_TERMINAL.json").is_file()
            else None
        )
        if worker_terminal is None or invocation is None:
            release_condition = "maintenance"
            raise RuntimeError("typed_retrieval_boundary:compact_terminal_missing")
        terminal = {
            "schema_version": 1,
            "classification": worker_terminal["classification"],
            "worker_returncode": worker.returncode,
            "worker_terminal": worker_terminal,
            "invocation_state": invocation,
            "claimed_seconds": time.time() - started,
            "actual_spend_usd": (time.time() - started) * 2.46 / 3600,
            "artifact_root": str(args.artifact_root),
        }
        atomic(args.artifact_root / "OWNER_TERMINAL.json", terminal)
        pool(
            "update",
            "--project",
            NAME,
            "--contents-json",
            json.dumps(
                {
                    "project": NAME,
                    "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                    "checkpoint": "Exact current checkpoint retained at /home/glmrunner/gemma4-h200-dense-fp8-streamk/checkpoint; immutable project W4 snapshot retained at /home/glmrunner/gemma4-h200-mlp-w4-hybrid/w4.",
                    "image": "SGLang v0.5.13 digest 6113665 retained.",
                    "runtime": f"Mixed W4/FP8 result: {worker_terminal['classification']}.",
                    "artifacts": "Compact terminal and raw remote diagnostics retrieved project-locally.",
                    "server_state": "Final hybrid server retained if endpoint stage completed; otherwise no endpoint server retained.",
                }
            ),
        )
    except Exception as error:
        terminal = {
            "schema_version": 1,
            "classification": "owner_failure",
            "error": {"type": type(error).__name__, "message": str(error)[:4000]},
            "claimed_seconds": time.time() - started,
            "actual_spend_usd": (time.time() - started) * 2.46 / 3600,
            "artifact_root": str(args.artifact_root),
        }
        atomic(args.artifact_root / "OWNER_TERMINAL.json", terminal)
    finally:
        stop.set()
        if claimed:
            pool(
                "release",
                "--project",
                NAME,
                "--condition",
                release_condition,
                check=False,
            )
    return 0 if terminal.get("classification") not in ("owner_failure",) else 1


if __name__ == "__main__":
    raise SystemExit(main())
