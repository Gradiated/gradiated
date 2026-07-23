#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
LAB = PROJECT_ROOT.parents[1]
REPO = PROJECT_ROOT.parents[6]
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
REMOTE = "/dev/shm/gemma4-fp8-tied-head-graph-bound"
RATE_USD_PER_HOUR = 2.46
AUTHORIZED_USD = 10.0
PRIOR_SPEND_USD = 0.9860778082499999
ARTIFACTS = HERE / "artifacts"
ABSOLUTE_DEADLINE = dt.datetime(2026, 7, 23, 22, 15, tzinfo=dt.timezone.utc)
PRIOR_ARTIFACT_TREE_SHA256 = (
    "6fe3854d0a9117bf6d75db753582533b38875f273256303f5b514738d35b4fe7"
)
PRIOR_FINAL_SHA256 = (
    "1cc0eedd960d0434845953a82a1bed2a7742260d93e9ac8142791cfdb68f604e"
)
INPUT_SHA256 = {
    "inputs/binding/fp8_qkv_paired_runner.py": (
        "ab5b9c2ce9c63d64481dfae9217c3dc3358ebdff3e933f32734f691977959d83"
    ),
    "inputs/binding/qualified-ring-ENDPOINT_RESULT.json": (
        "74bdb22c4bc217299d920bd53a49557403e3a838ba3c98df903ac119e4c4c64c"
    ),
    "inputs/binding/settled-COMPONENT_RESULT.json": (
        "59abd9e73f5b8df2e221d7a128fcef0bdf85f8aa66089a23fa7fe9476fcd0810"
    ),
    "inputs/binding/settled-representation.json": (
        "08705beaec0648c6b4577efadcad9b0946f033e1b1c7e7ba9223c224419c03ea"
    ),
    "inputs/source/cuda_graph_runner.py": (
        "7d1898247e80ff6a446eb42e4968d2eea0df30b109ee2d089a9ad78791bc079e"
    ),
    "inputs/source/model_runner.py": (
        "f4dad073eb9f89afd4cda0439b97dee63f8de131d0ed10078b817dba1f978f59"
    ),
    "inputs/source/sampler.py": (
        "85541951e1cf50d10c54978178e403ff9d4aa6f223e629ea91965735ba882a8f"
    ),
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def emit(event: str, **fields: Any) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    row = {"timestamp_utc": utc_now(), "event": event, **fields}
    with (ARTIFACTS / "OWNER_EVENTS.jsonl").open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    atomic_json(ARTIFACTS / "OWNER_STATE.json", row)


def update_status(**updates: Any) -> None:
    path = PROJECT_ROOT / "STATUS.json"
    value = json.loads(path.read_text())
    value.update(updates)
    atomic_json(path, value)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        relative = item.relative_to(path).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(sha256(item)))
    return digest.hexdigest()


def validate_inputs() -> None:
    verifier = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "verify_director_binding.py")],
        text=True,
        capture_output=True,
        timeout=30,
    )
    if verifier.returncode:
        raise RuntimeError(f"director_binding_invalid:{verifier.stderr[-1000:]}")
    for name, digest in INPUT_SHA256.items():
        if sha256(HERE / name) != digest:
            raise RuntimeError(f"project_local_snapshot_invalid:{name}")
    prior = PROJECT_ROOT / "artifacts"
    if sha256(prior / "FINAL_TERMINAL.json") != PRIOR_FINAL_SHA256:
        raise RuntimeError("prior_final_terminal_mutated")
    if tree_sha256(prior) != PRIOR_ARTIFACT_TREE_SHA256:
        raise RuntimeError("prior_attempt_tree_mutated")


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
        f"rm -rf {REMOTE}.stage && mkdir -p {REMOTE}.stage",
        60,
    )
    if prepared.returncode:
        raise RuntimeError(f"remote_stage_prepare_failed:{prepared.stderr[-1000:]}")
    scp_to(ip, HERE / "inputs", f"{REMOTE}.stage/input", recursive=True)
    scp_to(ip, HERE / "remote_graph_endpoint.sh", f"{REMOTE}.stage/")
    finalized = remote(
        ip,
        f"rm -rf {REMOTE}.previous && "
        f"if test -d {REMOTE}; then mv {REMOTE} {REMOTE}.previous; fi && "
        f"mv {REMOTE}.stage {REMOTE}",
        60,
    )
    if finalized.returncode:
        raise RuntimeError(f"remote_stage_finalize_failed:{finalized.stderr[-1000:]}")


def retrieve(
    ip: str, attempt: int, stdout: str, stderr: str
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    root = ARTIFACTS / f"attempt{attempt}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "worker.stdout").write_text(stdout)
    (root / "worker.stderr").write_text(stderr)
    requested = {
        "WORKER_TERMINAL.json": f"{REMOTE}/artifacts/WORKER_TERMINAL.json",
        "INVOCATION_STATE.json": f"{REMOTE}/artifacts/INVOCATION_STATE.json",
        "fp8-graph-endpoint-compact.tar.gz": (
            f"{REMOTE}/fp8-graph-endpoint-compact.tar.gz"
        ),
        "fp8-graph-endpoint-compact.tar.gz.sha256": (
            f"{REMOTE}/fp8-graph-endpoint-compact.tar.gz.sha256"
        ),
    }
    observed: dict[str, bool] = {}
    for name, source in requested.items():
        success = False
        while dt.datetime.now(dt.timezone.utc) < ABSOLUTE_DEADLINE:
            if scp_from(ip, source, root / name):
                success = True
                break
            emit("retrieval_retry", name=name, attempt=attempt)
            time.sleep(3)
            if name not in {"WORKER_TERMINAL.json", "INVOCATION_STATE.json"}:
                # Compact archive absence is allowed only after the two arm-state
                # records have been resolved.
                if (
                    (root / "WORKER_TERMINAL.json").exists()
                    and (root / "INVOCATION_STATE.json").exists()
                ):
                    break
        observed[name] = success
        emit("retrieval", name=name, success=success, attempt=attempt)
    terminal_path = root / "WORKER_TERMINAL.json"
    state_path = root / "INVOCATION_STATE.json"
    if not terminal_path.exists() or not state_path.exists():
        raise RuntimeError("remote_compact_arm_state_unresolved")
    terminal = json.loads(terminal_path.read_text())
    state = json.loads(state_path.read_text())
    archive = root / "fp8-graph-endpoint-compact.tar.gz"
    if archive.exists():
        extracted = root / "retrieved"
        extracted.mkdir(exist_ok=True)
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(extracted, filter="data")
    atomic_json(root / "RETRIEVAL.json", observed)
    return terminal, state, root


def incremental_cost(claimed_at: dt.datetime) -> float:
    return (
        max(
            0.0,
            (dt.datetime.now(dt.timezone.utc) - claimed_at).total_seconds(),
        )
        / 3600
        * RATE_USD_PER_HOUR
    )


def cumulative_cost(claimed_at: dt.datetime) -> float:
    return PRIOR_SPEND_USD + incremental_cost(claimed_at)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", default="foreground")
    parser.add_argument("--start-attempt", type=int, default=1)
    args = parser.parse_args()
    validate_inputs()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    pool = GpuPool(LAB)
    lease_seconds = max(
        300,
        int((ABSOLUTE_DEADLINE - dt.datetime.now(dt.timezone.utc)).total_seconds()),
    )
    bench = pool.claim(PROJECT, bench_id=BENCH, lease_seconds=lease_seconds)
    claimed_at = dt.datetime.fromisoformat(
        bench["claim"]["claimed_at"].replace("Z", "+00:00")
    )
    if cumulative_cost(claimed_at) >= AUTHORIZED_USD:
        pool.release(
            PROJECT,
            contents={
                "project": PROJECT,
                "fp8_tied_head_result": "cumulative_spend_gate",
                "fp8_tied_head_actual_spend_usd": cumulative_cost(claimed_at),
            },
            condition="ready",
        )
        raise RuntimeError("cumulative_project_reservation_exhausted")
    heartbeat = Heartbeat(pool)
    heartbeat.start()
    released = False
    update_status(
        actual_spend_usd=cumulative_cost(claimed_at),
        active_session={
            "kind": "bounded_shared_bench_owner",
            "pid": os.getpid(),
            "unit": args.unit,
            "unit_manager": "foreground",
            "deadline_utc": ABSOLUTE_DEADLINE.isoformat().replace("+00:00", "Z"),
            "artifact_root": str(ARTIFACTS),
            "forward_progress": (
                "claimed; prior artifact tree and immutable iteration inputs validated"
            ),
        },
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
            if dt.datetime.now(dt.timezone.utc) >= ABSOLUTE_DEADLINE - dt.timedelta(
                minutes=5
            ):
                raise RuntimeError("absolute_deadline_requires_director_disposition")
            stage(ip)
            session = json.loads((PROJECT_ROOT / "STATUS.json").read_text())[
                "active_session"
            ]
            update_status(
                actual_spend_usd=cumulative_cost(claimed_at),
                active_session={
                    **session,
                    "forward_progress": f"attempt {attempt}: worker running",
                },
            )
            timeout = max(
                60,
                min(
                    9000,
                    int(
                        (
                            ABSOLUTE_DEADLINE - dt.datetime.now(dt.timezone.utc)
                        ).total_seconds()
                    )
                    - 240,
                ),
            )
            worker = remote(
                ip,
                f"timeout --signal=TERM {timeout} "
                f"env FP8_HEAD_REMOTE_ROOT={REMOTE} "
                f"bash {REMOTE}/remote_graph_endpoint.sh",
                timeout + 90,
            )
            terminal, state, final_root = retrieve(
                ip, attempt, worker.stdout, worker.stderr
            )
            scientific = bool(
                state.get("smoke_science_started")
                or state.get("endpoint_science_started")
            )
            if terminal.get("classification") != "integration_failure" or scientific:
                break
            repair_deadline = min(
                ABSOLUTE_DEADLINE - dt.timedelta(minutes=5),
                dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15),
            )
            repair_ready = HERE / "REPAIR_READY.json"
            atomic_json(
                repair_ready,
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
                    repair_ready.unlink(missing_ok=True)
                    break
                time.sleep(5)
            else:
                raise RuntimeError("repair_deadline_expired")
        if not terminal:
            raise RuntimeError("remote_compact_terminal_missing")
        cost = cumulative_cost(claimed_at)
        if cost > AUTHORIZED_USD:
            raise RuntimeError("cumulative_project_reservation_exceeded")
        endpoint_path = (
            final_root / "retrieved/ENDPOINT_RESULT.json" if final_root else None
        )
        endpoint = (
            json.loads(endpoint_path.read_text())
            if endpoint_path and endpoint_path.exists()
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
            "incremental_iteration_spend_usd": incremental_cost(claimed_at),
            "prior_spend_usd": PRIOR_SPEND_USD,
            "prior_final_terminal_sha256": PRIOR_FINAL_SHA256,
            "prior_artifact_tree_sha256": PRIOR_ARTIFACT_TREE_SHA256,
            "component_replayed": False,
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
                "runtime": (
                    "Graph-bound E4M3 tied-head continuation completed; "
                    "settled component was not replayed"
                ),
                "server_state": (
                    "FP8 tied-head graph-bound ring candidate retained healthy"
                    if endpoint
                    else "No qualified endpoint claimed"
                ),
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
                "Director may schedule the campaign quality suite; no quality claim was made."
                if endpoint and endpoint.get("pass")
                else "Return to the director; the exact graph-bound tied-head endpoint is closed."
            ),
        )
        return 0
    except Exception as error:
        cost = cumulative_cost(claimed_at)
        atomic_json(
            ARTIFACTS / "FINAL_TERMINAL.json",
            {
                "schema_version": 1,
                "status": "terminal",
                "classification": "typed_external_or_integration_blocker",
                "error": f"{type(error).__name__}:{error}",
                "actual_spend_usd": cost,
                "incremental_iteration_spend_usd": incremental_cost(claimed_at),
                "prior_spend_usd": PRIOR_SPEND_USD,
                "prior_final_terminal_sha256": PRIOR_FINAL_SHA256,
                "prior_artifact_tree_sha256": PRIOR_ARTIFACT_TREE_SHA256,
                "worker_terminal": terminal,
                "invocation_state": state,
                "timestamp_utc": utc_now(),
            },
        )
        update_status(
            status="completed",
            actual_spend_usd=cost,
            active_session=None,
            summary=(
                "typed_external_or_integration_blocker:"
                f"{type(error).__name__}:{error}"
            ),
            terminal_artifact=str(ARTIFACTS / "FINAL_TERMINAL.json"),
        )
        if not released:
            pool.release(
                PROJECT,
                contents={
                    "project": PROJECT,
                    "fp8_tied_head_result": (
                        "typed_external_or_integration_blocker"
                    ),
                    "fp8_tied_head_actual_spend_usd": cost,
                    "artifacts": str(ARTIFACTS.relative_to(REPO)),
                    "runtime": f"{type(error).__name__}:{error}",
                },
                condition=(
                    "maintenance"
                    if "unreachable" in str(error)
                    or "arm_state_unresolved" in str(error)
                    else "ready"
                ),
            )
            released = True
        return 1
    finally:
        heartbeat.close()


if __name__ == "__main__":
    raise SystemExit(main())
