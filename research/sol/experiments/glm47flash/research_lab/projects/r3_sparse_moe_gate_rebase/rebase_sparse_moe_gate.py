#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT.parent
R3 = PROJECTS / "near_stock_c32_memory_frontier/artifacts/near_stock_c32_memory_frontier_r3_control/summary.json"
NATIVE = PROJECTS / "adaptive_moe_architecture/artifacts/ADAPTIVE_MOE_C16_PROXY_2026-07-15.json"
GEOMETRY = PROJECTS / "expert_count_geometry/expert_count_geometry_bound.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/R3_SPARSE_MOE_GATE_REBASE_2026-07-16.json")
    args = parser.parse_args()
    r3, native, geometry = map(load, (R3, NATIVE, GEOMETRY))
    profiles = r3["allocation_result"]["performance"]["profiles"]
    baseline = max(p["output_tokens_per_second_conservative"] for p in profiles)
    top2_shared = native["results"]["top2_routed_ceiling"]["trace_resident_time_fraction"]
    sparse = geometry["trace_bound"]["16_top2_ideal_half_fused_moe_plus_half_routing_ceiling"]
    required, robust = 594.466, 606.355
    endpoint = lambda fraction: baseline / (1.0 - fraction)
    candidate = next(c for c in geometry["candidates"] if c["experts"] == 16 and c["top_k"] == 2)
    result = {
        "schema_version": 1,
        "evidence_label": "derived_rebase_from_measured_r3_endpoint_and_summed_kernel_ceiling_not_gpu_result",
        "terminal_result": "ECONOMIC_CLOSE",
        "question": "Whether r3 552.171055 c16 reopens stock-native top-2/shared or 16-expert/top-2 with a 2% robust economic path.",
        "inputs": {
            "r3_summary": {"path": str(R3), "sha256": sha256(R3), "output_tokens_per_second": baseline},
            "native_top2_shared_proxy": {"path": str(NATIVE), "sha256": sha256(NATIVE), "ideal_summed_work_fraction": top2_shared},
            "expert_geometry": {"path": str(GEOMETRY), "sha256": sha256(GEOMETRY), "ideal_summed_work_fraction": sparse},
        },
        "economic_gate": {"required_output_tokens_per_second": required, "robust_nomination_output_tokens_per_second": robust, "required_margin_above_gate_fraction": 0.02},
        "candidates": [
            {
                "name": "stock_native_top2_with_shared",
                "representation": "exact config/checkpoint-native for top-k=2 with the shared expert retained",
                "ideal_endpoint_tokens_per_second": endpoint(top2_shared),
                "meets_required_gate": endpoint(top2_shared) >= required,
                "meets_robust_nomination_gate": endpoint(top2_shared) >= robust,
                "decision": "close",
            },
            {
                "name": "16_expert_top2",
                "representation": "not exact stock checkpoint: requires expert merging/selecting, router retraining, and checkpoint materialization; proxy is synthetic and semantics-changing",
                "ideal_endpoint_tokens_per_second": endpoint(sparse),
                "meets_required_gate": endpoint(sparse) >= required,
                "meets_robust_nomination_gate": endpoint(sparse) >= robust,
                "headroom_to_robust_gate_tokens_per_second": endpoint(sparse) - robust,
                "decision": "close",
            },
        ],
        "interpretation": {
            "r3_reopen": "16-expert/top-2 crosses only the ordinary target under impossible 100% transfer of a summed-kernel proxy.",
            "conservative_transfer": f"The {endpoint(sparse):.3f} tok/s ideal ceiling is {robust - endpoint(sparse):.3f} tok/s below the {robust:.3f} robust gate before any fragmentation, routing transfer loss, contextual uncertainty, or unmeasured target-geometry critical-path effect. Therefore no nonnegative conservative adjustment can nominate it.",
            "representation": "Materialization/recovery burden further weakens the 16e proxy, but this is ECONOMIC_CLOSE because the ideal ceiling itself fails the mandatory robustness gate.",
            "excluded": "No top-2/no-shared repair, CUDA, provider work, checkpoint mutation, or successor preparation was performed.",
        },
        "next_move": "none; terminal project result",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
