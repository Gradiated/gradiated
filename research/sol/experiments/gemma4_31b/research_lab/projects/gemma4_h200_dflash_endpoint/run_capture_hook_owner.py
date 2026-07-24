#!/usr/bin/env python3
"""Durable owner for the retained Gemma 4 DFlash capture-hook continuation."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import threading
import time
from typing import Any


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY_SRC = PROJECT.parents[5] / "factory" / "src"
NEBIUS_TOOLS = (
    PROJECT.parents[3]
    / "glm47flash"
    / "campaign_100"
    / "nebius"
)
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
BENCH = "h200-dflash-e00q45wf04571cb67n"
INSTANCE = "computeinstance-e00q45wf04571cb67n"
PROJECT_ID = "gemma4_h200_dflash_endpoint"
REMOTE_INPUTS = "/home/glmrunner/gemma4-dflash/continuation-inputs-20260724-hook1"
REMOTE_RUN = "/home/glmrunner/gemma4-dflash/work/capture-hook-continuation"
RATE_USD_HOUR = 2.46
PRIOR_SPEND_USD = 7.11
RESERVATION_START = dt.datetime.fromisoformat("2026-07-24T02:56:32.235995+00:00")

sys.path.insert(0, str(NEBIUS_TOOLS))
from placement_control import extract_public_ipv4, get_instance, wait_ssh  # noqa: E402


class OwnerError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def emit(path: pathlib.Path, event: str, **values: Any) -> None:
    with path.open("a") as handle:
        handle.write(
            json.dumps(
                {"timestamp": utc_now(), "event": event, **values},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    command: list[str],
    *,
    timeout: float,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=max(1, timeout),
        check=False,
    )


def pool(*args: str, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            "-m",
            "grad_research.gpu_pool",
            "--lab",
            str(LAB),
            *args,
        ],
        timeout=timeout,
    )


def ssh_base(ip: str) -> list[str]:
    return [
        "ssh",
        "-i",
        str(KEY),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"UserKnownHostsFile={KNOWN_HOSTS}",
        "-o",
        "ConnectTimeout=10",
        f"glmrunner@{ip}",
    ]


def scp_base() -> list[str]:
    return [
        "scp",
        "-i",
        str(KEY),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"UserKnownHostsFile={KNOWN_HOSTS}",
        "-o",
        "ConnectTimeout=10",
    ]


def retrieve(ip: str, output: pathlib.Path, events: pathlib.Path) -> None:
    package = "/home/glmrunner/gemma4-dflash/work/capture-hook-continuation.tar.gz"
    command = (
        "tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 "
        "--numeric-owner -czf "
        + package
        + " -C /home/glmrunner/gemma4-dflash/work capture-hook-continuation"
    )
    packed = run([*ssh_base(ip), command], timeout=300)
    (output / "retrieve-pack.stdout").write_text(packed.stdout)
    (output / "retrieve-pack.stderr").write_text(packed.stderr)
    if packed.returncode:
        raise OwnerError(f"remote packaging failed with {packed.returncode}")
    local_package = output / "capture-hook-continuation.tar.gz"
    copied = run(
        [*scp_base(), f"glmrunner@{ip}:{package}", str(local_package)],
        timeout=600,
    )
    (output / "retrieve-scp.stdout").write_text(copied.stdout)
    (output / "retrieve-scp.stderr").write_text(copied.stderr)
    if copied.returncode:
        raise OwnerError(f"remote retrieval failed with {copied.returncode}")
    (output / "capture-hook-continuation.tar.gz.sha256").write_text(
        f"{sha256(local_package)}  {local_package.name}\n"
    )
    extracted = output / "retrieved"
    extracted.mkdir(exist_ok=True)
    with tarfile.open(local_package, "r:gz") as archive:
        archive.extractall(extracted, filter="data")
    emit(events, "retrieval_complete", package_sha256=sha256(local_package))


def update_status(
    *,
    output: pathlib.Path,
    deadline_epoch: float,
    state: str,
    summary: str,
    terminal: pathlib.Path | None,
) -> float:
    ended = dt.datetime.now(dt.timezone.utc)
    additional = max(0.0, (ended - RESERVATION_START).total_seconds()) / 3600 * RATE_USD_HOUR
    actual = round(PRIOR_SPEND_USD + additional, 4)
    status_path = PROJECT / "STATUS.json"
    value = json.loads(status_path.read_text())
    value["actual_spend_usd"] = actual
    value["status"] = state
    value["summary"] = summary
    value["active_session"] = None
    if terminal is not None:
        value["terminal_artifact"] = str(terminal.relative_to(PROJECT))
    value["last_owner"] = {
        "artifact_root": str(output.relative_to(PROJECT)),
        "deadline_utc": dt.datetime.fromtimestamp(
            deadline_epoch, dt.timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "unit": os.environ.get("SYSTEMD_UNIT", "gemma4-dflash-capture-hook-owner.service"),
        "unit_manager": "user",
    }
    atomic_json(status_path, value)
    return actual


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--input-archive", type=pathlib.Path, required=True)
    parser.add_argument("--input-archive-sha256", required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    args = parser.parse_args()

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    events = output / "owner-events.jsonl"
    if sha256(args.input_archive) != args.input_archive_sha256:
        raise OwnerError("immutable input archive hash mismatch before claim")
    if not KEY.is_file():
        raise OwnerError("Nebius SSH key is unavailable")
    if time.time() >= args.deadline_epoch:
        raise OwnerError("owner deadline already expired")

    os.environ["PYTHONPATH"] = str(FACTORY_SRC)
    claimed = pool(
        "claim",
        "--project",
        PROJECT_ID,
        "--bench",
        BENCH,
        "--lease-seconds",
        "14400",
    )
    (output / "claim.stdout").write_text(claimed.stdout)
    (output / "claim.stderr").write_text(claimed.stderr)
    if claimed.returncode:
        raise OwnerError(f"bench claim failed with {claimed.returncode}")
    emit(events, "bench_claimed", bench=BENCH)

    stop_heartbeat = threading.Event()

    def heartbeat() -> None:
        while not stop_heartbeat.wait(45):
            beat = pool("heartbeat", "--project", PROJECT_ID)
            emit(events, "claim_heartbeat", returncode=beat.returncode)

    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    heartbeat_thread.start()
    ip = ""
    disposition = "maintenance"
    terminal_path: pathlib.Path | None = None
    final_state = "active"
    final_summary = "Capture-hook owner ended without a scientific terminal."
    remote_rc = 125
    try:
        payload = get_instance(INSTANCE)
        ip = extract_public_ipv4(payload)
        if not ip:
            raise OwnerError("registered instance has no public IPv4")
        wait_ssh(ip, KEY, min(args.deadline_epoch, time.time() + 180))
        emit(events, "ssh_ready")

        remote_archive = (
            "/home/glmrunner/gemma4-dflash/continuation-inputs-20260724-hook1.tar.gz"
        )
        copied = run(
            [*scp_base(), str(args.input_archive), f"glmrunner@{ip}:{remote_archive}"],
            timeout=min(600, args.deadline_epoch - time.time()),
        )
        (output / "stage-scp.stdout").write_text(copied.stdout)
        (output / "stage-scp.stderr").write_text(copied.stderr)
        if copied.returncode:
            raise OwnerError(f"immutable input staging failed with {copied.returncode}")
        staged = run(
            [
                *ssh_base(ip),
                f"mkdir -p {REMOTE_INPUTS} && "
                f"tar -xzf {remote_archive} -C {REMOTE_INPUTS} && "
                f"cd {REMOTE_INPUTS} && sha256sum -c INPUTS.sha256",
            ],
            timeout=min(180, args.deadline_epoch - time.time()),
        )
        (output / "stage-verify.stdout").write_text(staged.stdout)
        (output / "stage-verify.stderr").write_text(staged.stderr)
        if staged.returncode:
            raise OwnerError(f"remote input verification failed with {staged.returncode}")
        emit(events, "immutable_inputs_staged", archive_sha256=args.input_archive_sha256)

        remote = run(
            [*ssh_base(ip), f"bash {REMOTE_INPUTS}/remote_capture_hook_continuation.sh"],
            timeout=max(60, args.deadline_epoch - time.time()),
        )
        remote_rc = remote.returncode
        (output / "remote.stdout").write_text(remote.stdout)
        (output / "remote.stderr").write_text(remote.stderr)
        emit(events, "remote_returned", returncode=remote_rc)
        retrieve(ip, output, events)
        run_dir = output / "retrieved" / "capture-hook-continuation"
        remote_terminal = json.loads((run_dir / "REMOTE_TERMINAL.json").read_text())
        scientific_terminal = run_dir / "FINAL_TERMINAL.json"
        if scientific_terminal.is_file():
            terminal_path = scientific_terminal
            result = json.loads(scientific_terminal.read_text())
            classification = result.get("classification", "unknown_terminal")
            final_state = "terminal"
            final_summary = f"Capture-hook continuation reached {classification}."
        elif remote_terminal.get("candidate_workload_started") is True:
            terminal_path = run_dir / "REMOTE_TERMINAL.json"
            final_state = "terminal"
            final_summary = (
                "DFlash candidate workload began but ended without a final reconciled "
                f"terminal at stage {remote_terminal.get('stage')}."
            )
        else:
            ready = {
                "schema_version": 1,
                "classification": "recoverable_pre_science_integration_failure",
                "diagnostic": f"remote exit {remote_rc} at stage {remote_terminal.get('stage')}",
                "repair_deadline_utc": dt.datetime.fromtimestamp(
                    args.deadline_epoch, dt.timezone.utc
                ).isoformat().replace("+00:00", "Z"),
                "claim_retained": True,
            }
            atomic_json(output / "REPAIR_READY.json", ready)
            update_status(
                output=output,
                deadline_epoch=args.deadline_epoch,
                state="active",
                summary=ready["diagnostic"],
                terminal=None,
            )
            emit(events, "repair_ready")
            while time.time() < args.deadline_epoch:
                request = output / "REPAIR_REQUEST.json"
                if request.is_file():
                    raise OwnerError(
                        "repair request present; this owner version requires a "
                        "researcher-supplied in-session repair worker"
                    )
                time.sleep(10)
            final_summary = "Pre-science repair deadline expired with the claim retained."

        server = run(
            [
                *ssh_base(ip),
                "sudo docker ps --filter name=^/gemma4-dflash$ "
                "--format '{{.ID}} {{.Status}} {{.Ports}}'; "
                "nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits",
            ],
            timeout=30,
        )
        (output / "resident-state.stdout").write_text(server.stdout)
        (output / "resident-state.stderr").write_text(server.stderr)
        server_running = bool(server.stdout.splitlines()) and "Up " in server.stdout.splitlines()[0]
        disposition = "maintenance" if server_running else "ready"
    except subprocess.TimeoutExpired as error:
        emit(events, "owner_timeout", command=str(error.cmd))
        final_summary = "Absolute owner deadline expired; director disposition required."
    except Exception as error:
        emit(events, "owner_error", error=f"{type(error).__name__}: {error}")
        final_summary = f"Owner boundary: {type(error).__name__}: {error}"
        if ip:
            try:
                retrieve(ip, output, events)
            except Exception as retrieval_error:
                emit(
                    events,
                    "retrieval_error",
                    error=f"{type(retrieval_error).__name__}: {retrieval_error}",
                )
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=5)
        actual = update_status(
            output=output,
            deadline_epoch=args.deadline_epoch,
            state=final_state,
            summary=final_summary,
            terminal=terminal_path,
        )
        contents = {
            "project": PROJECT_ID,
            "artifacts": str(output.relative_to(PROJECT)),
            "result": final_summary,
            "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "draft": "z-lab/gemma-4-31B-it-DFlash@eabd648301ce28583cc14757912e5e0f84e152e1",
            "runtime": "SGLang 588d1f7bc942 plus project-bound Gemma 4 DFlash capture hook.",
            "actual_spend_usd": actual,
            "server_state": (
                "Healthy retained gemma4-dflash container on port 30000; "
                "maintenance disposition required before unrelated reuse."
                if disposition == "maintenance"
                else "No healthy server retained; checkpoint, image, source, and caches remain."
            ),
        }
        contents_path = output / "BENCH_CONTENTS.json"
        atomic_json(contents_path, contents)
        released = pool(
            "release",
            "--project",
            PROJECT_ID,
            "--contents",
            str(contents_path),
            "--condition",
            disposition,
        )
        (output / "release.stdout").write_text(released.stdout)
        (output / "release.stderr").write_text(released.stderr)
        emit(
            events,
            "bench_release_attempt",
            disposition=disposition,
            returncode=released.returncode,
            actual_spend_usd=actual,
        )
    return 0 if final_state == "terminal" and remote_rc in {0, 72} else remote_rc


if __name__ == "__main__":
    raise SystemExit(main())
