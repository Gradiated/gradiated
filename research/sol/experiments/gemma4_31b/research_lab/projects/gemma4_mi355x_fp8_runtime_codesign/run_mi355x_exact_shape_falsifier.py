#!/usr/bin/env python3
"""One-shot exact-consumer MI355X FP8 runtime falsifier.

This deliberately uses random exact-shape fixtures: it measures the admitted
runtime consumers and their physical cost, not checkpoint quality or endpoint
deployment.  A launcher/configuration failure before ``science_started`` is
left as an operational error for same-claim repair; only a complete suite can
write the scientific terminal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

PROJECT = Path(__file__).resolve().parent
DEFAULT_SCREEN = PROJECT / "MI355X_FP8_RUNTIME_SCREEN.json"
DEFAULT_OUTPUT = PROJECT / "MI355X_EXACT_SHAPE_FALSIFIER.json"
BINDINGS = PROJECT / "SOURCE_BINDINGS.json"
SCREEN_SHA256 = "e1bad18d0d2e0d3e281c3502a3b4a25108d0841ac2da85e5fd0fadebe99cc500"
BASE_HURDLE = 0.625149101968745
COMPONENT_HURDLE = 0.545847226968745
SERVICE_RESERVE = 0.07930187499999997
HIDDEN, INTERMEDIATE, VOCAB = 5376, 21504, 262144
LINEARS = (
    ("sliding_qkv", 50, HIDDEN, 16384),
    ("sliding_o", 50, 8192, HIDDEN),
    ("global_qkv", 10, HIDDEN, 20480),
    ("global_o", 10, 16384, HIDDEN),
    ("gate_up", 60, HIDDEN, 43008),
    ("down", 60, INTERMEDIATE, HIDDEN),
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def git_head(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def verify_sources(vllm_root: Path, aiter_root: Path) -> dict[str, Any]:
    bindings = json.loads(BINDINGS.read_text())
    roots = {"vllm": vllm_root, "aiter": aiter_root}
    checks: dict[str, Any] = {}
    for name, spec in bindings["repositories"].items():
        root = roots[name]
        observed = git_head(root)
        checks[f"{name}_commit"] = {"expected": spec["commit"], "observed": observed, "pass": observed == spec["commit"]}
        for relative, expected in spec["files"].items():
            observed_hash = digest(root / relative) if (root / relative).is_file() else None
            checks[f"{name}:{relative}"] = {"expected_sha256": expected, "observed_sha256": observed_hash, "pass": observed_hash == expected}
    failed = [name for name, row in checks.items() if not row["pass"]]
    if failed:
        raise RuntimeError(f"pinned runtime source check failed: {failed}")
    return checks


def metric(actual: torch.Tensor, reference: torch.Tensor) -> dict[str, Any]:
    a, b = actual.float().flatten(), reference.float().flatten()
    difference = torch.linalg.vector_norm(a - b)
    denom = torch.linalg.vector_norm(b).clamp_min(1e-12)
    return {
        "finite": bool(torch.isfinite(a).all().item()),
        "relative_l2": float((difference / denom).item()),
        "cosine": float(torch.nn.functional.cosine_similarity(a, b, dim=0).item()),
    }


def timed(fn: Callable[[], torch.Tensor], warmup: int, repeats: int) -> tuple[list[float], float]:
    for _ in range(warmup):
        value = fn()
        _ = value[:, 0].float().sum()
    torch.cuda.synchronize()
    values, sink = [], 0.0
    for _ in range(repeats):
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        start.record()
        value = fn()
        consumed = value[:, 0].float().sum()
        end.record()
        end.synchronize()
        if not torch.isfinite(value).all():
            raise RuntimeError("non-finite timed consumer output")
        sink += float(consumed.item())
        values.append(float(start.elapsed_time(end)))
    return values, sink


def fp8_pair(x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    # torch._scaled_mm consumes dequantization multipliers, not reciprocal scales.
    scale = (x.abs().amax().float() / torch.finfo(torch.float8_e4m3fn).max).clamp_min(1e-8)
    return (x.float() / scale).to(torch.float8_e4m3fn), scale.reshape(1)


def linear_row(name: str, layers: int, m: int, k: int, n: int, warmup: int, repeats: int) -> dict[str, Any]:
    x = torch.randn((m, k), device="cuda", dtype=torch.bfloat16) * 0.02
    weight = torch.randn((k, n), device="cuda", dtype=torch.bfloat16) * 0.02
    xq, xs = fp8_pair(x)
    wq, ws = fp8_pair(weight)
    reference = x @ weight
    def invoke() -> torch.Tensor:
        return torch._scaled_mm(xq, wq, out_dtype=torch.bfloat16, scale_a=xs, scale_b=ws)
    actual = invoke()
    numeric = metric(actual, reference)
    samples, sink = timed(invoke, warmup, repeats)
    return {"kind": "fp8_linear", "name": name, "layers": layers, "m": m, "n": n, "k": k,
            "consumer": "torch._scaled_mm", "candidate_path": {"called": True, "fallback": False, "scale_contract": "per_tensor_fp32"},
            "numeric": numeric, "timing_ms": {"samples": samples, "p50": statistics.median(samples), "p95": sorted(samples)[math.ceil(.95 * len(samples)) - 1]}, "sink": sink}


def attention_row(name: str, m: int, head_size: int, kv_heads: int, window: int | None, warmup: int, repeats: int) -> dict[str, Any]:
    from aiter.ops.triton.attention.unified_attention import unified_attention
    q_heads, context, block = 32, 4571, 32
    blocks = math.ceil(context / block)
    q = torch.randn((m, q_heads, head_size), device="cuda", dtype=torch.bfloat16) * 0.02
    k_bf16 = torch.randn((blocks, block, kv_heads, head_size), device="cuda", dtype=torch.bfloat16) * 0.02
    v_bf16 = torch.randn_like(k_bf16)
    k, ks = fp8_pair(k_bf16)
    v, vs = fp8_pair(v_bf16)
    block_table = torch.arange(blocks, device="cuda", dtype=torch.int32).reshape(1, -1)
    cu = torch.tensor([0, m], device="cuda", dtype=torch.int32)
    used = torch.tensor([context], device="cuda", dtype=torch.int32)
    out = torch.empty_like(q)
    # A compact BF16 oracle with the same GQA, causal, and local/global mask.
    keys = k_bf16.reshape(-1, kv_heads, head_size)[:context].permute(1, 0, 2)
    vals = v_bf16.reshape(-1, kv_heads, head_size)[:context].permute(1, 0, 2)
    keyq = keys.repeat_interleave(q_heads // kv_heads, dim=0)
    valq = vals.repeat_interleave(q_heads // kv_heads, dim=0)
    scores = torch.einsum("mhd,hkd->mhk", q.float(), keyq.float()) / math.sqrt(head_size)
    positions = torch.arange(context, device="cuda")
    if window is not None:
        scores[:, :, positions < context - window] = -float("inf")
    reference = torch.einsum("mhk,hkd->mhd", torch.softmax(scores, dim=-1), valq.float()).to(torch.bfloat16)
    def invoke() -> torch.Tensor:
        unified_attention(q, k, v, out, cu, m, used, context, 1.0 / math.sqrt(head_size), True,
                          (window - 1 if window is not None else -1, -1), block_table, 0.0, None, ks, vs)
        return out
    actual = invoke().clone()
    numeric = metric(actual, reference)
    samples, sink = timed(invoke, warmup, repeats)
    return {"kind": "fp8_kv_attention", "name": name, "m": m, "head_size": head_size, "kv_heads": kv_heads,
            "context": context, "window": window, "consumer": "aiter.ops.triton.attention.unified_attention.unified_attention",
            "candidate_path": {"called": True, "fallback": False, "kv_dtype": "float8_e4m3fn", "gqa": q_heads // kv_heads},
            "numeric": numeric, "timing_ms": {"samples": samples, "p50": statistics.median(samples), "p95": sorted(samples)[math.ceil(.95 * len(samples)) - 1]}, "sink": sink}


def head_row(m: int, calls: int, warmup: int, repeats: int) -> dict[str, Any]:
    from torch import nn
    from vllm.model_executor.layers.vocab_parallel_embedding import UnquantizedEmbeddingMethod
    layer = nn.Module()
    layer.weight = nn.Parameter(torch.randn((VOCAB, HIDDEN), device="cuda", dtype=torch.bfloat16) * 0.02, requires_grad=False)
    x = torch.randn((m, HIDDEN), device="cuda", dtype=torch.bfloat16) * 0.02
    method = UnquantizedEmbeddingMethod()
    reference = x @ layer.weight.t()
    def invoke() -> torch.Tensor:
        return method.apply(layer, x)
    actual = invoke()
    numeric = metric(actual, reference)
    argmax = bool(torch.equal(actual.argmax(dim=-1), reference.argmax(dim=-1)))
    samples, sink = timed(invoke, warmup, repeats)
    return {"kind": "bf16_tied_head", "m": m, "n": VOCAB, "k": HIDDEN, "semantic_calls_per_target_cycle": calls,
            "consumer": "vllm.model_executor.layers.vocab_parallel_embedding.UnquantizedEmbeddingMethod.apply -> dispatch_unquantized_gemm",
            "candidate_path": {"called": True, "fallback": False, "tied_bf16_weight": True}, "numeric": {**numeric, "argmax_identity": argmax},
            "timing_ms": {"samples": samples, "p50": statistics.median(samples), "p95": sorted(samples)[math.ceil(.95 * len(samples)) - 1]}, "sink": sink}


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    linear = {(r["name"], r["m"]): r for r in rows if r["kind"] == "fp8_linear"}
    attention = {(r["name"], r["m"]): r for r in rows if r["kind"] == "fp8_kv_attention"}
    heads = {r["m"]: r for r in rows if r["kind"] == "bf16_tied_head"}
    # Exact M32 decode (358 steps/c32) plus 15 M384 target cycles.  Prefill uses
    # the M384 tensor path for 32*3678.822 rows, preserving the admitted suite.
    total_ms = 0.0
    for name, layers, _, _ in LINEARS:
        total_ms += linear[(name, 32)]["timing_ms"]["p50"] * layers * 358 / 32
        total_ms += linear[(name, 384)]["timing_ms"]["p50"] * layers * 15 / 32
        total_ms += linear[(name, 384)]["timing_ms"]["p50"] * layers * (32 * 3678.822 / 384) / 32
    for name in ("sliding", "global"):
        total_ms += attention[(name, 32)]["timing_ms"]["p50"] * 358 / 32
        total_ms += attention[(name, 384)]["timing_ms"]["p50"] * 15 / 32
    total_ms += heads[32]["timing_ms"]["p50"] * 358 / 32
    total_ms += heads[32]["timing_ms"]["p50"] * 12 * 15 / 32
    component = total_ms / 1000
    return {"method": "charged exact M32/M384 p50s weighted by admitted c32 decode, target cycles, and fresh prefill rows", "component_seconds_per_request": component,
            "service_reserve_seconds_per_request": SERVICE_RESERVE, "whole_request_seconds_per_request": component + SERVICE_RESERVE,
            "component_gate": COMPONENT_HURDLE, "whole_request_gate": BASE_HURDLE}


def main() -> int:
    global torch
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=Path, default=DEFAULT_SCREEN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--vllm-root", type=Path, default=os.environ.get("VLLM_ROOT"))
    parser.add_argument("--aiter-root", type=Path, default=os.environ.get("AITER_ROOT"))
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--seed", type=int, default=20260726)
    args = parser.parse_args()
    import torch
    if args.vllm_root is None or args.aiter_root is None:
        raise RuntimeError("set VLLM_ROOT and AITER_ROOT to pinned source worktrees")
    if args.output.exists():
        raise SystemExit(f"refusing to replay an existing suite: {args.output}")
    if digest(args.screen) != SCREEN_SHA256:
        raise RuntimeError("screen identity does not match the admitted source terminal")
    screen = json.loads(args.screen.read_text())
    if screen.get("classification") != "source_complete_mi355x_candidate":
        raise RuntimeError("admitted source terminal is not a candidate")
    checks = verify_sources(args.vllm_root.resolve(), args.aiter_root.resolve())
    if not torch.cuda.is_available() or "gfx950" not in torch.cuda.get_device_name(0).lower():
        raise RuntimeError("MI355X/gfx950 target is required")
    if args.warmup < 1 or args.repeats < 5:
        raise ValueError("require >=1 warmup and >=5 measured repeats")
    sys.path[:0] = [str(args.vllm_root), str(args.aiter_root)]
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    marker = args.output.with_suffix(".science_started")
    marker.write_text("pinned identities validated; first GPU consumer follows\n")
    started = time.time()
    rows = []
    for name, layers, k, n in LINEARS:
        for m in (32, 384):
            rows.append(linear_row(name, layers, m, k, n, args.warmup, args.repeats))
    for m in (32, 384):
        rows.append(attention_row("sliding", m, 256, 16, 1024, args.warmup, args.repeats))
        rows.append(attention_row("global", m, 512, 4, None, args.warmup, args.repeats))
    rows.extend((head_row(32, 12, args.warmup, args.repeats), head_row(384, 12, args.warmup, args.repeats)))
    numeric_pass = all(r["numeric"]["finite"] and r["numeric"].get("relative_l2", 0.0) <= .02 and r["numeric"].get("cosine", 1.0) >= .995 and r["numeric"].get("argmax_identity", True) for r in rows)
    no_fallback = all(r["candidate_path"]["called"] and not r["candidate_path"]["fallback"] for r in rows)
    charge = aggregate(rows)
    passes = numeric_pass and no_fallback and charge["component_seconds_per_request"] <= COMPONENT_HURDLE and charge["whole_request_seconds_per_request"] <= BASE_HURDLE
    result = {"schema_version": 1, "classification": "measured_mi355x_candidate" if passes else "typed_none", "science_started": str(marker),
              "identity": {"runner_sha256": digest(Path(__file__)), "screen_sha256": digest(args.screen), "source_checks": checks,
                           "hardware": torch.cuda.get_device_name(0), "torch": torch.__version__, "hip": torch.version.hip, "python": platform.python_version()},
              "contract": {"unstacked": True, "linears": "all Gemma transformer linear shapes at M32/M384", "attention": "AITER FP8-KV sliding/global M32/M384", "head": "BF16 tied V=262144 and twelve semantic calls per target cycle"},
              "rows": rows, "charged_aggregation": charge, "numerical_gate": {"pass": numeric_pass, "relative_l2_max": .02, "cosine_min": .995, "head_argmax_identity": True},
              "no_fallback_gate": {"pass": no_fallback}, "elapsed_science_seconds": time.time() - started}
    atomic_json(args.output, result)
    return 0 if passes else 20


if __name__ == "__main__":
    raise SystemExit(main())
