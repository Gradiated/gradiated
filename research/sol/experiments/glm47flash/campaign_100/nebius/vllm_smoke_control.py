#!/usr/bin/env python3
"""Bounded stock-vLLM disambiguation smoke for the GLM AWQ checkpoint."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from awq_smoke_control import (  # noqa: E402
    DISK_GIB,
    DISK_HOURLY_RATE_USD,
    HOURLY_RATE_USD,
    PLATFORM,
    PRESET,
    emit,
    probe_transfer,
    transfer_local_model,
    validate_local_model,
)
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
from stock_control import extract_member, run_ssh, scp_from, scp_to, verify_internal_manifest  # noqa: E402


IMAGE = "vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543"
TRANSFORMERS_REVISION = "1618d44b9295361607ec74d7be860ba886aac039"
RUNTIME_IMAGE = "glm-vllm:0.15.0-transformers-1618d44"
ABSOLUTE_TIMEOUT_SECONDS = 4500


class VllmSmokeError(RuntimeError):
    pass


def allocation_has_harness_error(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    if isinstance(result.get("error"), dict):
        return True
    for stage in ("quality", "performance", "profiler"):
        value = result.get(stage)
        if isinstance(value, dict) and isinstance(value.get(f"{stage}_error"), dict):
            return True
    return False


def required_quality_files(quality_dir: Path) -> list[Path]:
    manifest = json.loads((quality_dir / "FROZEN_MANIFEST.json").read_text())
    return [quality_dir / name for name in sorted(manifest["files"])] + [quality_dir / "FROZEN_MANIFEST.json"]


def hold_for_repair_decision(output_dir: Path, events: Path, deadline: float) -> None:
    """Keep a failed allocation alive for at most ten minutes for an in-place repair decision."""
    decision_path = output_dir / "repair-decision.json"
    hold_deadline = min(deadline, time.time() + 600)
    emit(events, "repair_window_open", maximum_seconds=max(0, round(hold_deadline - time.time(), 3)))
    while time.time() < hold_deadline:
        if decision_path.exists():
            try:
                decision = json.loads(decision_path.read_text())
            except Exception:
                decision = {"action": "invalid"}
            emit(events, "repair_decision_received", action=decision.get("action"))
            if decision.get("action") == "teardown":
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
sudo docker run --rm --gpus all --entrypoint nvidia-smi {IMAGE} --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits
sudo docker build --network=host -t {RUNTIME_IMAGE} - <<'DOCKERFILE'
FROM {IMAGE}
RUN python3 -m pip install --no-cache-dir --upgrade https://github.com/huggingface/transformers/archive/{TRANSFORMERS_REVISION}.tar.gz
DOCKERFILE
sudo docker image inspect {RUNTIME_IMAGE} --format '{{{{.Id}}}}'
sudo docker run --rm --gpus all -v /home/glmrunner/input:/input:ro --entrypoint bash {RUNTIME_IMAGE} -lc 'rm -f /etc/ld.so.conf.d/00-cuda-compat.conf /etc/ld.so.conf.d/cuda-compat.conf; ldconfig; ldconfig -p | grep libcuda.so.1; exec python3 /input/vllm_preflight.py'
docker --version
sudo dpkg-query -W -f='${{Package}}=${{Version}}\n' docker.io nvidia-container-toolkit
'''


def build_container_command(spec_hash: str, deadline_epoch: int, dtype: str = "bfloat16", max_num_batched_tokens: int = 32768, decode_block_n: int = 32, decode_num_stages: int = 2) -> list[str]:
    return [
        "sudo", "docker", "run", "--rm", "--gpus", "all", "--ipc=host", "--shm-size=24g",
        "--cap-add", "SYS_NICE", "-v", "/home/glmrunner/input:/input:ro", "-v", "/workspace:/workspace",
        "-e", f"EXPERIMENT_SPEC_SHA256={spec_hash}", "-e", f"CAMPAIGN_DEADLINE_EPOCH={deadline_epoch}",
        "-e", "VLLM_RPC_TIMEOUT=1800000",
        "-e", f"VLLM_DTYPE={dtype}",
        "-e", f"VLLM_MAX_NUM_BATCHED_TOKENS={max_num_batched_tokens}",
        "-e", f"VLLM_DECODE_BLOCK_N={decode_block_n}",
        "-e", f"VLLM_DECODE_NUM_STAGES={decode_num_stages}",
        "-e", "MODEL_MANIFEST_PATH=/workspace/model-awq/model-files.sha256",
        "--entrypoint", "bash", RUNTIME_IMAGE, "-lc",
        "rm -f /etc/ld.so.conf.d/00-cuda-compat.conf /etc/ld.so.conf.d/cuda-compat.conf; ldconfig; exec bash /input/remote_vllm_awq_smoke.sh",
    ]


def run(output_dir: Path, name: str, key: Path, public_key: Path, model_dir: Path, tokenizer_dir: Path, spec_hash: str) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "summary.json").exists():
        raise VllmSmokeError("completed output directory already exists")
    identities = validate_local_model(model_dir)
    remote_script = HERE / "remote_vllm_awq_smoke.sh"
    batch_runner = HERE / "vllm_batched_runner.py"
    kernel_patcher = HERE / "vllm_decode_kernel_patch.py"
    preflight = HERE / "vllm_preflight.py"
    quality_dir = HERE.parent / "quality"
    required_tokenizer = [tokenizer_dir / name for name in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja")]
    required_quality = required_quality_files(quality_dir)
    if not all(path.is_file() for path in [remote_script, batch_runner, kernel_patcher, preflight, *required_tokenizer, *required_quality]):
        raise VllmSmokeError("batched vLLM inputs are incomplete")
    events = output_dir / "events.jsonl"
    started = time.time()
    deadline = started + ABSOLUTE_TIMEOUT_SECONDS
    instance_id = None
    disk_name = name + "-boot"
    outcome = "FAIL"
    artifact_hash = None
    manifest_files = 0
    allocation_result = None
    if list_items("instance"):
        raise VllmSmokeError("active instances exist")
    emit(events, "stock_control", instance_count=0, **identities)
    (output_dir / "provider-request.json").write_text(json.dumps({
        "name": name, "platform": PLATFORM, "preset": PRESET, "purchase_model": "preemptible_stop",
        "boot_disk_gib": DISK_GIB, "base_container_image": IMAGE,
        "derived_runtime_image": RUNTIME_IMAGE, "transformers_revision": TRANSFORMERS_REVISION,
        "hourly_rate_usd_vendor_calculator": HOURLY_RATE_USD,
        "disk_hourly_rate_usd_vendor_calculator": DISK_HOURLY_RATE_USD,
        "absolute_timeout_seconds": ABSOLUTE_TIMEOUT_SECONDS,
        "max_total_cost_usd": (HOURLY_RATE_USD + DISK_HOURLY_RATE_USD) * ABSOLUTE_TIMEOUT_SECONDS / 3600,
        **identities,
    }, indent=2, sort_keys=True) + "\n")
    try:
        create = build_create_command(name=name, disk_name=disk_name, cloud_init=make_cloud_init(public_key.read_text()), disk_gib=DISK_GIB, platform=PLATFORM, preset=PRESET, preemptible=True)
        proc = subprocess.run(create, capture_output=True, text=True, timeout=180)
        if proc.returncode:
            raise VllmSmokeError(f"instance create failed with exit {proc.returncode}")
        instance_id = extract_instance_id(json.loads(proc.stdout))
        emit(events, "instance_created", instance_id=instance_id)
        subprocess.Popen([sys.executable, str(HERE / "placement_control.py"), "watchdog", instance_id, disk_name, str(deadline)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        ip = None
        while time.time() < min(deadline, started + 600):
            payload = get_instance(instance_id)
            if payload is None:
                raise VllmSmokeError("instance disappeared before readiness")
            ip = extract_public_ipv4(payload)
            if ip:
                break
            time.sleep(5)
        if not ip:
            raise VllmSmokeError("public IP readiness exceeded 600 seconds")
        wait_ssh(ip, key, min(deadline, started + 600))
        emit(events, "ssh_ready", elapsed_seconds=round(time.time() - started, 3))
        if run_ssh(ip, key, "mkdir -p /home/glmrunner/input/model-config-only", timeout=30).returncode:
            raise VllmSmokeError("remote model-config preflight directory creation failed")
        scp_to(ip, key, [preflight], "/home/glmrunner/input/")
        scp_to(ip, key, [model_dir / "config.json"], "/home/glmrunner/input/model-config-only/")
        bootstrap = run_ssh(ip, key, "bash -s", timeout=1800, input_text=build_host_bootstrap())
        (output_dir / "host-bootstrap.stdout.log").write_text(bootstrap.stdout)
        (output_dir / "host-bootstrap.stderr.log").write_text(bootstrap.stderr)
        if bootstrap.returncode:
            raise VllmSmokeError("vLLM host bootstrap failed")
        emit(events, "cuda_and_transformers_preflight_passed", transformers_revision=TRANSFORMERS_REVISION)
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory)
            staged = staging / remote_script.name
            shutil.copy2(remote_script, staged)
            shutil.copy2(batch_runner, staging / batch_runner.name)
            shutil.copy2(kernel_patcher, staging / kernel_patcher.name)
            control_responses = staging / "bf16-control-responses.jsonl"
            with tarfile.open(HERE.parent / "allocations" / "nebius_h100_complete_stock_v13" / "stock_no_cache_fcfs-artifact.tar.gz", "r:gz") as bundle:
                member = next(row for row in bundle.getmembers() if row.name.endswith("/quality-stock_no_cache_fcfs-responses.jsonl"))
                handle = bundle.extractfile(member)
                if handle is None: raise VllmSmokeError("BF16 control responses missing")
                control_responses.write_bytes(handle.read())
            if run_ssh(ip, key, "mkdir -p /home/glmrunner/input/tokenizer /home/glmrunner/input/quality", timeout=30).returncode:
                raise VllmSmokeError("remote input directory creation failed")
            scp_to(ip, key, [staged, staging / batch_runner.name, staging / kernel_patcher.name, control_responses], "/home/glmrunner/input/")
            scp_to(ip, key, required_tokenizer, "/home/glmrunner/input/tokenizer/")
            scp_to(ip, key, required_quality, "/home/glmrunner/input/quality/")
        probe_hash = probe_transfer(ip, key)
        emit(events, "tiny_transfer_probe_passed", sha256=probe_hash)
        transfer_started = time.time()
        transfer_local_model(ip, key, model_dir)
        emit(events, "verified_local_awq_transferred", elapsed_seconds=round(time.time() - transfer_started, 3))
        remote = run_ssh(ip, key, build_container_command(spec_hash, int(deadline)), timeout=max(60, int(deadline - time.time()) + 180))
        (output_dir / "remote.stdout.log").write_text(remote.stdout)
        (output_dir / "remote.stderr.log").write_text(remote.stderr)
        archive = output_dir / "vllm-awq-batch.tar.gz"
        sidecar = output_dir / "vllm-awq-batch.remote.sha256"
        scp_from(ip, key, "/workspace/public-vllm-awq-batch/vllm-awq-batch.tar.gz", archive)
        scp_from(ip, key, "/workspace/public-vllm-awq-batch/vllm-awq-batch.tar.gz.sha256", sidecar)
        artifact_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        if artifact_hash != sidecar.read_text().split()[0]:
            raise VllmSmokeError("remote/local artifact hash mismatch")
        manifest_files = verify_internal_manifest(archive)
        allocation_result = json.loads(extract_member(archive, "/allocation-result.json"))
        outcome = "PASS" if remote.returncode == 0 and allocation_result.get("batch_pass") is True else "FAIL"
        emit(events, "artifact_retrieved", sha256=artifact_hash, manifest_files=manifest_files, outcome=outcome)
        if allocation_has_harness_error(allocation_result):
            raise VllmSmokeError("typed allocation result contains a harness error")
    except Exception as error:
        emit(events, "experiment_error", error_type=type(error).__name__, message=str(error))
        if instance_id is not None and allocation_result is None:
            hold_for_repair_decision(output_dir, events, deadline)
    finally:
        if instance_id is None:
            try: instance_id = find_named_instance(name)
            except Exception: instance_id = None
        delete_requested = time.time()
        if instance_id:
            delete_instance(instance_id)
            absent = wait_absent(instance_id, time.time() + 240)
        else:
            absent = True
        for disk in list_items("disk"):
            if metadata_name(disk) == disk_name and metadata_id(disk): delete_disk(metadata_id(disk))
        final_instances = list_items("instance")
        final_disks = list_items("disk")
        cleanup = absent and not any(metadata_name(row) == name for row in final_instances) and not any(metadata_name(row) == disk_name for row in final_disks)
        elapsed = max(0.0, delete_requested - started)
        compute_cost = elapsed / 3600 * HOURLY_RATE_USD
        disk_cost = elapsed / 3600 * DISK_HOURLY_RATE_USD
        (output_dir / "summary.json").write_text(json.dumps({
            "outcome": outcome, "cleanup_pass": cleanup, "instance_id": instance_id,
            "allocation_seconds": round(elapsed, 3), "compute_cost_usd_derived": round(compute_cost, 9),
            "disk_cost_usd_derived": round(disk_cost, 9), "cost_usd_derived": round(compute_cost + disk_cost, 9),
            "cost_basis": "measured exposure at authenticated Nebius preemptible VM and disk rates; public IPv4/egress excluded; invoice pending",
            "artifact_sha256": artifact_hash, "manifest_file_count": manifest_files, "allocation_result": allocation_result,
            "final_instance_count": len(final_instances), "final_disk_count": len(final_disks),
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
    parser.add_argument("--local-model-dir", type=Path, required=True)
    parser.add_argument("--reference-tokenizer-dir", type=Path, required=True)
    parser.add_argument("--experiment-spec-sha256", required=True)
    args = parser.parse_args()
    return run(args.output_dir, args.name, args.ssh_key, args.ssh_public_key, args.local_model_dir, args.reference_tokenizer_dir, args.experiment_spec_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
