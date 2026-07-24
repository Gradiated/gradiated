#!/usr/bin/env python3
"""Adopt the live candidate after the attribution owner's wait-deadline defect."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import shlex
import threading
import time

import run_bench_owner as base


STATE = base.PROJECT / "CANDIDATE_LOCAL_OWNER.json"
DEADLINE = dt.datetime(2026, 7, 24, 20, 50, tzinfo=dt.timezone.utc)


def retrieve(ip: str, artifact: Path) -> Path:
    result = base.ssh(
        ip,
        f"cd {shlex.quote(base.REMOTE)} && tar -czf candidate-compact.tar.gz "
        "CANDIDATE_OWNER.json CANDIDATE_OWNER.log out "
        "attribution-sampling-source.tar.gz donor-source-v2.tar.gz "
        "donor-container-inspect.json donor-pip-freeze.txt "
        "DONOR_CAPTURE_SHA256SUMS 2>candidate-compact-tar.stderr && "
        "sha256sum candidate-compact.tar.gz > candidate-compact.tar.gz.sha256",
        300,
    )
    (artifact / "retrieval-command.stdout").write_text(result.stdout)
    (artifact / "retrieval-command.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("recoverable_retrieval_defect:remote_archive")
    for remote_name, local_name in [
        (f"{base.REMOTE}/candidate-compact.tar.gz", "candidate-compact.tar.gz"),
        (
            f"{base.REMOTE}/candidate-compact.tar.gz.sha256",
            "candidate-compact.tar.gz.sha256",
        ),
    ]:
        copied = base.scp_from(ip, remote_name, artifact / local_name)
        if copied.returncode:
            (artifact / f"{local_name}.scp.stderr").write_text(copied.stderr)
            raise RuntimeError("recoverable_retrieval_defect:scp")
    expected = (artifact / "candidate-compact.tar.gz.sha256").read_text().split()[0]
    if base.digest(artifact / "candidate-compact.tar.gz") != expected:
        raise RuntimeError("recoverable_retrieval_defect:hash")
    snapshot = base.run(
        [
            str(base.ARTIFACT_SNAPSHOT),
            "--archive",
            str(artifact / "candidate-compact.tar.gz"),
            "--root",
            str(artifact / "snapshots"),
        ]
    )
    (artifact / "artifact-snapshot.stdout").write_text(snapshot.stdout)
    (artifact / "artifact-snapshot.stderr").write_text(snapshot.stderr)
    if snapshot.returncode:
        raise RuntimeError("recoverable_retrieval_defect:artifact_snapshot")
    return Path(json.loads(snapshot.stdout)["destination"])


def remote_state(ip: str) -> dict[str, object]:
    result = base.ssh(
        ip,
        f"cd {shlex.quote(base.REMOTE)} && "
        "./detached-owner status --state CANDIDATE_OWNER.json 2>/dev/null; "
        "test -f out/FINAL_TERMINAL.json && echo FINAL_PRESENT || true; "
        "test -f out/ATTEMPT_TERMINAL.json && echo ATTEMPT_PRESENT || true; "
        "cat out/INVOCATION_STATE.json 2>/dev/null || true",
        45,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "final": "FINAL_PRESENT" in result.stdout,
        "attempt": "ATTEMPT_PRESENT" in result.stdout,
        "owner_live": '"live": true' in result.stdout,
    }


def main() -> int:
    artifact = base.PROJECT / "artifacts" / dt.datetime.now(
        dt.timezone.utc
    ).strftime("broadcast-reuse-%Y%m%dt%H%M%Sz")
    artifact.mkdir(parents=True, exist_ok=False)
    claimed_at = base.claim_started_at()
    ip = base.instance_ip()
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(45):
            result = base.pool("heartbeat", "--project", base.NAME)
            base.atomic(
                base.PROJECT / "OWNER_HEARTBEAT.json",
                {
                    "at_utc": base.utc_now(),
                    "returncode": result.returncode,
                    "stderr": result.stderr,
                },
            )

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    for _ in range(100):
        if STATE.exists():
            break
        time.sleep(0.02)
    owner = json.loads(STATE.read_text())
    base.status_update(
        {
            "unit": str(STATE),
            "unit_manager": "pid",
            "pid": owner["pid"],
            "start_ticks": owner["start_ticks"],
            "deadline_utc": DEADLINE.isoformat().replace("+00:00", "Z"),
            "artifact_root": str(artifact),
            "bench_id": base.BENCH,
            "remote_root": base.REMOTE,
            "expected_terminal": "FINAL_TERMINAL.json",
        },
        "The replacement PID owner adopted the already-running single candidate after a controller wait-deadline defect; no producer replay occurred.",
    )
    disposition = None
    try:
        while dt.datetime.now(dt.timezone.utc) < DEADLINE:
            time.sleep(10)
            state = remote_state(ip)
            base.atomic(artifact / "REMOTE_STATE.json", state)
            if state["final"]:
                snapshot = retrieve(ip, artifact)
                terminal = json.loads((snapshot / "out/FINAL_TERMINAL.json").read_text())
                if not terminal.get("candidate_science_consumed"):
                    raise RuntimeError("recoverable_consumer_defect:unconsumed_terminal")
                gpu = base.ssh(
                    ip,
                    "sudo docker inspect -f '{{.State.Running}}' "
                    "gemma4-ngram-torch-staircase-candidate 2>/dev/null; "
                    "nvidia-smi --query-compute-apps=pid,used_memory "
                    "--format=csv,noheader,nounits",
                    45,
                )
                base.release(
                    {
                        "project": base.NAME,
                        "result": terminal["result"],
                        "artifacts": str(artifact.relative_to(base.PROJECT)),
                        "server_state": (
                            "Broadcast-reuse candidate container "
                            "gemma4-ngram-torch-staircase-candidate remains "
                            "loaded and healthy on port 30000."
                        ),
                        "gpu_processes": gpu.stdout.strip(),
                        "checkpoint": (
                            "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/"
                            "checkpoint remains resident and read-only."
                        ),
                    }
                )
                disposition = "scientific_terminal_released_maintenance"
                break
            if state["attempt"] and not state["owner_live"]:
                snapshot = retrieve(ip, artifact)
                raise RuntimeError(
                    "recoverable_candidate_defect:"
                    + str(snapshot / "out/ATTEMPT_TERMINAL.json")
                )
        else:
            raise RuntimeError("typed_deadline_boundary:absolute")
    except Exception as exc:
        base.atomic(
            artifact / "OWNER_EXCEPTION.json",
            {"at_utc": base.utc_now(), "error": repr(exc)},
        )
        try:
            snapshot = retrieve(ip, artifact)
        except Exception as retrieval_exc:
            base.atomic(
                artifact / "RETRIEVAL_EXCEPTION.json",
                {"at_utc": base.utc_now(), "error": repr(retrieval_exc)},
            )
        base.release(
            {
                "project": base.NAME,
                "result": "typed_candidate_or_controller_boundary",
                "error": repr(exc),
                "artifacts": str(artifact.relative_to(base.PROJECT)),
                "remote_state": remote_state(ip),
                "server_state": "Requires director inspection before reuse.",
            }
        )
        disposition = "typed_boundary_released_maintenance"
    finally:
        stop.set()
        thread.join(5)
        claimed_seconds = max(
            0.0,
            (dt.datetime.now(dt.timezone.utc) - claimed_at).total_seconds(),
        )
        spend = claimed_seconds / 3600 * base.HOURLY_USD
        base.atomic(
            base.PROJECT / "OWNER_TERMINAL.json",
            {
                "at_utc": base.utc_now(),
                "disposition": disposition,
                "artifact_root": str(artifact),
                "claimed_seconds": claimed_seconds,
                "conservative_provider_spend_usd": spend,
            },
        )
        status = json.loads((base.PROJECT / "STATUS.json").read_text())
        status["active_session"] = None
        status["actual_spend_usd"] = spend
        status["summary"] = (
            f"Candidate owner completed with disposition {disposition}; see {artifact}."
        )
        base.atomic(base.PROJECT / "STATUS.json", status)
    return 0 if disposition == "scientific_terminal_released_maintenance" else 2


if __name__ == "__main__":
    raise SystemExit(main())
