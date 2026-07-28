#!/usr/bin/env python3
"""Fixed c32 SM89 producer-plus-consumer component pairs for dual KV4.

This program deliberately has no checkpoint, model-server, or endpoint path.
It compiles the admitted local/global kernels, invokes their real producers and
consumers, and keeps each first CUDA call isolated by a synchronization marker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import time


BATCH = 32
DECODE_STEPS = 358
LOCAL_LAYERS = 50
GLOBAL_LAYERS = 10
LOCAL_DIM = 256
LOCAL_KV_HEADS = 16
GLOBAL_DIM = 512
GLOBAL_KV_HEADS = 4
QUERY_HEADS = 32
WINDOW = 1024
SEQUENCE = 4571
WARMUPS = 5
REPEATS = 31
SEED = 20260728


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def append_jsonl(path: Path, value: object) -> None:
    with path.open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def percentile(values: list[float], p: float) -> float:
    rows = sorted(values)
    position = (len(rows) - 1) * p
    lo, hi = math.floor(position), math.ceil(position)
    return rows[lo] if lo == hi else rows[lo] + (rows[hi] - rows[lo]) * (position - lo)


def distribution(values: list[float]) -> dict[str, float]:
    return {
        "min": min(values), "p05": percentile(values, 0.05),
        "median": statistics.median(values), "p95": percentile(values, 0.95),
        "max": max(values), "mean": statistics.fmean(values),
    }


def marker(root: Path, arm: str, state: str, **extra: object) -> None:
    value = {"arm": arm, "state": state, "at_ns": time.time_ns(), **extra}
    append_jsonl(root / "ARM_FIRST_CALL_MARKERS.jsonl", value)


def load_extensions(root: Path):
    from torch.utils.cpp_extension import load

    build = root / "torch_extensions"
    build.mkdir(exist_ok=True)
    local = load(
        name="dual_kv4_local_sm89",
        sources=[str(root / "local_kv4_outlier_bindings.cpp"), str(root / "local_kv4_outlier_cuda.cu")],
        extra_cflags=["-O3"],
        extra_cuda_cflags=["-O3", "--use_fast_math", "--ptxas-options=-v", "-gencode=arch=compute_89,code=sm_89"],
        build_directory=str(build / "local"), verbose=True,
    )
    global_ = load(
        name="dual_kv4_global_sm89",
        sources=[str(root / "global_tiered_kv4_bindings.cpp"), str(root / "global_tiered_kv4_cuda.cu")],
        extra_cflags=["-O3"],
        extra_cuda_cflags=["-O3", "--use_fast_math", "--ptxas-options=-v", "-gencode=arch=compute_89,code=sm_89"],
        build_directory=str(build / "global"), verbose=True,
    )
    return local, global_, build


def e5m2_pack(x):
    # This is the baseline E5M2 producer: one-byte E5M2 storage then BF16 use.
    return x.to(dtype=__import__("torch").float8_e5m2).to(dtype=x.dtype)


def e5m2_attention(query, keys, values, window: int | None):
    import torch

    rows, q_heads, dim = query.shape
    kv_heads = keys.shape[1]
    group = q_heads // kv_heads
    q = query.reshape(rows, kv_heads, group, dim).permute(1, 2, 0, 3).float()
    k = keys.permute(1, 0, 2).float()
    v = values.permute(1, 0, 2).float()
    if window is not None:
        k, v = k[:, -window:], v[:, -window:]
    scores = torch.einsum("hgrd,hsd->hgrs", q, k) / math.sqrt(dim)
    probs = torch.softmax(scores, dim=-1)
    return torch.einsum("hgrs,hsd->hgrd", probs, v).permute(2, 0, 1, 3).reshape(rows, q_heads, dim).to(query.dtype)


def local_case(root: Path, extension, query, keys, values):
    import torch

    cache_k = torch.empty((WINDOW, LOCAL_KV_HEADS, 144), dtype=torch.uint8, device="cuda")
    cache_v = torch.empty_like(cache_k)
    loc = torch.arange(WINDOW, dtype=torch.int64, device="cuda")
    qo = torch.arange(BATCH + 1, dtype=torch.int32, device="cuda")
    indptr = torch.arange(0, BATCH * WINDOW + 1, WINDOW, dtype=torch.int32, device="cuda")
    indices = torch.arange(BATCH * WINDOW, dtype=torch.int64, device="cuda").reshape(BATCH, WINDOW) % WINDOW
    indices = indices.flatten()

    def baseline():
        return e5m2_attention(query, e5m2_pack(keys), e5m2_pack(values), WINDOW)

    def candidate():
        extension.pack(keys[-WINDOW:].contiguous(), loc, cache_k)
        extension.pack(values[-WINDOW:].contiguous(), loc, cache_v)
        return extension.paged_attention(query, cache_k, cache_v, qo, indptr, indices, WINDOW, 1, 1.0 / math.sqrt(LOCAL_DIM), True)

    return run_pair(root, "local", baseline, candidate)


def global_case(root: Path, extension, query, keys, values):
    import torch

    physical = SEQUENCE
    old_count = physical - WINDOW
    old_locations = torch.full((physical,), -1, dtype=torch.int32, device="cuda")
    recent_locations = torch.full_like(old_locations, -1)
    old_locations[:old_count] = torch.arange(old_count, dtype=torch.int32, device="cuda")
    recent_locations[old_count:] = torch.arange(WINDOW, dtype=torch.int32, device="cuda")
    recent_k = torch.empty((WINDOW, GLOBAL_KV_HEADS, GLOBAL_DIM), dtype=torch.uint8, device="cuda")
    recent_v = torch.empty_like(recent_k)
    old_k = torch.empty((old_count, GLOBAL_KV_HEADS, 296), dtype=torch.uint8, device="cuda")
    old_v = torch.empty_like(old_k)
    old_phys = torch.arange(old_count, dtype=torch.int64, device="cuda")
    recent_phys = torch.arange(old_count, physical, dtype=torch.int64, device="cuda")
    qo = torch.arange(BATCH + 1, dtype=torch.int32, device="cuda")
    indptr = torch.arange(0, BATCH * SEQUENCE + 1, SEQUENCE, dtype=torch.int32, device="cuda")
    indices = torch.arange(BATCH * SEQUENCE, dtype=torch.int64, device="cuda") % physical

    def baseline():
        return e5m2_attention(query, e5m2_pack(keys), e5m2_pack(values), None)

    def candidate():
        extension.pack_old(keys[:old_count].contiguous(), old_phys, old_locations, old_k)
        extension.pack_old(values[:old_count].contiguous(), old_phys, old_locations, old_v)
        extension.store_recent(keys[old_count:].contiguous(), recent_phys, recent_locations, recent_k)
        extension.store_recent(values[old_count:].contiguous(), recent_phys, recent_locations, recent_v)
        return extension.paged_attention(query, recent_k, recent_v, old_k, old_v, recent_locations, old_locations, qo, indptr, indices, 1, 1.0 / math.sqrt(GLOBAL_DIM))

    return run_pair(root, "global", baseline, candidate)


def run_pair(root: Path, arm: str, baseline, candidate) -> dict:
    import torch

    marker(root, arm, "first_untimed_begin")
    baseline_out = baseline()
    torch.cuda.synchronize()
    marker(root, arm, "baseline_first_untimed_complete")
    candidate_out = candidate()
    torch.cuda.synchronize()
    marker(root, arm, "candidate_first_untimed_complete")
    if not torch.isfinite(candidate_out).all().item():
        raise RuntimeError(f"{arm}_candidate_nonfinite")
    delta = (candidate_out.float() - baseline_out.float()).flatten()
    base = baseline_out.float().flatten()
    error = {
        "finite": True,
        "relative_l2": float(torch.linalg.vector_norm(delta) / torch.clamp(torch.linalg.vector_norm(base), min=1e-12)),
        "max_abs": float(delta.abs().max()),
        "cosine": float(torch.nn.functional.cosine_similarity(candidate_out.float().flatten(), base, dim=0)),
    }
    for _ in range(WARMUPS):
        baseline(); candidate()
    torch.cuda.synchronize()
    rows = []
    for row in range(REPEATS):
        first, second = (baseline, candidate) if row % 2 == 0 else (candidate, baseline)
        start = time.perf_counter_ns(); first(); torch.cuda.synchronize(); first_ms = (time.perf_counter_ns() - start) / 1e6
        start = time.perf_counter_ns(); second(); torch.cuda.synchronize(); second_ms = (time.perf_counter_ns() - start) / 1e6
        baseline_ms, candidate_ms = (first_ms, second_ms) if row % 2 == 0 else (second_ms, first_ms)
        rows.append({"row": row, "baseline_complete_ms": baseline_ms, "candidate_complete_ms": candidate_ms, "margin_ms": baseline_ms - candidate_ms})
    atomic_json(root / f"{arm.upper()}_ROWS.json", rows)
    margins = [row["margin_ms"] for row in rows]
    return {"arm": arm, "error": error, "baseline_complete_ms": distribution([r["baseline_complete_ms"] for r in rows]), "candidate_complete_ms": distribution([r["candidate_complete_ms"] for r in rows]), "margin_ms": distribution(margins), "promotion_margin_positive": percentile(margins, 0.05) > 0}


def compiler_resources(build: Path) -> dict:
    rows = {}
    for library in build.rglob("*.so"):
        output = subprocess.run(["cuobjdump", "--dump-resource-usage", str(library)], text=True, capture_output=True, check=False)
        rows[str(library.relative_to(build))] = {"sha256": sha256(library), "returncode": output.returncode, "resource_text": output.stdout[-12000:], "stderr": output.stderr[-2000:]}
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    if args.artifact_root.exists():
        raise SystemExit("artifact_root_must_not_exist")
    root = Path(__file__).resolve().parent
    out = args.artifact_root
    out.mkdir(parents=True)
    import torch
    if not torch.cuda.is_available():
        raise SystemExit("cuda_required")
    properties = torch.cuda.get_device_properties(0)
    if properties.major != 8 or properties.minor != 9 or "L40S" not in properties.name:
        raise SystemExit(f"requires_l40s_sm89_got:{properties.name}:sm_{properties.major}{properties.minor}")
    atomic_json(out / "SCIENCE_STARTED.json", {"science_started": True, "device": properties.name, "compute_capability": [properties.major, properties.minor], "seed": SEED})
    torch.manual_seed(SEED); torch.cuda.manual_seed_all(SEED)
    local_ext, global_ext, build = load_extensions(root)
    local_q = torch.randn((BATCH, QUERY_HEADS, LOCAL_DIM), dtype=torch.bfloat16, device="cuda")
    local_k = torch.randn((WINDOW, LOCAL_KV_HEADS, LOCAL_DIM), dtype=torch.bfloat16, device="cuda")
    local_v = torch.randn_like(local_k)
    global_q = torch.randn((BATCH, QUERY_HEADS, GLOBAL_DIM), dtype=torch.bfloat16, device="cuda")
    global_k = torch.randn((SEQUENCE, GLOBAL_KV_HEADS, GLOBAL_DIM), dtype=torch.bfloat16, device="cuda")
    global_v = torch.randn_like(global_k)
    local = local_case(out, local_ext, local_q, local_k, local_v)
    global_ = global_case(out, global_ext, global_q, global_k, global_v)
    terminal = {"schema_version": 1, "kind": "l40s_dual_kv4_sm89_component", "sample_consumed": True, "fixed_contract": {"c32": BATCH, "decode_steps": DECODE_STEPS, "local_layers": LOCAL_LAYERS, "global_layers": GLOBAL_LAYERS, "warmups": WARMUPS, "repeats": REPEATS, "page_size": 1}, "arms": {"local": local, "global": global_}, "compiler_resources": compiler_resources(build), "complete_request_inequality_terms": {"local_s_per_request": "0.559375 * measured_local_margin_ms", "global_s_per_request": "0.111875 * measured_global_margin_ms", "integration_overhead": "not measured here; no endpoint claim", "price_normalized_boundary_s_per_request": 1.4776251501079425}, "classification": "component_positive" if local["promotion_margin_positive"] and global_["promotion_margin_positive"] else "complete_producer_consumer_nonpositive"}
    atomic_json(out / "TERMINAL.json", terminal)
    atomic_json(out / "INVOCATION_COMPLETE.json", {"terminal_sha256": sha256(out / "TERMINAL.json"), "sample_consumed": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
