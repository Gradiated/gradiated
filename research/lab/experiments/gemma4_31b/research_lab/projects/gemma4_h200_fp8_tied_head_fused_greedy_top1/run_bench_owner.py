#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
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
NEBIUS = REPO / "research/lab/experiments/glm47flash/campaign_100/nebius"
sys.path.insert(0, str(REPO / "research/factory/src"))
sys.path.insert(0, str(NEBIUS))

from grad_research.gpu_pool import GpuPool  # noqa: E402
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base  # noqa: E402


PROJECT = "gemma4_h200_fp8_tied_head_fused_greedy_top1"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
INSTANCE = "computeinstance-e00vhh6h29fj68x91g"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
REMOTE = "/dev/shm/gemma4-fused-greedy-top1"
CHECKPOINT = "/home/glmrunner/gemma4-async-result-pipeline/checkpoint"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
RATE_USD_PER_HOUR = 2.46
AUTHORIZED_USD = 10.0
PRIOR_SPEND_USD = 0.48409905331666664
ABSOLUTE_DEADLINE = dt.datetime(2026, 7, 24, 1, 10, tzinfo=dt.timezone.utc)
ARTIFACTS = HERE / "artifacts"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def update_status(**updates: Any) -> None:
    path = HERE / "STATUS.json"
    value = json.loads(path.read_text())
    value.update(updates)
    atomic_json(path, value)


def emit(event: str, **fields: Any) -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    row = {"timestamp_utc": utc_now(), "event": event, **fields}
    with (ARTIFACTS / "OWNER_EVENTS.jsonl").open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    atomic_json(ARTIFACTS / "OWNER_STATE.json", row)


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


def claimed_cost(claimed_at: dt.datetime) -> float:
    return min(
        AUTHORIZED_USD,
        PRIOR_SPEND_USD
        + max(0.0, (dt.datetime.now(dt.timezone.utc) - claimed_at).total_seconds())
        / 3600
        * RATE_USD_PER_HOUR,
    )


def stage_component(ip: str) -> None:
    prepared = remote(
        ip,
        f"sudo rm -rf {REMOTE}.stage && mkdir -p {REMOTE}.stage/input",
        60,
    )
    if prepared.returncode:
        raise RuntimeError(f"stage_prepare_failed:{prepared.stderr[-1000:]}")
    for source in (
        HERE / "fused_top1.py",
        HERE / "component_benchmark.py",
        HERE / "inputs/predecessor/tied-head/real_hidden_rows.pt",
        HERE / "inputs/predecessor/CHECKPOINT_SHA256SUMS.txt",
    ):
        scp_to(ip, source, f"{REMOTE}.stage/input/")
    finalized = remote(
        ip,
        f"sudo rm -rf {REMOTE}.previous && "
        f"if test -d {REMOTE}; then mv {REMOTE} {REMOTE}.previous; fi && "
        f"mv {REMOTE}.stage {REMOTE}",
        60,
    )
    if finalized.returncode:
        raise RuntimeError(f"stage_finalize_failed:{finalized.stderr[-1000:]}")


def component_command(attempt: int) -> str:
    return (
        f"mkdir -p {REMOTE}/component-attempt{attempt} && "
        f"sudo docker run --rm --gpus all --ipc=host "
        f"-v {REMOTE}:/work "
        f"-v {CHECKPOINT}:/checkpoint:ro "
        f"-e TRITON_CACHE_DIR=/work/triton-cache "
        f"--entrypoint python3 {IMAGE} "
        f"/work/input/component_benchmark.py "
        f"--checkpoint /checkpoint "
        f"--hidden /work/input/real_hidden_rows.pt "
        f"--output /work/component-attempt{attempt} --repeats 40"
    )


def retrieve_component(
    ip: str,
    attempt: int,
    worker: subprocess.CompletedProcess[str],
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    root = ARTIFACTS / f"component-attempt{attempt}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "worker.stdout").write_text(worker.stdout)
    (root / "worker.stderr").write_text(worker.stderr)
    for name in ("INVOCATION_STATE.json", "COMPONENT_RESULT.json", "WORKER_TERMINAL.json"):
        scp_from(ip, f"{REMOTE}/component-attempt{attempt}/{name}", root / name)
    result_path = root / "COMPONENT_RESULT.json"
    state_path = root / "INVOCATION_STATE.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else {}
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    return result, state, root


def await_repair(kind: str, attempt: int, diagnostic: dict[str, Any]) -> None:
    repair_deadline = min(
        ABSOLUTE_DEADLINE - dt.timedelta(minutes=5),
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=25),
    )
    atomic_json(
        HERE / "REPAIR_READY.json",
        {
            "schema_version": 1,
            "status": "repair_ready",
            "kind": kind,
            "attempt": attempt,
            "diagnostic": diagnostic,
            "absolute_repair_deadline_utc": repair_deadline.isoformat().replace(
                "+00:00", "Z"
            ),
            "intervention_unchanged": True,
        },
    )
    emit("repair_ready", kind=kind, attempt=attempt)
    while dt.datetime.now(dt.timezone.utc) < repair_deadline:
        request = HERE / "REPAIR_REQUEST.json"
        if request.exists():
            value = json.loads(request.read_text())
            if not value.get("intervention_unchanged"):
                raise RuntimeError("repair_attempted_intervention_change")
            request.unlink()
            (HERE / "REPAIR_READY.json").unlink(missing_ok=True)
            return
        time.sleep(2)
    raise RuntimeError(f"{kind}_repair_deadline_expired")


def stage_endpoint(ip: str) -> None:
    required = (HERE / "remote_endpoint.sh", HERE / "runtime_patch.py")
    for source in required:
        if not source.exists():
            raise RuntimeError(f"endpoint_file_missing:{source.name}")
        scp_to(ip, source, f"{REMOTE}/input/")
    scp_to(ip, HERE / "inputs", f"{REMOTE}/endpoint-inputs", recursive=True)


def retrieve_endpoint(
    ip: str, worker: subprocess.CompletedProcess[str]
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    root = ARTIFACTS / "endpoint"
    root.mkdir(parents=True, exist_ok=True)
    (root / "worker.stdout").write_text(worker.stdout)
    (root / "worker.stderr").write_text(worker.stderr)
    archive = root / "endpoint-compact.tar.gz"
    sidecar = root / "endpoint-compact.tar.gz.sha256"
    for remote_name, local in (
        (f"{REMOTE}/endpoint/FINAL_TERMINAL.json", root / "FINAL_TERMINAL.json"),
        (f"{REMOTE}/endpoint/INVOCATION_STATE.json", root / "INVOCATION_STATE.json"),
        (f"{REMOTE}/endpoint-compact.tar.gz", archive),
        (f"{REMOTE}/endpoint-compact.tar.gz.sha256", sidecar),
    ):
        scp_from(ip, remote_name, local)
    if archive.exists():
        extracted = root / "retrieved"
        extracted.mkdir(exist_ok=True)
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(extracted, filter="data")
    terminal_path = root / "FINAL_TERMINAL.json"
    state_path = root / "INVOCATION_STATE.json"
    terminal = json.loads(terminal_path.read_text()) if terminal_path.exists() else {}
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    return terminal, state, root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", default="foreground")
    args = parser.parse_args()
    ARTIFACTS.mkdir(exist_ok=True)
    pool = GpuPool(LAB)
    bench = pool.claim(PROJECT, bench_id=BENCH, lease_seconds=3600)
    claimed_at = dt.datetime.fromisoformat(
        bench["claim"]["claimed_at"].replace("Z", "+00:00")
    )
    heartbeat = Heartbeat(pool)
    heartbeat.start()
    released = False
    component: dict[str, Any] = {}
    endpoint: dict[str, Any] = {}
    state: dict[str, Any] = {}
    update_status(
        active_session={
            "kind": "bounded_shared_bench_owner",
            "pid": os.getpid(),
            "unit": args.unit,
            "unit_manager": "foreground",
            "deadline_utc": ABSOLUTE_DEADLINE.isoformat().replace("+00:00", "Z"),
            "artifact_root": str(ARTIFACTS),
            "forward_progress": "claimed; project-local immutable inputs staged",
        }
    )
    try:
        ip = extract_public_ipv4(get_instance(INSTANCE))
        if not ip:
            raise RuntimeError("registered_guest_has_no_public_ip")
        for attempt in range(1, 9):
            stage_component(ip)
            pool.update(
                PROJECT,
                {
                    "project": PROJECT,
                    "candidate_invocation_started": False,
                    "candidate_cuda_started": False,
                    "runtime": f"component attempt {attempt} staged",
                },
            )
            update_status(
                actual_spend_usd=claimed_cost(claimed_at),
                active_session={
                    **json.loads((HERE / "STATUS.json").read_text())["active_session"],
                    "forward_progress": f"component attempt {attempt} running",
                },
            )
            worker = remote(ip, component_command(attempt), 3600)
            component, state, _ = retrieve_component(ip, attempt, worker)
            pool.update(
                PROJECT,
                {
                    "candidate_invocation_started": bool(
                        state.get("component_science_started")
                    ),
                    "candidate_cuda_started": bool(state.get("candidate_cuda_started")),
                    "runtime": (
                        f"component attempt {attempt}: "
                        f"{component.get('classification', 'integration_failure')}"
                    ),
                },
            )
            if component:
                break
            if state.get("component_science_started"):
                raise RuntimeError(
                    f"scientific_component_failed:rc={worker.returncode}:"
                    f"{worker.stderr[-1000:]}"
                )
            await_repair(
                "pre_science_component_integration",
                attempt,
                {
                    "returncode": worker.returncode,
                    "stderr_tail": worker.stderr[-4000:],
                    "stdout_tail": worker.stdout[-2000:],
                    "invocation_state": state,
                },
            )
        if component.get("classification") != "component_positive":
            classification = component.get("classification", "component_integration_failure")
            cost = claimed_cost(claimed_at)
            atomic_json(
                ARTIFACTS / "FINAL_TERMINAL.json",
                {
                    "schema_version": 1,
                    "status": "terminal",
                    "classification": classification,
                    "component": component,
                    "actual_spend_usd": cost,
                    "timestamp_utc": utc_now(),
                },
            )
            pool.release(
                PROJECT,
                contents={
                    "project": PROJECT,
                    "fused_greedy_top1_result": classification,
                    "fused_greedy_top1_actual_spend_usd": cost,
                    "artifacts": str(ARTIFACTS.relative_to(REPO)),
                    "checkpoint": "Exact immutable checkpoint retained unchanged",
                    "image": "Pinned SGLang v0.5.13 digest 6113665 retained",
                    "server_state": "No endpoint server",
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
            )
            return 0

        pool.update(
            PROJECT,
            {
                "runtime": "exact positive component persisted; endpoint consumer pending",
                "candidate_invocation_started": True,
                "candidate_cuda_started": True,
            },
        )
        update_status(
            actual_spend_usd=claimed_cost(claimed_at),
            active_session={
                **json.loads((HERE / "STATUS.json").read_text())["active_session"],
                "forward_progress": "component positive persisted; waiting endpoint consumer",
            },
        )
        await_repair("positive_component_endpoint_consumer", 1, component)
        stage_endpoint(ip)
        update_status(
            actual_spend_usd=claimed_cost(claimed_at),
            active_session={
                **json.loads((HERE / "STATUS.json").read_text())["active_session"],
                "forward_progress": "conditional endpoint running",
            },
        )
        worker = remote(
            ip,
            f"timeout --signal=TERM 6000 env FUSED_TOP1_ROOT={REMOTE} "
            f"bash {REMOTE}/input/remote_endpoint.sh",
            6100,
        )
        endpoint, state, _ = retrieve_endpoint(ip, worker)
        if not endpoint:
            if not state.get("endpoint_science_started"):
                await_repair(
                    "pre_science_endpoint_integration",
                    1,
                    {
                        "returncode": worker.returncode,
                        "stderr_tail": worker.stderr[-4000:],
                        "stdout_tail": worker.stdout[-2000:],
                        "invocation_state": state,
                    },
                )
                stage_endpoint(ip)
                worker = remote(
                    ip,
                    f"timeout --signal=TERM 6000 env FUSED_TOP1_ROOT={REMOTE} "
                    f"bash {REMOTE}/input/remote_endpoint.sh",
                    6100,
                )
                endpoint, state, _ = retrieve_endpoint(ip, worker)
            if not endpoint:
                raise RuntimeError(
                    f"endpoint_terminal_missing:rc={worker.returncode}:"
                    f"{worker.stderr[-1000:]}"
                )
        cost = claimed_cost(claimed_at)
        classification = endpoint.get("classification", "typed_endpoint_boundary")
        atomic_json(
            ARTIFACTS / "FINAL_TERMINAL.json",
            {
                "schema_version": 1,
                "status": "terminal",
                "classification": classification,
                "component": component,
                "endpoint": endpoint,
                "actual_spend_usd": cost,
                "timestamp_utc": utc_now(),
            },
        )
        pool.release(
            PROJECT,
            contents={
                "project": PROJECT,
                "fused_greedy_top1_result": classification,
                "fused_greedy_top1_actual_spend_usd": cost,
                "artifacts": str(ARTIFACTS.relative_to(REPO)),
                "checkpoint": "Exact immutable checkpoint retained unchanged",
                "image": "Pinned SGLang v0.5.13 digest 6113665 retained",
                "runtime": "Fused E4M3 greedy top-1 conditional endpoint terminal",
                "server_state": endpoint.get("server_state", "See endpoint terminal"),
            },
            condition=endpoint.get("release_condition", "maintenance"),
        )
        released = True
        update_status(
            status="completed",
            actual_spend_usd=cost,
            active_session=None,
            summary=classification,
            terminal_artifact=str(ARTIFACTS / "FINAL_TERMINAL.json"),
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
                "component": component,
                "endpoint": endpoint,
                "invocation_state": state,
                "actual_spend_usd": cost,
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
                    "fused_greedy_top1_result": "typed_external_or_integration_blocker",
                    "fused_greedy_top1_actual_spend_usd": cost,
                    "artifacts": str(ARTIFACTS.relative_to(REPO)),
                    "runtime": f"{type(error).__name__}:{error}",
                },
                condition="maintenance" if state.get("candidate_cuda_started") else "ready",
            )
        return 1
    finally:
        heartbeat.close()


if __name__ == "__main__":
    raise SystemExit(main())
