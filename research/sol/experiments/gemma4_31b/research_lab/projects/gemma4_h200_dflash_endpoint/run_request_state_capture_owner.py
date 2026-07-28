#!/usr/bin/env python3
"""Bounded claim/heartbeat/capture/retrieval/release owner."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
from typing import Any

PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
POOL_ENV = {**os.environ, "PYTHONPATH": str(pathlib.Path("/root/workspace/research/factory/src"))}
POOL = ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
BENCH_ID = "h200-dflash-adapter-e00vyqp7gxsr34wrtz"
HOURLY_USD = 2.45
REMOTE_HOST = "glmrunner@89.169.109.132"
SSH_KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
REPAIR_TOOL = pathlib.Path("/root/workspace/research/factory/tools/repair-handshake")


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def iso(value: datetime.datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: pathlib.Path) -> Any:
    return json.loads(path.read_text())


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = pathlib.Path(handle.name)
    temporary.replace(path)


def run(
    command: list[str],
    *,
    timeout: float,
    stdout: pathlib.Path | None = None,
    stderr: pathlib.Path | None = None,
    check: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    out_handle = stdout.open("ab") if stdout is not None else subprocess.PIPE
    err_handle = stderr.open("ab") if stderr is not None else subprocess.PIPE
    try:
        result = subprocess.run(
            command,
            stdout=out_handle,
            stderr=err_handle,
            timeout=max(1.0, timeout),
            check=False,
            env=env,
        )
    finally:
        if hasattr(out_handle, "close"):
            out_handle.close()
        if hasattr(err_handle, "close"):
            err_handle.close()
    if check and result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {command}")
    return result


def ssh_prefix() -> list[str]:
    return [
        "ssh",
        "-i",
        str(SSH_KEY),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={KNOWN_HOSTS}",
        "-o",
        "ConnectTimeout=20",
        REMOTE_HOST,
    ]


def scp_prefix() -> list[str]:
    return [
        "scp",
        "-i",
        str(SSH_KEY),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={KNOWN_HOSTS}",
        "-o",
        "ConnectTimeout=20",
    ]


def seconds_left(deadline: datetime.datetime, operation_cap: float) -> float:
    return min(operation_cap, max(0.0, (deadline - utc_now()).total_seconds()))


def verify_packet(archive: pathlib.Path, expected_sha256: str) -> None:
    if not archive.is_file() or sha256(archive) != expected_sha256:
        raise ValueError("immutable packet archive missing or digest mismatch")
    with tarfile.open(archive) as handle:
        names = set(handle.getnames())
        if "REQUEST_STATE_CAPTURE_PACKET_MANIFEST.json" not in names:
            raise ValueError("packet manifest missing")


def predecessor_gate() -> tuple[bool, dict[str, Any]]:
    states = {}
    for name in (
        "gemma4_certified_lazy_vocab_head",
        "gemma4_h200_fp8_weight_stream_schedule",
    ):
        root = PROJECT.parent / name
        status = load(root / "STATUS.json")
        terminal_name = status.get("terminal_artifact")
        terminal_present = bool(terminal_name and (root / terminal_name).is_file())
        released = status.get("active_session") is None
        states[name] = {
            "terminal_artifact": terminal_name,
            "terminal_present": terminal_present,
            "released": released,
        }
    return all(
        value["terminal_present"] and value["released"] for value in states.values()
    ), states


def inventory_gate() -> tuple[bool, dict[str, Any]]:
    inventory = load(LAB / "runtime" / "gpus.json")
    bench = inventory["benches"][BENCH_ID]
    deadline = datetime.datetime.fromisoformat(
        bench["lifecycle"]["deadline_utc"].replace("Z", "+00:00")
    )
    remaining = (deadline - utc_now()).total_seconds() / 60.0
    claim = bench.get("claim")
    claim_is_ours = isinstance(claim, dict) and claim.get("project") == PROJECT.name
    return (
        bench["status"] in {"available", "claimed"}
        and (bench["claim"] is None or claim_is_ours)
        and remaining >= 50.0
    ), {
        "status": bench["status"],
        "claim": bench["claim"],
        "lifecycle_deadline_utc": iso(deadline),
        "lifecycle_remaining_minutes": remaining,
    }


class Heartbeat:
    def __init__(self, log: pathlib.Path):
        self.log = log
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self.stop.wait(30):
            run(
                POOL + ["heartbeat", "--project", PROJECT.name],
                timeout=20,
                stdout=self.log,
                stderr=self.log,
                env=POOL_ENV,
            )

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=5)


def stage_packet(
    archive: pathlib.Path,
    archive_digest: str,
    output: pathlib.Path,
    deadline: datetime.datetime,
) -> tuple[str, str]:
    remote_root = f"/home/glmrunner/gemma4-dflash/request-state-capture/{archive_digest}"
    remote_archive = f"{remote_root}.tar"
    remote_temporary = f"{remote_archive}.part"
    check = run(
        ssh_prefix()
        + [
            f"test -s '{remote_root}/REQUEST_STATE_CAPTURE_PACKET_MANIFEST.json' "
            f"&& test \"$(sha256sum '{remote_archive}' | cut -d' ' -f1)\" = '{archive_digest}'"
        ],
        timeout=seconds_left(deadline, 30),
    )
    if check.returncode:
        parent = run(
            ssh_prefix() + [f"mkdir -p '{remote_root.rsplit('/', 1)[0]}'"],
            timeout=seconds_left(deadline, 30),
        )
        if parent.returncode:
            raise RuntimeError("remote packet parent creation failed")
        transfer = run(
            scp_prefix() + [str(archive), f"{REMOTE_HOST}:{remote_temporary}"],
            timeout=seconds_left(deadline, 120),
            stdout=output / "stage.stdout",
            stderr=output / "stage.stderr",
        )
        if transfer.returncode:
            raise RuntimeError("packet transfer failed")
        command = (
            f"test \"$(sha256sum '{remote_temporary}' | cut -d' ' -f1)\" = '{archive_digest}'; "
            f"rm -rf '{remote_root}.part'; mkdir -p '{remote_root}.part'; "
            f"tar -xf '{remote_temporary}' -C '{remote_root}.part'; "
            f"rm -rf '{remote_root}'; mv '{remote_root}.part' '{remote_root}'; "
            f"mv '{remote_temporary}' '{remote_archive}'"
        )
        staged = run(
            ssh_prefix() + [command],
            timeout=seconds_left(deadline, 60),
            stdout=output / "stage.stdout",
            stderr=output / "stage.stderr",
        )
        if staged.returncode:
            raise RuntimeError("remote packet verification/finalization failed")
    return remote_root, remote_archive


def retrieve(
    remote_run: str,
    local: pathlib.Path,
    deadline: datetime.datetime,
) -> bool:
    if local.exists():
        shutil.rmtree(local)
    local.mkdir(parents=True)
    result = run(
        scp_prefix() + ["-r", f"{REMOTE_HOST}:{remote_run}/.", str(local)],
        timeout=seconds_left(deadline, 180),
        stdout=local.parent / "retrieve.stdout",
        stderr=local.parent / "retrieve.stderr",
    )
    required = [
        local / "REMOTE_TERMINAL.json",
        local / "ar-c32.server.log",
        local / "ar-c32.SCIENCE_STARTED.json",
    ]
    remote_terminal = load(local / "REMOTE_TERMINAL.json") if required[0].is_file() else {}
    if remote_terminal.get("active_arm") == "dflash-depth4-c32" or (
        local / "dflash-depth4-c32.SCIENCE_STARTED.json"
    ).exists():
        required.extend(
            [
                local / "dflash-depth4-c32.server.log",
                local / "dflash-depth4-c32.SCIENCE_STARTED.json",
            ]
        )
    return result.returncode == 0 and all(path.is_file() for path in required)


def update_spend(claimed_at: datetime.datetime, prior_spend: float) -> float:
    exposure = prior_spend + max(0.0, (utc_now() - claimed_at).total_seconds()) * HOURLY_USD / 3600.0
    status_path = PROJECT / "STATUS.json"
    status = load(status_path)
    status["actual_spend_usd"] = exposure
    status["continuation_remaining_spend_usd"] = max(
        0.0, float(status["authorized_spend_usd"]) - exposure
    )
    atomic(status_path, status)
    return exposure


def release(condition: str, contents: str, output: pathlib.Path) -> None:
    run(
        POOL
        + [
            "release",
            "--project",
            PROJECT.name,
            "--condition",
            condition,
            "--contents",
            json.dumps({"request_state_capture": contents}),
        ],
        timeout=30,
        stdout=output / "release.stdout",
        stderr=output / "release.stderr",
        env=POOL_ENV,
    )


def finalize_capture(
    output: pathlib.Path,
    terminal: pathlib.Path,
    result: pathlib.Path,
    claimed_at: datetime.datetime,
    prior_spend: float,
) -> None:
    spend = update_spend(claimed_at, prior_spend)
    terminal_value = load(terminal)
    terminal_value["actual_spend_usd"] = spend
    terminal_value["claim_seconds"] = (utc_now() - claimed_at).total_seconds()
    atomic(terminal, terminal_value)
    shutil.copy2(result, PROJECT / "DFLASH_EXACT_REQUEST_STATE_CAPTURE_RESULT.json")
    shutil.copy2(
        terminal, PROJECT / "DFLASH_EXACT_REQUEST_STATE_CAPTURE_TERMINAL.json"
    )
    release(
        "ready",
        "Exact-c32 AR/DFlash request-state capture completed; "
        f"terminal={terminal}",
        output,
    )


def repair_wait(
    output: pathlib.Path,
    diagnostic: pathlib.Path,
    retry_scope: str,
    deadline: datetime.datetime,
) -> dict[str, Any] | None:
    run(
        [
            str(REPAIR_TOOL),
            "ready",
            "--root",
            str(output),
            "--deadline",
            iso(deadline),
            "--failure-kind",
            "integration",
            "--diagnostic",
            str(diagnostic),
            "--retry-scope",
            retry_scope,
        ],
        timeout=20,
        check=True,
    )
    waited = run(
        [
            str(REPAIR_TOOL),
            "wait",
            "--root",
            str(output),
            "--poll-seconds",
            "5",
        ],
        timeout=seconds_left(deadline, (deadline - utc_now()).total_seconds()),
    )
    if waited.returncode or not (output / "REPAIR_REQUEST.json").is_file():
        return None
    return load(output / "REPAIR_REQUEST.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--deadline", required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    deadline = datetime.datetime.fromisoformat(args.deadline.replace("Z", "+00:00"))
    ready = load(PROJECT / "REQUEST_STATE_CAPTURE_READY.json")
    status_at_start = load(PROJECT / "STATUS.json")
    prior_spend = float(status_at_start["actual_spend_usd"])
    if prior_spend >= float(status_at_start["authorized_spend_usd"]):
        raise RuntimeError("project provider-spend reservation is exhausted")
    archive = PROJECT / ready["packet"]["archive"]
    archive_digest = ready["packet"]["archive_sha256"]

    preflight = {
        "checked_at_utc": iso(),
        "deadline_utc": iso(deadline),
        "packet_sha256": archive_digest,
    }
    try:
        verify_packet(archive, archive_digest)
        for path in (SSH_KEY, KNOWN_HOSTS):
            if not path.exists():
                raise ValueError(f"required SSH identity path missing: {path}")
        predecessors_pass, preflight["predecessors"] = predecessor_gate()
        inventory_pass, preflight["inventory"] = inventory_gate()
        preflight["predecessor_gate_superseded"] = {
            "value": True,
            "authority": "DIRECTOR_EXACT_REQUEST_STATE_CAPTURE.json and the 2026-07-25T22:49Z director decision",
            "reason": "The FP8 component's durable terminal and maintenance release were reconciled after the older local predecessor-file gate was written.",
            "observed_predecessors_pass": predecessors_pass,
        }
        preflight["pass"] = inventory_pass
        if not preflight["pass"]:
            atomic(output / "OWNER_PREFLIGHT_TERMINAL.json", preflight)
            return 75
    except Exception as exc:
        preflight.update(
            {
                "pass": False,
                "classification": "controller_preflight_defect",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        atomic(output / "OWNER_PREFLIGHT_TERMINAL.json", preflight)
        return 76
    atomic(output / "OWNER_PREFLIGHT.json", preflight)

    claim = run(
        POOL + ["claim", "--project", PROJECT.name, "--bench", BENCH_ID],
        timeout=30,
        stdout=output / "claim.stdout",
        stderr=output / "claim.stderr",
        env=POOL_ENV,
    )
    if claim.returncode:
        atomic(
            output / "OWNER_PREFLIGHT_TERMINAL.json",
            {
                **preflight,
                "pass": False,
                "classification": "atomic_claim_unavailable",
                "claim_exit_code": claim.returncode,
            },
        )
        return 75
    claimed_at = utc_now()
    remote_run = (
        f"/home/glmrunner/gemma4-dflash/request-state-capture/runs/"
        f"{output.name}-{archive_digest[:12]}"
    )
    terminal_disposition = False

    with Heartbeat(output / "heartbeat.log"):
        try:
            packet_root, _ = stage_packet(
                archive, archive_digest, output, deadline
            )
            run(
                ssh_prefix() + [f"mkdir -p '{remote_run}'"],
                timeout=seconds_left(deadline, 30),
                check=True,
            )
            scope = "both"
            repaired = False
            while True:
                worker = run(
                    ssh_prefix()
                    + [
                        f"bash '{packet_root}/remote_request_state_capture.sh' "
                        f"'{packet_root}' '{remote_run}' '{scope}'"
                    ],
                    timeout=seconds_left(deadline, 1800),
                    stdout=output / "remote.stdout",
                    stderr=output / "remote.stderr",
                )
                retrieved = retrieve(
                    remote_run, output / "retrieved", deadline
                )
                if worker.returncode == 0 and retrieved:
                    result = output / "DFLASH_EXACT_REQUEST_STATE_CAPTURE_RESULT.json"
                    terminal = output / "DFLASH_EXACT_REQUEST_STATE_CAPTURE_TERMINAL.json"
                    summarized = run(
                        [
                            "python3",
                            str(PROJECT / "summarize_request_state_capture.py"),
                            "--root",
                            str(output / "retrieved"),
                            "--prior",
                            str(PROJECT / "DFLASH_DEPTH4_ENDPOINT_TERMINAL.json"),
                            "--result",
                            str(result),
                            "--terminal",
                            str(terminal),
                        ],
                        timeout=seconds_left(deadline, 60),
                        stdout=output / "summarize.stdout",
                        stderr=output / "summarize.stderr",
                    )
                    if summarized.returncode == 0:
                        finalize_capture(output, terminal, result, claimed_at, prior_spend)
                        terminal_disposition = True
                        return 0
                    diagnostic = output / "summarize.stderr"
                    retry_scope = "consumer-only"
                else:
                    diagnostic = (
                        output / "retrieve.stderr"
                        if not retrieved
                        else output / "remote.stderr"
                    )
                    remote_terminal = (
                        load(output / "retrieved" / "REMOTE_TERMINAL.json")
                        if (output / "retrieved" / "REMOTE_TERMINAL.json").is_file()
                        else {}
                    )
                    retry_scope = (
                        "dflash"
                        if (
                            output
                            / "retrieved"
                            / "results"
                            / "ar-c32"
                            / "TERMINAL.json"
                        ).is_file()
                        else str(remote_terminal.get("active_arm") or "both")
                    )
                if repaired:
                    raise RuntimeError("corrected repair attempt also failed")
                request = repair_wait(
                    output,
                    diagnostic,
                    retry_scope,
                    min(deadline, utc_now() + datetime.timedelta(minutes=15)),
                )
                if request is None:
                    break
                patch_artifact = request.get("patch_artifact")
                if not patch_artifact:
                    raise RuntimeError("repair request has no patch artifact")
                patch = load(pathlib.Path(patch_artifact))
                requested_scope = str(patch.get("retry_scope", retry_scope))
                if requested_scope == "consumer-only":
                    consumer = pathlib.Path(patch["consumer_script"])
                    if not consumer.is_file() or sha256(consumer) != patch["consumer_sha256"]:
                        raise RuntimeError("consumer repair digest mismatch")
                    result = output / "DFLASH_EXACT_REQUEST_STATE_CAPTURE_RESULT.json"
                    terminal = output / "DFLASH_EXACT_REQUEST_STATE_CAPTURE_TERMINAL.json"
                    repaired_consumer = run(
                        [
                            "python3",
                            str(consumer),
                            "--root",
                            str(output / "retrieved"),
                            "--prior",
                            str(PROJECT / "DFLASH_DEPTH4_ENDPOINT_TERMINAL.json"),
                            "--result",
                            str(result),
                            "--terminal",
                            str(terminal),
                        ],
                        timeout=seconds_left(deadline, 60),
                        stdout=output / "summarize.repair.stdout",
                        stderr=output / "summarize.repair.stderr",
                    )
                    if repaired_consumer.returncode:
                        raise RuntimeError("corrected consumer attempt failed")
                    finalize_capture(output, terminal, result, claimed_at, prior_spend)
                    terminal_disposition = True
                    return 0
                replacement = pathlib.Path(patch["packet_archive"])
                verify_packet(replacement, patch["packet_archive_sha256"])
                archive, archive_digest = replacement, patch["packet_archive_sha256"]
                packet_root, _ = stage_packet(
                    archive, archive_digest, output, deadline
                )
                scope = requested_scope
                repaired = True
            spend = update_spend(claimed_at, prior_spend)
            atomic(
                output / "OWNER_TERMINAL.json",
                {
                    "schema_version": 1,
                    "classification": "repair_deadline_or_retrieval_boundary",
                    "actual_spend_usd": spend,
                    "claim_seconds": (utc_now() - claimed_at).total_seconds(),
                    "remote_run": remote_run,
                    "retrieval_present": (output / "retrieved" / "REMOTE_TERMINAL.json").is_file(),
                },
            )
            release(
                "maintenance",
                "Request-state capture reached repair/deadline boundary; "
                f"artifacts={output}",
                output,
            )
            terminal_disposition = True
            return 77
        except Exception as exc:
            spend = update_spend(claimed_at, prior_spend)
            atomic(
                output / "OWNER_TERMINAL.json",
                {
                    "schema_version": 1,
                    "classification": "owner_nonrecoverable_boundary",
                    "error": f"{type(exc).__name__}: {exc}",
                    "actual_spend_usd": spend,
                    "claim_seconds": (utc_now() - claimed_at).total_seconds(),
                    "remote_run": remote_run,
                },
            )
            retrieve(remote_run, output / "retrieved-final", deadline)
            release(
                "maintenance",
                "Request-state owner nonrecoverable boundary; "
                f"artifacts={output}",
                output,
            )
            terminal_disposition = True
            return 78
        finally:
            if not terminal_disposition and utc_now() >= deadline:
                update_spend(claimed_at, prior_spend)
                release(
                    "maintenance",
                    f"Request-state owner absolute deadline; artifacts={output}",
                    output,
                )


if __name__ == "__main__":
    raise SystemExit(main())
