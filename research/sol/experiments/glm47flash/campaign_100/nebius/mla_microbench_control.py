#!/usr/bin/env python3
"""Create, measure, retrieve, and destroy one bounded Nebius MLA microbenchmark VM."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from awq_smoke_control import emit  # noqa: E402
from placement_control import (  # noqa: E402
    build_create_command,
    delete_disk,
    delete_instance,
    extract_instance_id,
    extract_public_ipv4,
    find_named_instance,
    get_instance,
    list_items,
    make_cloud_init,
    metadata_id,
    metadata_name,
    wait_absent,
    wait_ssh,
)
from stock_control import run_ssh, scp_from, scp_to, verify_internal_manifest  # noqa: E402


IMAGE = "vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543"
PLATFORM = "gpu-l40s-a"
PRESET = "1gpu-8vcpu-32gb"
DISK_GIB = 100
HOURLY_RATE_USD = 0.7492
DISK_HOURLY_RATE_USD = 0.0097222
ABSOLUTE_TIMEOUT_SECONDS = 2700


class MicrobenchControlError(RuntimeError):
    pass


def hold_for_repair_decision(output_dir: Path, events: Path, deadline: float) -> None:
    decision_path = output_dir / "repair-decision.json"
    hold_deadline = min(deadline, time.time() + 600)
    emit(events, "repair_window_open", maximum_seconds=max(0, round(hold_deadline - time.time(), 3)))
    while time.time() < hold_deadline:
        if decision_path.exists():
            try:
                action = json.loads(decision_path.read_text()).get("action")
            except Exception:
                action = "invalid"
            emit(events, "repair_decision_received", action=action)
            if action == "teardown":
                return
        time.sleep(5)
    emit(events, "repair_window_expired")


def build_host_bootstrap() -> str:
    return f'''set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y docker.io curl ca-certificates gnupg
fi
sudo systemctl enable --now docker
if ! command -v nvidia-ctk >/dev/null 2>&1; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y nvidia-container-toolkit
fi
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
sudo docker pull {IMAGE}
sudo docker image inspect {IMAGE} --format '{{{{json .RepoDigests}}}}'
sudo docker run --rm --gpus all --entrypoint bash {IMAGE} -lc 'rm -f /etc/ld.so.conf.d/00-cuda-compat.conf /etc/ld.so.conf.d/cuda-compat.conf; ldconfig; exec python3 -c "import torch; print(torch.cuda.get_device_name())"'
'''


def build_container_command(spec_hash: str, deadline_epoch: int) -> list[str]:
    return [
        "sudo", "docker", "run", "--rm", "--gpus", "all", "--ipc=host", "--shm-size=16g",
        "-v", "/home/glmrunner/input:/input:ro", "-v", "/workspace:/workspace",
        "-e", f"EXPERIMENT_SPEC_SHA256={spec_hash}",
        "-e", f"CAMPAIGN_DEADLINE_EPOCH={deadline_epoch}",
        "-e", f"RUNTIME_IMAGE_IDENTITY={IMAGE}",
        "-e", "MICROBENCH_PATH=/input/vllm_mla_microbench.py",
        "--entrypoint", "bash", IMAGE, "-lc",
        "rm -f /etc/ld.so.conf.d/00-cuda-compat.conf /etc/ld.so.conf.d/cuda-compat.conf; ldconfig; exec bash /input/remote_mla_microbench.sh",
    ]


def run(output_dir: Path, name: str, key: Path, public_key: Path, spec_hash: str) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "summary.json").exists():
        raise MicrobenchControlError("completed output directory already exists")
    script = HERE / "remote_mla_microbench.sh"
    benchmark = HERE / "vllm_mla_microbench.py"
    if not script.is_file() or not benchmark.is_file():
        raise MicrobenchControlError("microbenchmark inputs are incomplete")
    if list_items("instance"):
        raise MicrobenchControlError("active instances exist")
    events = output_dir / "events.jsonl"
    started = time.time()
    deadline = started + ABSOLUTE_TIMEOUT_SECONDS
    instance_id = None
    disk_name = name + "-boot"
    outcome = "FAIL"
    artifact_hash = None
    manifest_files = 0
    allocation_result = None
    (output_dir / "provider-request.json").write_text(json.dumps({
        "name": name,
        "platform": PLATFORM,
        "preset": PRESET,
        "purchase_model": "preemptible_stop",
        "boot_disk_gib": DISK_GIB,
        "runtime_image": IMAGE,
        "hourly_rate_usd_vendor_calculator": HOURLY_RATE_USD,
        "disk_hourly_rate_usd_vendor_calculator": DISK_HOURLY_RATE_USD,
        "absolute_timeout_seconds": ABSOLUTE_TIMEOUT_SECONDS,
        "max_total_cost_usd": (HOURLY_RATE_USD + DISK_HOURLY_RATE_USD) * ABSOLUTE_TIMEOUT_SECONDS / 3600,
        "experiment_spec_sha256": spec_hash,
    }, indent=2, sort_keys=True) + "\n")
    try:
        create = build_create_command(
            name=name,
            disk_name=disk_name,
            cloud_init=make_cloud_init(public_key.read_text()),
            disk_gib=DISK_GIB,
            platform=PLATFORM,
            preset=PRESET,
            preemptible=True,
        )
        proc = subprocess.run(create, capture_output=True, text=True, timeout=180)
        if proc.returncode:
            raise MicrobenchControlError(f"instance create failed with exit {proc.returncode}")
        instance_id = extract_instance_id(json.loads(proc.stdout))
        emit(events, "instance_created", instance_id=instance_id)
        subprocess.Popen(
            [sys.executable, str(HERE / "placement_control.py"), "watchdog", instance_id, disk_name, str(deadline)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        ip = None
        while time.time() < min(deadline, started + 600):
            payload = get_instance(instance_id)
            if payload is None:
                raise MicrobenchControlError("instance disappeared before readiness")
            ip = extract_public_ipv4(payload)
            if ip:
                break
            time.sleep(5)
        if not ip:
            raise MicrobenchControlError("public IP readiness exceeded 600 seconds")
        wait_ssh(ip, key, min(deadline, started + 600))
        emit(events, "ssh_ready", elapsed_seconds=round(time.time() - started, 3))
        bootstrap = run_ssh(ip, key, "bash -s", timeout=1800, input_text=build_host_bootstrap())
        (output_dir / "host-bootstrap.stdout.log").write_text(bootstrap.stdout)
        (output_dir / "host-bootstrap.stderr.log").write_text(bootstrap.stderr)
        if bootstrap.returncode:
            raise MicrobenchControlError("host bootstrap failed")
        if run_ssh(ip, key, "mkdir -p /home/glmrunner/input", timeout=30).returncode:
            raise MicrobenchControlError("remote input directory creation failed")
        scp_to(ip, key, [script, benchmark], "/home/glmrunner/input/")
        remote = run_ssh(
            ip,
            key,
            build_container_command(spec_hash, int(deadline)),
            timeout=max(60, int(deadline - time.time()) + 180),
        )
        (output_dir / "remote.stdout.log").write_text(remote.stdout)
        (output_dir / "remote.stderr.log").write_text(remote.stderr)
        archive = output_dir / "mla-microbench.tar.gz"
        sidecar = output_dir / "mla-microbench.remote.sha256"
        scp_from(ip, key, "/workspace/public-mla-microbench/mla-microbench.tar.gz", archive)
        scp_from(ip, key, "/workspace/public-mla-microbench/mla-microbench.tar.gz.sha256", sidecar)
        artifact_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        if artifact_hash != sidecar.read_text().split()[0]:
            raise MicrobenchControlError("remote/local artifact hash mismatch")
        manifest_files = verify_internal_manifest(archive)
        import tarfile

        with tarfile.open(archive, "r:gz") as bundle:
            member = next(row for row in bundle.getmembers() if row.name.endswith("/allocation-result.json"))
            handle = bundle.extractfile(member)
            if handle is None:
                raise MicrobenchControlError("allocation result missing")
            allocation_result = json.loads(handle.read())
        outcome = "PASS" if remote.returncode == 0 and allocation_result.get("sweep_pass") is True else "FAIL"
        emit(events, "artifact_retrieved", sha256=artifact_hash, manifest_files=manifest_files, outcome=outcome)
    except Exception as error:
        emit(events, "experiment_error", error_type=type(error).__name__, message=str(error))
        if instance_id is not None and allocation_result is None:
            hold_for_repair_decision(output_dir, events, deadline)
    finally:
        if instance_id is None:
            try:
                instance_id = find_named_instance(name)
            except Exception:
                instance_id = None
        delete_requested = time.time()
        if instance_id:
            delete_instance(instance_id)
            absent = wait_absent(instance_id, time.time() + 240)
        else:
            absent = True
        for disk in list_items("disk"):
            if metadata_name(disk) == disk_name and metadata_id(disk):
                delete_disk(metadata_id(disk))
        final_instances = list_items("instance")
        final_disks = list_items("disk")
        cleanup = (
            absent
            and not any(metadata_name(row) == name for row in final_instances)
            and not any(metadata_name(row) == disk_name for row in final_disks)
        )
        elapsed = max(0.0, delete_requested - started)
        cost = elapsed / 3600 * (HOURLY_RATE_USD + DISK_HOURLY_RATE_USD)
        (output_dir / "summary.json").write_text(json.dumps({
            "outcome": outcome,
            "cleanup_pass": cleanup,
            "instance_get_not_found": absent,
            "instance_id": instance_id,
            "allocation_seconds": round(elapsed, 3),
            "cost_usd_derived": round(cost, 9),
            "cost_basis": "measured exposure at authenticated Nebius preemptible VM and disk rates; invoice pending",
            "artifact_sha256": artifact_hash,
            "manifest_file_count": manifest_files,
            "allocation_result": allocation_result,
            "final_instance_count": len(final_instances),
            "final_disk_count": len(final_disks),
            "ended_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        }, indent=2, sort_keys=True) + "\n")
        emit(events, "cleanup_verified", cleanup_pass=cleanup, instance_get_not_found=absent)
    return 0 if outcome == "PASS" and cleanup else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--ssh-public-key", type=Path, required=True)
    parser.add_argument("--experiment-spec-sha256", required=True)
    args = parser.parse_args()
    return run(args.output_dir, args.name, args.ssh_key, args.ssh_public_key, args.experiment_spec_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
