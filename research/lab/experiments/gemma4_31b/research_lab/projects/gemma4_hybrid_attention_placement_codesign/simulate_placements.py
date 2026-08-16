#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT.parent
WORKSPACE = next(
    parent
    for parent in (ROOT, *ROOT.parents)
    if (parent / "research/factory/data/accelerator_inventory.json").is_file()
)
FIXED = PROJECTS / "gemma4_h200_ngram_fixed_m384_executor_rewrite"
PROFILE = PROJECTS / "gemma4_h200_v0513_fp8_qkv_residual_profile"
GROUPED_HEAD = PROJECTS / "gemma4_h200_ngram_persistent_grouped_lm_head"

INPUTS = {
    "config": (
        GROUPED_HEAD / "inputs/bound/config.json",
        "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    ),
    "offline_result": (
        FIXED / "FIXED_M384_EXECUTOR_OFFLINE_RESULT.json",
        "87199d4f35a3d4131e1b11cf619547a28ffc1d7d06467237b80cc320efdb67a4",
    ),
    "component": (
        FIXED
        / "artifacts/mixed-local-m384-20260725t165205Z"
        / "preserved-component-attempt-1/COMPONENT_TERMINAL.json",
        "12fb8457e1b54c82de43506e72ef159b40ccf9379eb2f0f84607aef85417b115",
    ),
    "target_trace": (
        FIXED / "inputs/trace/exact_c32_profile.trace.json.gz",
        "37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b",
    ),
    "prefill_subtypes": (
        PROFILE / "ATTENTION_SUBTYPE_MAP.json",
        "554dd2c277762b07f4ae9e38057779ecf2ea810bbd5e78205eb6735567f51d2c",
    ),
    "prefill_profile": (
        PROFILE / "artifacts/global-attention-pair-20260720t1146z/TERMINAL.json",
        "480c2b41044677a6560bdb6426729b9019c1fc761d0c70be6559f8596b6bf4df",
    ),
    "ncu_csv": (
        FIXED
        / "artifacts/mixed-local-m384-20260725t165205Z"
        / "remote-retrieved-20260725t174148Z"
        / "artifacts/mixed-local-m384-20260725t165205Z/counters/ncu.csv",
        "67e03321bc2ed14689ffac8f39305ad91ef2d15506f541b09aab51e198955a74",
    ),
}

BATCH = 32
PREFIX = 4214
DRAFT = 12
WINDOW = 1024
FP8_BYTES = 1
CUTLASS_FP8_PREFIX = "void cutlass::device_kernel<cutlass_3x_gemm_sm90_fp8"


@dataclass(frozen=True)
class LayerGeometry:
    name: str
    head_dim: int
    kv_heads: int
    q_heads: int
    hidden_size: int
    window: int | None

    @property
    def qkv_width(self) -> int:
        return self.q_heads * self.head_dim + 2 * self.kv_heads * self.head_dim

    @property
    def output_width(self) -> int:
        return self.q_heads * self.head_dim

    @property
    def attention_linear_parameters(self) -> int:
        return self.hidden_size * self.qkv_width + self.output_width * self.hidden_size

    @property
    def kv_bytes_per_token(self) -> int:
        return 2 * self.kv_heads * self.head_dim * FP8_BYTES


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def verify_inputs() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for name, (path, expected) in INPUTS.items():
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"binding_mismatch:{name}:{actual}:{expected}")
        rows[name] = {
            "path": str(path.relative_to(WORKSPACE)),
            "sha256": actual,
            "match": True,
        }
    return rows


def tree_mask_true_elements(depth: int) -> int:
    total = 0
    for row in range(depth):
        columns = {row, 0}
        columns.update(
            column for column in range(1, row) if column % 3 == row % 3
        )
        total += len(columns)
    return total


def causal_pairs(length: int, window: int | None) -> int:
    if window is None or window >= length:
        return length * (length + 1) // 2
    return window * (window + 1) // 2 + (length - window) * window


def useful_work(geometry: LayerGeometry) -> dict[str, int]:
    prompt_pairs = causal_pairs(PREFIX, geometry.window)
    verify_pairs = DRAFT * min(PREFIX, geometry.window or PREFIX)
    verify_pairs += tree_mask_true_elements(DRAFT)
    return {
        "attention_linear_parameters": geometry.attention_linear_parameters,
        "prefill_attention_pairs_per_request": prompt_pairs,
        "prefill_attention_flops_c32": (
            BATCH * prompt_pairs * geometry.q_heads * 4 * geometry.head_dim
        ),
        "prefill_projection_flops_c32": (
            BATCH
            * PREFIX
            * 2
            * geometry.attention_linear_parameters
        ),
        "verification_attention_pairs_per_request": verify_pairs,
        "verification_attention_flops_c32": (
            BATCH * verify_pairs * geometry.q_heads * 4 * geometry.head_dim
        ),
        "verification_projection_flops_c32": (
            BATCH * DRAFT * 2 * geometry.attention_linear_parameters
        ),
        "kv_bytes_per_token": geometry.kv_bytes_per_token,
        "kv_residency_bytes_c32_at_prompt": (
            BATCH
            * min(PREFIX, geometry.window or PREFIX)
            * geometry.kv_bytes_per_token
        ),
    }


def trace_projection_costs(
    trace_path: Path, layer_types: list[str]
) -> dict[str, Any]:
    with gzip.open(trace_path, "rt", encoding="utf-8") as handle:
        trace = json.load(handle)
    complete = [
        event
        for event in trace["traceEvents"]
        if event.get("ph") == "X"
        and isinstance(event.get("ts"), (int, float))
        and isinstance(event.get("dur"), (int, float))
    ]
    targets = sorted(
        (
            event
            for event in complete
            if event.get("name") == "ngram.target_forward_verify"
        ),
        key=lambda event: event["ts"],
    )
    accepts = sorted(
        (
            event
            for event in complete
            if event.get("name") == "ngram.accept_bookkeeping_and_cache"
            and event["dur"] > 100_000
        ),
        key=lambda event: event["ts"],
    )
    if len(targets) != 15 or len(accepts) != 15:
        raise RuntimeError(f"unexpected_target_cycles:{len(targets)}:{len(accepts)}")

    samples: dict[str, dict[str, list[float]]] = {
        "sliding_attention": {name: [] for name in ("qkv", "o", "gate_up", "down")},
        "full_attention": {name: [] for name in ("qkv", "o", "gate_up", "down")},
    }
    layer_samples: list[dict[str, Any]] = [
        {
            "layer_index": index,
            "layer_type": layer_type,
            "qkv_us": [],
            "o_us": [],
            "gate_up_us": [],
            "down_us": [],
        }
        for index, layer_type in enumerate(layer_types)
    ]
    operation_names = ("qkv", "o", "gate_up", "down")
    for target, accept in zip(targets, accepts, strict=True):
        interval_end = accept["ts"] + accept["dur"]
        kernels = sorted(
            (
                event
                for event in complete
                if str(event.get("name", "")).startswith(CUTLASS_FP8_PREFIX)
                and target["ts"] <= event["ts"] <= interval_end
            ),
            key=lambda event: event["ts"],
        )
        expected = len(layer_types) * len(operation_names)
        if len(kernels) != expected:
            raise RuntimeError(f"unexpected_fp8_launch_count:{len(kernels)}:{expected}")
        for layer_index, layer_type in enumerate(layer_types):
            for operation_offset, operation in enumerate(operation_names):
                duration = kernels[layer_index * 4 + operation_offset]["dur"]
                samples[layer_type][operation].append(duration)
                layer_samples[layer_index][f"{operation}_us"].append(duration)

    family_medians = {
        layer_type: {
            f"{operation}_median_us": statistics.median(values)
            for operation, values in operations.items()
        }
        for layer_type, operations in samples.items()
    }
    if not (
        family_medians["sliding_attention"]["gate_up_median_us"]
        > family_medians["sliding_attention"]["down_median_us"]
        > family_medians["sliding_attention"]["qkv_median_us"]
        > family_medians["sliding_attention"]["o_median_us"]
    ):
        raise RuntimeError("unexpected_fp8_projection_order")
    return {
        "captured_cycles": len(targets),
        "launches_per_cycle": len(layer_types) * 4,
        "family_medians_us": family_medians,
        "layers": [
            {
                "layer_index": row["layer_index"],
                "layer_type": row["layer_type"],
                **{
                    f"{operation}_median_us": statistics.median(
                        row[f"{operation}_us"]
                    )
                    for operation in operation_names
                },
            }
            for row in layer_samples
        ],
    }


def parse_ncu(path: Path) -> dict[str, dict[str, Any]]:
    lines = path.read_text().splitlines()
    header_index = next(index for index, line in enumerate(lines) if line.startswith('"ID"'))
    rows = [
        row
        for row in csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
        if row["ID"].isdigit()
    ]
    names = ("control_local", "control_global", "candidate_local", "candidate_global")
    if len(rows) != len(names):
        raise RuntimeError(f"unexpected_ncu_rows:{len(rows)}")
    selected = {}
    fields = {
        "duration_ms": "gpu__time_duration.sum",
        "registers_per_thread": "launch__registers_per_thread",
        "dynamic_shared_kib": "launch__shared_mem_per_block_dynamic",
        "waves_per_sm": "launch__waves_per_multiprocessor",
        "dram_read_gb": "dram__bytes_read.sum",
        "l2_bytes_gb": "lts__t_bytes.sum",
        "grid_size": "launch__grid_size",
    }
    for name, row in zip(names, rows, strict=True):
        selected[name] = {
            output_name: float(row[column].replace(",", ""))
            for output_name, column in fields.items()
        }
    return selected


def full_positions(layer_types: list[str]) -> list[int]:
    return [
        index for index, layer_type in enumerate(layer_types) if layer_type == "full_attention"
    ]


def placement(name: str, layer_count: int, full: list[int]) -> dict[str, Any]:
    full_set = set(full)
    return {
        "name": name,
        "layer_types": [
            "full_attention" if index in full_set else "sliding_attention"
            for index in range(layer_count)
        ],
        "full_layer_indices": full,
    }


def main(output_path: Path) -> None:
    bindings = verify_inputs()
    config = load_json(INPUTS["config"][0])["text_config"]
    offline = load_json(INPUTS["offline_result"][0])
    component = load_json(INPUTS["component"][0])
    prefill_subtypes = load_json(INPUTS["prefill_subtypes"][0])
    prefill_profile = load_json(INPUTS["prefill_profile"][0])
    inventory = load_json(
        WORKSPACE / "research/factory/data/accelerator_inventory.json"
    )

    layer_types = config["layer_types"]
    if len(layer_types) != config["num_hidden_layers"]:
        raise RuntimeError("layer_count_mismatch")
    baseline_full = full_positions(layer_types)
    if baseline_full != list(range(5, 60, 6)):
        raise RuntimeError(f"unexpected_baseline_placement:{baseline_full}")

    local = LayerGeometry(
        "sliding_attention",
        config["head_dim"],
        config["num_key_value_heads"],
        config["num_attention_heads"],
        config["hidden_size"],
        config["sliding_window"],
    )
    global_layer = LayerGeometry(
        "full_attention",
        config["global_head_dim"],
        config["num_global_key_value_heads"],
        config["num_attention_heads"],
        config["hidden_size"],
        None,
    )
    geometries = {
        "sliding_attention": local,
        "full_attention": global_layer,
    }
    work = {name: useful_work(value) for name, value in geometries.items()}

    projections = trace_projection_costs(INPUTS["target_trace"][0], layer_types)
    component_rows = {row["layer_type"]: row for row in component["rows"]}
    target_attention_ms = {
        "sliding_attention": component_rows["sliding_window_1024"]["candidate"][
            "median_ms"
        ],
        "full_attention": component_rows["full_attention"]["candidate"]["median_ms"],
    }
    target_attention_stock_ms = {
        "sliding_attention": component_rows["sliding_window_1024"]["control"][
            "median_ms"
        ],
        "full_attention": component_rows["full_attention"]["control"]["median_ms"],
    }

    prefill_rows = {
        row["subtype"]: row for row in prefill_subtypes["subtypes"]
    }
    prefill_attention_seconds_per_layer = {
        "sliding_attention": (
            prefill_rows["local_sliding_extend"]["service_epoch"][
                "pre_median_ttft"
            ]["seconds"]
            / prefill_rows["local_sliding_extend"]["layers_per_model_forward"]
        ),
        "full_attention": (
            prefill_rows["global_extend"]["service_epoch"]["pre_median_ttft"][
                "seconds"
            ]
            / prefill_rows["global_extend"]["layers_per_model_forward"]
        ),
    }
    prefill_fp8_seconds = next(
        row["seconds"]
        for row in prefill_profile["attribution"]["phases"]["prefill"]["boundaries"]
        if row["boundary"] == "fp8_linear"
    )
    mlp_parameters = (
        config["hidden_size"] * (2 * config["intermediate_size"])
        + config["intermediate_size"] * config["hidden_size"]
    )
    baseline_projection_parameters = sum(
        geometries[layer_type].attention_linear_parameters + mlp_parameters
        for layer_type in layer_types
    )
    prefill_projection_seconds_per_layer = {
        name: (
            prefill_fp8_seconds
            * (geometry.attention_linear_parameters + mlp_parameters)
            / baseline_projection_parameters
        )
        for name, geometry in geometries.items()
    }

    candidates = [
        placement("baseline_5_local_1_global", len(layer_types), baseline_full),
        placement(
            "placement_only_phase_shift",
            len(layer_types),
            [3 + 6 * index for index in range(10)],
        ),
        placement(
            "half_global_keep_early_in_each_pair",
            len(layer_types),
            baseline_full[::2],
        ),
        placement("all_local_ceiling", len(layer_types), []),
    ]
    target_projection_ms = {
        name: (
            projections["family_medians_us"][name]["qkv_median_us"]
            + projections["family_medians_us"][name]["o_median_us"]
        )
        / 1000
        for name in geometries
    }
    target_layer_costs = [
        {
            **row,
            "attention_candidate_ms": target_attention_ms[row["layer_type"]],
            "attention_stock_ms": target_attention_stock_ms[row["layer_type"]],
            "attention_plus_all_projections_candidate_ms": (
                target_attention_ms[row["layer_type"]]
                + row["qkv_median_us"] / 1000
                + row["o_median_us"] / 1000
                + row["gate_up_median_us"] / 1000
                + row["down_median_us"] / 1000
            ),
        }
        for row in projections["layers"]
    ]
    prefill_layer_costs = [
        {
            "layer_index": index,
            "layer_type": layer_type,
            "attention_kernel_seconds_per_c32_batch": (
                prefill_attention_seconds_per_layer[layer_type]
            ),
            "flop_calibrated_attention_plus_mlp_linear_seconds_per_c32_batch": (
                prefill_projection_seconds_per_layer[layer_type]
            ),
        }
        for index, layer_type in enumerate(layer_types)
    ]
    baseline_target_variable_ms = sum(
        target_attention_ms[layer_type] + target_projection_ms[layer_type]
        for layer_type in layer_types
    )
    baseline_target_stock_attention_ms = sum(
        target_attention_stock_ms[layer_type] for layer_type in layer_types
    )
    baseline_prefill_attention_seconds = sum(
        prefill_attention_seconds_per_layer[layer_type] for layer_type in layer_types
    )
    baseline_prefill_projection_seconds = sum(
        prefill_projection_seconds_per_layer[layer_type] for layer_type in layer_types
    )
    baseline_kv_bytes = sum(
        work[layer_type]["kv_residency_bytes_c32_at_prompt"]
        for layer_type in layer_types
    )
    baseline_attention_parameters = sum(
        geometries[layer_type].attention_linear_parameters for layer_type in layer_types
    )

    passes = offline["critical_path"]["complete_target_forward_seconds_per_request_range"]
    target_fraction = offline["critical_path"][
        "complete_target_forward_fraction_of_request_range"
    ]
    critical = load_json(FIXED / "artifacts/BOUND_CRITICAL_PATH.json")[
        "target_verification_critical_path"
    ]
    pass_counts = sorted(
        (
            critical["request_equivalent_full_batch_passes"],
            critical["cuda_graph_passes_counter"],
        )
    )
    qualified_baseline = offline["critical_path"][
        "qualified_baseline_seconds_per_request"
    ]

    results = []
    for candidate in candidates:
        types = candidate.pop("layer_types")
        target_variable_ms = sum(
            target_attention_ms[layer_type] + target_projection_ms[layer_type]
            for layer_type in types
        )
        prefill_attention_seconds = sum(
            prefill_attention_seconds_per_layer[layer_type] for layer_type in types
        )
        prefill_projection_seconds = sum(
            prefill_projection_seconds_per_layer[layer_type] for layer_type in types
        )
        kv_bytes = sum(
            work[layer_type]["kv_residency_bytes_c32_at_prompt"]
            for layer_type in types
        )
        attention_parameters = sum(
            geometries[layer_type].attention_linear_parameters for layer_type in types
        )
        target_cycle_savings_seconds = (
            baseline_target_variable_ms - target_variable_ms
        ) / 1000
        verification_savings = [
            target_cycle_savings_seconds * count / BATCH for count in pass_counts
        ]
        prefill_savings = (
            baseline_prefill_attention_seconds
            - prefill_attention_seconds
            + baseline_prefill_projection_seconds
            - prefill_projection_seconds
        ) / BATCH
        whole_savings = [
            prefill_savings + verification for verification in verification_savings
        ]
        projected = [qualified_baseline - saving for saving in whole_savings]
        candidate.update(
            {
                "local_layers": types.count("sliding_attention"),
                "global_layers": types.count("full_attention"),
                "target_verification": {
                    "variable_attention_plus_attention_projection_ms_per_cycle": target_variable_ms,
                    "savings_ms_per_cycle_vs_tuned_50_10": (
                        baseline_target_variable_ms - target_variable_ms
                    ),
                    "predicted_service_savings_seconds_per_request_range": verification_savings,
                },
                "prefill": {
                    "measured_attention_kernel_seconds_per_c32_batch": prefill_attention_seconds,
                    "flop_calibrated_fp8_linear_seconds_per_c32_batch": prefill_projection_seconds,
                    "predicted_service_savings_seconds_per_request": prefill_savings,
                },
                "kv_residency": {
                    "bytes_c32_at_4214_prompt": kv_bytes,
                    "bytes_saved_vs_baseline": baseline_kv_bytes - kv_bytes,
                    "fraction_saved_vs_baseline": (
                        (baseline_kv_bytes - kv_bytes) / baseline_kv_bytes
                    ),
                },
                "attention_linear_parameters": attention_parameters,
                "attention_linear_parameters_removed_vs_baseline": (
                    baseline_attention_parameters - attention_parameters
                ),
                "predicted_whole_request": {
                    "service_seconds_per_request_range": sorted(projected),
                    "savings_seconds_per_request_range": whole_savings,
                    "reduction_fraction_range": [
                        saving / qualified_baseline for saving in whole_savings
                    ],
                },
            }
        )
        results.append(candidate)

    h200 = next(
        row for row in inventory["accelerators"] if row["id"] == "nvidia-h200-sxm"
    )
    ncu = parse_ncu(INPUTS["ncu_csv"][0])
    selected = next(
        row for row in results if row["name"] == "half_global_keep_early_in_each_pair"
    )
    placement_only = next(
        row for row in results if row["name"] == "placement_only_phase_shift"
    )
    if placement_only["predicted_whole_request"]["savings_seconds_per_request_range"] != [
        0.0,
        0.0,
    ]:
        raise RuntimeError("placement_only_cost_should_be_zero")

    output = {
        "schema_version": 1,
        "classification": "source_complete_offline_placement_simulation",
        "bindings": bindings,
        "semantics": {
            "classification": "quality_unsafe_architecture_proxy",
            "reason": (
                "Changing a full-attention layer to sliding attention changes head dimension "
                "512 to 256, KV heads 4 to 16, RoPE, receptive field, projection shapes, "
                "parameters, and checkpoint tensor compatibility."
            ),
        },
        "scope": {
            "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "runtime_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "hardware": h200,
            "batch": BATCH,
            "prompt_tokens_per_request": PREFIX,
            "verification_depth": DRAFT,
            "target_rows": BATCH * DRAFT,
            "qualified_baseline_seconds_per_request": qualified_baseline,
            "target_forward_seconds_per_request_range": passes,
            "target_forward_fraction_of_request_range": target_fraction,
        },
        "geometry": {
            "baseline_full_layer_indices": baseline_full,
            "layer_work": work,
            "tree_mask_true_elements_per_request": tree_mask_true_elements(DRAFT),
        },
        "layer_cost_reconstruction": {
            "target_verification": {
                "evidence_type": "measured_exact_c32_h200_trace_and_component",
                "attention_candidate_median_ms_per_layer": target_attention_ms,
                "attention_stock_median_ms_per_layer": target_attention_stock_ms,
                "attention_projection_median_ms_per_layer": target_projection_ms,
                "trace_projection_detail": projections,
                "layers": target_layer_costs,
                "tuned_50_10_variable_ms_per_cycle": baseline_target_variable_ms,
                "stock_50_10_attention_ms_per_cycle": baseline_target_stock_attention_ms,
            },
            "prefill": {
                "evidence_type": (
                    "measured_scope_matched_c32_h200_attention subtype time plus "
                    "measured aggregate FP8-linear time apportioned by exact projection FLOPs"
                ),
                "attention_seconds_per_layer_per_c32_batch": prefill_attention_seconds_per_layer,
                "fp8_linear_seconds_per_layer_per_c32_batch": prefill_projection_seconds_per_layer,
                "layers": prefill_layer_costs,
                "baseline_attention_kernel_seconds_per_c32_batch": baseline_prefill_attention_seconds,
                "baseline_flop_calibrated_fp8_linear_seconds_per_c32_batch": baseline_prefill_projection_seconds,
            },
        },
        "placements": results,
        "selected_candidate": {
            "name": selected["name"],
            "full_layer_indices": selected["full_layer_indices"],
            "quality_recovery_path": [
                "Initialize only the five converted attention modules from their nearest same-shape sliding-attention neighbors; retain each layer's MLP and norms.",
                "Distill hidden states, attention outputs, and logits from the locked 50/10 teacher on 4K-to-32K text plus long-context retrieval and tool-use trajectories.",
                "Continue pretraining with a curriculum that preserves 1,024-token local behavior before increasing long-context examples.",
                "Require exact served-model GPQA-Diamond and TauBench gates, long-context retrieval, tool-call formatting, and multimodal regression before production eligibility.",
            ],
            "cheapest_later_execution_proxy": (
                "Materialize a quality-unsafe five-module nearest-local weight-copy checkpoint, "
                "run one exact c32 M384 target-forward component comparing 50/10 and 55/5 on "
                "H200, then run an endpoint pair only if component timing and output finiteness pass."
            ),
            "falsifier": (
                "Reject the physical model if a converted layer does not dispatch the measured "
                "local M8 geometry or if the c32 target-forward cycle improves by less than "
                f"{selected['target_verification']['savings_ms_per_cycle_vs_tuned_50_10']:.6f} ms "
                "minus contemporaneous noise; reject the candidate if recovery misses the exact "
                "GPQA-Diamond, TauBench, long-context, or tool-use gates."
            ),
        },
        "physical_prediction": {
            "converted_layers": 5,
            "per_converted_layer_ncu": {
                "removed_global": ncu["candidate_global"],
                "added_local_m8": ncu["candidate_local"],
            },
            "interpretation": (
                "Each conversion replaces a 512-wide, 4-KV-head full-prefix kernel with a "
                "256-wide, 16-KV-head 1,024-window kernel. Measured M8 resources move from "
                "255 to 173 registers/thread and 102.4 to 37.888 KiB dynamic shared memory; "
                "grid waves double while DRAM and L2 bytes fall. The c32 KV footprint falls, "
                "but prior c48/c64 negatives make a batching gain unsupported."
            ),
        },
        "decision": {
            "result": "candidate_half_global_keep_early_in_each_pair",
            "candidate_is_deployable": False,
            "placement_only_same_count_speed_effect": "exactly_zero_in_this_layer-homogeneous_model",
            "predicted_incremental_reduction_fraction_range": selected[
                "predicted_whole_request"
            ]["reduction_fraction_range"],
            "campaign_objective_met": max(
                selected["predicted_whole_request"]["reduction_fraction_range"]
            )
            >= 0.20,
            "interpretation": (
                "The 55-local/5-global candidate is source-complete and physically material, "
                "but predicts only an incremental single-digit whole-request gain. It is a "
                "quality-unsafe candidate for a cheap execution proxy, not a campaign terminal "
                "or production claim."
            ),
        },
        "limitations": [
            "The whole-request range propagates two counter-derived target-pass counts; it is a scenario range, not a statistical confidence interval.",
            "The target-verification attention and projection inputs are exact c32 H200 measurements, but the M8 endpoint consumer produced no durable pair.",
            "The prefill attention subtype input is a scope-matched v0.5.13 c32 H200 profile at 0.7051819141250064 s/request, not the locked qualified denominator.",
            "Prefill FP8-linear time is measured only in aggregate and apportioned to layer geometry by exact projection FLOPs; persistent-kernel latency need not scale perfectly with FLOPs.",
            "No batching benefit is credited, no GPU was claimed, and no model-quality evidence was produced.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".part")
    temporary.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    temporary.replace(output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "PLACEMENT_SIMULATION_RESULT.json",
    )
    arguments = parser.parse_args()
    main(arguments.output)
