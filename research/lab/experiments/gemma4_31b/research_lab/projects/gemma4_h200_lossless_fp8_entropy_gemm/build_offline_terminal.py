#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
REPO = pathlib.Path("/root/workspace")
CODEC_RESULT = PROJECT / "FULL_CHECKPOINT_HUFFMAN12_RESULT.json"
PREREGISTRATION = PROJECT / "PREREGISTERED_CODEC.json"
SOURCE_STATISTICS = (
    PROJECT.parent
    / "gemma4_mi355x_lossless_fp8_weight_stream_codesign"
    / "FULL_CHECKPOINT_STREAM_RESULT.json"
)
DENSE_PROJECT = PROJECT.parent / "gemma4_h200_dense_fp8_linear_schedule"
ATTRIBUTION = DENSE_PROJECT / "inputs" / "evidence" / "ATTRIBUTION.json"
SHAPE_MAP = DENSE_PROJECT / "inputs" / "evidence" / "FP8_LINEAR_SHAPE_MAP.json"
DISPATCH_SOURCE = (
    DENSE_PROJECT
    / "inputs"
    / "sgl-kernel-v0513"
    / "csrc"
    / "cutlass_extensions"
    / "gemm"
    / "fp8_gemm_sm90_dispatch.cuh"
)
ACCELERATOR_INVENTORY = REPO / "research" / "factory" / "data" / "accelerator_inventory.json"
CAMPAIGN = LAB / "CAMPAIGN.md"
OUTPUT = PROJECT / "LOSSLESS_FP8_ENTROPY_GEMM_OFFLINE_TERMINAL.json"

QUALIFIED_SECONDS = 0.625149101968745
TARGET_SECONDS = 0.500119281574996
REQUESTS = 32
LAYERS = 60


def sha256_file(path: pathlib.Path, chunk_bytes: int = 64 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        while data := handle.read(chunk_bytes):
            digest.update(data)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def relative(path: pathlib.Path) -> str:
    return str(path.relative_to(PROJECT)) if path.is_relative_to(PROJECT) else str(path)


def main() -> int:
    codec = json.loads(CODEC_RESULT.read_text())
    source = json.loads(SOURCE_STATISTICS.read_text())
    attribution = json.loads(ATTRIBUTION.read_text())
    shape_map = json.loads(SHAPE_MAP.read_text())
    inventory = json.loads(ACCELERATOR_INVENTORY.read_text())
    accelerator = next(
        row for row in inventory["accelerators"] if row["id"] == "nvidia-h200-sxm"
    )
    architecture = inventory["architecture_profiles"][
        accelerator["architecture_profile_id"]
    ]
    fp8_boundary = next(
        row for row in attribution["boundaries"] if row["boundary"] == "fp8_linear"
    )
    measured_linear_seconds = fp8_boundary["seconds"] / REQUESTS
    fixed_seconds = QUALIFIED_SECONDS - measured_linear_seconds
    compression_ratio = codec["storage"]["compression_ratio"]
    zero_decoder_linear_seconds = measured_linear_seconds * compression_ratio
    zero_decoder_complete_seconds = fixed_seconds + zero_decoder_linear_seconds
    required_compressed_path_ratio = (
        TARGET_SECONDS - fixed_seconds
    ) / measured_linear_seconds
    entropy_ratio = source["aggregate"]["all_block_entropy_bits"]["mean"] / 8
    entropy_zero_metadata_seconds = fixed_seconds + measured_linear_seconds * entropy_ratio

    launches_per_family = shape_map["projection_families"][0]["launches"]
    stream_passes = launches_per_family / LAYERS
    raw_bytes_per_request = (
        codec["coverage"]["runtime_fp8_bytes"] * stream_passes / REQUESTS
    )
    encoded_bytes_per_request = raw_bytes_per_request * compression_ratio
    saved_bytes_per_request = raw_bytes_per_request - encoded_bytes_per_request
    optimistic_nonoverlap_budget = measured_linear_seconds * (1 - compression_ratio)
    measured_boundary_raw_decode_threshold = (
        raw_bytes_per_request / optimistic_nonoverlap_budget
    )
    measured_boundary_input_threshold = (
        encoded_bytes_per_request / optimistic_nonoverlap_budget
    )
    peak_hbm_bytes_per_second = accelerator["memory"]["bandwidth_gb_s"] * 1e9
    peak_serial_raw_decode_threshold = peak_hbm_bytes_per_second / (
        1 - compression_ratio
    )
    peak_full_overlap_raw_decode_threshold = (
        peak_hbm_bytes_per_second / compression_ratio
    )

    dominant = shape_map["dominant_kernel"]
    register_file_32bit = architecture["register_file_per_unit_kib"] * 1024 // 4
    current_registers_per_cta = (
        dominant["registers_per_thread"] * dominant["threads_per_cta"]
    )
    register_headroom = register_file_32bit - current_registers_per_cta
    threads_with_decoder_warp = dominant["threads_per_cta"] + 32
    uniform_register_ceiling = register_file_32bit // threads_with_decoder_warp
    decoder_warp_register_ceiling = register_headroom // 32
    shared_limit_bytes = architecture["max_local_memory_per_block_kib"] * 1024
    shared_headroom = shared_limit_bytes - dominant["dynamic_shared_memory_bytes"]
    double_tile_bytes = 2 * 32 * 128
    decode_table_bytes = codec["codec"]["decode_table"]["entries"] * codec["codec"][
        "decode_table"
    ]["entry_bytes"]
    staged_shared_bytes = double_tile_bytes + decode_table_bytes

    direct_inputs = {
        "project": {
            "path": relative(PROJECT / "PROJECT.md"),
            "sha256": sha256_file(PROJECT / "PROJECT.md"),
        },
        "campaign": {
            "path": relative(CAMPAIGN),
            "sha256": sha256_file(CAMPAIGN),
        },
        "preregistration": {
            "path": relative(PREREGISTRATION),
            "sha256": sha256_file(PREREGISTRATION),
        },
        "full_checkpoint_statistics": {
            "path": relative(SOURCE_STATISTICS),
            "sha256": sha256_file(SOURCE_STATISTICS),
        },
        "full_codec_measurement": {
            "path": relative(CODEC_RESULT),
            "sha256": sha256_file(CODEC_RESULT),
        },
        "h200_attribution": {
            "path": relative(ATTRIBUTION),
            "sha256": sha256_file(ATTRIBUTION),
        },
        "h200_shape_map": {
            "path": relative(SHAPE_MAP),
            "sha256": sha256_file(SHAPE_MAP),
        },
        "h200_dispatch_source": {
            "path": relative(DISPATCH_SOURCE),
            "sha256": sha256_file(DISPATCH_SOURCE),
        },
        "accelerator_inventory": {
            "path": relative(ACCELERATOR_INVENTORY),
            "sha256": sha256_file(ACCELERATOR_INVENTORY),
        },
        "cpu_reference": {
            "runner_path": "run_offline_codec.py",
            "runner_sha256": sha256_file(PROJECT / "run_offline_codec.py"),
            "codec_source_path": "huffman_tile_codec.cpp",
            "codec_source_sha256": sha256_file(PROJECT / "huffman_tile_codec.cpp"),
            "codec_binary_path": "artifacts/full-checkpoint-huffman12/huffman_tile_codec.so",
            "codec_binary_sha256": sha256_file(
                PROJECT / "artifacts" / "full-checkpoint-huffman12" / "huffman_tile_codec.so"
            ),
        },
        "checkpoint_shards": codec["bindings"]["checkpoint_shards"],
    }

    terminal = {
        "schema_version": 1,
        "project": PROJECT.name,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "classification": "typed_none",
        "decision": (
            "Close tensor_huffman12_row32_tile16_v1 without H200 spend. "
            "The format is lossless and materially compresses the full runtime "
            "FP8 stream, but even a zero-cost decoder leaves the qualified "
            "request above the locked campaign target."
        ),
        "codec": {
            "id": "tensor_huffman12_row32_tile16_v1",
            "preregistered": True,
            "codec_family_swept": False,
            "tile_random_access": True,
            "escape_free_256_symbol_coverage": True,
            "maximum_code_length": 12,
            "tile_shape_k_n": [32, 128],
            "row_streams_per_tile": 32,
            "tile_alignment_bytes": 16,
            "decode_table_entries_per_module": 4096,
        },
        "full_checkpoint_measurement": {
            "evidence_class": "measured",
            "runtime_modules": codec["coverage"]["runtime_modules"],
            "runtime_fp8_bytes": codec["coverage"]["runtime_fp8_bytes"],
            "tile_count": codec["coverage"]["tile_count"],
            "decoded_bytes": codec["coverage"]["decoded_bytes"],
            "mismatched_bytes": codec["coverage"]["mismatched_bytes"],
            "bitwise_equal": codec["coverage"]["bitwise_equal"],
            "encoded_bytes_all_overheads": codec["storage"]["encoded_bytes"],
            "bytes_avoided": codec["storage"]["bytes_avoided"],
            "compression_ratio": compression_ratio,
            "bits_per_weight_all_overheads": codec["storage"][
                "bits_per_weight_all_overheads"
            ],
            "payload_bits_per_weight_before_row_and_metadata_overheads": (
                sum(row["code"]["weighted_payload_bits"] for row in codec["modules"])
                / codec["coverage"]["runtime_fp8_bytes"]
            ),
            "overhead_bytes": codec["storage"]["encoded_bytes"]
            - codec["storage"]["components"]["row_payload_bytes"],
            "storage_components": codec["storage"]["components"],
            "fallback_bytes": 0,
            "encoded_module_manifest_sha256": codec["storage"][
                "encoded_module_manifest_sha256"
            ],
            "producer_rows_replayed_after_aggregation_defect": 0,
        },
        "h200_dense_consumer": {
            "evidence_class": "measured and source-bound",
            "qualified_seconds_per_request": QUALIFIED_SECONDS,
            "profile_control_seconds_per_request": attribution[
                "profile_control_service_seconds_per_request"
            ],
            "nonoverlapping_fp8_linear_trace_seconds": fp8_boundary["seconds"],
            "profile_requests": REQUESTS,
            "fp8_linear_seconds_per_request_used_for_bound": measured_linear_seconds,
            "bound_is_candidate_favorable": (
                "The absolute FP8-linear charge from the slower profile is subtracted "
                "from the faster qualified denominator instead of scaling down its share."
            ),
            "full_weight_stream_passes_in_trace": stream_passes,
            "raw_weight_bytes_per_request": raw_bytes_per_request,
            "encoded_weight_bytes_per_request": encoded_bytes_per_request,
            "saved_weight_bytes_per_request": saved_bytes_per_request,
            "dominant_kernel": dominant,
            "native_compressed_operand_support": False,
            "support_observation": (
                "The pinned SGLang/CUTLASS dispatch accepts dense E4M3 operands "
                "and selects SM90 TMA warp-specialized WGMMA schedules; no Huffman, "
                "entropy, or compressed-operand consumer is present."
            ),
        },
        "decoder_thresholds": {
            "evidence_class": "analytical from measured bytes and H200 trace",
            "to_beat_measured_dense_fp8_boundary": {
                "optimistic_nonoverlapped_decoder_budget_seconds_per_request": (
                    optimistic_nonoverlap_budget
                ),
                "minimum_raw_output_bytes_per_second": (
                    measured_boundary_raw_decode_threshold
                ),
                "minimum_compressed_input_bytes_per_second": (
                    measured_boundary_input_threshold
                ),
                "assumption": (
                    "Every non-decoder FP8-linear second scales with encoded bytes; "
                    "this grants the codec compute and launch savings it has not measured."
                ),
            },
            "h200_peak_hbm_serial_bound": {
                "peak_hbm_bytes_per_second": peak_hbm_bytes_per_second,
                "minimum_raw_decode_bytes_per_second_to_beat_dense_transfer": (
                    peak_serial_raw_decode_threshold
                ),
                "formula": "HBM_peak/(1-compression_ratio)",
            },
            "h200_peak_hbm_full_overlap_bound": {
                "minimum_raw_decode_bytes_per_second_to_hide_under_compressed_read": (
                    peak_full_overlap_raw_decode_threshold
                ),
                "formula": "HBM_peak/compression_ratio",
            },
            "to_reach_campaign_target": {
                "available_decoder_seconds_per_request": (
                    TARGET_SECONDS - zero_decoder_complete_seconds
                ),
                "minimum_decoder_throughput": "infinite",
                "feasible": False,
                "reason": "The zero-cost decoder complete bound already misses the target.",
            },
        },
        "sm90_resource_threshold": {
            "evidence_class": "analytical, not compiled or measured",
            "h200_sms": accelerator["execution"]["compute_units"],
            "current_grid_ctas": dominant["grid"][0],
            "current_threads_per_cta": dominant["threads_per_cta"],
            "current_registers_per_thread": dominant["registers_per_thread"],
            "register_file_32bit_registers_per_sm": register_file_32bit,
            "current_registers_per_cta": current_registers_per_cta,
            "register_headroom": register_headroom,
            "decoder_warp_register_ceiling_with_warp_specialized_allocation": (
                decoder_warp_register_ceiling
            ),
            "uniform_register_ceiling_if_adding_one_32_thread_warp": (
                uniform_register_ceiling
            ),
            "register_disposition": (
                "A fifth uniform 168-register warp is illegal. A viable integration "
                "must reuse an existing producer warp or use Hopper warp-specialized "
                "allocation with at most 32 registers per added decoder thread and no spills."
            ),
            "shared_memory_limit_bytes_per_cta": shared_limit_bytes,
            "current_dynamic_shared_memory_bytes": dominant[
                "dynamic_shared_memory_bytes"
            ],
            "shared_memory_headroom_bytes": shared_headroom,
            "single_k32_n128_fp8_tile_bytes": 4096,
            "double_buffer_tile_bytes": double_tile_bytes,
            "decode_table_bytes": decode_table_bytes,
            "double_buffer_plus_table_bytes": staged_shared_bytes,
            "remaining_shared_headroom_if_all_are_incremental": (
                shared_headroom - staged_shared_bytes
            ),
            "tile_staging_disposition": (
                "Decode one 32x128 B tile per warp, preferably into the existing "
                "CUTLASS B stage. Two 4096-byte stages plus the 8192-byte table fit "
                "the raw block limit by only 2048 bytes if all are incremental."
            ),
            "overlap_requirement": (
                "The producer warp must decode the next K32xN128 tile while the "
                "warpgroup consumes the current tile, with a producer-consumer "
                "barrier before the first WGMMA. Any nonoverlapped decode must meet "
                "the throughput thresholds above."
            ),
            "expected_occupancy": "one CTA per SM; no second block is resource-admissible",
        },
        "complete_analytical_bound": {
            "evidence_class": "derived, deliberately optimistic",
            "qualified_seconds_per_request": QUALIFIED_SECONDS,
            "campaign_target_seconds_per_request": TARGET_SECONDS,
            "fixed_non_fp8_linear_seconds_per_request": fixed_seconds,
            "measured_codec_ratio": compression_ratio,
            "maximum_admissible_compressed_path_ratio_at_zero_decoder_cost": (
                required_compressed_path_ratio
            ),
            "zero_decoder_fp8_linear_seconds_per_request": (
                zero_decoder_linear_seconds
            ),
            "zero_decoder_complete_seconds_per_request": (
                zero_decoder_complete_seconds
            ),
            "zero_decoder_complete_gain_fraction": (
                (QUALIFIED_SECONDS - zero_decoder_complete_seconds)
                / QUALIFIED_SECONDS
            ),
            "zero_decoder_margin_to_target_seconds": (
                TARGET_SECONDS - zero_decoder_complete_seconds
            ),
            "tile_entropy_ratio_without_any_metadata": entropy_ratio,
            "tile_entropy_zero_metadata_complete_seconds_per_request": (
                entropy_zero_metadata_seconds
            ),
            "target_reached": False,
            "assumptions": [
                "All measured FP8-linear time scales linearly with stored bytes.",
                "Decoder, lookup, synchronization, shared-memory staging, and integration cost zero.",
                "No regression in GEMM compute, occupancy, launch count, or cache behavior.",
                "The non-FP8-linear part of the qualified request is unchanged.",
            ],
        },
        "sm90_consumer_source_or_none": {
            "classification": "typed_none",
            "source_path": None,
            "reason": (
                "The preregistered decision rule requires a real SM90 path only if "
                "the physically optimistic complete bound can reach the campaign "
                "target. It misses by 0.09786692084884119 seconds/request before "
                "any decoder or integration cost, so source implementation cannot "
                "change this project's terminal decision."
            ),
            "cpu_reference": {
                "runner": "run_offline_codec.py",
                "codec": "huffman_tile_codec.cpp",
                "consumer_boundary": (
                    "32 independently decoded K rows reconstruct the exact K32xN128 "
                    "E4M3 B tile that would feed the first WGMMA."
                ),
            },
        },
        "direct_inputs": direct_inputs,
        "execution": {
            "gpu_claimed": False,
            "ssh_used": False,
            "provider_or_endpoint_used": False,
            "checkpoint_shards_copied": False,
            "checkpoint_shards_mutated": False,
            "codec_families_swept": False,
            "lossy_fallback_used": False,
            "actual_spend_usd": 0.0,
        },
        "next_action": (
            "Preserve this typed none and do not implement or GPU-test this Huffman "
            "realization. A future entropy project requires a materially different "
            "campaign question or a representation whose all-in ratio is at most "
            f"{required_compressed_path_ratio} before decoder cost."
        ),
    }
    if not codec["coverage"]["bitwise_equal"]:
        raise RuntimeError("codec result is not bitwise exact")
    if zero_decoder_complete_seconds <= TARGET_SECONDS:
        raise RuntimeError("typed-none bound no longer holds")
    atomic_json(OUTPUT, terminal)
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "classification": terminal["classification"],
                "compression_ratio": compression_ratio,
                "zero_decoder_complete_seconds_per_request": (
                    zero_decoder_complete_seconds
                ),
                "target_seconds_per_request": TARGET_SECONDS,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
