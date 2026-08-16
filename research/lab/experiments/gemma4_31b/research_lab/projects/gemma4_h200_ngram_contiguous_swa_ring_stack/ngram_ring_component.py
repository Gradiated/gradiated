#!/usr/bin/env python3
"""Exact c32/Q12 local target-verification layout discriminator."""
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

from ring_kv import store_ring_kv


BATCH, QLEN, WINDOW, QH, KVH, D = 32, 12, 1024, 32, 16, 256
CONTROL_SHA = "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"


def write(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    os.replace(temporary, path)


def timed(fn) -> float:
    begin, end = torch.cuda.Event(True), torch.cuda.Event(True)
    begin.record(); fn(); end.record(); end.synchronize()
    return float(begin.elapsed_time(end))


def dist(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    return {"samples_ms": values, "median_ms": statistics.median(values), "p90_ms": ordered[math.ceil(.9 * len(values)) - 1]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=25)
    args = parser.parse_args()
    root = args.artifact_root
    write(root / "INVOCATION_STATE.json", {"candidate_cuda_invocation_started": False, "scientific_invocation_started": False, "schema_version": 1})
    if not torch.cuda.is_available() or torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("exact_sm90_cuda_unavailable")
    from sglang.srt.layers.attention.triton_ops import extend_attention
    control_file = pathlib.Path(extend_attention.__file__)
    if hashlib.sha256(control_file.read_bytes()).hexdigest() != CONTROL_SHA:
        raise RuntimeError("pinned_extend_attention_hash_mismatch")
    torch.manual_seed(20260724)
    tokens, pages = BATCH * QLEN, BATCH * (WINDOW + QLEN)
    q = torch.randn((tokens, QH, D), device="cuda", dtype=torch.bfloat16)
    k = torch.randn((tokens, KVH, D), device="cuda", dtype=torch.bfloat16)
    v = torch.randn_like(k)
    prefix_k = torch.randn((BATCH * WINDOW, KVH, D), device="cuda", dtype=torch.bfloat16)
    prefix_v = torch.randn_like(prefix_k)
    ring_k = torch.zeros((BATCH, WINDOW, KVH, D), device="cuda", dtype=torch.float8_e5m2)
    ring_v = torch.zeros_like(ring_k)
    request_ids = torch.arange(BATCH, device="cuda", dtype=torch.int32).repeat_interleave(WINDOW)
    starts = (torch.arange(BATCH, device="cuda", dtype=torch.int64) * 137 + 897)
    positions = (starts[:, None] + torch.arange(WINDOW, device="cuda", dtype=torch.int64)).flatten()
    store_ring_kv(prefix_k, prefix_v, ring_k, ring_v, request_ids, positions)
    torch.cuda.synchronize()
    ring_starts = (starts & (WINDOW - 1)).to(torch.int64)
    chronological = ((ring_starts[:, None] + torch.arange(WINDOW, device="cuda")) & (WINDOW - 1)).flatten()
    candidate_prefix_indices = (torch.arange(BATCH, device="cuda")[:, None] * WINDOW + chronological.view(BATCH, WINDOW)).flatten().to(torch.int64)
    candidate_k = torch.cat((ring_k.flatten(0, 1), k.to(torch.float8_e5m2)), dim=0)
    candidate_v = torch.cat((ring_v.flatten(0, 1), v.to(torch.float8_e5m2)), dim=0)
    candidate_indices = torch.cat((candidate_prefix_indices.view(BATCH, WINDOW), (BATCH * WINDOW + torch.arange(tokens, device="cuda")).view(BATCH, QLEN)), dim=1).flatten().to(torch.int32)
    control_pages = torch.randperm(pages, device="cuda", dtype=torch.int64)
    control_k, control_v = torch.empty((pages, KVH, D), device="cuda", dtype=torch.float8_e5m2), torch.empty((pages, KVH, D), device="cuda", dtype=torch.float8_e5m2)
    logical_k = torch.cat((prefix_k.view(BATCH, WINDOW, KVH, D), k.view(BATCH, QLEN, KVH, D)), dim=1).flatten(0, 1).to(torch.float8_e5m2)
    logical_v = torch.cat((prefix_v.view(BATCH, WINDOW, KVH, D), v.view(BATCH, QLEN, KVH, D)), dim=1).flatten(0, 1).to(torch.float8_e5m2)
    control_k[control_pages] = logical_k; control_v[control_pages] = logical_v
    qo = torch.arange(0, tokens + 1, QLEN, device="cuda", dtype=torch.int32)
    kv = torch.arange(0, BATCH * (WINDOW + QLEN) + 1, WINDOW + QLEN, device="cuda", dtype=torch.int32)
    control_indices = control_pages.view(BATCH, WINDOW + QLEN).flatten().to(torch.int32)
    seq = torch.full((BATCH,), WINDOW + QLEN, device="cuda", dtype=torch.int32)
    tree = torch.tril(torch.ones((QLEN, QLEN), device="cuda", dtype=torch.bool))
    mask = torch.cat([torch.cat((torch.ones((QLEN, WINDOW), device="cuda", dtype=torch.bool), tree), dim=1).flatten() for _ in range(BATCH)])
    mask_indptr = torch.arange(0, BATCH * QLEN * (WINDOW + QLEN) + 1, QLEN * (WINDOW + QLEN), device="cuda", dtype=torch.int32)
    out0, out1 = torch.empty_like(q), torch.empty_like(q)
    def invoke(kbuf, vbuf, indices, out):
        extend_attention.extend_attention_fwd_unified(q, out, kbuf, vbuf, 1., 1., qo, kv, indices, seq, QLEN, mask, mask_indptr, 1 / math.sqrt(D), is_causal=True, sliding_window_size=1024, window_start_pos=torch.zeros(BATCH, device="cuda", dtype=torch.int32))
    invoke(control_k, control_v, control_indices, out0); invoke(candidate_k, candidate_v, candidate_indices, out1); torch.cuda.synchronize()
    write(root / "INVOCATION_STATE.json", {"candidate_cuda_invocation_started": True, "scientific_invocation_started": True, "schema_version": 1})
    delta = out1.float() - out0.float()
    exact_bytes = bool(torch.equal(ring_k[torch.arange(BATCH, device="cuda")[:, None], chronological.view(BATCH, WINDOW)].view(torch.uint8), prefix_k.view(BATCH, WINDOW, KVH, D).to(torch.float8_e5m2).view(torch.uint8)))
    pad_before = ring_k[0, 17].clone(); store_ring_kv(k[:1], v[:1], ring_k, ring_v, torch.tensor([-1], device="cuda", dtype=torch.int32), torch.tensor([0], device="cuda", dtype=torch.int64)); torch.cuda.synchronize()
    padding_noop = bool(torch.equal(pad_before, ring_k[0, 17]))
    for _ in range(args.warmups): invoke(control_k, control_v, control_indices, out0); invoke(candidate_k, candidate_v, candidate_indices, out1)
    torch.cuda.synchronize(); base, candidate = [], []
    for i in range(args.iterations):
        for side in ((0, 1) if i % 2 == 0 else (1, 0)):
            (base if side == 0 else candidate).append(timed(lambda s=side: invoke(control_k if s == 0 else candidate_k, control_v if s == 0 else candidate_v, control_indices if s == 0 else candidate_indices, out0 if s == 0 else out1)))
    control, cand = dist(base), dist(candidate)
    reduction = 1 - cand["median_ms"] / control["median_ms"]
    terminal = {"schema_version": 1, "kind": "exact_c32_q12_ngram_local_target_verification_ring_layout", "component_pass": bool(torch.isfinite(out1).all() and torch.allclose(out0.float(), out1.float(), atol=.005, rtol=.005) and exact_bytes and padding_noop and reduction > 0), "correct": {"finite": bool(torch.isfinite(out1).all()), "allclose": bool(torch.allclose(out0.float(), out1.float(), atol=.005, rtol=.005)), "max_abs_error": float(delta.abs().max()), "relative_l2": float(torch.linalg.vector_norm(delta) / torch.linalg.vector_norm(out0.float()).clamp_min(1e-12)), "ring_transition_bytes_exact": exact_bytes, "padded_row_noop": padding_noop}, "candidate_path": {"local_layers": 50, "global_layers_stock": 10, "q_rows_per_request": QLEN, "request_owned_contiguous_e5m2_ring": True, "ring_wrap_requests": int((ring_starts != 0).sum())}, "timing": {"control": control, "candidate": cand, "reduction_fraction": reduction}, "positive_whole_request_bound_fraction": reduction * 0.6266}
    write(root / "COMPONENT_TERMINAL.json", terminal)
    write(root / "INVOCATION_STATE.json", {"candidate_cuda_invocation_started": True, "scientific_invocation_started": True, "scientific_terminal_recorded": True, "schema_version": 1})
    print(json.dumps(terminal, sort_keys=True))
    return 0 if terminal["component_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
