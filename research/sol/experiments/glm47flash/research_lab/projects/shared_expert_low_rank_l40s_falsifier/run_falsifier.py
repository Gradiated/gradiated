#!/usr/bin/env python3
"""Deterministic exact-BF16 shared-MLP low-rank falsifier.

The checkpoint is read through safetensors headers and mmap; factor payloads are
never written.  All arithmetic after BF16 decoding is float32 CPU arithmetic.
"""
import hashlib
import json
import mmap
import struct
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path("/root/.cache/glm47flash-awq-ab31d120")
INDEX = ROOT / "model.safetensors.index.json"
OUT = Path(__file__).with_name("SHARED_FACTOR_FALSIFIER.json")
SEED = 47047
LAYERS = range(1, 47)
RANKS = {"joint_gate_up_rank512_plus_down_rank512": 512,
         "independent_gate_up_down_rank384": 384}


def tensor_view(path: Path, name: str):
    with path.open("rb") as f:
        header_len = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(header_len))
    meta = header[name]
    start, end = meta["data_offsets"]
    shape = tuple(meta["shape"])
    mm = np.memmap(path, mode="r", offset=8 + header_len + start,
                   dtype=np.uint16, shape=((end - start) // 2,))
    return mm, shape


def load_tensor(weight_map, name):
    raw, shape = tensor_view(ROOT / weight_map[name], name)
    # Copy only this tensor into CPU memory, then release the file mapping.
    bits = torch.from_numpy(np.asarray(raw).copy()).view(*shape)
    return (bits.to(torch.int32) << 16).view(torch.float32).contiguous()


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def randomized_factor(w, rank, seed):
    """Deterministic randomized truncated SVD, with a rank-sized payload."""
    m, n = w.shape
    q = min(n, rank + 24)
    g = torch.Generator(device="cpu"); g.manual_seed(seed)
    omega = torch.randn((n, q), generator=g, dtype=torch.float32)
    y = w @ omega
    for _ in range(1):
        y = w @ (w.T @ y)
    basis, _ = torch.linalg.qr(y, mode="reduced")
    b = basis.T @ w
    ub, s, vh = torch.linalg.svd(b, full_matrices=False)
    u = basis @ ub[:, :rank]
    s = s[:rank]
    vh = vh[:rank, :]
    approx = (u * s.unsqueeze(0)) @ vh
    err = torch.linalg.vector_norm(w - approx) / torch.linalg.vector_norm(w)
    return approx, float(err), [float(x) for x in s[:8]]


def cosine(a, b):
    return torch.sum(a * b, dim=1) / (torch.linalg.vector_norm(a, dim=1) * torch.linalg.vector_norm(b, dim=1)).clamp_min(1e-20)


def stats(values):
    a = np.asarray(values, dtype=np.float64)
    return {"median": float(np.median(a)), "p05": float(np.quantile(a, .05)),
            "p95": float(np.quantile(a, .95)), "max": float(np.max(a)),
            "min": float(np.min(a))}


def main():
    started = time.time()
    torch.set_num_threads(max(1, min(16, torch.get_num_threads())))
    weight_map = json.loads(INDEX.read_text())["weight_map"]
    names = [f"model.layers.{i}.mlp.shared_experts.{p}.weight"
             for i in LAYERS for p in ("gate_proj", "up_proj", "down_proj")]
    source_hashes = {str(INDEX): sha256(INDEX)}
    for shard in sorted({weight_map[n] for n in names}):
        source_hashes[str(ROOT / shard)] = sha256(ROOT / shard)

    torch.manual_seed(SEED)
    # Fixed Gaussian and heavy-tail hidden vectors, shared across all layers.
    xg = torch.randn((96, 2048), dtype=torch.float32)
    z = torch.randn((96, 2048), dtype=torch.float32)
    chi = torch.sqrt(torch.sum(torch.randn((96, 5), dtype=torch.float32) ** 2, dim=1) / 5.0).unsqueeze(1)
    xt = z / chi
    vectors = torch.cat((xg, xt), dim=0)
    families = {k: {"gate_up_frobenius": [], "down_frobenius": [],
                    "proxy_cosine": [], "proxy_relative_l2": [],
                    "layer_relative_l2": [], "finite": True} for k in RANKS}
    layer_records = []

    for layer in LAYERS:
        prefix = f"model.layers.{layer}.mlp.shared_experts"
        gate = load_tensor(weight_map, f"{prefix}.gate_proj.weight")
        up = load_tensor(weight_map, f"{prefix}.up_proj.weight")
        down = load_tensor(weight_map, f"{prefix}.down_proj.weight")
        joint = torch.cat((gate, up), dim=0)
        rec = {"layer": layer, "shapes": {"gate_up": list(joint.shape), "down": list(down.shape)}}
        for variant, rank in RANKS.items():
            if variant.startswith("joint"):
                japprox, je, js = randomized_factor(joint, rank, SEED + layer)
                dapprox, de, ds = randomized_factor(down, rank, SEED + 1000 + layer)
                gapprox, uapprox = japprox.split(1536, dim=0)
            else:
                gapprox, ge, gs = randomized_factor(gate, rank, SEED + 2000 + layer)
                uapprox, ue, us = randomized_factor(up, rank, SEED + 3000 + layer)
                dapprox, de, ds = randomized_factor(down, rank, SEED + 4000 + layer)
                je = float("nan")
            exact_gate = vectors @ gate.T
            exact_up = vectors @ up.T
            exact_down = torch.nn.functional.silu(exact_gate) * exact_up @ down.T
            proxy_gate = vectors @ gapprox.T
            proxy_up = vectors @ uapprox.T
            proxy_down = torch.nn.functional.silu(proxy_gate) * proxy_up @ dapprox.T
            co = cosine(exact_down, proxy_down)
            rel = torch.linalg.vector_norm(exact_down - proxy_down, dim=1) / torch.linalg.vector_norm(exact_down, dim=1).clamp_min(1e-20)
            vals = {"gate_up_frobenius": je if variant.startswith("joint") else float(np.sqrt((ge * ge + ue * ue) / 2)),
                    "down_frobenius": de, "proxy_cosine": stats(co.numpy()),
                    "proxy_relative_l2": stats(rel.numpy()),
                    "layer_relative_l2": float(torch.linalg.vector_norm(exact_down - proxy_down) / torch.linalg.vector_norm(exact_down)),
                    "finite": bool(torch.isfinite(proxy_down).all()),
                    "top8_singular_values": {"gate_up": js, "down": ds} if variant.startswith("joint") else {"gate": gs, "up": us, "down": ds}}
            families[variant]["gate_up_frobenius"].append(vals["gate_up_frobenius"])
            families[variant]["down_frobenius"].append(vals["down_frobenius"])
            families[variant]["proxy_cosine"].extend(co.tolist())
            families[variant]["proxy_relative_l2"].extend(rel.tolist())
            families[variant]["layer_relative_l2"].append(vals["layer_relative_l2"])
            families[variant]["finite"] &= vals["finite"]
            rec[variant] = vals
        layer_records.append(rec)
        print(f"layer={layer} elapsed={time.time()-started:.1f}s", flush=True)
        del gate, up, down, joint, exact_gate, exact_up, exact_down

    for variant, f in families.items():
        f["gate_up_frobenius_stats"] = stats(f.pop("gate_up_frobenius"))
        f["down_frobenius_stats"] = stats(f.pop("down_frobenius"))
        f["proxy_cosine_stats"] = stats(f.pop("proxy_cosine"))
        f["proxy_relative_l2_stats"] = stats(f.pop("proxy_relative_l2"))
        f["layer_relative_l2_stats"] = stats(f.pop("layer_relative_l2"))

    result = {"decision": "pending", "evidence_label": "measured exact local BF16 weights; semantics-changing shared-MLP proxy",
              "checkpoint_root": str(ROOT), "checkpoint_index_sha256": source_hashes[str(INDEX)],
              "source_hashes": source_hashes, "seed": SEED, "layers": [1, 46],
              "vector_contract": {"gaussian": 96, "heavy_tail_studentized": 96, "hidden_width": 2048},
              "execution_accounting": {
                  "stock": {"gemm_launches": 3, "intermediates": ["gate_2048x1536", "up_2048x1536", "down_1536x2048"]},
                  "joint_gate_up_rank512_plus_down_rank512": {"gemm_launches": 4, "intermediates": ["shared_input_rank512", "joint_expansion_3072_split", "silu_product", "down_input_rank512"], "launch_delta": 1},
                  "independent_gate_up_down_rank384": {"gemm_launches": 6, "intermediates": ["gate_rank384", "up_rank384", "silu_product", "down_rank384"], "launch_delta": 3},
                  "note": "Counts explicit unfused low-rank GEMMs; a production fused kernel could change launch count but was not measured."},
              "variants": {}, "layer_records": layer_records,
              "economic": {"shared_layers": 46, "stock_layer_bytes": 18 * 2**20,
                            "stock_total_mib": 828, "endpoint_control_tok_s": 602.157121,
                            "endpoint_gate_tok_s": 620.221834, "minimum_optimistic_reduction": .035,
                            "minimum_component_reduction": .50,
                            "note": "Theoretical endpoint ceiling only; no runtime endpoint was run."},
              "runtime": {"seconds": time.time() - started, "cuda": False, "artifacts_written": [str(OUT)]}}
    for variant, f in families.items():
        reduction = .5277777778 if variant.startswith("joint") else .5625
        gates = {"component_reduction": reduction, "component_gate": reduction >= .5,
                 "endpoint_ceiling": (reduction * 0.07101),
                 "endpoint_gate": reduction * .07101 >= .035,
                 "frob_gate": f["gate_up_frobenius_stats"]["max"] <= .10 and f["down_frobenius_stats"]["max"] <= .10,
                 "proxy_gate": f["proxy_cosine_stats"]["median"] >= .99 and f["proxy_cosine_stats"]["p05"] >= .98 and f["proxy_relative_l2_stats"]["p95"] <= .10 and f["layer_relative_l2_stats"]["max"] <= .15 and f["finite"]}
        f["economic_reduction"] = reduction
        f["gates"] = gates
        result["variants"][variant] = f
    result["decision"] = "NOMINATE_SHARED_FACTOR_PROXY" if sum(all(v["gates"].values()) for v in result["variants"].values()) else "SHARED_FACTOR_CLOSE"
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"decision": result["decision"], "variants": result["variants"], "seconds": result["runtime"]["seconds"]}, indent=2))


if __name__ == "__main__":
    main()
