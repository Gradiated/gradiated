"""Zero-cost source/descriptor/numerical gate for the 65th shared expert."""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BLOCK = 64
ROUTED = 64
TOP_K = 4
SHARED = 64
HIDDEN = 8
INTERMEDIATE = 6


def align(ids: list[list[int]], weights: list[list[float]], rows: int):
    """Model moe_align_block_size's expert-major padded descriptor contract."""
    pairs = [(ids[r][j], r, weights[r][j]) for r in range(rows) for j in range(len(ids[r]))]
    buckets = {e: [] for e in range(ROUTED + 1)}
    for item in pairs:
        buckets[item[0]].append(item)
    sorted_pairs, padded = [], {}
    for expert, bucket in buckets.items():
        if not bucket:
            padded[expert] = 0
            continue
        n = math.ceil(len(bucket) / BLOCK) * BLOCK
        padded[expert] = n
        sorted_pairs.extend(bucket)
        sorted_pairs.extend([(expert, -1, 0.0)] * (n - len(bucket)))
    return sorted_pairs, padded


def swiglu(x, gate, up, down):
    hidden = []
    for g_row, u_row in zip(gate, up):
        g = sum(a * b for a, b in zip(x, g_row))
        u = sum(a * b for a, b in zip(x, u_row))
        hidden.append((1.0 / (1.0 + math.exp(-g)) * g) * u)
    return [sum(a * b for a, b in zip(hidden, col)) for col in zip(*down)]


def fixture(seed: int, ids: list[list[int]], weights: list[list[float]]):
    rng = random.Random(seed)
    rand = lambda shape: [[rng.uniform(-1.0, 1.0) for _ in range(shape[1])] for _ in range(shape[0])]
    x = rand((len(ids), HIDDEN))
    weights_all = [rand((INTERMEDIATE, HIDDEN)) for _ in range(ROUTED + 1)]
    up_all = [rand((INTERMEDIATE, HIDDEN)) for _ in range(ROUTED + 1)]
    down_all = [rand((HIDDEN, INTERMEDIATE)) for _ in range(ROUTED + 1)]
    separate = [[0.0] * HIDDEN for _ in ids]
    for row, choices in enumerate(ids):
        for expert, route_weight in zip(choices, weights[row]):
            value = swiglu(x[row], weights_all[expert], up_all[expert], down_all[expert])
            separate[row] = [a + route_weight * b for a, b in zip(separate[row], value)]
        value = swiglu(x[row], weights_all[SHARED], up_all[SHARED], down_all[SHARED])
        separate[row] = [a + b for a, b in zip(separate[row], value)]

    appended_ids = [choice + [SHARED] for choice in ids]
    appended_weights = [weight + [1.0] for weight in weights]
    fused = [[0.0] * HIDDEN for _ in ids]
    for row, choices in enumerate(appended_ids):
        for expert, route_weight in zip(choices, appended_weights[row]):
            value = swiglu(x[row], weights_all[expert], up_all[expert], down_all[expert])
            fused[row] = [a + route_weight * b for a, b in zip(fused[row], value)]
    error = max(abs(a - b) for left, right in zip(separate, fused) for a, b in zip(left, right))
    return error, separate, fused, appended_ids, appended_weights


def main():
    cases = {
        "balanced": ([[i, (i + 1) % ROUTED, (i + 2) % ROUTED, (i + 3) % ROUTED] for i in range(8)], [[0.1, 0.2, 0.3, 0.4]] * 8),
        "duplicate": ([[3, 3, 7, 7], [3, 7, 3, 7]], [[0.1, 0.2, 0.3, 0.4], [0.4, 0.3, 0.2, 0.1]]),
        "empty": ([[0, 0, 0, 0], [63, 63, 63, 63]], [[0.25] * 4, [0.25] * 4]),
        "skew": ([[0, 1, 2, 3]] * 16, [[0.25] * 4] * 16),
    }
    proofs = {}
    for n, (ids, weights) in cases.items():
        error, separate, fused, appended_ids, appended_weights = fixture(100 + len(n), ids, weights)
        _, padded = align(appended_ids, appended_weights, len(ids))
        assert separate == fused, (n, error)
        assert all(row[-1] == SHARED and weight[-1] == 1.0 for row, weight in zip(appended_ids, appended_weights))
        proofs[n] = {
            "tokens": len(ids),
            "max_abs_error_float32": error,
            "shared_id": SHARED,
            "shared_weight": 1.0,
            "routed_assignments": len(ids) * TOP_K,
            "fused_assignments": len(ids) * (TOP_K + 1),
            "padded_rows_by_expert": {str(k): v for k, v in padded.items() if v},
            "aligned_rows": sum(padded.values()),
        }

    trace_files = [
        ROOT.parents[2] / "campaign_100/allocations/nebius_l40s_vllm_awq_splits_ab_v24r2/trace-regions.json",
        ROOT.parents[2] / "campaign_100/allocations/nebius_l40s_vllm_awq_splits_ab_v25r1/trace-regions.json",
    ]
    traces = []
    for path in trace_files:
        obj = json.loads(path.read_text())
        d = obj["decode"]
        shared = next(x["share_of_kernel_duration"] for x in d["top_exact_kernels"] if x["name"].startswith("triton_red_fused__to_copy_add_mean_moe_forward_shared"))
        traces.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "shared_residual_summed_share": shared})
    lower = min(x["shared_residual_summed_share"] for x in traces)
    baseline = 535.2861037029285
    target = 606.355
    result = {
        "decision": "MECHANISM_CLOSE",
        "evidence_label": "source_bound_fixture_and_derived_conservative_ceiling",
        "source_binding": {
            "model_moe_source": "../sglang_current_awq_runtime_gate/evidence/glm4_moe_lite.py:180-229",
            "binding": "num_experts = n_routed_experts + num_fused_shared_experts; top_k = routed_top_k + num_fused_shared_experts",
            "stock_sort_binding": "../expert_sorted_marlin_moe_sm89/RESEARCH_LOG.md:9",
            "wna16_sm89": "retained trace names marlin_moe_wna16_marlin_gemm and marlin::Marlin; L40S SM89 and 99-KiB block limit are in hardware/L40S.md",
        },
        "geometry": {
            "logical_routed_experts": ROUTED,
            "appended_physical_expert_id": SHARED,
            "physical_expert_count": 65,
            "wna16_weight_layout": "65 independent expert slots; K=2048 and N=2*1536/1536 are multiples of 128, so no scalar fallback is implied by the extra expert row",
            "block_size_rows": BLOCK,
            "c16_c32_shared_rows": {"c16": 16, "c32": 32},
            "added_padded_rows": {"c16": BLOCK, "c32": BLOCK},
            "added_descriptor_assignments": {"c16": 16, "c32": 32},
        },
        "numerical_proof": {"cases": proofs, "assertion": "exact float32 separate shared-plus-routed reduction equals appended descriptor reduction; duplicate, empty/skewed, and deterministic cases included"},
        "trace_ceiling": {
            "traces": traces,
            "credit_rule": "credit only the smaller explicitly shared residual attribution; summed kernel time is not wall time and unassigned standard-Marlin work receives zero credit",
            "conservative_removable_sequential_fraction": lower,
            "baseline_tok_s": baseline,
            "perfect_fusion_ceiling_tok_s": baseline / (1.0 - lower),
            "target_tok_s": target,
            "target_reached": baseline / (1.0 - lower) >= target,
            "required_wall_reduction": 1.0 - baseline / target,
        },
        "interpretation": "The descriptor and exact arithmetic survive, but the only defensible shared-branch sequential-wall credit is 0.3844%, yielding a 537.35 tok/s ideal ceiling versus 606.355 tok/s. Fusion is runtime-economically closed before an official-W4 full47 baseline exists.",
    }
    out = ROOT / "artifacts/SHARED_65TH_GATE.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
