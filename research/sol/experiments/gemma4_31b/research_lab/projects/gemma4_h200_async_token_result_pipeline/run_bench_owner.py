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


NAME = "gemma4_h200_async_token_result_pipeline"
PREDECESSOR = "gemma4_h200_local_kv_int4_endpoint"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
LAB = pathlib.Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path(
    "/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius"
)
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
REMOTE = "/home/glmrunner/gemma4-async-result-pipeline"
CHECKPOINT_CANDIDATES = (
    "/home/glmrunner/gemma4-device-conditional-graph/checkpoint",
    "/home/glmrunner/gemma4-width16384/checkpoint",
    "/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint",
)
RATE_USD_PER_HOUR = 2.46
AUTHORIZED_USD = 14.0
MAX_CLAIM_SECONDS = 65 * 60
RETRIEVAL_RESERVE_SECONDS = 8 * 60
STAGED_SCRIPTS = (
    "freeze_live_sources.py",
    "async_result_sitecustomize.py",
    "streaming_discriminator.py",
    "analyze_discriminator.py",
    "analyze_endpoint_pair.py",
    "remote_async_result_pipeline.sh",
    "ADMITTED_INPUT_MANIFEST.json",
)


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
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--absolute-deadline-epoch", type=int, required=True)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=False)
    events = args.artifact_root / "outer-events.jsonl"

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(
                json.dumps(
                    {"epoch": time.time(), "event": event, **fields},
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()

    predecessor_status = json.loads(
        (LAB / "projects" / PREDECESSOR / "STATUS.json").read_text()
    )
    if predecessor_status.get("status") not in {"complete", "blocked"}:
        atomic_json(
            args.artifact_root / "DEPENDENCY_BLOCKER.json",
            {
                "schema_version": 1,
                "classification": "higher_priority_predecessor_not_released",
                "predecessor": PREDECESSOR,
                "predecessor_status": predecessor_status.get("status"),
                "bench_claim_attempted": False,
            },
        )
        return 3

    manifest = json.loads((PROJECT / "ADMITTED_INPUT_MANIFEST.json").read_text())
    if manifest.get("pass") is not True:
        raise RuntimeError("admitted input snapshot invalid")
    files = [
        PROJECT / str(row["path"])
        for row in manifest["files"]
    ] + [PROJECT / name for name in STAGED_SCRIPTS]
    frozen = [
        {
            "path": str(path.relative_to(PROJECT)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(set(files))
    ]
    atomic_json(args.artifact_root / "CLAIM_INPUT_MANIFEST.json", frozen)

    status = json.loads((PROJECT / "STATUS.json").read_text())
    prior_spend = float(status.get("actual_spend_usd", 0.0))
    now = int(time.time())
    deadline = min(
        args.absolute_deadline_epoch,
        now + MAX_CLAIM_SECONDS,
        now + int((AUTHORIZED_USD - prior_spend) * 3600 / RATE_USD_PER_HOUR),
    )
    if deadline <= now + RETRIEVAL_RESERVE_SECONDS + 300:
        raise RuntimeError("typed budget boundary: insufficient claim window")

    inventory = json.loads((LAB / "runtime" / "gpus.json").read_text())
    bench = inventory["benches"][BENCH]
    started = time.time()
    claimed = False
    release_condition = "ready"
    stop = threading.Event()
    ip: str | None = None

    def heartbeat() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME, check=False)
            emit(
                "heartbeat",
                returncode=result.returncode,
                stderr=result.stderr[-1000:],
            )

    thread = threading.Thread(target=heartbeat, daemon=True)
    try:
        lease = max(600, deadline - int(time.time()))
        claim = pool(
            "claim",
            "--project",
            NAME,
            "--bench",
            BENCH,
            "--lease-seconds",
            str(lease),
        )
        claimed = True
        emit("claimed", result=json.loads(claim.stdout))
        thread.start()

        sys.path.insert(0, str(NEBIUS))
        from placement_control import extract_public_ipv4, get_instance, ssh_base
        from stock_control import run_ssh

        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip:
            raise RuntimeError("typed provider boundary: no public IP")
        identity = run_ssh(
            ip,
            KEY,
            "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; "
            "sudo docker --version",
            timeout=60,
        )
        (args.artifact_root / "remote-identity.stdout").write_text(identity.stdout)
        (args.artifact_root / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed remote boundary: SSH identity failed")
        prepared = run_ssh(
            ip,
            KEY,
            f"mkdir -p {REMOTE}/input {REMOTE}/inputs/current_stack "
            f"{REMOTE}/inputs/admitted_upstream {REMOTE}/artifacts",
            timeout=60,
        )
        if prepared.returncode:
            raise RuntimeError("typed remote boundary: prepare failed")

        probe = run_ssh(
            ip,
            KEY,
            "for p in "
            + " ".join(shlex.quote(path) for path in CHECKPOINT_CANDIDATES)
            + "; do if test -r \"$p/model.safetensors.index.json\" "
            + "&& test \"$(sha256sum \"$p/model.safetensors.index.json\" | awk '{print $1}')\" "
            + "= d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2; "
            + "then readlink -f \"$p\"; exit 0; fi; done; exit 1",
            timeout=120,
        )
        if probe.returncode or not probe.stdout.strip():
            raise RuntimeError("typed remote boundary: immutable checkpoint unavailable")
        checkpoint = probe.stdout.strip().splitlines()[-1]
        linked = run_ssh(
            ip,
            KEY,
            f"ln -sfn {shlex.quote(checkpoint)} {REMOTE}/checkpoint",
            timeout=60,
        )
        if linked.returncode:
            raise RuntimeError("typed remote boundary: checkpoint link failed")

        def stage(row: dict[str, object]) -> None:
            source = PROJECT / str(row["path"])
            if (
                source.stat().st_size != row["bytes"]
                or sha256(source) != row["sha256"]
            ):
                raise RuntimeError(f"claim-bound input changed: {row['path']}")
            relative = pathlib.PurePosixPath(str(row["path"]))
            if relative.parts[0] == "inputs":
                destination = pathlib.PurePosixPath(REMOTE) / relative
            else:
                destination = pathlib.PurePosixPath(REMOTE) / "input" / relative.name
            run_ssh(
                ip,
                KEY,
                f"mkdir -p {shlex.quote(str(destination.parent))}",
                timeout=30,
            )
            matched = run_ssh(
                ip,
                KEY,
                f"test -f {shlex.quote(str(destination))} && "
                f"test \"$(sha256sum {shlex.quote(str(destination))} | awk '{{print $1}}')\" "
                f"= {row['sha256']}",
                timeout=60,
            )
            if matched.returncode == 0:
                emit("input_preserved", path=row["path"], sha256=row["sha256"])
                return
            temporary = f"{destination}.{row['sha256']}.part"
            copied = run(
                [
                    "scp",
                    *ssh_base(ip, KEY)[1:-1],
                    str(source),
                    f"glmrunner@{ip}:{temporary}",
                ],
                capture_output=True,
                timeout=max(
                    120,
                    deadline - int(time.time()) - RETRIEVAL_RESERVE_SECONDS,
                ),
            )
            if copied.returncode:
                raise RuntimeError(
                    f"typed transfer boundary: {row['path']}: {copied.stderr[-1200:]}"
                )
            mode = "0555" if source.suffix == ".sh" else "0444"
            finalized = run_ssh(
                ip,
                KEY,
                f"test \"$(sha256sum {shlex.quote(temporary)} | awk '{{print $1}}')\" "
                f"= {row['sha256']} && chmod {mode} {shlex.quote(temporary)} "
                f"&& mv -f {shlex.quote(temporary)} {shlex.quote(str(destination))}",
                timeout=120,
            )
            if finalized.returncode:
                raise RuntimeError(f"typed transfer boundary: finalize {row['path']}")
            emit("input_staged", path=row["path"], sha256=row["sha256"])

        for row in frozen:
            stage(row)
        emit("immutable_staging_complete", files=len(frozen))

        def retrieve_json(remote_path: str, local_name: str) -> dict[str, object]:
            for attempt in range(3):
                result = run_ssh(
                    ip, KEY, f"cat {shlex.quote(remote_path)}", timeout=30
                )
                if result.returncode == 0 and result.stdout.strip():
                    value = json.loads(result.stdout)
                    atomic_json(args.artifact_root / local_name, value)
                    return value
                time.sleep(5 * (attempt + 1))
            raise RuntimeError(f"typed retrieval boundary: {remote_path}")

        worker = None
        invocation = None
        worker_terminal = None
        for attempt in range(1, 4):
            worker_timeout = max(
                60, deadline - int(time.time()) - RETRIEVAL_RESERVE_SECONDS
            )
            worker = run_ssh(
                ip,
                KEY,
                f"timeout --signal=TERM {worker_timeout} "
                f"bash {REMOTE}/input/remote_async_result_pipeline.sh",
                timeout=worker_timeout + 60,
            )
            (args.artifact_root / f"remote-worker-{attempt}.stdout").write_text(
                worker.stdout
            )
            (args.artifact_root / f"remote-worker-{attempt}.stderr").write_text(
                worker.stderr
            )
            emit(
                "worker_returned",
                attempt=attempt,
                returncode=worker.returncode,
            )
            invocation = retrieve_json(
                f"{REMOTE}/artifacts/INVOCATION_STATE.json",
                "INVOCATION_STATE.json",
            )
            worker_terminal = retrieve_json(
                f"{REMOTE}/artifacts/WORKER_TERMINAL.json",
                "REMOTE_WORKER_TERMINAL.json",
            )
            if worker.returncode == 0:
                break
            if invocation.get("candidate_scientific_started"):
                raise RuntimeError(
                    "scientific worker failed after candidate start: "
                    f"{worker_terminal}"
                )
            repair_ready = {
                "schema_version": 1,
                "classification": "pre_candidate_integration_failure",
                "attempt": attempt,
                "worker_returncode": worker.returncode,
                "invocation_state": invocation,
                "worker_terminal": worker_terminal,
                "absolute_repair_deadline_epoch": deadline
                - RETRIEVAL_RESERVE_SECONDS,
            }
            atomic_json(args.artifact_root / "REPAIR_READY.json", repair_ready)
            emit("repair_ready", attempt=attempt)
            request_path = args.artifact_root / "REPAIR_REQUEST.json"
            repair_deadline = deadline - RETRIEVAL_RESERVE_SECONDS
            while time.time() < repair_deadline and not request_path.exists():
                time.sleep(5)
            if not request_path.exists():
                raise RuntimeError(
                    "typed integration boundary: repair deadline expired"
                )
            request = json.loads(request_path.read_text())
            repair_rows = []
            frozen_paths = {str(row["path"]) for row in frozen}
            for requested in request.get("files", []):
                relative = str(requested["path"])
                if relative not in frozen_paths:
                    raise RuntimeError(f"repair path outside claim input: {relative}")
                source = PROJECT / relative
                row = {
                    "path": relative,
                    "bytes": source.stat().st_size,
                    "sha256": sha256(source),
                }
                if row["sha256"] != requested["sha256"]:
                    raise RuntimeError(f"repair hash mismatch: {relative}")
                stage(row)
                repair_rows.append(row)
            if not repair_rows:
                raise RuntimeError("repair request contains no files")
            os.replace(
                request_path,
                args.artifact_root / f"REPAIR_REQUEST.{attempt}.consumed.json",
            )
            atomic_json(
                args.artifact_root / f"REPAIR_INPUT_MANIFEST.{attempt}.json",
                repair_rows,
            )
            emit("repair_staged", attempt=attempt, files=len(repair_rows))
        else:
            raise RuntimeError("typed integration boundary: repair attempts exhausted")

        assert worker is not None
        assert invocation is not None
        assert worker_terminal is not None
        result_terminal = retrieve_json(
            f"{REMOTE}/artifacts/TERMINAL.json", "RESULT_BOUNDARY_COMPONENT.json"
        )
        live_binding = retrieve_json(
            f"{REMOTE}/live_sources/LIVE_SOURCE_BINDING.json",
            "LIVE_SOURCE_BINDING.json",
        )
        archive = args.artifact_root / "async-result-compact.tar.gz.part"
        sidecar = args.artifact_root / "async-result-compact.tar.gz.sha256"
        for remote_path, local_path in (
            (f"{REMOTE}/async-result-compact.tar.gz", archive),
            (f"{REMOTE}/async-result-compact.tar.gz.sha256", sidecar),
        ):
            copied = run(
                [
                    "scp",
                    *ssh_base(ip, KEY)[1:-1],
                    f"glmrunner@{ip}:{remote_path}",
                    str(local_path),
                ],
                capture_output=True,
                timeout=300,
            )
            if copied.returncode:
                raise RuntimeError(
                    f"typed retrieval boundary: archive: {copied.stderr[-1200:]}"
                )
        if sha256(archive) != sidecar.read_text().split()[0]:
            raise RuntimeError("typed retrieval boundary: archive hash mismatch")
        final_archive = args.artifact_root / "async-result-compact.tar.gz"
        os.replace(archive, final_archive)
        retrieved = args.artifact_root / "retrieved"
        retrieved.mkdir()
        with tarfile.open(final_archive, "r:gz") as bundle:
            bundle.extractall(retrieved, filter="data")

        exposure = time.time() - started
        spend = exposure * RATE_USD_PER_HOUR / 3600
        terminal = {
            **result_terminal,
            "worker_terminal": worker_terminal,
            "invocation_state": invocation,
            "live_source_binding": live_binding,
            "bench": BENCH,
            "provider_exposure_seconds": exposure,
            "provider_spend_usd": spend,
            "cumulative_provider_spend_usd": prior_spend + spend,
        }
        if terminal["cumulative_provider_spend_usd"] > AUTHORIZED_USD:
            terminal["classification"] = "budget_violation"
            terminal["pass"] = False
        atomic_json(args.artifact_root / "TERMINAL.json", terminal)
        return 0
    except Exception as error:
        release_condition = "maintenance" if claimed else "ready"
        terminal_path = args.artifact_root / "TERMINAL.json"
        if not terminal_path.exists():
            atomic_json(
                terminal_path,
                {
                    "schema_version": 1,
                    "status": "terminal",
                    "classification": "owner_failure",
                    "pass": False,
                    "error": {"type": type(error).__name__, "message": str(error)},
                    "provider_exposure_seconds": time.time() - started if claimed else 0,
                    "provider_spend_usd": (
                        (time.time() - started) * RATE_USD_PER_HOUR / 3600
                        if claimed
                        else 0
                    ),
                },
            )
        return 1
    finally:
        if claimed:
            stop.set()
            thread.join(timeout=5)
            contents = {
                "project": NAME,
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "image": "Pinned SGLang v0.5.13 digest 6113665 retained",
                "checkpoint": f"Exact immutable checkpoint retained and linked at {REMOTE}/checkpoint",
                "runtime": "Two-slot pinned async result discriminator terminal retrieved",
                "artifacts": str(args.artifact_root),
                "caches": "FP8, QKV, CUDA graph, and pinned result pipeline caches retained",
                "server_state": "Healthy discriminator server retained with arm reset to control when reachable",
            }
            atomic_json(args.artifact_root / "BENCH_CONTENTS.json", contents)
            release = pool(
                "release",
                "--project",
                NAME,
                "--condition",
                release_condition,
                "--contents",
                str(args.artifact_root / "BENCH_CONTENTS.json"),
                check=False,
            )
            (args.artifact_root / "bench-release.stdout").write_text(release.stdout)
            (args.artifact_root / "bench-release.stderr").write_text(release.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
