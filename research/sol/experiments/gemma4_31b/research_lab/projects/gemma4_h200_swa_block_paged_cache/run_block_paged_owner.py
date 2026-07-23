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
sys.path.insert(0, str(REPO / "research/factory/src"))
sys.path.insert(
    0, str(REPO / "research/sol/experiments/glm47flash/campaign_100/nebius")
)

from grad_research.gpu_pool import GpuPool, GpuPoolError  # noqa: E402
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base  # noqa: E402


PROJECT = "gemma4_h200_swa_block_paged_cache"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
REMOTE = "/home/glmrunner/gemma4-swa-block-paged-cache"
RATE = 2.46
CAP = 14.0
PRIOR_SPEND = 0.0
LEASE_SECONDS = 9000


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def emit(event: str, **fields: Any) -> None:
    row = {"timestamp_utc": utc_now(), "event": event, **fields}
    path = HERE / "artifacts/OWNER_EVENTS.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    atomic_json(HERE / "artifacts/OWNER_STATE.json", row)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest() -> dict[str, Any]:
    manifest = json.loads((HERE / "GPU_INPUT_MANIFEST.json").read_text())
    for row in manifest["component"]:
        path = HERE / row["path"]
        if path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            raise RuntimeError(f"immutable input mismatch:{row['path']}")
    return manifest


def remote(ip: str, command: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*ssh_base(ip, KEY), command],
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def scp_to(ip: str, source: Path, destination: str, timeout: int = 600) -> None:
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
        raise RuntimeError(f"transfer failed:{source.name}:{result.stderr[-1000:]}")


def scp_from(
    ip: str, source: str, destination: Path, timeout: int = 600
) -> tuple[bool, str]:
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
    return result.returncode == 0, result.stderr[-1000:]


def reconcile(ip: str, rows: list[dict[str, Any]]) -> None:
    query = """import hashlib,json,pathlib,sys
base=pathlib.Path(sys.argv[1]); rows=json.loads(sys.argv[2]); out={}
for row in rows:
 p=base/row['remote_name']; ok=p.is_file() and p.stat().st_size==row['bytes']
 if ok:
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(8<<20),b''): h.update(b)
  ok=h.hexdigest()==row['sha256']
 out[row['remote_name']]=ok
print(json.dumps(out))
"""
    result = remote(
        ip,
        f"mkdir -p {shlex.quote(REMOTE + '/input')} && "
        f"python3 - {shlex.quote(REMOTE + '/input')} {shlex.quote(json.dumps(rows))} <<'PY'\n"
        f"{query}PY",
        1800,
    )
    if result.returncode:
        raise RuntimeError(f"remote reconciliation failed:{result.stderr[-1000:]}")
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    for row in rows:
        if observed.get(row["remote_name"]):
            emit("input_matched", path=row["path"])
            continue
        source = HERE / row["path"]
        destination = f"{REMOTE}/input/{row['remote_name']}"
        temporary = destination + f".part.{os.getpid()}"
        scp_to(ip, source, temporary)
        finish = remote(
            ip,
            f"test $(stat -c %s {shlex.quote(temporary)}) -eq {row['bytes']} && "
            f"test $(sha256sum {shlex.quote(temporary)} | cut -d' ' -f1) = {row['sha256']} && "
            f"chmod 0444 {shlex.quote(temporary)} && mv -f {shlex.quote(temporary)} {shlex.quote(destination)}",
            300,
        )
        if finish.returncode:
            raise RuntimeError(f"remote finalize failed:{row['remote_name']}")
        emit("input_finalized", path=row["path"], bytes=row["bytes"])


def retrieve_component(ip: str) -> dict[str, Any]:
    root = HERE / "artifacts/remote-component"
    root.mkdir(parents=True, exist_ok=True)
    remote_paths = (
        f"{REMOTE}/artifacts/component/REMOTE_TERMINAL.json",
        f"{REMOTE}/artifacts/component/INVOCATION_STATE.json",
        f"{REMOTE}/artifacts/component/COMPONENT_TERMINAL.json",
        f"{REMOTE}/artifacts/component/worker.stdout",
        f"{REMOTE}/artifacts/component/worker.stderr",
        f"{REMOTE}/component-compact.tar.gz",
        f"{REMOTE}/component-compact.tar.gz.sha256",
    )
    retrieval = {}
    for source in remote_paths:
        name = source.removeprefix(REMOTE + "/").replace("/", "__")
        success, diagnostic = scp_from(ip, source, root / name)
        retrieval[source] = {"success": success, "diagnostic": diagnostic}
        emit("retrieval", source=source, success=success)
    atomic_json(root / "RETRIEVAL.json", retrieval)
    terminal_path = root / "artifacts__component__REMOTE_TERMINAL.json"
    invocation_path = root / "artifacts__component__INVOCATION_STATE.json"
    result_path = root / "artifacts__component__COMPONENT_TERMINAL.json"
    return {
        "remote": json.loads(terminal_path.read_text()) if terminal_path.is_file() else {},
        "invocation": (
            json.loads(invocation_path.read_text()) if invocation_path.is_file() else {}
        ),
        "component": json.loads(result_path.read_text()) if result_path.is_file() else {},
        "retrieval": retrieval,
    }


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


def wait_for_repair(deadline_epoch: float, classification: str) -> None:
    ready = HERE / "REPAIR_READY.json"
    request = HERE / "REPAIR_REQUEST.json"
    atomic_json(
        ready,
        {
            "schema_version": 1,
            "status": "repair_ready",
            "classification": classification,
            "absolute_deadline_utc": dt.datetime.fromtimestamp(
                deadline_epoch, dt.timezone.utc
            )
            .isoformat()
            .replace("+00:00", "Z"),
            "intervention_workload_and_gates_unchanged": True,
        },
    )
    emit("repair_ready", classification=classification)
    while time.time() < deadline_epoch:
        if request.is_file():
            request.unlink()
            ready.unlink(missing_ok=True)
            return
        time.sleep(10)
    raise TimeoutError(f"repair deadline reached:{classification}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-deadline-epoch", type=float, required=True)
    args = parser.parse_args()
    manifest = validate_manifest()
    emit("inputs_validated", files=len(manifest["component"]))
    pool = GpuPool(LAB)
    bench = None
    while time.time() < args.wait_deadline_epoch:
        try:
            bench = pool.claim(PROJECT, bench_id=BENCH, lease_seconds=LEASE_SECONDS)
            break
        except GpuPoolError as error:
            emit("bench_wait", error=str(error))
            time.sleep(20)
    if bench is None:
        atomic_json(
            HERE / "artifacts/FINAL_TERMINAL.json",
            {
                "schema_version": 1,
                "status": "terminal",
                "classification": "typed_external_blocker",
                "reason": "shared_bench_not_available_before_wait_deadline",
                "timestamp_utc": utc_now(),
            },
        )
        return 3

    claimed_epoch = time.time()
    lifecycle_epoch = dt.datetime.fromisoformat(
        bench["lifecycle"]["deadline_utc"].replace("Z", "+00:00")
    ).timestamp()
    absolute_deadline = min(
        lifecycle_epoch - 300,
        claimed_epoch + 120 * 60,
        claimed_epoch + (CAP - PRIOR_SPEND) / RATE * 3600,
    )
    if absolute_deadline - claimed_epoch < 900:
        pool.release(
            PROJECT,
            contents={"project": PROJECT, "reason": "insufficient lifecycle"},
            condition="ready",
        )
        atomic_json(
            HERE / "artifacts/FINAL_TERMINAL.json",
            {
                "schema_version": 1,
                "status": "terminal",
                "classification": "typed_external_blocker",
                "reason": "less_than_15_minutes_lifecycle_after_claim",
                "timestamp_utc": utc_now(),
            },
        )
        return 3

    emit("bench_claimed", bench=BENCH, absolute_deadline_epoch=absolute_deadline)
    heartbeat = Heartbeat(pool)
    heartbeat.start()
    condition = "ready"
    final: dict[str, Any] = {}
    returncode = 0
    try:
        instance = get_instance(bench["resource"]["instance_id"])
        ip = extract_public_ipv4(instance)
        if not ip:
            raise RuntimeError("claimed guest has no public IPv4")
        probe = remote(
            ip,
            "nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader && "
            "sudo docker ps --format '{{.ID}} {{.Names}} {{.Image}}'",
            60,
        )
        if probe.returncode:
            raise RuntimeError(f"claimed guest unreachable:{probe.stderr[-1000:]}")
        emit("guest_reached", telemetry=probe.stdout.strip())
        running = remote(ip, "sudo docker ps -q", 60)
        if running.returncode:
            raise RuntimeError(f"container inventory failed:{running.stderr[-1000:]}")
        if running.stdout.strip():
            stopped = remote(ip, "sudo docker stop $(sudo docker ps -q)", 300)
            if stopped.returncode:
                raise RuntimeError(f"incompatible resident stop failed:{stopped.stderr[-1000:]}")
            emit("incompatible_resident_stopped", container_ids=running.stdout.split())

        reconcile(ip, manifest["component"])
        pool.update(
            PROJECT,
            {
                "project": PROJECT,
                "runtime": "Pinned SGLang v0.5.13 E5M2 16-token block-paged local-KV component active",
                "checkpoint": "Exact lab-owned checkpoint remains read-only and unstaged",
                "server_state": "No endpoint server; component container active",
            },
        )
        command = (
            f"BLOCK_PAGED_REMOTE_ROOT={shlex.quote(REMOTE)} "
            f"bash {shlex.quote(REMOTE + '/input/remote_component.sh')}"
        )
        while True:
            emit("component_worker_started")
            worker = remote(
                ip,
                command,
                max(60, int(absolute_deadline - time.time() - 180)),
            )
            evidence = retrieve_component(ip)
            invocation = evidence["invocation"]
            remote_terminal = evidence["remote"]
            component = evidence["component"]
            emit(
                "component_worker_returned",
                returncode=worker.returncode,
                classification=remote_terminal.get("classification"),
                candidate_started=invocation.get("candidate_cuda_invocation_started"),
            )
            required_retrieval = (
                evidence["retrieval"][
                    f"{REMOTE}/artifacts/component/REMOTE_TERMINAL.json"
                ]["success"]
                and evidence["retrieval"][
                    f"{REMOTE}/artifacts/component/INVOCATION_STATE.json"
                ]["success"]
                and evidence["retrieval"][
                    f"{REMOTE}/artifacts/component/worker.stdout"
                ]["success"]
                and evidence["retrieval"][
                    f"{REMOTE}/artifacts/component/worker.stderr"
                ]["success"]
            )
            if not required_retrieval:
                wait_for_repair(
                    absolute_deadline - 180, "component_retrieval_defect"
                )
                continue
            if remote_terminal.get("classification") == "component_complete" and component:
                break
            if invocation.get("candidate_cuda_invocation_started"):
                final = {
                    "classification": "candidate_failure_after_cuda_start",
                    "remote_terminal": remote_terminal,
                    "invocation": invocation,
                }
                break
            wait_for_repair(
                absolute_deadline - 180,
                "component_pre_invocation_integration_failure",
            )
            manifest = validate_manifest()
            reconcile(ip, manifest["component"])

        if component:
            if component.get("conditional_endpoint_admitted"):
                endpoint_terminal_path = HERE / "ENDPOINT_TERMINAL.json"
                atomic_json(
                    HERE / "COMPONENT_POSITIVE.json",
                    {
                        "schema_version": 1,
                        "status": "component_positive",
                        "component_artifact": "artifacts/remote-component/artifacts__component__COMPONENT_TERMINAL.json",
                        "absolute_endpoint_deadline_utc": dt.datetime.fromtimestamp(
                            absolute_deadline - 180, dt.timezone.utc
                        )
                        .isoformat()
                        .replace("+00:00", "Z"),
                    },
                )
                emit("conditional_endpoint_wait")
                while time.time() < absolute_deadline - 180:
                    if endpoint_terminal_path.is_file():
                        endpoint_terminal = json.loads(
                            endpoint_terminal_path.read_text()
                        )
                        final = {
                            "classification": endpoint_terminal.get(
                                "classification", "endpoint_terminal"
                            ),
                            "component_result": component,
                            "endpoint_result": endpoint_terminal,
                            "endpoint_executed": True,
                        }
                        break
                    time.sleep(10)
                else:
                    raise TimeoutError("conditional endpoint terminal deadline reached")
            else:
                final = {
                    "classification": component.get("status", "component_terminal"),
                    "component_result": component,
                    "endpoint_executed": False,
                }

        elapsed = time.time() - claimed_epoch
        final.update(
            {
                "schema_version": 1,
                "status": "terminal",
                "bench": BENCH,
                "claimed_seconds": elapsed,
                "current_claim_cost_usd": elapsed / 3600 * RATE,
                "provider_cost_usd": PRIOR_SPEND + elapsed / 3600 * RATE,
                "timestamp_utc": utc_now(),
            }
        )
        atomic_json(HERE / "artifacts/FINAL_TERMINAL.json", final)
        emit("scientific_terminal", classification=final["classification"])
    except Exception as error:
        emit("owner_failure", error=repr(error))
        if "unreachable" in str(error) or "no public IPv4" in str(error):
            condition = "maintenance"
        elapsed = time.time() - claimed_epoch
        final = {
            "schema_version": 1,
            "status": "terminal",
            "classification": (
                "typed_external_blocker"
                if condition == "maintenance"
                else "owner_deadline_or_unrepaired_failure"
            ),
            "reason": str(error),
            "claimed_seconds": elapsed,
            "current_claim_cost_usd": elapsed / 3600 * RATE,
            "provider_cost_usd": PRIOR_SPEND + elapsed / 3600 * RATE,
            "timestamp_utc": utc_now(),
        }
        atomic_json(HERE / "artifacts/FINAL_TERMINAL.json", final)
        returncode = 3
    finally:
        heartbeat.close()
        elapsed = time.time() - claimed_epoch
        contents = {
            "project": PROJECT,
            "block_paged_cache_result": final.get("classification", "incomplete"),
            "block_paged_cache_claim_cost_usd": round(elapsed / 3600 * RATE, 6),
            "runtime": "Pinned SGLang v0.5.13 component caches retained",
            "checkpoint": "Exact lab-owned checkpoint remains unchanged and read-only",
            "server_state": "No retained server; component/CUDA caches preserved",
            "artifacts": str(HERE / "artifacts"),
        }
        try:
            pool.release(PROJECT, contents=contents, condition=condition)
        except Exception as error:
            emit("release_failure", error=repr(error))
        emit("bench_released", condition=condition, elapsed_seconds=elapsed)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
