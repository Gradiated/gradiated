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


NAME = "gemma4_h200_static_c32_multitoken_decode_engine"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
LAB = pathlib.Path(
    "/root/workspace/research/sol/experiments/gemma4_31b/research_lab"
)
PROJECT = LAB / "projects" / NAME
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path(
    "/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius"
)
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
REMOTE = "/home/glmrunner/gemma4-static-c32"
CHECKPOINT_CANDIDATES = (
    "/home/glmrunner/gemma4-async-result-pipeline/checkpoint",
    "/home/glmrunner/gemma4-fp8-layer-fusion/checkpoint",
)
RATE_USD_PER_HOUR = 2.46
AUTHORIZED_USD = 16.0
MAX_CLAIM_SECONDS = 3 * 60 * 60
RETRIEVAL_RESERVE_SECONDS = 10 * 60


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


def input_rows() -> list[dict[str, object]]:
    files = sorted(
        [path for path in (PROJECT / "inputs").rglob("*") if path.is_file()]
        + [
            PROJECT / "DIRECTOR_BINDING.json",
            PROJECT / "verify_director_binding.py",
            PROJECT / "static_c32_sitecustomize.py",
            PROJECT / "run_exact_workload.py",
            PROJECT / "analyze_static_c32.py",
            PROJECT / "remote_static_c32.sh",
        ]
    )
    return [
        {
            "path": str(path.relative_to(PROJECT)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in files
    ]


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

    verifier = run(
        [sys.executable, str(PROJECT / "verify_director_binding.py")],
        capture_output=True,
    )
    (args.artifact_root / "binding.stdout").write_text(verifier.stdout)
    (args.artifact_root / "binding.stderr").write_text(verifier.stderr)
    if verifier.returncode:
        raise RuntimeError("director binding rehash failed")

    frozen = input_rows()
    atomic_json(args.artifact_root / "CLAIM_INPUT_MANIFEST.json", frozen)
    status = json.loads((PROJECT / "STATUS.json").read_text())
    prior_spend = float(status.get("actual_spend_usd", 0.0))
    now = int(time.time())
    deadline = min(
        args.absolute_deadline_epoch,
        now + MAX_CLAIM_SECONDS,
        now + int((AUTHORIZED_USD - prior_spend) * 3600 / RATE_USD_PER_HOUR),
    )
    if deadline <= now + RETRIEVAL_RESERVE_SECONDS + 900:
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

    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    try:
        lease = max(900, deadline - int(time.time()))
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
        heartbeat_thread.start()

        sys.path.insert(0, str(NEBIUS))
        from placement_control import extract_public_ipv4, get_instance, ssh_base
        from stock_control import run_ssh

        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip:
            raise RuntimeError("typed provider boundary: no public IP")
        identity = run_ssh(
            ip,
            KEY,
            "hostname; nvidia-smi --query-gpu=name,uuid,memory.total --format=csv,noheader; sudo docker --version",
            timeout=60,
        )
        (args.artifact_root / "remote-identity.stdout").write_text(identity.stdout)
        (args.artifact_root / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed remote boundary: SSH identity failed")

        prepared = run_ssh(
            ip,
            KEY,
            f"mkdir -p {REMOTE}/input/bound {REMOTE}/input/stack {REMOTE}/input/upstream {REMOTE}/artifacts",
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
            + "then printf '%s\\n' \"$p\"; exit 0; fi; done; exit 1",
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

        def current_rows() -> list[dict[str, object]]:
            rows = input_rows()
            original = {row["path"]: row for row in frozen}
            for row in rows:
                prior = original.get(row["path"])
                if prior is None:
                    continue
                if row != prior:
                    emit(
                        "repair_input_changed",
                        path=row["path"],
                        old_sha256=prior["sha256"],
                        new_sha256=row["sha256"],
                    )
            return rows

        def stage(rows: list[dict[str, object]]) -> None:
            for row in rows:
                source = PROJECT / str(row["path"])
                if (
                    source.stat().st_size != row["bytes"]
                    or sha256(source) != row["sha256"]
                ):
                    raise RuntimeError(f"staging input changed: {row['path']}")
                relative = pathlib.Path(str(row["path"]))
                if relative.parts[0] == "inputs":
                    destination = (
                        pathlib.PurePosixPath(REMOTE)
                        / "input"
                        / pathlib.PurePosixPath(*relative.parts[1:])
                    )
                elif relative.name == "static_c32_sitecustomize.py":
                    destination = pathlib.PurePosixPath(REMOTE) / "input/sitecustomize.py"
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
                    f"test \"$(sha256sum {shlex.quote(str(destination))} | awk '{{print $1}}')\" = {row['sha256']}",
                    timeout=60,
                )
                if matched.returncode == 0:
                    continue
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
                    f"test \"$(sha256sum {shlex.quote(temporary)} | awk '{{print $1}}')\" = {row['sha256']} "
                    f"&& chmod {mode} {shlex.quote(temporary)} "
                    f"&& mv -f {shlex.quote(temporary)} {shlex.quote(str(destination))}",
                    timeout=120,
                )
                if finalized.returncode:
                    raise RuntimeError(f"typed transfer boundary: finalize {row['path']}")
            emit("immutable_staging_complete", files=len(rows))

        stage(frozen)
        attempt = 0
        final_worker_terminal: dict[str, object] | None = None
        final_invocation: dict[str, object] | None = None
        while time.time() < deadline - RETRIEVAL_RESERVE_SECONDS:
            attempt += 1
            worker_timeout = max(
                60, deadline - int(time.time()) - RETRIEVAL_RESERVE_SECONDS
            )
            worker = run_ssh(
                ip,
                KEY,
                f"STATIC_C32_REMOTE_ROOT={REMOTE} timeout --signal=TERM {worker_timeout} "
                f"bash {REMOTE}/input/remote_static_c32.sh",
                timeout=worker_timeout + 60,
            )
            (args.artifact_root / f"remote-worker-attempt-{attempt}.stdout").write_text(
                worker.stdout
            )
            (args.artifact_root / f"remote-worker-attempt-{attempt}.stderr").write_text(
                worker.stderr
            )
            emit("worker_returned", attempt=attempt, returncode=worker.returncode)

            def retrieve_json(remote_path: str, local_name: str) -> dict[str, object]:
                for retry in range(3):
                    result = run_ssh(
                        ip, KEY, f"cat {shlex.quote(remote_path)}", timeout=30
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        value = json.loads(result.stdout)
                        atomic_json(args.artifact_root / local_name, value)
                        return value
                    time.sleep(5 * (retry + 1))
                raise RuntimeError(f"typed retrieval boundary: {remote_path}")

            final_invocation = retrieve_json(
                f"{REMOTE}/artifacts/INVOCATION_STATE.json",
                "INVOCATION_STATE.json",
            )
            final_worker_terminal = retrieve_json(
                f"{REMOTE}/artifacts/WORKER_TERMINAL.json",
                "REMOTE_WORKER_TERMINAL.json",
            )
            classification = str(final_worker_terminal.get("classification"))
            endpoint_started = bool(
                final_invocation.get("candidate_endpoint_started")
            )
            if classification != "integration_failure" or endpoint_started:
                break
            repair_deadline = min(deadline - RETRIEVAL_RESERVE_SECONDS, time.time() + 900)
            ready = {
                "schema_version": 1,
                "classification": classification,
                "diagnostic": final_worker_terminal,
                "attempt": attempt,
                "candidate_endpoint_started": endpoint_started,
                "repair_deadline_epoch": repair_deadline,
            }
            atomic_json(args.artifact_root / "REPAIR_READY.json", ready)
            emit("repair_ready", attempt=attempt, deadline=repair_deadline)
            request = args.artifact_root / "REPAIR_REQUEST.json"
            while time.time() < repair_deadline:
                if request.exists():
                    value = json.loads(request.read_text())
                    if int(value.get("attempt", -1)) == attempt:
                        request.unlink()
                        stage(current_rows())
                        emit("repair_applied", attempt=attempt)
                        break
                time.sleep(5)
            else:
                break

        if final_worker_terminal is None or final_invocation is None:
            raise RuntimeError("typed retrieval boundary: no worker terminal")

        archive = args.artifact_root / "static-c32-compact.tar.gz.part"
        sidecar = args.artifact_root / "static-c32-compact.tar.gz.sha256"
        for remote_path, local_path in (
            (f"{REMOTE}/static-c32-compact.tar.gz", archive),
            (f"{REMOTE}/static-c32-compact.tar.gz.sha256", sidecar),
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
        final_archive = args.artifact_root / "static-c32-compact.tar.gz"
        os.replace(archive, final_archive)
        retrieved = args.artifact_root / "retrieved"
        retrieved.mkdir()
        with tarfile.open(final_archive, "r:gz") as bundle:
            bundle.extractall(retrieved, filter="data")

        endpoint_path = retrieved / "CANDIDATE_ENDPOINT_RESULT.json"
        component_path = retrieved / "COMPONENT_RESULT.json"
        decision = (
            json.loads(endpoint_path.read_text())
            if endpoint_path.exists()
            else json.loads(component_path.read_text())
            if component_path.exists()
            else final_worker_terminal
        )
        exposure = time.time() - started
        spend = exposure * RATE_USD_PER_HOUR / 3600
        terminal = {
            **decision,
            "worker_terminal": final_worker_terminal,
            "invocation_state": final_invocation,
            "bench": BENCH,
            "provider_exposure_seconds": exposure,
            "provider_spend_usd": spend,
            "cumulative_provider_spend_usd": prior_spend + spend,
            "artifact_archive_sha256": sha256(final_archive),
        }
        if terminal["cumulative_provider_spend_usd"] > AUTHORIZED_USD:
            terminal["classification"] = "budget_violation"
            terminal["pass"] = False
        atomic_json(args.artifact_root / "TERMINAL.json", terminal)
        return 0
    except Exception as error:
        if claimed and (
            "SSH" in str(error)
            or "no public IP" in str(error)
            or "checkpoint unavailable" in str(error)
        ):
            release_condition = "maintenance"
        atomic_json(
            args.artifact_root / "TERMINAL.json",
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
            heartbeat_thread.join(timeout=5)
            contents = {
                "project": NAME,
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "image": "Pinned SGLang v0.5.13 digest 6113665 retained",
                "checkpoint": f"Exact immutable checkpoint retained at {checkpoint if 'checkpoint' in locals() else 'resident path'}",
                "runtime": "Static c32 multi-token terminal retrieved",
                "artifacts": str(args.artifact_root),
                "caches": "Pinned image, checkpoint, CUDA graphs, Triton ring, and dynamic-FP8 caches retained",
                "server_state": "Last healthy control/candidate server retained when available",
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
