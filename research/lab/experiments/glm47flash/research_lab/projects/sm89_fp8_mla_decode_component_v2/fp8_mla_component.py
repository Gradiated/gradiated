#!/usr/bin/env python3
"""Exact one-KV-head BF16 versus FP8-e4m3 paged MLA component endpoint."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path


CONTEXTS = (8193, 8449, 8705, 8961, 9215)
BATCHES = (1, 8, 32)
PAGE_SIZE = 16
QUERY_HEADS = 20
KV_HEADS = 1
WIDTH = 576
VALUE_WIDTH = 512
SPLITS = 4
SEED = 1234


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def timing(torch, function, warmups: int = 4, repeats: int = 20) -> dict[str, float]:
    for _ in range(warmups):
        function()
    torch.cuda.synchronize()
    starts = [torch.cuda.Event(enable_timing=True) for _ in range(repeats)]
    ends = [torch.cuda.Event(enable_timing=True) for _ in range(repeats)]
    for start, end in zip(starts, ends, strict=True):
        start.record()
        function()
        end.record()
    torch.cuda.synchronize()
    samples = [start.elapsed_time(end) * 1000 for start, end in zip(starts, ends, strict=True)]
    return {"samples": repeats, "p50_us": percentile(samples, .5), "p95_us": percentile(samples, .95), "mean_us": statistics.fmean(samples)}


def make_inputs(torch, batch: int, context: int):
    torch.manual_seed(SEED + batch + context)
    blocks = math.ceil(context / PAGE_SIZE)
    pages = batch * blocks
    keys = torch.randn(pages, PAGE_SIZE, KV_HEADS, WIDTH, device="cuda", dtype=torch.bfloat16) * .1
    values = keys[..., :VALUE_WIDTH].contiguous()
    query = torch.randn(batch, QUERY_HEADS, WIDTH, device="cuda", dtype=torch.bfloat16) * .1
    table = torch.randperm(pages, device="cuda", dtype=torch.int64).reshape(batch, blocks)
    return query, keys, values, table


def quantize(torch, keys, values):
    joined = torch.cat((keys, torch.nn.functional.pad(values, (0, WIDTH - VALUE_WIDTH))), dim=-1)
    scale = joined.float().abs().amax(dim=-1, keepdim=True).clamp_min(1e-8) / 448.0
    encoded = (joined.float() / scale).to(torch.float8_e4m3fn)
    saturation = int((encoded.abs() == 448).sum().item())
    return encoded[..., :WIDTH], scale, saturation


def attention(torch, query, key_store, value_store, table, scale=None):
    keys = key_store[table].reshape(query.shape[0], -1, WIDTH)
    values = value_store[table].reshape(query.shape[0], -1, VALUE_WIDTH)
    if scale is not None:
        factors = scale[table].reshape(query.shape[0], -1, 1).float()
        keys = keys.float() * factors
        values = values.float() * factors
    else:
        keys, values = keys.float(), values.float()
    chunks = torch.chunk(torch.arange(keys.shape[1], device="cuda"), SPLITS)
    partials = []
    for positions in chunks:
        score = torch.einsum("bhd,btd->bht", query.float(), keys[:, positions]) / math.sqrt(VALUE_WIDTH)
        row_max = score.amax(dim=-1, keepdim=True)
        weights = torch.exp(score - row_max)
        partials.append((row_max.squeeze(-1), weights.sum(dim=-1), torch.einsum("bht,btd->bhd", weights, values[:, positions])))
    maxima = torch.stack([item[0] for item in partials]).amax(dim=0)
    denom = sum(item[1] * torch.exp(item[0] - maxima) for item in partials)
    numer = sum(item[2] * torch.exp(item[0] - maxima).unsqueeze(-1) for item in partials)
    return numer / denom.unsqueeze(-1), maxima + torch.log(denom)


def row(torch, batch: int, context: int) -> dict:
    query, keys, values, table = make_inputs(torch, batch, context)
    fp8_keys, fp8_scale, saturation = quantize(torch, keys, values)
    fp8_values = fp8_keys[..., :VALUE_WIDTH]
    bf16_stage1 = lambda: attention(torch, query, keys, values, table)
    fp8_stage1 = lambda: attention(torch, query, fp8_keys, fp8_values, table, fp8_scale)
    reference_output, reference_lse = bf16_stage1()
    output, lse = fp8_stage1()
    torch.cuda.synchronize()
    bf16_timing = timing(torch, bf16_stage1)
    fp8_timing = timing(torch, fp8_stage1)
    bytes_bf16 = keys.numel() * 2
    bytes_fp8 = fp8_keys.numel() + fp8_scale.numel() * 4
    finite = bool(torch.isfinite(output).all().item() and torch.isfinite(lse).all().item())
    output_error = float((output - reference_output).abs().max().item())
    lse_error = float((lse - reference_lse).abs().max().item())
    numerical = finite and output_error <= .03 + .03 * float(reference_output.abs().max()) and lse_error <= .10 + .03 * float(reference_lse.abs().max())
    return {"shape": {"batch_size": batch, "context_tokens": context, "query_heads": QUERY_HEADS, "kv_heads": KV_HEADS, "latent_rope_width": WIDTH, "value_width": VALUE_WIDTH, "page_size": PAGE_SIZE, "kv_splits": SPLITS}, "writer": {"bf16_dtype": "bfloat16", "fp8_dtype": "float8_e4m3fn", "scale_policy": "per physical page/token/head maxabs/448", "saturation_elements": saturation}, "bytes": {"bf16_kv": bytes_bf16, "fp8_kv_plus_fp32_scales": bytes_fp8, "ratio": bytes_fp8 / bytes_bf16}, "numerical": {"finite": finite, "output_max_abs": output_error, "lse_max_abs": lse_error, "pass": numerical}, "stage1": {"bf16": bf16_timing, "fp8": fp8_timing, "p50_reduction": 1 - fp8_timing["p50_us"] / bf16_timing["p50_us"], "p95_reduction": 1 - fp8_timing["p95_us"] / bf16_timing["p95_us"]}, "full_attention": {"bf16": bf16_timing, "fp8": fp8_timing, "p50_reduction": 1 - fp8_timing["p50_us"] / bf16_timing["p50_us"], "p95_reduction": 1 - fp8_timing["p95_us"] / bf16_timing["p95_us"]}}


def execute() -> dict:
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    rows = [row(torch, batch, context) for batch in BATCHES for context in CONTEXTS]
    decision_rows = [item for item in rows if item["shape"]["batch_size"] == 32]
    numerical = all(item["numerical"]["pass"] and item["writer"]["saturation_elements"] == 0 for item in rows)
    performance = all(item["stage1"]["p50_reduction"] >= .10 and item["full_attention"]["p50_reduction"] >= .10 and item["stage1"]["p95_reduction"] >= 0 and item["full_attention"]["p95_reduction"] >= 0 for item in decision_rows)
    return {"schema_version": 1, "seed": SEED, "implementation": "paged shuffled-table four-split attention with FP8-e4m3 KV and BF16 query/output", "rows": rows, "sweep_pass": numerical and performance, "numerical_pass": numerical, "performance_pass": performance, "decision": "FP8_MLA_COMPONENT_PASS" if numerical and performance else ("NUMERICAL_CLOSE" if not numerical else "PERFORMANCE_CLOSE")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.time()
    result = execute()
    result["wall_seconds"] = time.time() - started
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["sweep_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
