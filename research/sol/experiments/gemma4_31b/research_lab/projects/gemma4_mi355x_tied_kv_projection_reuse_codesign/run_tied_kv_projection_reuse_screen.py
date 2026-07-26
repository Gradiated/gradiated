#!/usr/bin/env python3
"""Fail-closed tied-K/V projection-reuse discriminator for exact Gemma 4."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = PROJECT_DIR.parent
WORKSPACE = next(parent for parent in PROJECT_DIR.parents if parent.name == "workspace")

BASELINE_DIR = PROJECTS_DIR / "gemma4_mi355x_fp8_runtime_codesign"
BASELINE_PATH = BASELINE_DIR / "MI355X_FP8_RUNTIME_SCREEN.json"
SOURCE_BINDINGS_PATH = BASELINE_DIR / "SOURCE_BINDINGS.json"
CONFIG_PATH = (
    PROJECTS_DIR
    / "gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/config.json"
)
CHECKPOINT_INDEX_PATH = CONFIG_PATH.with_name("model.safetensors.index.json")
GEMMA_SOURCE_PATH = (
    PROJECTS_DIR
    / "gemma4_b200_fp8_runtime_codesign/evidence/upstream/vllm/"
    "model_executor/models/gemma4.py"
)
DEFAULT_OUTPUT = PROJECT_DIR / "MI355X_TIED_KV_PROJECTION_REUSE_SCREEN.json"

MODEL_ID = "google/gemma-4-31B-it"
MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
VLLM_COMMIT = "0164022c907014a27e81c514cd4dff6091904c2b"
EXPECTED = {
    "baseline": "e1bad18d0d2e0d3e281c3502a3b4a25108d0841ac2da85e5fd0fadebe99cc500",
    "source_bindings": "c7f08b334a36e88009b273535dcbddb64c2c3307dfc7d7cd5a1ee946a04dd1bd",
    "config": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    "checkpoint_index": "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2",
    "gemma_source": "f101ae257cfe4c71e90ced922da04228468dbb84c01af00a0b48fa681f873a0f",
}

HIDDEN = 5376
SLIDING_LAYERS = 50
GLOBAL_LAYERS = 10
SLIDING_Q = 32 * 256
SLIDING_KV = 16 * 256
GLOBAL_Q = 32 * 512
GLOBAL_KV = 4 * 512
TARGET_SECONDS = 0.5910500600431771


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def bind_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    paths = {
        "baseline": BASELINE_PATH,
        "source_bindings": SOURCE_BINDINGS_PATH,
        "config": CONFIG_PATH,
        "checkpoint_index": CHECKPOINT_INDEX_PATH,
        "gemma_source": GEMMA_SOURCE_PATH,
    }
    bindings = {}
    for name, path in paths.items():
        observed = sha256(path)
        bindings[name] = {
            "path": str(path),
            "expected_sha256": EXPECTED[name],
            "observed_sha256": observed,
            "pass": observed == EXPECTED[name],
        }
    failures = [name for name, row in bindings.items() if not row["pass"]]
    if failures:
        raise RuntimeError(f"input binding failed: {failures}")
    return bindings, {
        "baseline": load_json(BASELINE_PATH),
        "source_bindings": load_json(SOURCE_BINDINGS_PATH),
        "config": load_json(CONFIG_PATH),
        "checkpoint_index": load_json(CHECKPOINT_INDEX_PATH),
        "gemma_source": GEMMA_SOURCE_PATH.read_text(),
    }


def layer_projection_names(weight_map: dict[str, str], layer: int) -> set[str]:
    prefix = f"model.language_model.layers.{layer}.self_attn."
    return {
        name.removeprefix(prefix)
        for name in weight_map
        if name.startswith(prefix) and re.search(r"[qkv]_proj\.weight$", name)
    }


def prove_contract(inputs: dict[str, Any]) -> dict[str, Any]:
    config = inputs["config"]["text_config"]
    weight_map = inputs["checkpoint_index"]["weight_map"]
    source = inputs["gemma_source"]
    layer_types = config["layer_types"]
    rows = []
    for layer, layer_type in enumerate(layer_types):
        names = layer_projection_names(weight_map, layer)
        has_q = "q_proj.weight" in names
        has_k = "k_proj.weight" in names
        has_v = "v_proj.weight" in names
        runtime_k_eq_v = (
            config["attention_k_eq_v"] is True
            and layer_type == "full_attention"
            and has_k
            and not has_v
        )
        rows.append(
            {
                "layer": layer,
                "layer_type": layer_type,
                "checkpoint_projection_names": sorted(names),
                "checkpoint_has_q": has_q,
                "checkpoint_has_k": has_k,
                "checkpoint_has_v": has_v,
                "runtime_k_eq_v_contract": runtime_k_eq_v,
            }
        )

    sliding = [row for row in rows if row["layer_type"] == "sliding_attention"]
    global_rows = [row for row in rows if row["layer_type"] == "full_attention"]
    source_needles = {
        "decoder_scopes_k_eq_v_to_full_attention": (
            'use_k_eq_v = self.is_full_attention and getattr('
        ),
        "loader_builds_only_full_layer_set": (
            'if lt == "full_attention":\n'
            "                        k_eq_v_layer_indices.add(idx)"
        ),
        "loader_clones_k_as_v": (
            'yield name.replace("k_proj", "v_proj"), weight.clone()'
        ),
        "loader_documents_sliding_real_v": (
            "# ONLY for full_attention layers — sliding layers have\n"
            "                # their own real v_proj weights."
        ),
        "forward_splits_distinct_logical_outputs": (
            "q, k, v = qkv.split([self.q_size, self.kv_size, self.kv_size], dim=-1)"
        ),
        "real_attention_consumer": "attn_output = self.attn(q, k, v)",
    }
    source_checks = {
        name: {"fragment": needle, "pass": needle in source}
        for name, needle in source_needles.items()
    }
    source_checks["k_and_v_take_separate_pre_attention_paths"] = {
        "fragments": ["k = self.k_norm(k)", "v = self.v_norm(v)"],
        "pass": "k = self.k_norm(k)" in source and "v = self.v_norm(v)" in source,
    }

    sliding_has_independent_v = all(
        row["checkpoint_has_q"] and row["checkpoint_has_k"] and row["checkpoint_has_v"]
        for row in sliding
    )
    global_omits_v = all(
        row["checkpoint_has_q"]
        and row["checkpoint_has_k"]
        and not row["checkpoint_has_v"]
        for row in global_rows
    )
    global_contract = (
        len(global_rows) == GLOBAL_LAYERS
        and global_omits_v
        and all(row["runtime_k_eq_v_contract"] for row in global_rows)
        and all(row["pass"] for row in source_checks.values())
    )
    all_layer_contract = (
        global_contract
        and len(sliding) == SLIDING_LAYERS
        and not sliding_has_independent_v
        and all(row["runtime_k_eq_v_contract"] for row in sliding)
    )

    return {
        "config": {
            "attention_k_eq_v": config["attention_k_eq_v"],
            "attention_bias": config["attention_bias"],
            "layer_count": len(layer_types),
            "sliding_layer_count": len(sliding),
            "global_layer_count": len(global_rows),
        },
        "checkpoint_metadata": {
            "metadata": inputs["checkpoint_index"]["metadata"],
            "projection_entry_count": sum(
                len(row["checkpoint_projection_names"]) for row in rows
            ),
            "sliding_layers_with_distinct_v_entry": sum(
                row["checkpoint_has_v"] for row in sliding
            ),
            "global_layers_with_distinct_v_entry": sum(
                row["checkpoint_has_v"] for row in global_rows
            ),
            "checkpoint_bytes_read": CHECKPOINT_INDEX_PATH.stat().st_size,
            "checkpoint_tensor_bytes_read": 0,
            "checkpoint_copied_or_downloaded": False,
        },
        "source_checks": source_checks,
        "layer_rows": rows,
        "global_raw_k_equals_raw_v_contract": global_contract,
        "sliding_raw_k_equals_raw_v_contract": not sliding_has_independent_v,
        "all_60_layers_raw_k_equals_raw_v_contract": all_layer_contract,
        "finding": (
            "attention_k_eq_v is a ten-full-layer contract. The fifty sliding "
            "layers own checkpoint v_proj tensors and are not admissible for "
            "raw K/V projection reuse."
        ),
    }


def dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def project(
    rows: list[list[float]], weights: list[list[float]]
) -> list[list[float]]:
    return [[dot(row, weight) for weight in weights] for row in rows]


def rms_norm(
    rows: list[list[float]], head_dim: int, weight: list[float] | None
) -> list[list[float]]:
    outputs = []
    for row in rows:
        output = []
        for offset in range(0, len(row), head_dim):
            head = row[offset : offset + head_dim]
            inverse_rms = 1.0 / math.sqrt(
                sum(value * value for value in head) / head_dim + 1e-6
            )
            for index, value in enumerate(head):
                scale = 1.0 if weight is None else weight[index]
                output.append(value * inverse_rms * scale)
        outputs.append(output)
    return outputs


def rope(rows: list[list[float]], positions: list[int]) -> list[list[float]]:
    outputs = []
    for row, position in zip(rows, positions, strict=True):
        angle = position * 0.03125
        cosine = math.cos(angle)
        sine = math.sin(angle)
        output = []
        for offset in range(0, len(row), 2):
            first, second = row[offset : offset + 2]
            output.extend(
                [first * cosine - second * sine, first * sine + second * cosine]
            )
        outputs.append(output)
    return outputs


def attention_consumer(
    queries: list[list[float]],
    keys: list[list[float]],
    values: list[list[float]],
    q_heads: int,
    kv_heads: int,
    head_dim: int,
) -> list[list[float]]:
    outputs = []
    group = q_heads // kv_heads
    for query, key, value in zip(queries, keys, values, strict=True):
        output = []
        for q_head in range(q_heads):
            kv_head = q_head // group
            q_slice = query[q_head * head_dim : (q_head + 1) * head_dim]
            k_slice = key[kv_head * head_dim : (kv_head + 1) * head_dim]
            v_slice = value[kv_head * head_dim : (kv_head + 1) * head_dim]
            score = dot(q_slice, k_slice) / math.sqrt(head_dim)
            output.extend(component * score for component in v_slice)
        outputs.append(output)
    return outputs


def max_abs(left: list[list[float]], right: list[list[float]]) -> float:
    return max(
        abs(a - b)
        for left_row, right_row in zip(left, right, strict=True)
        for a, b in zip(left_row, right_row, strict=True)
    )


def deterministic_matrix(rows: int, columns: int, salt: int) -> list[list[float]]:
    return [
        [
            (((row + 1) * 17 + (column + 1) * 13 + salt * 19) % 41 - 20) / 23
            for column in range(columns)
        ]
        for row in range(rows)
    ]


def semantic_fixture(
    *,
    phase: str,
    m: int,
    tied: bool,
) -> dict[str, Any]:
    hidden = 4
    q_heads = 2
    kv_heads = 1
    head_dim = 2
    inputs = deterministic_matrix(m, hidden, 1)
    q_weight = deterministic_matrix(q_heads * head_dim, hidden, 2)
    k_weight = deterministic_matrix(kv_heads * head_dim, hidden, 3)
    v_weight = k_weight if tied else deterministic_matrix(kv_heads * head_dim, hidden, 7)
    q_raw = project(inputs, q_weight)
    k_raw = project(inputs, k_weight)
    stock_v_raw = project(inputs, v_weight)
    candidate_v_raw = k_raw
    positions = list(range(m))
    q = rope(rms_norm(q_raw, head_dim, [1.1, 0.9]), positions)
    k = rope(rms_norm(k_raw, head_dim, [0.8, 1.2]), positions)
    stock_v = rms_norm(stock_v_raw, head_dim, None)
    candidate_v = rms_norm(candidate_v_raw, head_dim, None)
    stock_attention = attention_consumer(
        q, k, stock_v, q_heads, kv_heads, head_dim
    )
    candidate_attention = attention_consumer(
        q, k, candidate_v, q_heads, kv_heads, head_dim
    )
    raw_v_max_abs = max_abs(stock_v_raw, candidate_v_raw)
    attention_max_abs = max_abs(stock_attention, candidate_attention)
    return {
        "phase": phase,
        "m": m,
        "fixture_geometry": {
            "hidden": hidden,
            "q_heads": q_heads,
            "kv_heads": kv_heads,
            "head_dim": head_dim,
            "production_shape_bound_separately": True,
        },
        "tied_weight_fixture": tied,
        "q_max_abs": 0.0,
        "post_transform_k_max_abs": 0.0,
        "raw_v_max_abs": raw_v_max_abs,
        "attention_input_v_max_abs": max_abs(stock_v, candidate_v),
        "attention_output_max_abs": attention_max_abs,
        "finite": all(
            math.isfinite(value)
            for matrix in (q, k, stock_v, candidate_v, stock_attention, candidate_attention)
            for row in matrix
            for value in row
        ),
        "semantic_match": raw_v_max_abs == 0.0 and attention_max_abs == 0.0,
    }


def fixture_results() -> dict[str, Any]:
    phases = (("prefill", 5), ("ordinary_decode_m32", 32), ("target_m384", 384))
    global_rows = [
        semantic_fixture(phase=phase, m=m, tied=True) for phase, m in phases
    ]
    sliding_counterexamples = [
        semantic_fixture(phase=phase, m=m, tied=False) for phase, m in phases
    ]
    return {
        "execution_type": "deterministic_dependency_free_cpu_semantic_fixture",
        "global_pre_normalization_fork": global_rows,
        "sliding_forced_alias_counterexample": sliding_counterexamples,
        "global_all_match": all(row["semantic_match"] for row in global_rows),
        "sliding_all_diverge": all(
            not row["semantic_match"] for row in sliding_counterexamples
        ),
        "scope_boundary": (
            "The fixture executes the producer, separate K/V normalization and "
            "RoPE paths, GQA mapping, and attention input consumption at the "
            "three exact M values with reduced feature dimensions. It is a "
            "semantic discriminator, not a target-runtime or GPU measurement."
        ),
    }


def economic_floor(baseline: dict[str, Any]) -> dict[str, Any]:
    baseline_screen = baseline["physical_cost_screen"][
        "conservative_screen_seconds_per_request"
    ]
    transformer_params = baseline["geometry"]["executed_transformer_linear_parameters"]
    claimed_sliding = SLIDING_LAYERS * HIDDEN * SLIDING_KV
    proven_global = GLOBAL_LAYERS * HIDDEN * GLOBAL_KV
    eligible_fraction = proven_global / transformer_params
    credited_names = {
        "prefill_fp8_transformer_linears",
        "ordinary_decode_fp8_transformer_linears",
        "target_verification_m384_transformer",
    }
    credits = []
    for row in baseline["physical_cost_screen"]["line_items"]:
        if row["name"] in credited_names:
            credits.append(
                {
                    "baseline_line_item": row["name"],
                    "baseline_seconds_per_request": row["seconds_per_request"],
                    "ideal_proportional_credit_seconds_per_request": (
                        row["seconds_per_request"] * eligible_fraction
                    ),
                    "rule": (
                        "Optimistically credit the proven global V parameter "
                        "fraction at perfect proportionality with no shape penalty."
                    ),
                }
            )
    ideal_credit = sum(
        row["ideal_proportional_credit_seconds_per_request"] for row in credits
    )
    ideal_floor = baseline_screen - ideal_credit
    overheads = [
        ("reduced_qk_kernel_shape_and_tile_efficiency", 0.0),
        ("raw_kv_fork_or_copy", 0.0),
        ("attention_layout_materialization", 0.0),
        ("separate_k_norm_v_norm_and_rope", 0.0),
        ("cuda_graph_metadata_and_capture", 0.0),
        ("fallback_dispatch", 0.0),
        ("additional_activation_or_workspace_memory", 0.0),
        ("additional_launches", 0.0),
    ]
    return {
        "baseline_seconds_per_request": baseline_screen,
        "target_seconds_per_request": TARGET_SECONDS,
        "preregistered_claimed_redundant_parameters": claimed_sliding + proven_global,
        "invalid_sliding_redundant_parameters": claimed_sliding,
        "source_proven_global_redundant_parameters": proven_global,
        "source_proven_fraction_of_transformer_linears": eligible_fraction,
        "exact_shapes": {
            "sliding_stock_and_required_semantic_shape": {
                "m": ["prefill_dynamic", 32, 384],
                "k": HIDDEN,
                "n": SLIDING_Q + 2 * SLIDING_KV,
                "reason": "Distinct checkpoint V prevents column removal.",
            },
            "global_stock": {
                "m": ["prefill_dynamic", 32, 384],
                "k": HIDDEN,
                "n": GLOBAL_Q + 2 * GLOBAL_KV,
                "n_tiles_128": (GLOBAL_Q + 2 * GLOBAL_KV) // 128,
            },
            "global_q_plus_shared_kv": {
                "m": ["prefill_dynamic", 32, 384],
                "k": HIDDEN,
                "n": GLOBAL_Q + GLOBAL_KV,
                "n_tiles_128": (GLOBAL_Q + GLOBAL_KV) // 128,
                "m32_nominal_waves_over_256_cus": (
                    (GLOBAL_Q + GLOBAL_KV) // 128 / 256
                ),
                "m384_nominal_waves_over_256_cus_at_m_tile_128": (
                    3 * ((GLOBAL_Q + GLOBAL_KV) // 128) / 256
                ),
            },
        },
        "ideal_proportional_credits": credits,
        "ideal_credit_seconds_per_request": ideal_credit,
        "new_cost_floor": {
            "line_items": [
                {
                    "name": name,
                    "seconds_per_request": seconds,
                    "evidence_type": "optimistic_analytical_floor",
                    "rule": (
                        "Set to zero to give the mechanism its strongest possible "
                        "case; any real cost can only worsen the rejection."
                    ),
                }
                for name, seconds in overheads
            ],
            "normalization_rope_attention_kv_tied_head_launch_and_service": (
                "All unchanged baseline line items remain fully charged."
            ),
            "checkpoint_static_memory_credit_bytes": 0,
            "runtime_fp8_global_v_weight_credit_bytes": proven_global,
            "activation_memory_double_credit_bytes": 0,
            "rule": (
                "The transformer-line-item credit already includes the only "
                "admissible global weight/FLOP reduction. No L2, graph, fusion, "
                "launch, service, or NVIDIA-transfer credit is taken."
            ),
        },
        "ideal_zero_overhead_floor_seconds_per_request": ideal_floor,
        "margin_to_target_seconds_per_request": TARGET_SECONDS - ideal_floor,
        "passes_target_even_with_zero_new_cost": ideal_floor <= TARGET_SECONDS,
        "interpretation": (
            "Even perfect global-only reuse with zero packing, fork, layout, "
            "graph, fallback, memory, launch, or service penalty misses the "
            "required target. The all-layer credit needed to clear it is "
            "semantically forbidden by the checkpoint and pinned loader."
        ),
    }


def build_artifact() -> dict[str, Any]:
    bindings, inputs = bind_inputs()
    contract = prove_contract(inputs)
    fixtures = fixture_results()
    economics = economic_floor(inputs["baseline"])
    invalid_contract = not contract["all_60_layers_raw_k_equals_raw_v_contract"]
    misses_floor = not economics["passes_target_even_with_zero_new_cost"]
    terminal = (
        "typed_none"
        if invalid_contract and misses_floor
        else "unexpected_nonterminal_requires_manual_review"
    )
    return {
        "schema_version": 1,
        "terminal": terminal,
        "classification": "typed_none_semantic_contract_and_economic_floor"
        if terminal == "typed_none"
        else terminal,
        "scope": {
            "model": MODEL_ID,
            "revision": MODEL_REVISION,
            "vllm_commit": VLLM_COMMIT,
            "hardware_scope": "one AMD MI355X/gfx950 TP1",
            "execution_scope": "local CPU only; no accelerator or provider contact",
            "baseline": "unstacked 0.6000950932112802 s/request analytical screen",
            "target_seconds_per_request": TARGET_SECONDS,
        },
        "identity": {
            "inputs": bindings,
            "calculator": {
                "path": str(Path(__file__).resolve()),
                "sha256": sha256(Path(__file__).resolve()),
            },
        },
        "raw_projection_contract": contract,
        "fixtures": fixtures,
        "physical_and_full_request_accounting": economics,
        "intervention": {
            "preregistered_path": (
                "Q plus one shared raw K/V projection, forked before K-only "
                "normalization/RoPE and V normalization, through prefill, M32, "
                "and M384 attention consumers."
            ),
            "status": "not_implemented_invalid_preregistered_contract",
            "reason": (
                "Implementing the path in all 50 sliding layers would replace "
                "independent learned V projections with K and change model "
                "semantics. A global-only path cannot clear the economic target "
                "even under a zero-overhead lower bound."
            ),
            "global_only_source_feasibility": (
                "Source and CPU fixtures support a pre-normalization fork in "
                "the ten full-attention layers, but this is not promoted."
            ),
            "source_complete_measurement_candidate": False,
        },
        "decision": {
            "result": terminal,
            "semantic_gate_pass": not invalid_contract,
            "fixture_counterexample_pass": fixtures["sliding_all_diverge"],
            "economic_gate_pass": not misses_floor,
            "measurement_candidate_emitted": False,
            "typed_negative": (
                "The exact all-layer tied-K/V projection-reuse mechanism is "
                "inadmissible, and its admissible ten-global-layer subset has "
                "an ideal 0.598732148102411 s/request floor, above "
                "0.5910500600431771."
            ),
        },
        "evidence_labels": {
            "checkpoint_layout": "measured from immutable local index metadata",
            "runtime_contract": "source_backed at pinned vLLM commit",
            "fixtures": "measured local CPU synthetic counterexample",
            "economic_floor": "derived from bound baseline with optimistic zero overhead",
            "target_hardware_timing": "not measured and not claimed",
        },
        "prohibited_actions_respected": [
            "no checkpoint tensor bytes read, copied, or downloaded",
            "no path sweep or gain stacking",
            "no accelerator claim or GPU inventory mutation",
            "no provider contact, paid API, or resource creation",
            "no modification of the paid MI355X falsifier",
            "zero provider spend",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifact = build_artifact()
    atomic_json(args.output.resolve(), artifact)
    print(
        json.dumps(
            {
                "terminal": artifact["terminal"],
                "classification": artifact["classification"],
                "all_layer_contract": artifact["raw_projection_contract"][
                    "all_60_layers_raw_k_equals_raw_v_contract"
                ],
                "ideal_floor_seconds_per_request": artifact[
                    "physical_and_full_request_accounting"
                ]["ideal_zero_overhead_floor_seconds_per_request"],
                "target_seconds_per_request": TARGET_SECONDS,
                "output": str(args.output.resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
