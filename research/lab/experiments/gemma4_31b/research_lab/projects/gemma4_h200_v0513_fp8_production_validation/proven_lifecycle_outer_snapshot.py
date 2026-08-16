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


PROJECT_NAME = "gemma4_h200_qkv_epilogue_fusion"
BENCH = "h200-kernel-frontier-e00pfvrckjvwn7bhet"
LAB = pathlib.Path("/root/workspace/research/lab/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / PROJECT_NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS_TOOLS = pathlib.Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
SSH_KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
REMOTE = "/home/glmrunner/gemma-kernel-frontier"
RATE = 2.46
PRIOR_SPEND = 0.216647230664889
SPEND_CEILING = 6.0


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, **kwargs)


def pool(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(
        [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *arguments],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
        capture_output=True,
        check=check,
    )


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def copy_one(ip: str, source: pathlib.Path, destination: str, timeout: int) -> None:
    result = run(
        [
            "scp",
            "-i",
            str(SSH_KEY),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={KNOWN_HOSTS}",
            str(source),
            f"glmrunner@{ip}:{destination}",
        ],
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"typed_transfer_boundary:scp_failed:{source.name}:{result.stderr[-1000:]}")


def retrieve(ip: str, remote: str, local: pathlib.Path, timeout: int = 120) -> None:
    copy_command = [
        "scp",
        "-i",
        str(SSH_KEY),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"UserKnownHostsFile={KNOWN_HOSTS}",
        f"glmrunner@{ip}:{remote}",
        str(local),
    ]
    result = run(copy_command, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"typed_retrieval_boundary:scp_failed:{result.stderr[-1000:]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--absolute-deadline-epoch", type=int, required=True)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((PROJECT / "FP8_QKV_INPUT_MANIFEST.json").read_text())
    support = json.loads(
        (PROJECT / "FP8_QKV_LOCAL_BINDING.json").read_text()
    )
    if support.get("pass") is not True:
        raise RuntimeError("local_support_terminal_not_passing")
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    bench = inventory["benches"][BENCH]
    claim_state = bench.get("claim") or {}
    if bench["status"] != "available" and not (
        bench["status"] == "claimed" and claim_state.get("project") == PROJECT_NAME
    ):
        raise RuntimeError("cross_project_dependency:bench_not_released")
    maximum_seconds = int((SPEND_CEILING - PRIOR_SPEND) * 3600 / RATE) - 45
    if maximum_seconds < 600:
        raise RuntimeError("typed_budget_boundary:insufficient_remaining_spend")
    experiment_deadline = min(args.absolute_deadline_epoch, int(time.time()) + maximum_seconds)
    if experiment_deadline <= time.time() + 600:
        raise RuntimeError("typed_budget_boundary:insufficient_deadline")

    events = args.artifact_root / "outer-events.jsonl"
    started = time.time()
    claimed = False
    ip: str | None = None
    terminal: dict[str, object] | None = None
    heartbeat_stop = threading.Event()

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(json.dumps({"time": time.time(), "event": event, **fields}, sort_keys=True) + "\n")

    def heartbeat() -> None:
        while not heartbeat_stop.wait(45):
            result = pool("heartbeat", "--project", PROJECT_NAME, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-1000:])

    thread = threading.Thread(target=heartbeat, daemon=True)
    try:
        lease_seconds = max(600, experiment_deadline - int(time.time()))
        claim = pool("claim", "--project", PROJECT_NAME, "--bench", BENCH, "--lease-seconds", str(lease_seconds))
        claimed = True
        emit("claimed", result=json.loads(claim.stdout))
        thread.start()

        sys.path.insert(0, str(NEBIUS_TOOLS))
        from placement_control import extract_public_ipv4, get_instance
        from stock_control import run_ssh

        provider = get_instance(bench["resource"]["instance_id"])
        ip = extract_public_ipv4(provider)
        if not ip:
            raise RuntimeError("typed_provider_boundary:no_public_ip")
        refresh = run(["ssh-keygen", "-R", ip, "-f", str(KNOWN_HOSTS)], capture_output=True)
        emit("known_host_refreshed", returncode=refresh.returncode)
        identity = run_ssh(
            ip,
            SSH_KEY,
            "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version",
            timeout=60,
        )
        (args.artifact_root / "remote-identity.stdout").write_text(identity.stdout)
        (args.artifact_root / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_remote_boundary:ssh_identity_failed")

        prepare = run_ssh(
            ip,
            SSH_KEY,
            f"mkdir -p {REMOTE}/qkv-stack-input {REMOTE}/qkv-stack-assistant {REMOTE}/artifacts/fp8-qkv-stack-v0513",
            timeout=60,
        )
        if prepare.returncode:
            raise RuntimeError("typed_remote_boundary:prepare_failed")

        checkpoint_checks = " ".join(
            shlex.quote(f"{row['path']}:{row['bytes']}") for row in manifest["checkpoint_files"]
        )
        checkpoint = run_ssh(
            ip,
            SSH_KEY,
            f"set -e; cd {REMOTE}/checkpoint; for x in {checkpoint_checks}; do n=${{x%%:*}}; b=${{x#*:}}; test -r \"$n\"; test \"$(stat -c%s -- \"$n\")\" = \"$b\"; done",
            timeout=90,
        )
        if checkpoint.returncode:
            raise RuntimeError("typed_remote_boundary:immutable_checkpoint_identity_changed")
        emit("checkpoint_storage_identity_reused", files=8, bytes=sum(row["bytes"] for row in manifest["checkpoint_files"]))

        stage = [
            (PROJECT / "fp8_qkv_paired_runner.py", f"{REMOTE}/qkv-stack-input"),
            (PROJECT / "proven_v0513_endpoint_entrypoint.py", f"{REMOTE}/qkv-stack-input"),
            (PROJECT / "remote_fp8_stack.sh", f"{REMOTE}/qkv-stack-input"),
            (PROJECT / "FP8_QKV_INPUT_MANIFEST.json", f"{REMOTE}/qkv-stack-input"),
            (PROJECT / "stack_sitecustomize.py", f"{REMOTE}/qkv-stack-input"),
            (PROJECT / "install_endpoint_patch.py", f"{REMOTE}/qkv-stack-input"),
            (PROJECT / "qkv_epilogue_discriminator.py", f"{REMOTE}/qkv-stack-input"),
        ]
        for source, remote_directory in stage:
            expected = sha256(source)
            partial = f"{remote_directory}/.{source.name}.{expected}.part"
            final = f"{remote_directory}/{source.name}"
            check = run_ssh(
                ip,
                SSH_KEY,
                f"test -f {shlex.quote(final)} && test \"$(sha256sum {shlex.quote(final)} | awk '{{print $1}}')\" = {shlex.quote(expected)}",
                timeout=max(60, min(900, experiment_deadline - int(time.time()))),
            )
            if check.returncode:
                copy_one(ip, source, partial, max(60, min(900, experiment_deadline - int(time.time()))))
                finalize = run_ssh(
                    ip,
                    SSH_KEY,
                    f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {shlex.quote(expected)} && mv -f {shlex.quote(partial)} {shlex.quote(final)}",
                    timeout=120,
                )
                if finalize.returncode:
                    raise RuntimeError(f"typed_transfer_boundary:hash_or_finalize_failed:{source.name}")
            emit("input_staged", name=source.name, sha256=expected, bytes=source.stat().st_size)

        worker_timeout = max(60, experiment_deadline - int(time.time()) - 90)
        worker = run_ssh(
            ip,
            SSH_KEY,
            f"timeout --signal=TERM {worker_timeout} bash {REMOTE}/qkv-stack-input/remote_fp8_stack.sh",
            timeout=worker_timeout + 30,
        )
        (args.artifact_root / "remote-worker.stdout").write_text(worker.stdout)
        (args.artifact_root / "remote-worker.stderr").write_text(worker.stderr)
        emit("worker_returned", returncode=worker.returncode)

        state_result = run_ssh(ip, SSH_KEY, f"cat {REMOTE}/artifacts/fp8-qkv-stack-v0513/INVOCATION_STATE.json", timeout=30)
        state = json.loads(state_result.stdout) if state_result.returncode == 0 else {}
        atomic(args.artifact_root / "INVOCATION_STATE.json", state)
        compact_result = run_ssh(ip, SSH_KEY, f"cat {REMOTE}/artifacts/fp8-qkv-stack-v0513/WORKER_TERMINAL.json", timeout=30)
        worker_terminal = json.loads(compact_result.stdout) if compact_result.returncode == 0 else {}
        atomic(args.artifact_root / "REMOTE_WORKER_TERMINAL.json", worker_terminal)
        if worker.returncode and worker_terminal.get("classification") == "integration_failure":
            repair_deadline = min(experiment_deadline - 90, int(time.time()) + 300)
            atomic(
                args.artifact_root / "REPAIR_READY.json",
                {
                    "worker_terminal": worker_terminal,
                    "invocation_state": state,
                    "repair_deadline_epoch": repair_deadline,
                },
            )
            request = args.artifact_root / "REPAIR_REQUEST.json"
            while time.time() < repair_deadline and not request.is_file():
                time.sleep(5)
            if request.is_file() and json.loads(request.read_text()).get("retry") is True:
                for source in (
                    PROJECT / "fp8_qkv_paired_runner.py",
                    PROJECT / "proven_v0513_endpoint_entrypoint.py",
                    PROJECT / "remote_fp8_stack.sh",
                ):
                    expected = sha256(source)
                    partial = f"{REMOTE}/qkv-stack-input/.{source.name}.{expected}.part"
                    final = f"{REMOTE}/qkv-stack-input/{source.name}"
                    copy_one(ip, source, partial, max(60, experiment_deadline - int(time.time()) - 90))
                    finalized = run_ssh(
                        ip,
                        SSH_KEY,
                        f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {shlex.quote(expected)} && mv -f {shlex.quote(partial)} {shlex.quote(final)}",
                        timeout=120,
                    )
                    if finalized.returncode:
                        raise RuntimeError(f"typed_transfer_boundary:repair_finalize_failed:{source.name}")
                retry_timeout = max(60, experiment_deadline - int(time.time()) - 90)
                retry = run_ssh(
                    ip,
                    SSH_KEY,
                    f"timeout --signal=TERM {retry_timeout} bash {REMOTE}/qkv-stack-input/remote_fp8_stack.sh",
                    timeout=retry_timeout + 30,
                )
                (args.artifact_root / "remote-worker-retry.stdout").write_text(retry.stdout)
                (args.artifact_root / "remote-worker-retry.stderr").write_text(retry.stderr)
                emit("worker_retried", returncode=retry.returncode)
                state_result = run_ssh(ip, SSH_KEY, f"cat {REMOTE}/artifacts/fp8-qkv-stack-v0513/INVOCATION_STATE.json", timeout=30)
                state = json.loads(state_result.stdout) if state_result.returncode == 0 else state
                atomic(args.artifact_root / "INVOCATION_STATE.json", state)
                compact_result = run_ssh(ip, SSH_KEY, f"cat {REMOTE}/artifacts/fp8-qkv-stack-v0513/WORKER_TERMINAL.json", timeout=30)
                worker_terminal = json.loads(compact_result.stdout) if compact_result.returncode == 0 else worker_terminal
                atomic(args.artifact_root / "REMOTE_WORKER_TERMINAL.json", worker_terminal)

        archive = args.artifact_root / "compact.tar.gz"
        sidecar = args.artifact_root / "compact.tar.gz.sha256"
        retrieve(ip, f"{REMOTE}/fp8-qkv-stack-v0513-compact.tar.gz", archive, timeout=180)
        retrieve(ip, f"{REMOTE}/fp8-qkv-stack-v0513-compact.tar.gz.sha256", sidecar, timeout=60)
        if sha256(archive) != sidecar.read_text().split()[0]:
            raise RuntimeError("typed_retrieval_boundary:archive_hash_mismatch")
        retrieved = args.artifact_root / "retrieved"
        retrieved.mkdir()
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(retrieved, filter="data")
        paired = retrieved / "PAIRED_TERMINAL.json"
        if paired.is_file():
            terminal = json.loads(paired.read_text())
            terminal["provider_exposure_seconds"] = time.time() - started
            terminal["provider_spend_usd"] = terminal["provider_exposure_seconds"] * RATE / 3600
            terminal["project_cumulative_spend_usd"] = PRIOR_SPEND + terminal["provider_spend_usd"]
        else:
            terminal = {
                "schema_version": 1,
                "status": "terminal",
                "classification": "integration_failure",
                "pass": False,
                "worker_terminal": worker_terminal,
                "invocation_state": state,
                "provider_exposure_seconds": time.time() - started,
                "provider_spend_usd": (time.time() - started) * RATE / 3600,
            }
            terminal["project_cumulative_spend_usd"] = PRIOR_SPEND + terminal["provider_spend_usd"]
        if terminal["project_cumulative_spend_usd"] > SPEND_CEILING:
            terminal["classification"] = "budget_violation"
            terminal["pass"] = False
        atomic(args.artifact_root / "TERMINAL.json", terminal)
        return 0 if terminal.get("pass") else 1
    except Exception as error:
        terminal = {
            "schema_version": 1,
            "status": "terminal",
            "classification": "owner_failure",
            "pass": False,
            "error": {"type": type(error).__name__, "message": str(error)},
            "provider_exposure_seconds": time.time() - started if claimed else 0,
        }
        terminal["provider_spend_usd"] = terminal["provider_exposure_seconds"] * RATE / 3600
        terminal["project_cumulative_spend_usd"] = PRIOR_SPEND + terminal["provider_spend_usd"]
        atomic(args.artifact_root / "TERMINAL.json", terminal)
        emit("outer_error", error_type=type(error).__name__, message=str(error))
        return 1
    finally:
        heartbeat_stop.set()
        if thread.is_alive():
            thread.join(timeout=5)
        if claimed:
            classification = (terminal or {}).get("classification", "owner_failure")
            contents = {
                "project": PROJECT_NAME,
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "checkpoint": f"Exact immutable eight-file checkpoint retained at {REMOTE}/checkpoint.",
                "image": "SGLang v0.5.13 linux/amd64 digest 6113665a retained if pull completed.",
                "runtime": f"Same-session current-runtime FP8/QKV terminal: {classification}.",
                "caches": "SGLang FP8, QKV, and CUDA graph caches retained.",
                "server_state": "Final QKV server retained when healthy; otherwise image/checkpoint/caches retained.",
                "artifacts": "Compact worker terminal, logs, arm rows, telemetry, and invocation markers retrieved project-locally.",
            }
            contents_path = args.artifact_root / "BENCH_CONTENTS.json"
            atomic(contents_path, contents)
            release = pool("release", "--project", PROJECT_NAME, "--condition", "ready", "--contents", str(contents_path), check=False)
            emit("released", returncode=release.returncode, stderr=release.stderr[-1000:])


if __name__ == "__main__":
    raise SystemExit(main())
