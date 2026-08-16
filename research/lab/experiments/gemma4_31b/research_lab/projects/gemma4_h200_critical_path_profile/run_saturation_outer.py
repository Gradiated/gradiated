#!/usr/bin/env python3
"""One claimed-H200 c32/c48/c64 saturation discriminator with atomic arm retrieval."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import threading
import time

LAB = pathlib.Path("/root/workspace/research/lab/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects/gemma4_h200_critical_path_profile"
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
NEBIUS = pathlib.Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
BENCH = "h200-kernel-frontier-e00pfvrckjvwn7bhet"
NAME = "gemma4_h200_critical_path_profile"
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
REMOTE = "/home/glmrunner/gemma-critical-path-saturation"
RATE = 2.46


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pool(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args], env={**os.environ, "PYTHONPATH": str(FACTORY)}, capture_output=True, text=True, check=check)


def main() -> int:
    stamp = time.strftime("%Y%m%dt%H%Mz", time.gmtime())
    root = PROJECT / "artifacts" / f"h200-saturation-{stamp}"
    root.mkdir(parents=True, exist_ok=False)
    started = time.time(); claimed = False; terminal: dict | None = None
    events = root / "outer-events.jsonl"
    def emit(event: str, **fields: object) -> None:
        with events.open("a") as handle: handle.write(json.dumps({"epoch": time.time(), "event": event, **fields}, sort_keys=True) + "\n")
    stop = threading.Event()
    def heartbeats() -> None:
        while not stop.wait(45):
            result = pool("heartbeat", "--project", NAME, check=False)
            emit("heartbeat", returncode=result.returncode, stderr=result.stderr[-800:])
    thread = threading.Thread(target=heartbeats, daemon=True)
    try:
        runner, remote = PROJECT / "endpoint_saturation_runner.py", PROJECT / "remote_saturation.sh"
        manifest = {path.name: digest(path) for path in (runner, remote)}
        atomic(root / "INPUT_MANIFEST.json", {"files": manifest})
        claim = pool("claim", "--project", NAME, "--bench", BENCH, "--lease-seconds", "2700")
        claimed = True; emit("claimed", stdout=claim.stdout.strip()); thread.start()
        inventory = json.loads((LAB / "runtime/gpus.json").read_text()); benches = inventory["benches"]
        bench = benches[BENCH] if isinstance(benches, dict) else next(item for item in benches if item["id"] == BENCH)
        sys.path.insert(0, str(NEBIUS))
        from placement_control import extract_public_ipv4, get_instance
        from stock_control import run_ssh, scp_from
        ip = extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
        if not ip: raise RuntimeError("typed_provider_boundary:no_public_ip")
        identity = run_ssh(ip, KEY, "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version", timeout=60)
        (root / "remote-identity.stdout").write_text(identity.stdout); (root / "remote-identity.stderr").write_text(identity.stderr)
        if identity.returncode: raise RuntimeError("typed_remote_boundary:ssh_identity_failed")
        prepare = run_ssh(ip, KEY, f"mkdir -p {REMOTE}/input {REMOTE}/artifacts", timeout=60)
        if prepare.returncode: raise RuntimeError("typed_remote_boundary:prepare_failed")
        scp = ["scp", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts", str(runner), str(remote), f"glmrunner@{ip}:{REMOTE}/input/"]
        copied = subprocess.run(scp, capture_output=True, text=True, timeout=300)
        if copied.returncode: raise RuntimeError(f"typed_transfer_boundary:scp_failed:{copied.stderr[-500:]}")
        hashes = run_ssh(ip, KEY, f"cd {REMOTE}/input && sha256sum endpoint_saturation_runner.py remote_saturation.sh", timeout=60)
        (root / "remote-input-sha256.txt").write_text(hashes.stdout)
        if hashes.returncode or any(value not in hashes.stdout for value in manifest.values()): raise RuntimeError("typed_transfer_boundary:input_hash_mismatch")
        rows = []
        for concurrency in (32, 48, 64):
            arm = f"c{concurrency}"
            worker = run_ssh(ip, KEY, f"timeout --signal=TERM 1800 bash {REMOTE}/input/remote_saturation.sh {arm} {concurrency}", timeout=1860)
            (root / f"{arm}.stdout").write_text(worker.stdout); (root / f"{arm}.stderr").write_text(worker.stderr)
            emit("worker", arm=arm, returncode=worker.returncode)
            compact = run_ssh(ip, KEY, f"cat {REMOTE}/artifacts/{arm}/exact-c{concurrency}/TERMINAL.json", timeout=60)
            (root / f"{arm}-compact-terminal.json").write_text(compact.stdout)
            if worker.returncode or compact.returncode or not compact.stdout.strip(): raise RuntimeError(f"typed_remote_boundary:{arm}_terminal_unavailable")
            row = json.loads(compact.stdout); rows.append(row)
            partial = root / f".{arm}.tar.gz.partial"; sidecar = root / f"{arm}.tar.gz.sha256"
            scp_from(ip, KEY, f"{REMOTE}/{arm}.tar.gz", partial); scp_from(ip, KEY, f"{REMOTE}/{arm}.tar.gz.sha256", sidecar)
            if digest(partial) != sidecar.read_text().split()[0]: raise RuntimeError(f"typed_retrieval_boundary:{arm}_hash_mismatch")
            archive = root / f"{arm}.tar.gz"; partial.replace(archive)
            with tarfile.open(archive, "r:gz") as bundle: bundle.extractall(root / arm, filter="data")
            atomic(root / "PARTIAL.json", {"rows": rows})
            if not row.get("pass"): break
        c32 = rows[0] if rows else {}
        stable = len(rows) == 3 and all(row.get("pass") for row in rows)
        improvements = {row["arm"]: 1 - row["service_seconds_per_request"] / c32["service_seconds_per_request"] for row in rows[1:]} if stable else {}
        promoted = [arm for arm, improvement in improvements.items() if improvement >= .10]
        classification = "promote" if stable and promoted else "negative_saturated" if stable else "invalid_or_incomplete"
        terminal = {"schema_version": 1, "status": "terminal", "classification": classification, "pass": stable, "promotion": {"stable": stable, "minimum_improvement": .10, "improvements_vs_c32": improvements, "promoted_arms": promoted}, "rows": rows, "provider_exposure_seconds": time.time() - started, "provider_spend_usd_conservative": (time.time() - started) * RATE / 3600}
        atomic(root / "TERMINAL.json", terminal); emit("terminal", classification=classification)
        return 0 if stable else 1
    except Exception as error:
        emit("outer_error", error_type=type(error).__name__, message=str(error))
        terminal = {"schema_version": 1, "status": "terminal", "classification": "owner_failure", "pass": False, "error": {"type": type(error).__name__, "message": str(error)}, "provider_exposure_seconds": time.time() - started, "provider_spend_usd_conservative": (time.time() - started) * RATE / 3600}
        atomic(root / "TERMINAL.json", terminal); return 1
    finally:
        stop.set(); thread.join(timeout=3)
        if claimed:
            contents = {"project": NAME, "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4", "checkpoint": "Exact immutable checkpoint retained at /home/glmrunner/gemma-kernel-frontier/checkpoint.", "image": "Pinned SGLang v0.5.12 image retained.", "caches": "Triton and CUDA-graph compilation caches retained.", "runtime": "Same-session exact-distinct c32/c48/c64 saturation terminal.", "server_state": "Healthy c64 BF16/FP8-E5M2 server retained when final arm completed.", "artifacts": f"Saturation terminal retrieved at {root}."}
            atomic(root / "BENCH_CONTENTS.json", contents)
            release = pool("release", "--project", NAME, "--condition", "ready" if terminal and terminal.get("classification") != "owner_failure" else "maintenance", "--contents", str(root / "BENCH_CONTENTS.json"), check=False)
            emit("released", returncode=release.returncode, stderr=release.stderr[-800:])


if __name__ == "__main__": raise SystemExit(main())
