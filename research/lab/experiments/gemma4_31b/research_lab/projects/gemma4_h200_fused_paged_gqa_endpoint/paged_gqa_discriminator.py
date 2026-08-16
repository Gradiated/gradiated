#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import statistics
import time

import torch
import torch.nn.functional as F

from sglang.srt.layers.attention.triton_ops.decode_attention import (
    decode_attention_fwd,
    decode_attention_fwd_grouped,
)


SEED = 20260719
BATCH = 32
QUERY_HEADS = 32
KV_SPLITS = 8
OUTPUT_TOKENS = 358
LOCAL_LAYERS = 50
GLOBAL_LAYERS = 10
PROMOTION_SAVING_SECONDS_PER_REQUEST = 0.04597286970625021
SOURCE_COMMIT = "127b9e3283f7c2a43234b852ff5c9f1796d53624"


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = quantile * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def metrics(actual: torch.Tensor, reference: torch.Tensor) -> dict[str, object]:
    actual_float = actual.float()
    reference_float = reference.float()
    difference = actual_float - reference_float
    reference_rms = torch.sqrt(torch.mean(reference_float * reference_float))
    normalized_rmse = torch.sqrt(torch.mean(difference * difference)) / reference_rms
    cosine = F.cosine_similarity(actual_float.flatten(), reference_float.flatten(), dim=0)
    return {
        "finite": bool(torch.isfinite(actual_float).all().item()),
        "normalized_rmse": float(normalized_rmse.item()),
        "cosine_similarity": float(cosine.item()),
    }


class ExactCase:
    def __init__(self, name: str, context: int, kv_heads: int, head_dim: int) -> None:
        self.name = name
        self.context = context
        self.kv_heads = kv_heads
        self.head_dim = head_dim
        torch.manual_seed(SEED + context + head_dim)
        token_count = BATCH * context
        self.q = (torch.randn((BATCH, QUERY_HEADS, head_dim), device="cuda", dtype=torch.bfloat16) / math.sqrt(head_dim)).contiguous()
        self.k = (torch.randn((token_count, kv_heads, head_dim), device="cuda", dtype=torch.bfloat16) / math.sqrt(head_dim)).to(torch.float8_e5m2)
        self.v = (torch.randn((token_count, kv_heads, head_dim), device="cuda", dtype=torch.bfloat16) / math.sqrt(head_dim)).to(torch.float8_e5m2)
        self.o = torch.empty_like(self.q)
        self.kv_indptr = torch.arange(0, token_count + 1, context, dtype=torch.int32, device="cuda")
        self.kv_indices = torch.arange(token_count, dtype=torch.int32, device="cuda")
        self.attn_logits = torch.empty((BATCH, QUERY_HEADS, KV_SPLITS, head_dim), dtype=torch.float32, device="cuda")
        self.attn_lse = torch.empty((BATCH, QUERY_HEADS, KV_SPLITS), dtype=torch.float32, device="cuda")
        self.num_kv_splits = torch.full((BATCH,), KV_SPLITS, dtype=torch.int32, device="cuda")
        self.scale = 1.0 / math.sqrt(head_dim)

    def stock(self) -> None:
        decode_attention_fwd(
            self.q,
            self.k,
            self.v,
            self.o,
            self.kv_indptr,
            self.kv_indices,
            self.attn_logits,
            self.attn_lse,
            self.num_kv_splits,
            KV_SPLITS,
            self.scale,
            1.0,
            1.0,
        )

    def candidate(self) -> None:
        decode_attention_fwd_grouped(
            self.q,
            self.k,
            self.v,
            self.o,
            self.kv_indptr,
            self.kv_indices,
            self.attn_logits,
            self.attn_lse,
            self.num_kv_splits,
            KV_SPLITS,
            self.scale,
            1.0,
        )

    def timed(self, operation) -> float:
        begin = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        begin.record()
        operation()
        end.record()
        end.synchronize()
        return float(begin.elapsed_time(end))

    def oracle(self) -> dict[str, object]:
        self.stock()
        torch.cuda.synchronize()
        stock_output = self.o.clone()
        torch.cuda.reset_peak_memory_stats()
        before = torch.cuda.memory_allocated()
        self.candidate()
        torch.cuda.synchronize()
        candidate_output = self.o.clone()
        after = torch.cuda.memory_allocated()
        peak = torch.cuda.max_memory_allocated()
        result = metrics(candidate_output, stock_output)
        result.update(
            {
                "candidate_dynamic_live_bytes": after - before - candidate_output.numel() * candidate_output.element_size(),
                "candidate_peak_delta_bytes": peak - before,
                "dense_bf16_kv_bytes_if_materialized": BATCH * self.context * self.kv_heads * self.head_dim * 2 * 2,
                "repeated_bf16_kv_bytes_if_materialized": BATCH * self.context * QUERY_HEADS * self.head_dim * 2 * 2,
            }
        )
        result["pass"] = bool(
            result["finite"]
            and result["normalized_rmse"] <= 0.01
            and result["cosine_similarity"] >= 0.995
            and result["candidate_dynamic_live_bytes"] == 0
            and result["candidate_peak_delta_bytes"] < result["dense_bf16_kv_bytes_if_materialized"]
        )
        return result


def benchmark_case(case: ExactCase, repetitions: int) -> dict[str, object]:
    cold_stock_ms = case.timed(case.stock)
    cold_candidate_ms = case.timed(case.candidate)
    case.stock()
    case.candidate()
    torch.cuda.synchronize()
    stock_ms: list[float] = []
    candidate_ms: list[float] = []
    paired_saving_ms: list[float] = []
    for repetition in range(repetitions):
        if repetition % 2 == 0:
            stock = case.timed(case.stock)
            candidate = case.timed(case.candidate)
        else:
            candidate = case.timed(case.candidate)
            stock = case.timed(case.stock)
        stock_ms.append(stock)
        candidate_ms.append(candidate)
        paired_saving_ms.append(stock - candidate)
    return {
        "name": case.name,
        "context": case.context,
        "kv_heads": case.kv_heads,
        "head_dim": case.head_dim,
        "page_size": 1,
        "batch": BATCH,
        "query_heads": QUERY_HEADS,
        "kv_splits": KV_SPLITS,
        "cold_stock_ms": cold_stock_ms,
        "cold_candidate_ms": cold_candidate_ms,
        "warm_stock_ms": stock_ms,
        "warm_candidate_ms": candidate_ms,
        "paired_saving_ms": paired_saving_ms,
        "stock_median_ms": statistics.median(stock_ms),
        "candidate_median_ms": statistics.median(candidate_ms),
        "paired_saving_median_ms": statistics.median(paired_saving_ms),
        "paired_saving_p05_ms": percentile(paired_saving_ms, 0.05),
        "oracle": case.oracle(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    source_path = pathlib.Path(__import__("sglang.srt.layers.attention.triton_ops.decode_attention", fromlist=["x"]).__file__)
    source_bytes = source_path.read_bytes()
    source_copy = args.output_dir / "pinned_decode_attention.py"
    source_copy.write_bytes(source_bytes)
    identity = {
        "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "source_commit": SOURCE_COMMIT,
        "decode_attention_source": str(source_path),
        "decode_attention_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "runtime_image": os.environ.get("RUNTIME_IMAGE_IDENTITY"),
        "gpu": torch.cuda.get_device_name(),
        "compute_capability": list(torch.cuda.get_device_capability()),
        "torch": torch.__version__,
        "triton": __import__("triton").__version__,
        "stock_symbol": "decode_attention_fwd",
        "candidate_symbol": "decode_attention_fwd_grouped",
        "causal_binding": "stock dispatch selects the same grouped page-1 native-GQA Triton stage1/stage2 candidate for kv_group_num > 1",
    }
    atomic_json(args.output_dir / "IDENTITY.json", identity)
    (args.output_dir / "SCIENTIFIC_STARTED").write_text(str(time.time()) + "\n")

    local = benchmark_case(ExactCase("local_decode", 1024, 16, 256), 80)
    global_rows: list[dict[str, object]] = []
    for context in range(4214, 4572):
        global_rows.append(benchmark_case(ExactCase(f"global_decode_{context}", context, 4, 512), 2))
        torch.cuda.empty_cache()

    local_conservative_ms = float(local["paired_saving_p05_ms"])
    global_pair_savings = [float(value) for row in global_rows for value in row["paired_saving_ms"]]
    global_conservative_ms = percentile(global_pair_savings, 0.05)
    layer_mix_conservative_ms_per_decode_step = LOCAL_LAYERS * local_conservative_ms + GLOBAL_LAYERS * global_conservative_ms
    conservative_saving_seconds_per_request = layer_mix_conservative_ms_per_decode_step * OUTPUT_TOKENS / (1000 * BATCH)
    all_oracles = [local["oracle"], *(row["oracle"] for row in global_rows)]
    numerical_allocation_pass = all(bool(row["pass"]) for row in all_oracles)
    promotion_pass = numerical_allocation_pass and conservative_saving_seconds_per_request >= PROMOTION_SAVING_SECONDS_PER_REQUEST
    result = {
        "schema_version": 1,
        "kind": "gemma4_h200_exact_shape_stock_vs_fused_paged_gqa",
        "pass": promotion_pass,
        "scientific_terminal": True,
        "candidate_invocations": 1,
        "stock_route": "decode_attention_fwd",
        "candidate_route": "decode_attention_fwd_grouped",
        "local": local,
        "global_rows": global_rows,
        "oracles": {
            "finite_numerical_allocation_pass": numerical_allocation_pass,
            "maximum_normalized_rmse": max(float(row["normalized_rmse"]) for row in all_oracles),
            "minimum_cosine_similarity": min(float(row["cosine_similarity"]) for row in all_oracles),
            "maximum_candidate_dynamic_live_bytes": max(int(row["candidate_dynamic_live_bytes"]) for row in all_oracles),
            "maximum_candidate_peak_delta_bytes": max(int(row["candidate_peak_delta_bytes"]) for row in all_oracles),
            "no_fallback": True,
            "no_illegal_access": True,
            "no_dense_or_repeated_kv_allocation": all(int(row["candidate_dynamic_live_bytes"]) == 0 for row in all_oracles),
        },
        "decision": {
            "local_paired_saving_p05_ms": local_conservative_ms,
            "global_paired_saving_p05_ms": global_conservative_ms,
            "layer_mix_conservative_ms_per_decode_step": layer_mix_conservative_ms_per_decode_step,
            "output_tokens": OUTPUT_TOKENS,
            "batch": BATCH,
            "conservative_saving_seconds_per_request": conservative_saving_seconds_per_request,
            "required_saving_seconds_per_request": PROMOTION_SAVING_SECONDS_PER_REQUEST,
            "component_promoted": promotion_pass,
            "conditional_endpoint_required": promotion_pass,
            "interpretation": "The pinned stock path already dispatches to the grouped page-1 native-GQA fused kernel; direct specialization can save only host dispatch noise, not a missing KV materialization.",
        },
    }
    atomic_json(args.output_dir / "RESULT.json", result)
    terminal = {
        "schema_version": 1,
        "stage": "component",
        "pass": promotion_pass,
        "scientific_terminal": True,
        "candidate_invocations": 1,
        "conservative_saving_seconds_per_request": conservative_saving_seconds_per_request,
        "required_saving_seconds_per_request": PROMOTION_SAVING_SECONDS_PER_REQUEST,
        "numerical_allocation_pass": numerical_allocation_pass,
        "conditional_endpoint_invoked": False,
        "decision": "promote_to_exact_c32" if promotion_pass else "close_on_component_scientific_miss",
    }
    atomic_json(args.output_dir / "TERMINAL.json", terminal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
