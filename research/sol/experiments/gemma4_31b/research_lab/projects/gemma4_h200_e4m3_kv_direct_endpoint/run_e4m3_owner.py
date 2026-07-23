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
sys.path[:0] = [str(REPO / "research/factory/src"), str(REPO / "research/sol/experiments/glm47flash/campaign_100/nebius")]
from grad_research.gpu_pool import GpuPool
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base

PROJECT = "gemma4_h200_e4m3_kv_direct_endpoint"
BENCH = "h200-sync-linear-e00vhh6h29fj68x91g"
REMOTE = "/home/glmrunner/gemma4-e4m3-kv-direct"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
RATE = 2.46
CAP = 8.0
PRIOR_SPEND = 0.03299363944189196
ARTIFACTS = HERE / "artifacts" / "e4m3-kv-direct-20260723"
WATCHDOG = dt.datetime(2026, 7, 23, 12, 30, tzinfo=dt.timezone.utc)
UNIT = "gemma4-e4m3-kv-direct-20260723.service"

def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)

def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(8 << 20), b""):
            value.update(part)
    return value.hexdigest()

def event(name: str, **fields: Any) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    row = {"timestamp_utc": now(), "event": name, **fields}
    with (ARTIFACTS / "OWNER_EVENTS.jsonl").open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    atomic(ARTIFACTS / "OWNER_STATE.json", row)

def remote(ip: str, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*ssh_base(ip, KEY), command], text=True, capture_output=True, timeout=timeout)

def copy_to(ip: str, source: Path, target: str, timeout: int = 300) -> None:
    result = subprocess.run(["scp", *ssh_base(ip, KEY)[1:-1], str(source), f"{SSH_USER}@{ip}:{target}"], text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"scp_to_failed:{source.name}:{result.stderr[-1000:]}")

def copy_from(ip: str, source: str, target: Path, timeout: int = 300) -> None:
    result = subprocess.run(["scp", *ssh_base(ip, KEY)[1:-1], f"{SSH_USER}@{ip}:{source}", str(target)], text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"scp_from_failed:{source}:{result.stderr[-1000:]}")

def status(summary: str, next_action: str, spend: float, active: dict[str, Any] | None) -> None:
    value = json.loads((HERE / "STATUS.json").read_text())
    value.update({"summary": summary, "next_action": next_action, "actual_spend_usd": spend, "active_session": active})
    atomic(HERE / "STATUS.json", value)

def checkpoint_command() -> str:
    items = []
    for line in (HERE / "CHECKPOINT_SHA256SUMS.txt").read_text().splitlines():
        sha, path = line.split(maxsplit=1)
        items.append(f"{sha}:{Path(path).name}")
    quoted = " ".join(shlex.quote(item) for item in items)
    return "set -e; root=/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint; for x in " + quoted + "; do h=${x%%:*}; n=${x#*:}; printf '%s  %s\\n' \"$h\" \"$root/$n\" | sha256sum -c -; done"

class Pulse(threading.Thread):
    def __init__(self, pool: GpuPool):
        super().__init__(daemon=True); self.pool = pool; self.stop = threading.Event()
    def run(self) -> None:
        while not self.stop.wait(40):
            try: self.pool.heartbeat(PROJECT)
            except Exception as exc: event("heartbeat_failure", error=str(exc)); return

def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(HERE / "verify_director_binding.py")], check=True)
    cap = json.loads((LAB / "runtime/spend_cap.json").read_text())
    if cap.get("reservations", {}).get(PROJECT, {}).get("authorized_usd") != CAP:
        raise RuntimeError("reservation_not_durable")
    files = [HERE / "remote_e4m3_candidate.sh", HERE / "CHECKPOINT_SHA256SUMS.txt", *sorted(path for path in (HERE / "inputs").iterdir() if path.is_file())]
    atomic(HERE / "GPU_INPUT_MANIFEST.json", {"schema_version": 1, "files": [{"name": p.name, "bytes": p.stat().st_size, "sha256": digest(p)} for p in files]})
    remaining = int((WATCHDOG - dt.datetime.now(dt.timezone.utc)).total_seconds())
    if remaining < 900:
        raise RuntimeError("typed_watchdog_boundary_insufficient_time")
    deadline = min(time.time() + 6000, WATCHDOG.timestamp() - 120)
    session = {"pid": os.getpid(), "deadline_utc": dt.datetime.fromtimestamp(deadline, dt.timezone.utc).isoformat().replace("+00:00", "Z"), "artifact_root": str(ARTIFACTS), "expected_terminal": "retain_direct|hybrid_comparator|close|typed_external_boundary", "unit": UNIT, "unit_manager": "user"}
    status("Claimed owner preparing the sole E4M3 KV Triton candidate.", "Retain claim through the bounded candidate terminal or repair boundary.", PRIOR_SPEND, session)
    pool, claimed, pulse, started, ip, terminal = GpuPool(LAB), False, None, time.monotonic(), None, None
    try:
        bench = pool.claim(PROJECT, bench_id=BENCH, lease_seconds=max(600, int(deadline-time.time())))
        claimed = True; event("claimed", claim=bench["claim"]); pulse = Pulse(pool); pulse.start()
        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip: raise RuntimeError("typed_provider_boundary_no_public_ip")
        identity = remote(ip, "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version", 60)
        (ARTIFACTS / "remote-identity.stdout").write_text(identity.stdout); (ARTIFACTS / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode: raise RuntimeError("typed_provider_boundary_ssh_identity_failed")
        check = remote(ip, checkpoint_command(), 900)
        (ARTIFACTS / "checkpoint.stdout").write_text(check.stdout); (ARTIFACTS / "checkpoint.stderr").write_text(check.stderr)
        if check.returncode: raise RuntimeError("resident_checkpoint_manifest_failed")
        setup = remote(ip, f"mkdir -p {shlex.quote(REMOTE+'/input')} {shlex.quote(REMOTE+'/endpoint-artifacts')}", 60)
        if setup.returncode: raise RuntimeError("remote_prepare_failed")
        for source in files:
            expected, final = digest(source), f"{REMOTE}/input/{source.name}"
            probe = remote(ip, f"test -f {shlex.quote(final)} && test \"$(sha256sum {shlex.quote(final)} | awk '{{print $1}}')\" = {expected}", 60)
            if probe.returncode:
                partial = final + f".{expected}.part"; copy_to(ip, source, partial)
                finish = remote(ip, f"test \"$(sha256sum {shlex.quote(partial)} | awk '{{print $1}}')\" = {expected} && chmod 0444 {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {shlex.quote(final)}", 60)
                if finish.returncode: raise RuntimeError(f"input_finalize_failed:{source.name}")
            event("input_bound", input_name=source.name, sha256=expected)
        timeout = max(60, int(deadline-time.time()-90))
        worker = remote(ip, f"E4M3_REMOTE_ROOT={shlex.quote(REMOTE)} timeout --signal=TERM {timeout} bash {shlex.quote(REMOTE+'/input/remote_e4m3_candidate.sh')}", timeout+30)
        (ARTIFACTS / "remote-worker.stdout").write_text(worker.stdout); (ARTIFACTS / "remote-worker.stderr").write_text(worker.stderr)
        for name in ("INVOCATION_STATE.json", "WORKER_TERMINAL.json"):
            got = remote(ip, f"cat {shlex.quote(REMOTE+'/endpoint-artifacts/'+name)}", 60)
            (ARTIFACTS / f"REMOTE_{name}").write_text(got.stdout if got.returncode == 0 else json.dumps({"retrieval_error":got.stderr[-1000:]}))
        state = json.loads((ARTIFACTS / "REMOTE_INVOCATION_STATE.json").read_text())
        worker_terminal = json.loads((ARTIFACTS / "REMOTE_WORKER_TERMINAL.json").read_text())
        if worker.returncode and not state.get("candidate_science_started"):
            repair_deadline = min(deadline-90, time.time()+300)
            atomic(ARTIFACTS / "REPAIR_READY.json", {"diagnostic": worker_terminal, "invocation_state": state, "repair_deadline_epoch": repair_deadline})
            while time.time() < repair_deadline and not (ARTIFACTS / "REPAIR_REQUEST.json").is_file(): time.sleep(5)
            raise RuntimeError("preinvocation_repair_request_absent")
        copy_from(ip, f"{REMOTE}/compact.tar.gz", ARTIFACTS / "compact.tar.gz", 300)
        copy_from(ip, f"{REMOTE}/compact.tar.gz.sha256", ARTIFACTS / "compact.tar.gz.sha256", 60)
        if digest(ARTIFACTS / "compact.tar.gz") != (ARTIFACTS / "compact.tar.gz.sha256").read_text().split()[0]: raise RuntimeError("compact_hash_mismatch")
        with tarfile.open(ARTIFACTS / "compact.tar.gz", "r:gz") as archive: archive.extractall(ARTIFACTS / "retrieved", filter="data")
        result = ARTIFACTS / "retrieved/ENDPOINT_RESULT.json"
        if not result.is_file(): raise RuntimeError("missing_endpoint_terminal_after_scientific_invocation")
        terminal = json.loads(result.read_text()); terminal.update({"provider_exposure_seconds":time.monotonic()-started, "provider_spend_usd":(time.monotonic()-started)*RATE/3600, "project_cumulative_spend_usd":PRIOR_SPEND+(time.monotonic()-started)*RATE/3600})
        atomic(ARTIFACTS / "FINAL_TERMINAL.json", terminal)
        status("E4M3 candidate terminal persisted.", "Hand off the retrieved E4M3 terminal to the dependent FA3 project.", terminal["project_cumulative_spend_usd"], None)
        return 0 if terminal.get("pass") else 1
    except Exception as exc:
        exposure = time.monotonic()-started if claimed else 0.0
        terminal = {"schema_version":1,"status":"terminal","classification":"typed_external_or_integration_boundary","pass":False,"error":{"type":type(exc).__name__,"message":str(exc)},"provider_exposure_seconds":exposure,"provider_spend_usd":exposure*RATE/3600,"project_cumulative_spend_usd":PRIOR_SPEND+exposure*RATE/3600}
        atomic(ARTIFACTS / "FINAL_TERMINAL.json", terminal)
        status("E4M3 owner ended at a typed boundary; see final terminal and remote diagnostics.", "Director disposition required only if the typed boundary is not an ordinary retained-session repair.", terminal["project_cumulative_spend_usd"], None)
        return 1
    finally:
        if pulse: pulse.stop.set(); pulse.join(5)
        if claimed:
            contents = {"project":PROJECT,"model":"google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4","checkpoint":"Exact lab-owned manifest-verified checkpoint retained read-only.","image":"Pinned SGLang v0.5.13 digest 6113665a retained.","caches":"Triton/CUDA graph caches retained.","runtime":f"E4M3 direct endpoint terminal: {(terminal or {}).get('classification','owner_failure')}.","server_state":"Healthy E4M3 Triton candidate server retained when it reached readiness.","artifacts":str(ARTIFACTS)}
            atomic(ARTIFACTS / "BENCH_CONTENTS.json", contents)
            pool.release(PROJECT, condition="ready", contents=contents)

if __name__ == "__main__": raise SystemExit(main())
