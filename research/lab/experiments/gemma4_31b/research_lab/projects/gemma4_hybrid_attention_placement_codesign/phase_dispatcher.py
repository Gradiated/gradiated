#!/usr/bin/env python3
"""Executable phase dispatcher and offline cost model for the 55L/5G proxy.

This module intentionally does not import SGLang or touch a GPU.  It specifies
the dispatch and cache-coherence contract an exact-runtime adapter must obey,
and derives a phase-separated H200 cost bound from the project's pinned
measurements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
LAB_DIR = PROJECT_DIR.parents[1]
PROJECTS_DIR = PROJECT_DIR.parent

BASELINE_FULL_LAYERS = (5, 11, 17, 23, 29, 35, 41, 47, 53, 59)
CONVERTED_LAYERS = (11, 23, 35, 47, 59)
RETAINED_FULL_LAYERS = (5, 17, 29, 41, 53)
TARGET_DEPTH = 12
PINNED_BATCH = 32
PINNED_TARGET_ROWS = PINNED_BATCH * TARGET_DEPTH


class ForwardMode(str, Enum):
    EXTEND = "EXTEND"
    DECODE = "DECODE"
    MIXED = "MIXED"
    IDLE = "IDLE"
    TARGET_VERIFY = "TARGET_VERIFY"
    DRAFT_EXTEND = "DRAFT_EXTEND"
    DRAFT_EXTEND_V2 = "DRAFT_EXTEND_V2"
    PREBUILT = "PREBUILT"
    SPLIT_PREFILL = "SPLIT_PREFILL"
    DLLM_EXTEND = "DLLM_EXTEND"


class AttentionPath(str, Enum):
    STOCK = "stock"
    PROXY_LOCAL = "proxy_local"
    NONE = "none"


class CacheBank(str, Enum):
    STOCK = "stock"
    PROXY_LOCAL = "proxy_local"


@dataclass(frozen=True)
class BatchShape:
    requests: int
    logical_rows: int
    captured_rows: int
    tokens_per_request: int

    def validate(self, mode: ForwardMode) -> None:
        if min(self.requests, self.logical_rows, self.captured_rows) < 0:
            raise ValueError("batch dimensions must be non-negative")
        if self.logical_rows > self.captured_rows:
            raise ValueError("logical rows cannot exceed captured rows")
        if mode is ForwardMode.TARGET_VERIFY:
            expected = self.requests * self.tokens_per_request
            if self.logical_rows != expected:
                raise ValueError(
                    f"TARGET_VERIFY owns requests*tokens_per_request rows: "
                    f"{self.logical_rows=} != {expected}"
                )


@dataclass(frozen=True)
class LayerDispatch:
    layer: int
    mode: str
    primary_attention: str
    primary_cache_bank: str | None
    shadow_kv_write_bank: str | None
    logical_rows: int
    padded_rows: int
    cache_commit_policy: str
    graph_contract: str


def dispatch_layer(
    mode: ForwardMode,
    layer: int,
    shape: BatchShape,
) -> LayerDispatch:
    """Return the exact phase plan for one layer and one scalar ForwardMode.

    SGLang assigns one ForwardMode to the complete ForwardBatch.  In
    TARGET_VERIFY, all logical request-major draft rows use the proxy in the
    five converted layers. Graph-padding rows own no request and must remain
    inert. Every other non-idle mode retains stock attention.
    """

    shape.validate(mode)
    padded_rows = shape.captured_rows - shape.logical_rows
    converted = layer in CONVERTED_LAYERS

    if mode is ForwardMode.IDLE:
        primary = AttentionPath.NONE
        primary_bank = None
        shadow_bank = None
    elif converted and mode is ForwardMode.TARGET_VERIFY:
        primary = AttentionPath.PROXY_LOCAL
        primary_bank = CacheBank.PROXY_LOCAL
        # Accepted speculative rows can feed a later stock DECODE, so target
        # verification must also produce the stock layer's K/V.
        shadow_bank = CacheBank.STOCK
    else:
        primary = AttentionPath.STOCK
        primary_bank = CacheBank.STOCK
        # The proxy needs the preceding 1,024 positions when a future verify
        # batch arrives; hidden states cannot be reconstructed from stock K/V.
        shadow_bank = CacheBank.PROXY_LOCAL if converted else None

    return LayerDispatch(
        layer=layer,
        mode=mode.value,
        primary_attention=primary.value,
        primary_cache_bank=primary_bank.value if primary_bank else None,
        shadow_kv_write_bank=shadow_bank.value if shadow_bank else None,
        logical_rows=shape.logical_rows,
        padded_rows=padded_rows,
        cache_commit_policy=(
            "mirror_alloc_write_move_free_for_both_banks"
            if converted and mode is not ForwardMode.IDLE
            else "stock_runtime_policy"
        ),
        graph_contract=(
            "capture_static_target_verify_branch; replay updates values and "
            "logical-row count; padded rows perform no cache write"
            if mode is ForwardMode.TARGET_VERIFY
            else "stock_forward_batch_branch"
        ),
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_paths() -> dict[str, Path]:
    grouped = PROJECTS_DIR / "gemma4_h200_ngram_persistent_grouped_lm_head"
    tree = PROJECTS_DIR / "gemma4_h200_ngram_tree_verify_attention"
    mixed = PROJECTS_DIR / "gemma4_h200_layerwise_mixed_kv_endpoint"
    graph = PROJECTS_DIR / "gemma4_h200_static_c32_multitoken_decode_engine"
    return {
        "forward_batch": grouped / "inputs/bound/forward_batch_info.py",
        "ngram_worker": tree / "inputs/source/ngram_worker.py",
        "ngram_info": tree / "inputs/source/ngram_info.py",
        "cuda_graph_runner": (
            graph / "inputs/upstream/model_executor/cuda_graph_runner.py"
        ),
        "gemma4_model": mixed / "inputs/pinned_source/models/gemma4_causal.py",
        "swa_pool": mixed / "inputs/pinned_source/mem_cache/swa_memory_pool.py",
        "attention_backend": (
            mixed / "inputs/pinned_source/layers/attention/triton_backend.py"
        ),
    }


def verify_pinned_source_contract() -> dict[str, Any]:
    paths = _source_paths()
    texts = {name: path.read_text() for name, path in paths.items()}
    required_fragments = {
        "forward_batch": [
            "TARGET_VERIFY = auto()",
            "or self == ForwardMode.TARGET_VERIFY",
            "def is_cuda_graph(self)",
        ],
        "ngram_worker": [
            "total_draft_token_num == bs * self.draft_token_num",
            "batch.forward_mode = ForwardMode.TARGET_VERIFY",
            "batch.spec_info.prepare_for_verify(batch, self.page_size)",
        ],
        "ngram_info": [
            "batch.input_ids = self.draft_token",
            "batch.out_cache_loc = alloc_token_slots",
            "move_kv_cache(",
            "batch.out_cache_loc = tgt_cache_loc",
        ],
        "cuda_graph_runner": [
            "self.capture_forward_mode = ForwardMode.TARGET_VERIFY",
            "num_tokens = bs * self.num_tokens_per_bs",
            "raw_num_token = raw_bs * self.num_tokens_per_bs",
        ],
        "gemma4_model": [
            'if layer_type == "sliding_attention":',
            "self.q_size = self.num_heads * self.head_dim",
            "self.kv_size = self.num_kv_heads * self.head_dim",
            "sliding_window_size=self.sliding_window",
        ],
        "swa_pool": [
            "def translate_loc_from_full_to_swa",
            "self.swa_kv_pool.set_kv_buffer",
            "self.full_kv_pool.set_kv_buffer",
        ],
        "attention_backend": [
            "forward_batch.out_cache_loc",
            "self.token_to_kv_pool.set_kv_buffer",
        ],
    }
    missing: dict[str, list[str]] = {}
    for name, fragments in required_fragments.items():
        absent = [fragment for fragment in fragments if fragment not in texts[name]]
        if absent:
            missing[name] = absent
    if missing:
        raise RuntimeError(f"pinned source contract changed: {missing}")
    return {
        name: {
            "path": str(path.relative_to(LAB_DIR)),
            "sha256": sha256(path),
            "evidence_type": "pinned_source",
        }
        for name, path in paths.items()
    }


def _placement_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    placement_path = PROJECT_DIR / "PLACEMENT_SIMULATION_RESULT.json"
    terminal_path = PROJECT_DIR / "HYBRID_55L5G_H200_EXECUTION_TERMINAL.json"
    return (
        json.loads(placement_path.read_text()),
        json.loads(terminal_path.read_text()),
    )


def build_cost_model(ordinary_decode_steps: int = 0) -> dict[str, Any]:
    """Derive a phase cost range without claiming a new measurement.

    The lower maintenance estimate scales a K/V-only projection by its exact
    output-width fraction. The upper estimate charges the complete QKV launch,
    bounding the likely loss of efficiency in a narrower standalone GEMM.
    HBM write time is an analytical bandwidth floor, not a latency claim.
    """

    placement, component = _placement_inputs()
    target = placement["layer_cost_reconstruction"]["target_verification"]
    prefill = placement["layer_cost_reconstruction"]["prefill"]
    selected = next(
        row
        for row in placement["placements"]
        if row["name"] == "half_global_keep_early_in_each_pair"
    )
    scope = placement["scope"]

    gross_seconds = selected["target_verification"][
        "predicted_service_savings_seconds_per_request_range"
    ]
    savings_ms_per_cycle = selected["target_verification"][
        "savings_ms_per_cycle_vs_tuned_50_10"
    ]
    cycles_per_request = [
        value * PINNED_BATCH * 1000.0 / savings_ms_per_cycle
        for value in gross_seconds
    ]

    full_linear = prefill["fp8_linear_seconds_per_layer_per_c32_batch"][
        "full_attention"
    ]
    local_linear = prefill["fp8_linear_seconds_per_layer_per_c32_batch"][
        "sliding_attention"
    ]
    # The only family-varying term is attention projection. Full attention has
    # 1.5x the local projection FLOPs, so the difference is half the local
    # attention-projection total.
    local_all_attention_projection_s = 2.0 * (full_linear - local_linear)
    local_kv_projection_lower_s = local_all_attention_projection_s / 3.0
    local_qkv_projection_upper_s = local_all_attention_projection_s * 2.0 / 3.0

    prefill_projection_overhead = [
        len(CONVERTED_LAYERS) * local_kv_projection_lower_s / PINNED_BATCH,
        len(CONVERTED_LAYERS) * local_qkv_projection_upper_s / PINNED_BATCH,
    ]

    medians = target["trace_projection_detail"]["family_medians_us"]
    full_qkv_us = medians["full_attention"]["qkv_median_us"]
    local_qkv_us = medians["sliding_attention"]["qkv_median_us"]
    # Full QKV output is Q=16384 and K+V=4096; local QKV is split equally
    # between Q and K+V.
    target_stock_shadow_us_per_cycle = [
        len(CONVERTED_LAYERS) * full_qkv_us * 0.2,
        len(CONVERTED_LAYERS) * full_qkv_us,
    ]
    decode_local_shadow_us_per_step = [
        len(CONVERTED_LAYERS) * local_qkv_us * 0.5,
        len(CONVERTED_LAYERS) * local_qkv_us,
    ]

    hbm_bytes_per_second = (
        scope["hardware"]["memory"]["bandwidth_gb_s"] * 1_000_000_000
    )
    local_kv_bytes_per_token = placement["geometry"]["layer_work"][
        "sliding_attention"
    ]["kv_bytes_per_token"]
    full_kv_bytes_per_token = placement["geometry"]["layer_work"][
        "full_attention"
    ]["kv_bytes_per_token"]
    prompt_tokens = scope["prompt_tokens_per_request"]
    # SWA is bounded at 1,024 tokens for each request.
    local_prefill_write_bytes_c32 = (
        len(CONVERTED_LAYERS)
        * PINNED_BATCH
        * min(prompt_tokens, 1024)
        * local_kv_bytes_per_token
    )
    prefill_hbm_floor_s_per_request = (
        local_prefill_write_bytes_c32 / hbm_bytes_per_second / PINNED_BATCH
    )

    target_hbm_floor_s = []
    target_projection_overhead_s = []
    decode_projection_overhead_s = []
    decode_hbm_floor_s = (
        ordinary_decode_steps
        * len(CONVERTED_LAYERS)
        * local_kv_bytes_per_token
        / hbm_bytes_per_second
    )
    for index, cycles in enumerate(cycles_per_request):
        target_projection_overhead_s.append(
            cycles
            * target_stock_shadow_us_per_cycle[index]
            / PINNED_BATCH
            / 1_000_000.0
        )
        target_hbm_floor_s.append(
            cycles
            * PINNED_TARGET_ROWS
            * len(CONVERTED_LAYERS)
            * full_kv_bytes_per_token
            / hbm_bytes_per_second
            / PINNED_BATCH
        )
        decode_projection_overhead_s.append(
            ordinary_decode_steps
            * decode_local_shadow_us_per_step[index]
            / PINNED_BATCH
            / 1_000_000.0
        )

    maintenance_lower_s = (
        prefill_projection_overhead[0]
        + prefill_hbm_floor_s_per_request
        + target_projection_overhead_s[0]
        + target_hbm_floor_s[0]
        + decode_projection_overhead_s[0]
        + decode_hbm_floor_s
    )
    maintenance_upper_s = (
        prefill_projection_overhead[1]
        + prefill_hbm_floor_s_per_request
        + target_projection_overhead_s[1]
        + target_hbm_floor_s[1]
        + decode_projection_overhead_s[1]
        + decode_hbm_floor_s
    )
    net_savings = [
        gross_seconds[0] - maintenance_upper_s,
        gross_seconds[1] - maintenance_lower_s,
    ]
    baseline = scope["qualified_baseline_seconds_per_request"]

    baseline_kv_bytes = (
        selected["kv_residency"]["bytes_c32_at_4214_prompt"]
        + selected["kv_residency"]["bytes_saved_vs_baseline"]
    )
    extra_shadow_kv_bytes = (
        len(CONVERTED_LAYERS)
        * PINNED_BATCH
        * 1024
        * local_kv_bytes_per_token
    )

    return {
        "evidence_type": {
            "gross_target_savings": "derived_from_measured_exact_c32_h200_component",
            "projection_maintenance": (
                "derived_width-scaled_lower_and_full-qkv-launch_upper_bound"
            ),
            "hbm_write": "analytical_peak_bandwidth_floor",
        },
        "scope": {
            "batch": PINNED_BATCH,
            "target_depth": TARGET_DEPTH,
            "target_rows": PINNED_TARGET_ROWS,
            "ordinary_decode_steps_scenario": ordinary_decode_steps,
            "baseline_seconds_per_request": baseline,
        },
        "gross_target_savings_seconds_per_request_range": gross_seconds,
        "target_cycles_per_request_range": cycles_per_request,
        "maintenance_seconds_per_request": {
            "prefill_projection_range": prefill_projection_overhead,
            "prefill_hbm_floor": prefill_hbm_floor_s_per_request,
            "target_stock_kv_projection_range": target_projection_overhead_s,
            "target_stock_kv_hbm_floor_range": target_hbm_floor_s,
            "ordinary_decode_local_kv_projection_range": (
                decode_projection_overhead_s
            ),
            "ordinary_decode_local_kv_hbm_floor": decode_hbm_floor_s,
            "total_range": [maintenance_lower_s, maintenance_upper_s],
        },
        "net_savings_seconds_per_request_range": net_savings,
        "net_reduction_fraction_range": [
            net_savings[0] / baseline,
            net_savings[1] / baseline,
        ],
        "predicted_service_seconds_per_request_range": [
            baseline - net_savings[1],
            baseline - net_savings[0],
        ],
        "kv_residency": {
            "baseline_bytes_c32_at_4214_prompt": baseline_kv_bytes,
            "extra_shadow_local_bytes": extra_shadow_kv_bytes,
            "increase_fraction": extra_shadow_kv_bytes / baseline_kv_bytes,
        },
        "measured_component_binding": {
            "weighted_attention_reduction_fraction": component["measurement"][
                "weighted_attention_reduction_fraction"
            ],
            "local_control_median_ms": component["measurement"][
                "local_sliding_window_1024"
            ]["control_median_ms"],
            "local_candidate_median_ms": component["measurement"][
                "local_sliding_window_1024"
            ]["candidate_median_ms"],
        },
        "limitations": [
            "The phase dispatcher and maintenance model are not a GPU measurement.",
            "A narrow K/V-only GEMM may fall outside both width-scaling bounds.",
            "The zero ordinary-decode-step scenario matches the speculative "
            "target-only accounting; callers must set nonzero steps for a "
            "mixed ordinary-decode workload.",
            "No launch, allocator, cache-move, or graph-recapture overhead is "
            "credited beyond the stated projection and HBM terms.",
        ],
    }


def build_result() -> dict[str, Any]:
    source_contract = verify_pinned_source_contract()
    cost = build_cost_model(ordinary_decode_steps=0)
    exact_shape = BatchShape(
        requests=PINNED_BATCH,
        logical_rows=PINNED_TARGET_ROWS,
        captured_rows=PINNED_TARGET_ROWS,
        tokens_per_request=TARGET_DEPTH,
    )
    dispatch_examples = {
        mode.value: asdict(dispatch_layer(mode, CONVERTED_LAYERS[0], exact_shape))
        for mode in (
            ForwardMode.EXTEND,
            ForwardMode.DECODE,
            ForwardMode.TARGET_VERIFY,
            ForwardMode.IDLE,
        )
    }
    return {
        "schema_version": 1,
        "project": PROJECT_DIR.name,
        "classification": "source_complete_candidate",
        "result": "dual_cache_phase_dispatch_candidate",
        "decision": (
            "Retain for one later exact-c32 component falsification. The "
            "source-complete dispatcher isolates the proxy to TARGET_VERIFY, "
            "but safe stock fallback requires mirrored dual-cache maintenance."
        ),
        "scope": {
            "gpu_claimed": False,
            "endpoint_run": False,
            "provider_mutation": False,
            "actual_spend_usd": 0.0,
            "quality_preserving": False,
            "deployable": False,
        },
        "mechanism": {
            "converted_layers": list(CONVERTED_LAYERS),
            "retained_full_layers": list(RETAINED_FULL_LAYERS),
            "row_ownership": (
                "ForwardMode is scalar per ForwardBatch. TARGET_VERIFY owns "
                "all request-major logical rows [request][draft_token]; at "
                "c32 depth12 this is 384 rows. Captured padding rows own no "
                "request and perform no cache write."
            ),
            "dispatch_examples_layer_11": dispatch_examples,
            "cache_semantics": (
                "Both banks receive allocation/write/move/free events. Stock "
                "modes write proxy-local shadow K/V so later verification has "
                "its 1,024-token history. TARGET_VERIFY writes stock-global "
                "shadow K/V so accepted rows remain valid for later stock "
                "decode. Rejected speculative rows are freed from both banks. "
                "After the first converted layer diverges, later stock-shadow "
                "K/V are computed from hybrid hidden state; returning to stock "
                "operators does not restore all-stock semantics."
            ),
            "cuda_graph_boundary": (
                "The speculative runner captures a distinct TARGET_VERIFY "
                "graph with batch_size*tokens_per_request rows, so the Python "
                "mode branch is capture-static. Replay changes tensor values "
                "and logical size, not the selected attention module."
            ),
            "geometry": {
                "stock_global": {
                    "head_dim": 512,
                    "kv_heads": 4,
                    "kv_bytes_per_token": 4096,
                    "receptive_field": "full_prefix",
                },
                "proxy_local": {
                    "head_dim": 256,
                    "kv_heads": 16,
                    "kv_bytes_per_token": 8192,
                    "receptive_field_tokens": 1024,
                },
                "consequence": (
                    "Stock K/V cannot be reinterpreted as proxy-local K/V; "
                    "projection shapes, RoPE, head geometry, and cache layout "
                    "differ."
                ),
            },
        },
        "cost_model": cost,
        "first_expected_target_decision_divergence": {
            "location": (
                "TARGET_VERIFY layer 11 attention output, before its residual "
                "addition; the 4,214-token prompt already exceeds the proxy's "
                "1,024-token receptive field."
            ),
            "telemetry": [
                "forward mode, graph capture batch, logical and padded rows",
                "layer-11 stock/proxy attention-output max and relative error",
                "per-request target top-1/top-k logits and accepted draft count",
                "accepted indices plus stock/proxy cache locations before/after move",
                "post-accept stock-decode logits versus an eager dual-cache reference",
            ],
        },
        "cheapest_later_exact_c32_falsification": {
            "kind": "single_component_no_endpoint",
            "steps": [
                "Populate stock and proxy-local caches from one exact c32 4,214-token prefill.",
                "Run one stock ordinary-decode row and require control equivalence.",
                "Replay one depth-12 TARGET_VERIFY graph with 384 logical rows.",
                "Apply one synthetic accepted-index pattern to both banks, then compare one stock-operator decode with an eager dual-cache reference.",
            ],
            "gates": [
                "stock prefill and pre-verification ordinary decode are bit-exact to control",
                "all 384 logical rows use proxy only at converted layers",
                "padded rows never allocate or write cache slots",
                "both banks survive identical accept/move/free operations",
                "post-accept stock-operator decode is finite and matches the eager hybrid reference",
                "net component saving remains positive after shadow maintenance",
            ],
            "falsifiers": [
                "any stock-path output divergence before the first TARGET_VERIFY",
                "any cache-location mismatch or stale accepted stock K/V",
                "graph recapture or host synchronization caused by phase dispatch",
                "nonpositive net target-cycle saving",
            ],
        },
        "source_contract": source_contract,
        "artifacts": {
            "dispatcher": "phase_dispatcher.py",
            "tests": "test_phase_dispatcher.py",
            "prior_component": "HYBRID_55L5G_H200_EXECUTION_TERMINAL.json",
            "prior_placement": "PLACEMENT_SIMULATION_RESULT.json",
        },
    }


def self_check() -> None:
    verify_pinned_source_contract()
    target_shape = BatchShape(32, 384, 512, 12)
    target = dispatch_layer(ForwardMode.TARGET_VERIFY, 11, target_shape)
    assert target.primary_attention == AttentionPath.PROXY_LOCAL.value
    assert target.shadow_kv_write_bank == CacheBank.STOCK.value
    assert target.padded_rows == 128
    decode = dispatch_layer(
        ForwardMode.DECODE, 11, BatchShape(32, 32, 32, 1)
    )
    assert decode.primary_attention == AttentionPath.STOCK.value
    assert decode.shadow_kv_write_bank == CacheBank.PROXY_LOCAL.value
    cost = build_cost_model()
    low, high = cost["net_savings_seconds_per_request_range"]
    assert 0 < low <= high


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--emit",
        type=Path,
        help="write the typed result JSON to this path",
    )
    parser.add_argument(
        "--ordinary-decode-steps",
        type=int,
        default=0,
        help="emit a cost-only scenario for this many stock decode steps",
    )
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.ordinary_decode_steps < 0:
        parser.error("--ordinary-decode-steps must be non-negative")
    if args.self_check:
        self_check()
    payload = (
        build_result()
        if args.ordinary_decode_steps == 0
        else build_cost_model(args.ordinary_decode_steps)
    )
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.emit:
        args.emit.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
