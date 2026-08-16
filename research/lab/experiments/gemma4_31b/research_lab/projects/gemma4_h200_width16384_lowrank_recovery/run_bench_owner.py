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
sys.path.insert(0, str(REPO / "research/factory/src"))
sys.path.insert(
    0, str(REPO / "research/lab/experiments/glm47flash/campaign_100/nebius")
)

from grad_research.gpu_pool import GpuPool  # noqa: E402
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base  # noqa: E402


PROJECT = "gemma4_h200_width16384_lowrank_recovery"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
INSTANCE = "computeinstance-e00vhh6h29fj68x91g"
REMOTE = "/dev/shm/gemma4-width16384-lowrank-recovery"
CHECKPOINT = "/home/glmrunner/gemma4-async-result-pipeline/checkpoint"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
RATE_USD_PER_HOUR = 2.46
AUTHORIZED_USD = 20.0
ABSOLUTE_DEADLINE = dt.datetime(2026, 7, 24, 0, 2, tzinfo=dt.timezone.utc)
ARTIFACTS = HERE / "artifacts"
LOCAL_INPUTS = [
    HERE / "DIRECTOR_BINDING.json",
    HERE / "EXPERIMENT_CONTRACT.json",
    HERE / "remote_recovery.py",
    HERE / "remote_endpoint.sh",
    HERE / "inputs/JOINT_NORM_SELECTION.json",
    *sorted((HERE / "inputs/stack").glob("*.py")),
]


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


def scp_from(ip: str, source: str, destination: Path, timeout: int = 1800) -> None:
    result = subprocess.run(
        [
            "scp",
            *ssh_base(ip, KEY)[1:-1],
            f"{SSH_USER}@{ip}:{source}",
            str(destination),
        ],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"scp_from_failed:{source}:{result.stderr[-1000:]}")


def validate_local_inputs() -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(HERE / "verify_director_binding.py")],
        cwd=HERE,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(f"director_binding_invalid:{result.stderr[-1000:]}")
    files = []
    for path in LOCAL_INPUTS:
        files.append(
            {
                "path": str(path.relative_to(HERE)),
                "remote_name": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    names = [row["remote_name"] for row in files]
    if len(names) != len(set(names)):
        raise RuntimeError("staged input basename collision")
    manifest = {
        "schema_version": 1,
        "binding_valid": True,
        "generated_utc": utc_now(),
        "files": files,
    }
    atomic_json(ARTIFACTS / "GPU_INPUT_MANIFEST.json", manifest)
    return manifest


def stage(ip: str, manifest: dict[str, Any]) -> None:
    result = remote(ip, f"mkdir -p {shlex.quote(REMOTE + '/input')}", 60)
    if result.returncode:
        raise RuntimeError(f"remote_root_failed:{result.stderr[-1000:]}")
    for row in manifest["files"]:
        source = HERE / row["path"]
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
        scp_to(ip, source, part)
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
    checks = " ".join(f"{digest}:{shlex.quote(name)}" for digest, name in rows)
    command = (
        f"set -e; resident={shlex.quote(CHECKPOINT)}; test -d \"$resident\"; "
        f"for item in {checks}; do hash=${{item%%:*}}; name=${{item#*:}}; "
        "test -f \"$resident/$name\"; "
        "printf '%s  %s\\n' \"$hash\" \"$resident/$name\" | sha256sum -c -; done"
    )
    result = remote(ip, command, 2400)
    (ARTIFACTS / "checkpoint.stdout").write_text(result.stdout)
    (ARTIFACTS / "checkpoint.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("resident checkpoint manifest mismatch")
    emit("checkpoint_manifest_validated", files=len(rows), resident=CHECKPOINT)


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

    def close(self) -> None:
        self.stop_event.set()
        self.join(timeout=5)


def repair_wait(stage_name: str, attempt: int) -> None:
    deadline = min(ABSOLUTE_DEADLINE, dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=20))
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
        time.sleep(5)
    raise TimeoutError(f"repair deadline reached:{stage_name}")


def retrieve_json_if_present(ip: str, remote_path: str, local_path: Path) -> dict[str, Any] | None:
    probe = remote(ip, f"test -f {shlex.quote(remote_path)}", 30)
    if probe.returncode:
        return None
    scp_from(ip, remote_path, local_path)
    return json.loads(local_path.read_text())


def run_producer(ip: str) -> dict[str, Any]:
    attempt = 0
    while True:
        attempt += 1
        manifest = validate_local_inputs()
        stage(ip, manifest)
        command = (
            "set -o pipefail; "
            "sudo docker rm -f gemma-width-recovery-producer >/dev/null 2>&1 || true; "
            f"rm -rf {shlex.quote(REMOTE + '/producer')}; "
            f"mkdir -p {shlex.quote(REMOTE + '/producer')}; "
            "sudo docker run --rm --name gemma-width-recovery-producer "
            "--gpus all --ipc=host "
            f"-v {shlex.quote(CHECKPOINT)}:/checkpoint:ro "
            f"-v {shlex.quote(REMOTE)}:/work/recovery "
            f"{shlex.quote(IMAGE)} python3 /work/recovery/input/remote_recovery.py "
            "--checkpoint /checkpoint "
            "--selection /work/recovery/input/JOINT_NORM_SELECTION.json "
            "--output /work/recovery/producer"
        )
        result = remote(
            ip,
            command,
            max(60, int((ABSOLUTE_DEADLINE - dt.datetime.now(dt.timezone.utc)).total_seconds())),
        )
        attempt_root = ARTIFACTS / f"producer-attempt{attempt}"
        attempt_root.mkdir(parents=True, exist_ok=True)
        (attempt_root / "remote.stdout").write_text(result.stdout)
        (attempt_root / "remote.stderr").write_text(result.stderr)
        invocation = retrieve_json_if_present(
            ip,
            f"{REMOTE}/producer/INVOCATION_STATE.json",
            attempt_root / "INVOCATION_STATE.json",
        ) or {}
        terminal = retrieve_json_if_present(
            ip,
            f"{REMOTE}/producer/PRODUCER_TERMINAL.json",
            ARTIFACTS / "PRODUCER_TERMINAL.json",
        )
        retrieve_json_if_present(
            ip,
            f"{REMOTE}/producer/FACTOR_MANIFEST.json",
            ARTIFACTS / "FACTOR_MANIFEST.json",
        )
        retrieve_json_if_present(
            ip,
            f"{REMOTE}/producer/LAYER_RESULTS.json",
            ARTIFACTS / "LAYER_RESULTS.json",
        )
        retrieve_json_if_present(
            ip,
            f"{REMOTE}/producer/CAPTURE_IDENTITY.json",
            ARTIFACTS / "CAPTURE_IDENTITY.json",
        )
        if terminal is not None:
            return terminal
        layer_rows = (
            json.loads((ARTIFACTS / "LAYER_RESULTS.json").read_text()).get("rows", [])
            if (ARTIFACTS / "LAYER_RESULTS.json").is_file()
            else []
        )
        # A model-load/import failure before any layer row is an integration
        # failure even though the conservative pre-call marker records intent.
        if not layer_rows:
            repair_wait("producer_pre_science", attempt)
            continue
        raise RuntimeError(
            f"producer_failed_after_scientific_rows:{len(layer_rows)}:{result.returncode}"
        )


def retrieve_endpoint(ip: str, attempt: int) -> Path:
    root = ARTIFACTS / f"endpoint-attempt{attempt}"
    root.mkdir(parents=True, exist_ok=True)
    for name in ("endpoint-compact.tar.gz.sha256", "endpoint-compact.tar.gz"):
        scp_from(ip, f"{REMOTE}/{name}", root / name)
    expected = (root / "endpoint-compact.tar.gz.sha256").read_text().split()[0]
    archive = root / "endpoint-compact.tar.gz"
    if sha256(archive) != expected:
        raise RuntimeError("endpoint compact hash mismatch")
    extracted = root / "retrieved"
    extracted.mkdir(exist_ok=True)
    with tarfile.open(archive, "r:gz") as handle:
        handle.extractall(extracted, filter="data")
    return extracted


def run_endpoint(ip: str) -> dict[str, Any]:
    attempt = 0
    while True:
        attempt += 1
        manifest = validate_local_inputs()
        stage(ip, manifest)
        result = remote(
            ip,
            f"RECOVERY_REMOTE_ROOT={shlex.quote(REMOTE)} "
            f"bash {shlex.quote(REMOTE + '/input/remote_endpoint.sh')}",
            max(60, int((ABSOLUTE_DEADLINE - dt.datetime.now(dt.timezone.utc)).total_seconds())),
        )
        attempt_root = ARTIFACTS / f"endpoint-attempt{attempt}"
        attempt_root.mkdir(parents=True, exist_ok=True)
        (attempt_root / "remote.stdout").write_text(result.stdout)
        (attempt_root / "remote.stderr").write_text(result.stderr)
        extracted = retrieve_endpoint(ip, attempt)
        endpoint = extracted / "ENDPOINT_RESULT.json"
        if endpoint.is_file():
            value = json.loads(endpoint.read_text())
            atomic_json(ARTIFACTS / "ENDPOINT_RESULT.json", value)
            return value
        smoke_path = extracted / "candidate.smoke.json"
        if smoke_path.is_file():
            smoke = json.loads(smoke_path.read_text())
            if smoke.get("pass") is False:
                return {
                    "classification": "reconstruction_or_coherence_reject",
                    "basic_coherence_gate": smoke,
                    "pass": False,
                }
        invocation_path = extracted / "INVOCATION_STATE.json"
        invocation = json.loads(invocation_path.read_text()) if invocation_path.is_file() else {}
        if not invocation.get("candidate_science_started"):
            repair_wait("endpoint_consumer_pre_c32", attempt)
            continue
        return {
            "classification": "endpoint_nonpositive_or_invalid",
            "pass": False,
            "diagnostic": "c32 invocation consumed without valid endpoint terminal",
        }


def claimed_cost(claimed_at: dt.datetime) -> float:
    elapsed = max(0.0, (dt.datetime.now(dt.timezone.utc) - claimed_at).total_seconds())
    return elapsed / 3600 * RATE_USD_PER_HOUR


def retrieve_factors(ip: str) -> dict[str, Any]:
    target = ARTIFACTS / "recovery-factors.tar"
    command = (
        f"tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 "
        f"--numeric-owner -cf {shlex.quote(REMOTE + '/recovery-factors.tar')} "
        f"-C {shlex.quote(REMOTE + '/producer')} factors && "
        f"sha256sum {shlex.quote(REMOTE + '/recovery-factors.tar')} > "
        f"{shlex.quote(REMOTE + '/recovery-factors.tar.sha256')}"
    )
    result = remote(ip, command, 900)
    if result.returncode:
        raise RuntimeError(f"factor archive creation failed:{result.stderr[-1000:]}")
    scp_from(ip, f"{REMOTE}/recovery-factors.tar.sha256", target.with_suffix(".tar.sha256"))
    scp_from(ip, f"{REMOTE}/recovery-factors.tar", target, timeout=2400)
    expected = target.with_suffix(".tar.sha256").read_text().split()[0]
    actual = sha256(target)
    if actual != expected:
        raise RuntimeError("retrieved factor archive hash mismatch")
    return {"path": str(target), "bytes": target.stat().st_size, "sha256": actual}


def final_terminal(
    classification: str,
    producer: dict[str, Any] | None,
    endpoint: dict[str, Any] | None,
    factors: dict[str, Any] | None,
    cost: float,
) -> dict[str, Any]:
    value = {
        "schema_version": 1,
        "status": "terminal",
        "classification": classification,
        "actual_spend_usd": cost,
        "producer": producer,
        "endpoint": endpoint,
        "retrieved_factors": factors,
        "timestamp_utc": utc_now(),
    }
    atomic_json(ARTIFACTS / "FINAL_TERMINAL.json", value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit")
    parser.add_argument("--unit-manager", default="user")
    args = parser.parse_args()
    validate_local_inputs()
    pool = GpuPool(LAB)
    bench = pool.claim(PROJECT, bench_id=BENCH, lease_seconds=3600)
    claimed_at = dt.datetime.fromisoformat(
        bench["claim"]["claimed_at"].replace("Z", "+00:00")
    )
    heartbeat = Heartbeat(pool)
    heartbeat.start()
    released = False
    producer: dict[str, Any] | None = None
    endpoint: dict[str, Any] | None = None
    factors: dict[str, Any] | None = None
    update_status(
        active_session={
            "kind": "bounded_shared_bench_owner",
            "pid": os.getpid(),
            "unit": args.unit,
            "unit_manager": args.unit_manager,
            "deadline_utc": ABSOLUTE_DEADLINE.isoformat().replace("+00:00", "Z"),
            "artifact_root": str(ARTIFACTS),
            "remote_root": REMOTE,
            "bench_id": BENCH,
            "expected_terminal": "held-out reconstruction and coherence reject, endpoint reject, or quality-suite nomination",
            "forward_progress": "claimed; validating checkpoint and staging producer",
        },
        summary="Bounded H200 low-rank recovery owner is active.",
    )
    try:
        instance = get_instance(INSTANCE)
        ip = extract_public_ipv4(instance)
        if not ip:
            raise RuntimeError("bench_public_ip_unavailable")
        validate_checkpoint(ip)
        producer = run_producer(ip)
        update_status(
            actual_spend_usd=claimed_cost(claimed_at),
            active_session={
                **json.loads((HERE / "STATUS.json").read_text())["active_session"],
                "forward_progress": "producer terminal persisted; conditional consumer",
            },
        )
        if producer["classification"] == "heldout_reconstruction_pass":
            endpoint = run_endpoint(ip)
            classification = endpoint["classification"]
        else:
            classification = "reconstruction_or_coherence_reject"
        factors = retrieve_factors(ip)
        cost = claimed_cost(claimed_at)
        terminal = final_terminal(classification, producer, endpoint, factors, cost)
        pool.release(
            PROJECT,
            contents={
                "project": PROJECT,
                "width16384_lowrank_recovery_result": classification,
                "width16384_lowrank_recovery_actual_spend_usd": cost,
                "artifacts": str(ARTIFACTS.relative_to(REPO)),
                "checkpoint": "Exact immutable checkpoint retained",
                "image": "Pinned SGLang v0.5.13 digest 6113665 retained",
                "caches": "Checkpoint, image, Triton ring, and dynamic-FP8 caches retained",
                "server_state": "Recovered candidate retained if healthy; otherwise factors are content-addressed locally",
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
                "Director may nominate the exact campaign quality suite."
                if classification == "quality_suite_nomination"
                else "Director should close this fixed recovery representation."
            ),
            terminal_artifact=str(ARTIFACTS / "FINAL_TERMINAL.json"),
        )
        emit("scientific_terminal", classification=classification, cost=cost)
        return 0
    except Exception as error:
        cost = claimed_cost(claimed_at)
        final_terminal(
            "typed_external_blocker",
            producer,
            endpoint,
            factors,
            cost,
        )
        update_status(
            status="completed",
            actual_spend_usd=cost,
            active_session=None,
            summary=f"typed_external_blocker:{type(error).__name__}:{error}",
            terminal_artifact=str(ARTIFACTS / "FINAL_TERMINAL.json"),
        )
        emit("typed_external_blocker", error=f"{type(error).__name__}:{error}")
        if not released:
            pool.release(
                PROJECT,
                contents={
                    "project": PROJECT,
                    "width16384_lowrank_recovery_result": "typed_external_blocker",
                    "width16384_lowrank_recovery_actual_spend_usd": cost,
                    "artifacts": str(ARTIFACTS.relative_to(REPO)),
                    "runtime": f"{type(error).__name__}:{error}",
                },
                condition="maintenance",
            )
            released = True
        raise
    finally:
        heartbeat.close()


if __name__ == "__main__":
    raise SystemExit(main())
