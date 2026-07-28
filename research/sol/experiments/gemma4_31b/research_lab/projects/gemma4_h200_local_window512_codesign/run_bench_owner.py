#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
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

from grad_research.gpu_pool import GpuPool, GpuPoolError  # noqa: E402
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base  # noqa: E402


PROJECT = "gemma4_h200_local_window512_codesign"
DEPENDENCY = "gemma4_h200_ngram_speculative_endpoint"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
REMOTE = "/home/glmrunner/gemma4-local-window512-codesign"
RATE_USD_PER_HOUR = 2.46
WATCHDOG_DEADLINE = dt.datetime(2026, 7, 23, 12, 30, 0, tzinfo=dt.timezone.utc)
MINIMUM_CLAIM_SECONDS = 1500
RELEASE_RESERVE_SECONDS = 240
WAIT_DEADLINE = WATCHDOG_DEADLINE - dt.timedelta(
    seconds=MINIMUM_CLAIM_SECONDS
)
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
ARTIFACTS = HERE / "artifacts" / "window512-20260723"
INPUT_NAMES = (
    "window_component.py",
    "window512_patch.py",
    "sitecustomize.py",
    "remote_component.sh",
    "remote_endpoint_pair.sh",
)
STACK_NAMES = (
    "attention_deferred_local_kv.py",
    "fp8_qkv_paired_runner.py",
    "host_min_new_tokens_gate.py",
    "install_endpoint_patch.py",
    "pinned_async_penalty_tokens.py",
    "producer_fused_swa_translation.py",
    "proven_v0513_endpoint_entrypoint.py",
    "qkv_epilogue_discriminator.py",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def append_event(event: str, **fields: Any) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    row = {"timestamp_utc": utc_now(), "event": event, **fields}
    with (ARTIFACTS / "OWNER_EVENTS.jsonl").open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    atomic_json(ARTIFACTS / "OWNER_STATE.json", row)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.is_file() else {}


def admitted_inputs() -> list[dict[str, Any]]:
    paths = [HERE / name for name in INPUT_NAMES]
    paths.extend(HERE / "inputs" / "stack" / name for name in STACK_NAMES)
    rows = []
    for path in paths:
        rows.append(
            {
                "path": str(path.relative_to(HERE)),
                "name": path.name,
                "remote": f"input/{path.name}",
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return rows


def bound_checkpoint_rows() -> list[tuple[str, str]]:
    rows = []
    for line in (HERE / "CHECKPOINT_SHA256SUMS.txt").read_text().splitlines():
        digest, path = line.split(maxsplit=1)
        rows.append((digest, Path(path).name))
    return rows


def validate_shared_checkpoint(ip: str) -> None:
    resident = "/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint"
    checks = " ".join(
        f"{shlex.quote(digest)}:{shlex.quote(name)}"
        for digest, name in bound_checkpoint_rows()
    )
    command = (
        "set -e; resident=" + shlex.quote(resident) + "; "
        "test -d \"$resident\"; "
        "for item in " + checks + "; do hash=${item%%:*}; name=${item#*:}; "
        "test -f \"$resident/$name\"; "
        "printf '%s  %s\\n' \"$hash\" \"$resident/$name\" | sha256sum -c -; "
        "done; "
        "test \"$(find \"$resident\" -maxdepth 1 -type f | wc -l)\" -ge 8"
    )
    result = remote(ip, command, 900)
    (ARTIFACTS / "shared-checkpoint-validation.stdout").write_text(result.stdout)
    (ARTIFACTS / "shared-checkpoint-validation.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("shared_checkpoint_full_manifest_failed")
    append_event(
        "shared_checkpoint_validated",
        resident=resident,
        manifest=str(HERE / "CHECKPOINT_SHA256SUMS.txt"),
        manifest_sha256=sha256(HERE / "CHECKPOINT_SHA256SUMS.txt"),
        files=len(bound_checkpoint_rows()),
    )


def dependency_released() -> bool:
    status = read_json(LAB / "projects" / DEPENDENCY / "STATUS.json")
    inventory = read_json(LAB / "runtime" / "gpus.json")
    bench = inventory.get("benches", {}).get(BENCH, {})
    spend = read_json(LAB / "runtime" / "spend_cap.json")
    settled = any(
        key.startswith(DEPENDENCY + ":")
        for key in spend.get("settlements", {})
    )
    return (
        (status.get("status") != "active" or settled)
        and status.get("active_session") is None
        and (
            bench.get("status") == "available"
            or (
                bench.get("status") == "claimed"
                and bench.get("claim", {}).get("project") == PROJECT
            )
        )
        and (
            bench.get("claim") is None
            or bench.get("claim", {}).get("project") == PROJECT
        )
    )


def settle_status(
    status: str,
    summary: str,
    next_action: str,
    actual_spend_usd: float,
    active_session: dict[str, Any] | None = None,
) -> None:
    value = read_json(HERE / "STATUS.json")
    value.update(
        {
            "status": status,
            "summary": summary,
            "next_action": next_action,
            "actual_spend_usd": actual_spend_usd,
            "active_session": active_session,
        }
    )
    atomic_json(HERE / "STATUS.json", value)


def remote(
    ip: str, command: str, timeout: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*ssh_base(ip, KEY), command],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def scp_to(ip: str, source: Path, destination: str, timeout: int = 300) -> None:
    result = subprocess.run(
        [
            "scp",
            *ssh_base(ip, KEY)[1:-1],
            str(source),
            f"{SSH_USER}@{ip}:{destination}",
        ],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"scp_to_failed:{source.name}:{result.stderr[-1000:]}")


def scp_from(ip: str, source: str, destination: Path, timeout: int = 300) -> bool:
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
    return result.returncode == 0


def stage(ip: str, rows: list[dict[str, Any]]) -> None:
    result = remote(
        ip,
        f"mkdir -p {shlex.quote(REMOTE + '/input')} "
        f"{shlex.quote(REMOTE + '/checkpoint')} "
        f"{shlex.quote(REMOTE + '/component-artifacts')} "
        f"{shlex.quote(REMOTE + '/endpoint-artifacts')}",
        60,
    )
    if result.returncode:
        raise RuntimeError(f"remote_root_failed:{result.stderr[-1000:]}")
    for row in rows:
        target = f"{REMOTE}/{row['remote']}"
        probe = remote(
            ip,
            f"test -f {shlex.quote(target)} && "
            f"test $(stat -c %s {shlex.quote(target)}) -eq {row['bytes']} && "
            f"test $(sha256sum {shlex.quote(target)} | cut -d' ' -f1) = {row['sha256']}",
            60,
        )
        if probe.returncode == 0:
            append_event("input_matched", name=row["name"], sha256=row["sha256"])
            continue
        source = HERE / row["path"]
        part = target + f".part.{os.getpid()}"
        scp_to(
            ip,
            source,
            part,
            timeout=max(300, int(row["bytes"] / 20_000_000) + 300),
        )
        finish = remote(
            ip,
            f"test $(stat -c %s {shlex.quote(part)}) -eq {row['bytes']} && "
            f"test $(sha256sum {shlex.quote(part)} | cut -d' ' -f1) = {row['sha256']} && "
            f"chmod 0444 {shlex.quote(part)} && mv -f {shlex.quote(part)} {shlex.quote(target)}",
            60,
        )
        if finish.returncode:
            raise RuntimeError(f"remote_finalize_failed:{row['name']}")
        append_event("input_finalized", name=row["name"], sha256=row["sha256"])


def retrieve_files(ip: str, phase: str, names: tuple[str, ...]) -> Path:
    destination = ARTIFACTS / phase
    destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        source = f"{REMOTE}/{phase}-artifacts/{name}"
        ok = scp_from(ip, source, destination / name)
        append_event("retrieval", phase=phase, name=name, success=ok)
    return destination


class Heartbeat(threading.Thread):
    def __init__(self, pool: GpuPool):
        super().__init__(daemon=True)
        self.pool = pool
        self.stop_event = threading.Event()
        self.error: str | None = None

    def run(self) -> None:
        while not self.stop_event.wait(40):
            try:
                self.pool.heartbeat(PROJECT)
            except Exception as error:
                self.error = str(error)
                append_event("heartbeat_failure", error=self.error)
                return

    def close(self) -> None:
        self.stop_event.set()
        self.join(5)


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    rows = admitted_inputs()
    atomic_json(HERE / "GPU_INPUT_MANIFEST.json", {"schema_version": 1, "files": rows})
    physical = read_json(HERE / "PHYSICAL_BOUND.json")
    if not (
        physical.get("five_percent_gate_pass")
        or physical.get("economic_ceiling_bound_pass")
    ):
        settle_status(
            "complete",
            "The exact 512-window analytical physical bound failed the preregistered endpoint gate.",
            "Close this exact local-window proxy without claiming the H200.",
            0.0,
        )
        return 0
    append_event(
        "waiting_for_dependency",
        dependency=DEPENDENCY,
        wait_deadline_utc=WAIT_DEADLINE.isoformat().replace("+00:00", "Z"),
    )
    while dt.datetime.now(dt.timezone.utc) < WAIT_DEADLINE:
        if dependency_released():
            break
        time.sleep(15)
    if not dependency_released():
        terminal = {
            "schema_version": 1,
            "status": "terminal",
            "classification": "typed_external_dependency_watchdog_boundary",
            "dependency": DEPENDENCY,
            "bench": BENCH,
            "watchdog_deadline_utc": WATCHDOG_DEADLINE.isoformat().replace(
                "+00:00", "Z"
            ),
            "minimum_required_seconds": MINIMUM_CLAIM_SECONDS,
            "candidate_cuda_invocation_started": False,
            "scientific_invocation_started": False,
            "actual_spend_usd": 0.0,
            "timestamp_utc": utc_now(),
        }
        atomic_json(ARTIFACTS / "FINAL_TERMINAL.json", terminal)
        settle_status(
            "active",
            "Offline binding and the 6.56% physical bound are complete; the higher-priority n-gram lane retained the sole H200 until too near its watchdog for a safe exact pair.",
            "Director must supply a compatible retained H200 with at least 25 minutes of lifecycle after gemma4_h200_ngram_speculative_endpoint releases; then run the already materialized exact component/path check and conditional c32 pair once.",
            0.0,
        )
        return 3
    now = dt.datetime.now(dt.timezone.utc)
    remaining = int((WATCHDOG_DEADLINE - now).total_seconds())
    if remaining < MINIMUM_CLAIM_SECONDS:
        raise RuntimeError("dependency_released_without_minimum_watchdog_time")
    pool = GpuPool(LAB)
    claim_started = time.monotonic()
    claimed = False
    heartbeat: Heartbeat | None = None
    ip: str | None = None
    terminal: dict[str, Any] = {}
    release_condition = "ready"
    try:
        bench = pool.claim(
            PROJECT,
            bench_id=BENCH,
            lease_seconds=max(300, remaining - RELEASE_RESERVE_SECONDS),
        )
        claimed = True
        append_event("bench_claimed", claim=bench["claim"])
        heartbeat = Heartbeat(pool)
        heartbeat.start()
        instance = get_instance(bench["resource"]["instance_id"])
        ip = extract_public_ipv4(instance)
        validate_shared_checkpoint(ip)
        stage(ip, rows)
        identity = remote(
            ip,
            "test -f /home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint/model-00001-of-00002.safetensors "
            "&& nvidia-smi --query-gpu=name,uuid --format=csv,noheader",
            60,
        )
        (ARTIFACTS / "remote-identity.stdout").write_text(identity.stdout)
        (ARTIFACTS / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError("remote_identity_or_checkpoint_failed")
        component = remote(
            ip,
            f"WINDOW512_REMOTE_ROOT={shlex.quote(REMOTE)} "
            f"bash {shlex.quote(REMOTE + '/input/remote_component.sh')}",
            min(900, max(300, remaining - RELEASE_RESERVE_SECONDS)),
        )
        (ARTIFACTS / "component.worker.stdout").write_text(component.stdout)
        (ARTIFACTS / "component.worker.stderr").write_text(component.stderr)
        component_root = retrieve_files(
            ip,
            "component",
            (
                "REMOTE_TERMINAL.json",
                "INVOCATION_STATE.json",
                "COMPONENT_TERMINAL.json",
                "component.stdout",
                "component.stderr",
            ),
        )
        component_terminal = read_json(component_root / "COMPONENT_TERMINAL.json")
        if component.returncode or not component_terminal.get("component_pass"):
            terminal = {
                "schema_version": 1,
                "status": "terminal",
                "classification": (
                    component_terminal.get("status") or "component_failure"
                ),
                "component": component_terminal,
                "candidate_cuda_invocation_started": read_json(
                    component_root / "INVOCATION_STATE.json"
                ).get("candidate_cuda_invocation_started"),
                "scientific_invocation_started": read_json(
                    component_root / "INVOCATION_STATE.json"
                ).get("scientific_invocation_started"),
            }
        else:
            seconds_left = int(
                (WATCHDOG_DEADLINE - dt.datetime.now(dt.timezone.utc)).total_seconds()
            )
            if seconds_left < 900:
                terminal = {
                    "schema_version": 1,
                    "status": "terminal",
                    "classification": "component_pass_endpoint_watchdog_boundary",
                    "component": component_terminal,
                    "candidate_cuda_invocation_started": True,
                    "scientific_invocation_started": True,
                }
            else:
                endpoint = remote(
                    ip,
                    f"WINDOW512_REMOTE_ROOT={shlex.quote(REMOTE)} "
                    f"timeout {max(300, seconds_left - RELEASE_RESERVE_SECONDS)} "
                    f"bash {shlex.quote(REMOTE + '/input/remote_endpoint_pair.sh')}",
                    max(360, seconds_left - 120),
                )
                (ARTIFACTS / "endpoint.worker.stdout").write_text(endpoint.stdout)
                (ARTIFACTS / "endpoint.worker.stderr").write_text(endpoint.stderr)
                endpoint_root = retrieve_files(
                    ip,
                    "endpoint",
                    (
                        "WORKER_TERMINAL.json",
                        "INVOCATION_STATE.json",
                        "ENDPOINT_RESULT.json",
                        "control.runner.stdout",
                        "control.runner.stderr",
                        "candidate.runner.stdout",
                        "candidate.runner.stderr",
                        "control.server-start.log",
                        "candidate.server-start.log",
                    ),
                )
                endpoint_result = read_json(endpoint_root / "ENDPOINT_RESULT.json")
                invocation = read_json(endpoint_root / "INVOCATION_STATE.json")
                if endpoint_result:
                    terminal = {
                        "schema_version": 1,
                        "status": "terminal",
                        "classification": endpoint_result.get(
                            "classification", "endpoint_terminal"
                        ),
                        "component": component_terminal,
                        "endpoint": endpoint_result,
                        "candidate_cuda_invocation_started": invocation.get(
                            "candidate_cuda_started"
                        ),
                        "scientific_invocation_started": invocation.get(
                            "candidate_science_started"
                        ),
                    }
                else:
                    terminal = {
                        "schema_version": 1,
                        "status": "terminal",
                        "classification": "endpoint_consumer_failure",
                        "component": component_terminal,
                        "worker_exit_code": endpoint.returncode,
                        "invocation": invocation,
                        "candidate_cuda_invocation_started": invocation.get(
                            "candidate_cuda_started"
                        ),
                        "scientific_invocation_started": invocation.get(
                            "candidate_science_started"
                        ),
                    }
        return_code = 0
    except Exception as error:
        terminal = {
            "schema_version": 1,
            "status": "terminal",
            "classification": "owner_or_external_failure",
            "error": str(error),
            "candidate_cuda_invocation_started": None,
            "scientific_invocation_started": None,
        }
        return_code = 2
    finally:
        if heartbeat:
            heartbeat.close()
        spend = (
            (time.monotonic() - claim_started) * RATE_USD_PER_HOUR / 3600
            if claimed
            else 0.0
        )
        terminal["actual_spend_usd"] = spend
        terminal["timestamp_utc"] = utc_now()
        atomic_json(ARTIFACTS / "FINAL_TERMINAL.json", terminal)
        endpoint = terminal.get("endpoint", {})
        if terminal.get("classification") in {
            "quality_unsafe_performance_positive",
            "quality_unsafe_ceiling_pass",
        }:
            summary = (
                "The exact quality-unsafe 512-window proxy passed component/path checks "
                f"and measured {endpoint.get('reduction_fraction', 0):.3%} endpoint reduction."
            )
            next_action = (
                "Do not promote. Open separate exact served-model GPQA-Diamond, TauBench, "
                "tool-call, and feature validation or an explicit training/recovery plan."
            )
            status = "complete"
        elif terminal.get("classification") == "endpoint_negative":
            summary = (
                "The exact 512-window component/path check passed, but the sole c32 pair "
                "failed the endpoint or cheap-coherence gate."
            )
            next_action = "Close this exact 512-window proxy without replay or sweep."
            status = "complete"
        else:
            summary = (
                "The exact 512-window lane reached a typed component, endpoint, owner, "
                "or watchdog terminal; inspect the project-local final terminal."
            )
            next_action = (
                "Director disposition from artifacts/window512-20260723/FINAL_TERMINAL.json; "
                "do not replay a consumed scientific arm."
            )
            status = "active"
        settle_status(status, summary, next_action, spend)
        if claimed:
            contents = {
                "project": PROJECT,
                "local_window512_result": terminal.get("classification"),
                "local_window512_actual_spend_usd": spend,
                "artifacts": str(ARTIFACTS),
                "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
                "image": "Pinned SGLang v0.5.13 digest 6113665a retained.",
                "checkpoint": "Exact lab-owned resident checkpoint validated against the bound full manifest and exposed read-only; no project copy staged.",
                "server_state": (
                    "Healthy window512-candidate server retained if endpoint candidate reached "
                    "a server terminal; otherwise immutable image/checkpoint and caches retained."
                ),
            }
            try:
                pool.release(
                    PROJECT, contents=contents, condition=release_condition
                )
                append_event("bench_released", condition=release_condition)
            except GpuPoolError as error:
                append_event("bench_release_failure", error=str(error))
                return_code = 2
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
