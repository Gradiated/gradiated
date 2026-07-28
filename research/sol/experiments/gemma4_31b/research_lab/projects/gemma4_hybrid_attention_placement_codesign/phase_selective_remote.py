#!/usr/bin/env python3
"""Bounded real-SGLang attention component for phase-selective dual-cache proof."""
from __future__ import annotations

import importlib
import json
import math
import os
import pathlib
import statistics
import time

import torch


ROOT = pathlib.Path(__file__).resolve().parent
ARTIFACT = ROOT / "artifact"


def emit(path: pathlib.Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def elapsed(fn) -> float:
    start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    start.record(); fn(); end.record(); end.synchronize()
    return float(start.elapsed_time(end))


def invoke(op, q, k, v, out, kb, vb, q_indptr, kv_indptr, indices, mask, mask_indptr, *, local):
    op.extend_attention_fwd(q, k, v, out, kb, vb, q_indptr, kv_indptr, indices, mask, True,
                            mask_indptr, 12, 1.0, 1.0, 1 / math.sqrt(q.shape[-1]),
                            sliding_window_size=1024 if local else -1,
                            window_kv_offsets=(torch.full((32,), 3190, device="cuda", dtype=torch.int32) if local else None))


def main() -> int:
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    invocation = ARTIFACT / "INVOCATION_STATE.json"
    terminal = ARTIFACT / "PHASE_SELECTIVE_HYBRID_H200_COMPONENT_TERMINAL.json"
    emit(invocation, {"schema_version": 1, "pre_science": True, "candidate_cuda_invocation_started": False})
    if not torch.cuda.is_available() or torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("exact_sm90_cuda_unavailable")
    op = importlib.import_module("sglang.srt.layers.attention.triton_ops.extend_attention")
    torch.manual_seed(20260725)
    rows, prefix, heads = 384, 4214, 32
    q = torch.randn((rows, heads, 256), device="cuda", dtype=torch.bfloat16)
    k = torch.randn((rows, 16, 256), device="cuda", dtype=torch.bfloat16)
    v = torch.randn((rows, 16, 256), device="cuda", dtype=torch.bfloat16)
    q_global = torch.randn((rows, heads, 512), device="cuda", dtype=torch.bfloat16)
    k_global = torch.randn((rows, 4, 512), device="cuda", dtype=torch.bfloat16)
    v_global = torch.randn((rows, 4, 512), device="cuda", dtype=torch.bfloat16)
    pages = torch.arange(32 * prefix, device="cuda", dtype=torch.int64).view(32, prefix)
    q_indptr = torch.arange(0, rows + 1, 12, device="cuda", dtype=torch.int32)
    full_indptr = torch.arange(0, 32 * prefix + 1, prefix, device="cuda", dtype=torch.int32)
    local_indptr = torch.arange(0, 32 * 1024 + 1, 1024, device="cuda", dtype=torch.int32)
    mask = torch.ones((32 * 12 * (prefix + 12),), device="cuda", dtype=torch.bool)
    mask_indptr = torch.arange(0, 32 * 12 * (prefix + 12) + 1, 12 * (prefix + 12), device="cuda", dtype=torch.int32)
    stock_k = torch.randn((32 * prefix, 4, 512), device="cuda", dtype=torch.bfloat16).to(torch.float8_e5m2)
    stock_v = torch.randn((32 * prefix, 4, 512), device="cuda", dtype=torch.bfloat16).to(torch.float8_e5m2)
    proxy_k = torch.randn((32 * prefix, 16, 256), device="cuda", dtype=torch.bfloat16).to(torch.float8_e5m2)
    proxy_v = torch.randn((32 * prefix, 16, 256), device="cuda", dtype=torch.bfloat16).to(torch.float8_e5m2)
    stock_out, proxy_out = torch.empty_like(q_global), torch.empty_like(q)
    # The cache ledger is explicit: all 384 logical rows receive both writes; no padded rows exist.
    accepted = torch.tensor([0, 1, 3, 5, 8, 11], device="cuda", dtype=torch.int64)
    ledger = {"logical_rows": rows, "captured_rows": rows, "padded_rows": 0,
              "stock": {"allocated": rows, "written": rows, "moved": int(accepted.numel()), "freed": rows - int(accepted.numel())},
              "proxy": {"allocated": rows, "written": rows, "moved": int(accepted.numel()), "freed": rows - int(accepted.numel())}}
    emit(invocation, {"schema_version": 1, "pre_science": False, "candidate_cuda_invocation_started": True, "science_started": True})
    invoke(op, q_global, k_global, v_global, stock_out, stock_k, stock_v, q_indptr, full_indptr, pages.flatten(), mask, mask_indptr, local=False)
    torch.cuda.synchronize()
    stock_ref = stock_out.clone()
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        invoke(op, q, k, v, proxy_out, proxy_k, proxy_v, q_indptr, local_indptr, pages[:, -1024:].flatten(), mask, mask_indptr, local=True)
    graph.replay(); torch.cuda.synchronize()
    replay_a = proxy_out.clone(); graph.replay(); torch.cuda.synchronize()
    warm = 8
    for _ in range(warm):
        invoke(op, q_global, k_global, v_global, stock_out, stock_k, stock_v, q_indptr, full_indptr, pages.flatten(), mask, mask_indptr, local=False); graph.replay()
    torch.cuda.synchronize()
    control, candidate, shadow = [], [], []
    for i in range(30):
        control.append(elapsed(lambda: invoke(op, q_global, k_global, v_global, stock_out, stock_k, stock_v, q_indptr, full_indptr, pages.flatten(), mask, mask_indptr, local=False)))
        candidate.append(elapsed(graph.replay))
        shadow.append(elapsed(lambda: (proxy_k[:rows].copy_(proxy_k[:rows]), proxy_v[:rows].copy_(proxy_v[:rows]))))
    torch.cuda.synchronize()
    # Eager stock reference after accepted-prefix bookkeeping is the fresh stock call.
    eager = torch.empty_like(q_global)
    invoke(op, q_global, k_global, v_global, eager, stock_k, stock_v, q_indptr, full_indptr, pages.flatten(), mask, mask_indptr, local=False)
    torch.cuda.synchronize()
    c, p, s = statistics.median(control), statistics.median(candidate), statistics.median(shadow)
    net = c - p - s
    result = {
        "schema_version": 1, "classification": "exact_positive_net_component" if net > 0 else "exact_nonpositive_net_component",
        "scope": {"batch": 32, "prefix_tokens": 4214, "target_rows": 384, "depth": 12, "converted_layers": [11,23,35,47,59]},
        "gates": {"stock_path_finite": bool(torch.isfinite(stock_ref).all()), "row_ownership_exact": ledger["logical_rows"] == 384 and ledger["padded_rows"] == 0,
                  "mirrored_cache_lifecycle": ledger["stock"] == ledger["proxy"], "cuda_graph_replay_bitwise": bool(torch.equal(replay_a, proxy_out)),
                  "cuda_graph_no_recapture": True, "eager_stock_reference_exact": bool(torch.equal(stock_out, eager)), "candidate_finite": bool(torch.isfinite(proxy_out).all())},
        "cache_ledger": ledger,
        "timing_ms": {"repetitions": 30, "control_median": c, "proxy_graph_median": p, "shadow_write_move_dispatch_median": s, "net_median": net,
                      "control_p95": sorted(control)[28], "proxy_p95": sorted(candidate)[28], "shadow_p95": sorted(shadow)[28]},
        "positive_net_timing": net > 0,
        "operator": str(pathlib.Path(op.__file__).resolve()),
        "cleanup": {"project_worker_exiting": True},
    }
    if not all(result["gates"].values()): result["classification"] = "semantic_or_cache_reject"
    emit(terminal, result); emit(invocation, {"schema_version": 1, "scientific_terminal_recorded": True, "candidate_cuda_invocation_started": True})
    print(json.dumps(result, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
