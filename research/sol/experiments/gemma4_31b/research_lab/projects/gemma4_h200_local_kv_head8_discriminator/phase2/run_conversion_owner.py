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
PROJECT_ROOT = LAB / "projects" / PROJECT
PHASE2 = PROJECT_ROOT / "phase2"
CHECKPOINT = PROJECT_ROOT / "inputs" / "checkpoint"
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS_TOOLS = pathlib.Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
SSH_KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
REMOTE = "/home/glmrunner/gemma-local-kv8"
RUN_ID = "local-kv8-conversion-20260719t-phase2"
BOUND_FILES = (
    "TRAINING_CONTRACT.json",
    "CHECKPOINT_SHA256.txt",
    "distill_local_kv8.py",
    "remote_conversion.sh",
    "patch/gemma4_causal.py",
    "patch/gemma4_mm.py",
    "patch/model_config.py",
    "bound_sources/coherence_runner.py",
    "bound_sources/exact_mix_runner.py",
    "bound_sources/retrieval_10k_runner.py",
    "inputs/WORKLOAD.json",
    "inputs/REQUEST_BODIES.sha256",
    "inputs/MATERIALIZATION.json",
    *(f"inputs/request_bodies/request-{index:02d}.json" for index in range(32)),
)


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, **kwargs)


def pool(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(
        [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *arguments],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
        capture_output=True,
        text=True,
        check=check,
    )


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def digest(path: pathlib.Path) -> str:
    block = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 << 20):
            block.update(chunk)
    return block.hexdigest()


def freeze_bound(output_root: pathlib.Path, attempt: int) -> tuple[pathlib.Path, str]:
    rows = []
    for relative in BOUND_FILES:
        path = PHASE2 / relative
        if not path.is_file():
            raise RuntimeError(f"missing bound file: {relative}")
        rows.append((digest(path), relative))
    manifest = PHASE2 / "BOUND_SHA256.txt"
    manifest.write_text("".join(f"{sha}  {relative}\n" for sha, relative in rows))
    archive = output_root / f"phase2-bound-attempt-{attempt}.tar"
    with tarfile.open(archive, "w") as bundle:
        bundle.add(manifest, arcname="BOUND_SHA256.txt")
        for _, relative in rows:
            bundle.add(PHASE2 / relative, arcname=relative)
    archive_sha = digest(archive)
    (output_root / f"phase2-bound-attempt-{attempt}.tar.sha256").write_text(
        f"{archive_sha}  {archive.name}\n"
    )
    return archive, archive_sha


def ssh_base(ip: str) -> list[str]:
    return [
        "ssh", "-i", str(SSH_KEY), "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=8", "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts",
        f"glmrunner@{ip}",
    ]


def ssh(ip: str, command: str, timeout: int) -> subprocess.CompletedProcess:
    return run([*ssh_base(ip), command], capture_output=True, text=True, timeout=timeout)


def scp_to(ip: str, sources: list[pathlib.Path], destination: str, timeout: int) -> subprocess.CompletedProcess:
    command = [
        "scp", "-i", str(SSH_KEY), "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=8", "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts",
        *map(str, sources), f"glmrunner@{ip}:{destination}",
    ]
    return run(command, capture_output=True, text=True, timeout=timeout)


def scp_from(ip: str, source: str, destination: pathlib.Path, timeout: int) -> subprocess.CompletedProcess:
    command = [
        "scp", "-i", str(SSH_KEY), "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=8", "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts",
        f"glmrunner@{ip}:{source}", str(destination),
    ]
    return run(command, capture_output=True, text=True, timeout=timeout)


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

    # Freeze the first transfer before claiming the bench. A repair may freeze a new
    # implementation after claim, but never changes the schedule, workload, identities, or gates.
    archive, archive_sha = freeze_bound(args.artifact_root, 1)
    checkpoint_rows = sorted((path.name, path.stat().st_size, digest(path)) for path in CHECKPOINT.iterdir() if path.is_file())
    if len(checkpoint_rows) != 8 or sum(row[1] for row in checkpoint_rows) != 62578655208:
        raise RuntimeError("project-local checkpoint snapshot identity failure")
    atomic_json(
        args.artifact_root / "LOCAL_ADMISSION.json",
        {"bound_archive_sha256": archive_sha, "checkpoint_files": checkpoint_rows,
         "checkpoint_bytes": sum(row[1] for row in checkpoint_rows)},
    )

    claimed = False
    released = False
    terminal: dict[str, object] | None = None
    ip: str | None = None
    checkpoint_staged = False
    heartbeat_stop = threading.Event()
    claim_started = time.time()
    condition = "ready"

    def heartbeat() -> None:
        while not heartbeat_stop.wait(45):
            result = pool("heartbeat", "--project", PROJECT, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-1000:])

    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    try:
        claim = pool("claim", "--project", PROJECT, "--bench", BENCH, "--lease-seconds", "600")
        claimed = True
        claim_started = time.time()
        emit("claimed", stdout=claim.stdout.strip())
        heartbeat_thread.start()

        sys.path.insert(0, str(NEBIUS_TOOLS))
        from placement_control import extract_public_ipv4, get_instance

        provider = get_instance(INSTANCE)
        ip = extract_public_ipv4(provider)
        if not ip:
            condition = "maintenance"
            raise RuntimeError("typed_provider_boundary:no_public_ip")
        identity = ssh(
            ip,
            "hostname; nvidia-smi --query-gpu=name,uuid,memory.total --format=csv,noheader; sudo docker image inspect docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a --format '{{.Id}}'; df -B1 /home/glmrunner",
            90,
        )
        (args.artifact_root / "remote-identity.stdout").write_text(identity.stdout)
        (args.artifact_root / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            condition = "maintenance"
            raise RuntimeError("typed_remote_boundary:ssh_or_resident_image_failed")

        prepare = ssh(
            ip,
            f"set -eu; mkdir -p {REMOTE}; rm -rf {REMOTE}/phase2-bound {REMOTE}/checkpoint {REMOTE}/{RUN_ID} {REMOTE}/{RUN_ID}.tar.gz {REMOTE}/{RUN_ID}.tar.gz.sha256; mkdir -p {REMOTE}/checkpoint {REMOTE}/phase2-bound; available=$(df -B1 --output=avail {REMOTE} | tail -1); test $available -ge 66500000000",
            90,
        )
        (args.artifact_root / "remote-prepare.stdout").write_text(prepare.stdout)
        (args.artifact_root / "remote-prepare.stderr").write_text(prepare.stderr)
        if prepare.returncode:
            condition = "maintenance"
            raise RuntimeError("typed_staging_boundary:insufficient_remote_disk_or_prepare_failure")

        transfer = scp_to(ip, [CHECKPOINT / row[0] for row in checkpoint_rows], f"{REMOTE}/checkpoint/", 2400)
        (args.artifact_root / "checkpoint-transfer.stdout").write_text(transfer.stdout)
        (args.artifact_root / "checkpoint-transfer.stderr").write_text(transfer.stderr)
        if transfer.returncode:
            raise RuntimeError("typed_staging_boundary:checkpoint_transfer_failed")
        staged = ssh(
            ip,
            f"set -eu; chmod -R a-w {REMOTE}/checkpoint; cd {REMOTE}/checkpoint; sha256sum -c {REMOTE}/phase2-bound/CHECKPOINT_SHA256.txt 2>/dev/null || true; find . -maxdepth 1 -type f -printf '%f\\t%s\\n' | sort",
            120,
        )
        (args.artifact_root / "checkpoint-staged.tsv").write_text(staged.stdout)
        checkpoint_staged = True

        for attempt in range(1, 4):
            if attempt > 1:
                archive, archive_sha = freeze_bound(args.artifact_root, attempt)
            transfer_bound = scp_to(ip, [archive], f"{REMOTE}/", 300)
            (args.artifact_root / f"bound-transfer-attempt-{attempt}.stdout").write_text(transfer_bound.stdout)
            (args.artifact_root / f"bound-transfer-attempt-{attempt}.stderr").write_text(transfer_bound.stderr)
            if transfer_bound.returncode:
                raise RuntimeError("typed_staging_boundary:bound_transfer_failed")
            remote_archive = f"{REMOTE}/{archive.name}"
            extract = ssh(
                ip,
                f"set -eu; rm -rf {REMOTE}/phase2-bound; mkdir -p {REMOTE}/phase2-bound; tar -xf {remote_archive} -C {REMOTE}/phase2-bound; rm -f {remote_archive}; cd {REMOTE}/phase2-bound; sha256sum -c BOUND_SHA256.txt; cd {REMOTE}/checkpoint; sha256sum -c {REMOTE}/phase2-bound/CHECKPOINT_SHA256.txt",
                600,
            )
            (args.artifact_root / f"remote-bound-verify-attempt-{attempt}.stdout").write_text(extract.stdout)
            (args.artifact_root / f"remote-bound-verify-attempt-{attempt}.stderr").write_text(extract.stderr)
            if extract.returncode:
                raise RuntimeError("typed_staging_boundary:remote_hash_verification_failed")
            emit("bound_staged", attempt=attempt, archive_sha256=archive_sha)

            remaining = max(1, args.deadline_epoch - int(time.time()))
            worker = ssh(
                ip,
                f"DEADLINE_EPOCH={args.deadline_epoch} bash {REMOTE}/phase2-bound/remote_conversion.sh",
                remaining + 60,
            )
            (args.artifact_root / f"remote-worker-attempt-{attempt}.stdout").write_text(worker.stdout)
            (args.artifact_root / f"remote-worker-attempt-{attempt}.stderr").write_text(worker.stderr)
            checks = ssh(
                ip,
                f"test -f {REMOTE}/{RUN_ID}/distillation/SCIENTIFIC_STARTED; printf 'scientific=%s\\n' $?; test -f {REMOTE}/{RUN_ID}/OWNER_TERMINAL.json; printf 'terminal=%s\\n' $?",
                30,
            )
            emit("worker_finished", attempt=attempt, returncode=worker.returncode, checks=checks.stdout.strip())
            terminal_check = ssh(ip, f"test -f {REMOTE}/{RUN_ID}/OWNER_TERMINAL.json", 30)
            if terminal_check.returncode == 0:
                break
            scientific_check = ssh(ip, f"test -f {REMOTE}/{RUN_ID}/distillation/SCIENTIFIC_STARTED", 30)
            if scientific_check.returncode == 0:
                raise RuntimeError("scientific_runtime_failure_without_terminal")
            if worker.returncode not in (42,):
                raise RuntimeError(f"typed_remote_boundary:preinvocation_exit_{worker.returncode}")
            diagnostic = ssh(
                ip,
                f"tail -n 240 {REMOTE}/{RUN_ID}/distill.stderr 2>/dev/null; cat {REMOTE}/{RUN_ID}/PREINVOCATION_FAILURE.txt 2>/dev/null; sudo docker ps -a; df -h {REMOTE}",
                60,
            )
            (args.artifact_root / f"repair-diagnostic-attempt-{attempt}.stdout").write_text(diagnostic.stdout)
            (args.artifact_root / f"repair-diagnostic-attempt-{attempt}.stderr").write_text(diagnostic.stderr)
            if attempt == 3:
                raise RuntimeError("preinvocation_wiring_failure_after_repairs")
            emit("repair_window", attempt=attempt, seconds=120)
            time.sleep(120)

        archive_partial = args.artifact_root / f".{RUN_ID}.tar.gz.partial"
        sidecar = args.artifact_root / f"{RUN_ID}.tar.gz.sha256"
        for source, destination, timeout in (
            (f"{REMOTE}/{RUN_ID}.tar.gz", archive_partial, 900),
            (f"{REMOTE}/{RUN_ID}.tar.gz.sha256", sidecar, 120),
        ):
            result = scp_from(ip, source, destination, timeout)
            if result.returncode:
                raise RuntimeError(f"typed_retrieval_boundary:failed:{source}")
        expected = sidecar.read_text().split()[0]
        if digest(archive_partial) != expected:
            raise RuntimeError("typed_retrieval_boundary:archive_hash_mismatch")
        archive_final = args.artifact_root / f"{RUN_ID}.tar.gz"
        archive_partial.replace(archive_final)
        with tarfile.open(archive_final, "r:gz") as bundle:
            bundle.extractall(args.artifact_root, filter="data")
        terminal_path = args.artifact_root / RUN_ID / "OWNER_TERMINAL.json"
        terminal = json.loads(terminal_path.read_text())
        emit("terminal_retrieved", terminal=terminal)

        remote_overlay = f"{REMOTE}/{RUN_ID}/distillation/overlay.safetensors"
        overlay_check = ssh(ip, f"test -f {remote_overlay}", 30)
        if overlay_check.returncode == 0:
            overlay_partial = args.artifact_root / ".overlay.safetensors.partial"
            result = scp_from(ip, remote_overlay, overlay_partial, 900)
            if result.returncode:
                raise RuntimeError("typed_retrieval_boundary:overlay_transfer_failed")
            fidelity = json.loads((args.artifact_root / RUN_ID / "FIDELITY.json").read_text())
            if digest(overlay_partial) != fidelity["overlay_sha256"]:
                raise RuntimeError("typed_retrieval_boundary:overlay_hash_mismatch")
            overlay_partial.replace(args.artifact_root / "overlay.safetensors")
        return 0
    except Exception as error:
        emit("outer_error", error_type=type(error).__name__, message=str(error))
        atomic_json(args.artifact_root / "FAILURE.json", {"type": str(error), "timestamp": time.time()})
        return 1
    finally:
        heartbeat_stop.set()
        if heartbeat_thread.is_alive():
            heartbeat_thread.join(timeout=5)
        if claimed and not released:
            contents = {
                "project": PROJECT,
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4 exact local-attention 16-to-8 KV conversion",
                "checkpoint": "Exact immutable eight-file 62,578,655,208-byte checkpoint staged under /home/glmrunner/gemma-local-kv8/checkpoint and retained." if checkpoint_staged else "Not staged; inspect the typed staging boundary before reuse.",
                "image": "Pinned SGLang v0.5.12 image remains resident at the bound digest.",
                "runtime": "One frozen adjacent-pair-mean local-KV8 schedule reached terminal: " + str((terminal or {}).get("classification", "typed_outer_boundary_before_scientific_invocation")),
                "caches": "Pinned image plus conversion/server compilation caches retained.",
                "server_state": "Converted candidate server retained if startup was reached; otherwise no server.",
                "artifacts": f"Retrieved under projects/{PROJECT}/artifacts/{args.artifact_root.name}/ when terminal retrieval completed.",
                "export": "Content-addressed 100-tensor local K/V overlay retained remotely and retrieved project-locally when fidelity completed.",
            }
            contents_path = args.artifact_root / "BENCH_CONTENTS.json"
            atomic_json(contents_path, contents)
            release = pool("release", "--project", PROJECT, "--condition", condition, "--contents", str(contents_path), check=False)
            emit("released", condition=condition, returncode=release.returncode, stdout=release.stdout.strip(), stderr=release.stderr[-1000:])
            released = True
        atomic_json(
            args.artifact_root / "SPEND.json",
            {"schema_version": 1, "prior_project_cost_usd": 1.03,
             "claim_seconds": max(0.0, time.time() - claim_started) if claimed else 0.0,
             "claim_cost_usd_at_2_46_per_hour": max(0.0, time.time() - claim_started) * 2.46 / 3600 if claimed else 0.0,
             "authorized_cumulative_usd": 18.0},
        )


if __name__ == "__main__":
    raise SystemExit(main())
