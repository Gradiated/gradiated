#!/usr/bin/env python3
import argparse
import hashlib
import inspect
import json
import math
import os
import statistics
import subprocess
import time
import traceback
from pathlib import Path

import torch
import flashinfer
from flashinfer.decode import trtllm_batch_decode_with_kv_cache
from sglang.srt.layers.attention.triton_ops.decode_attention import decode_attention_fwd
from sglang.srt.layers.attention.triton_ops.extend_attention import extend_attention_fwd


HIDDEN = 5376
QUERY_HEADS = 32
KV_HEADS = 4
CURRENT_DIM = 512
CANDIDATE_DIM = 256
GLOBAL_LAYERS = 10
CONCURRENCY = 32
PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
CACHED_PROMPT_FRACTION = 0.127
PEAK_CONTEXT = 4571
PAGE_SIZE = 64
CHUNK = 2048
MINIMUM_SAVINGS = 0.04597286970625021
CANONICAL_SERVICE_SECONDS = 0.9194573941250042
SEED = 41


def atomic_json(path: Path, value: dict) -> None:
    part = path.with_suffix(path.suffix + ".part")
    with part.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(part, path)


def source_identity(symbol) -> dict:
    source = inspect.getsource(symbol).encode()
    return {
        "symbol": f"{symbol.__module__}.{symbol.__name__}",
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "source_file": inspect.getsourcefile(symbol),
    }


def cuda_ms(call, warmup: int, repeats: int) -> tuple[float, list[float]]:
    for _ in range(warmup):
        call()
    torch.cuda.synchronize()
    rows = []
    for _ in range(repeats):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        call()
        end.record()
        end.synchronize()
        rows.append(float(start.elapsed_time(end)))
    return statistics.median(rows), rows


def finite_nonzero(tensor: torch.Tensor) -> dict:
    view = tensor.float()
    return {
        "finite": bool(torch.isfinite(view).all()),
        "nonzero": bool(view.abs().max() > 1e-6),
        "checksum": float(view[: min(view.shape[0], 8)].sum()),
    }


def projection_rows(dim: int) -> list[dict]:
    rows = []
    torch.manual_seed(SEED + dim)
    shapes = (
        ("qkv_prompt_chunk", CHUNK, HIDDEN, (QUERY_HEADS + 2 * KV_HEADS) * dim),
        ("o_prompt_chunk", CHUNK, QUERY_HEADS * dim, HIDDEN),
        ("qkv_decode_step", CONCURRENCY, HIDDEN, (QUERY_HEADS + 2 * KV_HEADS) * dim),
        ("o_decode_step", CONCURRENCY, QUERY_HEADS * dim, HIDDEN),
    )
    for name, m, k, n in shapes:
        x = torch.randn((m, k), device="cuda", dtype=torch.bfloat16) * 0.02
        w = torch.randn((k, n), device="cuda", dtype=torch.bfloat16) * 0.02
        out = torch.empty((m, n), device="cuda", dtype=torch.bfloat16)

        def call():
            torch.mm(x, w, out=out)

        p50, raw = cuda_ms(call, 3, 9)
        rows.append(
            {
                "component": name,
                "head_dim": dim,
                "input_shape": list(x.shape),
                "weight_shape": list(w.shape),
                "output_shape": list(out.shape),
                "dtype": "bfloat16",
                "p50_ms": p50,
                "raw_ms": raw,
                "output": finite_nonzero(out),
            }
        )
        del x, w, out
        torch.cuda.empty_cache()
    return rows


def prompt_attention_row(dim: int) -> dict:
    torch.manual_seed(SEED + 10_000 + dim)
    prefix = round(PROMPT_TOKENS * CACHED_PROMPT_FRACTION)
    extend = PROMPT_TOKENS - prefix
    total_extend = CONCURRENCY * extend
    total_prefix = CONCURRENCY * prefix
    q = torch.randn((total_extend, QUERY_HEADS, dim), device="cuda", dtype=torch.bfloat16) * 0.02
    k = torch.randn((total_extend, KV_HEADS, dim), device="cuda", dtype=torch.bfloat16) * 0.02
    v = torch.randn((total_extend, KV_HEADS, dim), device="cuda", dtype=torch.bfloat16) * 0.02
    out = torch.empty_like(q)
    k_buffer = (torch.randn((total_prefix, KV_HEADS, dim), device="cuda", dtype=torch.bfloat16) * 0.02).to(torch.float8_e5m2)
    v_buffer = (torch.randn((total_prefix, KV_HEADS, dim), device="cuda", dtype=torch.bfloat16) * 0.02).to(torch.float8_e5m2)
    qo_indptr = torch.arange(CONCURRENCY + 1, device="cuda", dtype=torch.int32) * extend
    kv_indptr = torch.arange(CONCURRENCY + 1, device="cuda", dtype=torch.int32) * prefix
    kv_indices = torch.arange(total_prefix, device="cuda", dtype=torch.int64)

    def call():
        extend_attention_fwd(
            q,
            k,
            v,
            out,
            k_buffer,
            v_buffer,
            qo_indptr,
            kv_indptr,
            kv_indices,
            None,
            True,
            None,
            extend,
            1.0,
            1.0,
            sm_scale=dim**-0.5,
        )

    p50, raw = cuda_ms(call, 2, 7)
    result = {
        "component": "prompt_attention_triton",
        "head_dim": dim,
        "query_shape": list(q.shape),
        "kv_shape": list(k.shape),
        "batch": CONCURRENCY,
        "context": PROMPT_TOKENS,
        "cached_prefix_tokens": prefix,
        "fresh_extend_tokens": extend,
        "layout": "native_gqa_exact_cached_extend_with_e5m2_prefix",
        "prefix_kv_dtype": str(k_buffer.dtype),
        "kv_repeated": False,
        "p50_ms": p50,
        "raw_ms": raw,
        "output": finite_nonzero(out),
    }
    del q, k, v, out, k_buffer, v_buffer, qo_indptr, kv_indptr, kv_indices
    torch.cuda.empty_cache()
    return result


def make_linear_fp8_cache(dim: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    total = CONCURRENCY * PEAK_CONTEXT
    torch.manual_seed(SEED + 20_000 + dim)
    k = (torch.randn((total, KV_HEADS, dim), device="cuda", dtype=torch.bfloat16) * 0.02).to(torch.float8_e5m2)
    v = (torch.randn((total, KV_HEADS, dim), device="cuda", dtype=torch.bfloat16) * 0.02).to(torch.float8_e5m2)
    indptr = torch.arange(CONCURRENCY + 1, device="cuda", dtype=torch.int32) * PEAK_CONTEXT
    indices = torch.arange(total, device="cuda", dtype=torch.int64)
    return k, v, indptr, indices


def triton_decode_row(dim: int) -> dict:
    k, v, indptr, indices = make_linear_fp8_cache(dim)
    torch.manual_seed(SEED + 30_000 + dim)
    q = torch.randn((CONCURRENCY, QUERY_HEADS, dim), device="cuda", dtype=torch.bfloat16) * 0.02
    out = torch.empty_like(q)
    max_splits = 8
    logits = torch.empty((CONCURRENCY, QUERY_HEADS, max_splits, dim), device="cuda", dtype=torch.float32)
    lse = torch.empty((CONCURRENCY, QUERY_HEADS, max_splits), device="cuda", dtype=torch.float32)
    splits = torch.full((CONCURRENCY,), max_splits, device="cuda", dtype=torch.int32)

    def call():
        decode_attention_fwd(
            q,
            k,
            v,
            out,
            indptr,
            indices,
            logits,
            lse,
            splits,
            max_splits,
            dim**-0.5,
            1.0,
            1.0,
        )

    p50, raw = cuda_ms(call, 3, 11)
    result = {
        "component": "decode_attention_triton",
        "head_dim": dim,
        "query_shape": list(q.shape),
        "kv_shape": list(k.shape),
        "context": PEAK_CONTEXT,
        "layout": "native_gqa_linear_token_pool",
        "kv_dtype": str(k.dtype),
        "kv_repeated": False,
        "num_kv_splits": max_splits,
        "p50_ms": p50,
        "raw_ms": raw,
        "output": finite_nonzero(out),
    }
    del q, k, v, out, logits, lse, splits, indptr, indices
    torch.cuda.empty_cache()
    return result


def make_paged_fp8_cache(dim: int, batch: int = CONCURRENCY):
    pages_per_request = math.ceil(PEAK_CONTEXT / PAGE_SIZE)
    pages = batch * pages_per_request
    torch.manual_seed(SEED + 40_000 + dim + batch)
    k = (torch.randn((pages, KV_HEADS, PAGE_SIZE, dim), device="cuda", dtype=torch.bfloat16) * 0.02).to(torch.float8_e5m2)
    v = (torch.randn((pages, KV_HEADS, PAGE_SIZE, dim), device="cuda", dtype=torch.bfloat16) * 0.02).to(torch.float8_e5m2)
    table = torch.arange(pages, device="cuda", dtype=torch.int32).reshape(batch, pages_per_request)
    lengths = torch.full((batch,), PEAK_CONTEXT, device="cuda", dtype=torch.int32)
    return k, v, table, lengths


def xqa_oracle(q: torch.Tensor, k: torch.Tensor, v: torch.Tensor, candidate: torch.Tensor) -> dict:
    pages_per_request = math.ceil(PEAK_CONTEXT / PAGE_SIZE)
    context_k = k[:pages_per_request].permute(0, 2, 1, 3).reshape(-1, KV_HEADS, CANDIDATE_DIM)[:PEAK_CONTEXT].float()
    context_v = v[:pages_per_request].permute(0, 2, 1, 3).reshape(-1, KV_HEADS, CANDIDATE_DIM)[:PEAK_CONTEXT].float()
    head_to_kv = torch.arange(QUERY_HEADS, device="cuda") // (QUERY_HEADS // KV_HEADS)
    qf = q[0].float()
    scores = torch.einsum("hd,thd->ht", qf, context_k[:, head_to_kv]) * (CANDIDATE_DIM**-0.5)
    reference = torch.einsum("ht,thd->hd", torch.softmax(scores, dim=-1), context_v[:, head_to_kv])
    observed = candidate[0].float()
    cosine = float(torch.nn.functional.cosine_similarity(observed.flatten(), reference.flatten(), dim=0))
    nrmse = float(torch.linalg.vector_norm(observed - reference) / torch.linalg.vector_norm(reference).clamp_min(1e-12))
    return {
        "reference": "straightforward native-GQA softmax over dequantized page-64 E5M2 cache",
        "finite": bool(torch.isfinite(observed).all()),
        "cosine_similarity": cosine,
        "normalized_rmse": nrmse,
        "pass": bool(cosine >= 0.99 and nrmse <= 0.05),
    }


def xqa_decode_row() -> dict:
    dim = CANDIDATE_DIM
    k, v, table, lengths = make_paged_fp8_cache(dim)
    torch.manual_seed(SEED + 50_000)
    q = torch.randn((CONCURRENCY, QUERY_HEADS, dim), device="cuda", dtype=torch.bfloat16) * 0.02
    out = torch.empty_like(q)
    workspace = torch.zeros((128 * 1024 * 1024,), device="cuda", dtype=torch.uint8)

    def call():
        trtllm_batch_decode_with_kv_cache(
            query=q,
            kv_cache=(k, v),
            workspace_buffer=workspace,
            block_tables=table,
            seq_lens=lengths,
            max_seq_len=PEAK_CONTEXT,
            bmm1_scale=dim**-0.5,
            bmm2_scale=1.0,
            window_left=-1,
            out=out,
            out_dtype=torch.bfloat16,
            kv_layout="HND",
            backend="xqa",
        )

    call()
    torch.cuda.synchronize()
    first = out.clone()
    call()
    torch.cuda.synchronize()
    deterministic_max_abs = float((out.float() - first.float()).abs().max())
    p50, raw = cuda_ms(call, 2, 11)

    q1 = q[:1].clone()
    k1, v1, table1, lengths1 = make_paged_fp8_cache(dim, batch=1)
    out1 = torch.empty_like(q1)
    trtllm_batch_decode_with_kv_cache(
        query=q1,
        kv_cache=(k1, v1),
        workspace_buffer=workspace,
        block_tables=table1,
        seq_lens=lengths1,
        max_seq_len=PEAK_CONTEXT,
        bmm1_scale=dim**-0.5,
        bmm2_scale=1.0,
        out=out1,
        out_dtype=torch.bfloat16,
        kv_layout="HND",
        backend="xqa",
    )
    torch.cuda.synchronize()
    oracle = xqa_oracle(q1, k1, v1, out1)

    with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA]) as prof:
        call()
        torch.cuda.synchronize()
    events = sorted({event.key for event in prof.key_averages() if "xqa" in event.key.lower() or "attention" in event.key.lower()})
    result = {
        "component": "decode_attention_trtllm_flashinfer_xqa",
        "head_dim": dim,
        "query_shape": list(q.shape),
        "kv_shape": list(k.shape),
        "block_table_shape": list(table.shape),
        "context": PEAK_CONTEXT,
        "page_size": PAGE_SIZE,
        "kv_heads": KV_HEADS,
        "query_heads": QUERY_HEADS,
        "layout": "HND_native_gqa_page64",
        "kv_dtype": str(k.dtype),
        "kv_repeated": False,
        "requested_backend": "xqa",
        "profiler_xqa_events": events,
        "p50_ms": p50,
        "raw_ms": raw,
        "output": finite_nonzero(out),
        "deterministic_max_abs": deterministic_max_abs,
        "oracle": oracle,
    }
    del q, k, v, table, lengths, out, workspace, q1, k1, v1, table1, lengths1, out1
    torch.cuda.empty_cache()
    return result


def kv_write_rows(dim: int) -> list[dict]:
    rows = []
    torch.manual_seed(SEED + 60_000 + dim)
    for name, tokens in (("kv_write_prompt_chunk", CHUNK), ("kv_write_decode_step", CONCURRENCY)):
        source_k = torch.randn((tokens, KV_HEADS, dim), device="cuda", dtype=torch.bfloat16) * 0.02
        source_v = torch.randn((tokens, KV_HEADS, dim), device="cuda", dtype=torch.bfloat16) * 0.02
        pages = math.ceil(tokens / PAGE_SIZE)
        cache_k = torch.empty((pages, PAGE_SIZE, KV_HEADS, dim), device="cuda", dtype=torch.float8_e5m2)
        cache_v = torch.empty_like(cache_k)
        flat_k = cache_k.view(-1, KV_HEADS, dim)[:tokens]
        flat_v = cache_v.view(-1, KV_HEADS, dim)[:tokens]

        def call():
            flat_k.copy_(source_k)
            flat_v.copy_(source_v)

        p50, raw = cuda_ms(call, 3, 11)
        rows.append(
            {
                "component": name,
                "head_dim": dim,
                "tokens": tokens,
                "page_size": PAGE_SIZE,
                "kv_heads": KV_HEADS,
                "source_dtype": str(source_k.dtype),
                "cache_dtype": str(cache_k.dtype),
                "p50_ms": p50,
                "raw_ms": raw,
                "output": finite_nonzero(flat_k),
            }
        )
        del source_k, source_v, cache_k, cache_v, flat_k, flat_v
    torch.cuda.empty_cache()
    return rows


def index(rows: list[dict]) -> dict[tuple[int, str], dict]:
    return {(row["head_dim"], row["component"]): row for row in rows}


def weighted_decision(rows: list[dict]) -> dict:
    by = index(rows)
    fresh_prompt_tokens_per_batch = CONCURRENCY * PROMPT_TOKENS * (1.0 - CACHED_PROMPT_FRACTION)
    prompt_chunks = fresh_prompt_tokens_per_batch / CHUNK
    weights = {
        "qkv_prompt_chunk": GLOBAL_LAYERS * prompt_chunks / CONCURRENCY,
        "o_prompt_chunk": GLOBAL_LAYERS * prompt_chunks / CONCURRENCY,
        "kv_write_prompt_chunk": GLOBAL_LAYERS * prompt_chunks / CONCURRENCY,
        "prompt_attention_triton": GLOBAL_LAYERS / CONCURRENCY,
        "qkv_decode_step": GLOBAL_LAYERS * OUTPUT_TOKENS / CONCURRENCY,
        "o_decode_step": GLOBAL_LAYERS * OUTPUT_TOKENS / CONCURRENCY,
        "kv_write_decode_step": GLOBAL_LAYERS * OUTPUT_TOKENS / CONCURRENCY,
        "decode_attention": GLOBAL_LAYERS * OUTPUT_TOKENS / CONCURRENCY,
    }
    components = []
    current_total = 0.0
    candidate_total = 0.0
    for component in ("qkv_prompt_chunk", "o_prompt_chunk", "kv_write_prompt_chunk", "prompt_attention_triton", "qkv_decode_step", "o_decode_step", "kv_write_decode_step"):
        current = by[(CURRENT_DIM, component)]["p50_ms"] / 1000.0 * weights[component]
        candidate = by[(CANDIDATE_DIM, component)]["p50_ms"] / 1000.0 * weights[component]
        current_total += current
        candidate_total += candidate
        components.append({"component": component, "weight": weights[component], "current_seconds_per_request": current, "candidate_seconds_per_request": candidate})
    current_decode = by[(CURRENT_DIM, "decode_attention_triton")]["p50_ms"] / 1000.0 * weights["decode_attention"]
    candidate_decode = by[(CANDIDATE_DIM, "decode_attention_trtllm_flashinfer_xqa")]["p50_ms"] / 1000.0 * weights["decode_attention"]
    current_total += current_decode
    candidate_total += candidate_decode
    components.append({"component": "decode_attention", "weight": weights["decode_attention"], "current_seconds_per_request": current_decode, "candidate_seconds_per_request": candidate_decode})
    savings = current_total - candidate_total
    xqa = by[(CANDIDATE_DIM, "decode_attention_trtllm_flashinfer_xqa")]
    outputs_pass = all(row["output"]["finite"] and row["output"]["nonzero"] for row in rows)
    xqa_symbol_proven = bool(xqa["profiler_xqa_events"])
    pass_gate = bool(outputs_pass and xqa_symbol_proven and not xqa["kv_repeated"] and xqa["oracle"]["pass"] and xqa["deterministic_max_abs"] == 0.0 and savings >= MINIMUM_SAVINGS)
    return {
        "components": components,
        "weighting": {
            "fresh_prompt_tokens_per_batch": fresh_prompt_tokens_per_batch,
            "prompt_projection_chunks_per_batch": prompt_chunks,
            "prompt_attention_basis": "exact c32 cached-prefix/extend Triton call; no analytical attention fraction",
            "decode_steps": OUTPUT_TOKENS,
            "global_layers": GLOBAL_LAYERS,
            "concurrency_divisor": CONCURRENCY,
        },
        "current_subgraph_seconds_per_request": current_total,
        "candidate_subgraph_seconds_per_request": candidate_total,
        "measured_savings_seconds_per_request": savings,
        "minimum_savings_seconds_per_request": MINIMUM_SAVINGS,
        "fraction_of_canonical_service_saved": savings / CANONICAL_SERVICE_SECONDS,
        "candidate_kernel_supported": xqa_symbol_proven,
        "candidate_kernel_avoids_dense_kv_repetition": not xqa["kv_repeated"],
        "candidate_oracle_pass": xqa["oracle"]["pass"],
        "all_outputs_finite_nonzero": outputs_pass,
        "pass": pass_gate,
        "classification": "nominate_architecture_proxy" if pass_gate else "close_architecture_backend_line",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result = {"schema_version": 1, "status": "running", "pass": False, "stage": "initializing", "rows": []}
    atomic_json(args.output / "RESULT.json", result)
    try:
        if torch.cuda.get_device_capability() != (9, 0) or "H200" not in torch.cuda.get_device_name():
            raise RuntimeError("exact NVIDIA H200 SM90 target is required")
        torch.manual_seed(SEED)
        torch.use_deterministic_algorithms(False)
        identity = {
            "gpu": torch.cuda.get_device_name(),
            "capability": list(torch.cuda.get_device_capability()),
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "flashinfer": getattr(flashinfer, "__version__", "unknown"),
            "container_image": "docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a",
            "symbols": [source_identity(extend_attention_fwd), source_identity(decode_attention_fwd), source_identity(trtllm_batch_decode_with_kv_cache)],
            "nvidia_smi": subprocess.run(["nvidia-smi", "-L"], check=False, capture_output=True, text=True).stdout.strip(),
        }
        result["identity"] = identity
        stages = (
            ("current_projections", lambda: projection_rows(CURRENT_DIM)),
            ("candidate_projections", lambda: projection_rows(CANDIDATE_DIM)),
            ("current_prompt_attention", lambda: [prompt_attention_row(CURRENT_DIM)]),
            ("candidate_prompt_attention", lambda: [prompt_attention_row(CANDIDATE_DIM)]),
            ("candidate_xqa_decode", lambda: [xqa_decode_row()]),
            ("current_triton_decode", lambda: [triton_decode_row(CURRENT_DIM)]),
            ("current_kv_writes", lambda: kv_write_rows(CURRENT_DIM)),
            ("candidate_kv_writes", lambda: kv_write_rows(CANDIDATE_DIM)),
        )
        for stage, call in stages:
            result["stage"] = stage
            atomic_json(args.output / "RESULT.json", result)
            result["rows"].extend(call())
            atomic_json(args.output / "RESULT.json", result)
        rows = result["rows"]
        decision = weighted_decision(rows)
        result = {
            "schema_version": 1,
            "status": "terminal",
            "pass": decision["pass"],
            "classification": decision["classification"],
            "evidence_type": "measured exact-H200 non-quality-preserving architecture proxy",
            "quality_claim": False,
            "geometry": {
                "hidden_size": HIDDEN,
                "query_heads": QUERY_HEADS,
                "kv_heads": KV_HEADS,
                "current_global_head_dim": CURRENT_DIM,
                "candidate_global_head_dim": CANDIDATE_DIM,
                "global_layers": GLOBAL_LAYERS,
                "concurrency": CONCURRENCY,
                "prompt_tokens_per_request": PROMPT_TOKENS,
                "output_tokens_per_request": OUTPUT_TOKENS,
                "cached_prompt_fraction": CACHED_PROMPT_FRACTION,
                "peak_global_context": PEAK_CONTEXT,
                "page_size": PAGE_SIZE,
            },
            "identity": identity,
            "stage": "complete",
            "rows": rows,
            "decision": decision,
            "elapsed_seconds": time.time() - started,
        }
    except Exception as error:
        result = {
            "schema_version": 1,
            "status": "terminal",
            "pass": False,
            "classification": "execution_failure",
            "stage": result.get("stage"),
            "identity": result.get("identity"),
            "rows": result.get("rows", []),
            "error": {"type": type(error).__name__, "message": str(error)},
            "traceback": traceback.format_exc(),
            "elapsed_seconds": time.time() - started,
        }
    atomic_json(args.output / "RESULT.json", result)
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
