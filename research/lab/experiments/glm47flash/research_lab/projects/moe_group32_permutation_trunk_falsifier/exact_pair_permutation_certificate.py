#!/usr/bin/env python3
"""Bounded exact layer-24 group-32 coupled-permutation tail certificate."""
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
OUT = PROJECT / "artifacts" / "LAYER24_PAIR_GROUP32_PERMUTATION_CERTIFICATE.json"
INDEX = ROOT / "model.safetensors.index.json"
LAYER, A, B, GROUP, RANK = 24, 14, 46, 32, 256
PROJECTIONS = ("gate_proj", "up_proj", "down_proj")


def digest_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def header(path):
    with path.open("rb") as f:
        return json.loads(f.read(struct.unpack("<Q", f.read(8))[0]))


def raw_tensor(path, info):
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        f.seek(8 + n + info["data_offsets"][0])
        raw = f.read(info["data_offsets"][1] - info["data_offsets"][0])
    return np.frombuffer(raw, dtype={"I32": "<u4", "BF16": "<u2"}[info["dtype"]]).reshape(info["shape"]), raw


def load(wm, hs, expert, proj):
    base = f"model.layers.{LAYER}.mlp.experts.{expert}.{proj}"
    shard = ROOT / wm[base + ".weight_packed"]
    packed, packed_raw = raw_tensor(shard, hs[shard.name][base + ".weight_packed"])
    scales_u16, scales_raw = raw_tensor(shard, hs[shard.name][base + ".weight_scale"])
    q = ((packed[..., None] >> (4 * np.arange(8, dtype=np.uint32))) & 15).astype(np.int8)
    q[q >= 8] -= 16
    q = q.reshape(packed.shape[0], packed.shape[1] * 8)
    scales = (scales_u16.astype(np.uint32) << 16).view(np.float32)
    return q.astype(np.float32) * np.repeat(scales, GROUP, axis=1), {
        "packed_sha256": digest_bytes(packed_raw), "scale_sha256": digest_bytes(scales_raw),
        "packed_shape": list(packed.shape), "scale_shape": list(scales_u16.shape),
    }


def coupled_signatures(mats):
    # Full dequantized channel signatures, weighted equally by the three linears.
    chunks = []
    for proj in ("gate_proj", "up_proj"):
        w = mats[proj]
        chunks.append(w / max(float(np.linalg.norm(w)), 1e-30))
    w = mats["down_proj"]
    chunks.append(w.T / max(float(np.linalg.norm(w)), 1e-30))
    return np.concatenate(chunks, axis=1).astype(np.float32, copy=False)


def stable_assignment(cost):
    """Deterministic Kuhn-Munkres minimum assignment for the 32/48 square costs."""
    # The epsilon makes ties deterministic without changing any non-tie ordering.
    n = cost.shape[0]
    eps = np.finfo(np.float64).eps * max(1.0, float(np.max(cost)))
    a = cost + eps * (np.arange(n)[:, None] * n + np.arange(n)[None, :])
    # 1-indexed primal-dual Hungarian implementation; p[j] is row assigned to col j.
    u = np.zeros(n + 1, dtype=np.float64)
    v = np.zeros(n + 1, dtype=np.float64)
    p = np.zeros(n + 1, dtype=np.int64)
    way = np.zeros(n + 1, dtype=np.int64)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(n + 1, np.inf, dtype=np.float64)
        used = np.zeros(n + 1, dtype=bool)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], np.inf, 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = a[i0 - 1, j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = np.empty(n, dtype=np.int64)
    for j in range(1, n + 1):
        assignment[p[j] - 1] = j - 1
    return assignment


def main():
    started = time.time()
    idx = json.loads(INDEX.read_text())
    wm = idx["weight_map"]
    hs = {name: header(ROOT / name) for name in set(wm.values())}
    wa, wb, payload = {}, {}, {str(A): {}, str(B): {}}
    for proj in PROJECTIONS:
        wa[proj], payload[str(A)][proj] = load(wm, hs, A, proj)
        wb[proj], payload[str(B)][proj] = load(wm, hs, B, proj)
    sa, sb = coupled_signatures(wa), coupled_signatures(wb)
    # Squared Euclidean exact full-signature cost, computed from the Gram matrix.
    aa = np.sum(sa.astype(np.float64) ** 2, axis=1)
    bb = np.sum(sb.astype(np.float64) ** 2, axis=1)
    cost = np.maximum(aa[:, None] + bb[None, :] - 2.0 * (sa.astype(np.float64) @ sb.astype(np.float64).T), 0.0)
    groups = sa.shape[0] // GROUP
    group_cost = np.empty((groups, groups), dtype=np.float64)
    within = {}
    for ga in range(groups):
        for gb in range(groups):
            block = cost[ga * GROUP:(ga + 1) * GROUP, gb * GROUP:(gb + 1) * GROUP]
            p = stable_assignment(block)
            group_cost[ga, gb] = float(block[np.arange(GROUP), p].sum())
            within[(ga, gb)] = p
    group_map = stable_assignment(group_cost)
    perm = np.empty(sa.shape[0], dtype=np.int64)
    for ga, gb in enumerate(group_map):
        perm[ga * GROUP:(ga + 1) * GROUP] = gb * GROUP + within[(ga, int(gb))]
    invariant = {}
    rng = np.random.default_rng(240716)
    x = rng.standard_normal((7, wa["gate_proj"].shape[1]), dtype=np.float32)
    max_relative = 0.0
    for label, mats in (("expert14", wa), ("expert46", wb)):
        g, u, d = mats["gate_proj"], mats["up_proj"], mats["down_proj"]
        if label == "expert46":
            g, u, d = g[perm], u[perm], d[:, perm]
        y = (np.silu if hasattr(np, "silu") else lambda z: z / (1.0 + np.exp(-z)))(x @ g.T) * (x @ u.T)
        out = y @ d.T
        if label == "expert46":
            g0, u0, d0 = wb["gate_proj"], wb["up_proj"], wb["down_proj"]
            y0 = (np.silu if hasattr(np, "silu") else lambda z: z / (1.0 + np.exp(-z)))(x @ g0.T) * (x @ u0.T)
            out0 = y0 @ d0.T
            rel = float(np.linalg.norm(out - out0) / max(np.linalg.norm(out0), 1e-30))
            max_relative = rel
            invariant["expert46_permuted_vs_original_relative_l2"] = rel
    tails = {}
    for proj in PROJECTIONS:
        aligned = wb[proj][perm] if proj != "down_proj" else wb[proj][:, perm]
        diff = wa[proj] - aligned
        singular = np.linalg.svd(diff, compute_uv=False)
        tail = float(np.linalg.norm(singular[RANK:]))
        tolerance = 0.1 * (float(np.linalg.norm(wa[proj])) + float(np.linalg.norm(wb[proj])))
        tails[proj] = {"shape": list(diff.shape), "tail_fro": tail, "tolerance": tolerance,
                       "margin_tail_minus_tolerance": tail - tolerance, "tail_over_tolerance": tail / tolerance,
                       "singular_value_257": float(singular[RANK])}
    failed = [p for p, r in tails.items() if r["margin_tail_minus_tolerance"] > 1e-6]
    result = {
        "schema_version": 1,
        "decision": "PERMUTATION_CLOSE" if failed or max_relative > 1e-5 else "PAIR_SCREEN_SURVIVES",
        "scope": "exact local layer-24 dequantized W4 tensors; CPU only; no provider/GPU/checkpoint/shared-code mutation",
        "checkpoint": {"root": str(ROOT), "revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881", "index_sha256": digest(INDEX)},
        "pair": [A, B], "group_size": GROUP, "difference_rank": RANK,
        "payload": payload,
        "solver": {"objective": "minimum squared Euclidean distance of full normalized coupled gate-row/up-row/down-column signatures; exact within-group Hungarian then group Hungarian", "tie_breaking": "lowest lexicographic row/column via machine-epsilon perturbation", "group_map_expert14_to_expert46": group_map.tolist(), "within_group_maps": [within[(g, int(group_map[g]))].tolist() for g in range(groups)], "permutation_new_channel_to_old_expert46_channel": perm.tolist(), "objective_value": float(group_cost[np.arange(groups), group_map].sum())},
        "invariants": {"function": invariant, "max_relative_l2": max_relative, "group32_payload_association": "Each output-hidden group remains a 32-channel packed W4 payload with its original one BF16 scale; group moves copy a packed/scale pair and within-group nibble moves retain that group's shared scale.", "permutation_is_bijection": bool(np.array_equal(np.sort(perm), np.arange(perm.size)))},
        "tails": tails, "failed_projections": failed, "elapsed_seconds": time.time() - started,
        "next_action": "terminal close; rank-tail necessary condition fails after permitted alignment" if failed else "conditionally fit all 64 experts in this bounded turn",
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("decision", "failed_projections", "tails", "elapsed_seconds")}, indent=2))


if __name__ == "__main__":
    main()
