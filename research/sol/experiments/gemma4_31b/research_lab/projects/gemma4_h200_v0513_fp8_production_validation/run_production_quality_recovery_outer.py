#!/usr/bin/env python3
"""Durable claim owner for the single paired production-quality validation."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import threading
import time

LAB = pathlib.Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
PROJECT = LAB / "projects/gemma4_h200_v0513_fp8_production_validation"
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
TOOLS = pathlib.Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
BENCH = "h200-v0513-quality-e00wmzg4fqzrqgabek"
PROJECT_NAME = "gemma4_h200_v0513_fp8_production_validation"
REMOTE = "/home/glmrunner/gemma-v0513-quality-recovery"
CHECKPOINT = PROJECT / "inputs" / "checkpoint"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
MODEL = "google/gemma-4-31B-it"
RATE = 2.46


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def pool(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args], env={**os.environ, "PYTHONPATH": str(FACTORY)}, capture_output=True, text=True, check=check)


def scp(ip: str, source: str, destination: str, recursive: bool = False, timeout: int = 900) -> None:
    cmd = ["scp", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN}"]
    if recursive: cmd.append("-r")
    cmd += [source, f"glmrunner@{ip}:{destination}"] if destination.startswith("/") and source.startswith("/") is False else [source, destination]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode: raise RuntimeError(f"scp_failed:{result.stderr[-1000:]}")


def upload(ip: str, local: pathlib.Path, remote: str) -> None:
    cmd = ["scp", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN}", str(local), f"glmrunner@{ip}:{remote}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if result.returncode: raise RuntimeError(f"upload_failed:{local.name}:{result.stderr[-1000:]}")


def retrieve(ip: str, remote: str, local: pathlib.Path, recursive: bool = False, timeout: int = 900) -> None:
    local.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["scp", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN}"]
    if recursive: cmd.append("-r")
    cmd += [f"glmrunner@{ip}:{remote}", str(local)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode: raise RuntimeError(f"retrieve_failed:{remote}:{result.stderr[-1000:]}")


def transfer_checkpoint(ip: str) -> None:
    """Transfer the already verified immutable local snapshot to the cold bench."""
    remote_dir = f"{REMOTE}/checkpoint"
    subprocess.run(["ssh", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN}", f"glmrunner@{ip}", f"mkdir -p {remote_dir}"], check=True, capture_output=True, text=True, timeout=120)
    command = ["ssh", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN}", f"glmrunner@{ip}", f"tar -C {remote_dir} -xf -"]
    tar = subprocess.Popen(["tar", "-C", str(CHECKPOINT), "-cf", "-", "."], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    receiver = subprocess.run(command, stdin=tar.stdout, capture_output=True, timeout=2400)
    assert tar.stdout is not None; tar.stdout.close(); tar_stderr = tar.communicate(timeout=120)[1]
    if receiver.returncode or tar.returncode:
        raise RuntimeError(f"checkpoint_transfer_failed:{(receiver.stderr + tar_stderr)[-1000:].decode(errors='replace')}")


def remote(ip: str, command: str, timeout: int = 900) -> subprocess.CompletedProcess:
    from stock_control import run_ssh
    return run_ssh(ip, KEY, command, timeout=timeout)


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--artifact-root", type=pathlib.Path, required=True); ap.add_argument("--absolute-deadline-epoch", type=int, required=True); ap.add_argument("--unit", required=True); ap.add_argument("--resume-control", action="store_true"); args = ap.parse_args()
    if not os.getenv("INVOCATION_ID"):
        raise RuntimeError("durable_user_systemd_owner_required")
    root = args.artifact_root.resolve(); root.mkdir(parents=True, exist_ok=False)
    events = root / "events.jsonl"; claimed = False; ip = None; started = time.time(); terminal = None; stop_hb = threading.Event()
    status_path = PROJECT / "STATUS.json"
    status = json.loads(status_path.read_text())
    status["active_session"] = {"unit": args.unit, "unit_manager": "user", "pid": os.getpid(), "artifact_root": str(root), "deadline_utc": dt.datetime.fromtimestamp(args.absolute_deadline_epoch, dt.timezone.utc).isoformat().replace("+00:00", "Z"), "expected_terminal": "TERMINAL.json", "started_at_utc": now(), "forward_progress": "claim_pending"}
    atomic(status_path, status)

    def event(name: str, **fields: object) -> None:
        with events.open("a") as f: f.write(json.dumps({"timestamp": now(), "event": name, **fields}, sort_keys=True) + "\n")

    def heartbeat() -> None:
        while not stop_hb.wait(45):
            result = pool("heartbeat", "--project", PROJECT_NAME, check=False); event("heartbeat", returncode=result.returncode)

    hb = threading.Thread(target=heartbeat, daemon=True)
    try:
        inventory = json.loads((LAB / "runtime/gpus.json").read_text()); bench = inventory["benches"][BENCH]
        if bench.get("status") != "available": raise RuntimeError("bench_not_available")
        if time.time() + 15 * 60 >= args.absolute_deadline_epoch: raise RuntimeError("retrieval_reserve_deadline")
        claim = pool("claim", "--project", PROJECT_NAME, "--bench", BENCH, "--lease-seconds", str(min(6000, args.absolute_deadline_epoch - int(time.time()))))
        claimed = True; event("claimed", claim=json.loads(claim.stdout)); status["active_session"]["forward_progress"] = "bench_claimed"; atomic(status_path, status); hb.start()
        sys.path.insert(0, str(TOOLS)); from placement_control import extract_public_ipv4, get_instance
        provider = get_instance(bench["resource"]["instance_id"]); ip = extract_public_ipv4(provider)
        if not ip: raise RuntimeError("public_ip_unavailable")
        subprocess.run(["ssh-keygen", "-R", ip, "-f", str(KNOWN)], capture_output=True, check=False)
        ident = remote(ip, "hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker image inspect '" + IMAGE + "' >/dev/null 2>&1 || true", 90)
        (root / "remote-identity.stdout").write_text(ident.stdout); (root / "remote-identity.stderr").write_text(ident.stderr)
        if ident.returncode: raise RuntimeError("remote_identity_failed")
        remote(ip, f"mkdir -p {REMOTE}/quality-input {REMOTE}/quality-artifacts/run", 60)
        status["active_session"]["forward_progress"] = "checkpoint_verify" if args.resume_control else "checkpoint_transfer"; atomic(status_path, status)
        if not args.resume_control:
            transfer_checkpoint(ip)
        checkpoint_check = remote(ip, f"test \"$(sha256sum {REMOTE}/checkpoint/model.safetensors.index.json | awk '{{print $1}}')\" = d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2", 180)
        if checkpoint_check.returncode: raise RuntimeError("checkpoint_identity_mismatch")
        if args.resume_control:
            image_pull = remote(ip, f"sudo docker image inspect {IMAGE}", 120)
        else:
            image_pull = remote(ip, f"sudo docker pull {IMAGE}", 1800)
        (root / "image-pull.stdout").write_text(image_pull.stdout); (root / "image-pull.stderr").write_text(image_pull.stderr)
        if image_pull.returncode: raise RuntimeError("pinned_image_unavailable")
        status["active_session"]["forward_progress"] = "checkpoint_and_image_verified"; atomic(status_path, status)
        stage = [PROJECT / "production_quality_remote.py", PROJECT / "BINDINGS.json", PROJECT / "assets/source/gpqa/gpqa_diamond.csv", PROJECT / "assets/source/tau_bench/airline_tasks.py", PROJECT / "assets/source/tau_bench/retail_tasks.py", PROJECT.parent / "gemma4_h200_qkv_epilogue_fusion/proven_v0513_endpoint_entrypoint.py"]
        for source in ([PROJECT / "production_quality_remote.py"] if args.resume_control else stage):
            upload(ip, source, f"{REMOTE}/quality-input/{source.name}")
        remote(ip, f"test -r {REMOTE}/checkpoint/model.safetensors.index.json && sha256sum {REMOTE}/quality-input/production_quality_remote.py {REMOTE}/quality-input/BINDINGS.json", 90)
        status["active_session"]["forward_progress"] = "inputs_staged"; atomic(status_path, status)
        worker_timeout = max(60, args.absolute_deadline_epoch - int(time.time()) - 600)
        resume = " --resume-control" if args.resume_control else ""
        worker = remote(ip, f"QUALITY_ROOT={REMOTE} timeout --signal=TERM {worker_timeout} python3 {REMOTE}/quality-input/production_quality_remote.py --root {REMOTE}/quality-artifacts/run{resume}", worker_timeout + 60)
        (root / "remote-worker.stdout").write_text(worker.stdout); (root / "remote-worker.stderr").write_text(worker.stderr); event("worker_complete", returncode=worker.returncode)
        retrieve(ip, f"{REMOTE}/quality-artifacts/run", root / "remote-quality", recursive=True, timeout=1200)
        if (root / "remote-quality/TERMINAL.json").is_file(): terminal = json.loads((root / "remote-quality/TERMINAL.json").read_text())
        else: terminal = {"classification": "worker_terminal_missing", "pass": False}
        terminal["provider_exposure_seconds"] = time.time() - started; terminal["provider_spend_usd"] = terminal["provider_exposure_seconds"] * RATE / 3600; terminal["project_cumulative_spend_usd"] = terminal["provider_spend_usd"]
        atomic(root / "TERMINAL.json", terminal); event("terminal_persisted", classification=terminal.get("classification"), passed=terminal.get("pass"))
        return 0 if terminal.get("pass") else 1
    except Exception as exc:
        terminal = {"schema_version": 1, "classification": "owner_failure", "pass": False, "error": {"type": type(exc).__name__, "message": str(exc)[:4000]}, "provider_exposure_seconds": time.time() - started if claimed else 0}
        terminal["provider_spend_usd"] = terminal["provider_exposure_seconds"] * RATE / 3600; atomic(root / "TERMINAL.json", terminal); event("outer_error", error=str(exc)); return 1
    finally:
        stop_hb.set()
        if hb.is_alive(): hb.join(timeout=5)
        if claimed:
            contents = root / "BENCH_CONTENTS.json"; atomic(contents, {"project": PROJECT_NAME, "model": MODEL, "checkpoint": f"Exact immutable eight-file checkpoint staged at {REMOTE}/checkpoint.", "image": f"SGLang v0.5.13 image {IMAGE}.", "runtime": f"Paired BF16/FP8 production quality terminal: {(terminal or {}).get('classification', 'owner_failure')}.", "caches": "SGLang v0.5.13 and CUDA graph caches retained.", "server_state": "No quality server retained; checkpoint/image/caches retained.", "artifacts": "Paired raw captures, tool traces, feature/NLL results, and terminal retrieved project-locally."})
            release = pool("release", "--project", PROJECT_NAME, "--condition", "ready", "--contents", str(contents), check=False); event("released", returncode=release.returncode)
        status = json.loads(status_path.read_text()); status["active_session"] = None; status["last_terminal"] = str(root / "TERMINAL.json"); atomic(status_path, status)


if __name__ == "__main__":
    raise SystemExit(main())
