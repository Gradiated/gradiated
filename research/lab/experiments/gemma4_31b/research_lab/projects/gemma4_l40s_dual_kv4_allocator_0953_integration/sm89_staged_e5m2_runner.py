#!/usr/bin/env python3
"""Fixed dual-KV4 producers staged through stock SGLang E5M2 decode attention."""

from __future__ import annotations

import argparse
import hashlib
import importlib
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
LOCAL_DIM, LOCAL_HEADS, LOCAL_TOKENS = 256, 16, 1024
GLOBAL_DIM, GLOBAL_HEADS, GLOBAL_TOKENS = 512, 4, 4571
QUERY_HEADS = 32
WARMUPS, REPEATS, MAX_SPLITS = 5, 31, 8
SEED = 20260728
STOCK_SOURCE_SHA256 = "1040f43a9ea579b944aa037b585997f8d7b585d85f459a1b1f420002b4bd092a"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def append_marker(root: Path, arm: str, state: str) -> None:
    with (root / "ARM_MARKERS.jsonl").open("a") as stream:
        stream.write(json.dumps(
            {"arm": arm, "state": state, "at_ns": time.time_ns()},
            sort_keys=True,
        ) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def distribution(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    return {
        "samples_ms": values,
        "min_ms": ordered[0],
        "p05_ms": ordered[max(0, math.ceil(0.05 * len(ordered)) - 1)],
        "median_ms": statistics.median(values),
        "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "max_ms": ordered[-1],
        "mean_ms": statistics.fmean(values),
    }


def timed(callable_) -> float:
    import torch

    start = torch.cuda.Event(enable_timing=True)
    stop = torch.cuda.Event(enable_timing=True)
    start.record()
    callable_()
    stop.record()
    stop.synchronize()
    return float(start.elapsed_time(stop))


def load_extensions(root: Path):
    from torch.utils.cpp_extension import load

    build = root / "torch_extensions"
    for name in ("local", "global", "decode"):
        (build / name).mkdir(parents=True, exist_ok=True)
    common = ["-O3", "--use_fast_math", "--ptxas-options=-v",
              "-gencode=arch=compute_89,code=sm_89"]
    local = load(
        name="staged_dual_local_sm89",
        sources=[str(root / "local_kv4_outlier_bindings.cpp"),
                 str(root / "local_kv4_outlier_cuda.cu")],
        extra_cflags=["-O3"], extra_cuda_cflags=common,
        build_directory=str(build / "local"), verbose=True,
    )
    global_ = load(
        name="staged_dual_global_sm89",
        sources=[str(root / "global_tiered_kv4_bindings.cpp"),
                 str(root / "global_tiered_kv4_cuda.cu")],
        extra_cflags=["-O3"], extra_cuda_cflags=common,
        build_directory=str(build / "global"), verbose=True,
    )
    decode = load(
        name="staged_dual_decode_sm89",
        sources=[str(root / "staged_e5m2_decode_bindings.cpp"),
                 str(root / "staged_e5m2_decode_cuda.cu")],
        extra_cflags=["-O3"], extra_cuda_cflags=common,
        build_directory=str(build / "decode"), verbose=True,
    )
    return local, global_, decode, build


def stock_call(module, case, output) -> None:
    module.decode_attention_fwd(
        case["query"], case["scratch_k"], case["scratch_v"], output,
        case["kv_indptr"], case["kv_indices"], case["attn_logits"],
        case["attn_lse"], case["num_kv_splits"], MAX_SPLITS,
        1.0 / math.sqrt(case["dim"]), 1.0, 1.0, page_size=1,
    )


def common_case(torch, dim: int, kv_heads: int, tokens: int) -> dict:
    kv_indices = torch.arange(tokens, dtype=torch.int64, device="cuda").repeat(BATCH)
    return {
        "dim": dim,
        "query": torch.randn(
            (BATCH, QUERY_HEADS, dim), dtype=torch.bfloat16, device="cuda"),
        "keys": torch.randn(
            (tokens, kv_heads, dim), dtype=torch.bfloat16, device="cuda"),
        "values": torch.randn(
            (tokens, kv_heads, dim), dtype=torch.bfloat16, device="cuda"),
        "scratch_k": torch.empty(
            (tokens, kv_heads, dim), dtype=torch.float8_e5m2, device="cuda"),
        "scratch_v": torch.empty(
            (tokens, kv_heads, dim), dtype=torch.float8_e5m2, device="cuda"),
        "kv_indptr": torch.arange(
            0, (BATCH + 1) * tokens, tokens, dtype=torch.int32, device="cuda"),
        "kv_indices": kv_indices,
        "num_kv_splits": torch.full(
            (BATCH,), MAX_SPLITS, dtype=torch.int32, device="cuda"),
        "attn_logits": torch.empty(
            (BATCH, QUERY_HEADS, MAX_SPLITS, dim),
            dtype=torch.float32, device="cuda"),
        "attn_lse": torch.empty(
            (BATCH, QUERY_HEADS, MAX_SPLITS),
            dtype=torch.float32, device="cuda"),
        "baseline_output": torch.empty(
            (BATCH, QUERY_HEADS, dim), dtype=torch.bfloat16, device="cuda"),
        "candidate_output": torch.empty(
            (BATCH, QUERY_HEADS, dim), dtype=torch.bfloat16, device="cuda"),
    }


def reference(torch, case) -> object:
    q = case["query"].reshape(BATCH, case["keys"].shape[1], -1, case["dim"])
    q = q.permute(1, 2, 0, 3).float()
    k = case["keys"].permute(1, 0, 2).float()
    v = case["values"].permute(1, 0, 2).float()
    scores = torch.einsum("hgrd,hsd->hgrs", q, k) / math.sqrt(case["dim"])
    output = torch.einsum(
        "hgrs,hsd->hgrd", torch.softmax(scores, dim=-1), v)
    return output.permute(2, 0, 1, 3).reshape(
        BATCH, QUERY_HEADS, case["dim"])


def errors(torch, output, truth) -> dict[str, object]:
    candidate, control = output.float().flatten(), truth.float().flatten()
    delta = candidate - control
    return {
        "finite": bool(torch.isfinite(candidate).all().item()),
        "relative_l2": float(
            torch.linalg.vector_norm(delta) /
            torch.linalg.vector_norm(control).clamp_min(1e-12)),
        "max_abs": float(delta.abs().max()),
        "cosine": float(torch.nn.functional.cosine_similarity(
            candidate, control, dim=0)),
        "checksum": float(candidate.abs().sum()),
    }


def run_arm(root: Path, name: str, case: dict, producer, decoder, stock) -> dict:
    import torch

    def baseline_pack():
        case["scratch_k"].copy_(case["keys"])
        case["scratch_v"].copy_(case["values"])

    def candidate_pack():
        producer()

    def candidate_decode():
        decoder()

    def baseline_attention():
        stock_call(stock, case, case["baseline_output"])

    def candidate_attention():
        stock_call(stock, case, case["candidate_output"])

    append_marker(root, name, "baseline_first_untimed_begin")
    baseline_pack()
    baseline_attention()
    torch.cuda.synchronize()
    append_marker(root, name, "baseline_first_untimed_complete")
    candidate_pack()
    candidate_decode()
    torch.cuda.synchronize()
    append_marker(root, name, "staged_decode_first_untimed_complete")
    candidate_attention()
    torch.cuda.synchronize()
    append_marker(root, name, "candidate_stock_consumer_first_untimed_complete")

    truth = reference(torch, case)
    numerical = {
        "baseline_vs_high_precision": errors(
            torch, case["baseline_output"], truth),
        "candidate_vs_high_precision": errors(
            torch, case["candidate_output"], truth),
        "candidate_vs_baseline": errors(
            torch, case["candidate_output"], case["baseline_output"]),
    }

    for _ in range(WARMUPS):
        baseline_pack(); baseline_attention()
        candidate_pack(); candidate_decode(); candidate_attention()
    torch.cuda.synchronize()
    rows = []
    for row in range(REPEATS):
        baseline_pack_ms = timed(baseline_pack)
        baseline_attention_ms = timed(baseline_attention)
        candidate_pack_ms = timed(candidate_pack)
        candidate_decode_ms = timed(candidate_decode)
        candidate_attention_ms = timed(candidate_attention)
        baseline_complete_ms = timed(
            lambda: (baseline_pack(), baseline_attention()))
        candidate_complete_ms = timed(
            lambda: (candidate_pack(), candidate_decode(),
                     candidate_attention()))
        rows.append({
            "row": row,
            "baseline_pack_ms": baseline_pack_ms,
            "baseline_attention_ms": baseline_attention_ms,
            "baseline_complete_ms": baseline_complete_ms,
            "candidate_pack_ms": candidate_pack_ms,
            "candidate_staged_decode_ms": candidate_decode_ms,
            "candidate_stock_attention_ms": candidate_attention_ms,
            "candidate_complete_ms": candidate_complete_ms,
            "complete_margin_ms": baseline_complete_ms - candidate_complete_ms,
        })
    atomic_json(root / f"{name.upper()}_ROWS.json", rows)
    timings = {
        key: distribution([float(row[key]) for row in rows])
        for key in rows[0] if key != "row"
    }
    return {
        "arm": name,
        "numerical": numerical,
        "timings": timings,
        "complete_margin_p05_positive":
            timings["complete_margin_ms"]["p05_ms"] > 0,
    }


def compiler_resources(build: Path) -> dict[str, object]:
    result = {}
    for library in build.rglob("*.so"):
        process = subprocess.run(
            ["cuobjdump", "--dump-resource-usage", str(library)],
            text=True, capture_output=True, check=False)
        result[str(library.relative_to(build))] = {
            "sha256": sha256(library),
            "returncode": process.returncode,
            "resource_text": process.stdout[-16000:],
            "stderr": process.stderr[-2000:],
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args()
    if args.artifact_root.exists():
        raise SystemExit("artifact_root_must_not_exist")
    out = args.artifact_root
    out.mkdir(parents=True)
    import torch

    if not torch.cuda.is_available():
        raise SystemExit("cuda_required")
    device = torch.cuda.get_device_properties(0)
    if (device.major, device.minor) != (8, 9) or "L40S" not in device.name:
        raise SystemExit(f"requires_l40s_sm89:{device.name}")
    stock = importlib.import_module(
        "sglang.srt.layers.attention.triton_ops.decode_attention")
    stock_path = Path(stock.__file__).resolve()
    if sha256(stock_path) != STOCK_SOURCE_SHA256:
        raise SystemExit(f"stock_consumer_source_mismatch:{sha256(stock_path)}")
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    local_ext, global_ext, decode_ext, build = load_extensions(Path(__file__).resolve().parent)
    atomic_json(out / "SCIENCE_STARTED.json", {
        "science_started": True,
        "device": device.name,
        "stock_consumer": str(stock_path),
        "stock_consumer_sha256": sha256(stock_path),
    })

    local = common_case(torch, LOCAL_DIM, LOCAL_HEADS, LOCAL_TOKENS)
    local_cache_k = torch.empty(
        (LOCAL_TOKENS, LOCAL_HEADS, 144), dtype=torch.uint8, device="cuda")
    local_cache_v = torch.empty_like(local_cache_k)
    local_slots = torch.arange(
        LOCAL_TOKENS, dtype=torch.int64, device="cuda")
    local_result = run_arm(
        out, "local", local,
        lambda: (local_ext.pack(local["keys"], local_slots, local_cache_k),
                 local_ext.pack(local["values"], local_slots, local_cache_v)),
        lambda: (decode_ext.decode_local(local_cache_k, local["scratch_k"]),
                 decode_ext.decode_local(local_cache_v, local["scratch_v"])),
        stock,
    )
    local_scratch_bytes = 2 * local["scratch_k"].numel()
    del local, local_cache_k, local_cache_v
    torch.cuda.empty_cache()

    global_ = common_case(torch, GLOBAL_DIM, GLOBAL_HEADS, GLOBAL_TOKENS)
    old_count = GLOBAL_TOKENS - LOCAL_TOKENS
    old_locations = torch.full(
        (GLOBAL_TOKENS,), -1, dtype=torch.int32, device="cuda")
    recent_locations = torch.full_like(old_locations, -1)
    old_locations[:old_count] = torch.arange(
        old_count, dtype=torch.int32, device="cuda")
    recent_locations[old_count:] = torch.arange(
        LOCAL_TOKENS, dtype=torch.int32, device="cuda")
    old_slots = torch.arange(old_count, dtype=torch.int64, device="cuda")
    recent_slots = torch.arange(
        old_count, GLOBAL_TOKENS, dtype=torch.int64, device="cuda")
    recent_k = torch.empty(
        (LOCAL_TOKENS, GLOBAL_HEADS, GLOBAL_DIM),
        dtype=torch.uint8, device="cuda")
    recent_v = torch.empty_like(recent_k)
    old_k = torch.empty(
        (old_count, GLOBAL_HEADS, 296), dtype=torch.uint8, device="cuda")
    old_v = torch.empty_like(old_k)
    global_result = run_arm(
        out, "global", global_,
        lambda: (
            global_ext.pack_old(global_["keys"][:old_count], old_slots,
                                 old_locations, old_k),
            global_ext.pack_old(global_["values"][:old_count], old_slots,
                                 old_locations, old_v),
            global_ext.store_recent(global_["keys"][old_count:], recent_slots,
                                     recent_locations, recent_k),
            global_ext.store_recent(global_["values"][old_count:], recent_slots,
                                     recent_locations, recent_v),
        ),
        lambda: (
            decode_ext.decode_global(
                recent_k, old_k, recent_locations, old_locations,
                global_["scratch_k"]),
            decode_ext.decode_global(
                recent_v, old_v, recent_locations, old_locations,
                global_["scratch_v"]),
        ),
        stock,
    )
    global_scratch_bytes = 2 * global_["scratch_k"].numel()
    numerical_pass = all(
        arm["numerical"]["candidate_vs_high_precision"]["finite"]
        and arm["numerical"]["candidate_vs_high_precision"]["cosine"] > 0.99
        and arm["numerical"]["candidate_vs_high_precision"]["checksum"] > 0
        for arm in (local_result, global_result)
    )
    performance_pass = all(
        arm["complete_margin_p05_positive"]
        for arm in (local_result, global_result)
    )
    terminal = {
        "schema_version": 1,
        "kind": "l40s_dual_kv4_staged_e5m2_stock_consumer",
        "sample_consumed": True,
        "classification": (
            "staged_stock_component_positive"
            if numerical_pass and performance_pass
            else "staged_stock_component_nonpositive"
        ),
        "fixed_contract": {
            "c32": BATCH, "decode_steps": DECODE_STEPS,
            "local_layers": LOCAL_LAYERS, "global_layers": GLOBAL_LAYERS,
            "page_size": 1, "warmups": WARMUPS, "repeats": REPEATS,
            "stock_consumer_source_sha256": STOCK_SOURCE_SHA256,
        },
        "scratch_ownership": {
            "dtype": "torch.float8_e5m2",
            "local_kv_bytes": local_scratch_bytes,
            "global_kv_bytes": global_scratch_bytes,
            "peak_bytes": max(local_scratch_bytes, global_scratch_bytes),
            "lifetime": "one arm invocation; local is freed before global allocation",
            "allocator": "caller-owned torch CUDA allocation; decoder borrows without retention",
            "lower_physical_margin_before_scratch_bytes": 1579875259,
            "lower_physical_margin_after_peak_scratch_bytes":
                1579875259 - max(local_scratch_bytes, global_scratch_bytes),
        },
        "arms": {"local": local_result, "global": global_result},
        "compiler_resources": compiler_resources(build),
        "complete_request_inequality_terms": {
            "local_s_per_request": "0.559375 * measured_local_complete_margin_ms",
            "global_s_per_request": "0.111875 * measured_global_complete_margin_ms",
            "integration_overhead": "not measured; component only",
            "price_normalized_boundary_s_per_request": 1.4776251501079425,
        },
    }
    atomic_json(out / "TERMINAL.json", terminal)
    atomic_json(out / "INVOCATION_COMPLETE.json", {
        "sample_consumed": True,
        "terminal_sha256": sha256(out / "TERMINAL.json"),
    })
    return 0 if numerical_pass and performance_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
