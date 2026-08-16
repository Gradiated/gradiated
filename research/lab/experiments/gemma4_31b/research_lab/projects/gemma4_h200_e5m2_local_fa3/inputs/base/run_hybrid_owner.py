#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shlex
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
sys.path[:0] = [
    str(REPO / "research/factory/src"),
    str(REPO / "research/lab/experiments/glm47flash/campaign_100/nebius"),
]

from grad_research.gpu_pool import GpuPool, GpuPoolError
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base


PROJECT = "gemma4_h200_e4m3_local_fa3_hybrid"
DEPENDENCY = "gemma4_h200_layerwise_mixed_kv_endpoint"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
REMOTE = "/home/glmrunner/gemma4-mixed-kv-local-fa3-hybrid"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
RATE_USD_PER_HOUR = 2.46
SPEND_CAP_USD = 12.0
WATCHDOG = dt.datetime(2026, 7, 23, 12, 30, tzinfo=dt.timezone.utc)
WAIT_DEADLINE = dt.datetime(2026, 7, 23, 12, 0, tzinfo=dt.timezone.utc)
RELEASE_RESERVE_SECONDS = 180
MINIMUM_RUN_SECONDS = 1500
UNIT = "gemma4-e4m3-local-fa3-hybrid-20260723.service"
ARTIFACTS = HERE / "artifacts" / "mixed-kv-local-fa3-hybrid-20260723"
DEPENDENCY_SNAPSHOT = HERE / "inputs" / "mixed_dependency"
CURRENT_FRONTIER = 0.6743258590313417
ECONOMIC_CEILING = 0.6381105231
LOCAL_WALL_FRACTION = 0.1531203203096733


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.is_file() else {}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def event(event_name: str, **fields: Any) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    row = {"timestamp_utc": utc_now(), "event": event_name, **fields}
    with (ARTIFACTS / "OWNER_EVENTS.jsonl").open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    atomic(ARTIFACTS / "OWNER_STATE.json", row)


def update_status(
    summary: str,
    next_action: str,
    spend: float,
    active_session: dict[str, Any] | None,
    status: str = "active",
) -> None:
    value = read_json(HERE / "STATUS.json")
    value.update(
        {
            "status": status,
            "summary": summary,
            "next_action": next_action,
            "actual_spend_usd": spend,
            "active_session": active_session,
        }
    )
    atomic(HERE / "STATUS.json", value)


def remote(
    ip: str, command: str, timeout: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*ssh_base(ip, KEY), command],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def copy_to(ip: str, source: Path, target: str, timeout: int = 300) -> None:
    result = subprocess.run(
        [
            "scp",
            *ssh_base(ip, KEY)[1:-1],
            str(source),
            f"{SSH_USER}@{ip}:{target}",
        ],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"scp_to_failed:{source.name}:{result.stderr[-1000:]}")


def copy_from(ip: str, source: str, target: Path, timeout: int = 300) -> None:
    result = subprocess.run(
        [
            "scp",
            *ssh_base(ip, KEY)[1:-1],
            f"{SSH_USER}@{ip}:{source}",
            str(target),
        ],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"scp_from_failed:{source}:{result.stderr[-1000:]}")


def dependency_terminal_path(project: Path) -> Path | None:
    candidates = sorted((project / "artifacts").glob("**/FINAL_TERMINAL.json"))
    return candidates[-1] if candidates else None


def dependency_state() -> tuple[bool, dict[str, Any], dict[str, Any]]:
    project = LAB / "projects" / DEPENDENCY
    status = read_json(project / "STATUS.json")
    terminal_path = dependency_terminal_path(project)
    terminal = read_json(terminal_path) if terminal_path else {}
    inventory = read_json(LAB / "runtime/gpus.json")
    benches = inventory.get("benches", {})
    if isinstance(benches, dict):
        benches = benches.values()
    bench = next(
        (
            row
            for row in benches
            if row.get("id") == BENCH
        ),
        {},
    )
    ready = bool(
        status.get("active_session") is None
        and terminal.get("status") == "terminal"
        and (
            (
                bench.get("status") == "available"
                and bench.get("claim") is None
            )
            or (
                bench.get("status") == "claimed"
                and (bench.get("claim") or {}).get("project") == PROJECT
            )
        )
    )
    return ready, terminal, bench


def materialize_dependency(terminal: dict[str, Any]) -> dict[str, Any]:
    dependency_project = LAB / "projects" / DEPENDENCY
    terminal_path = dependency_terminal_path(dependency_project)
    if terminal_path is None:
        raise RuntimeError("dependency_terminal_missing")
    sources = [
        (terminal_path, "FINAL_TERMINAL.json"),
        (dependency_project / "STATUS.json", "STATUS.json"),
        (
            dependency_project / "inputs/fp8_qkv_paired_runner.py",
            "fp8_qkv_paired_runner.py",
        ),
        (
            dependency_project / "inputs/base/install_endpoint_patch.py",
            "install_endpoint_patch.py",
        ),
        (
            dependency_project / "inputs/mixed_endpoint_entrypoint.py",
            "mixed_endpoint_entrypoint.py",
        ),
        (
            dependency_project / "inputs/mixed_kv_patch.py",
            "mixed_kv_patch.py",
        ),
        (
            dependency_project / "inputs/component_path_check.py",
            "dependency_component_path_check.py",
        ),
        (
            dependency_project / "inputs/base/qkv_epilogue_discriminator.py",
            "qkv_epilogue_discriminator.py",
        ),
        (
            dependency_project / "inputs/base/stack_sitecustomize.py",
            "dependency_stack_sitecustomize.py",
        ),
    ]
    DEPENDENCY_SNAPSHOT.mkdir(parents=True, exist_ok=True)
    rows = []
    for source, target_name in sources:
        if not source.is_file():
            raise RuntimeError(f"dependency_artifact_missing:{source}")
        target = DEPENDENCY_SNAPSHOT / target_name
        temporary = target.with_suffix(target.suffix + ".part")
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
        rows.append(
            {
                "name": target.name,
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
        )
    snapshot_terminal = read_json(DEPENDENCY_SNAPSHOT / "FINAL_TERMINAL.json")
    if snapshot_terminal != terminal:
        raise RuntimeError("dependency_changed_during_materialization")
    manifest = {
        "schema_version": 1,
        "dependency_project": DEPENDENCY,
        "files": rows,
        "materialized_at_utc": utc_now(),
    }
    atomic(DEPENDENCY_SNAPSHOT / "MANIFEST.json", manifest)
    return snapshot_terminal


def comparator_seconds(terminal: dict[str, Any]) -> float:
    value = terminal.get("candidate_service_seconds_per_request")
    if value is None:
        value = (
            terminal.get("endpoint", {}).get(
                "candidate_service_seconds_per_request"
            )
        )
    if value is None:
        raise RuntimeError("dependency_comparator_missing")
    value = float(value)
    if not (0.1 < value < 2.0):
        raise RuntimeError(f"dependency_comparator_out_of_range:{value}")
    return value


def admitted_files() -> list[Path]:
    names = [
        "e4m3_fa3_component.py",
        "gemma4_layer_hybrid_backend.py",
        "install_hybrid_backend.py",
        "sitecustomize.py",
        "remote_component.sh",
        "remote_hybrid_candidate.sh",
    ]
    result = [HERE / name for name in names]
    result.extend(
        DEPENDENCY_SNAPSHOT / name
        for name in (
            "fp8_qkv_paired_runner.py",
            "install_endpoint_patch.py",
            "mixed_endpoint_entrypoint.py",
            "mixed_kv_patch.py",
            "qkv_epilogue_discriminator.py",
            "dependency_stack_sitecustomize.py",
        )
    )
    result.extend(
        [
            DEPENDENCY_SNAPSHOT / "FINAL_TERMINAL.json",
            DEPENDENCY_SNAPSHOT / "MANIFEST.json",
            HERE / "MIXED_SOURCE_BINDING.json",
        ]
    )
    return result


def stage(ip: str, files: list[Path]) -> None:
    setup = remote(
        ip,
        f"mkdir -p {shlex.quote(REMOTE + '/input')} "
        f"{shlex.quote(REMOTE + '/component-artifacts')} "
        f"{shlex.quote(REMOTE + '/endpoint-artifacts')}",
        60,
    )
    if setup.returncode:
        raise RuntimeError(f"remote_prepare_failed:{setup.stderr[-1000:]}")
    for source in files:
        expected = sha256(source)
        final = f"{REMOTE}/input/{source.name}"
        probe = remote(
            ip,
            f"test -f {shlex.quote(final)} && "
            f"test \"$(stat -c %s {shlex.quote(final)})\" = {source.stat().st_size} && "
            f"test \"$(sha256sum {shlex.quote(final)} | awk '{{print $1}}')\" = {expected}",
            60,
        )
        if probe.returncode:
            partial = final + f".{expected}.part"
            copy_to(ip, source, partial)
            finalize = remote(
                ip,
                f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {expected} && "
                f"chmod 0444 {shlex.quote(partial)} && "
                f"mv -f {shlex.quote(partial)} {shlex.quote(final)}",
                60,
            )
            if finalize.returncode:
                raise RuntimeError(f"input_finalize_failed:{source.name}")
        event("input_bound", input_name=source.name, sha256=expected)


def retrieve_component(ip: str) -> dict[str, Any]:
    destination = ARTIFACTS / "component"
    destination.mkdir(parents=True, exist_ok=True)
    for name in (
        "REMOTE_TERMINAL.json",
        "INVOCATION_STATE.json",
        "component.stdout",
        "component.stderr",
        "COMPONENT_TERMINAL.json",
    ):
        copy_from(ip, f"{REMOTE}/component-artifacts/{name}", destination / name)
    return read_json(destination / "COMPONENT_TERMINAL.json")


def retrieve_endpoint(ip: str) -> dict[str, Any]:
    compact = ARTIFACTS / "endpoint-compact.tar.gz"
    compact_hash = ARTIFACTS / "endpoint-compact.tar.gz.sha256"
    copy_from(ip, f"{REMOTE}/compact.tar.gz", compact, 300)
    copy_from(ip, f"{REMOTE}/compact.tar.gz.sha256", compact_hash, 60)
    if sha256(compact) != compact_hash.read_text().split()[0]:
        raise RuntimeError("endpoint_compact_hash_mismatch")
    destination = ARTIFACTS / "endpoint"
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(compact, "r:gz") as archive:
        archive.extractall(destination, filter="data")
    terminal = read_json(destination / "ENDPOINT_RESULT.json")
    if not terminal:
        raise RuntimeError("endpoint_terminal_missing")
    return terminal


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
                event("heartbeat_failure", error=str(error))
                return

    def close(self) -> None:
        self.stop_event.set()
        self.join(5)


def wait_for_dependency() -> dict[str, Any]:
    event(
        "waiting_for_dependency",
        dependency=DEPENDENCY,
        wait_deadline_utc=WAIT_DEADLINE.isoformat().replace("+00:00", "Z"),
    )
    while dt.datetime.now(dt.timezone.utc) < WAIT_DEADLINE:
        ready, terminal, _ = dependency_state()
        if ready:
            return materialize_dependency(terminal)
        time.sleep(15)
    _, terminal, bench = dependency_state()
    boundary = {
        "schema_version": 1,
        "status": "terminal",
        "classification": "typed_external_dependency_watchdog_boundary",
        "dependency_terminal": terminal,
        "bench_status": bench.get("status"),
        "bench_claim": bench.get("claim"),
        "candidate_cuda_invocation_started": False,
        "scientific_invocation_started": False,
        "actual_spend_usd": 0.0,
        "timestamp_utc": utc_now(),
    }
    atomic(ARTIFACTS / "FINAL_TERMINAL.json", boundary)
    raise RuntimeError("typed_external_dependency_watchdog_boundary")


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    prior_project_spend = float(
        read_json(HERE / "STATUS.json").get("actual_spend_usd", 0.0)
    )
    subprocess.run(
        [sys.executable, str(HERE / "verify_director_binding.py")], check=True
    )
    spend_ledger = read_json(LAB / "runtime/spend_cap.json")
    reservation = spend_ledger.get("reservations", {}).get(PROJECT, {})
    if float(reservation.get("authorized_usd", 0)) != SPEND_CAP_USD:
        raise RuntimeError("reservation_not_durable")
    session = {
        "pid": os.getpid(),
        "deadline_utc": (
            WATCHDOG - dt.timedelta(seconds=RELEASE_RESERVE_SECONDS)
        ).isoformat().replace("+00:00", "Z"),
        "artifact_root": str(ARTIFACTS),
        "expected_terminal": "component_negative|insufficient_bound|hybrid_endpoint|typed_external_boundary",
        "unit": UNIT,
        "unit_manager": "user",
        "forward_progress": "waiting_for_mixed_kv_triton_dependency",
    }
    update_status(
        "The mixed-format v0.5.13 local-FA3/global-Triton package is ready; its durable owner is waiting behind the claimed mixed-KV Triton dependency.",
        "The owner will materialize the dependency terminal before claim, run the exact component once, and invoke c32 only if the conservative bound survives.",
        prior_project_spend,
        session,
    )
    try:
        dependency_terminal = wait_for_dependency()
    except RuntimeError as error:
        if str(error) == "typed_external_dependency_watchdog_boundary":
            update_status(
                "Offline binding is complete, but the mixed-KV Triton dependency did not release with a terminal before the retained bench watchdog boundary.",
                "Director must provide a compatible retained H200 and the persisted mixed-KV terminal; do not replay the dependency.",
                0.0,
                None,
            )
            return 3
        raise
    subprocess.run(
        [sys.executable, str(HERE / "build_mixed_offline_binding.py")],
        check=True,
    )
    if dependency_terminal.get("pass") is not True:
        terminal = {
            "schema_version": 1,
            "status": "terminal",
            "classification": "dependency_mixed_kv_invalid_no_claim",
            "dependency_terminal": dependency_terminal,
            "candidate_cuda_invocation_started": False,
            "scientific_invocation_started": False,
            "actual_spend_usd": 0.0,
            "timestamp_utc": utc_now(),
        }
        atomic(ARTIFACTS / "FINAL_TERMINAL.json", terminal)
        update_status(
            "The persisted mixed-KV dependency closed without a valid comparator; no H200 claim or hybrid invocation was made.",
            "Close this exact hybrid dependency branch without replay or backend substitution.",
            0.0,
            None,
            status="complete",
        )
        return 0
    comparator = comparator_seconds(dependency_terminal)
    perfect_removal_bound = comparator - CURRENT_FRONTIER * LOCAL_WALL_FRACTION
    if perfect_removal_bound >= CURRENT_FRONTIER:
        terminal = {
            "schema_version": 1,
            "status": "terminal",
            "classification": "dependency_perfect_local_removal_bound_negative",
            "dependency_comparator_seconds_per_request": comparator,
            "perfect_local_removal_bound_seconds_per_request": perfect_removal_bound,
            "current_frontier_seconds_per_request": CURRENT_FRONTIER,
            "candidate_cuda_invocation_started": False,
            "scientific_invocation_started": False,
            "actual_spend_usd": 0.0,
            "timestamp_utc": utc_now(),
        }
        atomic(ARTIFACTS / "FINAL_TERMINAL.json", terminal)
        update_status(
            "The persisted mixed-KV comparator failed even the perfect-removal local-attention bound; no H200 claim was made.",
            "Close this hybrid candidate without replay or backend sweep.",
            0.0,
            None,
            status="complete",
        )
        return 0
    remaining = int((WATCHDOG - dt.datetime.now(dt.timezone.utc)).total_seconds())
    if remaining < MINIMUM_RUN_SECONDS:
        raise RuntimeError("typed_watchdog_boundary_insufficient_time_after_dependency")
    files = admitted_files()
    input_manifest = {
        "schema_version": 1,
        "files": [
            {
                "name": path.name,
                "path": str(path.relative_to(HERE)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in files
        ],
    }
    atomic(HERE / "GPU_INPUT_MANIFEST.json", input_manifest)
    pool = GpuPool(LAB)
    prior_spend = prior_project_spend
    claim_started_utc = dt.datetime.now(dt.timezone.utc)
    claimed = False
    heartbeat: Heartbeat | None = None
    ip: str | None = None
    terminal: dict[str, Any] = {}
    return_code = 0
    try:
        bench = pool.claim(
            PROJECT,
            bench_id=BENCH,
            lease_seconds=max(600, remaining - RELEASE_RESERVE_SECONDS),
        )
        claimed = True
        claim_started_utc = dt.datetime.fromisoformat(
            bench["claim"]["claimed_at"].replace("Z", "+00:00")
        )
        event("bench_claimed", claim=bench["claim"])
        heartbeat = Heartbeat(pool)
        heartbeat.start()
        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip:
            raise RuntimeError("typed_provider_boundary_no_public_ip")
        identity = remote(
            ip,
            "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version",
            60,
        )
        (ARTIFACTS / "remote-identity.stdout").write_text(identity.stdout)
        (ARTIFACTS / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_provider_boundary_ssh_identity_failed")
        stage(ip, files)
        component_worker = remote(
            ip,
            f"HYBRID_REMOTE_ROOT={shlex.quote(REMOTE)} "
            f"DEPENDENCY_COMPARATOR_SECONDS={comparator!r} "
            f"timeout --signal=TERM 900 bash {shlex.quote(REMOTE + '/input/remote_component.sh')}",
            930,
        )
        (ARTIFACTS / "component.worker.stdout").write_text(component_worker.stdout)
        (ARTIFACTS / "component.worker.stderr").write_text(component_worker.stderr)
        component = retrieve_component(ip)
        invocation = read_json(ARTIFACTS / "component/INVOCATION_STATE.json")
        if not component:
            if not invocation.get("scientific_invocation_started"):
                repair = {
                    "schema_version": 1,
                    "classification": "preinvocation_component_integration_failure",
                    "worker_exit_code": component_worker.returncode,
                    "invocation": invocation,
                    "repair_deadline_utc": (
                        dt.datetime.now(dt.timezone.utc)
                        + dt.timedelta(minutes=10)
                    ).isoformat().replace("+00:00", "Z"),
                }
                atomic(ARTIFACTS / "REPAIR_READY.json", repair)
            raise RuntimeError("component_terminal_missing")
        reduction = float(component.get("conservative_reduction_fraction", -1))
        projected = comparator - CURRENT_FRONTIER * LOCAL_WALL_FRACTION * reduction
        endpoint_admitted = bool(
            component.get("component_pass")
            and component.get("conditional_endpoint_admitted")
            and projected < CURRENT_FRONTIER
        )
        atomic(
            ARTIFACTS / "COMPONENT_DECISION.json",
            {
                "schema_version": 1,
                "dependency_comparator_seconds_per_request": comparator,
                "component_conservative_reduction_fraction": reduction,
                "projected_hybrid_seconds_per_request": projected,
                "current_frontier_seconds_per_request": CURRENT_FRONTIER,
                "economic_ceiling_seconds_per_request": ECONOMIC_CEILING,
                "conditional_endpoint_admitted": endpoint_admitted,
            },
        )
        if not endpoint_admitted:
            terminal = {
                "schema_version": 1,
                "status": "terminal",
                "classification": (
                    component.get("status") or "component_insufficient_bound"
                ),
                "dependency_comparator_seconds_per_request": comparator,
                "component": component,
                "projected_hybrid_seconds_per_request": projected,
                "candidate_cuda_invocation_started": invocation.get(
                    "candidate_cuda_invocation_started"
                ),
                "scientific_invocation_started": invocation.get(
                    "scientific_invocation_started"
                ),
            }
        else:
            seconds_left = int(
                (WATCHDOG - dt.datetime.now(dt.timezone.utc)).total_seconds()
            )
            if seconds_left < 900:
                raise RuntimeError("component_pass_endpoint_watchdog_boundary")
            endpoint_worker = remote(
                ip,
                f"HYBRID_REMOTE_ROOT={shlex.quote(REMOTE)} "
                f"timeout --signal=TERM {seconds_left - RELEASE_RESERVE_SECONDS} "
                f"bash {shlex.quote(REMOTE + '/input/remote_hybrid_candidate.sh')}",
                seconds_left - 120,
            )
            (ARTIFACTS / "endpoint.worker.stdout").write_text(endpoint_worker.stdout)
            (ARTIFACTS / "endpoint.worker.stderr").write_text(endpoint_worker.stderr)
            endpoint = retrieve_endpoint(ip)
            candidate = float(endpoint["candidate_service_seconds_per_request"])
            endpoint.update(
                {
                    "dependency_comparator_seconds_per_request": comparator,
                    "relative_to_dependency_fraction": 1 - candidate / comparator,
                    "relative_to_e5m2_frontier_fraction": 1
                    - candidate / CURRENT_FRONTIER,
                    "economic_ceiling_seconds_per_request": ECONOMIC_CEILING,
                    "ceiling_pass": candidate <= ECONOMIC_CEILING,
                }
            )
            classification = (
                "hybrid_endpoint_positive"
                if endpoint.get("pass") and candidate < comparator
                else "hybrid_endpoint_negative"
            )
            terminal = {
                "schema_version": 1,
                "status": "terminal",
                "classification": classification,
                "dependency_comparator_seconds_per_request": comparator,
                "component": component,
                "endpoint": endpoint,
                "candidate_cuda_invocation_started": True,
                "scientific_invocation_started": True,
            }
    except Exception as error:
        terminal = {
            "schema_version": 1,
            "status": "terminal",
            "classification": "typed_external_or_integration_boundary",
            "error": {"type": type(error).__name__, "message": str(error)},
            "candidate_cuda_invocation_started": None,
            "scientific_invocation_started": None,
        }
        return_code = 2
    finally:
        if heartbeat:
            heartbeat.close()
        spend = (
            prior_spend
            + (
                dt.datetime.now(dt.timezone.utc) - claim_started_utc
            ).total_seconds()
            * RATE_USD_PER_HOUR
            / 3600
            if claimed
            else prior_spend
        )
        if spend > SPEND_CAP_USD:
            terminal["spend_violation"] = True
            return_code = 2
        terminal["actual_spend_usd"] = spend
        terminal["timestamp_utc"] = utc_now()
        atomic(ARTIFACTS / "FINAL_TERMINAL.json", terminal)
        classification = terminal.get("classification", "owner_failure")
        if classification == "hybrid_endpoint_positive":
            endpoint = terminal.get("endpoint", {})
            update_status(
                f"The sole exact c32 hybrid measured {endpoint.get('candidate_service_seconds_per_request')} s/request against the persisted mixed-KV Triton comparator {comparator} s/request.",
                "Retain only as a representation-changing performance survivor pending separate quality and feature validation; do not sweep backends.",
                spend,
                None,
                status="complete",
            )
        elif classification in {
            "hybrid_endpoint_negative",
            "component_insufficient_bound",
            "component_numerical_or_performance_negative",
        }:
            update_status(
                f"The sole hybrid arm closed at {classification}; inspect the project-local component/endpoint terminal.",
                "Close this exact hybrid without replay, FA3 tuning, or backend sweep.",
                spend,
                None,
                status="complete",
            )
        else:
            update_status(
                f"The durable hybrid owner reached {classification}; compact diagnostics and invocation markers are project-local.",
                "Repair only an ordinary unconsumed operation under the retained owner when REPAIR_READY exists; otherwise director disposition from FINAL_TERMINAL.json.",
                spend,
                None,
            )
        if claimed:
            contents = {
                "project": PROJECT,
                "mixed_kv_local_fa3_hybrid_result": classification,
                "mixed_kv_local_fa3_hybrid_actual_spend_usd": spend,
                "artifacts": str(ARTIFACTS),
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "image": "Pinned SGLang v0.5.13 digest 6113665a retained.",
                "checkpoint": "Exact lab-owned resident checkpoint retained read-only; no project copy staged.",
                "caches": "Mixed E4M3-local/E5M2-global Triton/FA3/CUDA graph caches retained.",
                "server_state": "Healthy mixed-KV local-FA3/global-Triton candidate retained if endpoint startup completed.",
            }
            atomic(ARTIFACTS / "BENCH_CONTENTS.json", contents)
            try:
                pool.release(PROJECT, condition="ready", contents=contents)
                event("bench_released", condition="ready")
            except GpuPoolError as error:
                event("bench_release_failure", error=str(error))
                return_code = 2
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
