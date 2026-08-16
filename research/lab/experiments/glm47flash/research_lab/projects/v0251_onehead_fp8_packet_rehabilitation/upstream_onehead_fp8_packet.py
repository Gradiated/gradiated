#!/usr/bin/env python3
"""Execution-equivalent vLLM 0.25.1 one-head FP8 MLA packet.

The no-CUDA self-test exercises every deterministic contract.  The CUDA path
calls the pinned upstream writer, stage-1 MLA kernel, and upstream reduction;
it is intentionally not a custom kernel or a runtime survey.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

COMMIT = "752a3a504485790a2e8491cacbb35c137339ad34"
IMAGE = "vllm/vllm-openai:v0.25.1-x86_64-cu129@sha256:94a0aff7a289f23bcefa189d11841e487991405d86da782a63bf6e5f95d0d39a"
PAGE_SIZE, KV_HEADS, CACHE_WIDTH, VALUE_WIDTH = 16, 1, 576, 512
QUERY_HEADS, FP8_MAX = 20, 448.0
ATTENTION_SCALE = 256.0 ** -0.5
EXPECTED_SOURCES = {
    "vllm/v1/attention/backends/mla/triton_mla.py": "5e9aa13eca7ce718ce0648f11454bb0e0e98e9f5da40ee22bd8d0b05f4ba1d03",
    "vllm/v1/attention/ops/triton_reshape_and_cache_flash.py": "fd47641f8e62590516ca9596c52a80f8dab4204f2daf982d15a30a48d5f07d9c",
    "vllm/v1/attention/ops/triton_decode_attention.py": "b9823c65eba22d76abf64dad7d7d16a950f67471c86d6cb5b3e983aaf14381ac",
    "vllm/v1/worker/gpu_model_runner.py": "6c92ded8468f44d6df863a617ce588f132fa6df7031feecc0cc421702a41610e",
}


def pages_for(context: int) -> int:
    return math.ceil(context / PAGE_SIZE)


def slot_mapping(batch: int, context: int, table: list[list[int]]) -> list[int]:
    """Map a full page per sequence; padded tail slots are never truncated."""
    blocks = pages_for(context)
    if len(table) != batch or any(len(row) != blocks for row in table):
        raise ValueError("block table does not match per-sequence geometry")
    return [block * PAGE_SIZE + offset for row in table for block in row for offset in range(PAGE_SIZE)]


def allocation_bytes(batch: int, context: int, dtype_bytes: int = 1, scale_count: int = 2) -> int:
    pages = batch * pages_for(context)
    data = pages * PAGE_SIZE * KV_HEADS * CACHE_WIDTH * dtype_bytes
    return data + scale_count * 4


def select_kv_splits(sm_count: int, batch: int, context: int) -> int:
    """Mirror upstream L40S selection: 32 for this exact 142-SM workload."""
    if sm_count != 142:
        raise ValueError("packet is admitted only for the L40S 142-SM target")
    if batch not in (1, 8, 32) or context not in (8193, 9215):
        raise ValueError("unregistered exact geometry")
    return 32


def finite_comparison(output, lse, reference_output, reference_lse, saturation: bool) -> bool:
    """A non-self-failing finite BF16/FP8 comparison predicate."""
    if isinstance(output, (list, tuple)):
        def close(actual, expected, atol, rtol):
            return all(math.isfinite(a) and math.isfinite(e) and abs(a - e) <= atol + rtol * abs(e) for a, e in zip(actual, expected, strict=True))
        return not saturation and close(output, reference_output, .03, .03) and close(lse, reference_lse, .10, .03)
    import torch
    return bool(
        not saturation
        and torch.isfinite(output.float()).all().item()
        and torch.isfinite(lse.float()).all().item()
        and torch.allclose(output.float(), reference_output.float(), atol=0.03, rtol=0.03)
        and torch.allclose(lse.float(), reference_lse.float(), atol=0.10, rtol=0.03)
    )


def self_test() -> dict:
    table = [[7, 2], [4, 9]]
    slots = slot_mapping(2, 17, table)
    assert len(slots) == 64 and slots[16] == 32 and slots[-1] == 159
    assert allocation_bytes(32, 8193) == 32 * pages_for(8193) * 16 * 576 + 8
    assert math.isclose(ATTENTION_SCALE, 256 ** -0.5)
    assert select_kv_splits(142, 32, 9215) == 32
    assert select_kv_splits(142, 1, 8193) == 32
    assert finite_comparison([1.0, 1.0], [1.0], [1.0, 1.0], [1.0], False)
    assert not finite_comparison([1.0, 1.0], [1.0], [1.0, 1.0], [1.0], True)
    return {"self_test": True, "slot_count": len(slots), "b32_c8193_bytes": allocation_bytes(32, 8193), "l40s_splits": 32}


def percentile(values: list[float], q: float) -> float:
    return sorted(values)[max(0, min(len(values) - 1, math.ceil(q * len(values)) - 1))]


def timed(torch, fn, warmups: int = 20, repetitions: int = 60) -> dict:
    for _ in range(warmups):
        fn()
    torch.cuda.synchronize()
    values = []
    for _ in range(repetitions):
        start, end = torch.cuda.Event(True), torch.cuda.Event(True)
        start.record(); fn(); end.record(); torch.cuda.synchronize()
        values.append(start.elapsed_time(end) * 1000)
    return {"samples": len(values), "mean_us": statistics.fmean(values), "p50_us": percentile(values, .5), "p95_us": percentile(values, .95)}


def run_cuda(output_path: Path, seed: int) -> None:
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable: packet self-test remains valid, CUDA science does not")
    root = Path("/usr/local/lib/python3.12/dist-packages")
    source_paths = {str(root / path): want for path, want in EXPECTED_SOURCES.items()}
    for path, want in source_paths.items():
        got = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        if got != want:
            raise RuntimeError(f"v0.25.1 source identity mismatch {path}: {got}")
    from vllm.v1.attention.ops.triton_reshape_and_cache_flash import triton_reshape_and_cache_flash
    from vllm.v1.attention.ops import triton_decode_attention as kernels
    rows = []
    for batch in (1, 8, 32):
        for context in (8193, 9215):
            blocks = pages_for(context); total_blocks = batch * blocks; padded = total_blocks * PAGE_SIZE
            torch.manual_seed(seed + batch + context)
            key = torch.randn(padded, KV_HEADS, CACHE_WIDTH, dtype=torch.bfloat16, device="cuda")
            value = key[..., :VALUE_WIDTH]
            query = torch.randn(batch, QUERY_HEADS, CACHE_WIDTH, dtype=torch.bfloat16, device="cuda")
            gen = torch.Generator(device="cuda"); gen.manual_seed(seed + 7 + batch)
            table = torch.randperm(total_blocks, generator=gen, device="cuda").reshape(batch, blocks).to(torch.int32)
            slots = torch.tensor(slot_mapping(batch, context, table.cpu().tolist()), dtype=torch.int32, device="cuda")
            for mode in ("bf16", "fp8"):
                cache_dtype = torch.bfloat16 if mode == "bf16" else torch.float8_e4m3fn
                cache = torch.empty(total_blocks, PAGE_SIZE, KV_HEADS, CACHE_WIDTH, dtype=cache_dtype, device="cuda")
                vcache = cache[..., :VALUE_WIDTH]
                kscale = torch.tensor(max(1e-6, key.float().abs().max().item() / FP8_MAX), dtype=torch.float32, device="cuda") if mode == "fp8" else torch.ones((), device="cuda")
                vscale = kscale.clone()
                def writer():
                    triton_reshape_and_cache_flash(key, value, cache, vcache, slots, mode if mode == "bf16" else "fp8_e4m3", kscale, vscale)
                writer(); torch.cuda.synchronize()
                logits = torch.empty(batch, QUERY_HEADS, 32, VALUE_WIDTH + 1, dtype=torch.float32, device="cuda")
                out = torch.zeros(batch, QUERY_HEADS, VALUE_WIDTH, dtype=torch.bfloat16, device="cuda")
                lse = torch.zeros(batch, QUERY_HEADS, dtype=torch.bfloat16, device="cuda")
                lengths = torch.full((batch,), context, dtype=torch.int32, device="cuda")
                grid = (batch, math.ceil(QUERY_HEADS / 16), 32)
                def stage():
                    kernels._fwd_grouped_kernel_stage1[grid](query, cache, vcache, ATTENTION_SCALE, table, lengths, logits, table.stride(0), query.stride(0), query.stride(1), cache.stride(-3), cache.stride(-2), vcache.stride(-3), vcache.stride(-2), logits.stride(0), logits.stride(1), logits.stride(2), kv_group_num=QUERY_HEADS, q_head_num=QUERY_HEADS, BLOCK_DMODEL=VALUE_WIDTH, BLOCK_DPE=64, BLOCK_DV=VALUE_WIDTH, BLOCK_N=32, BLOCK_H=16, NUM_KV_SPLITS=32, PAGE_SIZE=PAGE_SIZE, logit_cap=0.0, num_warps=4, num_stages=2, Lk=CACHE_WIDTH, Lv=VALUE_WIDTH)
                def reduction():
                    kernels._decode_softmax_reducev_fwd(logits, query, out, lse, vcache, lengths, 32)
                def full():
                    stage(); reduction()
                stage(); reduction(); torch.cuda.synchronize()
                logical_k = cache[table].reshape(batch, blocks * PAGE_SIZE, CACHE_WIDTH).float()
                logical_v = vcache[table].reshape(batch, blocks * PAGE_SIZE, VALUE_WIDTH).float()
                if mode == "fp8":
                    logical_k = logical_k * kscale
                    logical_v = logical_v * vscale
                scores = torch.einsum("bhd,btd->bht", query.float(), logical_k) * ATTENTION_SCALE
                valid = torch.arange(blocks * PAGE_SIZE, device="cuda")[None, :] < context
                scores = scores.masked_fill(~valid[:, None, :], float("-inf"))
                ref_out = torch.einsum("bht,btd->bhd", scores.softmax(-1), logical_v)
                ref_lse = torch.logsumexp(scores, dim=-1)
                saturation = bool(mode == "fp8" and (cache.float().abs() >= FP8_MAX).any().item())
                rows.append({"batch": batch, "context": context, "mode": mode, "allocated_bytes": allocation_bytes(batch, context, 1 if mode == "fp8" else 2), "splits": 32, "attention_scale": ATTENTION_SCALE, "writer": timed(torch, writer), "attention_stage": timed(torch, stage), "reduction": timed(torch, reduction), "attention_full": timed(torch, full), "saturation": saturation, "output_max_abs_error": (out.float() - ref_out).abs().max().item(), "lse_max_abs_error": (lse.float() - ref_lse).abs().max().item(), "numerical_pass": finite_comparison(out, lse, ref_out, ref_lse, saturation)})
    checks = []
    for context in (8193, 9215):
        bf16 = next(row for row in rows if row["batch"] == 32 and row["context"] == context and row["mode"] == "bf16")
        fp8 = next(row for row in rows if row["batch"] == 32 and row["context"] == context and row["mode"] == "fp8")
        checks.append({"context": context, "bytes_exact": fp8["allocated_bytes"] == allocation_bytes(32, context), "numerical_pass": fp8["numerical_pass"], "writer_improvement": 1 - fp8["writer"]["p50_us"] / bf16["writer"]["p50_us"], "stage_improvement": 1 - fp8["attention_stage"]["p50_us"] / bf16["attention_stage"]["p50_us"], "full_improvement": 1 - fp8["attention_full"]["p50_us"] / bf16["attention_full"]["p50_us"], "p95_no_regression": fp8["attention_full"]["p95_us"] <= bf16["attention_full"]["p95_us"]})
    sweep_pass = all(row["numerical_pass"] and not row["saturation"] for row in rows) and all(check["bytes_exact"] and check["stage_improvement"] >= .10 and check["full_improvement"] >= .10 and check["p95_no_regression"] for check in checks)
    result = {"schema_version": 2, "sweep_pass": sweep_pass, "decision": "UPSTREAM_ONEHEAD_FP8_COMPONENT_PASS" if sweep_pass else "UPSTREAM_ONEHEAD_FP8_COMPONENT_CLOSE", "commit": COMMIT, "image": IMAGE, "geometry": {"page_size": PAGE_SIZE, "kv_heads": KV_HEADS, "cache_width": CACHE_WIDTH, "value_width": VALUE_WIDTH, "query_heads": QUERY_HEADS, "splits": 32}, "checks": checks, "rows": rows}
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--self-test", action="store_true"); parser.add_argument("--output", type=Path); parser.add_argument("--seed", type=int, default=1234)
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), sort_keys=True)); return 0
    if args.output is None: parser.error("--output is required without --self-test")
    run_cuda(args.output, args.seed); return 0


if __name__ == "__main__":
    raise SystemExit(main())
