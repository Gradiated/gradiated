#!/usr/bin/env python3
"""Resume a preregistered vLLM batch on a retained Nebius instance, then clean up."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import tarfile
import tempfile
import time
from pathlib import Path

from awq_smoke_control import DISK_HOURLY_RATE_USD, HOURLY_RATE_USD, emit, probe_transfer, transfer_local_model, validate_local_model
from placement_control import delete_disk, delete_instance, extract_public_ipv4, get_instance, list_items, metadata_id, metadata_name, wait_absent
from stock_control import extract_member, run_ssh, scp_from, scp_to, verify_internal_manifest
from vllm_smoke_control import (
    HERE, TRANSFORMERS_REVISION, allocation_has_harness_error, build_container_command, build_host_bootstrap,
    hold_for_repair_decision, required_quality_files,
)


def run(args: argparse.Namespace) -> int:
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    events = out / "events.jsonl"
    identities = validate_local_model(args.local_model_dir)
    if not events.exists():
        emit(
            events,
            "retained_arm_control",
            instance_id=args.instance_id,
            parent_experiment_id=args.parent_experiment_id,
        )
    first = json.loads(events.read_text().splitlines()[0])
    started = dt.datetime.fromisoformat(first["timestamp"].replace("Z", "+00:00")).timestamp()
    deadline = min(started + 4500, float(args.session_deadline_epoch))
    disk_name = args.name + "-boot"
    artifact_hash = None
    manifest_files = 0
    allocation_result = None
    outcome = "FAIL"
    error_record = None
    retain_after_result = False
    instance = get_instance(args.instance_id)
    if instance is None:
        raise RuntimeError("retained instance is absent")
    ip = extract_public_ipv4(instance)
    if not ip:
        raise RuntimeError("retained instance has no public IP")
    emit(events, "repair_01_begin", repair_spec_sha256=args.repair_spec_sha256, **identities)
    try:
        if not args.reuse_staged_runtime_and_checkpoint:
            preflight = HERE / "vllm_preflight.py"
            scp_to(ip, args.ssh_key, [preflight], "/home/glmrunner/input/")
            scp_to(ip, args.ssh_key, [args.local_model_dir / "config.json"], "/home/glmrunner/input/model-config-only/")
            bootstrap = run_ssh(ip, args.ssh_key, "bash -s", timeout=900, input_text=build_host_bootstrap())
            (out / "repair-01-bootstrap.stdout.log").write_text(bootstrap.stdout)
            (out / "repair-01-bootstrap.stderr.log").write_text(bootstrap.stderr)
            if bootstrap.returncode:
                raise RuntimeError("repair-01 derived runtime preflight failed")
            emit(events, "repair_01_cuda_transformers_preflight_passed", transformers_revision=TRANSFORMERS_REVISION)

        quality_dir = HERE.parent / "quality"
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory)
            for source in (HERE / "remote_vllm_awq_smoke.sh", HERE / "vllm_batched_runner.py", HERE / "vllm_decode_kernel_patch.py"):
                shutil.copy2(source, staging / source.name)
            control = staging / "bf16-control-responses.jsonl"
            archive_path = HERE.parent / "allocations" / "nebius_h100_complete_stock_v13" / "stock_no_cache_fcfs-artifact.tar.gz"
            with tarfile.open(archive_path, "r:gz") as bundle:
                member = next(row for row in bundle.getmembers() if row.name.endswith("/quality-stock_no_cache_fcfs-responses.jsonl"))
                handle = bundle.extractfile(member)
                if handle is None:
                    raise RuntimeError("BF16 control responses missing")
                control.write_bytes(handle.read())
            run_ssh(ip, args.ssh_key, "mkdir -p /home/glmrunner/input/tokenizer /home/glmrunner/input/quality", timeout=30)
            scp_to(ip, args.ssh_key, [staging / "remote_vllm_awq_smoke.sh", staging / "vllm_batched_runner.py", staging / "vllm_decode_kernel_patch.py", control], "/home/glmrunner/input/")
            tokenizer_files = [args.reference_tokenizer_dir / name for name in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja")]
            scp_to(ip, args.ssh_key, tokenizer_files, "/home/glmrunner/input/tokenizer/")
            scp_to(ip, args.ssh_key, required_quality_files(quality_dir), "/home/glmrunner/input/quality/")
        emit(events, "repair_01_inputs_staged")
        if not args.reuse_staged_runtime_and_checkpoint:
            probe_hash = probe_transfer(ip, args.ssh_key)
            emit(events, "repair_01_tiny_transfer_probe_passed", sha256=probe_hash)
            transfer_started = time.time()
            transfer_local_model(ip, args.ssh_key, args.local_model_dir)
            emit(events, "repair_01_verified_awq_transferred", elapsed_seconds=round(time.time() - transfer_started, 3))
        else:
            emit(events, "repair_01_reused_verified_runtime_and_checkpoint")

        remote = run_ssh(ip, args.ssh_key, build_container_command(args.repair_spec_sha256, int(deadline), dtype=args.dtype, max_num_batched_tokens=args.max_num_batched_tokens, decode_block_n=args.decode_block_n, decode_num_stages=args.decode_num_stages, num_kv_splits=args.num_kv_splits), timeout=max(60, int(deadline - time.time()) + 180))
        (out / "repair-01-remote.stdout.log").write_text(remote.stdout)
        (out / "repair-01-remote.stderr.log").write_text(remote.stderr)
        archive = out / "vllm-awq-batch.tar.gz"
        sidecar = out / "vllm-awq-batch.remote.sha256"
        scp_from(ip, args.ssh_key, "/workspace/public-vllm-awq-batch/vllm-awq-batch.tar.gz", archive)
        scp_from(ip, args.ssh_key, "/workspace/public-vllm-awq-batch/vllm-awq-batch.tar.gz.sha256", sidecar)
        artifact_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        if artifact_hash != sidecar.read_text().split()[0]:
            raise RuntimeError("repair artifact hash mismatch")
        manifest_files = verify_internal_manifest(archive)
        allocation_result = json.loads(extract_member(archive, "/allocation-result.json"))
        outcome = "PASS" if remote.returncode == 0 and allocation_result.get("batch_pass") is True else "SCIENTIFIC_FAIL"
        emit(events, "repair_01_artifact_retrieved", sha256=artifact_hash, manifest_files=manifest_files, outcome=outcome)
        if allocation_has_harness_error(allocation_result):
            outcome = "FAIL"
            raise RuntimeError("typed allocation result contains a harness error")
        retain_after_result = args.keep_instance_after_result
    except Exception as error:
        error_record = {"type": type(error).__name__, "message": str(error)}
        emit(events, "repair_01_error", **error_record)
        if allocation_result is None or allocation_has_harness_error(allocation_result):
            hold_for_repair_decision(out, events, deadline)
    finally:
        delete_requested = time.time()
        if retain_after_result:
            absent = False
            emit(events, "instance_retained_for_next_preregistered_experiment", instance_id=args.instance_id)
        else:
            delete_instance(args.instance_id)
            absent = wait_absent(args.instance_id, time.time() + 240)
            for disk in list_items("disk"):
                if metadata_name(disk) == disk_name and metadata_id(disk):
                    delete_disk(metadata_id(disk))
        instances = list_items("instance")
        disks = list_items("disk")
        cleanup = absent and not instances and not disks
        elapsed = max(0.0, delete_requested - started)
        summary = {
            "outcome": outcome, "error": error_record, "cleanup_pass": cleanup, "instance_id": args.instance_id,
            "repair_spec_sha256": args.repair_spec_sha256, "allocation_seconds": round(elapsed, 3),
            "compute_cost_usd_derived": round(elapsed / 3600 * HOURLY_RATE_USD, 9),
            "disk_cost_usd_derived": round(elapsed / 3600 * DISK_HOURLY_RATE_USD, 9),
            "cost_usd_derived": round(elapsed / 3600 * (HOURLY_RATE_USD + DISK_HOURLY_RATE_USD), 9),
            "artifact_sha256": artifact_hash, "manifest_file_count": manifest_files, "allocation_result": allocation_result,
            "retained_for_next_experiment": retain_after_result,
            "final_instance_count": len(instances), "final_disk_count": len(disks),
            "ended_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        emit(events, "cleanup_verified", cleanup_pass=cleanup, instance_get_not_found=absent)
    return 0 if retain_after_result or cleanup and outcome in {"PASS", "SCIENTIFIC_FAIL"} else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--parent-experiment-id", required=True)
    parser.add_argument("--session-deadline-epoch", type=float, required=True)
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--local-model-dir", type=Path, required=True)
    parser.add_argument("--reference-tokenizer-dir", type=Path, required=True)
    parser.add_argument("--repair-spec-sha256", required=True)
    parser.add_argument("--reuse-staged-runtime-and-checkpoint", action="store_true")
    parser.add_argument("--keep-instance-after-result", action="store_true")
    parser.add_argument("--dtype", choices=("bfloat16", "float16"), default="bfloat16")
    parser.add_argument("--max-num-batched-tokens", type=int, default=32768)
    parser.add_argument("--decode-block-n", type=int, choices=(32, 64), default=32)
    parser.add_argument("--decode-num-stages", type=int, choices=(1, 2), default=2)
    parser.add_argument("--num-kv-splits", type=int, choices=(4, 8, 16), default=4)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
