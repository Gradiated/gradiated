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
LAB = pathlib.Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path(
    "/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius"
)
KEY_CANDIDATES = (
    pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519"),
    pathlib.Path("/root/.config/gradiated/providers/gcore/id_ed25519"),
)
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
REMOTE = "/home/glmrunner/gemma4-h200-mlp-w4-hybrid"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
HOURLY_USD = 2.46


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
    component_terminal_path = (
        PROJECT
        / "artifacts/gemma4-w4hybrid-repair-20260723t062229z"
        / "result/component/TERMINAL.json"
    )
    component_terminal = json.loads(component_terminal_path.read_text())
    if not (
        component_terminal.get("classification") == "component_reject"
        and component_terminal.get("correctness_pass") is True
        and component_terminal.get("promotion_pass") is False
    ):
        raise RuntimeError("counter_repair_requires_persisted_component_reject")
    manifest = json.loads((PROJECT / "GPU_INPUT_MANIFEST.json").read_text())
    component_row = manifest["representation"]["component_snapshot"]
    component_path = PROJECT / component_row["path"]
    if (
        component_path.stat().st_size != component_row["bytes"]
        or sha256(component_path) != component_row["sha256"]
    ):
        raise RuntimeError("immutable_component_snapshot_invalid")

    deadline = min(args.absolute_deadline_epoch, int(time.time()) + 3600)
    started = time.time()
    stop = threading.Event()
    claimed = False
    release_condition = "ready"
    terminal: dict[str, object] = {}
    events = args.artifact_root / "outer-events.jsonl"
    ip: str | None = None
    key = KEY_CANDIDATES[0]

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
        bench = inventory["benches"][args.bench]
        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip:
            raise RuntimeError("typed_provider_boundary:no_public_ip")
        identity = None
        for candidate in KEY_CANDIDATES:
            if candidate.is_file():
                attempt = run_ssh(
                    ip,
                    candidate,
                    "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader",
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

        def ssh(command: str, timeout: int) -> subprocess.CompletedProcess[str]:
            return run_ssh(ip, key, command, timeout=timeout)

        def scp_to(source: pathlib.Path, destination: str, timeout: int = 600) -> None:
            expected = sha256(source)
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
                raise RuntimeError(f"typed_transfer_boundary:scp_to:{source.name}")
            finalized = ssh(
                f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {expected}"
                f" && chmod 0555 {shlex.quote(partial)}"
                f" && mv -f {shlex.quote(partial)} {shlex.quote(destination)}",
                timeout,
            )
            if finalized.returncode:
                raise RuntimeError(
                    f"typed_transfer_boundary:finalize:{source.name}"
                )
            emit("program_transferred", name=source.name, sha256=expected)

        remote_artifacts = f"{REMOTE}/counter-artifacts-{args.artifact_root.name}"
        remote_archive = f"{REMOTE}/counter-compact-{args.artifact_root.name}.tar.gz"
        prepared = ssh(
            f"mkdir -p {REMOTE}/input"
            f" && test \"$(sha256sum {REMOTE}/input/layer0_mlp_awq.safetensors"
            f" | awk '{{print $1}}')\" = {component_row['sha256']}"
            f" && test -s /home/glmrunner/gemma4-h200-dense-fp8-streamk/checkpoint/model.safetensors.index.json"
            f" && rm -rf {shlex.quote(remote_artifacts)}"
            f" && rm -f {shlex.quote(remote_archive)} {shlex.quote(remote_archive + '.sha256')}",
            600,
        )
        if prepared.returncode:
            raise RuntimeError("typed_remote_boundary:resident_inputs_invalid")
        scp_to(PROJECT / "hybrid_component.py", f"{REMOTE}/input/hybrid_component.py")
        scp_to(PROJECT / "remote_counters.sh", f"{REMOTE}/input/remote_counters.sh")

        worker = ssh(
            f"bash {REMOTE}/input/remote_counters.sh"
            f" {shlex.quote(remote_artifacts)} {shlex.quote(remote_archive)}",
            max(600, deadline - int(time.time())),
        )
        (args.artifact_root / "remote.stdout").write_text(worker.stdout)
        (args.artifact_root / "remote.stderr").write_text(worker.stderr)
        emit("worker_returned", returncode=worker.returncode)

        def retrieve(remote: str, local: pathlib.Path, timeout: int = 600) -> None:
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
            if result.returncode:
                raise RuntimeError(f"typed_retrieval_boundary:{pathlib.Path(remote).name}")

        archive = args.artifact_root / "counter-compact.tar.gz"
        retrieve(remote_archive, archive)
        retrieve(remote_archive + ".sha256", args.artifact_root / "counter-compact.tar.gz.sha256")
        retrieve(
            f"{remote_artifacts}/COUNTER_TERMINAL.json",
            args.artifact_root / "COUNTER_TERMINAL.json",
        )
        with tarfile.open(archive) as handle:
            handle.extractall(args.artifact_root / "result")
        counter_terminal = json.loads(
            (args.artifact_root / "COUNTER_TERMINAL.json").read_text()
        )
        for arm in ("control", "candidate"):
            required = (
                args.artifact_root / "result" / f"ncu-{arm}.csv",
                args.artifact_root / "result" / f"ncu-{arm}.stdout",
                args.artifact_root / "result" / f"ncu-{arm}.stderr",
                args.artifact_root / "result" / f"counter-{arm}" / "TERMINAL.json",
                args.artifact_root
                / "result"
                / f"counter-{arm}"
                / "INVOCATION_STATE.json",
            )
            if not all(path.is_file() for path in required):
                raise RuntimeError(f"typed_retrieval_boundary:{arm}_evidence_missing")
        if (
            worker.returncode
            or counter_terminal.get("classification") != "counter_complete"
        ):
            raise RuntimeError(
                f"typed_counter_boundary:{counter_terminal.get('classification')}"
            )

        elapsed = time.time() - started
        terminal = {
            "schema_version": 1,
            "classification": "counter_complete",
            "worker_returncode": worker.returncode,
            "counter_terminal": counter_terminal,
            "claimed_seconds": elapsed,
            "actual_spend_usd": elapsed * HOURLY_USD / 3600,
            "artifact_root": str(args.artifact_root),
            "component_terminal": str(component_terminal_path),
        }
        atomic(args.artifact_root / "OWNER_TERMINAL.json", terminal)
    except Exception as error:
        terminal = {
            "schema_version": 1,
            "classification": "counter_owner_failure",
            "error": {"type": type(error).__name__, "message": str(error)[:4000]},
            "claimed_seconds": time.time() - started,
            "actual_spend_usd": (time.time() - started) * HOURLY_USD / 3600,
            "artifact_root": str(args.artifact_root),
        }
        atomic(args.artifact_root / "OWNER_TERMINAL.json", terminal)
        if "typed_retrieval_boundary" in str(error):
            release_condition = "maintenance"
    finally:
        stop.set()
        if claimed:
            contents = {
                "project": NAME,
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "checkpoint": (
                    "Exact current checkpoint retained at "
                    "/home/glmrunner/gemma4-h200-dense-fp8-streamk/checkpoint; "
                    "immutable project W4 MLP snapshot retained at "
                    "/home/glmrunner/gemma4-h200-mlp-w4-hybrid/w4."
                ),
                "image": f"Pinned SGLang v0.5.13 digest {IMAGE.rsplit(':', 1)[-1]} retained.",
                "runtime": (
                    "Mixed group-128 AWQ W4 decode MLP component_reject: "
                    "correct outputs, negative c32 timing bound; exact basic NCU "
                    f"counter stage {terminal.get('classification')}."
                ),
                "artifacts": str(args.artifact_root),
                "server_state": "No endpoint server launched because the component did not promote.",
            }
            contents_path = args.artifact_root / "bench-contents.json"
            atomic(contents_path, contents)
            release = pool(
                "release",
                "--project",
                NAME,
                "--condition",
                release_condition,
                "--contents",
                str(contents_path),
                check=False,
            )
            emit(
                "released",
                condition=release_condition,
                returncode=release.returncode,
                stdout=release.stdout[-1000:],
                stderr=release.stderr[-1000:],
            )
    return 0 if terminal.get("classification") == "counter_complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
