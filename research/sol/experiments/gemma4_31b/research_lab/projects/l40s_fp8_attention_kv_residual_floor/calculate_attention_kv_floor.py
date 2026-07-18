#!/usr/bin/env python3

import hashlib
import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
LAB_DIR = PROJECT_DIR.parent.parent
WORKSPACE_DIR = LAB_DIR.parents[4]

GEOMETRY_PATH = LAB_DIR / "projects/exact_geometry_runtime_opportunities/GEOMETRY.json"
KV_CONTRACT_PATH = LAB_DIR / "projects/fp8_kv_contract_reconciliation/KV_CONTRACT.json"
GATE_PATH = LAB_DIR / "projects/l40s_saturation_economic_gate/SATURATION_GATE.json"
MARKET_PATH = LAB_DIR / "projects/exact_market_venue_decision_surface/MARKET_TARGET.json"
INVENTORY_PATH = WORKSPACE_DIR / "research/factory/data/accelerator_inventory.json"
MANIFEST_PATH = PROJECT_DIR / "SOURCE_MANIFEST.json"
OUTPUT_PATH = PROJECT_DIR / "ATTENTION_KV_RESIDUAL_FLOOR.json"

EXPECTED_SHA256 = {
    "geometry": "024450cd944c7827db442d8274e1e0cccae114ee3bbb2e0473704f2fbf0e3a72",
    "kv_contract": "d495553dab98eac4d101802e668469fea3758ba378a8bd89641075a277a07802",
    "saturation_gate": "690e0e457c6e8e9121b54fb7f88abc92c3dcc358e1d71accffddb083878d00d6",
    "market_target": "5d636809dc25450050c565cdc108bf7e91eaa60ce07c027ca390c8011e3b8e51",
    "accelerator_inventory": "bcb33ac6814400f6ab79faa7e44c0ced2d6fe2ac5d19dc43f4ee10b12d7ea6b8",
}

CONCURRENCIES = (12, 14)
OUTPUT_TOKENS = 358
AA_PROMPT_TOKENS = 10_000


def load_json(path: Path):
    return json.loads(path.read_text())


def sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def triangular(value):
    return value * (value + 1) / 2


def prompt_attention(prompt_tokens, cached_prefix_tokens, local_window, local_layers,
                     global_layers, query_heads, local_head_dim, global_head_dim):
    if not 0 <= cached_prefix_tokens <= prompt_tokens:
        raise ValueError("cached prefix must lie inside prompt")
    global_attended_pairs = triangular(prompt_tokens) - triangular(cached_prefix_tokens)
    if cached_prefix_tokens >= local_window:
        local_attended_pairs = (prompt_tokens - cached_prefix_tokens) * local_window
    elif prompt_tokens <= local_window:
        local_attended_pairs = triangular(prompt_tokens) - triangular(cached_prefix_tokens)
    else:
        local_attended_pairs = (
            triangular(local_window)
            - triangular(cached_prefix_tokens)
            + (prompt_tokens - local_window) * local_window
        )
    local_flops = 4 * query_heads * local_head_dim * local_layers * local_attended_pairs
    global_flops = 4 * query_heads * global_head_dim * global_layers * global_attended_pairs
    return {
        "prompt_tokens": prompt_tokens,
        "cached_prefix_tokens": cached_prefix_tokens,
        "fresh_query_tokens": prompt_tokens - cached_prefix_tokens,
        "local_attended_query_key_pairs": local_attended_pairs,
        "global_attended_query_key_pairs": global_attended_pairs,
        "local_qk_av_flops": local_flops,
        "global_qk_av_flops": global_flops,
        "total_qk_av_flops": local_flops + global_flops,
    }


def decode_attention(prompt_tokens, output_tokens, local_window, local_layers,
                     global_layers, query_heads, local_head_dim, global_head_dim,
                     local_value_bytes, local_scale_bytes, global_value_bytes,
                     global_scale_bytes):
    contexts = list(range(prompt_tokens, prompt_tokens + output_tokens))
    local_tokens = [min(context, local_window) for context in contexts]
    global_tokens = contexts

    local_value_read_bytes = sum(
        local_layers * tokens * local_value_bytes for tokens in local_tokens
    )
    local_scale_read_bytes = sum(
        local_layers * tokens * local_scale_bytes for tokens in local_tokens
    )
    global_value_read_bytes = sum(
        global_layers * tokens * global_value_bytes for tokens in global_tokens
    )
    global_scale_read_bytes = sum(
        global_layers * tokens * global_scale_bytes for tokens in global_tokens
    )
    bytes_by_step = [
        local_layers * local_tokens[index] * (local_value_bytes + local_scale_bytes)
        + global_layers * global_tokens[index] * (global_value_bytes + global_scale_bytes)
        for index in range(output_tokens)
    ]

    local_pairs = sum(local_tokens)
    global_pairs = sum(global_tokens)
    local_flops = 4 * query_heads * local_head_dim * local_layers * local_pairs
    global_flops = 4 * query_heads * global_head_dim * global_layers * global_pairs
    return {
        "context_convention": "cached context before each generated query; positions prompt_tokens through prompt_tokens+output_tokens-1",
        "contexts_inclusive": [contexts[0], contexts[-1]],
        "sum_local_tokens_per_layer": sum(local_tokens),
        "sum_global_tokens_per_layer": sum(global_tokens),
        "local_value_read_bytes": local_value_read_bytes,
        "local_scale_read_bytes": local_scale_read_bytes,
        "global_value_read_bytes": global_value_read_bytes,
        "global_scale_read_bytes": global_scale_read_bytes,
        "value_read_bytes": local_value_read_bytes + global_value_read_bytes,
        "scale_read_bytes": local_scale_read_bytes + global_scale_read_bytes,
        "total_read_bytes": sum(bytes_by_step),
        "bytes_by_step": bytes_by_step,
        "local_qk_av_flops": local_flops,
        "global_qk_av_flops": global_flops,
        "total_qk_av_flops": local_flops + global_flops,
    }


def service_ceilings(gate):
    result = {}
    for scenario in ("planning_base", "conservative"):
        result[scenario] = {}
        for target, row in gate["economic_surface"][scenario].items():
            rps = row["required_completed_requests_per_second"]["planning"]
            result[scenario][target] = {
                "required_completed_requests_per_second": rps,
                "whole_service_ceiling_seconds_per_request": 1 / rps,
            }
    return result


def make_operating_point(label, concurrency, prompt, decode, chip, ceilings):
    bandwidth_bytes_s = chip["memory"]["bandwidth_gb_s"] * 1_000_000_000
    l2_bytes = chip["cache"]["last_level_mb"] * 1_000_000
    fp8_flops_s = chip["peak_math"]["fp8_tflops"] * 1_000_000_000_000
    bf16_flops_s = chip["peak_math"]["bf16_tflops"] * 1_000_000_000_000
    raw_bytes = decode["total_read_bytes"]
    per_request_per_step_credit_bytes = sum(
        min(step_bytes, l2_bytes) for step_bytes in decode["bytes_by_step"]
    )
    shared_batch_per_step_credit_bytes = sum(
        min(concurrency * step_bytes, l2_bytes) for step_bytes in decode["bytes_by_step"]
    ) / concurrency

    bandwidth_floors = {
        "zero_l2_credit_seconds_per_request": raw_bytes / bandwidth_bytes_s,
        "literal_one_full_l2_credit_over_entire_request_seconds": max(0, raw_bytes - l2_bytes) / bandwidth_bytes_s,
        "impossible_ideal_full_l2_credit_per_request_each_decode_step_seconds": (
            raw_bytes - per_request_per_step_credit_bytes
        ) / bandwidth_bytes_s,
        "physical_shared_l2_credit_once_per_batch_decode_step_seconds": (
            raw_bytes - shared_batch_per_step_credit_bytes
        ) / bandwidth_bytes_s,
        "full_l2_credit_bytes_once_over_entire_request": min(raw_bytes, l2_bytes),
        "full_l2_credit_bytes_per_request_over_all_decode_steps": per_request_per_step_credit_bytes,
        "shared_l2_credit_bytes_per_request_over_all_decode_steps": shared_batch_per_step_credit_bytes,
    }
    prompt_fp8_seconds = prompt["total_qk_av_flops"] / fp8_flops_s
    decode_fp8_seconds = decode["total_qk_av_flops"] / fp8_flops_s
    total_fp8_seconds = prompt_fp8_seconds + decode_fp8_seconds
    arithmetic = {
        "fp8_peak_supported_absolute_optimistic": {
            "prompt_seconds_per_request": prompt_fp8_seconds,
            "decode_seconds_per_request": decode_fp8_seconds,
            "total_seconds_per_request": total_fp8_seconds,
        },
        "bf16_peak_format_sensitivity": {
            "prompt_seconds_per_request": prompt["total_qk_av_flops"] / bf16_flops_s,
            "decode_seconds_per_request": decode["total_qk_av_flops"] / bf16_flops_s,
            "total_seconds_per_request": (
                prompt["total_qk_av_flops"] + decode["total_qk_av_flops"]
            ) / bf16_flops_s,
        },
    }

    shared_bw = bandwidth_floors["physical_shared_l2_credit_once_per_batch_decode_step_seconds"]
    impossible_bw = bandwidth_floors["impossible_ideal_full_l2_credit_per_request_each_decode_step_seconds"]
    literal_bw = bandwidth_floors["literal_one_full_l2_credit_over_entire_request_seconds"]
    overlap_floor = max(total_fp8_seconds, literal_bw)
    shared_step_overlap_sensitivity = max(total_fp8_seconds, shared_bw)
    impossible_overlap_floor = max(total_fp8_seconds, impossible_bw)
    serialized_sensitivity = prompt_fp8_seconds + max(decode_fp8_seconds, shared_bw)
    sum_sensitivity = total_fp8_seconds + shared_bw
    literal_sensitivity = max(total_fp8_seconds, literal_bw)

    component_thresholds = {}
    for scenario in ("planning_base", "conservative"):
        component_thresholds[scenario] = {}
        for target, ceiling in ceilings[scenario].items():
            service_seconds = ceiling["whole_service_ceiling_seconds_per_request"]
            component_thresholds[scenario][target] = {
                "whole_service_ceiling_seconds_per_request": service_seconds,
                "maximum_component_total_under_prescribed_single_l2_credit_roofline_seconds_per_request": max(
                    0.0, service_seconds - overlap_floor
                ),
                "maximum_component_total_under_shared_l2_each_step_sensitivity_seconds_per_request": max(
                    0.0, service_seconds - shared_step_overlap_sensitivity
                ),
                "maximum_component_total_under_impossible_ideal_l2_roofline_seconds_per_request": max(
                    0.0, service_seconds - impossible_overlap_floor
                ),
                "maximum_component_total_under_literal_single_credit_sensitivity_seconds_per_request": max(
                    0.0, service_seconds - literal_sensitivity
                ),
                "residual_alone_closes": overlap_floor > service_seconds,
            }

    return {
        "label": label,
        "concurrency": concurrency,
        "concurrency_normalization": {
            "raw_batch_bytes": concurrency * raw_bytes,
            "raw_bytes_per_request_after_dividing_batch_once": raw_bytes,
            "raw_per_request_bytes_change_with_concurrency": False,
            "rule": "batch bytes and batch device time scale by c; divide by c exactly once to recover seconds/request; never divide the already normalized result by c again",
        },
        "prompt_attention": prompt,
        "decode_attention": {key: value for key, value in decode.items() if key != "bytes_by_step"},
        "bandwidth_floors": bandwidth_floors,
        "arithmetic_floors": arithmetic,
        "resource_overlap": {
            "prescribed_attention_roofline_seconds_per_request": overlap_floor,
            "shared_l2_each_step_roofline_sensitivity_seconds_per_request": shared_step_overlap_sensitivity,
            "impossible_ideal_per_request_l2_roofline_seconds_per_request": impossible_overlap_floor,
            "literal_single_credit_sensitivity_seconds_per_request": literal_sensitivity,
            "serialized_prompt_then_decode_sensitivity_seconds_per_request": serialized_sensitivity,
            "arithmetic_plus_bandwidth_sum_sensitivity_seconds_per_request": sum_sensitivity,
            "primary_rule": "max(total prompt+decode QK/AV time at absolute FP8 peak, decode KV time after one full 96 MB L2 credit over the request), exactly as preregistered",
            "why_not_sum": "QK/AV tensor-core arithmetic and KV memory service may overlap inside attention kernels and across continuously batched requests; their lower bounds cannot be added without an observed no-overlap schedule",
            "why_component_merge_is_additive": "the measured component contract covers separate linear/head/KV-writer kernels in the layer DAG; merge only after its result is normalized to seconds/request and confirms attention is excluded",
        },
        "maximum_admissible_component_totals": component_thresholds,
    }


def main():
    paths = {
        "geometry": GEOMETRY_PATH,
        "kv_contract": KV_CONTRACT_PATH,
        "saturation_gate": GATE_PATH,
        "market_target": MARKET_PATH,
        "accelerator_inventory": INVENTORY_PATH,
    }
    actual_hashes = {name: sha256(path) for name, path in paths.items()}
    if actual_hashes != EXPECTED_SHA256:
        raise RuntimeError(f"source identity mismatch: {actual_hashes}")

    geometry = load_json(GEOMETRY_PATH)
    contract = load_json(KV_CONTRACT_PATH)
    gate = load_json(GATE_PATH)
    market = load_json(MARKET_PATH)
    inventory = load_json(INVENTORY_PATH)
    l40s = next(item for item in inventory["accelerators"] if item["id"] == "nvidia-l40s")
    target = geometry["identities"]["target_model"]
    text = geometry["target_text_geometry_measured_from_config"]
    source_contract = contract["source_contract"]
    mix = market["campaign_mix"]

    assertions = {
        "model": (
            target["id"].lower()
            == market["model"].lower()
            == contract["identities"]["model"].lower()
        ),
        "revision": target["revision"] == market["model_revision"] == contract["identities"]["model_revision"],
        "layers": text["attention_pattern"] == {
            "sliding_attention_layers": 50,
            "full_attention_layers": 10,
            "pattern": "five sliding then one full, repeated",
        },
        "heads_dims": (
            text["num_attention_heads"] == 32
            and text["num_key_value_heads_sliding"] == 16
            and text["head_dim_sliding"] == 256
            and text["num_global_key_value_heads"] == 4
            and text["global_head_dim"] == 512
        ),
        "window": text["sliding_window_tokens"] == 1024,
        "workload": (
            mix["prompt_tokens"] == 4214
            and mix["output_tokens"] == OUTPUT_TOKENS
            and mix["prompt_cache_fraction"] == 0.127
            and mix["cache_prompt_tokens"] == 535.178
            and mix["fresh_prompt_tokens"] == 3678.822
        ),
        "fp8_payload_and_scales": (
            source_contract["local_layer_bytes_per_resident_token"] == 4224
            and source_contract["global_layer_bytes_per_resident_token"] == 4128
            and "one native Ada FP8 E4M3 byte" in source_contract["value_storage"]
            and "FP32 (4-byte) scale" in source_contract["scale_storage"]
        ),
        "l40s": (
            l40s["memory"]["bandwidth_gb_s"] == 864
            and l40s["cache"]["last_level_mb"] == 96
            and l40s["peak_math"]["bf16_tflops"] == 362.05
            and l40s["peak_math"]["fp8_tflops"] == 733
            and "fp8" in l40s["numeric_formats"]
        ),
        "gate_market_identity": gate["inputs"]["market"]["sha256"] == actual_hashes["market_target"],
    }
    if not all(assertions.values()):
        raise RuntimeError(f"semantic identity assertion failed: {assertions}")

    manifest = {
        "schema_version": 1,
        "source_snapshot_at_utc": market["captured_at_utc"],
        "sources": {
            name: {"path": str(path), "sha256": actual_hashes[name]}
            for name, path in paths.items()
        },
        "semantic_identity_assertions": assertions,
        "selected_l40s_inventory": l40s,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    common = {
        "local_window": text["sliding_window_tokens"],
        "local_layers": text["attention_pattern"]["sliding_attention_layers"],
        "global_layers": text["attention_pattern"]["full_attention_layers"],
        "query_heads": text["num_attention_heads"],
        "local_head_dim": text["head_dim_sliding"],
        "global_head_dim": text["global_head_dim"],
    }
    cache_sensitivities = {}
    for prefix in (0, 528, mix["cache_prompt_tokens"], 1024):
        row = prompt_attention(mix["prompt_tokens"], prefix, **common)
        cache_sensitivities[str(prefix)] = row

    primary_prompt = cache_sensitivities[str(mix["cache_prompt_tokens"])]
    primary_decode = decode_attention(
        mix["prompt_tokens"], OUTPUT_TOKENS,
        local_value_bytes=4096, local_scale_bytes=128,
        global_value_bytes=4096, global_scale_bytes=32,
        **common,
    )
    aa_prompt = prompt_attention(AA_PROMPT_TOKENS, 0, **common)
    aa_decode = decode_attention(
        AA_PROMPT_TOKENS, OUTPUT_TOKENS,
        local_value_bytes=4096, local_scale_bytes=128,
        global_value_bytes=4096, global_scale_bytes=32,
        **common,
    )
    ceilings = service_ceilings(gate)
    operating_points = [
        make_operating_point("campaign_4214_358", concurrency, primary_prompt, primary_decode, l40s, ceilings)
        for concurrency in CONCURRENCIES
    ]
    aa_point = make_operating_point("aa_10k_358_single_stream_sensitivity", 1, aa_prompt, aa_decode, l40s, ceilings)

    strict_target = "DeepInfra_fp8"
    primary_thresholds = {}
    for point in operating_points:
        primary_thresholds[f"c{point['concurrency']}"] = {
            "residual_floor_seconds_per_request": point["resource_overlap"]["prescribed_attention_roofline_seconds_per_request"],
            "planning_service_ceiling_seconds_per_request": ceilings["planning_base"][strict_target]["whole_service_ceiling_seconds_per_request"],
            "planning_maximum_component_total_seconds_per_request": point["maximum_admissible_component_totals"]["planning_base"][strict_target]["maximum_component_total_under_prescribed_single_l2_credit_roofline_seconds_per_request"],
            "conservative_service_ceiling_seconds_per_request": ceilings["conservative"][strict_target]["whole_service_ceiling_seconds_per_request"],
            "conservative_maximum_component_total_seconds_per_request": point["maximum_admissible_component_totals"]["conservative"][strict_target]["maximum_component_total_under_prescribed_single_l2_credit_roofline_seconds_per_request"],
        }

    artifact = {
        "schema_version": 1,
        "source_snapshot_at_utc": market["captured_at_utc"],
        "status": "complete",
        "result_type": "residual_threshold_bound",
        "evidence_type": "source_bound_deterministic_analytical_lower_bound",
        "scope": "$0 L40S attention/KV arithmetic and bandwidth bounds only; no GPU, endpoint, achieved kernel efficiency, quality, or paid-owner evidence",
        "source_manifest": {"path": str(MANIFEST_PATH), "sha256": sha256(MANIFEST_PATH)},
        "identities": {
            "model": target["id"],
            "revision": target["revision"],
            "workload": mix,
            "aa_sensitivity": {"prompt_tokens": AA_PROMPT_TOKENS, "output_tokens": OUTPUT_TOKENS, "concurrency": 1, "cache_prefix_tokens": 0},
            "geometry": {
                "local_layers": common["local_layers"],
                "global_layers": common["global_layers"],
                "local_window": common["local_window"],
                "query_heads": common["query_heads"],
                "local_kv_heads": text["num_key_value_heads_sliding"],
                "global_kv_heads": text["num_global_key_value_heads"],
                "local_head_dim": common["local_head_dim"],
                "global_head_dim": common["global_head_dim"],
            },
            "fp8_kv": {
                "local_value_bytes_per_token_layer": 4096,
                "local_scale_bytes_per_token_layer": 128,
                "global_value_bytes_per_token_layer": 4096,
                "global_scale_bytes_per_token_layer": 32,
                "scale_layout": source_contract["scale_storage"],
            },
            "l40s": {
                "bandwidth_gb_s_decimal": l40s["memory"]["bandwidth_gb_s"],
                "l2_mb_decimal": l40s["cache"]["last_level_mb"],
                "bf16_peak_tflops": l40s["peak_math"]["bf16_tflops"],
                "fp8_peak_tflops": l40s["peak_math"]["fp8_tflops"],
                "compute_units": l40s["execution"]["compute_units"],
                "numeric_formats": l40s["numeric_formats"],
            },
        },
        "formulas": {
            "decode_context": "prompt_tokens + decode_index for decode_index in [0,357]",
            "decode_kv_bytes_step": "50*min(context,1024)*(4096+128) + 10*context*(4096+32)",
            "qk_av_flops": "4 * query_heads * head_dim * attended_query_key_pairs (2 FLOPs/MAC for QK plus 2 FLOPs/MAC for AV)",
            "prompt_global_pairs": "T(prompt_tokens)-T(cached_prefix_tokens), T(n)=n*(n+1)/2",
            "prompt_local_pairs": "sum over fresh query positions of min(position,1024)",
            "shared_l2_floor": "sum_steps(max(0,c*bytes_step-96e6))/(864e9*c)",
            "roofline_residual": "max(total_QK_AV_flops/733e12, max(0,total_decode_KV_bytes-96e6)/864e9)",
            "component_merge": "combined_floor_s_per_request = measured_component_s_per_request + residual_floor_s_per_request; measured component must already include 358 architecture weighting, divide by c once, and exclude attention",
            "pass_rule": "combined_floor <= selected whole-service ceiling; equivalently measured_component <= maximum_admissible_component_total",
        },
        "service_ceilings": ceilings,
        "cache_prefix_arithmetic_sensitivities": cache_sensitivities,
        "operating_points": operating_points,
        "aa_10k_sensitivity": aa_point,
        "decision": {
            "classification": "residual_threshold_bound",
            "strict_target": strict_target,
            "primary_thresholds": primary_thresholds,
            "component_floor_already_closes": any(
                row["residual_floor_seconds_per_request"] > row["conservative_service_ceiling_seconds_per_request"]
                for row in primary_thresholds.values()
            ),
            "interpretation": "Attention/KV alone does not close c12 or c14. Merge the independent actual-consumer component only after its typed result confirms identical identities, seconds/request normalization, and attention exclusion.",
            "kernel_format_boundary": "FP8 is a supported L40S peak, but stock FP8-KV attention may dequantize Q/K/V and softmax is not an FP8 tensor-core operation. The 733-TFLOP/s conversion is an absolute optimistic arithmetic denominator, not an achieved-kernel claim; BF16 peak is reported only as sensitivity.",
            "l2_boundary": "The primary row follows the preregistered rule and credits the full 96 MB L2 once over each request. Shared-L2-per-batch-step and impossible per-request-L2-per-step rows are reported as persistent-reuse sensitivities; if persistent inter-step reuse occurs, the prescribed primary is conditional rather than an unconditional HBM floor.",
            "omissions": [
                "softmax, masks and reductions",
                "RMSNorm, rotary embedding and activation kernels",
                "sampling/argmax and vocabulary-side auxiliaries not in the measured component",
                "scheduler, queueing, request serialization and API overhead",
                "paging fragmentation, allocator effects and achieved bandwidth",
                "replica headroom, failures, reloads, storage and orchestration",
                "prompt KV data movement outside the isolated QK/AV arithmetic floor",
            ],
            "evidence_boundary": "This artifact is a capacity lower bound and merge threshold. It is not endpoint throughput, latency, kernel support, achieved utilization, sustainable economics, or quality evidence.",
        },
    }
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(json.dumps(artifact["decision"]["primary_thresholds"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
