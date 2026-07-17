#!/usr/bin/env python3
"""Resume a preregistered vLLM batch on a retained Nebius instance, then clean up."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import shutil
import tarfile
import tempfile
import time
from pathlib import Path

from awq_smoke_control import DISK_HOURLY_RATE_USD, HOURLY_RATE_USD, emit, probe_transfer, validate_local_model
from placement_control import delete_disk, delete_instance, extract_public_ipv4, get_instance, list_items, metadata_id, metadata_name, wait_absent
from stock_control import extract_member, run_ssh, scp_from, scp_to, verify_internal_manifest
from session_staging import transfer_checkpoint, transfer_timeout_seconds
from vllm_smoke_control import (
    ARTIFACT_RESERVE_SECONDS, HERE, TRANSFORMERS_REVISION, allocation_has_harness_error,
    build_container_command, build_host_bootstrap, hold_for_repair_decision, measured_phase,
    execution_outcome, required_quality_files, useful_gpu_seconds, validate_frontier_concurrencies,
)
from selective_w4_scope import VALID_SCOPES


def replace_remote_config(ip: str, key: Path, config: Path, expected_sha256: str) -> None:
    """Replace only config.json and atomically refresh its remote integrity rows."""
    payload = config.read_bytes()
    observed = hashlib.sha256(payload).hexdigest()
    if observed != expected_sha256:
        raise RuntimeError("config override hash mismatch")
    encoded = base64.b64encode(payload).decode()
    script = f'''python3 - <<'PY'
import base64, hashlib, json
from pathlib import Path
root = Path("/workspace/model-awq")
data = base64.b64decode("{encoded}")
if hashlib.sha256(data).hexdigest() != "{expected_sha256}": raise SystemExit("override hash mismatch")
(root / "config.json").write_bytes(data)
lines = (root / "model-files.sha256").read_text().splitlines()
digest = hashlib.sha256(data).hexdigest()
(root / "model-files.sha256").write_text("\\n".join((f"{{digest}}  config.json" if line.endswith("  config.json") else line) for line in lines) + "\\n")
manifest_path = root / "model-files-manifest.json"
manifest = json.loads(manifest_path.read_text())
for row in manifest["files"]:
    if row["path"] == "config.json": row.update({{"bytes": len(data), "sha256": digest}})
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\\n")
(root / ".campaign-integrity-v1").unlink(missing_ok=True)
PY'''
    result = run_ssh(ip, key, script, timeout=30)
    if result.returncode:
        raise RuntimeError("remote config override failed")


def resolve_control_summary(path: Path, name: str) -> str:
    try:
        summary = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"control summary is unreadable: {error}") from error
    instance_id = summary.get("instance_id")
    if summary.get("retained_for_next_experiment") is not True:
        raise RuntimeError("control summary does not retain an instance")
    if not isinstance(instance_id, str) or not instance_id:
        raise RuntimeError("control summary lacks a retained instance ID")
    if summary.get("final_instance_count") != 1 or summary.get("final_disk_count") != 1:
        raise RuntimeError("control summary does not describe exactly one retained instance and disk")
    instances = list_items("instance")
    matching_instances = [row for row in instances if metadata_id(row) == instance_id and metadata_name(row) == name]
    if len(instances) != 1 or len(matching_instances) != 1:
        raise RuntimeError("retained instance inventory drifted from control summary")
    disks = list_items("disk")
    matching_disks = [row for row in disks if metadata_name(row) == name + "-boot"]
    if len(disks) != 1 or len(matching_disks) != 1:
        raise RuntimeError("retained disk inventory drifted from control summary")
    return instance_id


def reuse_staged_runtime(args: argparse.Namespace) -> bool:
    return bool(
        args.reuse_staged_runtime
        or args.reuse_staged_runtime_and_checkpoint
    )


def run(args: argparse.Namespace) -> int:
    if args.control_summary is not None:
        args.instance_id = resolve_control_summary(args.control_summary, args.name)
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    events = out / "events.jsonl"
    identities = validate_local_model(args.local_model_dir)
    if args.selective_w4_scope not in VALID_SCOPES:
        raise RuntimeError("unknown selective-W4 scope")
    if args.selective_w4_scope != "combined" and not args.head_shared_w4:
        raise RuntimeError("an isolated selective-W4 recovery requires selective-W4 mode")
    frontier_concurrencies = validate_frontier_concurrencies(tuple(int(value) for value in args.frontier_concurrencies.split(",")), args.max_num_seqs)
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
    science_deadline = deadline - ARTIFACT_RESERVE_SECONDS
    disk_name = args.name + "-boot"
    artifact_hash = None
    manifest_files = 0
    allocation_result = None
    measured_useful_gpu_seconds = None
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
        if args.config_override is not None:
            replace_remote_config(ip, args.ssh_key, args.config_override, args.config_override_sha256)
            emit(events, "config_override_applied", sha256=args.config_override_sha256)
        if not reuse_staged_runtime(args):
            preflight = HERE / "vllm_preflight.py"
            scp_to(ip, args.ssh_key, [preflight], "/home/glmrunner/input/")
            scp_to(ip, args.ssh_key, [args.local_model_dir / "config.json"], "/home/glmrunner/input/model-config-only/")
            bootstrap = run_ssh(ip, args.ssh_key, "bash -s", timeout=900, input_text=build_host_bootstrap())
            (out / "repair-01-bootstrap.stdout.log").write_text(bootstrap.stdout)
            (out / "repair-01-bootstrap.stderr.log").write_text(bootstrap.stderr)
            if bootstrap.returncode:
                raise RuntimeError("repair-01 derived runtime preflight failed")
            emit(events, "repair_01_cuda_transformers_preflight_passed", transformers_revision=TRANSFORMERS_REVISION)
        else:
            emit(events, "repair_01_reused_verified_runtime")

        quality_dir = HERE.parent / "quality"
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory)
            for source in (HERE / "remote_vllm_awq_smoke.sh", HERE / "vllm_batched_runner.py", HERE / "vllm_methodology_runner.py", HERE / "vllm_decode_kernel_patch.py"):
                shutil.copy2(source, staging / source.name)
            binder = HERE.parent.parent / "research_lab" / "projects" / "full47_official_selective_w4_cuda_endpoint" / "official_head_shared_w4_bind.py"
            oracle = HERE.parent.parent / "research_lab" / "projects" / "full47_official_selective_w4_cuda_endpoint" / "official_head_shared_w4_cuda_oracle.py"
            if args.head_shared_w4:
                shutil.copy2(binder, staging / binder.name)
                shutil.copy2(oracle, staging / oracle.name)
            control = staging / "bf16-control-responses.jsonl"
            archive_path = HERE.parent / "allocations" / "nebius_h100_complete_stock_v13" / "stock_no_cache_fcfs-artifact.tar.gz"
            with tarfile.open(archive_path, "r:gz") as bundle:
                member = next(row for row in bundle.getmembers() if row.name.endswith("/quality-stock_no_cache_fcfs-responses.jsonl"))
                handle = bundle.extractfile(member)
                if handle is None:
                    raise RuntimeError("BF16 control responses missing")
                control.write_bytes(handle.read())
            run_ssh(ip, args.ssh_key, "mkdir -p /home/glmrunner/input/tokenizer /home/glmrunner/input/quality", timeout=30)
            extras = [staging / binder.name, staging / oracle.name] if args.head_shared_w4 else []
            scp_to(ip, args.ssh_key, [staging / "remote_vllm_awq_smoke.sh", staging / "vllm_batched_runner.py", staging / "vllm_methodology_runner.py", staging / "vllm_decode_kernel_patch.py", control, *extras], "/home/glmrunner/input/")
            tokenizer_files = [args.reference_tokenizer_dir / name for name in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja")]
            scp_to(ip, args.ssh_key, tokenizer_files, "/home/glmrunner/input/tokenizer/")
            scp_to(ip, args.ssh_key, required_quality_files(quality_dir), "/home/glmrunner/input/quality/")
        emit(events, "repair_01_inputs_staged")
        if not args.reuse_staged_runtime_and_checkpoint:
            probe_hash = probe_transfer(ip, args.ssh_key)
            emit(events, "repair_01_tiny_transfer_probe_passed", sha256=probe_hash)
            with measured_phase(events, "checkpoint_transfer"):
                available = int(science_deadline - time.time() - 300)
                if available < 60:
                    raise RuntimeError("retained session lacks time for checkpoint transfer and model load")
                transfer_result = transfer_checkpoint(
                    ip,
                    args.ssh_key,
                    args.local_model_dir,
                    "/workspace/model-awq",
                    timeout_seconds=min(
                        transfer_timeout_seconds(int(identities["model_weight_bytes"])),
                        available,
                    ),
                )
            emit(events, "repair_01_verified_awq_transferred", **transfer_result.__dict__)
        else:
            emit(events, "repair_01_reused_verified_runtime_and_checkpoint")

        with measured_phase(events, "scientific_workload"):
            remote = run_ssh(ip, args.ssh_key, build_container_command(args.repair_spec_sha256, int(science_deadline), dtype=args.dtype, max_num_batched_tokens=args.max_num_batched_tokens, max_num_seqs=args.max_num_seqs, frontier_concurrencies=frontier_concurrencies, decode_block_n=args.decode_block_n, decode_num_stages=args.decode_num_stages, num_kv_splits=args.num_kv_splits, kv_cache_dtype=args.kv_cache_dtype, head_shared_w4=args.head_shared_w4, selective_w4_scope=args.selective_w4_scope), timeout=max(60, int(deadline - time.time())))
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
        measured_useful_gpu_seconds = useful_gpu_seconds(allocation_result)
        outcome, background_pass = execution_outcome(
            remote.returncode,
            allocation_result,
            args.background_arm_envelope_seconds,
            allow_deferred_absolute_quality_failure=args.allow_deferred_absolute_quality_failure,
        )
        emit(events, "repair_01_artifact_retrieved", sha256=artifact_hash, manifest_files=manifest_files, outcome=outcome, background_pass=background_pass)
        if allocation_has_harness_error(allocation_result):
            outcome = "FAIL"
            raise RuntimeError("typed allocation result contains a harness error")
        retain_after_result = args.keep_instance_after_result and background_pass
    except Exception as error:
        error_record = {"type": type(error).__name__, "message": str(error)}
        emit(events, "repair_01_error", **error_record)
        if allocation_result is None or allocation_has_harness_error(allocation_result):
            hold_for_repair_decision(out, events, deadline, args.repair_window_seconds)
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
            "useful_gpu_seconds": measured_useful_gpu_seconds,
            "background_pass": background_pass if allocation_result is not None else False,
            "background_arm_envelope_seconds": args.background_arm_envelope_seconds,
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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--instance-id")
    source.add_argument("--control-summary", type=Path)
    parser.add_argument("--parent-experiment-id", required=True)
    parser.add_argument("--session-deadline-epoch", type=float, required=True)
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--local-model-dir", type=Path, required=True)
    parser.add_argument("--reference-tokenizer-dir", type=Path, required=True)
    parser.add_argument("--repair-spec-sha256", required=True)
    parser.add_argument("--config-override", type=Path)
    parser.add_argument("--config-override-sha256")
    parser.add_argument("--reuse-staged-runtime", action="store_true")
    parser.add_argument("--reuse-staged-runtime-and-checkpoint", action="store_true")
    parser.add_argument("--keep-instance-after-result", action="store_true")
    parser.add_argument("--dtype", choices=("bfloat16", "float16"), default="bfloat16")
    parser.add_argument("--max-num-batched-tokens", type=int, default=32768)
    parser.add_argument("--max-num-seqs", type=int, choices=(8, 16, 32, 36, 40), default=8)
    parser.add_argument("--frontier-concurrencies", default="1,8")
    parser.add_argument("--decode-block-n", type=int, choices=(32, 64), default=32)
    parser.add_argument("--decode-num-stages", type=int, choices=(1, 2), default=2)
    parser.add_argument("--num-kv-splits", type=int, choices=(4, 8, 16), default=4)
    parser.add_argument("--kv-cache-dtype", choices=("auto", "fp8_e4m3"), default="auto")
    parser.add_argument("--repair-window-seconds", type=int, choices=range(0, 601), default=0)
    parser.add_argument("--background-arm-envelope-seconds", type=int, default=300)
    parser.add_argument("--allow-deferred-absolute-quality-failure", action="store_true")
    parser.add_argument("--head-shared-w4", action="store_true")
    parser.add_argument("--selective-w4-scope", choices=VALID_SCOPES, default="combined")
    args = parser.parse_args()
    if (args.config_override is None) != (args.config_override_sha256 is None):
        parser.error("--config-override and --config-override-sha256 must be paired")
    if args.background_arm_envelope_seconds <= 0:
        parser.error("--background-arm-envelope-seconds must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
