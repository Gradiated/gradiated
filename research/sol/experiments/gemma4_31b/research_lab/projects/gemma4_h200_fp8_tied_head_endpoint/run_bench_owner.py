#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
REPO = HERE.parents[6]
sys.path.insert(0, str(REPO / "research/factory/src"))
sys.path.insert(
    0, str(REPO / "research/sol/experiments/glm47flash/campaign_100/nebius")
)

from grad_research.gpu_pool import GpuPool  # noqa: E402
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base  # noqa: E402


PROJECT = "gemma4_h200_fp8_tied_head_endpoint"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
INSTANCE = "computeinstance-e00vhh6h29fj68x91g"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
REMOTE = "/dev/shm/gemma4-fp8-tied-head"
RATE_USD_PER_HOUR = 2.46
AUTHORIZED_USD = 10.0
ARTIFACTS = HERE / "artifacts"
ABSOLUTE_DEADLINE = dt.datetime(2026, 7, 23, 20, 42, tzinfo=dt.timezone.utc)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def emit(event: str, **fields: Any) -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    row = {"timestamp_utc": utc_now(), "event": event, **fields}
    with (ARTIFACTS / "OWNER_EVENTS.jsonl").open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    atomic_json(ARTIFACTS / "OWNER_STATE.json", row)


def update_status(**updates: Any) -> None:
    path = HERE / "STATUS.json"
    value = json.loads(path.read_text())
    value.update(updates)
    atomic_json(path, value)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_inputs() -> None:
    verifier = subprocess.run(
        [sys.executable, str(HERE / "verify_director_binding.py")],
        text=True,
        capture_output=True,
        timeout=30,
    )
    if verifier.returncode:
        raise RuntimeError(f"director_binding_invalid:{verifier.stderr[-1000:]}")
    expected = {
        "inputs/binding/fp8_qkv_paired_runner.py": "ab5b9c2ce9c63d64481dfae9217c3dc3358ebdff3e933f32734f691977959d83",
        "inputs/binding/qualified-ring-ENDPOINT_RESULT.json": "74bdb22c4bc217299d920bd53a49557403e3a838ba3c98df903ac119e4c4c64c",
    }
    for name, digest in expected.items():
        if sha256(HERE / name) != digest:
            raise RuntimeError(f"project_local_snapshot_invalid:{name}")


def remote(ip: str, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*ssh_base(ip, KEY), command],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def scp_to(ip: str, source: Path, destination: str, recursive: bool = False) -> None:
    command = ["scp"]
    if recursive:
        command.append("-r")
    command.extend(ssh_base(ip, KEY)[1:-1])
    command.extend([str(source), f"{SSH_USER}@{ip}:{destination}"])
    result = subprocess.run(command, text=True, capture_output=True, timeout=300)
    if result.returncode:
        raise RuntimeError(f"transfer_failed:{source.name}:{result.stderr[-1000:]}")


def scp_from(ip: str, source: str, destination: Path) -> bool:
    result = subprocess.run(
        [
            "scp",
            *ssh_base(ip, KEY)[1:-1],
            f"{SSH_USER}@{ip}:{source}",
            str(destination),
        ],
        text=True,
        capture_output=True,
        timeout=300,
    )
    return result.returncode == 0


class Heartbeat(threading.Thread):
    def __init__(self, pool: GpuPool):
        super().__init__(daemon=True)
        self.pool = pool
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.wait(45):
            try:
                self.pool.heartbeat(PROJECT)
                emit("heartbeat")
            except Exception as error:
                emit("heartbeat_failure", error=repr(error))
                return

    def close(self) -> None:
        self.stop_event.set()
        self.join(5)


def stage(ip: str) -> None:
    prepared = remote(
        ip,
        f"mkdir -p {REMOTE}.stage && rm -rf {REMOTE}.stage/input "
        f"{REMOTE}.stage/remote_experiment.sh",
        60,
    )
    if prepared.returncode:
        raise RuntimeError(f"remote_stage_prepare_failed:{prepared.stderr[-1000:]}")
    scp_to(ip, HERE / "inputs", f"{REMOTE}.stage/input", recursive=True)
    scp_to(ip, HERE / "remote_experiment.sh", f"{REMOTE}.stage/")
    finalized = remote(
        ip,
        f"rm -rf {REMOTE}.previous && test ! -e {REMOTE}.previous && "
        f"if test -d {REMOTE}; then mv {REMOTE} {REMOTE}.previous; fi && "
        f"mv {REMOTE}.stage {REMOTE}",
        60,
    )
    if finalized.returncode:
        raise RuntimeError(f"remote_stage_finalize_failed:{finalized.stderr[-1000:]}")


def retrieve(ip: str, attempt: int, stdout: str, stderr: str) -> tuple[dict[str, Any], dict[str, Any], Path]:
    root = ARTIFACTS / f"attempt{attempt}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "worker.stdout").write_text(stdout)
    (root / "worker.stderr").write_text(stderr)
    requested = {
        "WORKER_TERMINAL.json": f"{REMOTE}/artifacts/WORKER_TERMINAL.json",
        "INVOCATION_STATE.json": f"{REMOTE}/artifacts/INVOCATION_STATE.json",
        "fp8-head-compact.tar.gz": f"{REMOTE}/fp8-head-compact.tar.gz",
        "fp8-head-compact.tar.gz.sha256": f"{REMOTE}/fp8-head-compact.tar.gz.sha256",
    }
    observed = {}
    for name, source in requested.items():
        success = False
        for _ in range(3):
            if scp_from(ip, source, root / name):
                success = True
                break
            time.sleep(2)
        observed[name] = success
        emit("retrieval", name=name, success=success, attempt=attempt)
    terminal_path = root / "WORKER_TERMINAL.json"
    state_path = root / "INVOCATION_STATE.json"
    terminal = json.loads(terminal_path.read_text()) if terminal_path.exists() else {}
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    archive = root / "fp8-head-compact.tar.gz"
    if archive.exists():
        extracted = root / "retrieved"
        extracted.mkdir(exist_ok=True)
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(extracted, filter="data")
    atomic_json(root / "RETRIEVAL.json", observed)
    return terminal, state, root


def claimed_cost(claimed_at: dt.datetime) -> float:
    return min(
        AUTHORIZED_USD,
        max(0.0, (dt.datetime.now(dt.timezone.utc) - claimed_at).total_seconds())
        / 3600
        * RATE_USD_PER_HOUR,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", default="foreground")
    parser.add_argument("--start-attempt", type=int, default=1)
    args = parser.parse_args()
    validate_inputs()
    ARTIFACTS.mkdir(exist_ok=True)
    pool = GpuPool(LAB)
    bench = pool.claim(PROJECT, bench_id=BENCH, lease_seconds=3600)
    claimed_at = dt.datetime.fromisoformat(
        bench["claim"]["claimed_at"].replace("Z", "+00:00")
    )
    heartbeat = Heartbeat(pool)
    heartbeat.start()
    released = False
    update_status(
        active_session={
            "kind": "bounded_shared_bench_owner",
            "pid": os.getpid(),
            "unit": args.unit,
            "unit_manager": "foreground",
            "deadline_utc": ABSOLUTE_DEADLINE.isoformat().replace("+00:00", "Z"),
            "artifact_root": str(ARTIFACTS),
            "forward_progress": "claimed; immutable project-local inputs validated",
        }
    )
    terminal: dict[str, Any] = {}
    state: dict[str, Any] = {}
    final_root: Path | None = None
    try:
        instance = get_instance(INSTANCE)
        ip = extract_public_ipv4(instance)
        if not ip:
            raise RuntimeError("registered_guest_has_no_public_ip")
        for attempt in range(args.start_attempt, 5):
            stage(ip)
            update_status(
                actual_spend_usd=claimed_cost(claimed_at),
                active_session={
                    **json.loads((HERE / "STATUS.json").read_text())["active_session"],
                    "forward_progress": f"attempt {attempt}: worker running",
                },
            )
            timeout = max(
                60,
                min(
                    6000,
                    int(
                        (
                            ABSOLUTE_DEADLINE - dt.datetime.now(dt.timezone.utc)
                        ).total_seconds()
                    )
                    - 180,
                ),
            )
            worker = remote(
                ip,
                f"timeout --signal=TERM {timeout} env FP8_HEAD_REMOTE_ROOT={REMOTE} "
                f"bash {REMOTE}/remote_experiment.sh",
                timeout + 60,
            )
            terminal, state, final_root = retrieve(
                ip, attempt, worker.stdout, worker.stderr
            )
            scientific = bool(
                state.get("component_science_started")
                or state.get("endpoint_science_started")
            )
            if terminal.get("classification") != "integration_failure" or scientific:
                break
            repair_deadline = min(
                ABSOLUTE_DEADLINE - dt.timedelta(minutes=3),
                dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=12),
            )
            atomic_json(
                HERE / "REPAIR_READY.json",
                {
                    "schema_version": 1,
                    "status": "repair_ready",
                    "attempt": attempt,
                    "diagnostic": terminal,
                    "invocation_state": state,
                    "absolute_repair_deadline_utc": repair_deadline.isoformat().replace(
                        "+00:00", "Z"
                    ),
                    "intervention_unchanged": True,
                },
            )
            emit("repair_ready", attempt=attempt, diagnostic=terminal)
            while dt.datetime.now(dt.timezone.utc) < repair_deadline:
                request = HERE / "REPAIR_REQUEST.json"
                if request.exists():
                    value = json.loads(request.read_text())
                    if not value.get("intervention_unchanged"):
                        raise RuntimeError("repair_attempted_intervention_change")
                    request.unlink()
                    (HERE / "REPAIR_READY.json").unlink(missing_ok=True)
                    break
                time.sleep(5)
            else:
                raise RuntimeError("repair_deadline_expired")
        if not terminal:
            raise RuntimeError("remote_compact_terminal_missing")
        cost = claimed_cost(claimed_at)
        endpoint_path = (
            final_root / "retrieved/ENDPOINT_RESULT.json" if final_root else None
        )
        component_path = (
            final_root / "retrieved/COMPONENT_DECISION.json" if final_root else None
        )
        endpoint = (
            json.loads(endpoint_path.read_text())
            if endpoint_path and endpoint_path.exists()
            else None
        )
        component = (
            json.loads(component_path.read_text())
            if component_path and component_path.exists()
            else None
        )
        classification = (
            endpoint.get("classification")
            if endpoint
            else terminal.get("classification", "typed_external_blocker")
        )
        final = {
            "schema_version": 1,
            "status": "terminal",
            "classification": classification,
            "actual_spend_usd": cost,
            "component": component,
            "endpoint": endpoint,
            "worker_terminal": terminal,
            "invocation_state": state,
            "timestamp_utc": utc_now(),
        }
        atomic_json(ARTIFACTS / "FINAL_TERMINAL.json", final)
        pool.release(
            PROJECT,
            contents={
                "project": PROJECT,
                "fp8_tied_head_result": classification,
                "fp8_tied_head_actual_spend_usd": cost,
                "artifacts": str(ARTIFACTS.relative_to(REPO)),
                "checkpoint": "Exact immutable checkpoint retained unchanged",
                "image": "Pinned SGLang v0.5.13 digest 6113665 retained",
                "runtime": "Per-tensor E4M3 tied output-head component completed",
                "server_state": "FP8 tied-head ring candidate retained healthy"
                if endpoint
                else "No endpoint qualification claimed",
            },
            condition="ready",
        )
        released = True
        update_status(
            status="completed",
            actual_spend_usd=cost,
            active_session=None,
            summary=classification,
            terminal_artifact=str(ARTIFACTS / "FINAL_TERMINAL.json"),
            next_action=(
                "Director may stack the measured endpoint and schedule the campaign quality suite."
                if endpoint and endpoint.get("pass")
                else "Return to the director; this exact tied-head mechanism is closed."
            ),
        )
        return 0
    except Exception as error:
        cost = claimed_cost(claimed_at)
        atomic_json(
            ARTIFACTS / "FINAL_TERMINAL.json",
            {
                "schema_version": 1,
                "status": "terminal",
                "classification": "typed_external_or_integration_blocker",
                "error": f"{type(error).__name__}:{error}",
                "actual_spend_usd": cost,
                "worker_terminal": terminal,
                "invocation_state": state,
                "timestamp_utc": utc_now(),
            },
        )
        update_status(
            status="completed",
            actual_spend_usd=cost,
            active_session=None,
            summary=f"typed_external_or_integration_blocker:{type(error).__name__}:{error}",
            terminal_artifact=str(ARTIFACTS / "FINAL_TERMINAL.json"),
        )
        if not released:
            pool.release(
                PROJECT,
                contents={
                    "project": PROJECT,
                    "fp8_tied_head_result": "typed_external_or_integration_blocker",
                    "fp8_tied_head_actual_spend_usd": cost,
                    "artifacts": str(ARTIFACTS.relative_to(REPO)),
                    "runtime": f"{type(error).__name__}:{error}",
                },
                condition="maintenance"
                if not terminal and state.get("candidate_cuda_started")
                else "ready",
            )
            released = True
        return 1
    finally:
        heartbeat.close()


if __name__ == "__main__":
    raise SystemExit(main())
