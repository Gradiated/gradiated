from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
SGLANG = Path("/root/workspace/.agents/runtime/sglang-v0.5.13-source")
PRIOR_PROJECTS = PROJECT.parent
CONFIG = (
    PRIOR_PROJECTS
    / "gemma4_hopper_packed_m384_verifier"
    / "inputs/checkpoint/config.json"
)
TRACE = (
    PRIOR_PROJECTS
    / "gemma4_h200_ngram_verification_critical_path"
    / "artifacts/ngram-critical-20260724t115729Z"
    / "retrieved/artifacts/profile-repair/torch"
    / "1784895017.9256246-TP-0.trace.json.gz"
)

SOURCE_FILES = {
    "gemma4_config_adapter": SGLANG
    / "python/sglang/srt/utils/hf_transformers/config.py",
    "gemma4_model": SGLANG / "python/sglang/srt/models/gemma4_causal.py",
    "forward_batch": SGLANG
    / "python/sglang/srt/model_executor/forward_batch_info.py",
    "cuda_graph": SGLANG
    / "python/sglang/srt/model_executor/cuda_graph_runner.py",
    "hybrid_backend": SGLANG
    / "python/sglang/srt/layers/attention/hybrid_attn_backend.py",
    "triton_backend": SGLANG
    / "python/sglang/srt/layers/attention/triton_backend.py",
    "extend_attention": SGLANG
    / "python/sglang/srt/layers/attention/triton_ops/extend_attention.py",
    "ngram_worker": SGLANG / "python/sglang/srt/speculative/ngram_worker.py",
    "ngram_info": SGLANG / "python/sglang/srt/speculative/ngram_info.py",
    "logits_processor": SGLANG
    / "python/sglang/srt/layers/logits_processor.py",
}

EXPECTED_SHA256 = {
    "config": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    "gemma4_config_adapter": "44610b292144f8a90a25c2bddfb52b92b3e705f74ec8d69f99f576f46b297e82",
    "gemma4_model": "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989",
    "forward_batch": "c977296f3b90be69fff5312f2b3af7699a17b20af24614b139f69888e5776516",
    "cuda_graph": "7d1898247e80ff6a446eb42e4968d2eea0df30b109ee2d089a9ad78791bc079e",
    "hybrid_backend": "c1dc9785ead5131375b9c66992ce66be4394deeff7b55b33a72b90d414fafce9",
    "triton_backend": "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d",
    "extend_attention": "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1",
    "ngram_worker": "27721b777cae08657ec9854ec0137a0db50afd49d84809503312fa43e399b554",
    "ngram_info": "ffa88c663e1893c306710ac801da0693d8248ebcfd1a5bc705c157f90657af1c",
    "logits_processor": "e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14",
}

SGLANG_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
REQUESTS = 32
DRAFT_ROWS = 12
M = REQUESTS * DRAFT_ROWS
SMS = 132
REGISTER_WORDS_PER_SM = 256 * 1024 // 4
SHARED_BYTES_PER_SM = 228 * 1024
THREADS = 256
MAX_WARPS_PER_SM = 64
STOCK_REGISTERS = 255
STOCK_SHARED_BYTES = 81920
TRACE_KERNEL_SECONDS = 1.488205758
TRACE_WINDOW_SECONDS = 2.375141908203125
FIXED_SECONDS_PER_REQUEST = 0.625149101968745
TARGET_SECONDS_PER_REQUEST = 0.500119281574996
PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358


@dataclass(frozen=True)
class Geometry:
    name: str
    layers: int
    q_heads: int
    kv_heads: int
    head_dim: int
    window: int | None
    block_m: int
    measured_median_us: float


LOCAL = Geometry("local", 50, 32, 16, 256, 1024, 64, 1329.763)
GLOBAL = Geometry("global", 10, 32, 4, 512, None, 32, 3270.790)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(tmp.read_text())
    os.replace(tmp, path)


def waves(blocks: int, resident_ctas: int) -> dict[str, float | int]:
    slots_per_wave = SMS * resident_ctas
    count = math.ceil(blocks / slots_per_wave)
    empty = count * slots_per_wave - blocks
    return {
        "logical_blocks": blocks,
        "resident_ctas_per_sm": resident_ctas,
        "wave_count": count,
        "empty_cta_slots": empty,
        "tail_waste_fraction": empty / (count * slots_per_wave),
    }


def resident_ctas(registers: int, shared_bytes: int, threads: int = THREADS) -> int:
    by_register = REGISTER_WORDS_PER_SM // (registers * threads)
    by_shared = (
        SHARED_BYTES_PER_SM // shared_bytes if shared_bytes else 32
    )
    by_warps = MAX_WARPS_PER_SM // (threads // 32)
    return max(1, min(by_register, by_shared, by_warps, 32))


def context_lengths() -> list[int]:
    return [
        round(PROMPT_TOKENS + i * OUTPUT_TOKENS / (REQUESTS - 1))
        for i in range(REQUESTS)
    ]


def layer_model(geometry: Geometry, seq_lens: list[int]) -> dict[str, object]:
    kv_lens = [
        min(seq_len, geometry.window) if geometry.window else seq_len
        for seq_len in seq_lens
    ]
    prefix_edges = sum(DRAFT_ROWS * kv_len for kv_len in kv_lens)
    extend_edges = REQUESTS * DRAFT_ROWS * (DRAFT_ROWS + 1) // 2
    useful_flops = (
        4 * geometry.q_heads * geometry.head_dim * (prefix_edges + extend_edges)
    )
    unique_prefix_kv_bytes = (
        sum(kv_lens) * geometry.kv_heads * geometry.head_dim * 2
    )
    repeated_prefix_kv_bytes = (
        sum(kv_lens) * geometry.q_heads * geometry.head_dim * 2
    )
    unique_extend_kv_bytes = (
        REQUESTS
        * DRAFT_ROWS
        * geometry.kv_heads
        * geometry.head_dim
        * 2
        * 2
    )
    repeated_extend_kv_bytes = (
        REQUESTS
        * DRAFT_ROWS
        * geometry.q_heads
        * geometry.head_dim
        * 2
        * 2
    )
    q_o_bytes = (
        2
        * REQUESTS
        * DRAFT_ROWS
        * geometry.q_heads
        * geometry.head_dim
        * 2
    )
    mask_kv_lens = kv_lens
    repeated_mask_bytes = (
        sum(DRAFT_ROWS * (kv_len + DRAFT_ROWS) for kv_len in mask_kv_lens)
        * geometry.q_heads
    )
    unique_index_bytes = sum(kv_lens) * 8
    repeated_index_bytes = sum(kv_lens) * geometry.q_heads * 8
    compulsory_bytes = (
        unique_prefix_kv_bytes
        + unique_extend_kv_bytes
        + q_o_bytes
        + repeated_mask_bytes
        + unique_index_bytes
    )
    requested_bytes = (
        repeated_prefix_kv_bytes
        + repeated_extend_kv_bytes
        + q_o_bytes
        + repeated_mask_bytes
        + repeated_index_bytes
    )
    return {
        "geometry": geometry.name,
        "context_lengths": {
            "minimum": min(kv_lens),
            "median": float(statistics.median(kv_lens)),
            "maximum": max(kv_lens),
            "evidence": (
                "derived sensitivity mix spanning the measured 4214-token prompt "
                "through the 358-token output cap; exact per-step seq_lens were "
                "not recorded and remain unknown"
            ),
        },
        "useful_flops_upper_with_dense_causal_extend": useful_flops,
        "compulsory_bytes_lower_bound": compulsory_bytes,
        "kernel_requested_bytes_before_cache_reuse": requested_bytes,
        "repeated_over_compulsory_ratio": requested_bytes / compulsory_bytes,
        "arithmetic_intensity_flop_per_requested_byte": useful_flops
        / requested_bytes,
        "arithmetic_intensity_flop_per_compulsory_byte": useful_flops
        / compulsory_bytes,
        "components": {
            "unique_prefix_fp8_kv_bytes": unique_prefix_kv_bytes,
            "repeated_prefix_fp8_kv_bytes": repeated_prefix_kv_bytes,
            "unique_extend_bf16_kv_bytes": unique_extend_kv_bytes,
            "repeated_extend_bf16_kv_bytes": repeated_extend_kv_bytes,
            "bf16_query_plus_output_bytes": q_o_bytes,
            "repeated_full_tree_mask_bytes": repeated_mask_bytes,
            "unique_int64_page_index_bytes": unique_index_bytes,
            "repeated_int64_page_index_bytes": repeated_index_bytes,
        },
    }


def online_state(
    q: list[list[float]],
    k: list[list[float]],
    v: list[list[float]],
    allowed: list[list[bool]],
) -> tuple[list[float], list[float], list[list[float]]]:
    scale = 1.0 / math.sqrt(len(q[0]))
    m: list[float] = []
    l: list[float] = []
    acc: list[list[float]] = []
    for query, row_mask in zip(q, allowed):
        scores = [
            sum(qv * kv for qv, kv in zip(query, key)) * scale
            if is_allowed
            else -math.inf
            for key, is_allowed in zip(k, row_mask)
        ]
        row_max = max(scores)
        probabilities = [
            math.exp(score - row_max) if is_allowed else 0.0
            for score, is_allowed in zip(scores, row_mask)
        ]
        denominator = sum(probabilities)
        row_acc = [
            sum(probability * value[d] for probability, value in zip(probabilities, v))
            for d in range(len(v[0]))
        ]
        m.append(row_max)
        l.append(denominator)
        acc.append(row_acc)
    return m, l, acc


def merge_states(
    states: list[tuple[list[float], list[float], list[list[float]]]]
) -> tuple[list[float], list[float], list[list[float]]]:
    m, l, acc = states[0]
    for next_m, next_l, next_acc in states[1:]:
        merged_m = [max(left_m, right_m) for left_m, right_m in zip(m, next_m)]
        left = [math.exp(old_m - new_m) for old_m, new_m in zip(m, merged_m)]
        right = [
            math.exp(old_m - new_m) for old_m, new_m in zip(next_m, merged_m)
        ]
        acc = [
            [
                old_value * left_scale + new_value * right_scale
                for old_value, new_value in zip(old_row, new_row)
            ]
            for old_row, new_row, left_scale, right_scale in zip(
                acc, next_acc, left, right
            )
        ]
        l = [
            old_l * left_scale + new_l * right_scale
            for old_l, new_l, left_scale, right_scale in zip(l, next_l, left, right)
        ]
        m = merged_m
    return m, l, acc


def normalized(state: tuple[list[float], list[float], list[list[float]]]) -> list[list[float]]:
    return [
        [value / denominator for value in row]
        for row, denominator in zip(state[2], state[1])
    ]


def errors(a: list[list[float]], b: list[list[float]]) -> tuple[float, float]:
    diffs = [
        left - right
        for left_row, right_row in zip(a, b)
        for left, right in zip(left_row, right_row)
    ]
    reference = [value for row in a for value in row]
    max_abs = max(abs(value) for value in diffs)
    relative = math.sqrt(sum(value * value for value in diffs)) / max(
        math.sqrt(sum(value * value for value in reference)), 1e-30
    )
    return max_abs, relative


def oracle_case(geometry: Geometry, seed: int) -> dict[str, object]:
    rng = random.Random(seed)
    requests = 1
    prefix_len = 19 if geometry.window else 23
    page_count = requests * (prefix_len + DRAFT_ROWS) + 17
    all_page_ids = list(range(page_count))
    rng.shuffle(all_page_ids)
    page_ids = [
        all_page_ids[
            request * (prefix_len + DRAFT_ROWS) : (request + 1)
            * (prefix_len + DRAFT_ROWS)
        ]
        for request in range(requests)
    ]
    k_pool = [
        [
            [rng.uniform(-1.0, 1.0) for _ in range(geometry.head_dim)]
            for _ in range(geometry.kv_heads)
        ]
        for _ in range(page_count)
    ]
    v_pool = [
        [
            [rng.uniform(-1.0, 1.0) for _ in range(geometry.head_dim)]
            for _ in range(geometry.kv_heads)
        ]
        for _ in range(page_count)
    ]
    sampled_q_heads = sorted(
        {
            0,
            1,
            geometry.q_heads // geometry.kv_heads,
            geometry.q_heads // 2,
            geometry.q_heads - 2,
            geometry.q_heads - 1,
        }
    )
    mapping_rows: list[dict[str, int]] = []
    oracle_rows: list[dict[str, float | int]] = []
    for req in range(requests):
        ids = page_ids[req]
        for q_head in range(geometry.q_heads):
            for part in range(4):
                task = ((req * geometry.q_heads + q_head) * 4) + part
                decoded_part = task % 4
                decoded_q_head = (task // 4) % geometry.q_heads
                decoded_req = task // (4 * geometry.q_heads)
                value_start = part * (geometry.head_dim // 4)
                mapping_rows.append(
                    {
                        "task": task,
                        "request": decoded_req,
                        "query_head": decoded_q_head,
                        "kv_head": decoded_q_head
                        // (geometry.q_heads // geometry.kv_heads),
                        "value_part": decoded_part,
                        "value_start": value_start,
                        "value_stop": value_start + geometry.head_dim // 4,
                    }
                )
        for q_head in sampled_q_heads:
            kv_head = q_head // (geometry.q_heads // geometry.kv_heads)
            keys = [k_pool[page_id][kv_head] for page_id in ids]
            values = [v_pool[page_id][kv_head] for page_id in ids]
            queries = [
                [rng.uniform(-1.0, 1.0) for _ in range(geometry.head_dim)]
                for _ in range(DRAFT_ROWS)
            ]
            allowed = [
                [True] * prefix_len
                + [column <= row for column in range(DRAFT_ROWS)]
                for row in range(DRAFT_ROWS)
            ]
            stock = normalized(online_state(queries, keys, values, allowed))
            split_v = [[0.0] * geometry.head_dim for _ in range(DRAFT_ROWS)]
            for part in range(4):
                start = part * (geometry.head_dim // 4)
                stop = start + geometry.head_dim // 4
                value_slice = [row[start:stop] for row in values]
                part_state = online_state(
                    queries, keys, value_slice, allowed
                )
                part_output = normalized(part_state)
                for row in range(DRAFT_ROWS):
                    split_v[row][start:stop] = part_output[row]
            cut_points = [0, 7, 15, len(keys)]
            partials = [
                online_state(
                    queries,
                    keys[left:right],
                    values[left:right],
                    [row[left:right] for row in allowed],
                )
                for left, right in zip(cut_points[:-1], cut_points[1:])
            ]
            merged = merge_states(partials)
            staged = normalized(merged)
            split_max_abs, split_relative = errors(stock, split_v)
            staged_max_abs, staged_relative = errors(stock, staged)
            if split_max_abs > 1e-10 or staged_max_abs > 1e-10:
                raise RuntimeError(
                    f"oracle mismatch {geometry.name=} {q_head=} "
                    f"{split_max_abs=} {staged_max_abs=}"
                )
            oracle_rows.append(
                {
                    "query_head": q_head,
                    "kv_head": kv_head,
                    "split_v4_max_abs_error": split_max_abs,
                    "split_v4_relative_l2": split_relative,
                    "staged_max_abs_error": staged_max_abs,
                    "staged_relative_l2": staged_relative,
                }
            )
    split_max_abs = max(row["split_v4_max_abs_error"] for row in oracle_rows)
    split_relative = max(row["split_v4_relative_l2"] for row in oracle_rows)
    staged_max_abs = max(row["staged_max_abs_error"] for row in oracle_rows)
    staged_relative = max(row["staged_relative_l2"] for row in oracle_rows)
    return {
        "geometry": geometry.name,
        "shape": {
            "requests": requests,
            "draft_rows_per_request": DRAFT_ROWS,
            "query_heads": geometry.q_heads,
            "kv_heads": geometry.kv_heads,
            "head_dim": geometry.head_dim,
            "page_size": 1,
            "prefix_len": prefix_len,
            "numerically_tested_query_heads": sampled_q_heads,
        },
        "paged_indexing": {
            "page_ids_unique": len({page for row in page_ids for page in row})
            == sum(len(row) for row in page_ids),
            "gqa_mapping_all_in_range": all(
                0 <= row["kv_head"] < geometry.kv_heads for row in mapping_rows
            ),
            "task_decode_exact": all(
                row["task"]
                == (
                    (
                        row["request"] * geometry.q_heads
                        + row["query_head"]
                    )
                    * 4
                    + row["value_part"]
                )
                for row in mapping_rows
            ),
            "mapping_rows": len(mapping_rows),
        },
        "split_v4_recompute": {
            "max_abs_error": split_max_abs,
            "relative_l2": split_relative,
            "allclose_atol_1e_10_rtol_1e_10": split_max_abs <= 1e-10,
        },
        "context_partition_online_merge": {
            "max_abs_error": staged_max_abs,
            "relative_l2": staged_relative,
            "allclose_atol_1e_10_rtol_1e_10": staged_max_abs <= 1e-10,
        },
        "rows": oracle_rows,
        "evidence_class": "measured deterministic CPU FP64 oracle",
        "transfer_limit": (
            "Proves page-1 task decoding, exact GQA head mapping, value-slice "
            "independence, and online-state merge algebra. It does not prove "
            "BF16/FP8 numerical tolerance, CUDA legality, compiler resources, "
            "or H200 performance."
        ),
    }


def opportunity_register() -> dict[str, object]:
    common_scope = (
        "google/gemma-4-31B-it@b9ea41...; SGLang v0.5.13@28b095c; "
        "NGRAM TARGET_VERIFY; c32 x 12=M384; H200 SXM sm90"
    )
    return {
        "schema_version": 1,
        "opportunities": [
            {
                "id": "persistent_packed_task_schedule",
                "observation": (
                    "The exact stock layer is already one 1024-CTA grid with "
                    "eight H200 waves and only 3.03% empty CTA slots."
                ),
                "evidence_scope": common_scope,
                "competing_explanations": [
                    "launch fragmentation rather than wave fill is dominant",
                    "inactive query lanes rather than grid fill are dominant",
                ],
                "mechanism": (
                    "Replace direct grid indexing with a persistent task queue "
                    "without changing the stock CTA computation."
                ),
                "falsifier": (
                    "Logical task waves, CTA residency, KV traffic, and launch "
                    "count remain unchanged after source-equivalent scheduling."
                ),
                "next_measurement": (
                    "None for this mechanism; require a different within-CTA "
                    "dataflow before H200 admission."
                ),
                "cost_usd": 0.0,
                "decision_impact": 0.35,
                "uncertainty": 0.1,
                "discrimination_power": 0.95,
                "readiness": 1.0,
                "transfer_penalty": 0.05,
                "promotion_rule": "At least one fewer logical wave or launch.",
                "kill_rule": "Same 1024 tasks, eight waves, and 60 launches.",
                "residual_bottleneck_rule": (
                    "Register/live-state and inactive query lanes remain."
                ),
            },
            {
                "id": "global_split_v4_recompute",
                "observation": (
                    "Global d512 stock uses 255 registers/thread and one CTA/SM; "
                    "a four-way value slice can shorten the accumulator."
                ),
                "evidence_scope": common_scope,
                "competing_explanations": [
                    "accumulator registers dominate",
                    "non-accumulator QK and mask state dominates",
                    "extra QK/K traffic dominates any residency gain",
                ],
                "mechanism": (
                    "Four CTAs per request/head recompute identical online "
                    "softmax and each accumulate one d128 value slice."
                ),
                "falsifier": (
                    "The deterministic model shows 2.5x issued attention FLOPs, "
                    "2.5x requested KV bytes, and no reduction below 16 waves "
                    "even at two CTAs/SM."
                ),
                "next_measurement": (
                    "Only after an exact sm90 compile proves <=128 registers, "
                    "zero spills, and a materially smaller no-recompute source."
                ),
                "cost_usd": 0.0,
                "decision_impact": 0.75,
                "uncertainty": 0.35,
                "discrimination_power": 0.9,
                "readiness": 0.35,
                "transfer_penalty": 0.35,
                "promotion_rule": (
                    "No repeated QK, <=128 registers/thread, no spills, and "
                    "CPU/reference equality."
                ),
                "kill_rule": "Recomputed QK or no compiler-proven residency gain.",
                "residual_bottleneck_rule": "QK/K traffic and synchronization remain.",
            },
            {
                "id": "paged_producer_consumer_stage",
                "observation": (
                    "Separating score/softmax from sliced-V ends the d512 live "
                    "range, but page-size-1 KV is an indexed gather."
                ),
                "evidence_scope": common_scope,
                "competing_explanations": [
                    "staging traffic is hidden by low HBM use",
                    "producer/consumer launch and probability traffic dominate",
                    "TMA cannot express the page gather",
                ],
                "mechanism": (
                    "A regular-gather producer writes BF16 probabilities and "
                    "four d128 consumers read them; TMA is restricted to "
                    "contiguous Q/output movement."
                ),
                "falsifier": (
                    "At the midpoint global context it adds five probability "
                    "transfers and five logical CTA families per stock task; a "
                    "prior exact H200 four-slice materialization was 5.10% slower."
                ),
                "next_measurement": (
                    "None for HBM probability materialization; a future candidate "
                    "must keep the producer state on chip without cluster-wide "
                    "page-gather replay."
                ),
                "cost_usd": 0.0,
                "decision_impact": 0.65,
                "uncertainty": 0.3,
                "discrimination_power": 0.85,
                "readiness": 0.3,
                "transfer_penalty": 0.25,
                "promotion_rule": (
                    "No HBM probability tensor, exact page-1 gather, and fewer "
                    "resource-weighted waves than stock."
                ),
                "kill_rule": "Materialized probabilities or TMA assumed to gather pages.",
                "residual_bottleneck_rule": (
                    "Irregular KV gather and stage synchronization remain."
                ),
            },
            {
                "id": "negative_control_maxnreg128",
                "observation": (
                    "The exact H200 global kernel forced to 128 registers doubled "
                    "the theoretical CTA residency but regressed 77.31%."
                ),
                "evidence_scope": (
                    "SGLang v0.5.13 global d512 H200 exact component at context 2048; "
                    "not the M384 target-verification workload"
                ),
                "competing_explanations": [
                    "spills dominate",
                    "extra residency should dominate",
                ],
                "mechanism": "Force maxnreg=128 without changing dataflow.",
                "falsifier": (
                    "Measured 4.300480 ms versus 2.425440 ms and much higher "
                    "L2/DRAM traffic."
                ),
                "next_measurement": "None; negative control is already measured.",
                "cost_usd": 0.0,
                "decision_impact": 0.5,
                "uncertainty": 0.15,
                "discrimination_power": 1.0,
                "readiness": 1.0,
                "transfer_penalty": 0.35,
                "promotion_rule": "Not applicable.",
                "kill_rule": "Measured regression.",
                "residual_bottleneck_rule": "Spill-free live-range redesign is required.",
            },
        ],
    }


def build_result() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    observed = {"config": sha256(CONFIG)}
    for name, path in SOURCE_FILES.items():
        observed[name] = sha256(path)
    mismatches = {
        name: {"expected": EXPECTED_SHA256[name], "observed": digest}
        for name, digest in observed.items()
        if digest != EXPECTED_SHA256[name]
    }
    if mismatches:
        raise RuntimeError(f"pinned input mismatch: {mismatches}")

    seq_lens = context_lengths()
    local = layer_model(LOCAL, seq_lens)
    global_ = layer_model(GLOBAL, seq_lens)
    stock_residency = resident_ctas(STOCK_REGISTERS, STOCK_SHARED_BYTES)
    stock_waves = waves(REQUESTS * LOCAL.q_heads, stock_residency)
    global_probability_bytes = (
        sum(seq_lens) * DRAFT_ROWS * GLOBAL.q_heads * 2
    )
    attention_fraction = TRACE_KERNEL_SECONDS / TRACE_WINDOW_SECONDS
    trace_seconds_per_completed_request = TRACE_KERNEL_SECONDS / REQUESTS
    inferred_whole_request_attention_upper = (
        attention_fraction * FIXED_SECONDS_PER_REQUEST
    )

    arms = [
        {
            "id": "stock",
            "legality": "source-backed production consumer",
            "logical_grid": [REQUESTS, 32, 1],
            "threads_per_cta": THREADS,
            "registers_per_thread": {
                "value": STOCK_REGISTERS,
                "evidence": "measured exact repaired H200 c32 trace",
            },
            "shared_bytes_per_cta": {
                "value": STOCK_SHARED_BYTES,
                "evidence": "measured exact repaired H200 c32 trace",
            },
            "waves": stock_waves,
            "useful_query_lane_fraction": {
                "local": DRAFT_ROWS / LOCAL.block_m,
                "global": DRAFT_ROWS / GLOBAL.block_m,
            },
            "issued_flop_ratio_to_stock": 1.0,
            "requested_kv_byte_ratio_to_stock": 1.0,
        },
        {
            "id": "persistent_packed_task_schedule_only",
            "legality": (
                "legal: a persistent queue changes task dispatch only and retains "
                "the exact stock per-request/head CTA"
            ),
            "logical_tasks": REQUESTS * 32,
            "physical_persistent_ctas": SMS,
            "waves": waves(REQUESTS * 32, stock_residency),
            "registers_per_thread": STOCK_REGISTERS,
            "shared_bytes_per_cta": STOCK_SHARED_BYTES,
            "issued_flop_ratio_to_stock": 1.0,
            "requested_kv_byte_ratio_to_stock": 1.0,
            "launches_per_verification_step": 60,
            "decision": "falsified",
            "reason": (
                "The production consumer is already one grid per dependent layer. "
                "Persistent scheduling cannot fuse across decoder-layer dependencies "
                "and does not change logical waves, CTA residency, or KV work."
            ),
        },
        {
            "id": "global_split_v2_recompute_online_softmax",
            "legality": (
                "legal: two independent d256 output slices share exact page/GQA "
                "mapping and reproduce the same normalized output"
            ),
            "logical_tasks": REQUESTS * GLOBAL.q_heads * 2,
            "registers_per_thread": {
                "range": [180, 255],
                "evidence": (
                    "measured compiler range from prior source-adjacent natural "
                    "V-split specializations; target M384 compile unavailable"
                ),
            },
            "resident_ctas_per_sm": 1,
            "waves": waves(REQUESTS * GLOBAL.q_heads * 2, 1),
            "issued_flop_ratio_to_stock": 1.5,
            "requested_kv_byte_ratio_to_stock": 1.5,
            "decision": "falsified",
            "reason": (
                "The closest compiler evidence does not cross the <=128-register "
                "two-CTA boundary, while the legal decomposition repeats all QK, "
                "mask, K, and index work."
            ),
        },
        {
            "id": "global_split_v4_recompute_online_softmax",
            "legality": (
                "legal: four independent d128 output slices use identical FP32 "
                "online-softmax state and exact GQA/page decoding"
            ),
            "logical_tasks": REQUESTS * GLOBAL.q_heads * 4,
            "registers_per_thread": {
                "range": [96, 180],
                "evidence": (
                    "96 is measured on a different SM90 streaming-cluster source; "
                    "the exact M384 specialization is unknown"
                ),
            },
            "resident_ctas_per_sm_range": [1, 2],
            "wave_count_range": [
                waves(REQUESTS * GLOBAL.q_heads * 4, 2)["wave_count"],
                waves(REQUESTS * GLOBAL.q_heads * 4, 1)["wave_count"],
            ],
            "issued_flop_ratio_to_stock": 2.5,
            "requested_kv_byte_ratio_to_stock": 2.5,
            "decision": "falsified",
            "reason": (
                "Even its optimistic two-CTA case needs 16 waves rather than "
                "stock's eight and repeats QK/K/mask work four times. The CPU "
                "oracle proves semantics but not a physical advantage."
            ),
        },
        {
            "id": "paged_gather_probability_stage_v4",
            "legality": (
                "legal only with ordinary indexed page gathers; TMA cannot encode "
                "the page-size-1 kv_indices gather"
            ),
            "producer_tasks": REQUESTS * GLOBAL.q_heads,
            "consumer_tasks": REQUESTS * GLOBAL.q_heads * 4,
            "producer_plus_consumer_task_families": 5,
            "bf16_probability_bytes_per_global_layer": global_probability_bytes,
            "bf16_probability_write_plus_four_reads_per_global_layer": (
                5 * global_probability_bytes
            ),
            "bf16_probability_traffic_per_ten_global_layers": (
                5 * global_probability_bytes * GLOBAL.layers
            ),
            "issued_flop_ratio_to_stock": 1.0,
            "requested_kv_byte_ratio_to_stock_excluding_probability_state": 1.0,
            "decision": "falsified",
            "reason": (
                "It replaces one register-heavy task family with five ordered task "
                "families and global probability traffic. Prior exact H200 staged "
                "four-slice evidence was 5.10% slower and materialized 1.376 GB; "
                "the paged gather prevents the proposed TMA shortcut."
            ),
        },
        {
            "id": "negative_control_forced_maxnreg128",
            "legality": "legal scope-adjacent H200 control; semantics preserved",
            "registers_per_thread": 128,
            "resident_ctas_per_sm": 2,
            "control_median_ms": 2.425440,
            "candidate_median_ms": 4.300480,
            "latency_ratio_to_control": 4.300480 / 2.425440,
            "l2_throughput_percent": 69.384687,
            "dram_throughput_percent": 54.155986,
            "decision": "regressed_as_predicted",
            "evidence": (
                "measured exact H200 global d512 component at context 2048; "
                "direction calibrates the model but magnitude does not transfer "
                "to M384"
            ),
        },
    ]

    oracle = {
        "schema_version": 1,
        "seed": 384132,
        "cases": [
            oracle_case(LOCAL, 384132),
            oracle_case(GLOBAL, 384133),
        ],
    }
    oracle["passed"] = all(
        case["paged_indexing"]["page_ids_unique"]
        and case["paged_indexing"]["gqa_mapping_all_in_range"]
        and case["paged_indexing"]["task_decode_exact"]
        and case["split_v4_recompute"]["allclose_atol_1e_10_rtol_1e_10"]
        and case["context_partition_online_merge"][
            "allclose_atol_1e_10_rtol_1e_10"
        ]
        for case in oracle["cases"]
    )

    binding = {
        "schema_version": 1,
        "model": f"google/gemma-4-31B-it@{MODEL_REVISION}",
        "runtime": f"SGLang v0.5.13@{SGLANG_COMMIT}",
        "hardware": {
            "accelerator": "NVIDIA H200 SXM",
            "compute_capability": "sm_90",
            "sms": SMS,
            "register_file_bytes_per_sm": 256 * 1024,
            "shared_memory_bytes_per_sm": SHARED_BYTES_PER_SM,
            "l2_bytes": 50 * 1024 * 1024,
            "hbm_bytes_per_second": 4.8e12,
            "evidence": "shared accelerator inventory; vendor-spec prior",
        },
        "source_sha256": observed,
        "trace": {
            "path": str(TRACE.relative_to(PROJECT.parent.parent)),
            "sha256": sha256(TRACE),
            "kernel_launches": 900,
            "verification_steps": 15,
            "local_launches": 750,
            "global_launches": 150,
            "grid": [32, 32, 1],
            "block": [256, 1, 1],
            "registers_per_thread": STOCK_REGISTERS,
            "shared_memory_bytes": STOCK_SHARED_BYTES,
            "summed_attention_seconds": TRACE_KERNEL_SECONDS,
            "trace_window_seconds": TRACE_WINDOW_SECONDS,
            "evidence": "measured exact repaired H200 c32 target-verification trace",
        },
        "producer_consumer_trace": [
            {
                "symbol": "NGRAMWorker._prepare_for_speculative_decoding",
                "source": "ngram_worker.py:165-247",
                "contract": (
                    "asserts bs*draft_token_num rows; writes int64 draft tokens "
                    "and positions, bool full tree mask, request-major retrieve "
                    "tables, sets TARGET_VERIFY, then allocates page-1 slots"
                ),
            },
            {
                "symbol": "ForwardBatch.from_schedule_batch",
                "source": "forward_batch_info.py:623-669,735-783",
                "contract": (
                    "aliases input_ids/req_pool_indices/seq_lens/out_cache_loc and "
                    "uses spec_info.positions; TARGET_VERIFY is a CUDA-graph mode"
                ),
            },
            {
                "symbol": "CudaGraphRunner.replay_prepare",
                "source": "cuda_graph_runner.py:1086-1158",
                "contract": (
                    "pads raw batch to the first captured bs >= raw_bs; at exact "
                    "c32 with cuda_graph_max_bs=32, bs=32 and M remains 384; dummy "
                    "rows use req slot 0 and seq_len fill 1 only for smaller batches"
                ),
            },
            {
                "symbol": "Gemma4Attention.forward",
                "source": "gemma4_causal.py:407-512",
                "contract": (
                    "QKV projection, fused Q/K/V RMSNorm, RoPE, [M,H,D] views, "
                    "RadixAttention, flattened attention output, unchanged o_proj"
                ),
            },
            {
                "symbol": "HybridAttnBackend._select_backend",
                "source": "hybrid_attn_backend.py:28-52",
                "contract": (
                    "TARGET_VERIFY selects the prefill backend unless "
                    "speculative_attention_mode=decode; the pinned launch uses Triton prefill"
                ),
            },
            {
                "symbol": "TritonAttnBackend.init_forward_metadata",
                "source": "triton_backend.py:640-793",
                "contract": (
                    "qo_indptr increments by 12, page-1 kv_indices derive from "
                    "request slots/seq_lens, local layers use window indices and "
                    "offsets, and custom mask/mask_indptr preserve tree semantics"
                ),
            },
            {
                "symbol": "extend_attention_fwd/_fwd_kernel",
                "source": "extend_attention.py:229-665",
                "contract": (
                    "stride-polymorphic [token,head,dim] Q/K/V/O plus int64 paged "
                    "indices; GQA kv_head=q_head//group; FP32 online m/l/acc; "
                    "Hopper local tile M64xN64 and global M32xN64; one CTA per "
                    "request/head because max_extend_len=12"
                ),
            },
            {
                "symbol": "Gemma4ForCausalLM.forward/LogitsProcessor",
                "source": "gemma4_causal.py:1128-1160",
                "contract": (
                    "attention output continues through every decoder layer and "
                    "the unchanged tied LM head/logits processor"
                ),
            },
            {
                "symbol": "NgramVerifyInput.verify",
                "source": "ngram_info.py:287-471",
                "contract": (
                    "reshapes target logits [bs,12,vocab], applies unchanged "
                    "greedy/sampling tree verifier, commits accepted page-1 KV "
                    "slots, and advances seq_lens"
                ),
            },
        ],
        "layout": {
            "rows": M,
            "row_order": "request-major, then 12 tree draft rows",
            "positions_dtype": "int64 from NGRAM preallocated buffer",
            "draft_token_dtype": "int64",
            "tree_mask_dtype": "bool/uint8 consumer",
            "paged_index_dtype": "int64 in pinned Triton target metadata",
            "page_size": 1,
            "query_and_output_dtype": "BF16",
            "new_kv_dtype_before_cache_store": "BF16",
            "paged_kv_cache_dtype": "FP8 E5M2 with scalar K/V descales",
            "online_softmax_dtype": "FP32 m, l, and value accumulator",
            "query_shape_local": [M, 32, 256],
            "kv_shape_local": [M, 16, 256],
            "output_shape_local": [M, 32, 256],
            "query_shape_global": [M, 32, 512],
            "kv_shape_global": [M, 4, 512],
            "output_shape_global": [M, 32, 512],
            "gqa_local": 2,
            "gqa_global": 8,
            "runtime_stride_values": "unknown in retained telemetry",
            "stride_contract": (
                "extend_attention_fwd passes token/head strides explicitly for "
                "Q/K/V/O and page/head strides for cache buffers; K/V extend "
                "inputs are made contiguous. A future GPU contract must capture "
                "actual strides/storage offsets before timing."
            ),
        },
    }

    result = {
        "schema_version": 1,
        "experiment": {
            "hypothesis": (
                "Packing heterogeneous M384 target rows or partitioning global "
                "d512 live state can increase useful H200 residency without "
                "enough repeated work or traffic to erase the gain."
            ),
            "stock_control": "Pinned Triton prefill _fwd_kernel",
            "quality_gate": (
                "Exact page-1/GQA/tree-mask indexing and FP32 online-softmax "
                "equivalence before any performance promotion."
            ),
            "slo": (
                f"Contribute materially toward {TARGET_SECONDS_PER_REQUEST:.15f} "
                f"s/request from {FIXED_SECONDS_PER_REQUEST:.15f} s/request."
            ),
            "maximum_spend_usd": 0.0,
            "gpu_seconds": 0,
            "timeout_minutes": 60,
            "artifact_contract": [
                "SOURCE_BINDING.json",
                "CPU_ORACLE.json",
                "FALSIFIER_RESULT.json",
                "OPPORTUNITIES.json",
                "MECHANISM_TERMINAL.json",
            ],
        },
        "row_mix": {
            "requests": REQUESTS,
            "draft_rows_per_request": DRAFT_ROWS,
            "total_rows": M,
            "exactness": "measured/source-backed",
            "global_context_sensitivity": seq_lens,
            "global_context_sensitivity_evidence": (
                "derived, not measured per step: spans the exact 4214-token "
                "prompt through the 358-token completion cap"
            ),
        },
        "layer_models": {"local": local, "global": global_},
        "arms": arms,
        "whole_request_bounds": {
            "measured_trace_attention_fraction": attention_fraction,
            "measured_profiled_attention_batch_total_seconds": TRACE_KERNEL_SECONDS,
            "measured_profiled_attention_seconds_per_completed_request": (
                trace_seconds_per_completed_request
            ),
            "inferred_attention_upper_seconds_per_qualified_request": (
                inferred_whole_request_attention_upper
            ),
            "inferred_non_attention_floor_seconds_per_request": (
                FIXED_SECONDS_PER_REQUEST - inferred_whole_request_attention_upper
            ),
            "normalization": (
                "The 1.488205758 s sum is batch-total work over 32 completed "
                "requests and 15 verification steps; division by 32 is retained. "
                "The larger whole-request figure transfers the measured 62.66% "
                "trace share to the qualified denominator and is an inferred "
                "upper bound, not a measured endpoint delta."
            ),
        },
        "decision": {
            "classification": "typed_analytical_negative",
            "mechanism": "packed_m384_prescribed_decompositions",
            "promoted_gpu_contract": None,
            "reason": (
                "The underfilled-grid premise is false at exact c32: stock already "
                "has 1,024 CTAs, eight waves, and 3.03% slot waste. Scheduling-only "
                "packing changes none of those quantities. Legal d512 value slicing "
                "requires 1.5x-2.5x issued work and no fewer resource-weighted waves; "
                "the staged alternative adds ordered task families and probability "
                "traffic, while page-size-1 KV prevents TMA gather. The negative "
                "control confirms that occupancy purchased through spills regresses."
            ),
            "scope": (
                "Closes these three prescribed decompositions for the exact pinned "
                "M384 target verifier. It does not close a materially different "
                "attention algorithm that proves compiler resources and eliminates "
                "repeated QK/state traffic."
            ),
            "future_readmission_gate": (
                "Require a concrete exact-source sm90 compile with <=128 "
                "registers/thread, zero spills, <=81920 shared bytes, no materialized "
                "probability tensor, no repeated QK/K page traffic, captured exact "
                "strides/storage offsets, and the same CPU/reference mapping oracle."
            ),
        },
        "evidence_labels": {
            "measured": [
                "exact repaired H200 c32 grid/resources/timings",
                "scope-adjacent H200 maxnreg negative control",
                "deterministic CPU FP64 oracle",
            ],
            "source_backed": [
                "producer/consumer symbols",
                "Hopper tile selection",
                "paged/GQA/mask/online-softmax indexing",
                "CUDA-graph padding rules",
            ],
            "derived": [
                "waves/tail waste",
                "FLOPs/bytes/intensity",
                "split/stage work ratios",
                "whole-request upper bound",
            ],
            "inferred": [
                "global context-length sensitivity",
                "future compiler resource thresholds",
            ],
            "unknown": [
                "actual per-step heterogeneous seq_lens",
                "actual Q/K/V/O strides and storage offsets",
                "exact compiler resources for unimplemented M384 variants",
                "target-shape H200 L2/HBM counters separated by local/global layer",
            ],
        },
    }
    return binding, oracle, result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "artifacts")
    args = parser.parse_args()
    binding, oracle, result = build_result()
    register = opportunity_register()
    atomic_json(args.output_dir / "SOURCE_BINDING.json", binding)
    atomic_json(args.output_dir / "CPU_ORACLE.json", oracle)
    atomic_json(args.output_dir / "FALSIFIER_RESULT.json", result)
    atomic_json(PROJECT / "OPPORTUNITIES.json", register)
    artifact_paths = {
        "source_binding": args.output_dir / "SOURCE_BINDING.json",
        "cpu_oracle": args.output_dir / "CPU_ORACLE.json",
        "falsifier_result": args.output_dir / "FALSIFIER_RESULT.json",
        "opportunity_register": PROJECT / "OPPORTUNITIES.json",
        "falsifier_source": Path(__file__).resolve(),
    }
    ranked = args.output_dir / "OPPORTUNITIES_RANKED.json"
    if ranked.exists():
        artifact_paths["ranked_opportunity_register"] = ranked
    terminal = {
        "schema_version": 1,
        "project": "gemma4_h200_packed_m384_target_verifier",
        "classification": result["decision"]["classification"],
        "scientific_result": True,
        "gpu_invocation_performed": False,
        "cuda_invocation_performed": False,
        "provider_mutation_performed": False,
        "paid_spend_usd": 0.0,
        "decision": result["decision"],
        "source_runtime_model_hardware_binding": binding,
        "opportunity_register": register,
        "physical_falsifier": result,
        "cpu_reference_evidence": oracle,
        "artifact_manifest": {
            name: {
                "path": str(path.relative_to(PROJECT)),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for name, path in artifact_paths.items()
        },
        "terminal_scope": (
            "Decision-bearing offline analytical result. The H200 trace and "
            "scope-adjacent negative controls are measured; the decomposition "
            "resource/traffic model is derived; no endpoint or component speedup "
            "is claimed."
        ),
    }
    atomic_json(PROJECT / "MECHANISM_TERMINAL.json", terminal)
    print(
        json.dumps(
            {
                "classification": result["decision"]["classification"],
                "oracle_passed": oracle["passed"],
                "output_dir": str(args.output_dir),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
