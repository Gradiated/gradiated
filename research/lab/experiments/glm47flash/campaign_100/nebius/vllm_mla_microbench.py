#!/usr/bin/env python3
"""Exact-shape GLM MLA grouped-decode correctness and latency sweep."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


SOURCE = Path("/usr/local/lib/python3.12/dist-packages/vllm/v1/attention/ops/triton_decode_attention.py")
SOURCE_SHA256 = "cf4debbbbdf2245355177dd7be91c4ac75730a9207a10cd7dab6306a5c3bdec4"
UNSCOPED_MIXED_TRACE_KERNEL_DURATION_SHARE = 0.3738261181394841
E2E_SHARE_STATUS = "unavailable_until_phase_aware_c8_trace_or_empirical_ab"
COMPONENT_REDUCTION_GATE = 0.10
PROSPECTIVE_E2E_GATE = 0.05


@dataclass(frozen=True, order=True)
class Candidate:
    block_h: int
    block_n: int
    num_warps: int
    num_stages: int
    num_kv_splits: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class ExactShape:
    batch_size: int
    context_tokens: int
    query_heads: int = 20
    kv_heads: int = 1
    kv_lora_rank: int = 512
    qk_rope_head_dim: int = 64
    model_value_head_dim: int = 256
    page_size: int = 16
    stock_kv_splits: int = 4

    @property
    def query_width(self) -> int:
        return self.kv_lora_rank + self.qk_rope_head_dim

    @property
    def value_width(self) -> int:
        return self.kv_lora_rank

    def as_dict(self) -> dict[str, int]:
        value = asdict(self)
        value.update(query_width=self.query_width, value_width=self.value_width)
        return value


def exact_shapes() -> tuple[ExactShape, ...]:
    return tuple(
        ExactShape(batch_size=batch_size, context_tokens=context_tokens)
        for batch_size in (1, 8)
        for context_tokens in (8193, 8449, 8705, 8961, 9215)
    )


def generate_candidates() -> list[Candidate]:
    legal_block_stage_pairs = ((16, 1), (16, 2), (16, 3), (32, 1), (32, 2), (64, 1))
    values = {
        Candidate(block_h, block_n, num_warps, num_stages, 4)
        for block_h in (8, 16, 32)
        for block_n, num_stages in legal_block_stage_pairs
        for num_warps in (2, 4, 8)
    }
    values.update(Candidate(16, 32, 4, 2, splits) for splits in (1, 2, 8, 16))
    return sorted(values)


def prospective_e2e_gain(
    component_time_reduction: float, measured_e2e_share: float | None = None
) -> float | None:
    """Return an Amdahl estimate only when a scope-matched E2E share is supplied."""
    if measured_e2e_share is None:
        return None
    if not 0.0 <= measured_e2e_share <= 1.0:
        raise ValueError("measured_e2e_share must be between zero and one")
    return component_time_reduction * measured_e2e_share


def select_promotable_candidate(
    rows: list[dict[str, Any]], measured_e2e_share: float | None = None
) -> dict[str, Any] | None:
    if measured_e2e_share is None:
        return None
    eligible = []
    for row in rows:
        reduction = float(row.get("component_time_reduction", -math.inf))
        e2e = prospective_e2e_gain(reduction, measured_e2e_share)
        if (
            row.get("correctness_pass") is True
            and row.get("hardware_legal") is True
            and reduction >= COMPONENT_REDUCTION_GATE
            and e2e is not None
            and e2e >= PROSPECTIVE_E2E_GATE
        ):
            eligible.append({**row, "prospective_e2e_gain": e2e})
    if not eligible:
        return None
    return max(eligible, key=lambda row: (row["prospective_e2e_gain"], row["component_time_reduction"]))


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def benchmark_cuda(torch, function, warmups: int = 20, repetitions: int = 80) -> dict[str, float]:
    for _ in range(warmups):
        function()
    torch.cuda.synchronize()
    starts = [torch.cuda.Event(enable_timing=True) for _ in range(repetitions)]
    ends = [torch.cuda.Event(enable_timing=True) for _ in range(repetitions)]
    for start, end in zip(starts, ends, strict=True):
        start.record()
        function()
        end.record()
    torch.cuda.synchronize()
    values = [start.elapsed_time(end) * 1000.0 for start, end in zip(starts, ends, strict=True)]
    return {
        "samples": len(values),
        "mean_us": statistics.fmean(values),
        "p50_us": percentile(values, 0.50),
        "p95_us": percentile(values, 0.95),
        "min_us": min(values),
        "max_us": max(values),
    }


def allocate_shape(torch, shape: ExactShape, seed: int):
    torch.manual_seed(seed)
    blocks_per_sequence = math.ceil(shape.context_tokens / shape.page_size)
    total_blocks = shape.batch_size * blocks_per_sequence
    cache = torch.randn(
        total_blocks,
        shape.page_size,
        shape.kv_heads,
        shape.query_width,
        dtype=torch.bfloat16,
        device="cuda",
    )
    query = torch.randn(
        shape.batch_size,
        shape.query_heads,
        shape.query_width,
        dtype=torch.bfloat16,
        device="cuda",
    )
    generator = torch.Generator(device="cuda")
    generator.manual_seed(seed + 17)
    block_table = torch.randperm(total_blocks, generator=generator, dtype=torch.int64, device="cuda").to(
        torch.int32
    ).reshape(
        shape.batch_size, blocks_per_sequence
    )
    sequence_lengths = torch.full(
        (shape.batch_size,), shape.context_tokens, dtype=torch.int32, device="cuda"
    )
    return query, cache, cache[..., : shape.value_width], block_table, sequence_lengths


def reference_attention(
    torch, query, key_cache, value_cache, block_table, sequence_lengths, scale: float
):
    batch, heads, _ = query.shape
    logical_keys = key_cache[block_table].reshape(batch, -1, key_cache.shape[-1])
    logical_values = value_cache[block_table].reshape(batch, -1, value_cache.shape[-1])
    scores = torch.einsum("bhd,btd->bht", query.float(), logical_keys.float()) * scale
    valid_tokens = torch.arange(scores.shape[-1], device=scores.device)[None, :] < sequence_lengths[:, None]
    scores = scores.masked_fill(~valid_tokens[:, None, :], float("-inf"))
    probabilities = torch.softmax(scores, dim=-1)
    output = torch.einsum("bht,btd->bhd", probabilities, logical_values.float())
    lse = torch.logsumexp(scores, dim=-1)
    return output, lse


def run_candidate(torch, kernels, shape: ExactShape, candidate: Candidate, tensors) -> dict[str, Any]:
    query, key_cache, value_cache, block_table, sequence_lengths = tensors
    scale = shape.model_value_head_dim**-0.5
    attention_logits = torch.empty(
        shape.batch_size,
        shape.query_heads,
        candidate.num_kv_splits,
        shape.value_width + 1,
        dtype=torch.float32,
        device="cuda",
    )
    output = torch.zeros(
        shape.batch_size,
        shape.query_heads,
        shape.value_width,
        dtype=query.dtype,
        device="cuda",
    )
    lse = torch.zeros(shape.batch_size, shape.query_heads, dtype=query.dtype, device="cuda")
    grid = (
        shape.batch_size,
        math.ceil(shape.query_heads / min(candidate.block_h, shape.query_heads)),
        candidate.num_kv_splits,
    )

    def stage1():
        kernels._fwd_grouped_kernel_stage1[grid](
            query,
            key_cache,
            value_cache,
            scale,
            block_table,
            sequence_lengths,
            attention_logits,
            block_table.stride(0),
            query.stride(0),
            query.stride(1),
            key_cache.stride(-3),
            key_cache.stride(-2),
            value_cache.stride(-3),
            value_cache.stride(-2),
            attention_logits.stride(0),
            attention_logits.stride(1),
            attention_logits.stride(2),
            kv_group_num=shape.query_heads,
            q_head_num=shape.query_heads,
            BLOCK_DMODEL=shape.kv_lora_rank,
            BLOCK_DPE=shape.qk_rope_head_dim,
            BLOCK_DV=shape.value_width,
            BLOCK_N=candidate.block_n,
            BLOCK_H=candidate.block_h,
            NUM_KV_SPLITS=candidate.num_kv_splits,
            PAGE_SIZE=shape.page_size,
            logit_cap=0.0,
            num_warps=candidate.num_warps,
            num_stages=candidate.num_stages,
            Lk=shape.query_width,
            Lv=shape.value_width,
        )

    def full_attention():
        stage1()
        kernels._decode_softmax_reducev_fwd(
            attention_logits,
            query,
            output,
            lse,
            value_cache,
            sequence_lengths,
            candidate.num_kv_splits,
        )

    stage1()
    full_attention()
    torch.cuda.synchronize()
    reference_output, reference_lse = reference_attention(
        torch, query, key_cache, value_cache, block_table, sequence_lengths, scale
    )
    output_float = output.float()
    lse_float = lse.float()
    output_max_abs = (output_float - reference_output).abs().max().item()
    lse_max_abs = (lse_float - reference_lse).abs().max().item()
    correctness_pass = bool(
        torch.isfinite(output_float).all().item()
        and torch.isfinite(lse_float).all().item()
        and torch.allclose(output_float, reference_output, atol=0.03, rtol=0.03)
        and torch.allclose(lse_float, reference_lse, atol=0.10, rtol=0.03)
    )
    stage1_timing = benchmark_cuda(torch, stage1)
    full_timing = benchmark_cuda(torch, full_attention)
    return {
        "candidate": candidate.as_dict(),
        "shape": shape.as_dict(),
        "hardware_legal": True,
        "correctness_pass": correctness_pass,
        "output_max_abs_error": output_max_abs,
        "lse_max_abs_error": lse_max_abs,
        "stage1_timing": stage1_timing,
        "full_attention_timing": full_timing,
    }


def summarize_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stock = Candidate(16, 32, 4, 2, 4).as_dict()
    stock_rows = {
        (row["shape"]["batch_size"], row["shape"]["context_tokens"]): row
        for row in rows
        if row.get("candidate") == stock and row.get("hardware_legal") is True
    }
    summaries = []
    for candidate in generate_candidates():
        selected = [row for row in rows if row.get("candidate") == candidate.as_dict()]
        legal = len(selected) == len(exact_shapes()) and all(row.get("hardware_legal") is True for row in selected)
        correct = legal and all(row.get("correctness_pass") is True for row in selected)
        b8_reductions = []
        b8_full_reductions = []
        if legal:
            for row in selected:
                if row.get("shape", {}).get("batch_size") != 8:
                    continue
                key = (8, row["shape"]["context_tokens"])
                stock_row = stock_rows.get(key)
                if stock_row is None:
                    continue
                b8_reductions.append(
                    1.0 - row["stage1_timing"]["p50_us"] / stock_row["stage1_timing"]["p50_us"]
                )
                b8_full_reductions.append(
                    1.0 - row["full_attention_timing"]["p50_us"] / stock_row["full_attention_timing"]["p50_us"]
                )
        reduction = min(b8_reductions) if len(b8_reductions) == 5 else None
        full_reduction = min(b8_full_reductions) if len(b8_full_reductions) == 5 else None
        conservative = min(reduction, full_reduction) if reduction is not None and full_reduction is not None else None
        summaries.append(
            {
                "candidate": candidate.as_dict(),
                "hardware_legal": legal,
                "correctness_pass": correct,
                "stage1_time_reduction_b8": reduction,
                "full_attention_time_reduction_b8": full_reduction,
                "component_time_reduction": conservative,
                "e2e_prediction_status": E2E_SHARE_STATUS,
                "prospective_e2e_gain": None,
            }
        )
    return summaries


def execute(seed: int) -> dict[str, Any]:
    import torch
    import vllm.v1.attention.ops.triton_decode_attention as kernels

    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if source_hash != SOURCE_SHA256:
        raise RuntimeError(f"unexpected vLLM decode source {source_hash}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    properties = torch.cuda.get_device_properties(0)
    rows: list[dict[str, Any]] = []
    for shape in exact_shapes():
        tensors = allocate_shape(torch, shape, seed + shape.batch_size)
        for candidate in generate_candidates():
            try:
                rows.append(run_candidate(torch, kernels, shape, candidate, tensors))
            except Exception as error:
                rows.append(
                    {
                        "candidate": candidate.as_dict(),
                        "shape": shape.as_dict(),
                        "hardware_legal": False,
                        "correctness_pass": False,
                        "error_type": type(error).__name__,
                        "error": str(error)[:2000],
                    }
                )
            torch.cuda.empty_cache()
        del tensors
        torch.cuda.empty_cache()
    summaries = summarize_candidates(rows)
    component_candidates = [
        row
        for row in summaries
        if row["hardware_legal"] is True
        and row["correctness_pass"] is True
        and row["component_time_reduction"] is not None
        and row["component_time_reduction"] >= COMPONENT_REDUCTION_GATE
    ]
    component_candidate = max(
        component_candidates, key=lambda row: row["component_time_reduction"], default=None
    )
    stock = next(
        row
        for row in summaries
        if row["candidate"] == Candidate(16, 32, 4, 2, 4).as_dict()
    )
    return {
        "schema_version": 1,
        "seed": seed,
        "source": str(SOURCE),
        "source_sha256": source_hash,
        "unscoped_mixed_trace_kernel_duration_share": UNSCOPED_MIXED_TRACE_KERNEL_DURATION_SHARE,
        "unscoped_share_use": "diagnostic_lead_only_not_an_e2e_or_c8_amhdahl_coefficient",
        "e2e_share_status": E2E_SHARE_STATUS,
        "component_reduction_gate": COMPONENT_REDUCTION_GATE,
        "prospective_e2e_gate": PROSPECTIVE_E2E_GATE,
        "shapes": [shape.as_dict() for shape in exact_shapes()],
        "candidate_count": len(generate_candidates()),
        "device": {
            "name": properties.name,
            "capability": list(torch.cuda.get_device_capability(0)),
            "total_memory_bytes": properties.total_memory,
            "shared_memory_per_block_bytes": properties.shared_memory_per_block,
            "shared_memory_per_block_optin_bytes": getattr(properties, "shared_memory_per_block_optin", None),
        },
        "stock": stock,
        "rows": rows,
        "candidate_summaries": summaries,
        "component_candidate_for_c8_trace": component_candidate,
        "promotable_candidate": None,
        "sweep_pass": stock["hardware_legal"] is True and stock["correctness_pass"] is True,
        "decision": "MEASURE_PHASE_AWARE_C8_THEN_CONSIDER_HOLDOUT" if component_candidate else "STOP_CUSTOM_MLA_LINEAGE",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1234)
    args = parser.parse_args()
    started = time.time()
    result = execute(args.seed)
    result["wall_seconds"] = time.time() - started
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["sweep_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
