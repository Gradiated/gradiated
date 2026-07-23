#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
BLOCK = 64
CONTROL_WINDOW = 1024
CANDIDATE_WINDOW = 512
LOCAL_WALL_FRACTION = 0.1531203203096733
CONTROL_SECONDS_PER_REQUEST = 0.6743258590313417
ECONOMIC_CEILING = 0.6381105231


def active_tiles(prefix: int, extend: int, window: int) -> dict[str, int]:
    prefix_tiles = 0
    extend_tiles = 0
    query_blocks = math.ceil(extend / BLOCK)
    for query_block in range(query_blocks):
        query_start = query_block * BLOCK
        query_stop = min(extend, query_start + BLOCK)
        for key_start in range(0, prefix, BLOCK):
            key_stop = min(prefix, key_start + BLOCK)
            if prefix + query_start <= key_stop - 1 + window:
                prefix_tiles += 1
        for key_start in range(0, min(extend, query_stop), BLOCK):
            key_stop = min(extend, key_start + BLOCK)
            if query_stop - 1 >= key_start and query_start <= key_stop - 1 + window:
                extend_tiles += 1
    return {
        "query_blocks": query_blocks,
        "prefix_tiles": prefix_tiles,
        "extend_tiles": extend_tiles,
        "total_tiles": prefix_tiles + extend_tiles,
    }


def main() -> None:
    cases = [
        ("boundary_65_1023", 1023, 65),
        ("boundary_127_1025", 1025, 127),
        ("observed_grid_z2", 1024, 128),
        ("observed_grid_z32_primary", 1024, 2048),
        ("observed_grid_z32_tail", 1025, 128),
    ]
    rows = []
    for name, prefix, extend in cases:
        control = active_tiles(prefix, extend, CONTROL_WINDOW)
        candidate = active_tiles(prefix, extend, CANDIDATE_WINDOW)
        rows.append(
            {
                "name": name,
                "prefix_tokens": prefix,
                "extend_tokens": extend,
                "control": control,
                "candidate": candidate,
                "active_tile_reduction_fraction": (
                    1 - candidate["total_tiles"] / control["total_tiles"]
                ),
            }
        )
    conservative_tile_reduction = min(
        row["active_tile_reduction_fraction"] for row in rows
    )
    whole_request_bound = conservative_tile_reduction * LOCAL_WALL_FRACTION
    predicted = CONTROL_SECONDS_PER_REQUEST * (1 - whole_request_bound)
    value = {
        "schema_version": 1,
        "classification": "analytical_active_tile_physical_bound",
        "source_semantics": {
            "kernel": "sglang.srt.layers.attention.triton_ops.extend_attention._fwd_kernel",
            "source_sha256": "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1",
            "block_m": BLOCK,
            "block_n": BLOCK,
            "control_window_tokens": CONTROL_WINDOW,
            "candidate_window_tokens": CANDIDATE_WINDOW,
            "rule": "count only prefix and causal-extend tiles for which _fwd_kernel SKIP_TILE is false",
        },
        "cases": rows,
        "conservative_active_tile_reduction_fraction": conservative_tile_reduction,
        "measured_local_kernel_wall_fraction": LOCAL_WALL_FRACTION,
        "conservative_whole_request_bound_fraction": whole_request_bound,
        "control_seconds_per_request": CONTROL_SECONDS_PER_REQUEST,
        "bound_seconds_per_request": predicted,
        "economic_ceiling_seconds_per_request": ECONOMIC_CEILING,
        "five_percent_gate_pass": whole_request_bound >= 0.05,
        "economic_ceiling_bound_pass": predicted <= ECONOMIC_CEILING,
        "interpretation": (
            "Analytical opportunity bound, not a measured latency claim. It assumes "
            "time removed scales with active QK/V tiles and leaves loop/launch/fixed work unchanged."
        ),
    }
    destination = HERE / "PHYSICAL_BOUND.json"
    temporary = destination.with_suffix(".json.part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(destination)
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
