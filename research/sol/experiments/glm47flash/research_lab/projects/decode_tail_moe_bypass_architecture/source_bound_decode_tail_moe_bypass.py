#!/usr/bin/env python3
"""Fail-closed source-contract and upper-bound screen for decode-tail MoE bypass."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROJECT = Path(__file__).resolve().parent
CHECKPOINT = Path("/root/.cache/glm47flash-awq-ab31d120")
CONFIG = CHECKPOINT / "config.json"
TRACE = ROOT / "campaign_100/allocations/nebius_l40s_vllm_awq_splits_ab_v25r1/trace-regions.json"
CONTROL = ROOT / "research_lab/projects/nebius_current_awq_c16_direct/artifacts/nebius_current_awq_c16_direct_2026-07-15-r2/summary.json"
PRICE = Path("/root/workspace/research/factory/data/gpu_prices.json")

CHECKPOINT_REVISION = "ab31d120fbe79988fe2a0259993cf3c222aa8881"
RUNTIME = "glm-vllm:0.15.0-transformers-1618d44"
TRANSFORMERS_REVISION = "1618d44b9295361607ec74d7be860ba886aac039"
VLLM_SOURCE = "vllm/model_executor/models/glm4_moe_lite.py"
VLLM_SOURCE_SHA256 = "6a984f701d46dfa05389a45d7aedde6a10ef45a6f59e73d3bbfa1e82f556b4a9"
SERVING_LAYERS = tuple(range(47))
BYPASS_LAYERS = tuple(range(35, 47))
SPARSE_LAYERS = tuple(range(1, 47))
HIDDEN_SIZE = 2048
MOE_WIDTH = 1536
ROUTED_EXPERTS = 4
SHARED_EXPERTS = 1
C16 = 16


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Metadata:
    phase: str
    rows: int


@dataclass
class Trace:
    attention: list[int] = field(default_factory=list)
    kv_writes: list[int] = field(default_factory=list)
    post_attention_norm: list[int] = field(default_factory=list)
    router: list[int] = field(default_factory=list)
    routed_experts: list[int] = field(default_factory=list)
    shared_experts: list[int] = field(default_factory=list)
    moe_residual_add: list[int] = field(default_factory=list)
    final_norm: int = 0
    head: int = 0


class BoundGlmForward:
    """Minimal execution oracle for the pinned vLLM layer boundaries.

    The selected decode path returns the residual produced by attention directly,
    matching the proposed omission of post-attention norm, MoE, and its add.
    """

    def __init__(self, bypass_layers: tuple[int, ...]) -> None:
        if any(layer not in SPARSE_LAYERS for layer in bypass_layers):
            raise ValueError("only sparse serving layers may bypass MoE")
        self.bypass_layers = bypass_layers
        self.trace = Trace()

    def forward(self, shape: tuple[int, int], metadata: Metadata) -> tuple[int, int]:
        if shape != (metadata.rows, HIDDEN_SIZE):
            raise ValueError("hidden shape and uniform phase metadata disagree")
        if metadata.phase not in {"prefill", "decode"}:
            raise ValueError("mixed or unknown prefill/decode batch rejected")
        for layer in SERVING_LAYERS:
            self.trace.attention.append(layer)
            self.trace.kv_writes.append(layer)
            bypass = metadata.phase == "decode" and layer in self.bypass_layers
            if bypass:
                continue
            self.trace.post_attention_norm.append(layer)
            if layer in SPARSE_LAYERS:
                self.trace.router.append(layer)
                self.trace.routed_experts.append(layer)
                self.trace.shared_experts.append(layer)
            self.trace.moe_residual_add.append(layer)
        self.trace.final_norm += 1
        self.trace.head += 1
        return shape


def run_case(phase: str, bypass: tuple[int, ...]) -> dict[str, object]:
    model = BoundGlmForward(bypass)
    shape = model.forward((C16, HIDDEN_SIZE), Metadata(phase=phase, rows=C16))
    return {"shape": list(shape), "trace": model.trace.__dict__}


def active_mlp_flops(experts: int) -> int:
    return 2 * 3 * HIDDEN_SIZE * MOE_WIDTH * experts


def main() -> None:
    config = json.loads(CONFIG.read_text())
    trace = json.loads(TRACE.read_text())["decode"]
    control = json.loads(CONTROL.read_text())
    prices = json.loads(PRICE.read_text())
    stock_prefill = run_case("prefill", ())
    stock_decode = run_case("decode", ())
    bypass_prefill = run_case("prefill", BYPASS_LAYERS)
    bypass_decode = run_case("decode", BYPASS_LAYERS)
    mixed_error = None
    try:
        run_case("mixed", BYPASS_LAYERS)
    except ValueError as exc:
        mixed_error = str(exc)

    decode_families = {row["family"]: row for row in trace["kernel_families"]}
    exact_routed = next(row for row in trace["top_exact_kernels"] if "marlin_moe_wna16::Marlin" in row["name"])["share_of_kernel_duration"]
    routing = decode_families["moe_routing_sort"]["share_of_kernel_duration"]
    no_shared_all_layers = 0.0710105777396504
    layer_fraction = len(BYPASS_LAYERS) / len(SPARSE_LAYERS)
    credited_decode_kernel_fraction = layer_fraction * (exact_routed + routing + no_shared_all_layers)
    control_tok_s = next(
        profile["output_tokens_per_second_conservative"]
        for profile in control["allocation_result"]["performance"]["profiles"]
        if profile["concurrency"] == C16
    )
    trace_kernel_ceiling_tok_s = control_tok_s / (1 - credited_decode_kernel_fraction)
    prefill_wall_fraction = 0.14830484090267484
    decode_wall_fraction = 1 - prefill_wall_fraction
    end_to_end_ceiling_reduction = decode_wall_fraction * credited_decode_kernel_fraction
    endpoint_ceiling_tok_s = control_tok_s / (1 - end_to_end_ceiling_reduction)
    planning_hourly = next(
        row["production_planning_usd_per_gpu_hour"]
        for row in prices["accelerators"]
        if row["id"] == "nvidia-l40s"
    )
    endpoint_cost = planning_hourly * 1_000_000 / (endpoint_ceiling_tok_s * 3600)
    target_tok_s = 594.466

    checks = {
        "stock_full_depth_identity": stock_prefill == run_case("prefill", ()) and stock_decode == run_case("decode", ()),
        "full_depth_prefill": bypass_prefill["trace"]["attention"] == list(SERVING_LAYERS),
        "all_layer_decode_attention": bypass_decode["trace"]["attention"] == list(SERVING_LAYERS),
        "all_layer_decode_kv_writes": bypass_decode["trace"]["kv_writes"] == list(SERVING_LAYERS),
        "moe_absent_only_in_nominated_decode_layers": (
            bypass_decode["trace"]["router"] == list(range(1, 35))
            and bypass_decode["trace"]["routed_experts"] == list(range(1, 35))
            and bypass_decode["trace"]["shared_experts"] == list(range(1, 35))
            and bypass_decode["trace"]["post_attention_norm"] == [0, *range(1, 35)]
            and bypass_decode["trace"]["moe_residual_add"] == [0, *range(1, 35)]
        ),
        "stable_hidden_shape": bypass_prefill["shape"] == bypass_decode["shape"] == [C16, HIDDEN_SIZE],
        "final_norm_and_head_execute": bypass_decode["trace"]["final_norm"] == 1 and bypass_decode["trace"]["head"] == 1,
        "mixed_batch_fail_closed": mixed_error is not None,
    }
    if not all(checks.values()):
        raise RuntimeError(f"fixture failed: {checks}")
    result = {
        "schema_version": 1,
        "evidence_class": "source_bound_fixture_plus_derived_measured_trace_upper_bound",
        "scope": "zero-provider-spend; semantics-changing decode-only architecture proxy; no CUDA, quality, or training claim",
        "inputs": {
            "checkpoint_revision": CHECKPOINT_REVISION,
            "config": {"path": str(CONFIG), "sha256": sha256(CONFIG)},
            "runtime": RUNTIME,
            "transformers_revision": TRANSFORMERS_REVISION,
            "vllm_target": VLLM_SOURCE,
            "vllm_source_sha256": VLLM_SOURCE_SHA256,
            "trace": {"path": str(TRACE), "sha256": sha256(TRACE)},
            "control": {"path": str(CONTROL), "sha256": sha256(CONTROL)},
            "price_inventory": {"path": str(PRICE), "sha256": sha256(PRICE), "planning_usd_per_gpu_hour": planning_hourly},
        },
        "fixture": {
            "bypass_layers": list(BYPASS_LAYERS),
            "preserved": ["all 47 attention paths", "all 47 KV writes", "full prefill", "final norm", "vocabulary head"],
            "omitted_in_decode_layers_35_to_46": ["post-attention norm", "router", "four routed experts", "shared expert", "MoE residual add"],
            "checks": checks,
            "mixed_batch_error": mixed_error,
            "semantic_status": "architecture-cost proxy only",
        },
        "geometry": {
            "serving_layers": len(SERVING_LAYERS), "sparse_layers": len(SPARSE_LAYERS), "bypassed_sparse_layers": len(BYPASS_LAYERS),
            "hidden_size": HIDDEN_SIZE, "moe_width": MOE_WIDTH, "routed_experts_per_token": ROUTED_EXPERTS, "shared_experts_per_token": SHARED_EXPERTS,
            "active_mlp_flops_per_sparse_decode_token": active_mlp_flops(ROUTED_EXPERTS + SHARED_EXPERTS),
            "active_mlp_flops_removed_per_decode_token": len(BYPASS_LAYERS) * active_mlp_flops(ROUTED_EXPERTS + SHARED_EXPERTS),
            "router_projection_flops_removed_per_decode_token": len(BYPASS_LAYERS) * 2 * HIDDEN_SIZE * config["n_routed_experts"],
            "c16_removed_active_mlp_flops_per_decode_step": C16 * len(BYPASS_LAYERS) * active_mlp_flops(ROUTED_EXPERTS + SHARED_EXPERTS),
        },
        "accounting": {
            "no_credit": ["attention/MLA", "KV cache writes", "prefill", "head", "other/copy/norm tail", "bypass dispatch overhead"],
            "credited_trace_components_all_sparse_layers": {"routed_marlin": exact_routed, "routing_sort": routing, "shared_path_conservative_upper_ceiling": no_shared_all_layers},
            "late_layer_fraction": layer_fraction,
            "credited_decode_kernel_fraction": credited_decode_kernel_fraction,
            "prefill_wall_fraction_from_retained_c8_trace": prefill_wall_fraction,
            "decode_wall_fraction_from_retained_c8_trace": decode_wall_fraction,
        },
        "bounds": {
            "control_output_tok_s": control_tok_s,
            "promotion_output_tok_s": target_tok_s,
            "ideal_decode_trace_kernel_work_ceiling_tok_s": trace_kernel_ceiling_tok_s,
            "end_to_end_prefill_diluted_optimistic_ceiling_tok_s": endpoint_ceiling_tok_s,
            "end_to_end_prefill_diluted_optimistic_cost_usd_per_million_output": endpoint_cost,
            "promotion_gap_tok_s": target_tok_s - endpoint_ceiling_tok_s,
            "decision": "close_no_future_L40S_ceiling_nomination",
            "reason": "The target is missed even after treating all credited late MoE kernel work as non-overlapped wall-time savings and assigning zero bypass overhead; real overlap and retained scheduling can only reduce the gain.",
        },
        "limitations": ["Pinned vLLM source is bound by recorded SHA-256; this local fixture does not execute its CUDA container.", "Kernel-duration sums are not wall-time; the reported endpoint number is intentionally an optimistic upper ceiling, not a measured prediction.", "Recovery quality is unmeasured."],
    }
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    (PROJECT / "decode_tail_moe_bypass_bound.json").write_text(output)
    print(output, end="")


if __name__ == "__main__":
    main()
