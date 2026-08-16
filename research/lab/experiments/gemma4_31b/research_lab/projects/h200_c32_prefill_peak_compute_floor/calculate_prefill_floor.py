#!/usr/bin/env python3

import hashlib
import json
from decimal import Decimal, getcontext
from fractions import Fraction
from pathlib import Path


getcontext().prec = 50

PROJECT_DIR = Path(__file__).resolve().parent
LAB_DIR = PROJECT_DIR.parents[1]
WORKSPACE = next(parent for parent in PROJECT_DIR.parents if parent.name == "workspace")

SOURCES = {
    "geometry": LAB_DIR / "projects/exact_geometry_runtime_opportunities/GEOMETRY.json",
    "linears_head_terminal": LAB_DIR / "projects/h200_bf16_exact_linear_floor/artifacts/RECONCILED_TERMINAL.json",
    "kv_floor_exclusion_guard": LAB_DIR / "projects/h200_bf16_kv_attention_bandwidth_floor/KV_ATTENTION_FLOOR.json",
    "economic_gate": LAB_DIR / "projects/h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json",
    "accelerator_inventory": WORKSPACE / "research/factory/data/accelerator_inventory.json",
}

EXPECTED_HASHES = {
    "geometry": "024450cd944c7827db442d8274e1e0cccae114ee3bbb2e0473704f2fbf0e3a72",
    "linears_head_terminal": "9f12b3ae4c8d82176f0ec9b09845c6e97ab1f278a458bd023adcbe433fd004fe",
    "kv_floor_exclusion_guard": "8d0d1ef6bc39adef386a072947bc0ae820e3193af4d6e8b28c19bc6f59fcb442",
    "economic_gate": "3f4ce08c7e3a6649c18af99f14e0d48dcaf3979ac818462f7cf159cd9dab9afd",
    "accelerator_inventory": "bcb33ac6814400f6ab79faa7e44c0ced2d6fe2ac5d19dc43f4ee10b12d7ea6b8",
}

MODEL_ID = "google/gemma-4-31B-it"
MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
CACHE_FRACTION = Fraction(127, 1000)
FRESH_TOKENS = Fraction(PROMPT_TOKENS) * (1 - CACHE_FRACTION)
CONCURRENCY = 32
STRICT_CEILING = Decimal("0.47201182295214134")
LENIENT_CEILING = Decimal("0.47751364375858635")
DECODE_LINEARS_HEAD_SECONDS = Decimal("0.22476958992984145")
EXPECTED_DECODE_KV_FLOOR_SECONDS = Decimal("0.05799790933333333")

SHAPES = {
    "sliding": {
        "layers": 50,
        "linears": {
            "qkv": (5376, 16384),
            "attention_output": (8192, 5376),
            "gate_up": (5376, 43008),
            "down": (21504, 5376),
        },
        "query_heads": 32,
        "kv_heads": 16,
        "head_dim": 256,
        "window": 1024,
    },
    "global": {
        "layers": 10,
        "linears": {
            "qkv": (5376, 20480),
            "attention_output": (16384, 5376),
            "gate_up": (5376, 43008),
            "down": (21504, 5376),
        },
        "query_heads": 32,
        "kv_heads": 4,
        "head_dim": 512,
        "window": None,
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text())


def fraction_record(value: Fraction):
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": str(Decimal(value.numerator) / Decimal(value.denominator)),
    }


def decimal_from_fraction(value: Fraction) -> Decimal:
    return Decimal(value.numerator) / Decimal(value.denominator)


def linear_geometry():
    regimes = {}
    total_macs_per_token = 0
    for name, regime in SHAPES.items():
        linear_rows = []
        macs_per_layer = 0
        for linear_name, (input_width, output_width) in regime["linears"].items():
            parameters = input_width * output_width
            macs_per_layer += parameters
            linear_rows.append(
                {
                    "name": linear_name,
                    "input_width": input_width,
                    "output_width": output_width,
                    "parameters": parameters,
                    "macs_per_prompt_token_per_layer": parameters,
                    "flops_per_prompt_token_per_layer": 2 * parameters,
                }
            )
        architecture_macs = regime["layers"] * macs_per_layer
        total_macs_per_token += architecture_macs
        regimes[name] = {
            "layers": regime["layers"],
            "linears": linear_rows,
            "parameters_and_macs_per_prompt_token_per_layer": macs_per_layer,
            "flops_per_prompt_token_per_layer": 2 * macs_per_layer,
            "architecture_macs_per_prompt_token": architecture_macs,
            "architecture_flops_per_prompt_token": 2 * architecture_macs,
        }
    return regimes, total_macs_per_token, 2 * total_macs_per_token


def attended_pairs(cache_tokens: int):
    fresh_tokens = PROMPT_TOKENS - cache_tokens
    sliding_pairs = sum(
        min(SHAPES["sliding"]["window"], cache_tokens + fresh_index)
        for fresh_index in range(1, fresh_tokens + 1)
    )
    global_pairs = fresh_tokens * cache_tokens + fresh_tokens * (fresh_tokens + 1) // 2
    return {
        "cache_tokens": cache_tokens,
        "fresh_tokens": fresh_tokens,
        "sliding_attended_query_kv_pairs_per_layer": sliding_pairs,
        "global_attended_query_kv_pairs_per_layer": global_pairs,
    }


def attention_flops(sliding_pairs: Fraction, global_pairs: Fraction):
    result = {}
    total = Fraction(0)
    for name, pairs in (("sliding", sliding_pairs), ("global", global_pairs)):
        regime = SHAPES[name]
        qk_per_layer = Fraction(2 * regime["query_heads"] * regime["head_dim"]) * pairs
        av_per_layer = Fraction(2 * regime["query_heads"] * regime["head_dim"]) * pairs
        architecture_qk = regime["layers"] * qk_per_layer
        architecture_av = regime["layers"] * av_per_layer
        architecture_total = architecture_qk + architecture_av
        total += architecture_total
        result[name] = {
            "layers": regime["layers"],
            "query_heads": regime["query_heads"],
            "kv_heads": regime["kv_heads"],
            "head_dim": regime["head_dim"],
            "attended_query_kv_pairs_per_layer": fraction_record(pairs),
            "qk_flops_architecture": fraction_record(architecture_qk),
            "av_flops_architecture": fraction_record(architecture_av),
            "qk_plus_av_flops_architecture": fraction_record(architecture_total),
        }
    return result, total


def ceiling_comparison(ceiling: Decimal, prefill_linear_seconds: Decimal, attention_seconds: Decimal):
    residual_after_linear = ceiling - DECODE_LINEARS_HEAD_SECONDS - prefill_linear_seconds
    residual_after_attention_sensitivity = residual_after_linear - attention_seconds
    return {
        "whole_service_ceiling_seconds_per_request": str(ceiling),
        "decode_linears_plus_head_seconds_per_request": str(DECODE_LINEARS_HEAD_SECONDS),
        "prefill_linear_floor_seconds_per_request": str(prefill_linear_seconds),
        "combined_disjoint_floor_seconds_per_request": str(
            DECODE_LINEARS_HEAD_SECONDS + prefill_linear_seconds
        ),
        "residual_after_disjoint_linear_floor_seconds_per_request": str(residual_after_linear),
        "residual_after_disjoint_linear_floor_percent_of_ceiling": str(
            residual_after_linear / ceiling * 100
        ),
        "maximum_actual_decode_attention_seconds_per_request_if_every_other_omission_were_zero": str(
            residual_after_linear
        ),
        "qk_av_impossible_ideal_sensitivity_seconds_per_request": str(attention_seconds),
        "combined_with_qk_av_sensitivity_seconds_per_request": str(
            DECODE_LINEARS_HEAD_SECONDS + prefill_linear_seconds + attention_seconds
        ),
        "residual_after_qk_av_sensitivity_seconds_per_request": str(
            residual_after_attention_sensitivity
        ),
        "residual_after_qk_av_sensitivity_percent_of_ceiling": str(
            residual_after_attention_sensitivity / ceiling * 100
        ),
        "maximum_actual_decode_attention_seconds_per_request_after_qk_av_sensitivity_if_every_other_omission_were_zero": str(
            residual_after_attention_sensitivity
        ),
        "closed_by_disjoint_linear_floor": residual_after_linear < 0,
        "closed_after_qk_av_sensitivity": residual_after_attention_sensitivity < 0,
    }


def main():
    actual_hashes = {name: sha256(path) for name, path in SOURCES.items()}
    if actual_hashes != EXPECTED_HASHES:
        raise RuntimeError(f"source identity mismatch: {actual_hashes}")

    geometry = load_json(SOURCES["geometry"])
    linears = load_json(SOURCES["linears_head_terminal"])
    kv_floor = load_json(SOURCES["kv_floor_exclusion_guard"])
    gate = load_json(SOURCES["economic_gate"])
    inventory = load_json(SOURCES["accelerator_inventory"])

    target = geometry["identities"]["target_model"]
    measured_geometry = geometry["target_text_geometry_measured_from_config"]
    assert target["id"] == MODEL_ID and target["revision"] == MODEL_REVISION
    assert measured_geometry["num_hidden_layers"] == 60
    assert measured_geometry["attention_pattern"]["sliding_attention_layers"] == 50
    assert measured_geometry["attention_pattern"]["full_attention_layers"] == 10
    assert measured_geometry["hidden_size"] == 5376
    assert measured_geometry["intermediate_size"] == 21504
    assert measured_geometry["num_attention_heads"] == 32
    assert measured_geometry["head_dim_sliding"] == 256
    assert measured_geometry["num_key_value_heads_sliding"] == 16
    assert measured_geometry["global_head_dim"] == 512
    assert measured_geometry["num_global_key_value_heads"] == 4
    assert measured_geometry["sliding_window_tokens"] == 1024

    assert linears["economic_gate"]["model"].lower() == MODEL_ID.lower()
    assert linears["economic_gate"]["revision"] == MODEL_REVISION
    assert linears["economic_gate"]["workload"] == {
        "prompt_tokens": PROMPT_TOKENS,
        "output_tokens": OUTPUT_TOKENS,
        "cache_prompt_fraction": 0.127,
    }
    m32 = next(row for row in linears["combined_cuda_event_component_floor"] if row["m"] == 32)
    assert Decimal(str(m32["combined_seconds_per_request_358_steps"])) == DECODE_LINEARS_HEAD_SECONDS
    assert gate["identities"]["model"].lower() == MODEL_ID.lower()
    assert gate["identities"]["revision"] == MODEL_REVISION
    assert gate["identities"]["workload_campaign_mix"] == {
        "prompt_tokens": PROMPT_TOKENS,
        "output_tokens": OUTPUT_TOKENS,
        "cache_prompt_fraction": 0.127,
        "fresh_prompt_tokens": 3678.822,
        "cache_prompt_tokens": 535.178,
        "total_tokens": 4572,
    }
    assert gate["campaign_mix_throughput_interpretation"]["planning_rate_frontier_rps"]["planning_base_all_in"] == [
        2.094181,
        2.118591,
    ]
    assert Decimal(
        str(linears["economic_gate"]["planning_base_total_service_ceiling_seconds_per_request"]["strict"])
    ) == STRICT_CEILING
    assert Decimal(
        str(linears["economic_gate"]["planning_base_total_service_ceiling_seconds_per_request"]["lenient"])
    ) == LENIENT_CEILING

    h200 = next(item for item in inventory["accelerators"] if item["id"] == "nvidia-h200-sxm")
    assert h200["model"] == "H200 SXM"
    assert h200["peak_math"]["bf16_tflops"] == 989.5
    assert h200["peak_math"]["fp8_tflops"] == 1979
    peak_flops_per_second = Fraction(9895, 10) * 10**12

    kv_c32 = next(row for row in kv_floor["operating_points"] if row["batch_concurrency"] == 32)
    kv_floor_seconds = Decimal(
        str(kv_c32["bandwidth_floors_seconds_per_request"]["h200_4_8_tb_s_full_50_mib_l2_credit_each_step"])
    )
    assert kv_floor_seconds == EXPECTED_DECODE_KV_FLOOR_SECONDS
    assert Decimal(
        str(kv_c32["residual_comparison"]["strict"]["measured_linears_plus_head_seconds_per_request"])
    ) == DECODE_LINEARS_HEAD_SECONDS

    regimes, total_macs_per_token, total_flops_per_token = linear_geometry()
    assert total_macs_per_token == 29_396_828_160
    assert total_flops_per_token == 58_793_656_320
    prefill_linear_flops = FRESH_TOKENS * total_flops_per_token
    prefill_linear_seconds_fraction = prefill_linear_flops / peak_flops_per_second
    prefill_linear_seconds = decimal_from_fraction(prefill_linear_seconds_fraction)

    cache_535 = attended_pairs(535)
    cache_536 = attended_pairs(536)
    primary_weights = {535: Fraction(822, 1000), 536: Fraction(178, 1000)}
    assert sum(primary_weights.values()) == 1
    assert sum(Fraction(cache) * weight for cache, weight in primary_weights.items()) == Fraction(267589, 500)
    assert sum(Fraction(PROMPT_TOKENS - cache) * weight for cache, weight in primary_weights.items()) == FRESH_TOKENS
    primary_sliding_pairs = sum(
        primary_weights[row["cache_tokens"]] * row["sliding_attended_query_kv_pairs_per_layer"]
        for row in (cache_535, cache_536)
    )
    primary_global_pairs = sum(
        primary_weights[row["cache_tokens"]] * row["global_attended_query_kv_pairs_per_layer"]
        for row in (cache_535, cache_536)
    )
    primary_attention_detail, primary_attention_flops = attention_flops(
        primary_sliding_pairs, primary_global_pairs
    )
    primary_attention_seconds_fraction = primary_attention_flops / peak_flops_per_second
    primary_attention_seconds = decimal_from_fraction(primary_attention_seconds_fraction)

    block_row = attended_pairs(528)
    block_attention_detail, block_attention_flops = attention_flops(
        Fraction(block_row["sliding_attended_query_kv_pairs_per_layer"]),
        Fraction(block_row["global_attended_query_kv_pairs_per_layer"]),
    )
    block_linear_flops = Fraction(block_row["fresh_tokens"] * total_flops_per_token)
    block_linear_seconds = decimal_from_fraction(block_linear_flops / peak_flops_per_second)
    block_attention_seconds = decimal_from_fraction(block_attention_flops / peak_flops_per_second)

    comparisons = {
        "strict": ceiling_comparison(STRICT_CEILING, prefill_linear_seconds, primary_attention_seconds),
        "lenient": ceiling_comparison(LENIENT_CEILING, prefill_linear_seconds, primary_attention_seconds),
    }
    decision = (
        "c32_closed_by_disjoint_prefill_plus_decode_floor"
        if all(row["closed_by_disjoint_linear_floor"] for row in comparisons.values())
        else "c32_preserved_with_attention_threshold"
    )

    calculator_hash = sha256(Path(__file__).resolve())
    manifest = {
        "schema_version": 1,
        "calculator": {"path": str(Path(__file__).resolve()), "sha256": calculator_hash},
        "sources": {
            name: {"path": str(SOURCES[name]), "sha256": actual_hashes[name]}
            for name in SOURCES
        },
        "bound_extracts": {
            "model": MODEL_ID,
            "revision": MODEL_REVISION,
            "runtime_image": linears["measurement_validity"]["runtime_image"],
            "vllm_version": linears["measurement_validity"]["vllm_version"],
            "h200_id": h200["id"],
            "h200_dense_non_sparse_bf16_tflops": h200["peak_math"]["bf16_tflops"],
            "h200_dense_fp8_tflops_not_used": h200["peak_math"]["fp8_tflops"],
            "h200_two_to_four_sparse_bf16_tflops_not_used": 2
            * h200["peak_math"]["bf16_tflops"],
            "decode_linears_head_c32_seconds_per_request": str(DECODE_LINEARS_HEAD_SECONDS),
            "decode_kv_floor_seconds_per_request_excluded": str(kv_floor_seconds),
            "strict_ceiling_seconds_per_request": str(STRICT_CEILING),
            "lenient_ceiling_seconds_per_request": str(LENIENT_CEILING),
        },
    }
    manifest_path = PROJECT_DIR / "SOURCE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest_hash = sha256(manifest_path)

    artifact = {
        "schema_version": 1,
        "status": "complete",
        "decision": decision,
        "evidence_type": "exact_integer_arithmetic_plus_optimistic_vendor_peak_analytical_floor",
        "scope": {
            "model": MODEL_ID,
            "revision": MODEL_REVISION,
            "runtime": linears["measurement_validity"]["runtime_image"],
            "tp": 1,
            "dtype": "bfloat16",
            "concurrency": CONCURRENCY,
            "prompt_tokens": PROMPT_TOKENS,
            "output_tokens": OUTPUT_TOKENS,
            "campaign_cache_fraction": fraction_record(CACHE_FRACTION),
            "campaign_fresh_prompt_tokens_per_request": fraction_record(FRESH_TOKENS),
        },
        "identity": {
            "pass": True,
            "source_manifest": {"path": str(manifest_path), "sha256": manifest_hash},
            "source_hashes": actual_hashes,
        },
        "peak_denominator": {
            "accelerator": h200["id"],
            "dense_non_sparse_bf16_tflops": h200["peak_math"]["bf16_tflops"],
            "flops_per_second": fraction_record(peak_flops_per_second),
            "dense_fp8_tflops_not_used": h200["peak_math"]["fp8_tflops"],
            "two_to_four_sparse_bf16_tflops_not_used": 2
            * h200["peak_math"]["bf16_tflops"],
            "density_guard": "The inventory's 989.5 BF16 TFLOP/s is the dense Hopper rate. The 2:4 sparse BF16 ceiling is twice that rate and is inadmissible for this dense checkpoint; its numerical equality to the inventory's 1,979 dense FP8 TFLOP/s is coincidental and neither value is used.",
            "interpretation": "Vendor-reported full-chip peak is an impossible-ideal denominator, not achieved or transferable workload throughput.",
        },
        "exact_transformer_linear_algebra": {
            "two_flops_per_dense_multiply_accumulate": True,
            "regimes": regimes,
            "architecture_macs_per_fresh_prompt_token": total_macs_per_token,
            "architecture_flops_per_fresh_prompt_token": total_flops_per_token,
            "fresh_prompt_tokens_per_request": fraction_record(FRESH_TOKENS),
            "prefill_linear_flops_per_request": fraction_record(prefill_linear_flops),
            "prefill_linear_floor_seconds_per_request": fraction_record(prefill_linear_seconds_fraction),
            "batching_guard": {
                "formula_used": "per-request FLOPs / full-H200 FLOP/s",
                "divided_by_concurrency_32": False,
                "reason": "The numerator is already per request; sustainable c32 throughput amortizes one batch across 32 requests, so another /32 would be a second amortization.",
                "incorrect_double_divided_seconds_per_request_not_used": str(
                    prefill_linear_seconds / CONCURRENCY
                ),
            },
        },
        "fresh_query_qk_av_sensitivity": {
            "primary_cache_mix_interpretation": {
                "type": "adjacent_integer_request_mix_exactly_realizing_the_12_7_percent_mean",
                "components": [
                    {"weight": fraction_record(primary_weights[535]), **cache_535},
                    {"weight": fraction_record(primary_weights[536]), **cache_536},
                ],
                "boundary": "The campaign supplies an aggregate cache fraction, not a cache-length distribution. This adjacent-integer realization preserves the exact mean but its causal-global QK/AV total is a labeled sensitivity, not part of the hard primary floor.",
            },
            "pair_formula": {
                "sliding": "sum over fresh query j=1..F of min(1024, cached_prefix_tokens+j)",
                "global": "F*cached_prefix_tokens + F*(F+1)/2",
                "gqa": "All 32 query heads perform QK and AV work; 16 local or 4 global KV heads share K/V storage but do not divide query-head arithmetic.",
                "qk_flops": "2 * query_heads * head_dim * attended_pairs",
                "av_flops": "2 * query_heads * head_dim * attended_pairs",
            },
            "primary": {
                "detail": primary_attention_detail,
                "qk_plus_av_flops_per_request": fraction_record(primary_attention_flops),
                "impossible_ideal_seconds_per_request": fraction_record(primary_attention_seconds_fraction),
            },
            "exact_block_cache_528_of_4214": {
                "counts": block_row,
                "detail": block_attention_detail,
                "linear_flops_per_request": fraction_record(block_linear_flops),
                "linear_impossible_ideal_seconds_per_request": str(block_linear_seconds),
                "qk_plus_av_flops_per_request": fraction_record(block_attention_flops),
                "qk_plus_av_impossible_ideal_seconds_per_request": str(block_attention_seconds),
            },
            "combination_validity": "Linear and QK/AV BF16 MACs all consume the same finite full-chip math capacity; summing compulsory FLOPs before dividing by the optimistic BF16 peak remains a capacity lower bound even with an ideal schedule. The aggregate cache distribution ambiguity keeps this combined value a sensitivity rather than the primary exact floor.",
        },
        "service_comparison": comparisons,
        "double_count_guards": {
            "decode_linears_plus_head_added_exactly_once": True,
            "decode_linears_plus_head_source_value_seconds_per_request": str(DECODE_LINEARS_HEAD_SECONDS),
            "analytical_decode_kv_floor_added": False,
            "analytical_decode_kv_floor_seconds_per_request_excluded": str(kv_floor_seconds),
            "reason": "The project derives prefill work. The separately measured live actual decode-attention consumer is expected to include decode KV reads, so adding the analytical KV-read floor would double count that work at merge time.",
            "merge_formula": "whole-service lower bound = measured decode linears+head + exact prefill-linear floor + actual decode-attention consumer; compare actual decode attention to the emitted residual threshold, leaving all other omissions at zero.",
        },
        "omissions": [
            "prefill softmax and causal masking",
            "RMSNorm, rotary embedding, and activation functions",
            "KV-cache writes, paging, allocation, and memory traffic",
            "embedding lookup and any prefill logits processing not already represented by the 358-step measured head",
            "decode attention; emitted only as a maximum admissible threshold",
            "scheduler, continuous batching inefficiency, queueing, host work, serialization, and networking",
            "endpoint utilization, replica headroom, failures, reloads, storage, orchestration, and quality",
        ],
        "interpretation": {
            "typed_decision": decision,
            "primary": "The exact disjoint prefill-linear plus measured decode-linears/head floor remains below both service ceilings; c32 survives but has only the emitted residual for every omitted component.",
            "attention_sensitivity": "Adding the source-shaped fresh-query QK/AV arithmetic under the same impossible peak still preserves c32, while narrowing the zero-other-overhead actual decode-attention thresholds further.",
            "claim_boundary": "This is an optimistic arithmetic floor, not an endpoint, achieved-throughput, latency, economic, quality, or production-eligibility result.",
        },
        "resources": {
            "provider_queries": 0,
            "provider_mutations": 0,
            "gpu_seconds": 0,
            "spend_usd": 0,
        },
    }
    artifact_path = PROJECT_DIR / "PREFILL_COMPUTE_FLOOR.json"
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"artifact": str(artifact_path), "sha256": sha256(artifact_path), "decision": decision}))


if __name__ == "__main__":
    main()
