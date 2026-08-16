#!/usr/bin/env python3
"""Full draft-plus-verify analytical discriminator for the c32 workload."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

from causal_parallel_offset_head import HeadConfig, service_bytes, service_flops


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def depth_row(cost: dict, depth: int) -> dict:
    return next(row for row in cost["depths"] if row["depth"] == depth)


def projected_service(
    accepted_target_tokens: float,
    *,
    baseline: float,
    current_accept: float,
    gpu_sensitive_fraction: float,
    verifier_cost_ratio: float,
    head_ms_per_call: float,
    calls_in_trace: int,
    trace_window_ms: float,
) -> float:
    call_ratio = current_accept / accepted_target_tokens
    target_fraction = (
        gpu_sensitive_fraction * verifier_cost_ratio * call_ratio
    )
    draft_fraction = (
        head_ms_per_call * calls_in_trace / trace_window_ms * call_ratio
    )
    fixed_fraction = 1.0 - gpu_sensitive_fraction
    return baseline * (fixed_fraction + target_fraction + draft_fraction)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dflash-cost", required=True, type=pathlib.Path)
    parser.add_argument("--grouped-head", required=True, type=pathlib.Path)
    parser.add_argument("--control-stage", required=True, type=pathlib.Path)
    parser.add_argument("--trace-analysis", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    expected = {
        "dflash_cost": "c2cdc9bedbe4de8120ef9641ec7c9d745657e21352c3d388291ef5020ecdf637",
        "grouped_head": "d6ce199adc0debcc5e10380e71b219009858c160efc60be56c81d571f240bda1",
        "control_stage": "de7512df1428a77810902df196c228df9328f33ecdb5ffcdef72b754365d641d",
        "trace_analysis": "a22e25b3e911891d75e1008f22a03ad2a7d160584e1c83e660b8a3238602304f",
    }
    observed = {
        "dflash_cost": sha256(args.dflash_cost),
        "grouped_head": sha256(args.grouped_head),
        "control_stage": sha256(args.control_stage),
        "trace_analysis": sha256(args.trace_analysis),
    }
    if observed != expected:
        raise RuntimeError(f"input_hash_mismatch:{observed}")
    dflash = json.loads(args.dflash_cost.read_text())
    grouped = json.loads(args.grouped_head.read_text())
    control = json.loads(args.control_stage.read_text())
    trace = json.loads(args.trace_analysis.read_text())
    d12 = depth_row(dflash, 12)
    d16 = depth_row(dflash, 16)
    frontier_accept = {
        12: 3.2593437945791726,
        16: 3.3452415812591507,
    }
    verifier_per_request_verification_ms = {
        depth: row["robust_summary"]["verifier"]["sum_ms"]
        * frontier_accept[depth]
        / 11424
        for depth, row in ((12, d12), (16, d16))
    }
    verifier_cost_ratio = (
        verifier_per_request_verification_ms[16]
        / verifier_per_request_verification_ms[12]
    )
    depth16_mean_prefix = frontier_accept[16] - 1
    lower, upper = 0.0, 1.0
    for _ in range(80):
        probability = (lower + upper) / 2
        expected_prefix = sum(
            probability**offset for offset in range(1, 17)
        )
        if expected_prefix < depth16_mean_prefix:
            lower = probability
        else:
            upper = probability
    measured_survival_probability = (lower + upper) / 2
    raw_offset_weights = [
        measured_survival_probability**offset
        * verifier_per_request_verification_ms[16]
        for offset in range(16)
    ]
    weight_sum = sum(raw_offset_weights)
    current_accept = control["telemetry"]["sglang:spec_accept_length"]["delta"]
    grouped_d12_ms = grouped["timing_ms"]["candidate_median"]
    grouped_d16_ms = grouped_d12_ms * 16 / 12
    causal_block_allowance_ms = 0.5
    head_ms_per_call = grouped_d16_ms + causal_block_allowance_ms
    gpu_sensitive_fraction = trace["gpu"]["interval_union_fraction_of_window"]
    calls_in_trace = trace["semantic_ranges"]["ngram.target_forward_verify"]["calls"]
    trace_window_ms = trace["window_us"] / 1000
    baseline = 0.625149101968745
    target = 0.500119281574996
    sensitivity = []
    for accepted in (12.0, 14.0, 15.0, 16.0, 16.05, 16.06, 16.5, 17.0):
        service = projected_service(
            accepted,
            baseline=baseline,
            current_accept=current_accept,
            gpu_sensitive_fraction=gpu_sensitive_fraction,
            verifier_cost_ratio=verifier_cost_ratio,
            head_ms_per_call=head_ms_per_call,
            calls_in_trace=calls_in_trace,
            trace_window_ms=trace_window_ms,
        )
        sensitivity.append(
            {
                "mean_accepted_target_tokens": accepted,
                "mean_accepted_draft_tokens": accepted - 1,
                "projected_seconds_per_request": service,
                "meets_target": service <= target,
            }
        )
    threshold = None
    for integer in range(10000, 17001):
        accepted = integer / 1000
        service = projected_service(
            accepted,
            baseline=baseline,
            current_accept=current_accept,
            gpu_sensitive_fraction=gpu_sensitive_fraction,
            verifier_cost_ratio=verifier_cost_ratio,
            head_ms_per_call=head_ms_per_call,
            calls_in_trace=calls_in_trace,
            trace_window_ms=trace_window_ms,
        )
        if service <= target:
            threshold = {
                "mean_accepted_target_tokens": accepted,
                "mean_accepted_draft_tokens": accepted - 1,
                "draft_prefix_fraction_of_maximum": (accepted - 1) / 16,
                "projected_seconds_per_request": service,
            }
            break
    config = HeadConfig()
    result = {
        "schema_version": 1,
        "classification": "full_draft_plus_verify_cost_discriminator",
        "inputs": observed,
        "production_geometry": {
            "batch": 32,
            "depth": 16,
            "tap_layers": list(config.tap_layers),
            "tap_shape_each": [32, 5376],
            "offset_hidden": [32, 16, 5376],
            "tied_weight": [262144, 5376],
            "tied_weight_dtype": "BF16",
            "consumer_output": [512, 262144],
            "consumer_output_dtype": "FP32",
            "row_order": "request_major_offset_minor",
        },
        "complete_head_accounting": {
            "flops": service_flops(config, 32),
            "bytes": service_bytes(config, 32),
            "launches": {
                "tap_rmsnorm": 1,
                "tap_down_projections": 3,
                "qkv": 1,
                "causal_sdpa": 1,
                "attention_out": 1,
                "mlp_norm": 1,
                "mlp_up_activation": 1,
                "mlp_down": 1,
                "hidden_up_residual": 1,
                "batched_tied_head": 1,
                "top1_reduction": 1,
                "total_unfused_upper_bound": 13,
            },
            "measured_grouped_d12_ms": grouped_d12_ms,
            "derived_grouped_d16_ms": grouped_d16_ms,
            "causal_block_and_launch_allowance_ms": causal_block_allowance_ms,
            "head_ms_per_verification_call": head_ms_per_call,
        },
        "verifier": {
            "measured_d12_per_request_verification_ms": verifier_per_request_verification_ms[
                12
            ],
            "measured_d16_per_request_verification_ms": verifier_per_request_verification_ms[
                16
            ],
            "d16_over_d12_cost_ratio": verifier_cost_ratio,
            "acceptance_and_bonus_boundary": (
                "NgramVerifyInput.num_accept_tokens = num_correct_drafts + 1; "
                "accepted cache rows are compacted before seq_lens and "
                "seq_lens_sum advance"
            ),
        },
        "training_offset_weights": {
            "derivation": (
                "Geometric prefix survival fitted to the measured DFlash "
                "depth-16 mean accepted draft prefix, multiplied by the "
                "measured depth-16 verifier cost per request-verification."
            ),
            "measured_depth16_mean_accepted_draft_tokens": depth16_mean_prefix,
            "fitted_conditional_token_match_probability": measured_survival_probability,
            "normalized_offsets_1_through_16": [
                value / weight_sum for value in raw_offset_weights
            ],
        },
        "service_model": {
            "qualified_baseline_seconds_per_request": baseline,
            "target_seconds_per_request": target,
            "same_distribution_current_accepted_target_tokens": current_accept,
            "trace_gpu_interval_union_fraction": gpu_sensitive_fraction,
            "trace_target_forward_calls": calls_in_trace,
            "trace_window_ms": trace_window_ms,
            "optimism": [
                "every GPU-union interval is treated as verification-sensitive",
                "verification calls scale inversely with mean accepted target tokens",
                "no loss is charged for c32 tail effects, lower live batch, or depth-16 padding",
                "the measured depth-12 grouped head scales only linearly to depth 16",
            ],
            "threshold": threshold,
            "sensitivity": sensitivity,
        },
        "decision": {
            "ready_path_exists_analytically": threshold is not None,
            "holdout_evidence_present": False,
            "ready": False,
            "reason": (
                "The optimistic cost path exists only at near-perfect prefix "
                "survival, but no request-disjoint target-layer-tap holdout or "
                "trained checkpoint exists."
            ),
        },
        "evidence_labels": {
            "grouped_head_timing": "measured H200 CUDA graph replay",
            "dflash_verifier_cost": "measured H200 CUDA events",
            "trace_fraction": "measured non-overlapping GPU interval union",
            "depth16_projection": "derived linear extrapolation from exact D12",
            "service_projection": "analytical optimistic lower-bound model",
        },
    }
    atomic(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
