#!/usr/bin/env python3
"""Bounded Nebius H100 placement smoke with fail-closed cleanup."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any


NEBIUS = Path("/root/.nebius/bin/nebius")
PROFILE = "glm-campaign"
PROJECT_ID = "project-e00h1vhmpr00vbmfd5k7pg"
SUBNET_ID = "vpcsubnet-e00gr2f2ydymwjmr4f"
PLATFORM = "gpu-h100-sxm"
PRESET = "1gpu-16vcpu-200gb"
IMAGE_FAMILY = "ubuntu24.04-cuda13.0"
HOURLY_RATE_USD = 2.95
ABSOLUTE_TIMEOUT_SECONDS = 900
READY_TIMEOUT_SECONDS = 600
SSH_USER = "glmrunner"


class PlacementError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def conservative_cost_usd(seconds: float) -> float:
    return seconds / 3600 * HOURLY_RATE_USD


def build_create_command(*, name: str, disk_name: str, cloud_init: str, disk_gib: int = 100) -> list[str]:
    network = json.dumps(
        [{
            "name": "default-subnet",
            "subnet_id": SUBNET_ID,
            "ip_address": {},
            "public_ip_address": {"static": False},
        }],
        separators=(",", ":"),
    )
    return [
        str(NEBIUS), "compute", "instance", "create",
        "--profile", PROFILE,
        "--format", "json",
        "--no-progress",
        "--timeout", "2m",
        "--parent-id", PROJECT_ID,
        "--name", name,
        "--hostname", name,
        "--resources-platform", PLATFORM,
        "--resources-preset", PRESET,
        "--recovery-policy", "fail",
        "--reservation-policy-policy", "auto",
        "--boot-disk-attach-mode", "read_write",
        "--boot-disk-managed-disk-name", disk_name,
        "--boot-disk-managed-disk-size-gibibytes", str(disk_gib),
        "--boot-disk-managed-disk-type", "network_ssd",
        "--boot-disk-managed-disk-source-image-family-image-family", IMAGE_FAMILY,
        "--network-interfaces", network,
        "--cloud-init-user-data", cloud_init,
    ]


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def extract_instance_id(payload: Any) -> str:
    for value in _walk(payload):
        if isinstance(value, str) and value.startswith("computeinstance-"):
            return value
    raise PlacementError("create response did not contain a compute instance ID")


def extract_public_ipv4(payload: Any) -> str | None:
    for value in _walk(payload):
        if not isinstance(value, dict):
            continue
        public = value.get("public_ip_address")
        if not isinstance(public, dict):
            continue
        for candidate in public.values():
            if not isinstance(candidate, str):
                continue
            plain_candidate = candidate.split("/", 1)[0]
            try:
                address = ipaddress.ip_address(plain_candidate)
            except ValueError:
                continue
            if address.version == 4 and not address.is_private:
                return plain_candidate
    return None


def validate_gpu_csv(text: str) -> dict[str, Any]:
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    if len(rows) != 1:
        raise ValueError(f"expected exactly one GPU, found {len(rows)}")
    fields = [field.strip() for field in rows[0].split(",")]
    if len(fields) < 7:
        raise ValueError("GPU telemetry row is incomplete")
    name, memory, mig, driver, utilization, memory_used, power = fields[:7]
    if "H100" not in name:
        raise ValueError(f"expected H100, got {name}")
    if mig.lower() not in {"disabled", "n/a", "not supported"}:
        raise ValueError(f"MIG must be disabled, got {mig}")
    memory_mib = int(float(memory))
    if memory_mib < 80000:
        raise ValueError(f"expected at least 80000 MiB, got {memory_mib}")
    return {
        "gpu_count": 1,
        "name": name,
        "memory_mib": memory_mib,
        "mig_mode": mig,
        "driver_version": driver,
        "utilization_gpu_percent": float(utilization),
        "memory_used_mib": float(memory_used),
        "power_draw_w": float(power),
    }


def cli(args: list[str], *, timeout: int = 90, check: bool = True) -> tuple[int, Any, str]:
    command = [str(NEBIUS), *args, "--profile", PROFILE, "--format", "json", "--no-progress"]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    parsed = None
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            parsed = None
    if check and proc.returncode:
        # Do not persist provider stderr: it may contain request metadata.
        raise PlacementError(f"Nebius command failed ({args[:3]}) with exit {proc.returncode}")
    return proc.returncode, parsed, proc.stderr


def list_items(kind: str) -> list[dict[str, Any]]:
    _, payload, _ = cli(["compute", kind, "list", "--parent-id", PROJECT_ID, "--all"])
    if isinstance(payload, dict):
        for key in ("items", "instances", "disks"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return payload if isinstance(payload, list) else []


def metadata_name(item: dict[str, Any]) -> str | None:
    metadata = item.get("metadata")
    return metadata.get("name") if isinstance(metadata, dict) else item.get("name")


def metadata_id(item: dict[str, Any]) -> str | None:
    metadata = item.get("metadata")
    return metadata.get("id") if isinstance(metadata, dict) else item.get("id")


def get_instance(instance_id: str) -> Any | None:
    code, payload, _ = cli(
        ["compute", "instance", "get", "--id", instance_id], check=False, timeout=30
    )
    return payload if code == 0 else None


def delete_instance(instance_id: str) -> None:
    cli(["compute", "instance", "delete", "--id", instance_id], timeout=120, check=False)


def delete_disk(disk_id: str) -> None:
    cli(["compute", "disk", "delete", "--id", disk_id], timeout=120, check=False)


def find_named_instance(name: str) -> str | None:
    for item in list_items("instance"):
        if metadata_name(item) == name:
            return metadata_id(item)
    return None


def wait_absent(instance_id: str, deadline: float) -> bool:
    while time.time() < deadline:
        if get_instance(instance_id) is None:
            return True
        time.sleep(5)
    return False


def make_cloud_init(public_key: str) -> str:
    return "\n".join([
        "#cloud-config",
        "users:",
        f"  - name: {SSH_USER}",
        "    groups: [sudo]",
        "    shell: /bin/bash",
        "    sudo: ALL=(ALL) NOPASSWD:ALL",
        "    ssh_authorized_keys:",
        f"      - {public_key.strip()}",
        "ssh_pwauth: false",
        "disable_root: true",
        "package_update: false",
        "runcmd:",
        "  - [sh, -c, 'date -u +%FT%TZ > /var/tmp/glm-cloud-init-ready']",
        "",
    ])


REMOTE_SCRIPT = r'''set -euo pipefail
umask 077
out=/tmp/glm-nebius-evidence
rm -rf "$out"
mkdir -p "$out"
date -u +%FT%TZ > "$out/collected_at_utc.txt"
uname -a > "$out/uname.txt"
cat /etc/os-release > "$out/os-release.txt"
nvidia-smi --query-gpu=name,memory.total,mig.mode.current,driver_version,utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits > "$out/gpu.csv"
nvidia-smi -q > "$out/nvidia-smi-q.txt"
(nvcc --version || true) > "$out/nvcc.txt" 2>&1
test -f /var/tmp/glm-cloud-init-ready && cp /var/tmp/glm-cloud-init-ready "$out/cloud-init-ready.txt"
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf /tmp/glm-nebius-evidence.tar.gz -C /tmp glm-nebius-evidence
sha256sum /tmp/glm-nebius-evidence.tar.gz > /tmp/glm-nebius-evidence.tar.gz.sha256
cat /tmp/glm-nebius-evidence.tar.gz.sha256
'''


def ssh_base(ip: str, key_path: Path) -> list[str]:
    return [
        "ssh", "-i", str(key_path),
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts",
        "-o", "ConnectTimeout=10",
        f"{SSH_USER}@{ip}",
    ]


def wait_ssh(ip: str, key_path: Path, deadline: float) -> None:
    while time.time() < deadline:
        proc = subprocess.run(
            [*ssh_base(ip, key_path), "test -f /var/tmp/glm-cloud-init-ready"],
            capture_output=True, text=True, timeout=20,
        )
        if proc.returncode == 0:
            return
        time.sleep(8)
    raise PlacementError("SSH/cloud-init readiness SLO exceeded")


def watchdog(instance_id: str, disk_name: str, deadline_epoch: float) -> int:
    while time.time() < deadline_epoch:
        if get_instance(instance_id) is None:
            return 0
        time.sleep(10)
    delete_instance(instance_id)
    wait_absent(instance_id, time.time() + 180)
    for disk in list_items("disk"):
        if metadata_name(disk) == disk_name and metadata_id(disk):
            delete_disk(metadata_id(disk))
    return 0


def emit(path: Path, event: str, **fields: Any) -> None:
    row = {"timestamp": utc_now(), "event": event, **fields}
    with path.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def run(output_dir: Path, name: str, key_path: Path, public_key_path: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "summary.json").exists() or (output_dir / "events.jsonl").exists():
        raise PlacementError("output directory already contains a prior run")
    events = output_dir / "events.jsonl"
    started = time.time()
    deadline = started + ABSOLUTE_TIMEOUT_SECONDS
    instance_id = None
    disk_name = name + "-boot"
    initial_instances = list_items("instance")
    initial_disks = list_items("disk")
    if initial_instances:
        raise PlacementError("stock control failed: project already has active instances")
    if find_named_instance(name):
        raise PlacementError("stock control failed: experiment name already exists")
    emit(events, "stock_control", instance_count=len(initial_instances), disk_count=len(initial_disks))
    cloud_init = make_cloud_init(public_key_path.read_text())
    create_command = build_create_command(name=name, disk_name=disk_name, cloud_init=cloud_init)
    sanitized_request = {
        "name": name,
        "project_id": PROJECT_ID,
        "subnet_id": SUBNET_ID,
        "platform": PLATFORM,
        "preset": PRESET,
        "image_family": IMAGE_FAMILY,
        "boot_disk_gib": 100,
        "boot_disk_type": "network_ssd",
        "regular_on_demand": True,
        "hourly_rate_usd_vendor_list": HOURLY_RATE_USD,
        "absolute_timeout_seconds": ABSOLUTE_TIMEOUT_SECONDS,
    }
    (output_dir / "request.json").write_text(json.dumps(sanitized_request, indent=2, sort_keys=True) + "\n")
    outcome = "FAIL"
    try:
        proc = subprocess.run(create_command, capture_output=True, text=True, timeout=150)
        if proc.returncode:
            raise PlacementError(f"instance create failed with exit {proc.returncode}")
        try:
            create_payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise PlacementError("instance create returned invalid JSON") from exc
        instance_id = extract_instance_id(create_payload)
        emit(events, "instance_created", instance_id=instance_id)
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "watchdog", instance_id, disk_name, str(deadline)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        public_ip = None
        latest = None
        while time.time() < min(deadline, started + READY_TIMEOUT_SECONDS):
            latest = get_instance(instance_id)
            if latest is None:
                raise PlacementError("instance disappeared before readiness")
            public_ip = extract_public_ipv4(latest)
            if public_ip:
                break
            time.sleep(5)
        if not public_ip:
            raise PlacementError("public IPv4 readiness SLO exceeded")
        emit(events, "public_ip_ready", elapsed_seconds=round(time.time() - started, 3))
        wait_ssh(public_ip, key_path, min(deadline, started + READY_TIMEOUT_SECONDS))
        ssh_ready = time.time()
        emit(events, "ssh_ready", elapsed_seconds=round(ssh_ready - started, 3))
        remote = subprocess.run(
            [*ssh_base(public_ip, key_path), "bash -s"],
            input=REMOTE_SCRIPT, capture_output=True, text=True, timeout=120,
        )
        if remote.returncode:
            raise PlacementError("remote telemetry command failed")
        remote_hash = remote.stdout.strip().split()[0]
        archive = output_dir / "remote-evidence.tar.gz"
        scp = subprocess.run(
            ["scp", "-i", str(key_path), "-o", "BatchMode=yes",
             "-o", "StrictHostKeyChecking=accept-new",
             "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts",
             f"{SSH_USER}@{public_ip}:/tmp/glm-nebius-evidence.tar.gz", str(archive)],
            capture_output=True, text=True, timeout=120,
        )
        if scp.returncode:
            raise PlacementError("artifact retrieval failed")
        local_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        if local_hash != remote_hash:
            raise PlacementError("retrieved artifact hash mismatch")
        with tempfile.TemporaryDirectory() as directory:
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(directory, filter="data")
            gpu_csv = Path(directory, "glm-nebius-evidence", "gpu.csv").read_text()
        gate = validate_gpu_csv(gpu_csv)
        (output_dir / "quality-gate.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n")
        (output_dir / "remote-evidence.sha256").write_text(local_hash + "  remote-evidence.tar.gz\n")
        emit(events, "evidence_hashed", sha256=local_hash, gate_pass=True)
        outcome = "PASS"
    except Exception as exc:
        outcome = "FAIL"
        emit(events, "experiment_error", error_type=type(exc).__name__, message=str(exc))
    finally:
        if instance_id is None:
            try:
                instance_id = find_named_instance(name)
            except Exception:
                instance_id = None
        delete_requested = time.time()
        if instance_id:
            delete_instance(instance_id)
            absent = wait_absent(instance_id, time.time() + 180)
        else:
            absent = True
        for disk in list_items("disk"):
            if metadata_name(disk) == disk_name and metadata_id(disk):
                delete_disk(metadata_id(disk))
        final_instances = list_items("instance")
        final_disks = list_items("disk")
        cleanup_pass = absent and not any(metadata_name(x) == name for x in final_instances) and not any(
            metadata_name(x) == disk_name for x in final_disks
        )
        ended = time.time()
        summary = {
            "outcome": outcome,
            "cleanup_pass": cleanup_pass,
            "instance_id": instance_id,
            "started_at_utc": dt.datetime.fromtimestamp(started, dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "ended_at_utc": dt.datetime.fromtimestamp(ended, dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "allocation_elapsed_seconds": round(delete_requested - started, 3),
            "cleanup_elapsed_seconds": round(ended - delete_requested, 3),
            "conservative_cost_usd": round(conservative_cost_usd(delete_requested - started), 9),
            "rate_basis": "vendor list price; elapsed exposure is measured, provider invoice pending",
            "final_instance_count": len(final_instances),
            "final_disk_count": len(final_disks),
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        emit(events, "cleanup_verified", cleanup_pass=cleanup_pass, instance_get_not_found=absent)
    return 0 if outcome == "PASS" and cleanup_pass else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--output-dir", type=Path, required=True)
    run_parser.add_argument("--name", required=True)
    run_parser.add_argument("--ssh-key", type=Path, required=True)
    run_parser.add_argument("--ssh-public-key", type=Path, required=True)
    watchdog_parser = sub.add_parser("watchdog")
    watchdog_parser.add_argument("instance_id")
    watchdog_parser.add_argument("disk_name")
    watchdog_parser.add_argument("deadline_epoch", type=float)
    args = parser.parse_args()
    if args.command == "watchdog":
        return watchdog(args.instance_id, args.disk_name, args.deadline_epoch)
    return run(args.output_dir, args.name, args.ssh_key, args.ssh_public_key)


if __name__ == "__main__":
    raise SystemExit(main())
