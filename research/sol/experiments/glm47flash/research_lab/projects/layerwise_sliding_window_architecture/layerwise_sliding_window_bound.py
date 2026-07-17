#!/usr/bin/env python3
"""Derive exact context-work and KV residency bounds for admitted policies."""

from __future__ import annotations

import json
from pathlib import Path


LAYERS = 47
PROMPT = 8192
OUTPUT = 1024
FINAL_CONTEXT = PROMPT + OUTPUT
KV_BYTES_PER_TOKEN_MODEL = 54144
KV_BYTES_PER_TOKEN_PER_LAYER = KV_BYTES_PER_TOKEN_MODEL // LAYERS
TRANSFER = 0.0105 / 0.1435
GATE_REDUCTION = 0.09955144882554656


def periodic(step: int) -> list[int]:
    return list(range(0, LAYERS, step))


def sums(window: int, globals_: list[int]) -> dict[str, float | int]:
    full = sum(range(PROMPT + 1, FINAL_CONTEXT + 1))
    local = sum(min(window, position + 1) for position in range(PROMPT, FINAL_CONTEXT))
    g = len(globals_)
    stock = LAYERS * full
    policy = g * full + (LAYERS - g) * local
    reduction = 1.0 - policy / stock
    endpoint_bound = TRANSFER * reduction
    endpoint_speed = 1.0 / (1.0 - endpoint_bound)
    stock_kv = LAYERS * FINAL_CONTEXT * KV_BYTES_PER_TOKEN_PER_LAYER
    policy_kv = (g * FINAL_CONTEXT + (LAYERS - g) * window) * KV_BYTES_PER_TOKEN_PER_LAYER
    return {
        "window": window,
        "global_layer_count": g,
        "global_layers_zero_based": globals_,
        "full_context_work_token_positions": full,
        "local_context_work_token_positions": local,
        "stock_total_context_work": stock,
        "policy_total_context_work": policy,
        "attention_work_reduction": reduction,
        "conservative_endpoint_reduction_bound": endpoint_bound,
        "conservative_endpoint_speedup_bound": endpoint_speed,
        "stock_endpoint_kv_gib": stock_kv / 2**30,
        "policy_endpoint_kv_gib": policy_kv / 2**30,
        "endpoint_bound_clears_wall_reduction_gate": endpoint_bound >= GATE_REDUCTION,
    }


def main() -> None:
    rows = [sums(window, periodic(step)) for window in (1024, 2048, 4096) for step in (4, 8)]
    artifact = {
        "schema_version": 1,
        "status": "closed_no_paid_arm",
        "question": "Can periodic global MLA layers plus bounded local attention clear the exact 8K/1K L40S gate?",
        "workload": {"layers": LAYERS, "prompt_tokens": PROMPT, "decode_tokens": OUTPUT,
                     "decode_positions": [PROMPT, FINAL_CONTEXT - 1]},
        "model_geometry": {"kv_rank": 512, "rope_dimensions": 64,
                           "kv_bytes_per_token_model": KV_BYTES_PER_TOKEN_MODEL,
                           "kv_bytes_per_token_per_layer": KV_BYTES_PER_TOKEN_PER_LAYER},
        "economic_gate": {"baseline_output_tok_s": 535.2861037029285,
                          "promotion_output_tok_s": 594.466,
                          "required_nonoverlapped_wall_reduction": GATE_REDUCTION},
        "transfer_calibration": {
            "component_reduction": 0.1435,
            "endpoint_reduction": 0.0105,
            "endpoint_transfer_factor": TRANSFER,
            "evidence": "retained exact-shape MLA split A/B; calibrated proxy, not wall-time Amdahl share",
        },
        "policies": rows,
        "runtime_support_boundary": {
            "pinned_runtime": "vLLM 0.15.0 extracted v24r2",
            "observed_cache_metric": "sliding_window=None",
            "observed_server_config": "enable_prefix_caching=False; GLM MLA uses unified_mla_attention",
            "per_layer_window_support": False,
            "interpretation": "The stock runtime exposes no source-bound per-layer GLM window policy in the retained artifact; implementing one requires a bounded MLA mask/KV-state change, not a launcher flag.",
        },
        "fixture": {
            "path": "source_bound_window_fixture.py",
            "command": "python3 source_bound_window_fixture.py --json",
            "checks": ["global layer sees positions 0..9215", "local layer sees 8192..9215 for W=1024", "local KV state remains 1024 tokens", "stock mode unchanged"],
        },
        "decision": "CLOSE_SLIDING_WINDOW_NO_GPU",
        "decision_reason": "Even an all-local limit cannot exceed the retained 7.32% endpoint-transfer envelope, below the 9.96% wall-time gate; every screened periodic policy is weaker. Runtime support is also absent, so no bounded exact-shape proxy is nominated.",
        "evidence_labels": ["measured retained trace", "derived exact context accounting", "derived conservative transfer bound", "runtime artifact observation", "executable source-bound fixture"],
    }
    out = Path(__file__).with_name("layerwise_sliding_window_bound.json")
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(out)


if __name__ == "__main__":
    main()
