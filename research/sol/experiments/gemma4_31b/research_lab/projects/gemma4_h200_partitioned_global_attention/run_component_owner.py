#!/usr/bin/env python3
"""Retained shared-bench owner for the exact attention component and gated endpoint."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import shutil
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
NEBIUS = REPO / "research/sol/experiments/glm47flash/campaign_100/nebius"
sys.path.insert(0, str(FACTORY))
sys.path.insert(0, str(NEBIUS))

from grad_research.gpu_pool import GpuPool, GpuPoolError  # noqa: E402
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base  # noqa: E402

PROJECT = "gemma4_h200_partitioned_global_attention"
BENCH = "h200-residual-kernel-e00fpjxk4ww2g49apd"
# Director cloud-init bound this bench to the host agent identity (fingerprint
# g5df+MD3rnTnW0lmqaEvI+esJ+H14qj/g7NeeJgDBXg), not the legacy campaign key.
KEY = Path("/root/.config/gradiated/providers/gcore/id_ed25519")
REMOTE = "/home/glmrunner/gemma4-partitioned-attention"
RATE = 2.46
CAP = 10.0
PRIOR_SPEND = 0.0
LEASE_SECONDS = 9000
RETRIEVAL_RESERVE_SECONDS = 300


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def emit(event: str, **fields: Any) -> None:
    row = {"timestamp_utc": utc_now(), "event": event, **fields}
    with (HERE / "artifacts/OWNER_EVENTS.jsonl").open("a") as handle:
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
    for group in ("component", "endpoint_programs", "stack", "checkpoint"):
        for row in manifest[group]:
            path = HERE / row["path"]
            if path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
                raise RuntimeError(f"immutable input mismatch: {row['path']}")
    return manifest


def remote(ip: str, command: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*ssh_base(ip, KEY), command], text=True, capture_output=True, timeout=timeout)


def scp_to(ip: str, source: Path, destination: str, timeout: int) -> None:
    result = subprocess.run(
        ["scp", *ssh_base(ip, KEY)[1:-1], str(source), f"{SSH_USER}@{ip}:{destination}"],
        text=True, capture_output=True, timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"transfer failed for {source.name}: {result.stderr[-1000:]}")


def scp_from(ip: str, source: str, destination: Path, timeout: int = 600) -> bool:
    result = subprocess.run(
        ["scp", *ssh_base(ip, KEY)[1:-1], f"{SSH_USER}@{ip}:{source}", str(destination)],
        text=True, capture_output=True, timeout=timeout,
    )
    return result.returncode == 0


def reconcile(ip: str, rows: list[dict[str, Any]], remote_dir: str) -> None:
    check_script = """import hashlib,json,pathlib,sys
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
    result = remote(ip, f"mkdir -p {shlex.quote(remote_dir)} && python3 - {shlex.quote(remote_dir)} {shlex.quote(json.dumps(rows))} <<'PY'\n{check_script}PY", 3600)
    if result.returncode:
        raise RuntimeError(f"remote reconciliation failed: {result.stderr[-1000:]}")
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    for row in rows:
        if observed.get(row["remote_name"]):
            emit("input_matched", path=row["path"], remote_name=row["remote_name"])
            continue
        source = HERE / row["path"]
        target = f"{remote_dir}/{row['remote_name']}"
        parent = str(Path(target).parent)
        part = target + f".part.{os.getpid()}"
        prep = remote(ip, f"mkdir -p {shlex.quote(parent)} && rm -f {shlex.quote(part)}", 60)
        if prep.returncode:
            raise RuntimeError(f"cannot prepare remote input: {row['remote_name']}")
        emit("input_transfer_started", path=row["path"], bytes=row["bytes"])
        scp_to(ip, source, part, max(600, int(row["bytes"] / 20_000_000) + 600))
        command = (
            f"test $(stat -c %s {shlex.quote(part)}) -eq {row['bytes']} && "
            f"test $(sha256sum {shlex.quote(part)} | cut -d' ' -f1) = {row['sha256']} && "
            f"chmod 0444 {shlex.quote(part)} && mv -f {shlex.quote(part)} {shlex.quote(target)}"
        )
        finish = remote(ip, command, max(300, int(row["bytes"] / 100_000_000) + 300))
        if finish.returncode:
            raise RuntimeError(f"remote hash/finalize failed: {row['remote_name']}")
        emit("input_finalized", path=row["path"], bytes=row["bytes"])


def retrieve(ip: str, phase: str) -> Path:
    root = HERE / "artifacts" / f"remote-{phase}"
    root.mkdir(parents=True, exist_ok=True)
    paths = {
        "component": [
            f"{REMOTE}/artifacts/REMOTE_TERMINAL.json", f"{REMOTE}/artifacts/component/INVOCATION_STATE.json",
            f"{REMOTE}/artifacts/COMPONENT_RESULT.json", f"{REMOTE}/artifacts/component.stdout",
            f"{REMOTE}/artifacts/component.stderr", f"{REMOTE}/component-compact.tar.gz",
            f"{REMOTE}/component-compact.tar.gz.sha256",
        ],
        "endpoint": [
            f"{REMOTE}/endpoint-artifacts/WORKER_TERMINAL.json", f"{REMOTE}/endpoint-artifacts/INVOCATION_STATE.json",
            f"{REMOTE}/endpoint-artifacts/ENDPOINT_RESULT.json", f"{REMOTE}/endpoint-compact.tar.gz",
            f"{REMOTE}/endpoint-compact.tar.gz.sha256",
        ],
    }[phase]
    for source in paths:
        destination = root / source.removeprefix(REMOTE + "/").replace("/", "__")
        ok = scp_from(ip, source, destination)
        emit("retrieval", phase=phase, source=source, success=ok)
    return root


def json_if(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.is_file() else {}


class Heartbeat(threading.Thread):
    def __init__(self, pool: GpuPool):
        super().__init__(daemon=True); self.pool = pool; self.stop_event = threading.Event(); self.error = None

    def run(self) -> None:
        while not self.stop_event.wait(45):
            try: self.pool.heartbeat(PROJECT)
            except Exception as error: self.error = str(error); emit("heartbeat_failure", error=self.error); return

    def close(self) -> None:
        self.stop_event.set(); self.join(5)


def wait_repair(classification: str, deadline_epoch: float) -> None:
    repair = HERE / "REPAIR_REQUEST.json"
    ready = {"schema_version": 1, "status": "repair_ready", "classification": classification, "absolute_deadline_utc": dt.datetime.fromtimestamp(deadline_epoch, dt.timezone.utc).isoformat().replace('+00:00','Z'), "intervention_unchanged": True}
    atomic_json(HERE / "REPAIR_READY.json", ready)
    emit("repair_ready", classification=classification)
    while time.time() < deadline_epoch:
        if repair.is_file():
            repair.unlink(); (HERE / "REPAIR_READY.json").unlink(missing_ok=True); return
        time.sleep(10)
    raise TimeoutError("repair handshake deadline reached")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", default=BENCH)
    parser.add_argument("--wait-deadline-epoch", type=float, required=True)
    args = parser.parse_args()
    manifest = validate_manifest()
    emit("inputs_validated", checkpoint_bytes=manifest["checkpoint_total_bytes"])
    pool = GpuPool(LAB)
    bench = None
    while time.time() < args.wait_deadline_epoch:
        try:
            bench = pool.claim(PROJECT, bench_id=args.bench, lease_seconds=LEASE_SECONDS)
            break
        except GpuPoolError as error:
            emit("bench_wait", error=str(error)); time.sleep(20)
    if bench is None:
        atomic_json(HERE / "artifacts/FINAL_TERMINAL.json", {"status": "terminal", "classification": "typed_external_blocker", "reason": "shared_bench_not_released_before_wait_deadline", "timestamp_utc": utc_now()})
        return 3
    claimed_epoch = time.time()
    lifecycle = dt.datetime.fromisoformat(bench["lifecycle"]["deadline_utc"].replace("Z", "+00:00")).timestamp()
    spend_deadline = claimed_epoch + (CAP - PRIOR_SPEND) / RATE * 3600
    absolute_deadline = min(lifecycle, spend_deadline, claimed_epoch + 3 * 3600)
    if absolute_deadline - claimed_epoch < 900:
        pool.release(PROJECT, contents={"attention_project": "insufficient_lifecycle_after_claim"}, condition="ready")
        atomic_json(HERE / "artifacts/FINAL_TERMINAL.json", {"status": "terminal", "classification": "typed_external_blocker", "reason": "less_than_15_minutes_lifecycle_remained", "timestamp_utc": utc_now()})
        return 3
    emit("bench_claimed", bench=args.bench, absolute_deadline_epoch=absolute_deadline)
    heartbeat = Heartbeat(pool); heartbeat.start()
    condition = "ready"; final: dict[str, Any] = {}
    try:
        instance = get_instance(bench["resource"]["instance_id"])
        ip = extract_public_ipv4(instance)
        if not ip: raise RuntimeError("claimed guest has no public IPv4")
        probe = remote(ip, "nvidia-smi --query-gpu=name --format=csv,noheader && df -BG /home/glmrunner | tail -1", 60)
        if probe.returncode: raise RuntimeError(f"claimed guest unreachable: {probe.stderr[-1000:]}")
        emit("guest_reached", telemetry=probe.stdout.strip())
        reconcile(ip, manifest["component"], REMOTE + "/input")
        pool.update(PROJECT, {"project": PROJECT, "runtime": "SGLang v0.5.13 exact attention component active", "checkpoint": "project-local immutable snapshot bound; not staged until component pass"})
        command = f"PARTITIONED_ATTENTION_REMOTE_ROOT={shlex.quote(REMOTE)} bash {shlex.quote(REMOTE + '/input/remote_component.sh')}"
        emit("component_worker_started")
        worker = remote(ip, command, max(60, int(absolute_deadline - time.time() - RETRIEVAL_RESERVE_SECONDS)))
        root = retrieve(ip, "component")
        terminal = json_if(root / "artifacts__REMOTE_TERMINAL.json")
        invocation = json_if(root / "artifacts__component__INVOCATION_STATE.json")
        result = json_if(root / "artifacts__COMPONENT_RESULT.json")
        emit("component_worker_returned", returncode=worker.returncode, terminal=terminal.get("classification"), candidate_started=invocation.get("candidate_cuda_invocation_started"))
        while terminal.get("classification") in {"integration_failure", "component_consumer_failure"}:
            if invocation.get("scientific_invocation_started"):
                wait_repair("component_consumer_failure", absolute_deadline - RETRIEVAL_RESERVE_SECONDS)
                reconcile(ip, [row for row in manifest["component"] if row["remote_name"] == "analyze_component.py"], REMOTE + "/input")
                reconcile(ip, [next(row for row in manifest["component"] if row["remote_name"] == "remote_component_consumer.sh")], REMOTE + "/input")
                worker = remote(ip, f"PARTITIONED_ATTENTION_REMOTE_ROOT={shlex.quote(REMOTE)} bash {shlex.quote(REMOTE + '/input/remote_component_consumer.sh')}", 900)
            else:
                wait_repair("component_pre_invocation_integration_failure", absolute_deadline - RETRIEVAL_RESERVE_SECONDS)
                reconcile(ip, manifest["component"], REMOTE + "/input")
                worker = remote(ip, command, max(60, int(absolute_deadline - time.time() - RETRIEVAL_RESERVE_SECONDS)))
            root = retrieve(ip, "component"); terminal = json_if(root / "artifacts__REMOTE_TERMINAL.json"); invocation = json_if(root / "artifacts__component__INVOCATION_STATE.json"); result = json_if(root / "artifacts__COMPONENT_RESULT.json")
        if terminal.get("classification") != "component_complete" or not result:
            raise RuntimeError("component terminal/result retrieval incomplete")
        component_pass = bool(result.get("mechanism_pass") or result.get("component_pass") or result.get("pass"))
        if not component_pass:
            final = {"classification": "component_reject", "component_result": result, "endpoint_executed": False}
        else:
            emit("component_pass_endpoint_staging")
            reconcile(ip, manifest["endpoint_programs"] + manifest["stack"], REMOTE + "/input")
            reconcile(ip, manifest["checkpoint"], REMOTE + "/checkpoint")
            pool.update(PROJECT, {"runtime": "exact FP8+QKV+deferred-local-KV paired endpoint active", "checkpoint": "exact project-local immutable snapshot staged and verified"})
            endpoint_command = f"PARTITIONED_ATTENTION_REMOTE_ROOT={shlex.quote(REMOTE)} bash {shlex.quote(REMOTE + '/input/remote_endpoint_pair.sh')}"
            endpoint_worker = remote(ip, endpoint_command, max(60, int(absolute_deadline - time.time() - RETRIEVAL_RESERVE_SECONDS)))
            endpoint_root = retrieve(ip, "endpoint")
            endpoint_terminal = json_if(endpoint_root / "endpoint-artifacts__WORKER_TERMINAL.json")
            endpoint_invocation = json_if(endpoint_root / "endpoint-artifacts__INVOCATION_STATE.json")
            endpoint_result = json_if(endpoint_root / "endpoint-artifacts__ENDPOINT_RESULT.json")
            emit("endpoint_worker_returned", returncode=endpoint_worker.returncode, terminal=endpoint_terminal.get("classification"), candidate_started=endpoint_invocation.get("candidate_science_started"))
            if endpoint_terminal.get("classification") != "endpoint_complete" or not endpoint_result:
                if time.time() < absolute_deadline - RETRIEVAL_RESERVE_SECONDS:
                    wait_repair("endpoint_consumer_or_integration_failure", absolute_deadline - RETRIEVAL_RESERVE_SECONDS)
                raise RuntimeError("endpoint terminal/result incomplete; completed component preserved remotely")
            final = {"classification": endpoint_result.get("classification"), "component_result": result, "endpoint_result": endpoint_result, "endpoint_executed": True}
        elapsed = time.time() - claimed_epoch
        final.update({"schema_version": 1, "status": "terminal", "bench": args.bench, "claimed_seconds": elapsed, "provider_cost_usd": PRIOR_SPEND + elapsed / 3600 * RATE, "timestamp_utc": utc_now()})
        atomic_json(HERE / "artifacts/FINAL_TERMINAL.json", final)
        emit("scientific_terminal", classification=final["classification"])
    except Exception as error:
        emit("owner_failure", error=repr(error))
        # The claimed guest is only marked maintenance if it is unreachable/unsafe.
        condition = "maintenance" if "unreachable" in str(error) or "no public IPv4" in str(error) else "ready"
        final = {"schema_version": 1, "status": "terminal", "classification": "typed_external_blocker" if condition == "maintenance" else "owner_deadline_or_unrepaired_failure", "reason": str(error), "timestamp_utc": utc_now()}
        atomic_json(HERE / "artifacts/FINAL_TERMINAL.json", final)
        returncode = 3
    else:
        returncode = 0
    finally:
        heartbeat.close()
        elapsed = time.time() - claimed_epoch
        contents = {"project": "shared: next gemma4_h200_fp8_layer_dataflow_fusion", "attention_result": final.get("classification", "incomplete"), "attention_claim_cost_usd": round(elapsed / 3600 * RATE, 6), "server_state": "No retained server; caches and verified staged bytes preserved warm."}
        try: pool.release(PROJECT, contents=contents, condition=condition)
        except Exception as error: emit("release_failure", error=repr(error))
        emit("bench_released", condition=condition, elapsed_seconds=elapsed)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
