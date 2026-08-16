#!/usr/bin/env python3
"""Reproduce the zero-GPU SwiGLU/down fusion causal screen.

This script consumes only pinned source, model configuration, and the retained
Nsight Systems SQLite export. It does not import SGLang, compile code, or touch
CUDA.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


GENERATED_AT_UTC = "2026-07-25T23:21:52Z"
MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
RUNTIME_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
IMAGE = (
    "docker.io/lmsysorg/sglang@sha256:"
    "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def stable_json(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def source_record(
    root: Path,
    path: Path,
    expected_sha256: str,
    evidence_type: str,
    role: str,
    revision: str,
) -> dict[str, Any]:
    actual = sha256(path)
    if actual != expected_sha256:
        raise RuntimeError(
            f"source hash mismatch for {path}: expected {expected_sha256}, got {actual}"
        )
    return {
        "evidence_type": evidence_type,
        "path": str(path.relative_to(root)),
        "publication_or_revision": revision,
        "retrieved_at_utc": GENERATED_AT_UTC,
        "role": role,
        "sha256": actual,
        "url": None,
    }


def kernel_measurements(sqlite_path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        quant_rows = list(
            connection.execute(
                """
                SELECT k.start, k.end, k.correlationId, k.gridX, k.blockX,
                       s.value AS name
                FROM CUPTI_ACTIVITY_KIND_KERNEL AS k
                JOIN StringIds AS s ON s.id = k.demangledName
                WHERE s.value LIKE '%per_token_quant%'
                ORDER BY k.start
                """
            )
        )
        activation_rows = list(
            connection.execute(
                """
                SELECT k.start, k.end, k.correlationId, k.gridX, k.blockX,
                       s.value AS name
                FROM CUPTI_ACTIVITY_KIND_KERNEL AS k
                JOIN StringIds AS s ON s.id = k.demangledName
                WHERE s.value LIKE '%act_and_mul_kernel%'
                ORDER BY k.start
                """
            )
        )
        if len(quant_rows) != 14_640 or len(activation_rows) != 3_660:
            raise RuntimeError(
                "unexpected retained trace cardinality: "
                f"quant={len(quant_rows)}, activation={len(activation_rows)}"
            )

        # The model source fixes projection order as qkv, o, gate/up, down.
        # The retained trace repeats four quant launches in that order. The
        # fourth family is independently identified by its 21,504-wide,
        # approximately 50-us kernel versus the two 5,376-wide families.
        family_names = ["qkv_input", "o_input", "gate_up_input", "down_input"]
        quant_families: dict[str, dict[str, Any]] = {}
        for offset, family_name in enumerate(family_names):
            rows = quant_rows[offset::4]
            grids: dict[int, int] = {}
            for row in rows:
                grids[int(row["gridX"])] = grids.get(int(row["gridX"]), 0) + 1
            quant_families[family_name] = {
                "evidence_type": "measured_sequence_joined_to_source",
                "grid_x_counts": [
                    {"grid_x": grid, "launches": count}
                    for grid, count in sorted(grids.items())
                ],
                "launches": len(rows),
                "mean_microseconds": sum(row["end"] - row["start"] for row in rows)
                / len(rows)
                / 1_000,
                "seconds": sum(row["end"] - row["start"] for row in rows) / 1e9,
            }

        def runtime_sum(rows: list[sqlite3.Row]) -> dict[str, Any]:
            correlations = {int(row["correlationId"]) for row in rows}
            total_ns = 0
            maximum_ns = 0
            names: set[str] = set()
            # A single joined scan avoids thousands of point queries.
            for row in connection.execute(
                """
                SELECT r.correlationId, r.start, r.end, s.value AS name
                FROM CUPTI_ACTIVITY_KIND_RUNTIME AS r
                JOIN StringIds AS s ON s.id = r.nameId
                """
            ):
                if int(row["correlationId"]) in correlations:
                    duration = int(row["end"]) - int(row["start"])
                    total_ns += duration
                    maximum_ns = max(maximum_ns, duration)
                    names.add(str(row["name"]))
            return {
                "api_names": sorted(names),
                "evidence_type": "measured_correlated_host_runtime",
                "maximum_single_call_microseconds": maximum_ns / 1_000,
                "seconds": total_ns / 1e9,
            }

        activation_seconds = (
            sum(row["end"] - row["start"] for row in activation_rows) / 1e9
        )
        return {
            "activation": {
                "kernel_name": activation_rows[0]["name"],
                "launches": len(activation_rows),
                "seconds": activation_seconds,
                "runtime_launch": runtime_sum(activation_rows),
            },
            "quant_families": quant_families,
            "down_quant_runtime_launch": runtime_sum(quant_rows[3::4]),
        }
    finally:
        connection.close()


def build_artifacts(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    project = (
        root
        / "research/lab/experiments/gemma4_31b/research_lab/projects"
        / "gemma4_fp8_swiglu_down_fusion_codesign"
    )
    projects = project.parent
    runtime = root / ".agents/runtime/sglang-v0.5.13-source"
    width_inputs = projects / "gemma4_h200_mlp_width16384_codesign/inputs/bound"

    paths = {
        "accelerator_inventory": root / "research/factory/data/accelerator_inventory.json",
        "campaign": project.parents[1] / "CAMPAIGN.md",
        "config": projects
        / "gemma4_hybrid_attention_placement_codesign/inputs/bound/config.json",
        "trace": width_inputs / "CURRENT_TRACE_ATTRIBUTION.json",
        "shape_map": width_inputs / "CURRENT_FP8_LINEAR_SHAPE_MAP.json",
        "gemma3": width_inputs / "gemma3_causal.v0.5.13.py",
        "gemma4": width_inputs / "gemma4_causal.v0.5.13.py",
        "activation_py": runtime
        / "python/sglang/srt/layers/activation.py",
        "activation_cuh": runtime
        / "python/sglang/jit_kernel/csrc/elementwise/activation.cuh",
        "fp8_utils": runtime
        / "python/sglang/srt/layers/quantization/fp8_utils.py",
        "fp8_kernel_py": runtime
        / "python/sglang/srt/layers/quantization/fp8_kernel.py",
        "quant_cu": runtime / "sgl-kernel/csrc/gemm/per_token_quant_fp8.cu",
        "sqlite": projects
        / (
            "gemma4_h200_residual_h2d_sync_residency/artifacts/"
            "residual-h2d-current-frontier-20260723t0403z/current-frontier.sqlite"
        ),
    }
    expected_hashes = {
        "accelerator_inventory": "bcb33ac6814400f6ab79faa7e44c0ced2d6fe2ac5d19dc43f4ee10b12d7ea6b8",
        "campaign": "c20fb10b1c1c12b53a430cf7401e42a1d10c0d1a9d80d1e36a6b8b264d8a8863",
        "config": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
        "trace": "5679e8d635c759e9d37fdccfece02a9ac23d4ad8c565c9fb3558ab9e005801be",
        "shape_map": "9535b050fa132dcd40091b3539a28342fb6eedff43035367e97d1b78c97d1774",
        "gemma3": "a9827bde583c5b8b0abfeaced097c4e9d060fb99ec2961b4f9c66173d3027282",
        "gemma4": "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989",
        "activation_py": "e0bfddf2c5ad0ba62df2c68b5682518f11f0592c8a51f144a363ea5ddcc772ca",
        "activation_cuh": "8654de9cd6e2655427f95bf1d95dc20c953ef28b0cfee631ce2a71a01aaa0d61",
        "fp8_utils": "a3a130f40974047084e3daff2bd0efbbfe69e197d4c9a5ba3fbc5304dd4e43d9",
        "fp8_kernel_py": "95882e4fed8ac449240ffc8e62b13176bb5057db6c77a06cdfcfffa5f5d89a06",
        "quant_cu": "c8a3e755dc165cecfa09232bed58e8b36010061f050acf2f82722b75c3c1edb8",
        "sqlite": "73d03c99293d425e73c9d72e94bdb0df2b02215c3804400754b7b480c59cdeef",
    }
    roles = {
        "accelerator_inventory": ("vendor_reported_curated_inventory", "H200 resource limits"),
        "campaign": ("campaign_contract", "economic and workload contract"),
        "config": ("pinned_model_configuration", "exact Gemma geometry"),
        "trace": ("measured", "request-window critical-path attribution"),
        "shape_map": ("measured_and_derived", "projection timings and FP8 shapes"),
        "gemma3": ("pinned_source", "dense MLP construction and call order"),
        "gemma4": ("pinned_source", "Gemma4-to-Gemma3 MLP binding"),
        "activation_py": ("pinned_source", "BF16 activation allocation boundary"),
        "activation_cuh": ("pinned_source", "GELU-tanh multiply and BF16 cast order"),
        "fp8_utils": ("pinned_source", "dynamic per-token quant and down GEMM dispatch"),
        "fp8_kernel_py": ("pinned_source", "quantized tensor and float32 scale allocation"),
        "quant_cu": ("pinned_source", "two-pass row amax and FP8 conversion"),
        "sqlite": ("measured", "retained CUPTI kernel and runtime rows"),
    }
    source_table = []
    for name, path in paths.items():
        evidence_type, role = roles[name]
        revision = (
            RUNTIME_COMMIT
            if name
            in {
                "gemma3",
                "gemma4",
                "activation_py",
                "activation_cuh",
                "fp8_utils",
                "fp8_kernel_py",
                "quant_cu",
            }
            else MODEL_REVISION
            if name == "config"
            else "retained exact bytes"
        )
        source_table.append(
            source_record(
                root,
                path,
                expected_hashes[name],
                evidence_type,
                role,
                revision,
            )
        )

    config = load_json(paths["config"])["text_config"]
    if (
        config["hidden_size"],
        config["intermediate_size"],
        config["num_hidden_layers"],
        config["hidden_activation"],
    ) != (5_376, 21_504, 60, "gelu_pytorch_tanh"):
        raise RuntimeError("pinned model geometry changed")

    trace = load_json(paths["trace"])
    shape_map = load_json(paths["shape_map"])
    measurements = kernel_measurements(paths["sqlite"])
    projections = {
        row["projection"]: row for row in shape_map["projection_families"]
    }
    activation_seconds = measurements["activation"]["seconds"]
    down_quant_seconds = measurements["quant_families"]["down_input"]["seconds"]
    pair_seconds = activation_seconds + down_quant_seconds
    gate_up_seconds = projections["gate_up_proj"]["seconds"]
    down_seconds = projections["down_proj"]["seconds"]
    component_seconds = (
        gate_up_seconds + activation_seconds + down_quant_seconds + down_seconds
    )

    down_grid_counts = measurements["quant_families"]["down_input"]["grid_x_counts"]
    summed_rows = sum(row["grid_x"] * row["launches"] for row in down_grid_counts)
    intermediate = int(config["intermediate_size"])
    output_elements = summed_rows * intermediate

    # The retained small-batch quant kernel globally reads the BF16 row twice:
    # once for amax, once for conversion. Scale traffic is one float32 per row.
    current_bytes = output_elements * 11 + summed_rows * 4
    staged_fused_bytes = output_elements * 5 + summed_rows * 4
    removed_bytes = current_bytes - staged_fused_bytes
    traffic_reduction_fraction = removed_bytes / current_bytes

    activation_launch_seconds = measurements["activation"]["runtime_launch"]["seconds"]
    down_quant_launch_seconds = measurements["down_quant_runtime_launch"]["seconds"]
    removed_launch_upper_seconds = max(
        activation_launch_seconds, down_quant_launch_seconds
    )
    same_bandwidth_fused_seconds = pair_seconds * (
        staged_fused_bytes / current_bytes
    )
    point_estimate_saved_seconds = (
        pair_seconds - same_bandwidth_fused_seconds + removed_launch_upper_seconds
    )
    window_seconds = trace["window"]["seconds"]
    component_gate_seconds = component_seconds * 0.05
    request_gate_seconds = window_seconds * 0.01
    maximum_fused_seconds_for_request_gate = (
        pair_seconds + removed_launch_upper_seconds - request_gate_seconds
    )
    required_effective_bandwidth_tb_s = (
        staged_fused_bytes / maximum_fused_seconds_for_request_gate / 1e12
    )
    current_effective_bandwidth_tb_s = current_bytes / pair_seconds / 1e12
    accelerator_inventory = load_json(paths["accelerator_inventory"])
    h200 = next(
        row
        for row in accelerator_inventory["accelerators"]
        if row["id"] == "nvidia-h200-sxm"
    )
    h200_architecture = accelerator_inventory["architecture_profiles"][
        h200["architecture_profile_id"]
    ]

    causal_map = {
        "artifact": "SWIGLU_DOWN_FUSION_CAUSAL_MAP",
        "causal_graph": {
            "edges": [
                {
                    "from": "bf16_residual_input",
                    "materialization": "read",
                    "to": "dynamic_fp8_gate_up_input_quant",
                },
                {
                    "from": "dynamic_fp8_gate_up_input_quant",
                    "materialization": "fp8[M,5376]+fp32[M,1]",
                    "to": "fp8_gate_up_gemm",
                },
                {
                    "from": "fp8_gate_up_gemm",
                    "materialization": "bf16[M,43008]",
                    "to": "gelu_tanh_and_mul",
                },
                {
                    "from": "gelu_tanh_and_mul",
                    "materialization": "bf16[M,21504]",
                    "to": "dynamic_fp8_down_input_quant",
                },
                {
                    "from": "dynamic_fp8_down_input_quant",
                    "materialization": "fp8_e4m3[M,21504]+fp32[M,1]",
                    "to": "fp8_down_gemm",
                },
                {
                    "from": "fp8_down_gemm",
                    "materialization": "bf16[M,5376]",
                    "to": "residual_add_outside_mlp",
                },
            ],
            "nodes": [
                {
                    "id": "fp8_gate_up_gemm",
                    "semantics": "dynamic per-row FP8 activation scale; per-output-channel FP8 weight scale; BF16 output",
                    "shape": "[M,5376] x [5376,43008] -> [M,43008]",
                },
                {
                    "id": "gelu_tanh_and_mul",
                    "semantics": "cast BF16 gate/up to FP32, tanh-approximate GELU and multiply in FP32, one cast to BF16",
                    "shape": "two BF16 [M,21504] halves -> BF16 [M,21504]",
                },
                {
                    "id": "dynamic_fp8_down_input_quant",
                    "semantics": "row-wide BF16 amax; scale=amax/448 in FP32; clamp and cast to FP8 E4M3",
                    "shape": "BF16 [M,21504] -> FP8 [M,21504] + FP32 [M,1]",
                },
                {
                    "id": "fp8_down_gemm",
                    "semantics": "per-row activation and per-output-channel weight scaling; BF16 output",
                    "shape": "[M,21504] x [21504,5376] -> [M,5376]",
                },
            ],
        },
        "candidate_screen": {
            "candidate": {
                "dataflow": [
                    "one 256-thread CTA owns one row",
                    "load paired BF16 gate/up values and reproduce the pinned FP32 GELU-tanh multiply",
                    "cast each product once to BF16 and stage the 21,504-element row in shared memory",
                    "reduce absmax over the staged BF16 row and write the exact FP32 scale",
                    "reread staged BF16, clamp/cast to FP8 E4M3, and materialize qinput for the unchanged down GEMM",
                ],
                "exactness_requirements": [
                    "gate/up GEMM BF16 output remains materialized and unchanged",
                    "GELU-tanh constants and FP32 operation order match activation.cuh",
                    "product is rounded to BF16 before amax and FP8 conversion",
                    "row amax, scale, zero-row behavior, clamp, and FP8 cast match per_token_quant_fp8.cu",
                    "down GEMM and BF16-visible output remain unchanged",
                ],
                "h200_resource_model": {
                    "cta_per_row": 1,
                    "h200_compute_units": h200["execution"]["compute_units"],
                    "h200_local_memory_per_block_bytes": h200_architecture[
                        "max_local_memory_per_block_kib"
                    ]
                    * 1024,
                    "shared_stage_bytes_per_cta": intermediate * 2,
                    "threads_per_cta": 256,
                    "trace_physical_row_counts": [
                        row["grid_x"] for row in down_grid_counts
                    ],
                    "warning": "The exact M=32 component discriminator exposes only 32 CTAs; the retained request trace mostly executes a padded M=2048 grid. No measured fused occupancy or cluster result exists.",
                },
                "materializations_retained": [
                    "BF16 gate/up [M,43008]",
                    "FP8 down qinput [M,21504]",
                    "FP32 per-row scale [M,1]",
                ],
                "materializations_removed": [
                    "global BF16 activated intermediate write",
                    "two global BF16 activated-intermediate reads by the retained small-batch quant kernel",
                    "one of two host kernel launches",
                ],
                "scope": "activation-plus-down-input-quant only; gate/up and down GEMMs are unchanged",
                "source_complete": True,
            },
            "gates": {
                "component_required_fraction": 0.05,
                "request_required_fraction": 0.01,
                "request_required_seconds_in_trace_window": request_gate_seconds,
            },
            "point_screen": {
                "classification": "derived_point_estimate_not_conservative_bound",
                "component_fraction": point_estimate_saved_seconds
                / component_seconds,
                "component_seconds": component_seconds,
                "current_activation_plus_quant_seconds": pair_seconds,
                "current_effective_bandwidth_tb_s": current_effective_bandwidth_tb_s,
                "current_hbm_bytes": current_bytes,
                "fused_hbm_bytes": staged_fused_bytes,
                "h200_peak_hbm_bandwidth_tb_s": h200["memory"][
                    "bandwidth_gb_s"
                ]
                / 1000,
                "point_estimate_saved_seconds": point_estimate_saved_seconds,
                "request_fraction": point_estimate_saved_seconds / window_seconds,
                "same_effective_bandwidth_fused_seconds": same_bandwidth_fused_seconds,
                "traffic_reduction_fraction": traffic_reduction_fraction,
            },
            "conservative_gate_failure": {
                "allowed_fused_seconds_to_clear_request_gate": maximum_fused_seconds_for_request_gate,
                "headroom_over_same_bandwidth_point_seconds": (
                    maximum_fused_seconds_for_request_gate
                    - same_bandwidth_fused_seconds
                ),
                "reason": (
                    "The point screen clears both thresholds only by assuming the "
                    "fused shared-memory/reduction kernel sustains the current pair's "
                    "effective bandwidth and by crediting the larger full correlated "
                    "host-launch duration. The request margin is too narrow to cover "
                    "unmeasured shared-memory staging, row reduction/barriers, the "
                    "M=32 one-CTA-per-row underfill, or integration overhead."
                ),
                "required_effective_bandwidth_fraction_of_current": (
                    required_effective_bandwidth_tb_s
                    / current_effective_bandwidth_tb_s
                ),
                "required_effective_bandwidth_fraction_of_h200_peak": (
                    required_effective_bandwidth_tb_s
                    / (h200["memory"]["bandwidth_gb_s"] / 1000)
                ),
                "required_effective_bandwidth_tb_s": required_effective_bandwidth_tb_s,
                "request_margin_seconds_at_point_estimate": (
                    point_estimate_saved_seconds - request_gate_seconds
                ),
                "verdict": "not_conservatively_supported",
            },
            "other_dataflows": [
                {
                    "candidate": "gate_up_gemm_epilogue_to_activation",
                    "reason_rejected": (
                        "Gate and up halves are separated by 21,504 columns while the "
                        "dominant 128-column CUTLASS N tiles are owned by different "
                        "CTAs. Pairing them requires a new GEMM layout/schedule or "
                        "cross-CTA materialization and changes the measured dominant "
                        "214,016-byte, one-CTA-per-SM kernel; it is not a narrow "
                        "source-complete intervention."
                    ),
                },
                {
                    "candidate": "direct_gate_up_tiles_into_down_gemm",
                    "reason_rejected": (
                        "The down activation scale depends on amax across all 21,504 "
                        "BF16-rounded channels, and each quantized activation is reused "
                        "across 5,376 down outputs. Avoiding qinput materialization "
                        "therefore requires global synchronization plus recomputation "
                        "or a cross-GEMM persistent schedule with no source-backed "
                        "resource or timing bound."
                    ),
                },
                {
                    "candidate": "four_cta_cluster_per_row",
                    "reason_rejected": (
                        "A Hopper DSM cluster could repair M=32 occupancy, but it adds "
                        "cluster-wide max reduction and scale broadcast not present in "
                        "the retained kernel. With only 21.3 ms request-gate margin, "
                        "the existing evidence cannot conservatively budget that cost."
                    ),
                },
            ],
        },
        "decision_contract": {
            "decision": "whether to nominate a later H200 exact-shape component discriminator",
            "falsification_rule": (
                "Return typed_none unless a source-complete, bitwise-compatible "
                "candidate clears 5% of the component and 1% of the measured request "
                "window under a conservative evidence-supported bound."
            ),
            "non_scope": [
                "compilation",
                "GPU execution or claim",
                "endpoint replay",
                "provider mutation",
                "cross-model or cross-accelerator speedup transfer",
            ],
            "quality_gate": "bitwise equality at the BF16-visible down output",
            "question": "Can exact FP8 gate/up-SwiGLU-down materialization support a conservative positive nomination?",
        },
        "generated_at_utc": GENERATED_AT_UTC,
        "identities": {
            "accelerator": "nvidia-h200-sxm",
            "image": IMAGE,
            "model": f"google/gemma-4-31B-it@{MODEL_REVISION}",
            "runtime_commit": RUNTIME_COMMIT,
            "workload": {
                "cached_prompt_tokens_per_request": 535,
                "completion_tokens_per_request": 358,
                "concurrency": 32,
                "logical_component_shape_m": 32,
                "prompt_tokens_per_request": 4214,
                "trace_physical_rows": [
                    {"rows": row["grid_x"], "launches": row["launches"]}
                    for row in down_grid_counts
                ],
            },
        },
        "limitations": [
            "CUPTI kernel durations and correlated runtime APIs are measured, but no DRAM-byte, shared-memory, or fused-candidate counters were collected.",
            "The projection map covers 3,600 dominant M>128 GEMMs, while activation/quant cover 3,660 launches including 60 M=118 invocations; using the dominant GEMMs understates the component denominator and favors nomination.",
            "Correlated host launch duration is credited in full as an upper credit even though it is not proven request-critical.",
            "The point screen is not a measured candidate result and is not predictor calibration.",
        ],
        "measurements": {
            "evidence_type": "measured",
            "kernel_measurements": measurements,
            "projection_families": shape_map["projection_families"],
            "request_trace_boundaries": trace["boundaries"],
            "request_trace_window_seconds": window_seconds,
            "summed_physical_rows": summed_rows,
            "summed_swiglu_output_elements": output_elements,
        },
        "method": {
            "commands": [
                "python3 analyze_swiglu_down_fusion.py",
                "python3 analyze_swiglu_down_fusion.py --check",
            ],
            "formulae": {
                "current_hbm_bytes": "E*(4 gate/up read + 2 BF16 write + 4 two-pass quant read + 1 FP8 write) + 4*M scales",
                "fused_hbm_bytes": "E*(4 gate/up read + 1 FP8 write) + 4*M scales",
                "point_saved_seconds": "pair_seconds*(1-fused_bytes/current_bytes) + max(correlated activation launch, correlated quant launch)",
            },
            "no_cuda_or_compilation": True,
            "script": str((project / "analyze_swiglu_down_fusion.py").relative_to(root)),
        },
        "model_geometry": {
            "activation": "gelu_pytorch_tanh",
            "down_weight_k_n": [21_504, 5_376],
            "gate_up_output": [None, 43_008],
            "gate_up_weight_k_n": [5_376, 43_008],
            "hidden_size": 5_376,
            "intermediate_size": 21_504,
            "layers": 60,
            "swiglu_output": [None, 21_504],
        },
        "result": {
            "evidence_type": "derived_from_measured_and_pinned_source",
            "reason_code": "conservative_whole_request_gate_not_supported",
            "terminal_type": "typed_none",
        },
        "schema_version": 1,
        "source_table": source_table,
        "uncertainty_and_competing_explanations": [
            "A measured fused kernel could outperform the point model, but that would be new evidence rather than a conservative consequence of the retained trace.",
            "A measured fused kernel could also regress because one-CTA row ownership serializes activation work or because shared-memory/barrier overhead dominates the 21.3 ms point margin.",
            "The down GEMM may remain the dominant compute boundary even if activated-intermediate traffic is removed.",
        ],
    }

    causal_text = stable_json(causal_map)
    causal_hash = hashlib.sha256(causal_text.encode()).hexdigest()
    terminal = {
        "actual_spend_usd": 0.0,
        "artifact": "SWIGLU_DOWN_FUSION_TERMINAL",
        "causal_map": {
            "path": "SWIGLU_DOWN_FUSION_CAUSAL_MAP.json",
            "sha256": causal_hash,
        },
        "compilation_performed": False,
        "decision": (
            "Do not nominate an H200 discriminator from this lane. The only "
            "source-complete exact candidate has a favorable point estimate, but "
            "it clears the 1% request gate by only 21.3 ms under unverified "
            "same-bandwidth and full-launch-credit assumptions. That is not a "
            "conservative bound."
        ),
        "generated_at_utc": GENERATED_AT_UTC,
        "gpu_claimed": False,
        "next_action": (
            "Close this zero-GPU lane. Reopen only if independently collected "
            "exact-path counters or an already-authorized target-GPU measurement "
            "can bound fused shared-memory/reduction efficiency; this terminal "
            "does not request a bench."
        ),
        "provider_mutation": False,
        "reason_code": "conservative_whole_request_gate_not_supported",
        "result": "typed_none",
        "schema_version": 1,
        "scientific_sample_consumed": False,
        "terminal_type": "typed_none",
    }
    return causal_map, terminal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail unless checked-in outputs equal a fresh reconstruction",
    )
    args = parser.parse_args()

    script = Path(__file__).resolve()
    root = next(parent for parent in script.parents if (parent / ".git").exists())
    causal_map, terminal = build_artifacts(root)
    outputs = {
        script.parent / "SWIGLU_DOWN_FUSION_CAUSAL_MAP.json": stable_json(causal_map),
        script.parent / "SWIGLU_DOWN_FUSION_TERMINAL.json": stable_json(terminal),
    }
    if args.check:
        for path, expected in outputs.items():
            actual = path.read_text(encoding="utf-8")
            if actual != expected:
                raise RuntimeError(f"artifact differs from reconstruction: {path}")
        print("PASS: causal map and terminal reproduce exactly")
        return 0

    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path} sha256={hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
