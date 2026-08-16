#!/usr/bin/env python3
import hashlib
import json
import os
import struct
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("OMP_NUM_THREADS", "8")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "8")
ROOT = Path("/root/.cache/glm47flash-awq-ab31d120")
PROJECT = Path(__file__).parent
OUT = PROJECT / "artifacts" / "EXACT_LAYER24_SHARED_BASIS_FACTORIZATION.json"
INDEX = ROOT / "model.safetensors.index.json"
RANKS = (128, 256, 384, 512)
SEED = 240724


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def header(path):
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        return json.loads(f.read(n))


def raw_tensor(path, info):
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        f.seek(8 + n + info["data_offsets"][0])
        raw = f.read(info["data_offsets"][1] - info["data_offsets"][0])
    dtype = {"I32": "<u4", "I64": "<i8", "BF16": "<u2"}[info["dtype"]]
    return np.frombuffer(raw, dtype=dtype).reshape(info["shape"])


def dequant(root, wm, headers, base):
    shard = root / wm[base + ".weight_packed"]
    packed = raw_tensor(shard, headers[wm[base + ".weight_packed"]][base + ".weight_packed"])
    scale = raw_tensor(root / wm[base + ".weight_scale"], headers[wm[base + ".weight_scale"]][base + ".weight_scale"])
    q = ((packed[..., None] >> (4 * np.arange(8, dtype=np.uint32))) & 15).astype(np.int8)
    q[q >= 8] -= 16
    q = q.reshape(packed.shape[0], packed.shape[1] * 8)
    scale = (scale.astype(np.uint32) << 16).view(np.float32)
    return q.astype(np.float32) * np.repeat(scale, 32, axis=1)


def basis(mats, rank, axis):
    # Shared output basis is the top eigenspace of sum(W W^T); input is sum(W^T W).
    d = mats[0].shape[axis]
    cov = np.zeros((d, d), dtype=np.float64)
    for w in mats:
        a = w if axis == 0 else w.T
        cov += a @ a.T
    vals, vecs = np.linalg.eigh(cov)
    order = np.argsort(vals)[::-1][:rank]
    return vecs[:, order].astype(np.float32), vals.astype(np.float32)


def assess(mats, name, rng):
    out_dim, in_dim = mats[0].shape
    u, uvals = basis(mats, 512, 0)
    v, vvals = basis(mats, 512, 1)
    norms = np.array([np.linalg.norm(w) for w in mats])
    x = rng.standard_normal((256, in_dim), dtype=np.float32)
    rows = []
    for rank in RANKS:
        ur, vr = u[:, :rank], v[:, :rank]
        fro = []
        l2 = []
        cos = []
        for w, norm in zip(mats, norms):
            core = ur.T @ w @ vr
            approx = ur @ core @ vr.T
            fro.append(float(np.linalg.norm(w - approx) / norm))
            y = x @ w.T
            ya = (x @ vr) @ core.T @ ur.T
            l2.append(float(np.linalg.norm(y - ya) / np.linalg.norm(y)))
            cos.append(float(np.mean(np.sum(y * ya, axis=1) / (np.linalg.norm(y, axis=1) * np.linalg.norm(ya, axis=1)))))
        # W4 core with group-32 scales, BF16 shared bases; include both bases once.
        original_bytes = sum(w.nbytes for w in mats) / 2.0  # packed W4 payload only
        core_bytes = len(mats) * (rank * rank / 2.0 + rank * (rank // 32) * 2.0)
        factor_bytes = (out_dim * rank + in_dim * rank) * 2.0 + core_bytes
        # c32: shared input projection once per 32 tokens; each routed assignment gets core+output.
        k = 4
        shared = 2 * 32 * in_dim * rank
        routed = 32 * k * (2 * rank * rank + 2 * rank * out_dim)
        original_flops = 32 * k * 2 * in_dim * out_dim
        fact_flops = shared + routed
        rows.append({
            "rank": rank,
            "relative_frobenius": {"median": float(np.median(fro)), "worst": float(np.max(fro)), "per_expert": fro},
            "heldout_activation": {"relative_l2": {"median": float(np.median(l2)), "worst": float(np.max(l2))}, "cosine": {"median": float(np.median(cos)), "worst": float(np.min(cos))}},
            "singular_tail_proxy": float(np.sqrt(np.sum(uvals[rank:] ** 2)) / np.sqrt(np.sum(uvals ** 2))),
            "bytes": {"original_w4_payload": original_bytes, "factorized_w4_bases_and_cores": factor_bytes, "ratio": original_bytes / factor_bytes},
            "c32_active_flops": {"original": original_flops, "factorized_shared_core": fact_flops, "work_ratio": original_flops / fact_flops, "reduction": 1 - fact_flops / original_flops},
            "tile_legality": {"rank_multiple_32": rank % 32 == 0, "rank_multiple_64": rank % 64 == 0, "core_group32": rank % 32 == 0, "tensor_tile_128": rank % 128 == 0, "projected_shapes": {"shared_input": [32, in_dim, rank], "expert_core": [32, rank, rank], "shared_output": [32, rank, out_dim]}},
        })
    return {"projection": name, "shape": [out_dim, in_dim], "ranks": rows}


def main():
    started = time.time()
    idx = json.loads(INDEX.read_text())
    wm = idx["weight_map"]
    headers = {s: header(ROOT / s) for s in set(wm.values())}
    rng = np.random.default_rng(SEED)
    projections = {}
    for proj in ("gate_proj", "up_proj", "down_proj"):
        bases = [f"model.layers.24.mlp.experts.{i}.{proj}" for i in range(64)]
        mats = [dequant(ROOT, wm, headers, b) for b in bases]
        projections[proj] = assess(mats, proj, rng)
    result = {
        "schema_version": 1, "decision": "APPROXIMATION_CLOSE", "scope": "exact local layer-24 current-AWQ dequantized weights; synthetic architecture-cost evidence; no GPU/runtime/provider",
        "checkpoint": {"root": str(ROOT), "revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881", "index_sha256": sha256(INDEX), "layer": 24, "experts": 64, "top_k": 4, "group_size": 32},
        "method": "deterministic two-sided shared bases from sum(W W^T) and sum(W^T W), expert-specific dense reduced cores subsequently represented as group-32 W4; held-out Gaussian activations",
        "seed": SEED, "c32_rows": 32, "fused_moe_wall_share": 0.12374, "component_path_gate": 1.63, "projections": projections, "elapsed_seconds": time.time() - started,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"elapsed_seconds": result["elapsed_seconds"], "artifact": str(OUT), "summaries": {p: [{k: r[k] for k in ("rank", "relative_frobenius", "heldout_activation", "c32_active_flops", "tile_legality")} for r in d["ranks"]] for p, d in projections.items()}}, indent=2))


if __name__ == "__main__":
    main()
