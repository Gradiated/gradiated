#!/usr/bin/env python3
"""Exact BF16 lm_head Gram/spectrum and low-rank cost proxy."""
import json
import mmap
import struct
from pathlib import Path

import numpy as np

ROOT = Path("/root/.cache/glm47flash-bf16-75fce703")
SHARD = ROOT / "model-00047-of-00048.safetensors"
OUT = Path(__file__).with_name("HEAD_SPECTRUM_PROXY.json")


def tensor_view(path: Path, name: str):
    with path.open("rb") as f:
        header_len = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(header_len))
    meta = header[name]
    start, end = meta["data_offsets"]
    shape = tuple(meta["shape"])
    mm = np.memmap(path, mode="r", offset=8 + header_len + start,
                   dtype=np.uint16, shape=(end - start) // 2)
    return mm, shape


def bf16_to_f32(x):
    return (x.astype(np.uint32) << 16).view(np.float32)


def main():
    raw, shape = tensor_view(SHARD, "lm_head.weight")
    rows, cols = shape
    gram = np.zeros((cols, cols), dtype=np.float64)
    row_norm_sq = np.empty(rows, dtype=np.float64)
    chunk = 4096
    for i in range(0, rows, chunk):
        j = min(rows, i + chunk)
        x = bf16_to_f32(raw[i * cols * 1:j * cols * 1].reshape(j - i, cols))
        gram += x.T @ x
        row_norm_sq[i:j] = np.einsum("ij,ij->i", x, x)
    eig = np.linalg.eigvalsh(gram)[::-1]
    energy = np.maximum(eig, 0).cumsum() / max(float(np.maximum(eig, 0).sum()), 1e-30)
    ranks = [64, 128, 256, 384, 512, 768, 1024, 1536, 2048]
    bf16_bytes = rows * cols * 2
    records = []
    for r in ranks:
        factor_bytes = (rows + cols) * r * 2
        factor_flops = 2 * (rows + cols) * r
        full_flops = 2 * rows * cols
        records.append({
            "rank": r,
            "captured_frobenius_energy": float(energy[r - 1]),
            "relative_frobenius_error": float(np.sqrt(max(0.0, 1 - energy[r - 1]))),
            "factor_weight_bytes": factor_bytes,
            "weight_bytes_ratio": factor_bytes / bf16_bytes,
            "matmul_flops_ratio": factor_flops / full_flops,
            "ideal_flop_reduction": 1 - factor_flops / full_flops,
        })
    top = np.argsort(row_norm_sq)[::-1]
    shortlist = []
    for frac in (0.01, 0.05, 0.10, 0.25, 0.50):
        k = int(rows * frac)
        shortlist.append({
            "fraction": frac,
            "rows": k,
            "weight_bytes_ratio": k / rows,
            "top_row_norm_energy": float(row_norm_sq[top[:k]].sum() / row_norm_sq.sum()),
        })
    result = {
        "evidence_label": "measured exact local checkpoint tensor; semantics-changing proxy",
        "checkpoint_root": str(ROOT),
        "shard": SHARD.name,
        "tensor": "lm_head.weight",
        "shape": [rows, cols],
        "dtype": "bfloat16",
        "weight_bytes": bf16_bytes,
        "full_single_token_flops": 2 * rows * cols,
        "singular_value_squared_top10": [float(x) for x in eig[:10]],
        "effective_rank_99pct_frobenius": int(np.searchsorted(energy, 0.99) + 1),
        "effective_rank_999pct_frobenius": int(np.searchsorted(energy, 0.999) + 1),
        "low_rank": records,
        "norm_shortlist_proxy": shortlist,
        "row_norm_stats": {
            "min": float(row_norm_sq.min()), "median": float(np.median(row_norm_sq)),
            "p99": float(np.quantile(row_norm_sq, .99)), "max": float(row_norm_sq.max()),
        },
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
