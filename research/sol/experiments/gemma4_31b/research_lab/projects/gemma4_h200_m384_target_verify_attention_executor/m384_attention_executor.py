#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class LayerGeometry:
    name: str
    layers: int
    query_heads: int
    kv_heads: int
    head_dim: int
    prefix_tokens: int
    sliding_window: int | None
    query_tile: int
    kv_partitions: int


LOCAL = LayerGeometry(
    name="local",
    layers=50,
    query_heads=32,
    kv_heads=16,
    head_dim=256,
    prefix_tokens=1024,
    sliding_window=1024,
    query_tile=12,
    kv_partitions=1,
)
GLOBAL = LayerGeometry(
    name="global",
    layers=10,
    query_heads=32,
    kv_heads=4,
    head_dim=512,
    prefix_tokens=4393,
    sliding_window=None,
    query_tile=4,
    kv_partitions=1,
)

REQUESTS = 32
TARGET_ROWS = 12
REQUEST_WAVE_EXPOSURES = 1186
WAVES_PER_COMPLETED_REQUEST = REQUEST_WAVE_EXPOSURES / REQUESTS
H200_SMS = 132
H200_HBM_BYTES_PER_SECOND = 4_800_000_000_000
QUALIFIED_SECONDS_PER_REQUEST = 0.625149101968745


@dataclass
class Fixture:
    geometry: LayerGeometry
    q: list[list[list[float]]]
    k_extend: list[list[list[float]]]
    v_extend: list[list[list[float]]]
    k_cache: list[list[list[float]]]
    v_cache: list[list[list[float]]]
    page_indices: list[int]
    tree_mask: list[list[bool]]
    scale: float


def _vector(rng: random.Random, n: int, extreme: bool = False) -> list[float]:
    values = [rng.uniform(-0.25, 0.25) for _ in range(n)]
    if extreme and n >= 4:
        values[0] = 0.0
        values[1] = 8.0
        values[2] = -8.0
        values[3] = 2.0**-12
    return values


def make_fixture(
    geometry: LayerGeometry,
    *,
    prefix_tokens: int,
    sliding_window: int | None,
    seed: int,
) -> Fixture:
    rng = random.Random(seed)
    fixture_geometry = LayerGeometry(
        **{
            **asdict(geometry),
            "prefix_tokens": prefix_tokens,
            "sliding_window": sliding_window,
        }
    )
    q = [
        [_vector(rng, geometry.head_dim, extreme=(row == 0 and head == 0)) for head in range(geometry.query_heads)]
        for row in range(TARGET_ROWS)
    ]
    k_extend = [
        [_vector(rng, geometry.head_dim, extreme=(row == 1 and head == 0)) for head in range(geometry.kv_heads)]
        for row in range(TARGET_ROWS)
    ]
    v_extend = [
        [_vector(rng, geometry.head_dim, extreme=(row == 2 and head == 0)) for head in range(geometry.kv_heads)]
        for row in range(TARGET_ROWS)
    ]

    physical_slots = prefix_tokens * 2 + 3
    k_cache = [
        [_vector(rng, geometry.head_dim) for _ in range(geometry.kv_heads)]
        for _ in range(physical_slots)
    ]
    v_cache = [
        [_vector(rng, geometry.head_dim) for _ in range(geometry.kv_heads)]
        for _ in range(physical_slots)
    ]
    candidates = list(range(1, physical_slots, 2))
    rng.shuffle(candidates)
    page_indices = candidates[:prefix_tokens]

    parents = [-1, 0, 0, 1, 1, 2, 2, 3, 4, 5, 6, 7]
    tree_mask = []
    for query in range(TARGET_ROWS):
        allowed = {query}
        parent = parents[query]
        while parent >= 0:
            allowed.add(parent)
            parent = parents[parent]
        tree_mask.append([key in allowed for key in range(TARGET_ROWS)])

    return Fixture(
        geometry=fixture_geometry,
        q=q,
        k_extend=k_extend,
        v_extend=v_extend,
        k_cache=k_cache,
        v_cache=v_cache,
        page_indices=page_indices,
        tree_mask=tree_mask,
        scale=1.0,
    )


def _allowed_key_positions(fixture: Fixture, query: int) -> list[tuple[str, int]]:
    geometry = fixture.geometry
    positions: list[tuple[str, int]] = []
    absolute_query = geometry.prefix_tokens + query
    for logical_key in range(geometry.prefix_tokens):
        if (
            geometry.sliding_window is None
            or absolute_query <= logical_key + geometry.sliding_window
        ):
            positions.append(("prefix", logical_key))
    for key in range(TARGET_ROWS):
        if not fixture.tree_mask[query][key]:
            continue
        if (
            geometry.sliding_window is None
            or query <= key + geometry.sliding_window
        ):
            positions.append(("extend", key))
    return positions


def _key_value(
    fixture: Fixture, kind: str, logical_index: int, kv_head: int
) -> tuple[list[float], list[float]]:
    if kind == "prefix":
        physical_index = fixture.page_indices[logical_index]
        return (
            fixture.k_cache[physical_index][kv_head],
            fixture.v_cache[physical_index][kv_head],
        )
    return (
        fixture.k_extend[logical_index][kv_head],
        fixture.v_extend[logical_index][kv_head],
    )


def _dot(a: list[float], b: list[float]) -> float:
    return math.fsum(x * y for x, y in zip(a, b))


def _direct_attention(
    fixture: Fixture,
    query: int,
    query_head: int,
    positions: list[tuple[str, int]],
) -> list[float]:
    kv_head = query_head // (
        fixture.geometry.query_heads // fixture.geometry.kv_heads
    )
    scores = []
    values = []
    for kind, index in positions:
        key, value = _key_value(fixture, kind, index, kv_head)
        scores.append(_dot(fixture.q[query][query_head], key) * fixture.scale)
        values.append(value)
    maximum = max(scores)
    weights = [math.exp(score - maximum) for score in scores]
    denominator = math.fsum(weights)
    return [
        math.fsum(weight * value[dim] for weight, value in zip(weights, values))
        / denominator
        for dim in range(fixture.geometry.head_dim)
    ]


def stock_reference(fixture: Fixture) -> list[list[list[float]]]:
    return [
        [
            _direct_attention(
                fixture,
                query,
                query_head,
                _allowed_key_positions(fixture, query),
            )
            for query_head in range(fixture.geometry.query_heads)
        ]
        for query in range(TARGET_ROWS)
    ]


def _partial_online_state(
    fixture: Fixture,
    query: int,
    query_head: int,
    positions: Iterable[tuple[str, int]],
) -> tuple[float, float, list[float]]:
    kv_head = query_head // (
        fixture.geometry.query_heads // fixture.geometry.kv_heads
    )
    maximum = -math.inf
    denominator = 0.0
    accumulator = [0.0] * fixture.geometry.head_dim
    for kind, index in positions:
        key, value = _key_value(fixture, kind, index, kv_head)
        score = _dot(fixture.q[query][query_head], key) * fixture.scale
        next_maximum = max(maximum, score)
        old_scale = 0.0 if maximum == -math.inf else math.exp(maximum - next_maximum)
        new_scale = math.exp(score - next_maximum)
        denominator = denominator * old_scale + new_scale
        accumulator = [
            prior * old_scale + new_scale * item
            for prior, item in zip(accumulator, value)
        ]
        maximum = next_maximum
    return maximum, denominator, accumulator


def _merge_states(
    states: Iterable[tuple[float, float, list[float]]]
) -> list[float]:
    states = list(states)
    maximum = max(state[0] for state in states)
    weighted_denominators = [
        denominator * math.exp(local_maximum - maximum)
        for local_maximum, denominator, _ in states
    ]
    denominator = math.fsum(weighted_denominators)
    return [
        math.fsum(
            scale * accumulator[dim]
            for scale, (_, _, accumulator) in zip(
                [
                    math.exp(local_maximum - maximum)
                    for local_maximum, _, _ in states
                ],
                states,
            )
        )
        / denominator
        for dim in range(len(states[0][2]))
    ]


def grouped_partitioned_candidate(
    fixture: Fixture,
) -> list[list[list[float]]]:
    output = [
        [
            [0.0] * fixture.geometry.head_dim
            for _ in range(fixture.geometry.query_heads)
        ]
        for _ in range(TARGET_ROWS)
    ]
    group_size = fixture.geometry.query_heads // fixture.geometry.kv_heads
    for kv_head in range(fixture.geometry.kv_heads):
        query_heads = range(kv_head * group_size, (kv_head + 1) * group_size)
        for query_start in range(0, TARGET_ROWS, fixture.geometry.query_tile):
            query_end = min(TARGET_ROWS, query_start + fixture.geometry.query_tile)
            for query in range(query_start, query_end):
                positions = _allowed_key_positions(fixture, query)
                partition_size = math.ceil(
                    len(positions) / fixture.geometry.kv_partitions
                )
                partitions = [
                    positions[start : start + partition_size]
                    for start in range(0, len(positions), partition_size)
                ]
                for query_head in query_heads:
                    states = [
                        _partial_online_state(
                            fixture, query, query_head, partition
                        )
                        for partition in partitions
                        if partition
                    ]
                    output[query][query_head] = _merge_states(states)
    return output


def compare_outputs(
    expected: list[list[list[float]]],
    actual: list[list[list[float]]],
) -> dict[str, float | int]:
    max_abs = 0.0
    squared_error = 0.0
    squared_reference = 0.0
    compared = 0
    for expected_rows, actual_rows in zip(expected, actual):
        for expected_vector, actual_vector in zip(expected_rows, actual_rows):
            for lhs, rhs in zip(expected_vector, actual_vector):
                difference = abs(lhs - rhs)
                max_abs = max(max_abs, difference)
                squared_error += difference * difference
                squared_reference += lhs * lhs
                compared += 1
    return {
        "compared_elements": compared,
        "max_abs_error": max_abs,
        "relative_l2_error": math.sqrt(squared_error / squared_reference),
    }


def run_oracle() -> dict:
    cases = [
        ("local_exact_geometry", make_fixture(LOCAL, prefix_tokens=7, sliding_window=1024, seed=11)),
        ("local_window_boundary", make_fixture(LOCAL, prefix_tokens=9, sliding_window=4, seed=17)),
        ("global_exact_geometry", make_fixture(GLOBAL, prefix_tokens=11, sliding_window=None, seed=23)),
    ]
    rows = []
    for name, fixture in cases:
        result = compare_outputs(
            stock_reference(fixture),
            grouped_partitioned_candidate(fixture),
        )
        rows.append(
            {
                "case": name,
                "geometry": asdict(fixture.geometry),
                **result,
                "passed": result["max_abs_error"] <= 2e-12
                and result["relative_l2_error"] <= 2e-12,
            }
        )
    return {
        "artifact_type": "m384_attention_cpu_oracle",
        "schema_version": 1,
        "seed_contract": [11, 17, 23],
        "semantics": {
            "cache_layout": "page_size_1_NHD_with_noncontiguous_physical_slots",
            "prefix_mask": "all prefix positions allowed before optional local-window clipping",
            "target_mask": "explicit branching NGRAM ancestry mask, including self",
            "gqa_mapping": "kv_head = query_head // (query_heads / kv_heads)",
            "softmax": "float64 direct stock oracle versus partitioned online-softmax merge",
            "scale": 1.0,
            "output_consumer": "flatten heads then unchanged Gemma4 o_proj",
        },
        "cases": rows,
        "passed": all(row["passed"] for row in rows),
    }


def _layer_physical_model(geometry: LayerGeometry) -> dict:
    group_size = geometry.query_heads // geometry.kv_heads
    unique_kv_bytes_per_request_layer = (
        geometry.prefix_tokens
        * geometry.kv_heads
        * geometry.head_dim
        * 2
        * 2
    )
    stock_logical_kv_bytes_per_request_layer = (
        unique_kv_bytes_per_request_layer * group_size
    )
    query_tiles = math.ceil(TARGET_ROWS / geometry.query_tile)
    candidate_logical_kv_bytes_per_request_layer = (
        unique_kv_bytes_per_request_layer * query_tiles
    )
    partial_bytes_per_batch_layer = 0
    if geometry.kv_partitions > 1:
        partial_elements = (
            REQUESTS
            * TARGET_ROWS
            * geometry.query_heads
            * geometry.head_dim
            * geometry.kv_partitions
        )
        partial_state_elements = (
            REQUESTS
            * TARGET_ROWS
            * geometry.query_heads
            * geometry.kv_partitions
            * 2
        )
        partial_bytes_per_batch_layer = (
            partial_elements * 4 * 2 + partial_state_elements * 4 * 2
        )
    prefix_attention_flops_per_batch_layer = (
        4
        * REQUESTS
        * TARGET_ROWS
        * geometry.query_heads
        * geometry.prefix_tokens
        * geometry.head_dim
    )
    extend_attention_flops_upper_per_batch_layer = (
        4
        * REQUESTS
        * TARGET_ROWS
        * geometry.query_heads
        * TARGET_ROWS
        * geometry.head_dim
    )
    stock_attention_ctas = REQUESTS * geometry.query_heads
    candidate_stage1_ctas = (
        REQUESTS
        * geometry.kv_heads
        * query_tiles
        * geometry.kv_partitions
    )
    candidate_reducer_ctas = (
        REQUESTS * geometry.kv_heads * query_tiles
        if geometry.kv_partitions > 1
        else 0
    )
    kv_store_bytes_per_batch_layer = (
        REQUESTS
        * TARGET_ROWS
        * geometry.kv_heads
        * geometry.head_dim
        * 2
        * 2
    )
    return {
        "geometry": asdict(geometry),
        "gqa_group_size": group_size,
        "useful_prefix_attention_flops_per_batch_layer": prefix_attention_flops_per_batch_layer,
        "useful_attention_flops_upper_per_batch_layer": prefix_attention_flops_per_batch_layer
        + extend_attention_flops_upper_per_batch_layer,
        "unique_compulsory_kv_bytes_per_batch_layer": unique_kv_bytes_per_request_layer
        * REQUESTS,
        "stock_logical_kv_load_bytes_per_batch_layer": stock_logical_kv_bytes_per_request_layer
        * REQUESTS,
        "candidate_logical_kv_load_bytes_per_batch_layer": candidate_logical_kv_bytes_per_request_layer
        * REQUESTS,
        "candidate_partial_read_write_bytes_per_batch_layer": partial_bytes_per_batch_layer,
        "kv_store_bytes_per_batch_layer": kv_store_bytes_per_batch_layer,
        "stock": {
            "attention_launches_per_layer": 1,
            "kv_store_launches_per_layer": 1,
            "attention_grid_ctas": stock_attention_ctas,
            "attention_grid_waves": stock_attention_ctas / H200_SMS,
        },
        "candidate": {
            "stage1_launches_per_layer": 1,
            "reducer_launches_per_layer": int(geometry.kv_partitions > 1),
            "separate_kv_store_launches_per_layer": 0,
            "stage1_grid_ctas": candidate_stage1_ctas,
            "stage1_grid_waves": candidate_stage1_ctas / H200_SMS,
            "reducer_grid_ctas": candidate_reducer_ctas,
            "reducer_grid_waves": candidate_reducer_ctas / H200_SMS,
        },
    }


def build_physical_model() -> dict:
    layers = [_layer_physical_model(LOCAL), _layer_physical_model(GLOBAL)]
    totals = {
        "useful_prefix_attention_flops_per_full_wave": 0,
        "useful_attention_flops_upper_per_full_wave": 0,
        "unique_compulsory_kv_bytes_per_full_wave": 0,
        "stock_logical_kv_load_bytes_per_full_wave": 0,
        "candidate_logical_and_partial_bytes_per_full_wave": 0,
        "kv_store_bytes_per_full_wave": 0,
        "stock_attention_and_store_launches_per_full_wave": 0,
        "candidate_attention_and_store_launches_per_full_wave": 0,
    }
    for row in layers:
        count = row["geometry"]["layers"]
        totals["useful_prefix_attention_flops_per_full_wave"] += (
            row["useful_prefix_attention_flops_per_batch_layer"] * count
        )
        totals["useful_attention_flops_upper_per_full_wave"] += (
            row["useful_attention_flops_upper_per_batch_layer"] * count
        )
        totals["unique_compulsory_kv_bytes_per_full_wave"] += (
            row["unique_compulsory_kv_bytes_per_batch_layer"] * count
        )
        totals["stock_logical_kv_load_bytes_per_full_wave"] += (
            row["stock_logical_kv_load_bytes_per_batch_layer"] * count
        )
        totals["candidate_logical_and_partial_bytes_per_full_wave"] += (
            row["candidate_logical_kv_load_bytes_per_batch_layer"]
            + row["candidate_partial_read_write_bytes_per_batch_layer"]
        ) * count
        totals["kv_store_bytes_per_full_wave"] += (
            row["kv_store_bytes_per_batch_layer"] * count
        )
        totals["stock_attention_and_store_launches_per_full_wave"] += 2 * count
        totals["candidate_attention_and_store_launches_per_full_wave"] += (
            row["candidate"]["stage1_launches_per_layer"]
            + row["candidate"]["reducer_launches_per_layer"]
        ) * count

    removable_bytes_per_full_wave = (
        totals["stock_logical_kv_load_bytes_per_full_wave"]
        + totals["kv_store_bytes_per_full_wave"]
        - totals["candidate_logical_and_partial_bytes_per_full_wave"]
    )
    byte_floor_seconds_per_request = (
        removable_bytes_per_full_wave
        / REQUESTS
        * WAVES_PER_COMPLETED_REQUEST
        / H200_HBM_BYTES_PER_SECOND
    )
    totals.update(
        {
            "candidate_logical_bytes_removed_per_full_wave": removable_bytes_per_full_wave,
            "candidate_launches_removed_per_full_wave": totals[
                "stock_attention_and_store_launches_per_full_wave"
            ]
            - totals["candidate_attention_and_store_launches_per_full_wave"],
            "zero_cache_peak_hbm_time_scale_seconds_per_completed_request": byte_floor_seconds_per_request,
            "zero_cache_peak_hbm_time_scale_fraction_of_qualified_service": byte_floor_seconds_per_request
            / QUALIFIED_SECONDS_PER_REQUEST,
            "strict_source_only_whole_request_savings_upper_fraction": 1.0,
            "strict_upper_bound_reason": "The two bound predecessor artifacts contain no attention timing or scope-matched critical-path attribution; source and byte counts cannot prove a tighter latency upper bound than the complete qualified request.",
        }
    )
    return {
        "artifact_type": "m384_attention_physical_model",
        "schema_version": 1,
        "evidence_labels": {
            "geometry": "source-backed and predecessor-measured",
            "flops_bytes_launches_grid_waves": "analytical",
            "h200_specs": "vendor-reported shared inventory prior",
            "whole_request_denominator": "campaign-measured",
            "performance_effect": "not measured and not claimed",
        },
        "workload": {
            "requests": REQUESTS,
            "target_rows_per_request": TARGET_ROWS,
            "m": REQUESTS * TARGET_ROWS,
            "request_wave_exposures": REQUEST_WAVE_EXPOSURES,
            "waves_per_completed_request": WAVES_PER_COMPLETED_REQUEST,
            "qualified_seconds_per_request": QUALIFIED_SECONDS_PER_REQUEST,
        },
        "hardware": {
            "id": "nvidia-h200-sxm",
            "sms": H200_SMS,
            "hbm_bandwidth_bytes_per_second": H200_HBM_BYTES_PER_SECOND,
            "l2_bytes": 50_000_000,
            "register_file_32bit_registers_per_sm": 65_536,
            "max_registers_per_thread": 255,
            "shared_memory_bytes_per_sm": 228 * 1024,
            "max_shared_memory_bytes_per_block": 227 * 1024,
        },
        "layers": layers,
        "totals": totals,
        "interpretation": {
            "stock_metadata": "Request/page/SWA/mask metadata is built once per forward and reused across all layers; it is not a per-layer optimization target.",
            "stock_new_kv": "The two-stage Triton extend kernel consumes new K/V directly while a separate store_cache launch writes the same K/V for future forwards.",
            "candidate": "Map CTAs by request and KV head, flatten query-position x GQA-head within each CTA, reuse each paged K/V tile across that group, and fuse the future-cache store into the q-tile-zero CTA. Local uses one 12x2 tile; global uses three 4x8 tiles with unchanged per-row key reduction order.",
            "transfer_limit": "Logical K/V load reduction becomes HBM reduction only if stock GQA reuse misses L2. The peak-HBM time scale is a discriminator scale, not a latency prediction or upper bound.",
        },
    }


def _atomic_json(path: Path, value: dict) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(encoded)
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    oracle = run_oracle()
    physical = build_physical_model()
    _atomic_json(args.output_dir / "CPU_ORACLE_RESULT.json", oracle)
    _atomic_json(args.output_dir / "PHYSICAL_MODEL.json", physical)
    summary = {
        "oracle_passed": oracle["passed"],
        "oracle_cases": len(oracle["cases"]),
        "max_abs_error": max(row["max_abs_error"] for row in oracle["cases"]),
        "relative_l2_error": max(
            row["relative_l2_error"] for row in oracle["cases"]
        ),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if oracle["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
