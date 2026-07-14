#!/usr/bin/env python3
"""Run the frozen stock and conditional MTP controls on one Nebius H100."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
CAMPAIGN = HERE.parent
PHASE_B = CAMPAIGN / "phase_b"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PHASE_B))
sys.path.insert(0, str(CAMPAIGN / "quality"))

from placement_control import (  # noqa: E402
    HOURLY_RATE_USD,
    SSH_USER,
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
    ssh_base,
    utc_now,
    wait_absent,
    wait_ssh,
)
from runpod_stock_control import frozen_archive_b64  # noqa: E402
from score_pair import score_pair  # noqa: E402


IMAGE = "lmsysorg/sglang:v0.5.15-cu130@sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af"
ABSOLUTE_TIMEOUT_SECONDS = 9000
MAX_COMPUTE_COST_USD = ABSOLUTE_TIMEOUT_SECONDS / 3600 * HOURLY_RATE_USD
DISK_GIB = 250
MTP_ARGS = [
    "--speculative-algorithm", "EAGLE",
    "--speculative-draft-model-path", "/workspace/model-bf16",
    "--speculative-num-steps", "3",
    "--speculative-eagle-topk", "1",
    "--speculative-num-draft-tokens", "4",
]
WORKLOAD_SHA256 = "f47c7af5e53483524010d06a93313b29f1a10c08f7df4bf18638349b4767193a"
QUALITY_SHA256 = "152548d51fba8e8ff5e8f1e665c5af166fb6d97cdf3010723042112855964668"


class StockError(RuntimeError):
    pass


def validate_local_contracts() -> dict[str, str]:
    checks = {
        "workload_sha256": (CAMPAIGN / "workloads" / "validate_bundle.py", WORKLOAD_SHA256),
        "quality_sha256": (CAMPAIGN / "quality" / "validate_quality.py", QUALITY_SHA256),
    }
    result = {}
    for name, (script, expected) in checks.items():
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=30)
        observed = proc.stdout.strip()
        if proc.returncode or observed != expected:
            raise StockError(f"local {name} contract validation failed")
        result[name] = observed
    return result


def emit(path: Path, event: str, **fields: Any) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(
            {"timestamp": utc_now(), "event": event, **fields},
            sort_keys=True, separators=(",", ":"),
        ) + "\n")


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
sudo docker run --rm --gpus all {IMAGE} nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits
docker --version
sudo dpkg-query -W -f='${{Package}}=${{Version}}\n' docker.io nvidia-container-toolkit
'''


def build_container_command(
    experiment_spec_sha256: str,
    deadline_epoch: int,
    *,
    configuration: str = "stock_no_cache_fcfs",
    output_name: str = "campaign-100-phase-b",
    public_name: str = "public-stock",
    extra_args: list[str] | None = None,
) -> list[str]:
    extra_payload = ""
    if extra_args:
        extra_payload = base64.b64encode(("\n".join(extra_args) + "\n").encode()).decode()
    return [
        "sudo", "docker", "run", "--rm", "--gpus", "all", "--ipc=host",
        "--shm-size=32g", "--cap-add", "SYS_NICE",
        "-v", "/home/glmrunner/input:/input:ro",
        "-v", "/workspace:/workspace",
        "-e", f"EXPERIMENT_SPEC_SHA256={experiment_spec_sha256}",
        "-e", f"CAMPAIGN_DEADLINE_EPOCH={deadline_epoch}",
        "-e", "WORKLOAD_ARCHIVE_PATH=/input/frozen-workloads.tar.gz",
        "-e", "QUALITY_ARCHIVE_PATH=/input/frozen-quality.tar.gz",
        "-e", "ARTIFACT_BUILDER_PATH=/input/artifact_builder.py",
        "-e", "SERVE_ARTIFACT=0",
        "-e", f"CONFIGURATION={configuration}",
        "-e", f"OUT=/workspace/{output_name}",
        "-e", f"PUBLIC=/workspace/{public_name}",
        "-e", f"SERVER_EXTRA_ARGS_B64={extra_payload}",
        IMAGE, "bash", "/input/remote_baseline.sh",
    ]


def verify_internal_manifest(archive: Path) -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(root, filter="data")
        children = [path for path in root.iterdir() if path.is_dir()]
        if len(children) != 1:
            raise ValueError("artifact must contain exactly one bundle root")
        bundle_root = children[0]
        rows = json.loads((bundle_root / "manifest.json").read_text())
        if not isinstance(rows, list) or not rows:
            raise ValueError("artifact manifest is empty or invalid")
        for row in rows:
            relative = Path(row["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("artifact manifest path escapes root")
            payload = (bundle_root / relative).read_bytes()
            if len(payload) != row["bytes"]:
                raise ValueError(f"byte count mismatch: {relative}")
            if hashlib.sha256(payload).hexdigest() != row["sha256"]:
                raise ValueError(f"hash mismatch: {relative}")
        return len(rows)


def extract_member(archive: Path, suffix: str) -> bytes:
    with tarfile.open(archive, "r:gz") as bundle:
        matches = [member for member in bundle.getmembers() if member.name.endswith(suffix)]
        if len(matches) != 1:
            raise StockError(f"expected one artifact member ending in {suffix}")
        handle = bundle.extractfile(matches[0])
        if handle is None:
            raise StockError(f"artifact member is not a file: {suffix}")
        return handle.read()


def run_ssh(ip: str, key: Path, command: list[str] | str, *, timeout: int, input_text: str | None = None):
    remote = command if isinstance(command, str) else shlex.join(command)
    return subprocess.run(
        [*ssh_base(ip, key), remote], input=input_text,
        capture_output=True, text=True, timeout=timeout,
    )


def scp_to(ip: str, key: Path, sources: list[Path], destination: str) -> None:
    command = [
        "scp", "-i", str(key), "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts",
        *map(str, sources), f"{SSH_USER}@{ip}:{destination}",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise StockError("input transfer failed")


def scp_from(ip: str, key: Path, source: str, destination: Path) -> None:
    command = [
        "scp", "-i", str(key), "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts",
        f"{SSH_USER}@{ip}:{source}", str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise StockError(f"artifact retrieval failed: {source}")


def write_inputs(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    workload = directory / "frozen-workloads.tar.gz"
    quality = directory / "frozen-quality.tar.gz"
    workload.write_bytes(base64.b64decode(frozen_archive_b64(CAMPAIGN / "workloads")))
    quality.write_bytes(base64.b64decode(frozen_archive_b64(CAMPAIGN / "quality")))
    shutil.copy2(PHASE_B / "remote_baseline.sh", directory / "remote_baseline.sh")
    shutil.copy2(PHASE_B / "artifact_builder.py", directory / "artifact_builder.py")
    return [workload, quality, directory / "remote_baseline.sh", directory / "artifact_builder.py"]


def normalized(value: Any) -> str:
    return " ".join(str(value).strip().split()).casefold()


def paired_identity(control_payload: bytes, candidate_payload: bytes) -> dict[str, Any]:
    control = {row["case_id"]: row["output"] for row in map(json.loads, control_payload.splitlines())}
    candidate = {row["case_id"]: row["output"] for row in map(json.loads, candidate_payload.splitlines())}
    if set(control) != set(candidate):
        raise StockError("paired quality case identities differ")
    comparable = [key for key in sorted(control) if isinstance(control[key], str) and isinstance(candidate[key], str)]
    mismatches = [key for key in comparable if normalized(control[key]) != normalized(candidate[key])]
    return {"comparable_cases": len(comparable), "mismatch_case_ids": mismatches, "pass": not mismatches}


def paired_quality(control_payload: bytes, candidate_payload: bytes) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        control = Path(directory) / "control.jsonl"
        candidate = Path(directory) / "candidate.jsonl"
        control.write_bytes(control_payload)
        candidate.write_bytes(candidate_payload)
        return score_pair(CAMPAIGN / "quality", "development", control, candidate)


def mtp_performance_gate(control_result: dict[str, Any], candidate_result: dict[str, Any]) -> dict[str, Any]:
    def c8(result: dict[str, Any]) -> dict[str, Any]:
        rows = {row["profile_id"]: row for row in result.get("profiles", [])}
        if "fixed_8k_1k_c8" not in rows:
            raise StockError("paired result lacks fixed_8k_1k_c8")
        return rows["fixed_8k_1k_c8"]

    control = c8(control_result)
    candidate = c8(candidate_result)
    control_rate = float(control["output_tokens_per_second_conservative"])
    candidate_rate = float(candidate["output_tokens_per_second_conservative"])
    improvement = candidate_rate / control_rate - 1 if control_rate > 0 else float("-inf")
    return {
        "profile_id": "fixed_8k_1k_c8",
        "control_output_tokens_per_second": control_rate,
        "candidate_output_tokens_per_second": candidate_rate,
        "relative_improvement": improvement,
        "minimum_relative_improvement": 0.05,
        "control_slo_pass": control.get("frozen_slo_pass") is True,
        "candidate_slo_pass": candidate.get("frozen_slo_pass") is True,
        "pass": control.get("frozen_slo_pass") is True
        and candidate.get("frozen_slo_pass") is True
        and improvement >= 0.05,
    }


def fixed_sequence_pass(arm: dict[str, Any]) -> bool:
    result = arm.get("allocation_result")
    return arm.get("artifact_ok") is True and isinstance(result, dict) and result.get("sequence_pass") is True


def paired_non_regression_gate(result: dict[str, Any]) -> dict[str, Any]:
    overall = float(result.get("overall_regression", float("-inf")))
    categories = result.get("category_regressions")
    category_pass = isinstance(categories, dict) and bool(categories) and all(
        float(value) >= -0.05 for value in categories.values()
    )
    return {
        "overall_regression": overall,
        "minimum_overall_regression": -0.02,
        "minimum_category_regression": -0.05,
        "category_pass": category_pass,
        "absolute_point_screen_pass": result.get("point_screen_pass") is True,
        "pass": overall >= -0.02 and category_pass,
    }


def run_arm(
    *, ip: str, key: Path, output_dir: Path, spec_hash: str, deadline_epoch: int,
    configuration: str, output_name: str, public_name: str, extra_args: list[str] | None,
) -> dict[str, Any]:
    command = build_container_command(
        spec_hash, deadline_epoch, configuration=configuration, output_name=output_name,
        public_name=public_name, extra_args=extra_args,
    )
    started = time.time()
    result = run_ssh(ip, key, command, timeout=max(60, deadline_epoch - int(time.time()) + 180))
    (output_dir / f"{configuration}-remote.stdout.log").write_text(result.stdout)
    (output_dir / f"{configuration}-remote.stderr.log").write_text(result.stderr)
    archive = output_dir / f"{configuration}-artifact.tar.gz"
    try:
        scp_from(ip, key, f"/workspace/{public_name}/phase-b-control.tar.gz", archive)
        sidecar = output_dir / f"{configuration}-artifact.remote.sha256"
        scp_from(ip, key, f"/workspace/{public_name}/phase-b-control.tar.gz.sha256", sidecar)
        local_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        remote_hash = sidecar.read_text().split()[0]
        if local_hash != remote_hash:
            raise StockError("remote and local artifact hashes differ")
        manifest_files = verify_internal_manifest(archive)
        allocation_result = json.loads(extract_member(archive, "/allocation-result.json"))
        artifact_ok = True
    except Exception as error:
        local_hash = None
        manifest_files = 0
        allocation_result = None
        artifact_ok = False
        (output_dir / f"{configuration}-artifact-error.txt").write_text(f"{type(error).__name__}: {error}\n")
    return {
        "configuration": configuration,
        "remote_exit_code": result.returncode,
        "elapsed_seconds": round(time.time() - started, 3),
        "artifact_ok": artifact_ok,
        "artifact_sha256": local_hash,
        "manifest_file_count": manifest_files,
        "allocation_result": allocation_result,
        "pass": result.returncode == 0 and artifact_ok and allocation_result is not None
        and allocation_result.get("sequence_pass") is True and allocation_result.get("quality_pass") is True,
    }


def run(
    output_dir: Path, name: str, key: Path, public_key: Path, spec_hash: str,
    *, diagnostic_mtp_after_fixed_slo: bool = False,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "summary.json").exists():
        raise StockError("output directory contains a completed run")
    contract_identities = validate_local_contracts()
    events = output_dir / "events.jsonl"
    started = time.time()
    deadline = started + ABSOLUTE_TIMEOUT_SECONDS
    instance_id = None
    disk_name = name + "-boot"
    arms: list[dict[str, Any]] = []
    outcome = "FAIL"
    initial_instances = list_items("instance")
    initial_disks = list_items("disk")
    if initial_instances:
        raise StockError("stock control failed: active instances exist")
    emit(events, "stock_control", instance_count=0, disk_count=len(initial_disks), **contract_identities)
    (output_dir / "provider-request.json").write_text(json.dumps({
        "name": name,
        "platform": "gpu-h100-sxm",
        "preset": "1gpu-16vcpu-200gb",
        "purchase_model": "regular_on_demand",
        "image_family": "ubuntu24.04-cuda13.0",
        "boot_disk_gib": DISK_GIB,
        "container_image": IMAGE,
        "hourly_rate_usd_vendor_list": HOURLY_RATE_USD,
        "absolute_timeout_seconds": ABSOLUTE_TIMEOUT_SECONDS,
        "max_compute_cost_usd": MAX_COMPUTE_COST_USD,
        "diagnostic_mtp_after_fixed_slo": diagnostic_mtp_after_fixed_slo,
    }, indent=2, sort_keys=True) + "\n")
    try:
        cloud_init = make_cloud_init(public_key.read_text())
        create = build_create_command(
            name=name, disk_name=disk_name, cloud_init=cloud_init, disk_gib=DISK_GIB,
        )
        proc = subprocess.run(create, capture_output=True, text=True, timeout=180)
        if proc.returncode:
            raise StockError(f"instance create failed with exit {proc.returncode}")
        instance_id = extract_instance_id(json.loads(proc.stdout))
        emit(events, "instance_created", instance_id=instance_id)
        subprocess.Popen(
            [sys.executable, str(HERE / "placement_control.py"), "watchdog", instance_id, disk_name, str(deadline)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        ip = None
        while time.time() < min(deadline, started + 600):
            payload = get_instance(instance_id)
            if payload is None:
                raise StockError("instance disappeared before readiness")
            ip = extract_public_ipv4(payload)
            if ip:
                break
            time.sleep(5)
        if not ip:
            raise StockError("public IP readiness exceeded 600 seconds")
        wait_ssh(ip, key, min(deadline, started + 600))
        emit(events, "ssh_ready", elapsed_seconds=round(time.time() - started, 3))
        bootstrap = run_ssh(ip, key, "bash -s", timeout=1800, input_text=build_host_bootstrap())
        (output_dir / "host-bootstrap.stdout.log").write_text(bootstrap.stdout)
        (output_dir / "host-bootstrap.stderr.log").write_text(bootstrap.stderr)
        if bootstrap.returncode:
            raise StockError("host Docker/NVIDIA bootstrap failed")
        emit(events, "container_runtime_ready", elapsed_seconds=round(time.time() - started, 3))
        with tempfile.TemporaryDirectory() as directory:
            inputs = write_inputs(Path(directory))
            mkdir = run_ssh(ip, key, "mkdir -p /home/glmrunner/input", timeout=30)
            if mkdir.returncode:
                raise StockError("remote input directory creation failed")
            scp_to(ip, key, inputs, "/home/glmrunner/input/")
        emit(events, "frozen_inputs_transferred")

        stock = run_arm(
            ip=ip, key=key, output_dir=output_dir, spec_hash=spec_hash,
            deadline_epoch=int(deadline), configuration="stock_no_cache_fcfs",
            output_name="campaign-100-phase-b-stock", public_name="public-stock", extra_args=None,
        )
        arms.append(stock)
        emit(events, "stock_arm_complete", passed=stock["pass"], elapsed_seconds=stock["elapsed_seconds"])
        mtp_admitted = stock["pass"] or (
            diagnostic_mtp_after_fixed_slo and fixed_sequence_pass(stock)
        )
        emit(events, "mtp_admission", admitted=mtp_admitted, diagnostic=diagnostic_mtp_after_fixed_slo)
        if mtp_admitted and time.time() < deadline - 1200:
            mtp = run_arm(
                ip=ip, key=key, output_dir=output_dir, spec_hash=spec_hash,
                deadline_epoch=int(deadline), configuration="mtp_eagle_3_1_4",
                output_name="campaign-100-phase-b-mtp", public_name="public-mtp", extra_args=MTP_ARGS,
            )
            arms.append(mtp)
            emit(events, "mtp_arm_complete", passed=mtp["pass"], elapsed_seconds=mtp["elapsed_seconds"])
            if mtp["artifact_ok"]:
                control_responses = extract_member(output_dir / "stock_no_cache_fcfs-artifact.tar.gz", "/quality-stock_no_cache_fcfs-responses.jsonl")
                candidate_responses = extract_member(output_dir / "mtp_eagle_3_1_4-artifact.tar.gz", "/quality-mtp_eagle_3_1_4-responses.jsonl")
                identity = paired_identity(control_responses, candidate_responses)
                quality = paired_quality(control_responses, candidate_responses)
                performance = mtp_performance_gate(stock["allocation_result"], mtp["allocation_result"])
                non_regression = paired_non_regression_gate(quality)
                (output_dir / "mtp-exact-identity.json").write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n")
                (output_dir / "paired-quality.json").write_text(json.dumps(quality, indent=2, sort_keys=True) + "\n")
                (output_dir / "mtp-performance.json").write_text(json.dumps(performance, indent=2, sort_keys=True) + "\n")
                (output_dir / "mtp-paired-non-regression.json").write_text(json.dumps(non_regression, indent=2, sort_keys=True) + "\n")
                mtp["exact_normalized_identity"] = identity
                mtp["paired_quality"] = {
                    "point_screen_pass": quality["point_screen_pass"],
                    "provisional_due_to_uncertainty": quality["provisional_due_to_uncertainty"],
                    "reject_reasons": quality["reject_reasons"],
                }
                mtp["performance"] = performance
                mtp["paired_non_regression"] = non_regression
            if diagnostic_mtp_after_fixed_slo:
                diagnostic_pass = (
                    fixed_sequence_pass(mtp)
                    and mtp.get("exact_normalized_identity", {}).get("pass")
                    and mtp.get("paired_non_regression", {}).get("pass")
                    and mtp.get("performance", {}).get("pass")
                )
                outcome = "DIAGNOSTIC_PASS" if diagnostic_pass else "DIAGNOSTIC_FALSIFIED"
            else:
                outcome = "PASS" if (
                    mtp["pass"]
                    and mtp.get("exact_normalized_identity", {}).get("pass")
                    and mtp.get("paired_quality", {}).get("point_screen_pass")
                    and not mtp.get("paired_quality", {}).get("provisional_due_to_uncertainty")
                    and mtp.get("performance", {}).get("pass")
                ) else "FAIL"
        else:
            outcome = "STOCK_ONLY_PASS" if stock["pass"] else "FAIL"
    except Exception as error:
        emit(events, "experiment_error", error_type=type(error).__name__, message=str(error))
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
        cleanup = absent and not any(metadata_name(row) == name for row in final_instances) and not any(
            metadata_name(row) == disk_name for row in final_disks
        )
        elapsed = max(0.0, delete_requested - started)
        summary = {
            "outcome": outcome,
            "cleanup_pass": cleanup,
            "instance_id": instance_id,
            "allocation_seconds": round(elapsed, 3),
            "cost_usd_derived": round(elapsed / 3600 * HOURLY_RATE_USD, 9),
            "cost_basis": "measured elapsed exposure at vendor list rate; provider invoice pending",
            "diagnostic_mtp_after_fixed_slo": diagnostic_mtp_after_fixed_slo,
            "arms": arms,
            "final_instance_count": len(final_instances),
            "final_disk_count": len(final_disks),
            "ended_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        emit(events, "cleanup_verified", cleanup_pass=cleanup, instance_get_not_found=absent)
    return 0 if cleanup and outcome in {"PASS", "DIAGNOSTIC_PASS"} else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--ssh-public-key", type=Path, required=True)
    parser.add_argument("--experiment-spec-sha256", required=True)
    parser.add_argument("--diagnostic-mtp-after-fixed-slo", action="store_true")
    args = parser.parse_args()
    return run(
        args.output_dir, args.name, args.ssh_key, args.ssh_public_key,
        args.experiment_spec_sha256,
        diagnostic_mtp_after_fixed_slo=args.diagnostic_mtp_after_fixed_slo,
    )


if __name__ == "__main__":
    raise SystemExit(main())
