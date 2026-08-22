#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import sqlite3


HIDDEN = 5376
DOWN_K = 21504
QKV_N = 16384
SMS = 132
DOWN_TILE_COLUMNS = 64
DOWN_CTAS = HIDDEN // DOWN_TILE_COLUMNS
CLUSTER_CTAS = 8
PROFILE_BATCH_SECONDS = 23.038600455
CURRENT_SECONDS_PER_REQUEST = 0.625149101968745
TARGET_SECONDS_PER_REQUEST = 0.500119281574996
PROFILE_RELATIVE = pathlib.Path(
    "../gemma4_h200_v0513_fp8_qkv_residual_profile/"
    "artifacts/residual-profile-20260720t0821z/control-profile.sqlite"
)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def measured_profile(database: pathlib.Path) -> dict[str, object]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    norm_rows = connection.execute(
        """
        SELECT s.value, COUNT(*), SUM(k.end-k.start)/1e9, AVG(k.end-k.start)/1e3
        FROM CUPTI_ACTIVITY_KIND_KERNEL k
        JOIN StringIds s ON s.id=k.demangledName
        WHERE lower(s.value) LIKE '%rmsnorm%'
           OR lower(s.value) LIKE '%per_token_quant_fp8%'
        GROUP BY s.value
        ORDER BY SUM(k.end-k.start) DESC
        """
    ).fetchall()
    quant_rows = connection.execute(
        """
        SELECT k.end-k.start
        FROM CUPTI_ACTIVITY_KIND_KERNEL k
        JOIN StringIds s ON s.id=k.demangledName
        WHERE s.value LIKE 'void per_token_quant_fp8_small_batch_kernel%'
        ORDER BY k.start
        """
    ).fetchall()
    connection.close()
    if len(quant_rows) != 14640 or len(quant_rows) % 4:
        raise RuntimeError("unexpected pinned quantization launch stream")
    qkv_seconds = sum(row[0] for row in quant_rows[0::4]) / 1e9
    named = {}
    for name, launches, seconds, average_us in norm_rows:
        if name == "_gemma_rmsnorm_residual_kernel":
            named["post_ff_residual"] = {
                "kernel": name,
                "launches": launches,
                "seconds": seconds,
                "average_us": average_us,
            }
        elif name.startswith(
            "kernel_cutlass_kernel_flashinfernormkernelsrmsnormRMSNormKernel"
        ):
            named["plain_hidden_rmsnorm_family"] = {
                "kernel": name,
                "launches": launches,
                "seconds": seconds,
                "average_us": average_us,
            }
        elif name.startswith("void per_token_quant_fp8_small_batch_kernel"):
            named["all_dynamic_quant"] = {
                "kernel": name,
                "launches": launches,
                "seconds": seconds,
                "average_us": average_us,
            }
    if set(named) != {
        "post_ff_residual",
        "plain_hidden_rmsnorm_family",
        "all_dynamic_quant",
    }:
        raise RuntimeError("required pinned telemetry families not found")
    named["qkv_dynamic_quant"] = {
        "evidence": "measured interleaved projection stream, qkv is index 0 of each four-launch layer group",
        "launches": len(quant_rows[0::4]),
        "seconds": qkv_seconds,
        "average_us": qkv_seconds * 1e6 / len(quant_rows[0::4]),
    }
    return named


def bytes_for_m(m: int) -> dict[str, int]:
    scale_bytes = 4 * m
    shared_weights = 4 * HIDDEN
    control_activation = m * 17 * HIDDEN + scale_bytes
    finalizer_activation = m * 9 * HIDDEN + scale_bytes
    partial_round_trip = m * DOWN_CTAS * 4 * 2
    return {
        "m": m,
        "shared_weight_bytes_both_paths": shared_weights,
        "materialized_control_activation_bytes": control_activation,
        "epilogue_partial_activation_bytes": finalizer_activation
        + partial_round_trip,
        "row_finalizer_activation_bytes": finalizer_activation,
        "epilogue_partial_extra_bytes": partial_round_trip,
        "epilogue_partial_saved_bytes": control_activation
        - finalizer_activation
        - partial_round_trip,
        "row_finalizer_saved_bytes": control_activation - finalizer_activation,
    }


def exact_consumer_contract(
    project: pathlib.Path,
    oracle: pathlib.Path,
    analysis_source: pathlib.Path,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "classification": "unfunded_exact_consumer_h200_measurement_contract",
        "authority": {
            "gpu_claim_allowed_now": False,
            "spend_authorized_usd_now": 0.0,
            "next_step_requires_director_admission": True,
        },
        "identities": {
            "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "runtime": "SGLang v0.5.13@28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "image": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6",
            "accelerator": "NVIDIA H200 SXM, sm_90a, 132 SMs",
            "candidate_source": {
                "path": "sm90a_two_phase_finalizer.cu",
                "sha256": sha256(project / "sm90a_two_phase_finalizer.cu"),
            },
            "oracle": {
                "path": oracle.name,
                "sha256": sha256(oracle),
            },
            "analysis_source": {
                "path": analysis_source.name,
                "sha256": sha256(analysis_source),
            },
        },
        "exact_geometry": {
            "m": [1, 16, 32],
            "down_activation": "row-major E4M3FN [M,21504] with contiguous FP32 [M,1] scale",
            "down_weight": "column-major E4M3FN [21504,5376], stride [1,21504], contiguous FP32 [1,5376] scale",
            "down_output": "row-major BF16 [M,5376]",
            "post_ff_weight": "contiguous BF16 [5376]",
            "residual": "row-major BF16 [M,5376]",
            "layer_scalar": "contiguous FP32 [1]",
            "next_input_weight": "contiguous BF16 [5376]",
            "qkv_activation": "row-major E4M3FN [M,5376] with contiguous FP32 [M,1] scale",
            "qkv_weight": "column-major E4M3FN [5376,16384], stride [1,5376], contiguous FP32 [1,16384] scale",
            "qkv_output": "row-major BF16 [M,16384]",
            "tensor_parallel_size": 1,
        },
        "control": [
            "Pinned fp8_scaled_mm down projection producing materialized BF16 down_output.",
            "Pinned _gemma_rmsnorm_residual_kernel producing required BF16 next-layer residual.",
            "Pinned FlashInfer RMSNorm producing materialized next-normalized BF16.",
            "Pinned per_token_quant_fp8_small_batch_kernel producing E4M3 and FP32 scale.",
            "Pinned fp8_scaled_mm QKV consumer producing complete BF16 [M,16384].",
        ],
        "candidate": [
            "The identical pinned fp8_scaled_mm down projection and identical materialized BF16 down_output.",
            "finalize_post_ff_residual_next_norm_e4m3 producing required residual plus E4M3/scale without a normalized-BF16 global tensor.",
            "The identical pinned fp8_scaled_mm QKV consumer producing complete BF16 [M,16384].",
        ],
        "first_call_discovery_gate": {
            "shape": [1, 21504, 5376, 16384],
            "requirements": [
                "Candidate symbol executes on sm_90a and CUDA synchronizes immediately after the untimed call.",
                "Control and candidate down-output BF16 bytes are identical because the producer is unchanged.",
                "Complete residual BF16, E4M3, FP32 scale, and QKV BF16 bytes are identical.",
                "All-zero input reproduces E4M3 +448 bytes with FP32 +0 scale.",
            ],
            "ordinary_repair_scope": "Compile, registration, launch, tree-order implementation, or layout defects may be patched before timing while preserving the stock producer, two BF16 boundaries, scale convention, shapes, and consumer.",
        },
        "required_row_ledger_per_shape": [
            "control boundary warm samples",
            "candidate boundary warm samples",
            "control down-to-QKV complete component warm samples",
            "candidate down-to-QKV complete component warm samples",
            "complete numerical oracle and candidate-path proof",
        ],
        "timing": {
            "method": "CUDA events, profiler off, compilation/autotune excluded, complete output consumed and synchronized.",
            "repetitions": "At least five alternating A/B/A/B/A bracket repetitions per M after 10 warmups; each bracket reports a median over enough inner iterations for at least 20 ms aggregate event time.",
            "units": "microseconds per invocation processing the stated M-row batch",
            "decision": "Promote only if every numerical/path/resource gate passes and the candidate complete-component median is lower at M=32 without a material M=1 or M=16 regression. Report paired raw samples; no endpoint transfer claim.",
        },
        "compiler_and_runtime_gates": [
            "Loaded cubin is sm_90a and dispatch proves the candidate symbol.",
            "Dynamic shared memory is exactly 43,520 bytes or a hash-bound equivalent; report registers/thread, spills, and active-block limit.",
            "No down GEMM duplication, cooperative-grid launch, cross-cluster dependency, or second normalized BF16 allocation.",
            "CUDA graph capture and replay pass separately at M=1,16,32 with fixed addresses.",
            "TP!=1 dispatches to stock until an all-reduce-aware contract exists.",
        ],
        "telemetry": {
            "minimum": [
                "warm event samples",
                "candidate symbol/launch geometry",
                "register/shared/spill metadata",
                "global load/store bytes or the shortest counters needed to verify the traffic direction",
            ],
            "whole_request_gate": "Only after a positive component, integrate the prequantized QKV handoff into the pinned runtime and run a contemporaneous c32 endpoint A/B; component magnitude alone is not an endpoint claim.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--consumer-contract", type=pathlib.Path, required=True)
    args = parser.parse_args()

    project = pathlib.Path(__file__).resolve().parent
    oracle = json.loads(args.oracle.read_text())
    if not oracle.get("pass"):
        raise RuntimeError("reference oracle did not pass")
    if oracle.get("candidate_source_sha256") != sha256(
        project / "sm90a_two_phase_finalizer.cu"
    ):
        raise RuntimeError("oracle does not bind current candidate source")

    profile = (project / PROFILE_RELATIVE).resolve()
    telemetry = measured_profile(profile)
    forward_batches = telemetry["post_ff_residual"]["launches"] // 60
    if forward_batches != 61:
        raise RuntimeError("unexpected forward-batch count")
    transition_launches = forward_batches * 59
    post_seconds = (
        telemetry["post_ff_residual"]["seconds"] * transition_launches / 3660
    )
    next_norm_seconds = (
        telemetry["plain_hidden_rmsnorm_family"]["seconds"]
        * transition_launches
        / telemetry["plain_hidden_rmsnorm_family"]["launches"]
    )
    qkv_quant_seconds = (
        telemetry["qkv_dynamic_quant"]["seconds"] * transition_launches / 3660
    )
    attributed_upper_seconds = post_seconds + next_norm_seconds + qkv_quant_seconds
    attributed_upper_fraction = attributed_upper_seconds / PROFILE_BATCH_SECONDS
    loose_request_ceiling = CURRENT_SECONDS_PER_REQUEST * attributed_upper_fraction

    byte_rows = [bytes_for_m(m) for m in (1, 16, 32)]
    down_flops = {str(m): 2 * m * DOWN_K * HIDDEN for m in (1, 16, 32)}
    cluster_count = math.ceil(DOWN_CTAS / CLUSTER_CTAS)
    analysis = {
        "schema_version": 1,
        "classification": "source_candidate_promoted_to_unfunded_h200_contract",
        "evidence_classes": {
            "runtime_trace": "source-backed",
            "kernel_totals": "measured on the older exact v0.5.13 c32 residual profile; shapes were M=118/1409/1631/2048, not the M<=32 target",
            "traffic_waves_resources": "analytical from pinned source geometry and H200 inventory",
            "reference_oracle": "synthetic deterministic CPU/reference",
            "performance": "unmeasured",
        },
        "source_trace": {
            "sequence": [
                "Gemma3MLP.down_proj: dynamic-E4M3 [M,21504] x per-channel-E4M3 [21504,5376] -> BF16 [M,5376]",
                "Gemma4DecoderLayer gemma_rmsnorm_residual_scalar: BF16 post-FF RMSNorm(down), BF16 residual add, FP32 layer scalar, BF16 layer output",
                "next Gemma4DecoderLayer.input_layernorm: BF16 [M,5376] -> BF16 [M,5376]",
                "Fp8LinearMethod/apply_fp8_linear/per_token_quant_fp8_small_batch_kernel: BF16 -> row-major E4M3 plus FP32 [M,1] scale",
                "qkv_proj/fp8_scaled_mm: row-major E4M3 [M,5376] x column-major E4M3 [5376,16384] -> BF16 [M,16384]",
            ],
            "exact_order": "The down result is BF16-rounded before post-FF RMSNorm. The residual/scalar result is BF16-rounded before the next RMSNorm. The next normalized value is BF16-rounded before max/448 scaling and E4M3 conversion.",
            "tp_ownership": "The qualified endpoint is TP=1. RowParallelLinear would require completion of its tensor-parallel reduction before either row norm at TP>1; the candidate therefore fail-closes to stock for TP!=1.",
            "small_batch_zero_semantics": "For M<=32 the pinned small-batch quantizer divides by zero on an all-zero row; fmin/fmax converts NaN to +448 and stores FP32 scale +0. The candidate intentionally preserves those bytes.",
        },
        "geometry": {
            "m": [1, 16, 32],
            "down_k": DOWN_K,
            "hidden": HIDDEN,
            "qkv_n": QKV_N,
            "down_tile_columns": DOWN_TILE_COLUMNS,
            "down_ctas": DOWN_CTAS,
            "down_grid_waves_on_132_sms": DOWN_CTAS / SMS,
            "finalizer_ctas": {"1": 1, "16": 16, "32": 32},
            "finalizer_grid_waves": {
                "1": 1 / SMS,
                "16": 16 / SMS,
                "32": 32 / SMS,
            },
            "down_useful_flops": down_flops,
            "down_duplicated_flops_control_and_selected_candidate": 0,
        },
        "bytes": {
            "accounting": "Activation/intermediate traffic counts down BF16 store/read, residual read, layer-output BF16 store/read, next-normalized BF16 store/two quantizer reads, E4M3 store, and one FP32 scale. Both norm weights are reported separately and unchanged.",
            "per_shape": byte_rows,
            "selected_candidate_removed_bytes_per_row": 8 * HIDDEN,
            "selected_candidate_removed_launches_per_layer_transition": 2,
            "selected_candidate_dynamic_shared_bytes_per_cta": 43520,
        },
        "decompositions": [
            {
                "id": "epilogue_tree_partials",
                "legal": True,
                "result": "falsified_as_dominated",
                "detail": "The 84 stock hidden-tile CTAs can emit exact aligned 64-leaf sum-of-squares partials after BF16 rounding, and the oracle proves they compose to the registered 8192-leaf tree. They do not remove the compulsory down BF16 store/read, add 672 global bytes per row, add epilogue square/reduction work, and still require the same row finalizer. The selected no-partial finalizer saves 672 more bytes per row and avoids the producer modification.",
                "extra_flops": "At least one BF16-to-FP32 square per down output plus 63 FP32 adds per row/tile.",
                "synchronization": "One later kernel boundary; no cross-CTA barrier in the producer.",
                "register_shared_risk": "Adds epilogue live values to the tuned CUTLASS producer; compiler resources unknown until H200.",
            },
            {
                "id": "cluster_dsm_hidden_strip",
                "legal": True,
                "result": "falsified_as_scope_insufficient_or_dominated",
                "detail": f"An eight-CTA portable cluster covers only {CLUSTER_CTAS * DOWN_TILE_COLUMNS} of 5376 columns, so {cluster_count} clusters own one row. DSM and cluster barriers do not cross those clusters. Retaining exact row values therefore still needs global materialization and a finalizer, where it is dominated by the selected path. Serializing all 84 tiles through one cluster needs 11 tile slots per CTA and replaces a 0.636-wave producer grid with an 11-slot critical chain.",
                "cluster_shape": [1, 8, 1],
                "clusters_per_hidden_row_group": cluster_count,
                "synchronization": "At least one global phase boundary or a cooperative-grid barrier; the latter is not the pinned CUDA-graph/CUTLASS launch.",
                "duplicated_flops": 0,
            },
            {
                "id": "row_owned_two_phase_finalizer",
                "legal": True,
                "result": "selected_source_candidate",
                "detail": "Keep the tuned stock down GEMM and its BF16 output. One 256-thread CTA per row uses a 32-KiB FP32 reduction tree plus a 10.5-KiB BF16 row buffer to execute both exact-order RMSNorms, persist only the required next-layer residual, and emit the complete E4M3/scale for unchanged QKV.",
                "source": "sm90a_two_phase_finalizer.cu",
                "source_sha256": sha256(project / "sm90a_two_phase_finalizer.cu"),
                "synchronization": "One kernel boundary after down; three ordered in-CTA reduction phases and no inter-CTA dependency.",
                "register_shared_risk": "43,520 dynamic shared bytes; loop-carried scalar registers only by construction. Compiled registers and spills remain an H200 gate.",
                "duplicated_down_flops": 0,
                "cuda_graph": "Fixed shape, address, grid, block, and dynamic shared size; capture/replay remains a required target check.",
            },
        ],
        "reference_oracle": {
            "artifact": args.oracle.name,
            "sha256": sha256(args.oracle),
            "classification": oracle["classification"],
            "rows_checked": oracle["scope"]["rows_checked"],
            "result": "All required BF16 residual, registered next-normalized BF16, FP32 scale, complete E4M3, partial-tree, and sampled Q/K/V consumer fragments are bitwise exact for random, signed-zero, and extreme fixtures at M=1/16/32.",
            "transfer_limit": oracle["transfer_limit"],
        },
        "whole_request_bound": {
            "profile_batch_seconds": PROFILE_BATCH_SECONDS,
            "transition_launches": transition_launches,
            "measured_or_allocated_kernel_seconds": {
                "post_ff_residual": post_seconds,
                "next_input_rmsnorm_allocated_from_plain_hidden_family": next_norm_seconds,
                "qkv_dynamic_quant": qkv_quant_seconds,
                "total_entire_kernels": attributed_upper_seconds,
            },
            "loose_entire_kernel_fraction": attributed_upper_fraction,
            "loose_seconds_per_request_ceiling_if_entire_kernels_were_free": loose_request_ceiling,
            "loose_percent_of_current_request": attributed_upper_fraction * 100,
            "target_gap_seconds_per_request": CURRENT_SECONDS_PER_REQUEST
            - TARGET_SECONDS_PER_REQUEST,
            "interpretation": "This is a loose source/telemetry ceiling, not a candidate prediction: the finalizer retains both reductions, residual math, quantization, and all GEMMs. It only establishes that the boundary is positive and stackable enough for a cheap component measurement.",
        },
        "telemetry": {
            "profile_path": str(PROFILE_RELATIVE),
            "profile_sha256": sha256(profile),
            "kernel_families": telemetry,
            "shape_transfer_warning": "Measured totals came from the older residual profile's prefill-dominant M=118/1409/1631/2048 stream. They bound relevance but do not predict M=1/16/32 latency.",
        },
        "decision": "Promote only row_owned_two_phase_finalizer to an unfunded exact-consumer H200 component contract. Close the epilogue-partial and cluster/DSM families as dominated within this boundary. Do not claim a bench until separately admitted and funded.",
    }

    contract = exact_consumer_contract(
        project, args.oracle, pathlib.Path(__file__).resolve()
    )
    atomic_json(args.consumer_contract, contract)
    atomic_json(args.output, analysis)
    print(
        json.dumps(
            {
                "classification": analysis["classification"],
                "selected": "row_owned_two_phase_finalizer",
                "loose_percent": attributed_upper_fraction * 100,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
