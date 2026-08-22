#!/usr/bin/env python3
"""Durable claim/repair/release owner for one later-authorized QKV endpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
from typing import Any


PROJECT_NAME = "gemma4_h200_qkv_norm_rope_fp8_epilogue"
PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY_SRC = pathlib.Path("/root/workspace/research/factory/src")
REPAIR = pathlib.Path("/root/workspace/research/factory/tools/repair-handshake")
READY = PROJECT / "ENDPOINT_EXECUTION_PACKET_READY.json"
AUTHORIZED_USD = 10.0
MINIMUM_CLAIM_TO_RELEASE_SECONDS = 90 * 60


class Boundary(RuntimeError):
    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}:{message}")
        self.kind = kind
        self.message = message


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise Boundary("typed_input_boundary", f"{path.name}_not_object")
    return value


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
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
        env={**os.environ, "PYTHONPATH": str(FACTORY_SRC)},
        capture_output=True,
        check=check,
    )


def validate_binding(path: pathlib.Path) -> dict[str, Any]:
    binding = load(path)
    ready_sha = sha256(READY)
    required = {
        "project": PROJECT_NAME,
        "decision": "one_qkv_direct_c32_endpoint",
        "claim_allowed": True,
        "endpoint_submission_limit": 1,
        "endpoint_packet_ready_sha256": ready_sha,
        "accelerator": "nvidia-h200-sxm",
    }
    bad = {
        key: {"expected": value, "observed": binding.get(key)}
        for key, value in required.items()
        if binding.get(key) != value
    }
    if bad:
        raise Boundary("typed_binding_boundary", json.dumps(bad, sort_keys=True))
    if float(binding["conservative_project_exposure_usd"]) > AUTHORIZED_USD:
        raise Boundary("typed_budget_boundary", "binding_exceeds_10_usd")
    deadline = int(binding["absolute_release_deadline_epoch"])
    if deadline <= time.time() + MINIMUM_CLAIM_TO_RELEASE_SECONDS:
        raise Boundary("typed_deadline_boundary", "insufficient_cold_lifecycle")
    ready = load(READY)
    packet_path = (PROJECT / ready["packet"]["path"]).resolve()
    if (
        PROJECT not in packet_path.parents
        or sha256(packet_path) != ready["packet"]["sha256"]
        or binding.get("packet_sha256") != ready["packet"]["sha256"]
    ):
        raise Boundary("typed_input_boundary", "packet_identity")
    if binding.get("packet_manifest_sha256") != ready["packet_manifest"]["sha256"]:
        raise Boundary("typed_input_boundary", "packet_manifest_identity")
    # Cheap preclaim validation binds every small file and the already-deep-hashed
    # checkpoint inode/size/mtime identities. It performs no remote operation.
    validation = run(
        [sys.executable, str(packet_path), "--offline-validate"],
        capture_output=True,
        timeout=180,
    )
    if validation.returncode:
        raise Boundary(
            "typed_input_boundary", f"offline_packet_validation:{validation.stderr[-1000:]}"
        )
    return binding


def show_bench(bench_id: str) -> dict[str, Any]:
    result = pool("show", "--bench", bench_id)
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise Boundary("typed_pool_boundary", "show_not_object")
    return value


def terminal_complete(
    terminal: dict[str, Any],
    invocation: dict[str, Any],
    cleanup: dict[str, Any],
) -> bool:
    gate = terminal.get("quality_gate") or {}
    return (
        terminal.get("classification") in {"endpoint_positive", "endpoint_negative"}
        and terminal.get("pass") is True
        and terminal.get("endpoint_science_consumed") is True
        and terminal.get("endpoint_submission_count") == 1
        and invocation.get("endpoint_science_started") is True
        and invocation.get("endpoint_submission_count") == 1
        and gate.get("request_and_token_accounting") is True
        and gate.get("local_and_global_candidate_path") is True
        and gate.get("raw_responses") == 32
        and gate.get("zero_gpu_cleanup") is True
        and cleanup.get("zero_gpu") is True
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-binding", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    if PROJECT not in root.parents or root.exists():
        raise Boundary(
            "typed_controller_boundary", "artifact root must be fresh and project-local"
        )
    root.mkdir(parents=True)
    events = root / "OWNER_EVENTS.jsonl"

    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle:
            handle.write(
                json.dumps(
                    {"epoch": time.time(), "event": event, **fields}, sort_keys=True
                )
                + "\n"
            )
            handle.flush()

    binding = validate_binding(args.execution_binding.resolve())
    atomic(root / "EXECUTION_BINDING.json", binding)
    deadline = int(binding["absolute_release_deadline_epoch"])
    bench_id = str(binding["bench_id"])
    preclaim = show_bench(bench_id)
    if (
        preclaim.get("accelerator") != "nvidia-h200-sxm"
        or preclaim.get("status") != "available"
        or preclaim.get("claim") is not None
    ):
        raise Boundary("typed_pool_boundary", "bound_bench_not_available_H200")
    if binding.get("watchdog") != preclaim["lifecycle"]["watchdog"]["unit"]:
        raise Boundary("typed_binding_boundary", "watchdog_mismatch")
    if float(binding["hourly_cost_usd"]) != float(preclaim["hourly_cost_usd"]):
        raise Boundary("typed_binding_boundary", "hourly_rate_mismatch")

    claimed = False
    released = False
    stop = threading.Event()
    release_condition: str | None = None

    def heartbeat() -> None:
        while not stop.wait(30):
            result = pool("heartbeat", "--project", PROJECT_NAME, check=False)
            emit(
                "heartbeat",
                returncode=result.returncode,
                stderr=result.stderr[-1000:],
            )

    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)

    def release(condition: str, reason: str) -> None:
        nonlocal released, release_condition
        result = pool(
            "release",
            "--project",
            PROJECT_NAME,
            "--bench",
            bench_id,
            "--condition",
            condition,
            check=False,
        )
        atomic(
            root / "RELEASE_EVIDENCE.json",
            {
                "schema_version": 1,
                "condition": condition,
                "reason": reason,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
        )
        released = result.returncode == 0
        release_condition = condition
        if not released:
            raise Boundary("typed_release_boundary", result.stderr[-1000:])

    try:
        lease = max(900, deadline - int(time.time()))
        claim = pool(
            "claim",
            "--project",
            PROJECT_NAME,
            "--bench",
            bench_id,
            "--lease-seconds",
            str(lease),
        )
        claimed = True
        emit("claimed", claim=json.loads(claim.stdout))
        heartbeat_thread.start()
        bench = show_bench(bench_id)
        if (bench.get("claim") or {}).get("project") != PROJECT_NAME:
            raise Boundary("typed_pool_boundary", "postclaim_ownership_missing")
        atomic(root / "BENCH_RECORD.json", bench)

        ready = load(READY)
        packet = (PROJECT / ready["packet"]["path"]).resolve()
        repair_scope: str | None = None
        prior_artifact: pathlib.Path | None = None
        retrieval_origin: pathlib.Path | None = None
        attempt = 1
        terminal: dict[str, Any] = {}
        invocation: dict[str, Any] = {}
        cleanup: dict[str, Any] = {}
        while time.time() < deadline - 180:
            attempt_root = root / f"attempt-{attempt}"
            command = [
                sys.executable,
                str(packet),
                "--artifact-root",
                str(attempt_root),
                "--deadline-epoch",
                str(deadline),
                "--execution-binding",
                str(args.execution_binding.resolve()),
                "--bench-record",
                str(root / "BENCH_RECORD.json"),
            ]
            if repair_scope:
                command.extend(["--repair-scope", repair_scope])
            if prior_artifact:
                command.extend(["--prior-artifact-root", str(prior_artifact)])
            emit(
                "worker_start",
                attempt=attempt,
                repair_scope=repair_scope,
                packet_sha256=sha256(packet),
                command=command,
            )
            timeout = int(deadline - time.time() - 120)
            if timeout <= 0:
                break
            try:
                worker = run(command, capture_output=True, timeout=timeout)
                (root / f"attempt-{attempt}.stdout").write_text(worker.stdout)
                (root / f"attempt-{attempt}.stderr").write_text(worker.stderr)
                for name in (
                    "INVOCATION_STATE.json",
                    "WORKER_TERMINAL.json",
                    "CLEANUP.json",
                ):
                    source = attempt_root / name
                    if not source.is_file():
                        raise Boundary(
                            "typed_retrieval_boundary",
                            f"attempt_{attempt}_{name}_missing",
                        )
                invocation = load(attempt_root / "INVOCATION_STATE.json")
                terminal = load(attempt_root / "WORKER_TERMINAL.json")
                cleanup = load(attempt_root / "CLEANUP.json")
            except Exception as worker_error:
                if isinstance(worker_error, subprocess.TimeoutExpired):
                    stdout = worker_error.stdout or ""
                    stderr = worker_error.stderr or ""
                    if isinstance(stdout, bytes):
                        stdout = stdout.decode(errors="replace")
                    if isinstance(stderr, bytes):
                        stderr = stderr.decode(errors="replace")
                    (root / f"attempt-{attempt}.stdout").write_text(stdout)
                    (root / f"attempt-{attempt}.stderr").write_text(stderr)
                invocation = (
                    load(attempt_root / "INVOCATION_STATE.json")
                    if (attempt_root / "INVOCATION_STATE.json").is_file()
                    else {
                        "schema_version": 1,
                        "endpoint_science_started": None,
                        "endpoint_submission_count": None,
                        "science_observation": "missing",
                    }
                )
                observation = invocation.get("science_observation")
                if observation not in {"pre_driver", "marker_absent_after_driver"}:
                    invocation["endpoint_science_started"] = None
                    invocation["endpoint_submission_count"] = None
                terminal = {
                    "schema_version": 1,
                    "classification": "worker_observation_incomplete",
                    "pass": False,
                    "message": f"{type(worker_error).__name__}:{worker_error}",
                }
                cleanup = (
                    load(attempt_root / "CLEANUP.json")
                    if (attempt_root / "CLEANUP.json").is_file()
                    else {"attempted": False, "zero_gpu": False}
                )
                atomic(attempt_root / "INVOCATION_STATE.json", invocation)
                atomic(attempt_root / "WORKER_TERMINAL.json", terminal)
                atomic(attempt_root / "CLEANUP.json", cleanup)
            atomic(root / "INVOCATION_STATE.json", invocation)
            atomic(root / "REMOTE_WORKER_TERMINAL.json", terminal)
            atomic(root / "CLEANUP.json", cleanup)
            if terminal_complete(terminal, invocation, cleanup):
                atomic(
                    root / "TERMINAL.json",
                    {
                        **terminal,
                        "schema_version": 1,
                        "continuous_claimed_at": (bench.get("claim") or {}).get(
                            "claimed_at"
                        ),
                        "accepted_attempt": attempt,
                        "worker_terminal_sha256": sha256(
                            attempt_root / "WORKER_TERMINAL.json"
                        ),
                    },
                )
                release("ready", "complete_interpretable_endpoint_and_zero_gpu")
                return 0

            science_started = invocation.get("endpoint_science_started")
            if science_started is False:
                retry_scope = "pre_science_launcher_staging_or_adapter"
            else:
                retry_scope = "retrieval_or_terminal_adoption_no_endpoint_replay"
                # Keep every no-replay repair anchored to the attempt that
                # actually owns the retained science evidence. A failed
                # retrieval attempt may contain only synthetic boundary files.
                if retrieval_origin is None:
                    retrieval_origin = attempt_root
            unsafe = terminal.get("classification") in {
                "remote_unreachable",
                "unsafe_guest",
            }
            if unsafe:
                atomic(
                    root / "TERMINAL_BOUNDARY.json",
                    {
                        "schema_version": 1,
                        "classification": terminal.get("classification"),
                        "endpoint_science_started": science_started,
                        "worker_terminal": terminal,
                    },
                )
                release("maintenance", "unsafe_or_unreachable_guest")
                return 1

            repair_id = f"endpoint-{attempt}"
            repair_deadline = min(deadline - 180, int(time.time()) + 900)
            if repair_deadline <= time.time() + 30:
                break
            diagnostic = json.dumps(
                {
                    "terminal": terminal,
                    "invocation": invocation,
                    "cleanup": cleanup,
                },
                sort_keys=True,
            )[:4000]
            ready_result = run(
                [
                    str(REPAIR),
                    "ready",
                    "--root",
                    str(root),
                    "--repair-id",
                    repair_id,
                    "--deadline",
                    time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(repair_deadline)
                    ),
                    "--failure-kind",
                    str(terminal.get("classification", "unknown")),
                    "--diagnostic",
                    diagnostic,
                    "--retry-scope",
                    retry_scope,
                ],
                capture_output=True,
            )
            if ready_result.returncode:
                raise Boundary(
                    "typed_repair_boundary", ready_result.stderr[-1000:]
                )
            request_path = (
                root
                / ".repair-handshakes"
                / repair_id
                / "REPAIR_REQUEST.json"
            )
            emit(
                "repair_ready",
                repair_id=repair_id,
                retry_scope=retry_scope,
                deadline_epoch=repair_deadline,
            )
            while time.time() < repair_deadline and not request_path.is_file():
                time.sleep(3)
            if not request_path.is_file():
                break
            request = load(request_path)
            if request.get("retry_scope") != retry_scope:
                raise Boundary("typed_repair_boundary", "request_scope_mismatch")
            repair_artifact = pathlib.Path(str(request["patch_artifact"])).resolve()
            if PROJECT not in repair_artifact.parents or not repair_artifact.is_file():
                raise Boundary(
                    "typed_repair_boundary", "repair_artifact_not_project_local"
                )
            repair = load(repair_artifact)
            candidate = (PROJECT / repair["packet_path"]).resolve()
            if (
                PROJECT not in candidate.parents
                or sha256(candidate) != repair["packet_sha256"]
                or repair.get("retry_scope") != retry_scope
            ):
                raise Boundary("typed_repair_boundary", "repair_packet_identity")
            packet = candidate
            prior_artifact = (
                retrieval_origin
                if retry_scope
                == "retrieval_or_terminal_adoption_no_endpoint_replay"
                else attempt_root
            )
            repair_scope = retry_scope
            attempt += 1

        atomic(
            root / "TERMINAL_BOUNDARY.json",
            {
                "schema_version": 1,
                "classification": "absolute_deadline_or_repair_deadline",
                "endpoint_science_started": invocation.get(
                    "endpoint_science_started"
                ),
                "endpoint_submission_count": invocation.get(
                    "endpoint_submission_count"
                ),
                "last_worker_terminal": terminal,
            },
        )
        release("maintenance", "absolute_deadline_requires_director_disposition")
        return 1
    except Exception as error:
        emit("owner_exception", error=f"{type(error).__name__}:{error}")
        atomic(
            root / "OWNER_EXCEPTION.json",
            {
                "schema_version": 1,
                "classification": (
                    error.kind if isinstance(error, Boundary) else "owner_exception"
                ),
                "message": str(error),
                "claimed": claimed,
                "released": released,
            },
        )
        if not claimed:
            return 1
        # A live claimed bench is not released merely because controller wiring
        # failed. Keep heartbeats alive until the absolute fence, allowing a
        # director-bound repair request to arrive in the normal loop on a later
        # generation. At the fence, maintenance is an explicit safe handoff.
        while time.time() < deadline - 180:
            time.sleep(min(3, max(0, deadline - 180 - time.time())))
        if not released:
            release("maintenance", "owner_exception_at_absolute_fence")
        return 1
    finally:
        if released or not claimed:
            stop.set()
        if claimed and not released:
            # The only remaining path reaches here after an unhandled release
            # failure. The heartbeat thread remains live while this process is
            # live; do not manufacture an unconditional release.
            emit(
                "claim_retained_due_release_failure",
                release_condition=release_condition,
            )


if __name__ == "__main__":
    raise SystemExit(main())
