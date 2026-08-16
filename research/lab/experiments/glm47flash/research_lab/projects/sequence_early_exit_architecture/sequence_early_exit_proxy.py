#!/usr/bin/env python3
"""Executable semantics-changing proxy and c16 early-exit economics bound."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


SERVING_LAYERS = 47
PREFILL_WALL_FRACTION = 176.766519 / (176.766519 + 1015.146826)
TARGET_COST_RATIO = 0.90


@dataclass
class SequenceState:
    phase: str = "prefill"
    exit_depth: int | None = None
    hidden_shape: tuple[int, int] = (1, 2048)
    head_calls: int = 0


class EarlyExitProxy:
    """Toy source-bound forward contract; it deliberately changes semantics."""

    def __init__(self, layer_count: int = SERVING_LAYERS, exit_depth: int | None = None):
        if layer_count != SERVING_LAYERS:
            raise ValueError("stock serving graph must contain exactly 47 layers")
        if exit_depth is not None and not 1 <= exit_depth < layer_count:
            raise ValueError("exit depth must be an interior serving boundary")
        self.layer_count = layer_count
        self.exit_depth = exit_depth

    def run(self, input_tokens: int, output_tokens: int, decisions: list[bool]) -> SequenceState:
        if len(decisions) != output_tokens:
            raise ValueError("one decision is required for each generated token")
        state = SequenceState(hidden_shape=(input_tokens, 2048))
        # Full-depth prefill is mandatory; no early exit is permitted here.
        state.phase = "decode_full"
        for index, use_exit in enumerate(decisions):
            if state.phase == "decode_full" and use_exit:
                if self.exit_depth is None:
                    raise RuntimeError("exit decision in stock mode")
                state.exit_depth = self.exit_depth
                state.phase = "decode_early"
            elif state.phase == "decode_early" and not use_exit:
                raise RuntimeError("re-entry into full depth is forbidden")
            state.head_calls += 1
            if state.hidden_shape != (input_tokens, 2048):
                raise AssertionError("hidden shape changed at exit")
            if index == output_tokens - 1:
                state.phase = "complete"
        return state


def bound(exit_depth: int, overhead_fraction: float) -> dict[str, float | int | bool]:
    tail = SERVING_LAYERS - exit_depth
    decode_fraction = 1.0 - PREFILL_WALL_FRACTION
    net_tail = tail / SERVING_LAYERS - overhead_fraction
    minimum_switch = float("inf") if net_tail <= 0 else (1 - TARGET_COST_RATIO) / (decode_fraction * net_tail)
    return {
        "exit_after_serving_layers": exit_depth,
        "tail_layers": tail,
        "tail_fraction_of_decode_block_work": tail / SERVING_LAYERS,
        "per_switched_decode_overhead_fraction": overhead_fraction,
        "minimum_switched_output_fraction_for_10pct_cost_reduction": minimum_switch,
        "candidate_can_clear_target": minimum_switch <= 1.0,
    }


def projected(exit_depth: int, overhead_fraction: float, switch_rate: float) -> dict[str, float]:
    decode_fraction = 1.0 - PREFILL_WALL_FRACTION
    ratio = PREFILL_WALL_FRACTION + decode_fraction * (
        1 - switch_rate * ((SERVING_LAYERS - exit_depth) / SERVING_LAYERS - overhead_fraction)
    )
    return {
        "switch_rate": switch_rate,
        "cost_ratio": ratio,
        "output_tok_s_equivalent": 535.286 / ratio,
        "usd_per_million_output": 0.5708267273 * ratio,
    }


def main() -> None:
    fixture = EarlyExitProxy(exit_depth=35)
    full = fixture.run(8192, 4, [False, False, False, False])
    switched = fixture.run(8192, 4, [False, True, True, True])
    assert full.phase == switched.phase == "complete"
    assert switched.exit_depth == 35 and switched.head_calls == 4
    try:
        fixture.run(8192, 2, [True, False])
    except RuntimeError as exc:
        assert "re-entry" in str(exc)
    else:
        raise AssertionError("proxy must reject re-entry")
    result = {
        "evidence_class": "derived_trace_bound_plus_executable_semantics_fixture",
        "model": {"serving_layers": SERVING_LAYERS, "hidden_size": 2048, "checkpoint_layer_47_is_mtp": True},
        "workload": {"input_tokens": 8192, "output_tokens": 1024, "concurrency": 16},
        "control": {"output_tok_s": 535.286, "planning_usd_per_gpu_hour": 1.10, "cost_usd_per_million_output": 0.5708267273},
        "trace_wall_proxy": {
            "prefill_region_ms": 176.766519,
            "decode_region_ms": 1015.146826,
            "prefill_wall_fraction": PREFILL_WALL_FRACTION,
            "decode_wall_fraction": 1 - PREFILL_WALL_FRACTION,
            "source": "campaign_100/analysis/TRACE_BOTTLENECK_V13.json",
            "caveat": "retained c8 trace used as a wall-time mix; transfer remains an analytical bound",
        },
        "accounting": {
            "formula": "cost_ratio = prefill_fraction + decode_fraction * (1 - switch_rate * (tail_layers/47 - overhead_fraction))",
            "overhead_definition": "per switched output token, as a fraction of full-depth decode wall time",
            "screen": [bound(depth, overhead) for depth in (35, 39, 43) for overhead in (0.00, 0.02, 0.05)],
            "nominated_exit": 35,
            "nominated_overhead_case": 0.02,
            "nominated_projections": [projected(35, 0.02, rate) for rate in (0.50, 0.60, 0.80, 1.00)],
        },
        "fixture": {
            "stock_full_decode": full.__dict__,
            "one_way_switched_decode": switched.__dict__,
            "proves": ["full-depth prefill", "one-way per-sequence transition", "stable hidden shape", "head invocation", "re-entry rejection"],
            "semantic_status": "semantics-changing oracle decisions; not quality evidence",
        },
    }
    out = Path(__file__).with_name("sequence_early_exit_bound.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
