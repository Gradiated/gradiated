#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import statistics
import subprocess
import tempfile
from datetime import datetime, timezone


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
RUNTIME = pathlib.Path("/root/workspace/.agents/runtime/sglang-v0.5.13-source")
ATTRIBUTION = (
    PROJECT.parent
    / "gemma4_h200_dense_fp8_linear_schedule/inputs/evidence/ATTRIBUTION.json"
)
PROFILE_SQLITE = (
    PROJECT.parent
    / "gemma4_h200_v0513_fp8_qkv_residual_profile"
    / "artifacts/residual-profile-20260720t0821z/control-profile.sqlite"
)
FIXED_FLOOR = (
    PROJECT.parent
    / "gemma4_h200_fixed_floor_crossop_executor"
    / "FIXED_FLOOR_CROSSOP_OFFLINE_TERMINAL.json"
)
OBSERVED_SCHEDULE_BATCH = (
    PROJECT.parent
    / "gemma4_h200_scheduler_gap_pipeline_overlap"
    / "artifacts/scheduler-gap-rebind-20260723t0258z/observed-source/schedule_batch.py"
)
UPSTREAM_SCHEDULE_BATCH = (
    RUNTIME / "python/sglang/srt/managers/schedule_batch.py"
)
COMMON = RUNTIME / "python/sglang/srt/mem_cache/common.py"
SCHEDULER = RUNTIME / "python/sglang/srt/managers/scheduler.py"
RESULT_PROCESSOR = (
    RUNTIME
    / "python/sglang/srt/managers/scheduler_components/batch_result_processor.py"
)
CAMPAIGN = LAB / "CAMPAIGN.md"

LOCKED_SERVICE_SECONDS_PER_REQUEST = 0.625149101968745
TARGET_SECONDS_PER_REQUEST = 0.500119281574996
REQUESTS = 32
DECODE_STEPS = 358


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def manifest(path: pathlib.Path) -> dict[str, object]:
    return {
        "path": os.path.relpath(path.resolve(), PROJECT),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def reconstruct_gap_signature() -> dict[str, object]:
    attribution = json.loads(ATTRIBUTION.read_text())
    window_start = int(attribution["window"]["start_ns"])
    window_end = int(attribution["window"]["end_ns"])
    decode_start = window_start + round(
        float(attribution["phases"]["prefill"]["seconds"]) * 1e9
    )
    connection = sqlite3.connect(f"file:{PROFILE_SQLITE}?mode=ro", uri=True)
    strings = dict(connection.execute("select id,value from StringIds"))

    covered = [
        (max(int(start), window_start), min(int(end), window_end))
        for start, end in connection.execute(
            "select start,end from CUPTI_ACTIVITY_KIND_KERNEL "
            "where end>? and start<?",
            (window_start, window_end),
        )
    ]
    for start, end, name_id in connection.execute(
        "select start,end,nameId from CUPTI_ACTIVITY_KIND_RUNTIME "
        "where end>? and start<?",
        (window_start, window_end),
    ):
        lowered = str(strings[int(name_id)]).lower()
        if (
            "synchron" in lowered
            or "streamwait" in lowered
            or "eventquery" in lowered
            or "launch" in lowered
        ):
            covered.append(
                (max(int(start), window_start), min(int(end), window_end))
            )
    merged: list[list[int]] = []
    for start, end in sorted(covered):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    gaps: list[tuple[int, int]] = []
    cursor = window_start
    for start, end in merged:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < window_end:
        gaps.append((cursor, window_end))

    kernels = [
        (
            int(start),
            int(end),
            str(strings[int(short_name)]),
            int(grid_x),
            int(block_x),
        )
        for start, end, short_name, grid_x, block_x in connection.execute(
            "select start,end,shortName,gridX,blockX "
            "from CUPTI_ACTIVITY_KIND_KERNEL "
            "where streamId=37 and start>=? and start<? order by start",
            (decode_start, window_end),
        )
    ]

    def scheduler_gap_overlap(start: int, end: int) -> int:
        total = 0
        for gap_start, gap_end in gaps:
            if gap_start >= end:
                break
            if gap_end > start:
                total += max(
                    0, min(end, gap_end) - max(start, gap_start, decode_start)
                )
        return total

    matched = []
    signature = ("vectorized_elementwise_kernel", 1, 128)
    for previous, following in zip(kernels, kernels[1:]):
        if previous[2:] == signature and following[2:] == signature:
            overlap = scheduler_gap_overlap(previous[1], following[0])
            if overlap:
                matched.append(overlap)
    decode_gap_ns = sum(
        max(0, min(end, window_end) - max(start, decode_start))
        for start, end in gaps
        if end > decode_start
    )
    expected_decode_gap_ns = round(
        next(
            row["seconds"]
            for row in attribution["phases"]["decode"]["boundaries"]
            if row["boundary"] == "scheduler_gap"
        )
        * 1e9
    )
    median_ns = int(statistics.median(matched))
    median_capped_ns = sum(min(value, median_ns) for value in matched)
    if decode_gap_ns != expected_decode_gap_ns:
        raise RuntimeError(
            f"decode_gap_reconstruction_mismatch:{decode_gap_ns}:"
            f"{expected_decode_gap_ns}"
        )
    if len(matched) != 714:
        raise RuntimeError(f"decode_metadata_signature_count:{len(matched)}")
    return {
        "decode_start_ns": decode_start,
        "decode_end_ns": window_end,
        "decode_scheduler_gap_ns": decode_gap_ns,
        "signature_stream": 37,
        "signature": {
            "predecessor": {
                "short_name": signature[0],
                "grid_x": signature[1],
                "block_x": signature[2],
            },
            "consumer": {
                "short_name": signature[0],
                "grid_x": signature[1],
                "block_x": signature[2],
            },
            "count": len(matched),
            "raw_overlap_ns": sum(matched),
            "median_ns": median_ns,
            "median_capped_overlap_ns": median_capped_ns,
            "mapping": (
                "Source-backed and geometry-correlated: overlap-mode "
                "ScheduleBatch.prepare_for_decode emits two c32 length-vector "
                "adds after req_to_token publication once per steady decode step."
            ),
            "uncertainty": (
                "Kernel short names are not source symbols. The raw overlap has "
                "long cross-stream outliers, so the bound uses per-gap median "
                "capping and then a 50% realization haircut."
            ),
        },
    }


def validate_installation() -> dict[str, object]:
    with tempfile.TemporaryDirectory(
        prefix="decode-task-graph-", dir=PROJECT
    ) as raw:
        root = pathlib.Path(raw) / "python"
        managers = root / "sglang/srt/managers"
        cache = root / "sglang/srt/mem_cache"
        managers.mkdir(parents=True)
        cache.mkdir(parents=True)
        shutil.copyfile(OBSERVED_SCHEDULE_BATCH, managers / "schedule_batch.py")
        shutil.copyfile(COMMON, cache / "common.py")
        command = [
            "python3",
            str(PROJECT / "install_decode_scheduler_task_graph.py"),
            "--sglang-python",
            str(root),
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=30, check=False
        )
        if result.returncode:
            raise RuntimeError(
                f"installer_failed:{result.returncode}:{result.stderr[-2000:]}"
            )
        patched_schedule = managers / "schedule_batch.py"
        patched_common = cache / "common.py"
        candidate_copy = managers / "decode_scheduler_task_graph.py"
        compile_result = subprocess.run(
            [
                "python3",
                "-m",
                "py_compile",
                str(patched_schedule),
                str(patched_common),
                str(candidate_copy),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if compile_result.returncode:
            raise RuntimeError(
                f"patched_compile_failed:{compile_result.stderr[-2000:]}"
            )
        schedule_text = patched_schedule.read_text()
        common_text = patched_common.read_text()
        claims = {
            "candidate_imported": (
                "commit_schedule_batch_decode_metadata" in schedule_text
            ),
            "allocator_decision_retained": (
                "alloc_for_decode(" in schedule_text
                and "publish_req_to_token=not task_graph_enabled" in schedule_text
            ),
            "stock_fallback_retained": (
                "elif self.enable_overlap:" in schedule_text
                and "self.seq_lens = self.seq_lens + 1" in schedule_text
            ),
            "publication_deferred_only_on_candidate": (
                "if publish_req_to_token:" in common_text
            ),
            "candidate_module_materialized": candidate_copy.exists(),
        }
        if not all(claims.values()):
            raise RuntimeError(f"installation_claim_failed:{claims}")
        return {
            "passed": True,
            "claims": claims,
            "patched_schedule_batch_sha256": sha256(patched_schedule),
            "patched_common_sha256": sha256(patched_common),
            "candidate_copy_sha256": sha256(candidate_copy),
        }


def main() -> None:
    gap = reconstruct_gap_signature()
    installation = validate_installation()
    selected_gap_seconds = (
        gap["signature"]["median_capped_overlap_ns"] / 1e9
    )
    predicted_eliminated_seconds = selected_gap_seconds * 0.5
    profile_absolute_reduction = predicted_eliminated_seconds / REQUESTS
    profile_service = json.loads(ATTRIBUTION.read_text())[
        "profile_control_service_seconds_per_request"
    ]
    candidate_source = PROJECT / "decode_scheduler_task_graph.py"
    consumer = PROJECT / "exact_h200_consumer.py"
    installer = PROJECT / "install_decode_scheduler_task_graph.py"
    builder = PROJECT / "build_offline_terminal.py"
    candidate_hash = sha256(candidate_source)
    command = (
        f"PYTHONPATH={PROJECT} python3 {consumer} "
        f"--output {PROJECT}/artifacts/h200_exact_consumer/TERMINAL.json "
        "--sglang-python /sgl-workspace/sglang/python "
        f"--expected-candidate-sha256 {candidate_hash} "
        "--warmups 3 --iterations 15"
    )
    result = {
        "schema_version": 1,
        "terminal_type": "decode_scheduler_task_graph_offline_positive",
        "status": "complete",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": PROJECT.name,
        "classification": (
            "source_complete_positive_small_bound_requires_exact_h200_component"
        ),
        "answer": (
            "One exact one-step boundary is source-complete: retain host KV-slot "
            "selection, then replace req_to_token publication and both device "
            "length-vector advances with one c32 Triton task. The conservative "
            "offline bound is positive but small and cannot independently reach "
            "the locked economic target."
        ),
        "scope": {
            "model": "google/gemma-4-31B-it",
            "model_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "runtime": "SGLang v0.5.13",
            "sglang_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "image": (
                "docker.io/lmsysorg/sglang@sha256:"
                "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
            ),
            "target_gpu": "NVIDIA H200 SXM, SM90, 132 SMs",
            "workload": {
                "concurrency": 32,
                "requests": 32,
                "prompt_tokens_per_request": 4214,
                "completion_tokens_per_request": 358,
                "fresh_prompt_tokens": 117728,
                "cached_prompt_tokens": 17120,
            },
            "provider_or_gpu_used_this_turn": False,
            "ssh_or_endpoint_used_this_turn": False,
            "checkpoint_shards_read_or_copied_this_turn": False,
            "actual_spend_usd": 0.0,
        },
        "direct_inputs": {
            "attribution": manifest(ATTRIBUTION),
            "profile_sqlite": manifest(PROFILE_SQLITE),
            "fixed_floor_terminal": manifest(FIXED_FLOOR),
            "campaign": manifest(CAMPAIGN),
            "upstream_schedule_batch": manifest(UPSTREAM_SCHEDULE_BATCH),
            "observed_retained_schedule_batch": manifest(
                OBSERVED_SCHEDULE_BATCH
            ),
            "allocator_common": manifest(COMMON),
            "scheduler": manifest(SCHEDULER),
            "result_processor": manifest(RESULT_PROCESSOR),
        },
        "selected_boundary": {
            "single_candidate": True,
            "name": "allocator_result_to_forward_metadata_task",
            "phase": "decode only",
            "producer": {
                "symbol": (
                    "alloc_for_decode -> BaseTokenToKVPoolAllocator.alloc/"
                    "alloc_decode"
                ),
                "ownership": (
                    "Host allocator remains authoritative for eviction, free-list "
                    "movement, and unique out_cache_loc selection."
                ),
                "output": "c32 int64 out_cache_loc",
            },
            "baseline_tasks": [
                "out_cache_loc.to(torch.int32)",
                "ReqToTokenPool.write[(req_pool_indices, seq_lens)]",
                "seq_lens + 1",
                "orig_seq_lens + 1",
            ],
            "candidate_task": (
                "_commit_decode_metadata publishes the allocator-selected slot "
                "and writes next int64 seq_lens and int32 orig_seq_lens in one CTA."
            ),
            "first_decision_bearing_consumer": (
                "ForwardBatch.init_new and the attention backend consume "
                "req_to_token[req_pool_indices, seq_lens-1], seq_lens, and "
                "orig_seq_lens after the existing forward_stream waits on "
                "schedule_stream."
            ),
            "excluded_mechanisms": [
                "No multi-token model replay or continuous-decode step.",
                "No host sampling/result boundary removal.",
                "No allocator, cache, request, or KV-slot ownership change.",
                "No synchronization removal or credit.",
                "No penalty-snapshot overlap replay.",
            ],
        },
        "trace_to_source": {
            "evidence_class": "measured_geometry_plus_source_backed_mapping",
            **gap,
            "runtime_chain": [
                "Scheduler.event_loop_overlap",
                "Scheduler.get_next_batch_to_run",
                "Scheduler.update_running_batch",
                "ScheduleBatch.prepare_for_decode",
                "alloc_for_decode",
                "ReqToTokenPool.write",
                "ForwardBatch.init_new",
            ],
            "synchronization_exclusion": (
                "The reconstruction uses the profile's mutually exclusive rule. "
                "cudaStreamSynchronize, stream/event waits, and event queries stay "
                "in synchronization and contribute zero to this bound."
            ),
        },
        "physical_model": {
            "geometry": {
                "batch_rows": 32,
                "req_to_token_dtype": "int32",
                "req_pool_indices_dtype": "int64",
                "seq_lens_dtype": "int64",
                "orig_seq_lens_dtype": "int32",
                "out_cache_loc_dtype": "int64",
                "candidate_grid": [1, 1, 1],
                "candidate_threads": 32,
                "h200_sms": 132,
                "grid_waves": 1,
            },
            "useful_integer_operations_per_step": 64,
            "compulsory_bytes_per_step": {
                "reads": 896,
                "writes": 512,
                "total": 1408,
            },
            "baseline_device_tasks_per_step": 4,
            "candidate_device_tasks_per_step": 1,
            "eliminated_device_tasks_per_358_step_window": 1074,
            "roofline": (
                "One warp and 1.408 KiB useful traffic cannot occupy H200; both "
                "paths are launch/host-dispatch limited. The candidate targets "
                "dispatch gaps, not SM throughput or synchronization."
            ),
            "prediction": (
                "The selected two repeated host-dispatch gaps collapse into the "
                "single task submission; integer work and mapping bytes remain."
            ),
            "falsifier": (
                "On H200, reject if any mapping/length/ownership consumer differs, "
                "if the candidate does not execute one device task per step, or if "
                "the 358-step warm median is non-positive."
            ),
        },
        "correctness_and_ownership_contract": {
            "semantics": "bit-exact metadata/state preserving",
            "required_cases": [1, 31, 32],
            "required_decode_steps": 358,
            "requirements": [
                "Exact req_to_token contents after every unique slot publication.",
                "Exact int64 seq_lens and int32 orig_seq_lens.",
                "Immediate consumer returns the allocator's last slot for every row.",
                "Unique request rows and unique slot ownership.",
                "Two output-buffer sets; existing schedule-to-forward stream wait and "
                "two-iteration overlap lifetime remain unchanged.",
                "Fallback on unsupported dtype/layout/device/shape.",
                "No credit for CUDA event or stream synchronization.",
            ],
        },
        "complete_bound": {
            "profile_scope_discontinuity": (
                "The 0.766971497 s decode gap comes from an older scope-matched "
                "0.7051819141250064 s/request control. It is a discovery prior, "
                "not a transferable endpoint measurement."
            ),
            "measured_decode_scheduler_gap_seconds_per_32_request_window": (
                gap["decode_scheduler_gap_ns"] / 1e9
            ),
            "all_decode_gap_ideal_upper_bound_seconds_per_request": (
                gap["decode_scheduler_gap_ns"] / 1e9 / REQUESTS
            ),
            "selected_signature_median_capped_seconds_per_window": (
                selected_gap_seconds
            ),
            "realization_haircut": 0.5,
            "predicted_eliminated_seconds_per_window": (
                predicted_eliminated_seconds
            ),
            "predicted_absolute_reduction_seconds_per_request": (
                profile_absolute_reduction
            ),
            "profile_control_seconds_per_request": profile_service,
            "profile_scope_candidate_bound_seconds_per_request": (
                profile_service - profile_absolute_reduction
            ),
            "locked_qualified_seconds_per_request": (
                LOCKED_SERVICE_SECONDS_PER_REQUEST
            ),
            "locked_reanchored_candidate_bound_seconds_per_request": (
                LOCKED_SERVICE_SECONDS_PER_REQUEST - profile_absolute_reduction
            ),
            "locked_target_seconds_per_request": TARGET_SECONDS_PER_REQUEST,
            "locked_request_reduction_fraction": (
                profile_absolute_reduction / LOCKED_SERVICE_SECONDS_PER_REQUEST
            ),
            "target_reached_by_candidate_alone": (
                LOCKED_SERVICE_SECONDS_PER_REQUEST - profile_absolute_reduction
                <= TARGET_SECONDS_PER_REQUEST
            ),
            "even_all_decode_scheduler_gap_reaches_target": (
                LOCKED_SERVICE_SECONDS_PER_REQUEST
                - gap["decode_scheduler_gap_ns"] / 1e9 / REQUESTS
                <= TARGET_SECONDS_PER_REQUEST
            ),
        },
        "implementation": {
            "source_complete": True,
            "source_manifest": [
                manifest(candidate_source),
                manifest(installer),
                manifest(consumer),
                manifest(builder),
            ],
            "installation_validation": installation,
            "exact_source_paths": {
                "candidate": str(candidate_source),
                "installer": str(installer),
                "runtime_schedule_batch": (
                    "/sgl-workspace/sglang/python/sglang/srt/managers/"
                    "schedule_batch.py"
                ),
                "runtime_allocator": (
                    "/sgl-workspace/sglang/python/sglang/srt/mem_cache/common.py"
                ),
            },
        },
        "h200_consumer": {
            "type": "command",
            "command": command,
            "working_directory": str(PROJECT),
            "expected_terminal": (
                f"{PROJECT}/artifacts/h200_exact_consumer/TERMINAL.json"
            ),
            "required_environment": (
                "Pinned SGLang image with this immutable project snapshot mounted "
                "at the same absolute path; a later director-authorized H200 pool "
                "claim is required outside this command."
            ),
            "science_start": (
                "INVOCATION_STATE.json changes candidate_cuda_invocation_started "
                "to true only after H200 and source identities pass."
            ),
        },
    }
    atomic_json(PROJECT / "DECODE_SCHEDULER_TASK_GRAPH_OFFLINE_TERMINAL.json", result)
    atomic_json(
        PROJECT / "OFFLINE_VALIDATION.json",
        {
            "schema_version": 1,
            "passed": True,
            "gap_signature": gap,
            "installation": installation,
            "candidate_sha256": candidate_hash,
            "terminal_sha256": sha256(
                PROJECT / "DECODE_SCHEDULER_TASK_GRAPH_OFFLINE_TERMINAL.json"
            ),
        },
    )


if __name__ == "__main__":
    main()
