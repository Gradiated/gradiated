#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
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
STACK_STATUS = HERE.parent / "gemma4_h200_width16384_ring_stack/STATUS.json"
sys.path.insert(0, str(REPO / "research/factory/src"))
sys.path.insert(
    0, str(REPO / "research/lab/experiments/glm47flash/campaign_100/nebius")
)

from grad_research.gpu_pool import GpuPool  # noqa: E402
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base  # noqa: E402


PROJECT = "gemma4_h200_mirrored_ring_e5m2_local_fa3"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
INSTANCE = "computeinstance-e00vhh6h29fj68x91g"
REMOTE = "/home/glmrunner/gemma4-mirrored-ring-e5m2"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
RATE_USD_PER_HOUR = 2.46
AUTHORIZED_USD = 14.0
ABSOLUTE_DEADLINE = dt.datetime(2026, 7, 23, 20, 15, tzinfo=dt.timezone.utc)
MAX_CLAIM_SECONDS = 90 * 60
ARTIFACTS = HERE / "artifacts"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def emit(event: str, **fields: Any) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    row = {"timestamp_utc": utc_now(), "event": event, **fields}
    with (ARTIFACTS / "OWNER_EVENTS.jsonl").open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    atomic_json(ARTIFACTS / "OWNER_STATE.json", row)


def update_status(**updates: Any) -> None:
    path = HERE / "STATUS.json"
    value = json.loads(path.read_text())
    value.update(updates)
    atomic_json(path, value)


def validate_local_inputs() -> dict[str, Any]:
    subprocess.run(
        [sys.executable, str(HERE / "verify_director_binding.py")],
        check=True,
        cwd=HERE,
    )
    manifest = json.loads((HERE / "GPU_INPUT_MANIFEST.json").read_text())
    for row in manifest["files"]:
        path = HERE / row["path"]
        if path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            raise RuntimeError(f"immutable input mismatch:{row['path']}")
    if sha256(HERE / "inputs/bound/ring_e5m2_flash_ops.so") != (
        "cddaf2bc58281a935c638ebec0f615cbabb8f6d2833bff8ca6c242063a05075f"
    ):
        raise RuntimeError("bound direct-E5M2 extension mismatch")
    return manifest


def dependency_complete() -> bool:
    try:
        status = json.loads(STACK_STATUS.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return status.get("status") in {
        "completed",
        "terminal",
        "closed",
        "failed",
        "blocked",
    }


def remote(ip: str, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*ssh_base(ip, KEY), command],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def scp_to(ip: str, source: Path, destination: str) -> None:
    result = subprocess.run(
        [
            "scp",
            *ssh_base(ip, KEY)[1:-1],
            str(source),
            f"{SSH_USER}@{ip}:{destination}",
        ],
        text=True,
        capture_output=True,
        timeout=900,
    )
    if result.returncode:
        raise RuntimeError(f"scp_to_failed:{source.name}:{result.stderr[-1000:]}")


def scp_from(ip: str, source: str, destination: Path) -> tuple[bool, str]:
    result = subprocess.run(
        [
            "scp",
            *ssh_base(ip, KEY)[1:-1],
            f"{SSH_USER}@{ip}:{source}",
            str(destination),
        ],
        text=True,
        capture_output=True,
        timeout=900,
    )
    return result.returncode == 0, result.stderr[-1000:]


def stage(ip: str, manifest: dict[str, Any]) -> None:
    result = remote(ip, f"mkdir -p {shlex.quote(REMOTE + '/input')}", 60)
    if result.returncode:
        raise RuntimeError(f"remote_root_failed:{result.stderr[-1000:]}")
    for row in manifest["files"]:
        target = f"{REMOTE}/input/{row['remote_name']}"
        probe = remote(
            ip,
            f"test -f {shlex.quote(target)} && "
            f"test $(stat -c %s {shlex.quote(target)}) -eq {row['bytes']} && "
            f"test $(sha256sum {shlex.quote(target)} | cut -d' ' -f1) = {row['sha256']}",
            120,
        )
        if probe.returncode == 0:
            emit("input_matched", path=row["path"], sha256=row["sha256"])
            continue
        part = target + f".part.{os.getpid()}"
        scp_to(ip, HERE / row["path"], part)
        finish = remote(
            ip,
            f"test $(stat -c %s {shlex.quote(part)}) -eq {row['bytes']} && "
            f"test $(sha256sum {shlex.quote(part)} | cut -d' ' -f1) = {row['sha256']} && "
            f"chmod 0444 {shlex.quote(part)} && mv -f {shlex.quote(part)} {shlex.quote(target)}",
            120,
        )
        if finish.returncode:
            raise RuntimeError(f"remote_finalize_failed:{row['remote_name']}")
        emit("input_finalized", path=row["path"], sha256=row["sha256"])


def validate_checkpoint(ip: str) -> None:
    rows = []
    for line in (HERE / "inputs/CHECKPOINT_SHA256SUMS.txt").read_text().splitlines():
        digest, path = line.split(maxsplit=1)
        rows.append((digest, Path(path).name))
    resident = "/home/glmrunner/gemma4-async-result-pipeline/checkpoint"
    checks = " ".join(f"{digest}:{shlex.quote(name)}" for digest, name in rows)
    command = (
        f"set -e; resident={shlex.quote(resident)}; test -d \"$resident\"; "
        f"for item in {checks}; do hash=${{item%%:*}}; name=${{item#*:}}; "
        "test -f \"$resident/$name\"; "
        "printf '%s  %s\\n' \"$hash\" \"$resident/$name\" | sha256sum -c -; done"
    )
    result = remote(ip, command, 1800)
    (ARTIFACTS / "checkpoint.stdout").write_text(result.stdout)
    (ARTIFACTS / "checkpoint.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("resident checkpoint manifest mismatch")
    emit("checkpoint_manifest_validated", files=len(rows), resident=resident)


class Heartbeat(threading.Thread):
    def __init__(self, pool: GpuPool):
        super().__init__(daemon=True)
        self.pool = pool
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.wait(40):
            try:
                self.pool.heartbeat(PROJECT)
            except Exception as error:
                emit("heartbeat_failure", error=repr(error))
                return

    def close(self) -> None:
        self.stop_event.set()
        self.join(timeout=5)


def retrieve_stage(ip: str, stage_name: str, attempt: int) -> dict[str, Any]:
    root = ARTIFACTS / f"{stage_name}-attempt{attempt}"
    root.mkdir(parents=True, exist_ok=True)
    remote_names = (
        f"{stage_name}-compact.tar.gz.sha256",
        f"{stage_name}-compact.tar.gz",
    )
    for name in remote_names:
        success, diagnostic = scp_from(ip, f"{REMOTE}/{name}", root / name)
        emit("retrieval", stage=stage_name, path=name, success=success)
        if not success:
            raise RuntimeError(
                f"{stage_name}_compact_retrieval_failed:{name}:{diagnostic}"
            )
    expected = (root / remote_names[0]).read_text().split()[0]
    archive = root / remote_names[1]
    if sha256(archive) != expected:
        raise RuntimeError(f"{stage_name}_compact_hash_mismatch")
    extracted = root / "retrieved"
    extracted.mkdir(exist_ok=True)
    with tarfile.open(archive, "r:gz") as handle:
        handle.extractall(extracted, filter="data")
    return {
        "root": root,
        "retrieved": extracted,
        "remote_terminal": json.loads(
            (extracted / "REMOTE_TERMINAL.json").read_text()
        )
        if (extracted / "REMOTE_TERMINAL.json").is_file()
        else json.loads((extracted / "WORKER_TERMINAL.json").read_text()),
    }


def repair_wait(stage_name: str, attempt: int, deadline: dt.datetime) -> None:
    ready = HERE / "REPAIR_READY.json"
    request = HERE / "REPAIR_REQUEST.json"
    atomic_json(
        ready,
        {
            "schema_version": 1,
            "status": "repair_ready",
            "stage": stage_name,
            "attempt": attempt,
            "absolute_repair_deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
            "intervention_workload_bound_identities_and_gates_unchanged": True,
        },
    )
    emit("repair_ready", stage=stage_name, attempt=attempt)
    while dt.datetime.now(dt.timezone.utc) < deadline:
        if request.is_file():
            request.unlink()
            ready.unlink(missing_ok=True)
            emit("repair_request_consumed", stage=stage_name, attempt=attempt)
            return
        time.sleep(10)
    raise TimeoutError(f"repair deadline reached:{stage_name}")


def claimed_cost(claimed_at: dt.datetime) -> float:
    elapsed = max(
        0.0,
        (dt.datetime.now(dt.timezone.utc) - claimed_at).total_seconds(),
    )
    return elapsed / 3600 * RATE_USD_PER_HOUR


def final_terminal(
    classification: str,
    component: dict[str, Any] | None,
    endpoint: dict[str, Any] | None,
    cost: float,
) -> dict[str, Any]:
    value = {
        "schema_version": 1,
        "status": "terminal",
        "classification": classification,
        "actual_spend_usd": cost,
        "component": component,
        "endpoint": endpoint,
        "timestamp_utc": utc_now(),
    }
    atomic_json(ARTIFACTS / "FINAL_TERMINAL.json", value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-for-priority", action="store_true")
    parser.add_argument("--unit")
    parser.add_argument("--unit-manager", default="user")
    args = parser.parse_args()
    manifest = validate_local_inputs()
    update_status(
        active_session={
            "kind": "bounded_shared_bench_owner",
            "pid": os.getpid(),
            "unit": args.unit,
            "unit_manager": args.unit_manager,
            "deadline_utc": ABSOLUTE_DEADLINE.isoformat().replace("+00:00", "Z"),
            "expected_terminal": (
                "one complete producer-consumer component terminal and, only "
                "if admitted, one exact c32 endpoint terminal"
            ),
            "artifact_root": str(ARTIFACTS),
            "remote_root": REMOTE,
            "bench_id": BENCH,
            "forward_progress": "immutable_inputs_validated_waiting_for_higher_priority_stack",
        }
    )
    while not dependency_complete():
        if not args.wait_for_priority:
            emit("higher_priority_dependency_active", dependency=str(STACK_STATUS))
            update_status(active_session=None)
            return 4
        if dt.datetime.now(dt.timezone.utc) >= ABSOLUTE_DEADLINE - dt.timedelta(
            minutes=50
        ):
            terminal = final_terminal(
                "higher_priority_dependency_consumed_runway", None, None, 0.0
            )
            update_status(
                status="blocked",
                actual_spend_usd=0.0,
                active_session=None,
                summary=terminal["classification"],
            )
            return 4
        time.sleep(20)

    manifest = validate_local_inputs()
    pool = GpuPool(LAB)
    bench = pool.claim(PROJECT, bench_id=BENCH, lease_seconds=MAX_CLAIM_SECONDS)
    claimed_at = dt.datetime.fromisoformat(
        bench["claim"]["claimed_at"].replace("Z", "+00:00")
    )
    claim_deadline = min(
        ABSOLUTE_DEADLINE, claimed_at + dt.timedelta(seconds=MAX_CLAIM_SECONDS)
    )
    heartbeat = Heartbeat(pool)
    heartbeat.start()
    released = False
    component_result: dict[str, Any] | None = None
    endpoint_result: dict[str, Any] | None = None
    try:
        instance = get_instance(INSTANCE)
        ip = extract_public_ipv4(instance)
        if not ip:
            raise RuntimeError("bench_public_ip_unavailable")
        validate_checkpoint(ip)
        stage(ip, manifest)
        update_status(
            active_session={
                **json.loads((HERE / "STATUS.json").read_text())["active_session"],
                "claimed_at_utc": claimed_at.isoformat().replace("+00:00", "Z"),
                "claim_deadline_utc": claim_deadline.isoformat().replace("+00:00", "Z"),
                "forward_progress": "component_discovery_and_scientific_invocation",
            }
        )

        component_attempt = 0
        while component_result is None:
            component_attempt += 1
            result = remote(
                ip,
                f"MIRRORED_RING_REMOTE_ROOT={shlex.quote(REMOTE)} "
                f"bash {shlex.quote(REMOTE + '/input/remote_component.sh')}",
                max(
                    60,
                    int(
                        (
                            claim_deadline - dt.datetime.now(dt.timezone.utc)
                        ).total_seconds()
                    ),
                ),
            )
            attempt_root = ARTIFACTS / f"component-attempt{component_attempt}"
            attempt_root.mkdir(parents=True, exist_ok=True)
            (attempt_root / "remote.stdout").write_text(result.stdout)
            (attempt_root / "remote.stderr").write_text(result.stderr)
            evidence = retrieve_stage(ip, "component", component_attempt)
            terminal_path = evidence["retrieved"] / "COMPONENT_TERMINAL.json"
            if terminal_path.is_file():
                component_result = json.loads(terminal_path.read_text())
                atomic_json(ARTIFACTS / "COMPONENT_TERMINAL.json", component_result)
                break
            invocation = evidence["remote_terminal"]
            if not invocation.get("candidate_scientific_invocation_started"):
                repair_wait("component", component_attempt, claim_deadline)
                manifest = json.loads((HERE / "GPU_INPUT_MANIFEST.json").read_text())
                validate_local_inputs()
                stage(ip, manifest)
                continue
            raise RuntimeError("component_failure_after_scientific_invocation")

        cost = claimed_cost(claimed_at)
        update_status(actual_spend_usd=cost)
        if not component_result.get("component_positive"):
            terminal = final_terminal(
                "component_semantic_or_nonpositive_reject",
                component_result,
                None,
                cost,
            )
            pool.release(
                PROJECT,
                contents={
                    "project": PROJECT,
                    "mirrored_ring_e5m2_result": terminal["classification"],
                    "mirrored_ring_e5m2_actual_spend_usd": cost,
                    "mirrored_ring_component_artifacts": str(ARTIFACTS.relative_to(REPO)),
                    "caches": "Pinned image, checkpoint, Triton ring, and direct-E5M2 FA3 caches retained",
                    "server_state": "No candidate endpoint launched; previous server state unchanged",
                },
                condition="ready",
            )
            released = True
            update_status(
                status="completed",
                active_session=None,
                summary=terminal["classification"],
                next_action="Director should close the mirrored-ring lane; the complete producer-consumer gate did not pass.",
            )
            return 0

        update_status(
            active_session={
                **json.loads((HERE / "STATUS.json").read_text())["active_session"],
                "forward_progress": "component_positive_conditional_exact_c32_endpoint",
            }
        )
        endpoint_attempt = 0
        while endpoint_result is None:
            endpoint_attempt += 1
            result = remote(
                ip,
                f"MIRRORED_RING_REMOTE_ROOT={shlex.quote(REMOTE)} "
                f"bash {shlex.quote(REMOTE + '/input/remote_endpoint.sh')}",
                max(
                    60,
                    int(
                        (
                            claim_deadline - dt.datetime.now(dt.timezone.utc)
                        ).total_seconds()
                    ),
                ),
            )
            attempt_root = ARTIFACTS / f"endpoint-attempt{endpoint_attempt}"
            attempt_root.mkdir(parents=True, exist_ok=True)
            (attempt_root / "remote.stdout").write_text(result.stdout)
            (attempt_root / "remote.stderr").write_text(result.stderr)
            evidence = retrieve_stage(ip, "endpoint", endpoint_attempt)
            endpoint_path = evidence["retrieved"] / "ENDPOINT_RESULT.json"
            if endpoint_path.is_file():
                endpoint_result = json.loads(endpoint_path.read_text())
                atomic_json(ARTIFACTS / "ENDPOINT_RESULT.json", endpoint_result)
                break
            invocation_path = evidence["retrieved"] / "INVOCATION_STATE.json"
            invocation = (
                json.loads(invocation_path.read_text())
                if invocation_path.is_file()
                else {}
            )
            if not invocation.get("candidate_science_started"):
                repair_wait("endpoint", endpoint_attempt, claim_deadline)
                manifest = json.loads((HERE / "GPU_INPUT_MANIFEST.json").read_text())
                validate_local_inputs()
                stage(ip, manifest)
                continue
            raise RuntimeError("endpoint_failure_after_scientific_invocation")

        cost = claimed_cost(claimed_at)
        classification = endpoint_result["classification"]
        terminal = final_terminal(
            classification, component_result, endpoint_result, cost
        )
        pool.release(
            PROJECT,
            contents={
                "project": PROJECT,
                "mirrored_ring_e5m2_result": classification,
                "mirrored_ring_e5m2_actual_spend_usd": cost,
                "mirrored_ring_component_median_ms": component_result["timing"][
                    "candidate"
                ]["median_ms"],
                "mirrored_ring_endpoint_seconds_per_request": endpoint_result[
                    "candidate_seconds_per_request"
                ],
                "artifacts": str(ARTIFACTS.relative_to(REPO)),
                "caches": "FP8, QKV, deferred-local-KV, CUDA graph, mirrored ring, Triton, and direct-E5M2 FA3 caches retained",
                "server_state": "Healthy final mirrored-ring candidate server retained if responsive",
            },
            condition="ready",
        )
        released = True
        update_status(
            status="completed",
            actual_spend_usd=cost,
            active_session=None,
            summary=classification,
            next_action=(
                "Director should retain and stack the mirrored-ring endpoint."
                if classification == "retain_mirrored_ring"
                else "Director should retain the settled ring endpoint and close this lane."
            ),
        )
        return 0
    except Exception as error:
        cost = claimed_cost(claimed_at)
        final_terminal(
            "typed_owner_or_external_failure",
            component_result,
            endpoint_result,
            cost,
        )
        update_status(
            status="completed",
            actual_spend_usd=cost,
            active_session=None,
            summary=f"typed_owner_or_external_failure:{type(error).__name__}:{error}",
        )
        if not released:
            pool.release(
                PROJECT,
                contents={
                    "project": PROJECT,
                    "mirrored_ring_e5m2_result": "typed_owner_or_external_failure",
                    "mirrored_ring_e5m2_actual_spend_usd": cost,
                    "artifacts": str(ARTIFACTS.relative_to(REPO)),
                    "runtime": f"{type(error).__name__}:{error}",
                    "server_state": "Inspect retained remote diagnostics before reuse",
                },
                condition="maintenance",
            )
            released = True
        raise
    finally:
        heartbeat.close()


if __name__ == "__main__":
    raise SystemExit(main())
