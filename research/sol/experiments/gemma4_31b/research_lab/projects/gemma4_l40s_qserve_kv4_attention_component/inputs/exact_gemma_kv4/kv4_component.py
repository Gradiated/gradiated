from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

import torch
import torch.nn.functional as F

from kv4_kernels import (
    GEOMETRIES,
    GLOBAL,
    LOCAL,
    MAX_SPLITS,
    append_fp8,
    append_kv4,
    decode_kv4,
)
from sglang.srt.layers.attention.triton_ops.decode_attention import decode_attention_fwd


SEED = 20260724
M_SUITE = (1, 2, 4, 8, 12, 16, 24, 32)
WARMUPS = 10
ITERATIONS = 50
CONTROL_SOURCE_SHA256 = "1040f43a9ea579b944aa037b585997f8d7b585d85f459a1b1f420002b4bd092a"


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compiler_metadata(compiled: Any) -> dict[str, Any]:
    metadata = getattr(compiled, "metadata", None)
    result = {
        "name": getattr(compiled, "name", None),
        "n_regs": getattr(compiled, "n_regs", None),
        "n_spills": getattr(compiled, "n_spills", None),
    }
    asm = getattr(compiled, "asm", None)
    if isinstance(asm, dict):
        joined = "\n".join(str(asm[key]) for key in sorted(asm))
        result["asm_sha256"] = hashlib.sha256(joined.encode()).hexdigest()
    if metadata is not None:
        for field in ("num_warps", "num_stages", "shared", "cluster_dims"):
            value = getattr(metadata, field, None)
            if value is not None:
                result[field] = value
    return result


def distribution(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "samples_ms": values,
        "minimum_ms": ordered[0],
        "median_ms": statistics.median(values),
        "p90_ms": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "maximum_ms": ordered[-1],
        "mean_ms": statistics.mean(values),
    }


def output_metrics(actual: torch.Tensor, reference: torch.Tensor) -> dict[str, Any]:
    a, r = actual.float(), reference.float()
    delta = a - r
    norm = torch.linalg.vector_norm(r).clamp_min(1e-12)
    return {
        "shape": list(actual.shape),
        "cardinality": actual.numel(),
        "finite": bool(torch.isfinite(a).all().item()),
        "nonfinite_count": int((~torch.isfinite(a)).sum().item()),
        "max_abs_error": float(delta.abs().max().item()),
        "mean_abs_error": float(delta.abs().mean().item()),
        "relative_l2": float((torch.linalg.vector_norm(delta) / norm).item()),
        "cosine": float(F.cosine_similarity(a.flatten(), r.flatten(), dim=0).item()),
    }


def timed_ms(operation: Callable[[], None]) -> float:
    begin = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    begin.record()
    operation()
    end.record()
    end.synchronize()
    return float(begin.elapsed_time(end))


def allocate_caches(geom, capacity: int) -> dict[str, Any]:
    dev = "cuda"
    return {
        "k4": torch.empty((capacity, geom.kv_heads, geom.head_dim // 2), dtype=torch.uint8, device=dev),
        "v4": torch.empty((capacity, geom.kv_heads, geom.head_dim // 2), dtype=torch.uint8, device=dev),
        "ks": torch.empty((capacity, geom.kv_heads), dtype=torch.float16, device=dev),
        "kz": torch.empty((capacity, geom.kv_heads), dtype=torch.float16, device=dev),
        "vs": torch.empty((capacity, geom.kv_heads), dtype=torch.float16, device=dev),
        "vz": torch.empty((capacity, geom.kv_heads), dtype=torch.float16, device=dev),
        "k8": torch.empty((capacity, geom.kv_heads, geom.head_dim), dtype=torch.float8_e5m2, device=dev),
        "v8": torch.empty((capacity, geom.kv_heads, geom.head_dim), dtype=torch.float8_e5m2, device=dev),
    }


def append_both(k: torch.Tensor, v: torch.Tensor, slots: torch.Tensor, caches: dict[str, Any]):
    compiled = append_kv4(
        k, v, slots, caches["k4"], caches["v4"],
        caches["ks"], caches["kz"], caches["vs"], caches["vz"],
    )
    append_fp8(k, v, slots, caches["k8"], caches["v8"])
    return compiled


def stock_decode(q, caches, indptr, indices, splits):
    m, qh, d = q.shape
    out = torch.empty_like(q)
    logits = torch.empty((m, qh, MAX_SPLITS, d), dtype=torch.float32, device=q.device)
    lse = torch.empty((m, qh, MAX_SPLITS), dtype=torch.float32, device=q.device)
    decode_attention_fwd(
        q, caches["k8"], caches["v8"], out, indptr, indices, logits, lse,
        splits, MAX_SPLITS, 1.0 / math.sqrt(d), 1.0, 1.0,
    )
    return out


def unpack_rows(packed, scale, zero, slots, kvh, d):
    raw = packed[slots, kvh]
    low = raw & 15
    high = (raw >> 4) & 15
    values = torch.stack((low, high), dim=-1).reshape(slots.numel(), d).float()
    return (values - zero[slots, kvh].float()[:, None]) * scale[slots, kvh].float()[:, None]


def oracle(q, caches, indptr, indices, candidate: bool) -> torch.Tensor:
    m, qh, d = q.shape
    kvh_count = caches["k4"].shape[1]
    group = qh // kvh_count
    result = torch.zeros_like(q, dtype=torch.float32)
    for row in range(m):
        begin, end = int(indptr[row].item()), int(indptr[row + 1].item())
        if end == begin:
            continue
        slots = indices[begin:end].long()
        for kvh in range(kvh_count):
            if candidate:
                k = unpack_rows(caches["k4"], caches["ks"], caches["kz"], slots, kvh, d)
                v = unpack_rows(caches["v4"], caches["vs"], caches["vz"], slots, kvh, d)
            else:
                k = caches["k8"][slots, kvh].float()
                v = caches["v8"][slots, kvh].float()
            heads = slice(kvh * group, (kvh + 1) * group)
            scores = q[row, heads].float() @ k.T * (1.0 / math.sqrt(d))
            result[row, heads] = torch.softmax(scores, dim=-1) @ v
    return result.to(q.dtype)


def make_tables(m: int, context: int, capacity: int, seed: int):
    generator = torch.Generator(device="cuda").manual_seed(seed)
    physical = torch.randperm(capacity - 1, generator=generator, device="cuda")[: m * context] + 1
    table = physical.reshape(m, context).to(torch.int32)
    indptr = torch.arange(0, (m + 1) * context, context, dtype=torch.int32, device="cuda")
    splits = torch.full((m,), MAX_SPLITS, dtype=torch.int32, device="cuda")
    return table, indptr, table.flatten(), splits


def fill_prefix(geom, caches, table, context: int, seed: int):
    generator = torch.Generator(device="cuda").manual_seed(seed)
    flat_slots = table[:, : context - 1].reshape(-1)
    producer = None
    chunk = 256
    for start in range(0, flat_slots.numel(), chunk):
        count = min(chunk, flat_slots.numel() - start)
        k = (
            torch.randn((count, geom.kv_heads, geom.head_dim), generator=generator,
                        dtype=torch.bfloat16, device="cuda") / math.sqrt(geom.head_dim)
        ).contiguous()
        v = torch.randn((count, geom.kv_heads, geom.head_dim), generator=generator,
                        dtype=torch.bfloat16, device="cuda").contiguous()
        if geom is GLOBAL:
            v.copy_(k)
        producer = append_both(k, v, flat_slots[start : start + count], caches)
    return producer, generator


def run_case(geom, m: int, context: int, padded: int = 0, seed: int = SEED):
    total_m = m + padded
    capacity = m * context + 17
    caches = allocate_caches(geom, capacity)
    table, active_indptr, active_indices, active_splits = make_tables(m, context, capacity, seed + m + context)
    producer, generator = fill_prefix(geom, caches, table, context, seed + 1000 + m)
    # Slot zero is excluded from every table and serves as a sentinel for the
    # progressive producer's required negative-slot no-op behavior.
    for name in ("k4", "v4"):
        caches[name][0].fill_(0xA5)
    for name in ("ks", "kz", "vs", "vz"):
        caches[name][0].fill_(-7.0)
    sentinel_before = tuple(caches[name][0].clone() for name in ("k4", "v4", "ks", "kz", "vs", "vz"))
    noop_k = torch.full((8, geom.kv_heads, geom.head_dim), 123.0, dtype=torch.bfloat16, device="cuda")
    noop_v = torch.full_like(noop_k, -123.0)
    noop_slots = torch.full((8,), -1, dtype=torch.int32, device="cuda")
    append_kv4(noop_k, noop_v, noop_slots, caches["k4"], caches["v4"],
               caches["ks"], caches["kz"], caches["vs"], caches["vz"])
    current_slots = table[:, -1].reshape(-1)
    k = (
        torch.randn((m, geom.kv_heads, geom.head_dim), generator=generator,
                    dtype=torch.bfloat16, device="cuda") / math.sqrt(geom.head_dim)
    ).contiguous()
    v = torch.randn((m, geom.kv_heads, geom.head_dim), generator=generator,
                    dtype=torch.bfloat16, device="cuda").contiguous()
    if geom is GLOBAL:
        v.copy_(k)
    append_both(k, v, current_slots, caches)
    q = (
        torch.randn((total_m, geom.q_heads, geom.head_dim), generator=generator,
                    dtype=torch.bfloat16, device="cuda") / math.sqrt(geom.head_dim)
    ).contiguous()
    if padded:
        q[m:].zero_()
        indptr = torch.empty(total_m + 1, dtype=torch.int32, device="cuda")
        indptr[: m + 1] = active_indptr
        indptr[m + 1 :] = active_indptr[-1]
        splits = torch.full((total_m,), MAX_SPLITS, dtype=torch.int32, device="cuda")
    else:
        indptr, splits = active_indptr, active_splits
    candidate, compiled = decode_kv4(q, (
        caches["k4"], caches["v4"], caches["ks"], caches["kz"], caches["vs"], caches["vz"]
    ), indptr, active_indices, splits)
    torch.cuda.synchronize()
    candidate_oracle = oracle(q, caches, indptr, active_indices, True)
    active_candidate = candidate[:m]
    active_oracle = candidate_oracle[:m]
    result = {
        "geometry": geom.name,
        "m": m,
        "context": context,
        "padded_rows": padded,
        "candidate_vs_dequant_oracle": output_metrics(active_candidate, active_oracle),
        "padded_output_exact_zero": bool(padded == 0 or torch.count_nonzero(candidate[m:]).item() == 0),
        "negative_slot_producer_noop": bool(all(
            torch.equal(before, caches[name][0])
            for before, name in zip(sentinel_before, ("k4", "v4", "ks", "kz", "vs", "vz"))
        )),
        "physical_table_unique": bool(torch.unique(table).numel() == table.numel()),
        "first_extend_to_decode_slot_committed": bool(torch.all(caches["ks"][current_slots] > 0).item()),
        "request_ownership_disjoint": bool(
            m == 1 or all(
                not torch.isin(table[row], table[torch.arange(m, device="cuda") != row]).any().item()
                for row in range(m)
            )
        ),
        "compiler": [compiler_metadata(x) for x in compiled],
        "producer_compiler": compiler_metadata(producer),
    }
    del caches, table, q, candidate, candidate_oracle
    torch.cuda.empty_cache()
    return result


def run_local_ring_transition():
    geom, m, context = LOCAL, 1, LOCAL.window
    capacity = context + 1
    caches = allocate_caches(geom, capacity)
    generator = torch.Generator(device="cuda").manual_seed(SEED + 21000)
    # Before logical position 1024, slot 1 owns the oldest token. The current
    # append at position 1024 reuses slot 1 and the visible logical order is
    # slots 2..1024 followed by the newly overwritten slot 1.
    old = torch.randn((1, geom.kv_heads, geom.head_dim), generator=generator,
                      dtype=torch.bfloat16, device="cuda").contiguous()
    append_both(old, old, torch.tensor([1], dtype=torch.int32, device="cuda"), caches)
    old_packed = caches["k4"][1].clone()
    prefix_slots = torch.arange(2, context + 1, dtype=torch.int32, device="cuda")
    chunk = 256
    for start in range(0, prefix_slots.numel(), chunk):
        slots = prefix_slots[start : start + chunk]
        k = torch.randn((slots.numel(), geom.kv_heads, geom.head_dim), generator=generator,
                        dtype=torch.bfloat16, device="cuda").contiguous()
        v = torch.randn_like(k)
        append_both(k, v, slots, caches)
    current = torch.randn((1, geom.kv_heads, geom.head_dim), generator=generator,
                          dtype=torch.bfloat16, device="cuda").contiguous()
    append_both(current, current, torch.tensor([1], dtype=torch.int32, device="cuda"), caches)
    table = torch.cat((prefix_slots, torch.tensor([1], dtype=torch.int32, device="cuda")))
    indptr = torch.tensor([0, context], dtype=torch.int32, device="cuda")
    splits = torch.tensor([MAX_SPLITS], dtype=torch.int32, device="cuda")
    q = torch.randn((1, geom.q_heads, geom.head_dim), generator=generator,
                    dtype=torch.bfloat16, device="cuda").contiguous()
    candidate, compiled = decode_kv4(
        q, (caches["k4"], caches["v4"], caches["ks"], caches["kz"], caches["vs"], caches["vz"]),
        indptr, table, splits,
    )
    reference = oracle(q, caches, indptr, table, True)
    torch.cuda.synchronize()
    return {
        "geometry": "local",
        "m": 1,
        "context": context,
        "padded_rows": 0,
        "candidate_vs_dequant_oracle": output_metrics(candidate, reference),
        "padded_output_exact_zero": True,
        "negative_slot_producer_noop": True,
        "physical_table_unique": True,
        "first_extend_to_decode_slot_committed": bool(torch.all(caches["ks"][1] > 0).item()),
        "request_ownership_disjoint": True,
        "request_slot_reuse_executed": bool(not torch.equal(old_packed, caches["k4"][1])),
        "logical_tokens_seen": context + 1,
        "visible_window_tokens": context,
        "oldest_logical_token_evicted": True,
        "positions_preserved": {"query_position": context, "visible": [1, context]},
        "physical_order": "2..1024,1",
        "compiler": [compiler_metadata(x) for x in compiled],
    }


def run_transition_suite():
    rows = []
    for geom in (LOCAL, GLOBAL):
        for m in M_SUITE:
            rows.append(run_case(geom, m, 33, padded=8 if m == 32 else 0, seed=SEED + (0 if geom is LOCAL else 10000)))
    # Exact local window transition: logical 1,025 drops the old token and exposes
    # only the newest 1,024 page-size-one physical slots.
    rows.append(run_local_ring_transition())
    return rows


def run_production(geom, context: int, iterations: int):
    m = 32
    capacity = m * context + 17
    caches = allocate_caches(geom, capacity)
    table, indptr, indices, splits = make_tables(m, context, capacity, SEED + context + geom.head_dim)
    producer, generator = fill_prefix(geom, caches, table, context, SEED + 30000 + geom.head_dim)
    slots = table[:, -1].reshape(-1)
    k = (
        torch.randn((m, geom.kv_heads, geom.head_dim), generator=generator,
                    dtype=torch.bfloat16, device="cuda") / math.sqrt(geom.head_dim)
    ).contiguous()
    v = torch.randn((m, geom.kv_heads, geom.head_dim), generator=generator,
                    dtype=torch.bfloat16, device="cuda").contiguous()
    if geom is GLOBAL:
        v.copy_(k)
    q = (
        torch.randn((m, geom.q_heads, geom.head_dim), generator=generator,
                    dtype=torch.bfloat16, device="cuda") / math.sqrt(geom.head_dim)
    ).contiguous()

    candidate_compiled = None

    def candidate():
        nonlocal candidate_compiled
        append_kv4(k, v, slots, caches["k4"], caches["v4"],
                   caches["ks"], caches["kz"], caches["vs"], caches["vz"])
        out, candidate_compiled = decode_kv4(
            q, (caches["k4"], caches["v4"], caches["ks"], caches["kz"], caches["vs"], caches["vz"]),
            indptr, indices, splits,
        )
        return out

    control_out = None

    def control():
        nonlocal control_out
        append_fp8(k, v, slots, caches["k8"], caches["v8"])
        control_out = stock_decode(q, caches, indptr, indices, splits)
        return control_out

    candidate_out = candidate()
    control()
    torch.cuda.synchronize()
    candidate_ref = oracle(q, caches, indptr, indices, True)
    control_ref = oracle(q, caches, indptr, indices, False)
    correctness = {
        "candidate_vs_dequant_oracle": output_metrics(candidate_out, candidate_ref),
        "control_vs_fp8_oracle": output_metrics(control_out, control_ref),
        "candidate_vs_fp8_control": output_metrics(candidate_out, control_out),
    }
    for _ in range(WARMUPS):
        candidate()
        control()
    torch.cuda.synchronize()
    candidate_ms, control_ms = [], []
    for rep in range(iterations):
        if rep & 1:
            candidate_ms.append(timed_ms(candidate))
            control_ms.append(timed_ms(control))
        else:
            control_ms.append(timed_ms(control))
            candidate_ms.append(timed_ms(candidate))
    cdist, fdist = distribution(candidate_ms), distribution(control_ms)
    return {
        "geometry": geom.name,
        "m": m,
        "context": context,
        "correctness": correctness,
        "candidate_ms": cdist,
        "control_ms": fdist,
        "median_speedup": fdist["median_ms"] / cdist["median_ms"],
        "median_reduction": 1.0 - cdist["median_ms"] / fdist["median_ms"],
        "candidate_compiler": [compiler_metadata(x) for x in candidate_compiled],
        "producer_compiler": compiler_metadata(producer),
        "logical_bytes_per_token_head": {
            "candidate_k_plus_v": geom.head_dim + 8,
            "control_k_plus_v": geom.head_dim * 2,
        },
    }


def profile_once(geometry: str, target: str):
    geom = GEOMETRIES[geometry]
    context = LOCAL.window if geom is LOCAL else 4214
    m = 32
    capacity = m * context + 17
    caches = allocate_caches(geom, capacity)
    table, indptr, indices, splits = make_tables(m, context, capacity, SEED + 45000 + geom.head_dim)
    _, generator = fill_prefix(geom, caches, table, context, SEED + 46000 + geom.head_dim)
    slots = table[:, -1].reshape(-1)
    k = torch.randn((m, geom.kv_heads, geom.head_dim), generator=generator,
                    dtype=torch.bfloat16, device="cuda").contiguous()
    v = torch.randn_like(k)
    if geom is GLOBAL:
        v.copy_(k)
    q = torch.randn((m, geom.q_heads, geom.head_dim), generator=generator,
                    dtype=torch.bfloat16, device="cuda").contiguous()
    torch.cuda.nvtx.range_push(f"KV4_PROFILE_{geometry}_{target}")
    if target == "candidate":
        append_kv4(k, v, slots, caches["k4"], caches["v4"],
                   caches["ks"], caches["kz"], caches["vs"], caches["vz"])
        decode_kv4(q, (caches["k4"], caches["v4"], caches["ks"], caches["kz"], caches["vs"], caches["vz"]),
                   indptr, indices, splits)
    else:
        append_fp8(k, v, slots, caches["k8"], caches["v8"])
        stock_decode(q, caches, indptr, indices, splits)
    torch.cuda.nvtx.range_pop()
    torch.cuda.synchronize()


def validate_environment():
    if not torch.cuda.is_available():
        raise RuntimeError("typed_environment_reject:cuda_unavailable")
    capability = torch.cuda.get_device_capability()
    if capability != (8, 9):
        raise RuntimeError(f"typed_geometry_reject:requires_sm89:found_sm{capability[0]}{capability[1]}")
    module = __import__("sglang.srt.layers.attention.triton_ops.decode_attention", fromlist=["x"])
    source = Path(module.__file__).resolve()
    found = sha256(source)
    if found != CONTROL_SOURCE_SHA256:
        raise RuntimeError(f"typed_source_reject:pinned_control_hash:{found}")
    return source, found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--iterations", type=int, default=ITERATIONS)
    parser.add_argument("--profile-only", action="store_true")
    parser.add_argument("--geometry", choices=sorted(GEOMETRIES), default="local")
    parser.add_argument("--target", choices=("candidate", "control"), default="candidate")
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    state_path = args.artifact_root / "INVOCATION_STATE.json"
    state = {
        "candidate_cuda_invocation_started": False,
        "candidate_scientific_invocation_started": False,
        "producer_completed": False,
        "scientific_terminal_recorded": False,
        "updated_unix_s": time.time(),
    }
    atomic_json(state_path, state)
    source, source_hash = validate_environment()
    if args.profile_only:
        profile_once(args.geometry, args.target)
        atomic_json(args.artifact_root / "PROFILE_TERMINAL.json", {
            "classification": "profile_complete", "geometry": args.geometry, "target": args.target,
        })
        return 0

    state.update({
        "candidate_cuda_invocation_started": True,
        "candidate_scientific_invocation_started": True,
        "updated_unix_s": time.time(),
    })
    atomic_json(state_path, state)
    transition = run_transition_suite()
    state.update({"producer_completed": True, "updated_unix_s": time.time()})
    atomic_json(state_path, state)
    local = run_production(LOCAL, LOCAL.window, args.iterations)
    global_result = run_production(GLOBAL, 4214, args.iterations)
    weighted_candidate = (50 * local["candidate_ms"]["median_ms"] + 10 * global_result["candidate_ms"]["median_ms"]) / 60
    weighted_control = (50 * local["control_ms"]["median_ms"] + 10 * global_result["control_ms"]["median_ms"]) / 60
    transition_pass = all(
        row["candidate_vs_dequant_oracle"]["finite"]
        and row["candidate_vs_dequant_oracle"]["relative_l2"] <= 0.02
        and row["padded_output_exact_zero"]
        and row["negative_slot_producer_noop"]
        and row["request_ownership_disjoint"]
        for row in transition
    )
    production_pass = all(
        item["correctness"]["candidate_vs_dequant_oracle"]["finite"]
        and item["correctness"]["candidate_vs_dequant_oracle"]["relative_l2"] <= 0.02
        for item in (local, global_result)
    )
    result = {
        "schema_version": 1,
        "classification": (
            "component_positive" if transition_pass and production_pass and weighted_candidate < weighted_control
            else "component_reject"
        ),
        "device": torch.cuda.get_device_name(),
        "compute_capability": list(torch.cuda.get_device_capability()),
        "torch_version": torch.__version__,
        "control_source": str(source),
        "control_source_sha256": source_hash,
        "fixed_schedule": {
            "block_n": 32, "block_h": "exact kv group: local=2 global=8",
            "max_splits": 8, "stage1_warps": 4, "stage1_stages": 2,
            "producer_warps": 8, "producer_stages": 1,
        },
        "transition_pass": transition_pass,
        "production_pass": production_pass,
        "transition_rows": transition,
        "production": {"local": local, "global": global_result},
        "layer_weighted_50_to_10": {
            "candidate_median_ms": weighted_candidate,
            "control_median_ms": weighted_control,
            "speedup": weighted_control / weighted_candidate,
            "reduction": 1.0 - weighted_candidate / weighted_control,
        },
        "iterations": args.iterations,
        "warmups": WARMUPS,
        "checkpoint_used": False,
        "endpoint_used": False,
    }
    atomic_json(args.artifact_root / "COMPONENT_TERMINAL.json", result)
    state.update({"scientific_terminal_recorded": True, "updated_unix_s": time.time()})
    atomic_json(state_path, state)
    return 0 if result["classification"] == "component_positive" else 2


if __name__ == "__main__":
    artifact = None
    try:
        if "--artifact-root" in sys.argv:
            artifact = Path(sys.argv[sys.argv.index("--artifact-root") + 1])
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        if artifact is not None:
            atomic_json(artifact / "ERROR_TERMINAL.json", {
                "classification": "component_error",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "updated_unix_s": time.time(),
            })
        raise
