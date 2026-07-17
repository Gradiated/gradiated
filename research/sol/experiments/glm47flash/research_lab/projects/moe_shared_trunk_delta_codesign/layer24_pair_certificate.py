#!/usr/bin/env python3
"""Exact local layer-24 compressed-tensors W4 pair certificate."""
import hashlib
import json
import struct
import time
from pathlib import Path

import numpy as np

ROOT = Path("/root/.cache/glm47flash-awq-ab31d120")
PROJECT = Path(__file__).parent
OUT = PROJECT / "artifacts" / "LAYER24_GATE_PAIR_CERTIFICATE.json"
INDEX = ROOT / "model.safetensors.index.json"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def headers(path):
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        return json.loads(f.read(n))


def tensor_bytes(path, info):
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        f.seek(8 + n + info["data_offsets"][0])
        raw = f.read(info["data_offsets"][1] - info["data_offsets"][0])
    dtype = {"I32": "<u4", "I64": "<i8", "BF16": "<u2"}[info["dtype"]]
    return np.frombuffer(raw, dtype=dtype).reshape(info["shape"])


def tensor_sha256(path, info):
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        f.seek(8 + n + info["data_offsets"][0])
        raw = f.read(info["data_offsets"][1] - info["data_offsets"][0])
    return hashlib.sha256(raw).hexdigest()


def dequant(shard, header, base):
    packed = tensor_bytes(shard, header[base + ".weight_packed"])
    scales_u16 = tensor_bytes(shard, header[base + ".weight_scale"])
    # compressed-tensors INT4 is signed two's-complement, eight nibbles/int32;
    # scales are BF16 and cover contiguous groups of 32 input features.
    q = ((packed[..., None] >> (4 * np.arange(8, dtype=np.uint32))) & 15).astype(np.int8)
    q[q >= 8] -= 16
    q = q.reshape(packed.shape[0], packed.shape[1] * 8)
    scale_bits = scales_u16.astype(np.uint32) << 16
    scales = scale_bits.view(np.float32)
    return q.astype(np.float32) * np.repeat(scales, 32, axis=1)


def main():
    started = time.time()
    idx = json.loads(INDEX.read_text())
    wm = idx["weight_map"]
    shards = {s: headers(ROOT / s) for s in set(wm.values())}
    bases = [f"model.layers.24.mlp.experts.{i}.gate_proj" for i in range(64)]
    for b in bases:
        assert b + ".weight_packed" in shards[wm[b + ".weight_packed"]]
    matrices = {}
    norms = {}
    pair_rows = []
    for i in range(32):
        a, b = bases[i], bases[i + 32]
        wa = dequant(ROOT / wm[a + ".weight_packed"], shards[wm[a + ".weight_packed"]], a)
        wb = dequant(ROOT / wm[b + ".weight_packed"], shards[wm[b + ".weight_packed"]], b)
        na, nb = float(np.linalg.norm(wa)), float(np.linalg.norm(wb))
        d = wa - wb
        nd = float(np.linalg.norm(d))
        pair_rows.append({"i": i, "f": i + 32, "distance_fro": nd, "norm_i_fro": na, "norm_f_fro": nb})
        matrices[i], matrices[i + 32] = wa, wb
        norms[i], norms[i + 32] = na, nb
    chosen = max(pair_rows, key=lambda x: (x["distance_fro"], -x["i"]))
    i, f = chosen["i"], chosen["f"]
    diff = matrices[i] - matrices[f]
    singular = np.linalg.svd(diff, compute_uv=False)
    tail = float(np.linalg.norm(singular[256:]))
    tolerance = 0.1 * (norms[i] + norms[f])
    result = {
        "schema_version": 1,
        "decision": "PAIR_DIFFERENCE_CLOSE" if tail > tolerance else "PAIR_SCREEN_SURVIVES",
        "question": "Does one layer-24 gate-projection expert pair falsify rank-128 shared trunk plus deltas?",
        "scope": "offline exact local checkpoint; no provider, GPU, training, full decomposition, or runtime",
        "selection": {"rule": "max Frobenius distance among (i,i+32), i=0..31; ties lowest i", "chosen": chosen, "all_pairs": pair_rows},
        "tensor": {
            "layer": 24, "projection": "gate_proj", "shape": list(diff.shape), "group_size": 32,
            "quantization": "compressed-tensors symmetric signed INT4 W4A16; contiguous nibble unpack; BF16 group scales",
            "checkpoint_root": str(ROOT), "index_sha256": sha256(INDEX),
            "packed_hashes": {"i": tensor_sha256(ROOT / wm[bases[i] + ".weight_packed"], shards[wm[bases[i] + ".weight_packed"]][bases[i] + ".weight_packed"]), "f": tensor_sha256(ROOT / wm[bases[f] + ".weight_packed"], shards[wm[bases[f] + ".weight_packed"]][bases[f] + ".weight_packed"])},
            "scale_hashes": {"i": tensor_sha256(ROOT / wm[bases[i] + ".weight_scale"], shards[wm[bases[i] + ".weight_scale"]][bases[i] + ".weight_scale"]), "f": tensor_sha256(ROOT / wm[bases[f] + ".weight_scale"], shards[wm[bases[f] + ".weight_scale"]][bases[f] + ".weight_scale"])},
        },
        "certificate": {"difference_rank": 256, "tail_fro": tail, "tolerance": tolerance, "margin_tail_minus_tolerance": tail - tolerance, "tail_over_tolerance": tail / tolerance, "singular_value_257": float(singular[256])},
        "elapsed_seconds": time.time() - started,
        "next_action": "terminal close; no broad factorization" if tail > tolerance else "new admission required for fixed-seed rank-128 fitting",
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("decision", "selection", "certificate", "elapsed_seconds")}, indent=2))


if __name__ == "__main__":
    main()
