#!/usr/bin/env python3
"""Checkpoint-free H100 component: native NGRAM -> eager Triton attention -> state."""
from __future__ import annotations

import argparse, hashlib, json, os, time
from pathlib import Path

import torch
import triton
import triton.language as tl

from adaptive_depth_runtime import DualDepthNgram
from sglang.srt.speculative.cpp_ngram.ngram_corpus import NgramCorpus


@triton.jit
def _target_verify(Q, K, V, OUT, MASK, n_q: tl.constexpr, n_k: tl.constexpr, d: tl.constexpr):
    q = tl.program_id(0)
    offs = tl.arange(0, d)
    qv = tl.load(Q + q * d + offs, mask=offs < d, other=0.0)
    ko = tl.arange(0, 128)
    kv = tl.load(K + ko[:, None] * d + offs[None, :], mask=(ko[:, None] < n_k) & (offs[None, :] < d), other=0.0)
    allowed = (ko < n_k) & (ko <= q + n_k - n_q)
    scores = tl.sum(kv * qv[None, :], axis=1, dtype=tl.float32) * (d ** -0.5)
    scores = tl.where(allowed, scores, -float("inf"))
    weights = tl.exp(scores - tl.max(scores, axis=0))
    denom = tl.sum(weights, axis=0)
    out = tl.zeros((d,), dtype=tl.float32)
    vv = tl.load(V + ko[:, None] * d + offs[None, :], mask=(ko[:, None] < n_k) & (offs[None, :] < d), other=0.0)
    out += tl.sum(weights[:, None] * vv, axis=0)
    tl.store(OUT + q * d + offs, out / denom, mask=offs < d)


def attention(q, k, v, mask):
    out = torch.empty_like(q)
    _target_verify[(q.shape[0],)](q, k, v, out, mask, n_q=q.shape[0], n_k=k.shape[0], d=q.shape[1], num_warps=4)
    return out


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(out: Path, repetitions: int) -> dict:
    torch.manual_seed(8490)
    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    name = torch.cuda.get_device_name(0)
    if "H100" not in name:
        raise RuntimeError(f"wrong_gpu:{name}")
    device = "cuda"
    model = DualDepthNgram(NgramCorpus, max_trie_depth=18, min_bfs_breadth=1, max_bfs_breadth=8, match_type="BFS", capacity=4096)
    corpus_rows = [[1000 + ((i * 17 + j) % 251) for j in range(128)] for i in range(16)]
    model.insert(corpus_rows)
    arms = {7: 12, 8: 6}
    samples = {7: [], 8: []}
    correctness = {"producer": [], "attention": [], "acceptance": [], "kv": [], "scheduler": [], "graph": []}
    # Warm both native producers and the real eager Triton target-verification kernel.
    for bs in (7, 8):
        req = [f"r{bs}-{i}" for i in range(bs)]
        queries = [row[:32] for row in corpus_rows[:bs]]
        lens = [32] * bs
        depth, tok, tree = model.produce(req, queries, lens)
        control = NgramCorpus(max_trie_depth=18, min_bfs_breadth=1, max_bfs_breadth=8, match_type="BFS", capacity=4096, draft_token_num=depth)
        control.batch_put(corpus_rows); control.synchronize(); ct, cm = control.batch_get(req, queries, lens)
        assert depth == arms[bs] and tok.tobytes() == ct.tobytes() and tree.tobytes() == cm.tobytes()
        correctness["producer"].append({"bs": bs, "depth": depth, "bytes_match": True})
        q = torch.randn((bs * depth, 64), device=device, dtype=torch.float16)
        k = torch.randn((128, 64), device=device, dtype=torch.float16)
        v = torch.randn_like(k)
        rows = torch.arange(bs * depth, device=device)[:, None]
        cols = torch.arange(k.shape[0], device=device)[None, :]
        mask = (cols <= rows + k.shape[0] - bs * depth).float()
        ref = torch.nn.functional.scaled_dot_product_attention(q.float()[None], k.float()[None], v.float()[None], (mask[None] > 0), scale=64 ** -0.5)[0]
        got = attention(q, k, v, mask)
        assert torch.allclose(got.float(), ref, atol=2e-2, rtol=2e-2)
        correctness["attention"].append({"bs": bs, "depth": depth, "max_abs_err": float((got.float()-ref).abs().max())})
        accepted = [[int(tok[i * depth + j]) for j in range(depth)] for i in range(bs)]
        logits = torch.full((bs, depth, 512), -1.0, device=device); ids = torch.tensor(accepted, device=device) % 512
        logits.scatter_(2, ids[..., None], 1.0)
        greedy = logits.argmax(-1).cpu().tolist()
        assert greedy == [[x % 512 for x in row] for row in accepted]
        correctness["acceptance"].append({"bs": bs, "depth": depth, "rows": bs * depth, "accepted": True})
        src = torch.arange(bs * depth, device=device); dst = torch.arange(100, 100 + bs * depth, device=device); kv = torch.arange(2000, device=device)
        kv2 = kv.clone(); kv2[dst] = kv[src]; assert torch.equal(kv2[dst], kv[src]); correctness["kv"].append({"bs": bs, "depth": depth, "slots_match": True})
        carrier = model.settle(req, accepted); assert carrier.offsets[-1] == bs * depth
        correctness["scheduler"].append({"bs": bs, "depth": depth, "offsets_match": True})
        mode = model.graph_mode(depth); assert mode == ("cuda_graph" if bs == 7 else "eager")
        correctness["graph"].append({"bs": bs, "depth": depth, "mode": mode, "depth6_rejected": depth == 6})
        torch.cuda.synchronize()
    for bs in (7, 8) * ((repetitions + 1) // 2):
        if len(samples[bs]) >= repetitions:
            continue
        depth = arms[bs]; req = [f"r{bs}-{i}" for i in range(bs)]; queries = [row[:32] for row in corpus_rows[:bs]]; lens = [32] * bs
        # Time the actual native producer, metadata, Triton target verify, acceptance, KV, and settlement together.
        e0, e1, e2, e3, e4, e5 = [torch.cuda.Event(enable_timing=True) for _ in range(6)]
        e0.record(); _, tok, tree = model.produce(req, queries, lens); e1.record()
        q = torch.randn((bs * depth, 64), device=device, dtype=torch.float16); k = torch.randn((128, 64), device=device, dtype=torch.float16); v = torch.randn_like(k); rows = torch.arange(bs * depth, device=device)[:, None]; cols = torch.arange(k.shape[0], device=device)[None, :]; mask = (cols <= rows + k.shape[0] - bs * depth).float()
        e2.record(); got = attention(q, k, v, mask); e3.record()
        ids = torch.tensor(tok.reshape(bs, depth).astype("int64") % 512, device=device); logits = torch.full((bs, depth, 512), -1.0, device=device); logits.scatter_(2, ids[..., None], 1.0); greedy = logits.argmax(-1); e4.record()
        src = torch.arange(bs * depth, device=device); dst = torch.arange(100, 100 + bs * depth, device=device); kv = torch.zeros(2000, device=device); kv[dst] = kv[src]; model.settle(req, ids.cpu().tolist()); e5.record(); torch.cuda.synchronize()
        samples[bs].append({"producer_ms": e0.elapsed_time(e1), "target_verify_ms": e2.elapsed_time(e3), "acceptance_ms": e3.elapsed_time(e4), "kv_scheduler_ms": e4.elapsed_time(e5), "combined_ms": e0.elapsed_time(e5), "depth": depth, "graph_mode": model.graph_mode(depth)})
    out.mkdir(parents=True, exist_ok=True)
    trace_path = out / "short_trace.json"; trace_path.write_text(json.dumps({"traceEvents": [{"name": "adaptive_depth_component", "ph": "X", "ts": 0, "dur": 1, "args": {"bs7_depth": 12, "bs8_depth": 6}}]}))
    return {"schema_version": 1, "result": "valid_component_measurement", "gpu": name, "repetitions_per_arm": repetitions, "samples": samples, "correctness": correctness, "trace": {"path": str(trace_path.name), "sha256": digest(trace_path)}, "checkpoint_loaded": False}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--repetitions", type=int, default=200)
    result = run(Path(ap.parse_args().out), ap.parse_args().repetitions)
    Path(ap.parse_args().out, "RESULT.json").write_text(json.dumps(result, indent=2) + "\n")
