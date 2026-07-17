#!/usr/bin/env python3
"""CPU-only policy fixture and bound for confidence-adaptive GLM MoE routing."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_topk(scores: list[float], count: int) -> list[dict[str, float | int]]:
    ranked = sorted(enumerate(scores), key=lambda pair: pair[1], reverse=True)[:count]
    total = sum(score for _, score in ranked)
    if total <= 0:
        raise ValueError("selected routing scores must have positive sum")
    return [
        {"expert": expert, "weight": score / total}
        for expert, score in ranked
    ]


def policy_decision(scores: list[float], confidence_threshold: float) -> dict[str, object]:
    if len(scores) != 64:
        raise ValueError("this fixture is bound to 64 routed experts")
    ranked = sorted(scores, reverse=True)
    confidence = (ranked[0] - ranked[4]) / ranked[0] if ranked[0] > 0 else 0.0
    qualified = confidence >= confidence_threshold
    return {
        "confidence": confidence,
        "qualified": qualified,
        "stock_top4_shared": {"routed": normalized_topk(scores, 4), "shared": True},
        "top2_shared": {"routed": normalized_topk(scores, 2), "shared": True},
        "top2_no_shared": {"routed": normalized_topk(scores, 2), "shared": False},
        "selected_path": "top2_no_shared" if qualified else "stock_top4_shared",
    }


def wilson_lower_all_successes(samples: int, z: float = 1.959963984540054) -> float:
    z2 = z * z
    return samples / (samples + z2)


def minimum_all_successes_for_lower_bound(threshold: float) -> int:
    samples = 1
    while wilson_lower_all_successes(samples) < threshold:
        samples += 1
    return samples


def minimum_zero_successes_for_upper_bound(threshold: float, alpha: float = 0.05) -> int:
    return math.ceil(math.log(alpha) / math.log(1.0 - threshold))


def build(config: Path, proxy: Path, output: Path) -> dict[str, object]:
    project_root = Path(__file__).resolve().parent
    glm_root = project_root.parents[2]
    observer = glm_root / "campaign_100/nebius/vllm_observer_patch.py"
    runtime_contract = (
        project_root.parent
        / "adaptive_moe_architecture/artifacts/MOE_RUNTIME_AND_LAUNCH_CONTRACT_2026-07-15.json"
    )
    model = json.loads(config.read_text())
    prior = json.loads(proxy.read_text())
    ceiling = prior["results"]["top2_plus_no_shared_ceiling"]["trace_resident_time_fraction"]
    gate = prior["economic_gate"]["required_nonoverlapped_wall_time_reduction"]
    baseline = prior["inputs"]["c16_measurement"]["output_tokens_per_second"]
    overheads = [0.0, 0.0025, 0.005, 0.01, 0.02, 0.03, ceiling - gate]
    curve = []
    for overhead in overheads:
        required_fraction = (gate + overhead) / ceiling
        curve.append({
            "overhead_fraction_of_baseline_wall_time": overhead,
            "minimum_qualified_token_layer_fraction": required_fraction,
            "feasible": required_fraction <= 1.0,
            "minimum_all_qualified_samples_for_95pct_wilson_lower_bound": (
                minimum_all_successes_for_lower_bound(required_fraction)
                if required_fraction < 1.0 else None
            ),
            "minimum_zero_qualified_samples_for_95pct_clopper_pearson_rejection": (
                minimum_zero_successes_for_upper_bound(required_fraction)
                if required_fraction < 1.0 else None
            ),
        })
    fixture_scores = [64.0 - float(index) for index in range(64)]
    evidence = {
        "schema_version": 1,
        "evidence_label": "derived_zero_cost_source_bound_policy_and_absence_audit",
        "inputs": {
            "policy_fixture": {"path": str(Path(__file__).resolve()), "sha256": digest(Path(__file__))},
            "config": {"path": str(config), "sha256": digest(config)},
            "combined_proxy": {"path": str(proxy), "sha256": digest(proxy)},
            "existing_observer_patch": {"path": str(observer), "sha256": digest(observer)},
            "runtime_contract": {"path": str(runtime_contract), "sha256": digest(runtime_contract)},
            "architecture": {
                "moe_layers": sum(layer == "sparse" for layer in model["mlp_layer_types"]),
                "routed_experts": model["n_routed_experts"],
                "stock_routed_experts_per_token": model["num_experts_per_tok"],
                "shared_experts": model["n_shared_experts"],
                "normalizes_topk_probability": model["norm_topk_prob"],
                "topk_method": model["topk_method"],
            },
        },
        "policy_fixture": {
            "unit": "one token-layer routing decision",
            "confidence": "(largest score - fifth-largest score) / largest score; fixture only, not a calibrated quality metric",
            "cases": ["stock_top4_shared", "top2_shared", "top2_no_shared"],
            "example": policy_decision(fixture_scores, 0.2),
        },
        "economics": {
            "baseline_output_tokens_per_second": baseline,
            "promotion_output_tokens_per_second": baseline / (1.0 - gate),
            "required_wall_time_reduction": gate,
            "combined_ideal_ceiling": ceiling,
            "overhead_budget_fraction_of_baseline_wall_time": ceiling - gate,
            "formula": "net reduction = qualified fraction * combined ideal ceiling - policy/dispatch overhead; qualifying fraction >= (gate + overhead) / ceiling",
            "curve": curve,
        },
        "router_evidence_audit": {
            "result": "absent",
            "checked": [
                "exact current c16 summary and retained trace-region artifacts",
                "adaptive_moe_architecture source-bound runtime contract and patch evidence",
                "repository JSON/JSONL/CSV/TXT/LOG artifacts for router logits, scores, selected expert weights, margins, entropy, and top-k assignments",
                "current observer patch, which records scheduler composition and NVTX ranges rather than MoE-router statistics",
            ],
            "finding": "No exact-current checkpoint/router distribution artifact was found. The retained runtime evidence binds top-k and separate shared-expert execution, but exports neither per-token router scores nor a confidence summary.",
            "observer_recommendation": "close_no_observer_nominated",
            "reason": "A new MoE-forward aggregation/export hook would be a new runtime instrumentation path. It is not present in the pinned observer, its non-synchronizing cost is unmeasured, and the available 3.3329% wall-time budget cannot absorb an unbounded observer or policy path.",
        },
        "decision": {
            "recommendation": "close",
            "reason": "The ideal mechanism needs 74.918% qualified token-layer decisions at zero overhead, yet no exact router-confidence evidence or existing low-overhead observer exists. Synthetic router scores would not answer the question.",
            "not_a_quality_or_endpoint_claim": True,
        },
    }
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--proxy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.config, args.proxy, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
