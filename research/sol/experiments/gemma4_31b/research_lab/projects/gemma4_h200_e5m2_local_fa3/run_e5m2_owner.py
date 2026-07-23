#!/usr/bin/env python3
from __future__ import annotations

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
sys.path[:0] = [
    str(REPO / "research/factory/src"),
    str(REPO / "research/sol/experiments/glm47flash/campaign_100/nebius"),
]

from grad_research.gpu_pool import GpuPool, GpuPoolError
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base


PROJECT = "gemma4_h200_e5m2_local_fa3"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
REMOTE = "/home/glmrunner/gemma4-e5m2-local-fa3"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
RATE_USD_PER_HOUR = 2.46
SPEND_CAP_USD = 14.0
CONTROL = 0.6743258590313417
WATCHDOG = dt.datetime(2026, 7, 23, 16, 30, tzinfo=dt.timezone.utc)
CLAIM_LIMIT = dt.timedelta(minutes=100)
RELEASE_RESERVE = dt.timedelta(minutes=3)
UNIT = "gemma4-e5m2-local-fa3-20260723.service"
ARTIFACTS = HERE / "artifacts" / "e5m2-local-fa3-20260723"


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
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def event(name: str, **fields: Any) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    row = {"timestamp_utc": utc_now(), "event": name, **fields}
    with (ARTIFACTS / "OWNER_EVENTS.jsonl").open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    atomic(ARTIFACTS / "OWNER_STATE.json", row)


def status(
    summary: str,
    next_action: str,
    spend: float,
    active_session: dict[str, Any] | None,
    state: str = "active",
) -> None:
    value = read_json(HERE / "STATUS.json")
    value.update(
        {
            "status": state,
            "summary": summary,
            "next_action": next_action,
            "actual_spend_usd": spend,
            "active_session": active_session,
        }
    )
    atomic(HERE / "STATUS.json", value)


def remote(ip: str, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
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


def copy_from(ip: str, source: str, target: Path, timeout: int = 300) -> bool:
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
    return result.returncode == 0


def admitted_files() -> list[Path]:
    manifest = read_json(HERE / "GPU_INPUT_MANIFEST.json")
    return [HERE / row["path"] for row in manifest["files"]]


def stage(ip: str, files: list[Path]) -> None:
    result = remote(
        ip,
        f"mkdir -p {shlex.quote(REMOTE + '/input')} "
        f"{shlex.quote(REMOTE + '/component-artifacts')} "
        f"{shlex.quote(REMOTE + '/endpoint-artifacts')}",
        60,
    )
    if result.returncode:
        raise RuntimeError(f"remote_prepare_failed:{result.stderr[-1000:]}")
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
            finish = remote(
                ip,
                f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {expected} && "
                f"chmod 0444 {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {shlex.quote(final)}",
                60,
            )
            if finish.returncode:
                raise RuntimeError(f"input_finalize_failed:{source.name}")
        event("input_bound", input_name=source.name, sha256=expected)


def retrieve_component(ip: str) -> tuple[dict[str, Any], dict[str, Any]]:
    destination = ARTIFACTS / "component"
    destination.mkdir(parents=True, exist_ok=True)
    for name in (
        "REMOTE_TERMINAL.json",
        "INVOCATION_STATE.json",
        "component.stdout",
        "component.stderr",
        "COMPONENT_TERMINAL.json",
        "router-audit.jsonl",
    ):
        copy_from(ip, f"{REMOTE}/component-artifacts/{name}", destination / name)
    return (
        read_json(destination / "COMPONENT_TERMINAL.json"),
        read_json(destination / "INVOCATION_STATE.json"),
    )


def retrieve_endpoint(ip: str) -> dict[str, Any]:
    compact = ARTIFACTS / "endpoint-compact.tar.gz"
    compact_hash = ARTIFACTS / "endpoint-compact.tar.gz.sha256"
    if not copy_from(ip, f"{REMOTE}/compact.tar.gz", compact):
        raise RuntimeError("endpoint_compact_retrieval_failed")
    if not copy_from(ip, f"{REMOTE}/compact.tar.gz.sha256", compact_hash):
        raise RuntimeError("endpoint_compact_hash_retrieval_failed")
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


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(HERE / "verify_director_binding.py")], check=True)
    subprocess.run([sys.executable, str(HERE / "build_source_binding.py")], check=True)
    reservation = read_json(LAB / "runtime/spend_cap.json").get("reservations", {}).get(PROJECT, {})
    if float(reservation.get("authorized_usd", 0)) != SPEND_CAP_USD:
        raise RuntimeError("reservation_not_durable")
    now = dt.datetime.now(dt.timezone.utc)
    deadline = min(WATCHDOG - RELEASE_RESERVE, now + CLAIM_LIMIT)
    session = {
        "pid": os.getpid(),
        "deadline_utc": deadline.isoformat().replace("+00:00", "Z"),
        "artifact_root": str(ARTIFACTS),
        "expected_terminal": "component_terminal|conditional_c32_terminal|typed_boundary",
        "unit": UNIT,
        "unit_manager": "user",
        "forward_progress": "claiming_bound_h200",
    }
    status(
        "The immutable direct-E5M2 FA3 producer/consumer program is frozen and the durable reservation is validated.",
        "The bounded owner is claiming the named H200, then running the sole component and only conditionally c32.",
        0.0,
        session,
    )
    pool = GpuPool(LAB)
    claim_started = now
    claimed = False
    heartbeat: Heartbeat | None = None
    terminal: dict[str, Any] = {}
    result_code = 0
    ip: str | None = None
    release_condition = "ready"
    try:
        bench = pool.claim(
            PROJECT,
            bench_id=BENCH,
            lease_seconds=max(600, int((deadline - now).total_seconds())),
        )
        claimed = True
        claim_started = dt.datetime.fromisoformat(
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
            "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker ps --format '{{.Names}}'; sudo docker --version",
            60,
        )
        (ARTIFACTS / "remote-identity.stdout").write_text(identity.stdout)
        (ARTIFACTS / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("typed_provider_boundary_ssh_identity_failed")
        stage(ip, admitted_files())
        component_worker = remote(
            ip,
            f"E5M2_REMOTE_ROOT={shlex.quote(REMOTE)} CONTROL_SECONDS={CONTROL!r} "
            f"timeout --signal=TERM 900 bash {shlex.quote(REMOTE + '/input/remote_component.sh')}",
            930,
        )
        (ARTIFACTS / "component.worker.stdout").write_text(component_worker.stdout)
        (ARTIFACTS / "component.worker.stderr").write_text(component_worker.stderr)
        component, invocation = retrieve_component(ip)
        if not component:
            repair_deadline = min(deadline, dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10))
            diagnostic = {
                "schema_version": 1,
                "classification": "component_integration_failure",
                "worker_exit_code": component_worker.returncode,
                "invocation": invocation,
                "repair_deadline_utc": repair_deadline.isoformat().replace("+00:00", "Z"),
            }
            atomic(ARTIFACTS / "REPAIR_READY.json", diagnostic)
            if not invocation.get("scientific_invocation_started"):
                session["forward_progress"] = "repair_ready_pre_science"
                status(
                    "The component stopped before its scientific invocation; the claim remains warm and heartbeating with diagnostics retrieved.",
                    "Patch only the invalidated integration operation and write REPAIR_REQUEST.json before the recorded repair deadline.",
                    (dt.datetime.now(dt.timezone.utc) - claim_started).total_seconds() * RATE_USD_PER_HOUR / 3600,
                    session,
                )
                while dt.datetime.now(dt.timezone.utc) < repair_deadline:
                    if (ARTIFACTS / "REPAIR_REQUEST.json").is_file():
                        raise RuntimeError("repair_request_requires_owner_restart_not_supported")
                    time.sleep(5)
                raise RuntimeError("typed_repair_deadline_elapsed")
            raise RuntimeError("component_failed_after_scientific_invocation")
        reduction = float(component.get("estimated_whole_request_reduction_fraction", -1))
        endpoint_admitted = bool(
            component.get("component_pass")
            and component.get("conditional_endpoint_admitted")
            and reduction >= 0.03
        )
        atomic(
            ARTIFACTS / "COMPONENT_DECISION.json",
            {
                "schema_version": 1,
                "component_status": component.get("status"),
                "conservative_whole_request_reduction_fraction": reduction,
                "minimum_fraction": 0.03,
                "conditional_endpoint_admitted": endpoint_admitted,
            },
        )
        if not endpoint_admitted:
            terminal = {
                "schema_version": 1,
                "status": "terminal",
                "classification": component.get("status", "component_reject"),
                "component": component,
                "candidate_cuda_invocation_started": invocation.get("candidate_cuda_invocation_started"),
                "scientific_invocation_started": invocation.get("scientific_invocation_started"),
            }
        else:
            seconds_left = int((deadline - dt.datetime.now(dt.timezone.utc)).total_seconds())
            if seconds_left < 900:
                raise RuntimeError("component_pass_endpoint_deadline_boundary")
            endpoint_worker = remote(
                ip,
                f"E5M2_REMOTE_ROOT={shlex.quote(REMOTE)} timeout --signal=TERM {seconds_left - 120} "
                f"bash {shlex.quote(REMOTE + '/input/remote_e5m2_candidate.sh')}",
                seconds_left - 60,
            )
            (ARTIFACTS / "endpoint.worker.stdout").write_text(endpoint_worker.stdout)
            (ARTIFACTS / "endpoint.worker.stderr").write_text(endpoint_worker.stderr)
            endpoint = retrieve_endpoint(ip)
            candidate = float(endpoint["candidate_service_seconds_per_request"])
            endpoint["control_service_seconds_per_request"] = CONTROL
            endpoint["improvement_fraction"] = 1 - candidate / CONTROL
            classification = (
                "endpoint_positive"
                if endpoint.get("pass") and candidate < CONTROL
                else "endpoint_negative"
            )
            terminal = {
                "schema_version": 1,
                "status": "terminal",
                "classification": classification,
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
        result_code = 2
        if "provider_boundary" in str(error):
            release_condition = "maintenance"
    finally:
        if heartbeat:
            heartbeat.close()
        spend = (
            (dt.datetime.now(dt.timezone.utc) - claim_started).total_seconds()
            * RATE_USD_PER_HOUR
            / 3600
            if claimed
            else 0.0
        )
        terminal["actual_spend_usd"] = spend
        terminal["timestamp_utc"] = utc_now()
        atomic(ARTIFACTS / "FINAL_TERMINAL.json", terminal)
        classification = terminal.get("classification", "owner_failure")
        scientific_terminal = classification in {
            "component_bound_pass",
            "component_insufficient_bound",
            "component_numerical_or_performance_negative",
            "endpoint_positive",
            "endpoint_negative",
        }
        status(
            f"The direct-E5M2 local-FA3 owner reached {classification}; compact evidence and invocation markers are project-local.",
            "Close without replay or tuning." if scientific_terminal else "Director disposition from the typed terminal; do not infer arm consumption without the retrieved markers.",
            spend,
            None,
            state="complete" if scientific_terminal else "active",
        )
        if claimed:
            contents = {
                "project": PROJECT,
                "e5m2_local_fa3_result": classification,
                "e5m2_local_fa3_actual_spend_usd": spend,
                "artifacts": str(ARTIFACTS),
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "image": "Pinned SGLang v0.5.13 digest 6113665 retained",
                "checkpoint": "Exact immutable checkpoint retained at /home/glmrunner/gemma4-width16384/checkpoint",
                "caches": "E5M2, QKV, FA3 v3, Triton, and CUDA graph caches retained",
                "server_state": "Direct E5M2 local-FA3 candidate retained if endpoint startup completed",
            }
            atomic(ARTIFACTS / "BENCH_CONTENTS.json", contents)
            try:
                pool.release(PROJECT, condition=release_condition, contents=contents)
                event("bench_released", condition=release_condition)
            except GpuPoolError as error:
                event("bench_release_failure", error=str(error))
                result_code = 2
    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
