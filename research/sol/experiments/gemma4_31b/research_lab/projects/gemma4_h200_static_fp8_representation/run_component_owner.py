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
import threading
import time
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
REPO = HERE.parents[6]
FACTORY = REPO / "research/factory/src"
NEBIUS_TOOLS = REPO / "research/sol/experiments/glm47flash/campaign_100/nebius"
sys.path.insert(0, str(FACTORY))
sys.path.insert(0, str(NEBIUS_TOOLS))

from grad_research.gpu_pool import GpuPool, GpuPoolError  # noqa: E402
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base  # noqa: E402


PROJECT = "gemma4_h200_static_fp8_representation"
BENCH = "h200-continuity-e00hzj9a8khp0fevy5"
KEY = Path("/root/.config/gradiated/providers/gcore/id_ed25519")
REMOTE = "/home/glmrunner/gemma4-static-fp8"
RATE_USD_PER_HOUR = 2.46
AUTHORIZED_USD = 1.8
PRIOR_SPEND_USD = 0.0
MAX_CLAIM_SECONDS = 2400
RETRIEVAL_RESERVE_SECONDS = 180
HIGHER_PRIORITY_PROJECTS = {
    "gemma4_current_runtime_frontier",
    "gemma4_h200_partitioned_global_attention",
}
BENCH_REGISTERED_AT = "2026-07-22T14:46:16.480323Z"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def emit(event: str, **fields: Any) -> None:
    row = {"timestamp_utc": utc_now(), "event": event, **fields}
    root = HERE / "artifacts"
    root.mkdir(exist_ok=True)
    with (root / "OWNER_EVENTS.jsonl").open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    atomic_json(root / "OWNER_STATE.json", row)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_inputs() -> dict[str, Any]:
    manifest = json.loads((HERE / "GPU_INPUT_MANIFEST.json").read_text())
    if sha256(HERE / "PRODUCER_MANIFEST.json") != manifest["producer_manifest_sha256"]:
        raise RuntimeError("producer manifest identity mismatch")
    for row in manifest["files"]:
        path = HERE / row["path"]
        if path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            raise RuntimeError(f"immutable input mismatch: {row['path']}")
    return manifest


def completed_priority_releases() -> set[str]:
    events_path = LAB / "runtime/gpu_events.jsonl"
    completed = set()
    if not events_path.is_file():
        return completed
    for line in events_path.read_text().splitlines():
        event = json.loads(line)
        if (
            event.get("event") == "bench_released"
            and event.get("bench_id") == BENCH
            and event.get("timestamp", "") >= BENCH_REGISTERED_AT
            and event.get("project") in HIGHER_PRIORITY_PROJECTS
        ):
            completed.add(event["project"])
    return completed


def wait_for_ordered_claim(
    pool: GpuPool,
    bench_id: str,
    wait_deadline_epoch: float,
) -> dict[str, Any] | None:
    last_observed: set[str] | None = None
    while time.time() < wait_deadline_epoch:
        completed = completed_priority_releases()
        if completed != last_observed:
            emit(
                "priority_wait",
                completed=sorted(completed),
                remaining=sorted(HIGHER_PRIORITY_PROJECTS - completed),
            )
            last_observed = completed
        if completed == HIGHER_PRIORITY_PROJECTS:
            try:
                return pool.claim(PROJECT, bench_id=bench_id, lease_seconds=2700)
            except GpuPoolError as error:
                emit("ordered_claim_wait", error=str(error))
        time.sleep(30)
    return None


def remote(ip: str, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*ssh_base(ip, KEY), command], text=True, capture_output=True, timeout=timeout
    )


def scp_to(ip: str, source: Path, destination: str, timeout: int) -> None:
    result = subprocess.run(
        ["scp", *ssh_base(ip, KEY)[1:-1], str(source), f"{SSH_USER}@{ip}:{destination}"],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"transfer failed for {source.name}: {result.stderr[-1200:]}")


def scp_from(ip: str, source: str, destination: Path, timeout: int = 300) -> bool:
    result = subprocess.run(
        ["scp", *ssh_base(ip, KEY)[1:-1], f"{SSH_USER}@{ip}:{source}", str(destination)],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return result.returncode == 0


def reconcile(ip: str, rows: list[dict[str, Any]]) -> None:
    remote_dir = REMOTE + "/input"
    check = """import hashlib,json,pathlib,sys
base=pathlib.Path(sys.argv[1]); rows=json.loads(sys.argv[2]); out={}
for row in rows:
 p=base/row['remote_name']; ok=p.is_file() and p.stat().st_size==row['bytes']
 if ok:
  h=hashlib.sha256()
  with p.open('rb') as f:
   for chunk in iter(lambda:f.read(8<<20),b''): h.update(chunk)
  ok=h.hexdigest()==row['sha256']
 out[row['remote_name']]=ok
print(json.dumps(out))
"""
    result = remote(
        ip,
        f"mkdir -p {shlex.quote(remote_dir)} && python3 - {shlex.quote(remote_dir)} {shlex.quote(json.dumps(rows))} <<'PY'\n{check}PY",
        600,
    )
    if result.returncode:
        raise RuntimeError(f"remote reconciliation failed: {result.stderr[-1200:]}")
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    for row in rows:
        if observed.get(row["remote_name"]):
            emit("input_matched", remote_name=row["remote_name"])
            continue
        source = HERE / row["path"]
        target = f"{remote_dir}/{row['remote_name']}"
        temporary = target + f".part.{os.getpid()}"
        prepared = remote(ip, f"rm -f {shlex.quote(temporary)}", 60)
        if prepared.returncode:
            raise RuntimeError(f"remote temporary cleanup failed: {row['remote_name']}")
        emit("input_transfer_started", remote_name=row["remote_name"], bytes=row["bytes"])
        scp_to(ip, source, temporary, max(300, int(row["bytes"] / 20_000_000) + 180))
        finalized = remote(
            ip,
            f"test $(stat -c %s {shlex.quote(temporary)}) -eq {row['bytes']} && "
            f"test $(sha256sum {shlex.quote(temporary)} | cut -d' ' -f1) = {row['sha256']} && "
            f"chmod 0444 {shlex.quote(temporary)} && mv -f {shlex.quote(temporary)} {shlex.quote(target)}",
            300,
        )
        if finalized.returncode:
            raise RuntimeError(f"remote finalize failed: {row['remote_name']}")
        emit("input_finalized", remote_name=row["remote_name"], bytes=row["bytes"])


class Heartbeat(threading.Thread):
    def __init__(self, pool: GpuPool):
        super().__init__(daemon=True)
        self.pool = pool
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.wait(45):
            try:
                self.pool.heartbeat(PROJECT)
            except Exception as error:
                emit("heartbeat_failure", error=repr(error))
                return

    def close(self) -> None:
        self.stop_event.set()
        self.join(5)


def retrieve(ip: str) -> tuple[dict[str, Any], dict[str, Any], Path]:
    root = HERE / "artifacts" / "retrieved"
    root.mkdir(parents=True, exist_ok=True)
    paths = [
        (f"{REMOTE}/artifacts/REMOTE_TERMINAL.json", root / "REMOTE_TERMINAL.json"),
        (f"{REMOTE}/artifacts/run/INVOCATION_STATE.json", root / "INVOCATION_STATE.json"),
        (f"{REMOTE}/artifacts/consumer.stdout", root / "consumer.stdout"),
        (f"{REMOTE}/artifacts/consumer.stderr", root / "consumer.stderr"),
        (f"{REMOTE}/static-fp8-compact.tar.gz", root / "static-fp8-compact.tar.gz"),
        (f"{REMOTE}/static-fp8-compact.tar.gz.sha256", root / "static-fp8-compact.tar.gz.sha256"),
    ]
    for source, destination in paths:
        emit("retrieval", source=source, success=scp_from(ip, source, destination))
    terminal_path = root / "REMOTE_TERMINAL.json"
    state_path = root / "INVOCATION_STATE.json"
    terminal = json.loads(terminal_path.read_text()) if terminal_path.is_file() else {}
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    return terminal, state, root


def wait_for_repair(
    absolute_deadline: float,
    terminal: dict[str, Any],
    state: dict[str, Any],
) -> None:
    repair_deadline = absolute_deadline - RETRIEVAL_RESERVE_SECONDS
    ready_path = HERE / "REPAIR_READY.json"
    request_path = HERE / "REPAIR_REQUEST.json"
    atomic_json(
        ready_path,
        {
            "schema_version": 1,
            "status": "repair_ready",
            "classification": terminal.get("classification", "retrieval_failure"),
            "diagnostic": terminal,
            "invocation_state": state,
            "absolute_repair_deadline_utc": dt.datetime.fromtimestamp(
                repair_deadline, dt.timezone.utc
            ).isoformat().replace("+00:00", "Z"),
            "intervention_unchanged": True,
        },
    )
    emit(
        "repair_ready",
        classification=terminal.get("classification", "retrieval_failure"),
        scientific_started=state.get("scientific_invocation_started", False),
    )
    while time.time() < repair_deadline:
        if request_path.is_file():
            request = json.loads(request_path.read_text())
            if not request.get("intervention_unchanged", False):
                raise RuntimeError("repair request attempted an intervention change")
            request_path.unlink()
            ready_path.unlink(missing_ok=True)
            emit("repair_requested", request=request)
            return
        time.sleep(5)
    raise TimeoutError("repair handshake deadline expired")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", default=BENCH)
    parser.add_argument("--wait-deadline-epoch", type=float, required=True)
    args = parser.parse_args()
    manifest = validate_inputs()
    emit("inputs_validated", input_bytes=sum(row["bytes"] for row in manifest["files"]))

    pool = GpuPool(LAB)
    bench = wait_for_ordered_claim(pool, args.bench, args.wait_deadline_epoch)
    if bench is None:
        atomic_json(
            HERE / "artifacts/FINAL_TERMINAL.json",
            {
                "schema_version": 1,
                "status": "terminal",
                "classification": "typed_external_blocker",
                "reason": "higher_priority_lanes_did_not_release_with_safe_claim_window",
                "required_releases": sorted(HIGHER_PRIORITY_PROJECTS),
                "observed_releases": sorted(completed_priority_releases()),
                "provider_cost_usd": PRIOR_SPEND_USD,
                "timestamp_utc": utc_now(),
            },
        )
        emit("ordered_wait_terminal", classification="typed_external_blocker")
        return 3
    claimed_epoch = time.time()
    lifecycle_epoch = dt.datetime.fromisoformat(
        bench["lifecycle"]["deadline_utc"].replace("Z", "+00:00")
    ).timestamp()
    spend_seconds = (AUTHORIZED_USD - PRIOR_SPEND_USD) / RATE_USD_PER_HOUR * 3600
    absolute_deadline = min(
        claimed_epoch + MAX_CLAIM_SECONDS,
        claimed_epoch + spend_seconds,
        lifecycle_epoch,
    )
    emit("bench_claimed", bench=args.bench, absolute_deadline_epoch=absolute_deadline)
    heartbeat = Heartbeat(pool)
    heartbeat.start()
    condition = "ready"
    final: dict[str, Any] = {}
    returncode = 0
    try:
        if absolute_deadline - claimed_epoch < 600:
            raise RuntimeError("typed_external_blocker:less_than_ten_minutes_remain")
        instance = get_instance(bench["resource"]["instance_id"])
        ip = extract_public_ipv4(instance)
        if not ip:
            condition = "maintenance"
            raise RuntimeError("typed_external_blocker:claimed_guest_has_no_public_ipv4")
        probe = remote(
            ip,
            "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader && df -BG /home/glmrunner | tail -1",
            60,
        )
        if probe.returncode:
            condition = "maintenance"
            raise RuntimeError(f"typed_external_blocker:claimed_guest_unreachable:{probe.stderr[-800:]}")
        emit("guest_reached", telemetry=probe.stdout.strip())
        reconcile(ip, manifest["files"])
        pool.update(
            PROJECT,
            {
                "project": PROJECT,
                "runtime": "pinned SGLang v0.5.13 static-FP8 exact component active",
                "checkpoint": "project-local layer-0 BF16 tensor and serialized static-FP8 representation staged",
                "model": manifest["model"],
                "server_state": "No server; exact component consumer only.",
            },
        )
        command = (
            f"STATIC_FP8_REMOTE_ROOT={shlex.quote(REMOTE)} "
            f"bash {shlex.quote(REMOTE + '/input/remote_static_fp8_component.sh')}"
        )
        attempt = 0
        while True:
            attempt += 1
            emit("component_worker_started", attempt=attempt)
            timeout = max(
                60,
                int(absolute_deadline - time.time() - RETRIEVAL_RESERVE_SECONDS),
            )
            worker = remote(ip, command, timeout)
            terminal, state, retrieved = retrieve(ip)
            emit(
                "component_worker_returned",
                attempt=attempt,
                returncode=worker.returncode,
                classification=terminal.get("classification"),
                scientific_started=state.get("scientific_invocation_started", False),
            )
            if terminal.get("classification") == "component_complete":
                break
            wait_for_repair(absolute_deadline, terminal, state)
            manifest = validate_inputs()
            reconcile(ip, manifest["files"])
        archive = retrieved / "static-fp8-compact.tar.gz"
        if not archive.is_file():
            raise RuntimeError("retrieval_failure:compact archive missing")
        subprocess.run(["tar", "-xzf", str(archive), "-C", str(retrieved)], check=True)
        component_path = retrieved / "run/TERMINAL.json"
        if not component_path.is_file():
            raise RuntimeError("retrieval_failure:component terminal absent from archive")
        component = json.loads(component_path.read_text())
        elapsed = time.time() - claimed_epoch
        final = {
            "schema_version": 1,
            "status": "terminal",
            "classification": component["classification"],
            "bench": args.bench,
            "claimed_seconds": elapsed,
            "provider_cost_usd": PRIOR_SPEND_USD + elapsed / 3600 * RATE_USD_PER_HOUR,
            "component_terminal_path": str(component_path.relative_to(HERE)),
            "component": component,
            "endpoint_executed": False,
            "endpoint_reason": "component-only admission; no endpoint promotion without a positive component and remaining loader/measurement time",
            "timestamp_utc": utc_now(),
        }
        atomic_json(HERE / "artifacts/FINAL_TERMINAL.json", final)
        emit("scientific_terminal", classification=final["classification"])
    except Exception as error:
        emit("owner_failure", error=repr(error))
        elapsed = time.time() - claimed_epoch
        final = {
            "schema_version": 1,
            "status": "terminal",
            "classification": "typed_external_blocker"
            if condition == "maintenance" or "typed_external_blocker" in str(error)
            else "owner_or_integration_failure",
            "reason": str(error),
            "claimed_seconds": elapsed,
            "provider_cost_usd": PRIOR_SPEND_USD + elapsed / 3600 * RATE_USD_PER_HOUR,
            "timestamp_utc": utc_now(),
        }
        atomic_json(HERE / "artifacts/FINAL_TERMINAL.json", final)
        returncode = 3
    finally:
        heartbeat.close()
        elapsed = time.time() - claimed_epoch
        contents = {
            "project": "shared: higher-priority current-runtime and partitioned-attention lanes remain next",
            "static_fp8_result": final.get("classification", "incomplete"),
            "static_fp8_claim_cost_usd": round(elapsed / 3600 * RATE_USD_PER_HOUR, 6),
            "image": manifest["runtime_image"],
            "checkpoint": "project-local layer-0 BF16 and static-FP8 snapshots remain staged under /home/glmrunner/gemma4-static-fp8/input",
            "server_state": "No server; image and exact component artifacts retained.",
        }
        try:
            pool.release(PROJECT, contents=contents, condition=condition)
        except Exception as error:
            emit("release_failure", error=repr(error))
        emit("bench_released", condition=condition, elapsed_seconds=elapsed)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
