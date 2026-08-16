#!/usr/bin/env python3
"""Run a bounded, locally staged GLM-4.7-Flash AWQ smoke on Nebius L40S."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
CAMPAIGN = HERE.parent
GLM = CAMPAIGN.parent
sys.path.insert(0, str(HERE))

from placement_control import (  # noqa: E402
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
from stock_control import (  # noqa: E402
    build_host_bootstrap,
    extract_member,
    run_ssh,
    scp_from,
    scp_to,
    transfer_local_model as stream_local_model,
    verify_internal_manifest,
)
from session_staging import validate_local_files_cached  # noqa: E402


IMAGE = "lmsysorg/sglang:v0.5.15-cu130@sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af"
MODEL_REVISION = "ab31d120fbe79988fe2a0259993cf3c222aa8881"
MODEL_SHARD_COUNT = 4
MODEL_WEIGHT_BYTES = 20_170_199_928
DERIVED_STUDENT_REPOSITORY = "local-derived/glm47flash-student39"
MINIMAL_DEPTH42_V2_REPOSITORY = "local-derived/glm47flash-minimal-depth42-v2"
MINIMAL_DEPTH43_V2_REPOSITORY = "local-derived/glm47flash-minimal-depth43-v2"
DERIVED_AWQ_IDENTITIES = {
    "official-selective-w4": {
        "manifest_sha256": "7ab75a5258cce406351790cefe1f3f8ba2c63aa4ad618f8d94c5ac3a65ec7778",
        "config_sha256": "",
        "index_sha256": "",
        "weight_bytes": 19090237368,
    },
    "student39": {
        "manifest_sha256": "d09c1b7dbd10c91eec8aba98fc3f14878bf8d1784d610499935c3e355ba9e86a",
        "config_sha256": "07b92832975cb7d174660e88127e91b6269605fe0cfb1bd9bfd282056969be54",
        "index_sha256": "407b00ffcfa0a69174d4d65473f3fd889ccc9cadb88a75d98393ff2034d8153e",
        "weight_bytes": 15_544_868_264,
    },
    "student42": {
        "manifest_sha256": "a41e353015487ff58d367bf5ce42ae7c7d49de87c339c49deab714a69a42a584",
        "config_sha256": "3859511a5a451f8d9a5fd0dd10e25edd98dd40cc4e970d4a124047dc86982899",
        "index_sha256": "8758d9236670cb1c0f693ce6b54f7a9318c85c76feb8b333b8e0429a0113edde",
        "weight_bytes": 16_658_558_680,
    },
}
MINIMAL_DEPTH42_V2_IDENTITY = {
    "manifest_sha256": "cfee71f350b69a931bc6700712db9850780c30f2e8aa51a406ce9ac7a668cdda",
    "checksum_list_sha256": "87d080fa3b10a184abf39e050f6dd67264b32394b43d45caecd93d32e3512950",
    "config_sha256": "3859511a5a451f8d9a5fd0dd10e25edd98dd40cc4e970d4a124047dc86982899",
    "index_sha256": "8758d9236670cb1c0f693ce6b54f7a9318c85c76feb8b333b8e0429a0113edde",
    "weight_bytes": 16_658_558_680,
}
MINIMAL_DEPTH43_V2_IDENTITY = {
    "manifest_sha256": "745fdda3cd7c4ef43ad4a88cb10a05628e1887085528419bf7a004af80b47741",
    "checksum_list_sha256": "87e5f71388c1cd5293e13681641a0575136930e360bdbd52db0cc59ba5a045eb",
    "config_sha256": "a400acbe6b5322ba4ad2ef14e3892105bc516bd802584e60775b492b5ca68e7c",
    "index_sha256": "fb7aaed29073ab00a662526aab18e977de284b88533c777db7ea039b4c76764d",
    "weight_bytes": 17_029_788_816,
}
PLATFORM = "gpu-l40s-a"
PRESET = "1gpu-16vcpu-64gb"
DISK_GIB = 100
HOURLY_RATE_USD = 0.8484
DISK_HOURLY_RATE_USD = 0.0097222
ABSOLUTE_TIMEOUT_SECONDS = 4500


class AwqSmokeError(RuntimeError):
    pass


def derived_awq_identity(observed: dict[str, Any]) -> str | None:
    return next((name for name, identity in DERIVED_AWQ_IDENTITIES.items() if observed == identity), None)


def emit(path: Path, event: str, **fields: Any) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps({"timestamp": utc_now(), "event": event, **fields}, sort_keys=True) + "\n")


def validate_local_model(model_dir: Path) -> dict[str, Any]:
    manifest_path = model_dir / "model-files-manifest.json"
    checksum_path = model_dir / "model-files.sha256"
    if model_dir.is_symlink() or manifest_path.is_symlink() or checksum_path.is_symlink():
        raise AwqSmokeError("local model contract must not use symlinks")
    if not manifest_path.is_file() or not checksum_path.is_file():
        raise AwqSmokeError("local model lacks manifest contract")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("revision") != MODEL_REVISION:
        raise AwqSmokeError("local model revision mismatch")
    if manifest.get("shard_count") != MODEL_SHARD_COUNT:
        raise AwqSmokeError("local model shard count mismatch")
    repository = manifest.get("repository")
    derived_student = repository == DERIVED_STUDENT_REPOSITORY
    official_selective_w4 = repository == "local-derived/glm47flash-full47-official-selective-w4"
    minimal_depth42_v2 = repository == MINIMAL_DEPTH42_V2_REPOSITORY
    minimal_depth43_v2 = repository == MINIMAL_DEPTH43_V2_REPOSITORY
    derived_identity = None
    if derived_student or official_selective_w4 or minimal_depth42_v2 or minimal_depth43_v2:
        rows_by_path = {row.get("path"): row for row in manifest.get("files", []) if isinstance(row, dict)}
        observed = {
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "config_sha256": rows_by_path.get("config.json", {}).get("sha256"),
            "index_sha256": rows_by_path.get("model.safetensors.index.json", {}).get("sha256"),
            "weight_bytes": manifest.get("weight_bytes"),
        }
        if minimal_depth42_v2 or minimal_depth43_v2:
            identity = MINIMAL_DEPTH42_V2_IDENTITY if minimal_depth42_v2 else MINIMAL_DEPTH43_V2_IDENTITY
            expected = {**identity}
            expected.pop("checksum_list_sha256")
            if observed != expected or hashlib.sha256(checksum_path.read_bytes()).hexdigest() != identity["checksum_list_sha256"]:
                raise AwqSmokeError("minimal depth v2 identity is not allowlisted")
            derived_identity = "minimal-depth42-v2" if minimal_depth42_v2 else "minimal-depth43-v2"
            expected_weight_bytes = identity["weight_bytes"]
        elif official_selective_w4:
            expected = DERIVED_AWQ_IDENTITIES["official-selective-w4"]
            if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != expected["manifest_sha256"] or observed["weight_bytes"] != expected["weight_bytes"]:
                raise AwqSmokeError("official selective W4 identity is not allowlisted")
            derived_identity = "official-selective-w4"
            expected_weight_bytes = expected["weight_bytes"]
        else:
            derived_identity = derived_awq_identity(observed)
            if derived_identity is None:
                raise AwqSmokeError("derived AWQ identity is not allowlisted")
            expected_weight_bytes = DERIVED_AWQ_IDENTITIES[derived_identity]["weight_bytes"]
    else:
        expected_weight_bytes = MODEL_WEIGHT_BYTES
    if manifest.get("weight_bytes") != expected_weight_bytes:
        raise AwqSmokeError("local model weight bytes mismatch")
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        raise AwqSmokeError("local model manifest files invalid")
    shard_rows = [row for row in rows if row.get("path", "").endswith(".safetensors")]
    if len(shard_rows) != MODEL_SHARD_COUNT or sum(row["bytes"] for row in shard_rows) != expected_weight_bytes:
        raise AwqSmokeError("local AWQ shard geometry mismatch")
    validate_local_files_cached(model_dir, rows, persist_marker=False)
    return {
        "model_revision": MODEL_REVISION,
        "model_shard_count": MODEL_SHARD_COUNT,
        "model_weight_bytes": expected_weight_bytes,
        "model_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "derived_student": derived_student,
        "official_selective_w4": official_selective_w4,
        "minimal_depth42_v2": minimal_depth42_v2,
        "minimal_depth43_v2": minimal_depth43_v2,
        "derived_identity": derived_identity,
    }


def build_model_transfer_command(target: str = "/workspace/model-awq") -> str:
    return (
        f"sudo rm -rf {target} && "
        f"sudo install -d -o {SSH_USER} -g {SSH_USER} {target} && "
        f"tar -C {target} -xf -"
    )


def probe_transfer(ip: str, key: Path) -> str:
    payload = "glm-awq-transfer-probe-v1\n"
    expected = hashlib.sha256(payload.encode()).hexdigest()
    command = (
        f"sudo install -d -o {SSH_USER} -g {SSH_USER} /workspace/awq-transfer-probe && "
        "cat > /workspace/awq-transfer-probe/payload && sha256sum /workspace/awq-transfer-probe/payload"
    )
    result = run_ssh(ip, key, command, timeout=30, input_text=payload)
    if result.returncode or not result.stdout.startswith(expected):
        raise AwqSmokeError("tiny AWQ transfer probe failed")
    return expected


def transfer_local_model(ip: str, key: Path, model_dir: Path, target: str = "/workspace/model-awq", timeout: int = 900) -> None:
    # Reuse the tested streaming implementation with only the target path changed.
    import stock_control
    original = stock_control.build_model_transfer_command
    stock_control.build_model_transfer_command = lambda: build_model_transfer_command(target)
    try:
        stream_local_model(ip, key, model_dir, timeout=timeout)
    finally:
        stock_control.build_model_transfer_command = original


def build_container_command(spec_hash: str, deadline_epoch: int) -> list[str]:
    return [
        "sudo", "docker", "run", "--rm", "--gpus", "all", "--ipc=host", "--shm-size=24g",
        "--cap-add", "SYS_NICE", "-v", "/home/glmrunner/input:/input:ro", "-v", "/workspace:/workspace",
        "-e", f"EXPERIMENT_SPEC_SHA256={spec_hash}",
        "-e", f"CAMPAIGN_DEADLINE_EPOCH={deadline_epoch}",
        "-e", "MODEL_MANIFEST_PATH=/workspace/model-awq/model-files.sha256",
        "-e", "PATCHER_PATH=/input/patch_sglang_awq_loader.py",
        IMAGE, "bash", "/input/remote_awq_smoke.sh",
    ]


def run(
    output_dir: Path,
    name: str,
    key: Path,
    public_key: Path,
    local_model_dir: Path,
    spec_hash: str,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "summary.json").exists():
        raise AwqSmokeError("output directory contains a completed run")
    identities = validate_local_model(local_model_dir)
    patcher = GLM / "patch_sglang_awq_loader.py"
    remote_script = HERE / "remote_awq_smoke.sh"
    if not patcher.is_file() or not remote_script.is_file():
        raise AwqSmokeError("AWQ runtime inputs missing")
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
        raise AwqSmokeError("stock control failed: active instances exist")
    emit(events, "stock_control", instance_count=0, **identities)
    (output_dir / "provider-request.json").write_text(json.dumps({
        "name": name,
        "platform": PLATFORM,
        "preset": PRESET,
        "purchase_model": "preemptible_stop",
        "image_family": "ubuntu24.04-cuda13.0",
        "boot_disk_gib": DISK_GIB,
        "container_image": IMAGE,
        "hourly_rate_usd_vendor_calculator": HOURLY_RATE_USD,
        "disk_hourly_rate_usd_vendor_calculator": DISK_HOURLY_RATE_USD,
        "absolute_timeout_seconds": ABSOLUTE_TIMEOUT_SECONDS,
        "max_total_cost_usd": (HOURLY_RATE_USD + DISK_HOURLY_RATE_USD) * ABSOLUTE_TIMEOUT_SECONDS / 3600,
        **identities,
    }, indent=2, sort_keys=True) + "\n")
    try:
        create = build_create_command(
            name=name, disk_name=disk_name, cloud_init=make_cloud_init(public_key.read_text()),
            disk_gib=DISK_GIB, platform=PLATFORM, preset=PRESET, preemptible=True,
        )
        proc = subprocess.run(create, capture_output=True, text=True, timeout=180)
        if proc.returncode:
            raise AwqSmokeError(f"instance create failed with exit {proc.returncode}")
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
                raise AwqSmokeError("preemptible instance disappeared before readiness")
            ip = extract_public_ipv4(payload)
            if ip:
                break
            time.sleep(5)
        if not ip:
            raise AwqSmokeError("public IP readiness exceeded 600 seconds")
        wait_ssh(ip, key, min(deadline, started + 600))
        emit(events, "ssh_ready", elapsed_seconds=round(time.time() - started, 3))
        bootstrap = run_ssh(ip, key, "bash -s", timeout=1800, input_text=build_host_bootstrap())
        (output_dir / "host-bootstrap.stdout.log").write_text(bootstrap.stdout)
        (output_dir / "host-bootstrap.stderr.log").write_text(bootstrap.stderr)
        if bootstrap.returncode:
            raise AwqSmokeError("host Docker/NVIDIA bootstrap failed")
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory)
            shutil.copy2(remote_script, staging / remote_script.name)
            shutil.copy2(patcher, staging / patcher.name)
            mkdir = run_ssh(ip, key, "mkdir -p /home/glmrunner/input", timeout=30)
            if mkdir.returncode:
                raise AwqSmokeError("remote input directory creation failed")
            scp_to(ip, key, [staging / remote_script.name, staging / patcher.name], "/home/glmrunner/input/")
        probe_hash = probe_transfer(ip, key)
        emit(events, "tiny_transfer_probe_passed", sha256=probe_hash)
        transfer_started = time.time()
        transfer_local_model(ip, key, local_model_dir)
        emit(events, "verified_local_awq_transferred", elapsed_seconds=round(time.time() - transfer_started, 3))
        command = build_container_command(spec_hash, int(deadline))
        remote = run_ssh(ip, key, command, timeout=max(60, int(deadline - time.time()) + 180))
        (output_dir / "remote.stdout.log").write_text(remote.stdout)
        (output_dir / "remote.stderr.log").write_text(remote.stderr)
        archive = output_dir / "awq-smoke.tar.gz"
        scp_from(ip, key, "/workspace/public-awq/awq-smoke.tar.gz", archive)
        sidecar = output_dir / "awq-smoke.remote.sha256"
        scp_from(ip, key, "/workspace/public-awq/awq-smoke.tar.gz.sha256", sidecar)
        artifact_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        if artifact_hash != sidecar.read_text().split()[0]:
            raise AwqSmokeError("remote/local artifact hash mismatch")
        manifest_files = verify_internal_manifest(archive)
        allocation_result = json.loads(extract_member(archive, "/allocation-result.json"))
        outcome = "PASS" if remote.returncode == 0 and allocation_result.get("smoke_pass") is True else "FAIL"
        emit(events, "artifact_retrieved", sha256=artifact_hash, manifest_files=manifest_files, outcome=outcome)
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
        compute_cost = elapsed / 3600 * HOURLY_RATE_USD
        disk_cost = elapsed / 3600 * DISK_HOURLY_RATE_USD
        (output_dir / "summary.json").write_text(json.dumps({
            "outcome": outcome,
            "cleanup_pass": cleanup,
            "instance_id": instance_id,
            "allocation_seconds": round(elapsed, 3),
            "compute_cost_usd_derived": round(compute_cost, 9),
            "disk_cost_usd_derived": round(disk_cost, 9),
            "cost_usd_derived": round(compute_cost + disk_cost, 9),
            "cost_basis": "measured exposure at authenticated Nebius preemptible full-VM and disk rates; public IPv4/egress excluded; invoice pending",
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
    parser.add_argument("--local-model-dir", type=Path, required=True)
    parser.add_argument("--experiment-spec-sha256", required=True)
    args = parser.parse_args()
    return run(args.output_dir, args.name, args.ssh_key, args.ssh_public_key, args.local_model_dir, args.experiment_spec_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
