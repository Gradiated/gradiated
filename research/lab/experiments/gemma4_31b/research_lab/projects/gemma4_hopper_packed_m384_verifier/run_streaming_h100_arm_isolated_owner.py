#!/usr/bin/env python3
"""One-shot retained controller for the director-bound arm-isolated H100 run."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parent
LAB = ROOT.parent.parent
PROJECT = "gemma4_hopper_packed_m384_verifier"
MANIFEST = ROOT / "STREAMING_H100_ARM_ISOLATED_INPUT_MANIFEST.json"
READY = ROOT / "PACKED_M384_STREAMING_ARM_ISOLATED_H100_READY.json"
IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
IDENTITY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN_HOSTS = Path("/root/.config/nebius/glm-campaign/known_hosts")


def utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def run(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout)


def pool(bench: str, action: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), action, "--project", PROJECT, "--bench", bench, *extra], 60)


def ssh(user: str, host: str) -> list[str]:
    return ["ssh", "-i", str(IDENTITY), "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes", f"{user}@{host}"]


def row_for(bench: str) -> dict:
    benches = json.loads((LAB / "runtime/gpus.json").read_text())["benches"]
    row = benches[bench] if isinstance(benches, dict) else next(item for item in benches if item["id"] == bench)
    if row.get("status") != "claimed" or (row.get("claim") or {}).get("project") != PROJECT:
        raise RuntimeError("bound_claim_not_owned")
    if row.get("accelerator") != "nvidia-h100-sxm" or row.get("provider") != "nebius":
        raise RuntimeError("bound_h100_required")
    return row


def heartbeat(bench: str, stop: threading.Event, root: Path) -> None:
    while not stop.wait(60):
        done = pool(bench, "heartbeat")
        atomic(root / "OWNER_HEARTBEAT.json", {"at_utc": utc(), "exit": done.returncode, "stderr": done.stderr[-1000:]})


def stage(user: str, host: str, output: Path) -> tuple[str, str]:
    manifest = json.loads(MANIFEST.read_text())
    for entry in manifest["files"]:
        source = ROOT / entry["source"]
        if not source.is_file() or source.stat().st_size != entry["bytes"] or digest(source) != entry["sha256"]:
            raise RuntimeError(f"manifest_mismatch:{entry['path']}")
    archive = output / "packet.tar"
    packed = run(["/root/workspace/research/factory/tools/manifest-pack", "--root", str(ROOT), "--manifest", str(MANIFEST), "--archive", str(archive)], 180)
    if packed.returncode:
        raise RuntimeError(f"packet_pack_failed:{packed.stderr[-1000:]}")
    remote = f"/home/{user}/{PROJECT}-arm-isolated"
    packet = f"{remote}/packet-{digest(MANIFEST)}"
    temporary = packet + ".tmp"
    prepared = run(ssh(user, host) + [f"mkdir -p {shlex.quote(remote)}"], 120)
    if prepared.returncode:
        raise RuntimeError(f"remote_root_prepare_failed:{prepared.stderr[-1000:]}")
    copied = run(["scp", "-i", str(IDENTITY), "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes", str(archive), f"{user}@{host}:{temporary}.tar"], 300)
    if copied.returncode:
        raise RuntimeError(f"packet_copy_failed:{copied.stderr[-1000:]}")
    install = f"mkdir -p {shlex.quote(remote)}; rm -rf {shlex.quote(temporary)}; mkdir {shlex.quote(temporary)}; tar -xf {shlex.quote(temporary)}.tar -C {shlex.quote(temporary)}; test ! -e {shlex.quote(packet)} && mv -T {shlex.quote(temporary)} {shlex.quote(packet)}"
    done = run(ssh(user, host) + [install], 300)
    if done.returncode:
        raise RuntimeError(f"packet_install_failed:{done.stderr[-1000:]}")
    return remote, packet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--authorization", required=True, type=Path)
    parser.add_argument("--deadline-utc", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    deadline = dt.datetime.fromisoformat(args.deadline_utc.replace("Z", "+00:00"))
    output = args.output_dir
    authorization = json.loads(args.authorization.read_text())
    ready = json.loads(READY.read_text())
    if authorization.get("type") != "director_hopper_packed_streaming_arm_isolated_retry" or ready.get("owner", {}).get("sha256") != digest(Path(__file__)) or ready.get("runner", {}).get("sha256") != digest(ROOT / "arm_isolated_accuracy_component_runner.py") or ready.get("input_manifest", {}).get("sha256") != digest(MANIFEST):
        raise RuntimeError("binding_not_ready")
    row = row_for(args.bench)
    if dt.datetime.now(dt.UTC) >= deadline:
        raise RuntimeError("absolute_deadline_elapsed")
    user, host = row["resource"]["ssh_user"], row["resource"]["public_ipv4"]
    state = output / "OWNER_PROGRESS.json"
    atomic(state, {"at_utc": utc(), "phase": "owner_started", "bench": args.bench, "claimed_at": row["claim"]["claimed_at"], "deadline_utc": args.deadline_utc})
    stop = threading.Event()
    thread = threading.Thread(target=heartbeat, args=(args.bench, stop, output), daemon=True)
    thread.start()
    terminal = {"bench": args.bench, "claimed_at": row["claim"]["claimed_at"], "started_at_utc": utc()}
    try:
        remote, packet = stage(user, host, output)
        remaining = int((deadline - dt.datetime.now(dt.UTC)).total_seconds()) - 300
        if remaining <= 0:
            raise RuntimeError("insufficient_time_for_bound_run_and_retrieval")
        artifact = remote + "/artifacts/arm-isolated"
        command = f"sudo -n docker run --rm --gpus all --ipc=host --entrypoint python3 -v {shlex.quote(packet + ':/project:ro')} -v {shlex.quote(remote + ':/run')} {shlex.quote(IMAGE)} /project/arm_isolated_accuracy_component_runner.py --artifact-root /run/artifacts/arm-isolated --source /project/packed_m384_streaming_cluster.cu --source-sha256 2262a4a20e9438671f795eeb8aad7f5db9cbe65ae446a94758e3d4c1cce78656 --control /project/inputs/source/extend_attention.py --repetitions 25 --seed 20260726"
        atomic(state, {"at_utc": utc(), "phase": "runner_launch_attempted", "remote": remote, "packet": packet})
        worker = run(ssh(user, host) + [f"mkdir -p {shlex.quote(artifact)}; {command} > {shlex.quote(artifact)}/stdout.log 2> {shlex.quote(artifact)}/stderr.log"], remaining)
        terminal.update({"worker_exit": worker.returncode, "ssh_stdout": worker.stdout[-2000:], "ssh_stderr": worker.stderr[-2000:]})
        fetched = run(["scp", "-r", "-i", str(IDENTITY), "-o", "BatchMode=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes", f"{user}@{host}:{artifact}/.", str(output)], 300)
        if fetched.returncode:
            raise RuntimeError(f"retrieval_failed:{fetched.stderr[-1000:]}")
        result_path = output / "PACKED_M384_STREAMING_ARM_ISOLATED_RESULT.json"
        terminal["result"] = json.loads(result_path.read_text())
        terminal["classification"] = terminal["result"]["result"]
        atomic(output / "STREAMING_H100_ARM_ISOLATED_OWNER_TERMINAL.json", terminal)
        contents = json.dumps({"project": PROJECT, "artifacts": str(output), "result": terminal["classification"], "server_state": "No server retained; preserve image, packet, and compiler cache."})
        released = pool(args.bench, "release", "--condition", "ready", "--contents", contents)
        terminal["release_exit"] = released.returncode
        atomic(output / "STREAMING_H100_ARM_ISOLATED_OWNER_TERMINAL.json", terminal)
        return 0
    finally:
        stop.set()


if __name__ == "__main__":
    raise SystemExit(main())
