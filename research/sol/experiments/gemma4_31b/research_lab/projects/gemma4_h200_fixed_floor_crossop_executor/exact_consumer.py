#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import statistics
import time
from types import SimpleNamespace

import torch

from fused_qkv_kv_cache import (
    CacheDestination,
    qkv_norm_rope_cache_store,
    qkv_norm_rope_inplace,
)
from sglang.srt.layers.rotary_embedding import get_rope
from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool


MODEL = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
SOURCE_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
PINNED_MEMORY_POOL_SHA256 = (
    "37f9915a2945c7bb389212eed65eb770cb9e3fa6976d0778b6831d2ac29d7bdd"
)


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)]


def timed_ms(fn, warmups: int, iterations: int) -> dict[str, object]:
    for _ in range(warmups):
        fn()
    torch.cuda.synchronize()
    samples = []
    for _ in range(iterations):
        begin = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        begin.record()
        fn()
        end.record()
        end.synchronize()
        samples.append(float(begin.elapsed_time(end)))
    return {
        "samples_ms": samples,
        "median_ms": statistics.median(samples),
        "p10_ms": percentile(samples, 0.10),
        "p90_ms": percentile(samples, 0.90),
    }


def metrics(actual: torch.Tensor, reference: torch.Tensor) -> dict[str, object]:
    actual_f32 = actual.float()
    reference_f32 = reference.float()
    delta = actual_f32 - reference_f32
    reference_rms = torch.sqrt(torch.mean(reference_f32.square())).clamp_min(1e-12)
    return {
        "all_finite": bool(torch.isfinite(actual_f32).all().item()),
        "max_abs": float(delta.abs().max().item()),
        "normalized_rmse": float(
            (torch.sqrt(torch.mean(delta.square())) / reference_rms).item()
        ),
    }


def make_pool(tokens: int, kv_heads: int, head_dim: int) -> MHATokenToKVPool:
    return MHATokenToKVPool(
        size=tokens + 1,
        page_size=1,
        dtype=torch.float8_e5m2,
        head_num=kv_heads,
        head_dim=head_dim,
        layer_num=1,
        device="cuda",
        enable_memory_saver=False,
        enable_alt_stream=False,
    )


def run_case(
    *,
    tokens: int,
    kv_heads: int,
    head_dim: int,
    local: bool,
    warmups: int,
    iterations: int,
) -> dict[str, object]:
    torch.manual_seed(20260727 + tokens + head_dim)
    q_heads = 32
    width = (q_heads + 2 * kv_heads) * head_dim
    q_size = q_heads * head_dim
    kv_size = kv_heads * head_dim
    base = torch.randn((tokens, width), dtype=torch.bfloat16, device="cuda")
    q_weight = torch.randn((head_dim,), dtype=torch.bfloat16, device="cuda")
    k_weight = torch.randn((head_dim,), dtype=torch.bfloat16, device="cuda")
    positions = torch.arange(tokens, dtype=torch.int64, device="cuda")
    slots = torch.arange(1, tokens + 1, dtype=torch.int64, device="cuda")
    rope_parameters = (
        {
            "base": 10000.0,
            "rope_scaling": {"rope_type": "default"},
            "partial_rotary_factor": 1.0,
        }
        if local
        else {
            "base": 1000000.0,
            "rope_scaling": {"rope_type": "proportional"},
            "partial_rotary_factor": 0.25,
        }
    )
    rope = get_rope(
        head_dim,
        rotary_dim=head_dim,
        max_position=max(8192, tokens + 1),
        **rope_parameters,
        is_neox_style=True,
    ).cuda()
    rope(positions, base[:, :q_size].clone(), base[:, q_size : q_size + kv_size].clone())

    baseline_qkv = base.clone()
    candidate_qkv = base.clone()
    baseline_pool = make_pool(tokens, kv_heads, head_dim)
    candidate_pool = make_pool(tokens, kv_heads, head_dim)
    layer = SimpleNamespace(layer_id=0)
    candidate_destination = CacheDestination(
        slots,
        *candidate_pool.get_kv_buffer(0),
    )

    qkv_norm_rope_inplace(
        baseline_qkv,
        q_weight,
        k_weight,
        positions,
        rope.cos_sin_cache,
        num_q_heads=q_heads,
        num_kv_heads=kv_heads,
        head_dim=head_dim,
        eps=1e-6,
    )
    baseline_snapshot = baseline_qkv.clone()
    baseline_k = baseline_qkv[:, q_size : q_size + kv_size].view(
        tokens, kv_heads, head_dim
    )
    baseline_v = baseline_qkv[:, q_size + kv_size :].view(
        tokens, kv_heads, head_dim
    )
    if local:
        baseline_pool.set_kv_buffer(
            layer, slots, baseline_k, baseline_v, 1.0, 1.0
        )
    else:
        baseline_pool.set_kv_buffer(
            layer, slots, baseline_k.clone(), baseline_v.clone(), 1.0, 1.0
        )

    qkv_norm_rope_cache_store(
        candidate_qkv,
        q_weight,
        k_weight,
        positions,
        rope.cos_sin_cache,
        candidate_destination,
        num_q_heads=q_heads,
        num_kv_heads=kv_heads,
        head_dim=head_dim,
        eps=1e-6,
        k_scale=1.0,
        v_scale=1.0,
    )
    torch.cuda.synchronize()
    candidate_k, candidate_v = candidate_pool.get_kv_buffer(0)
    baseline_cache_k, baseline_cache_v = baseline_pool.get_kv_buffer(0)
    cache_match = {
        "key_bytewise_equal": bool(
            torch.equal(
                candidate_k[slots].view(torch.uint8),
                baseline_cache_k[slots].view(torch.uint8),
            )
        ),
        "value_bytewise_equal": bool(
            torch.equal(
                candidate_v[slots].view(torch.uint8),
                baseline_cache_v[slots].view(torch.uint8),
            )
        ),
    }
    qkv_error = metrics(candidate_qkv, baseline_snapshot)

    def baseline() -> None:
        baseline_qkv.copy_(base)
        qkv_norm_rope_inplace(
            baseline_qkv,
            q_weight,
            k_weight,
            positions,
            rope.cos_sin_cache,
            num_q_heads=q_heads,
            num_kv_heads=kv_heads,
            head_dim=head_dim,
            eps=1e-6,
        )
        key = baseline_qkv[:, q_size : q_size + kv_size].view(
            tokens, kv_heads, head_dim
        )
        value = baseline_qkv[:, q_size + kv_size :].view(
            tokens, kv_heads, head_dim
        )
        if local:
            baseline_pool.set_kv_buffer(layer, slots, key, value, 1.0, 1.0)
        else:
            baseline_pool.set_kv_buffer(
                layer, slots, key.clone(), value.clone(), 1.0, 1.0
            )

    def candidate() -> None:
        candidate_qkv.copy_(base)
        qkv_norm_rope_cache_store(
            candidate_qkv,
            q_weight,
            k_weight,
            positions,
            rope.cos_sin_cache,
            candidate_destination,
            num_q_heads=q_heads,
            num_kv_heads=kv_heads,
            head_dim=head_dim,
            eps=1e-6,
            k_scale=1.0,
            v_scale=1.0,
        )

    control = timed_ms(baseline, warmups, iterations)
    treatment = timed_ms(candidate, warmups, iterations)
    speedup = 1.0 - treatment["median_ms"] / control["median_ms"]
    consumed_checksum = float(
        candidate_k[slots].float().sum().item()
        + candidate_v[slots].float().sum().item()
    )
    passed = (
        qkv_error["normalized_rmse"] <= 1e-5
        and cache_match["key_bytewise_equal"]
        and cache_match["value_bytewise_equal"]
        and speedup > 0.0
    )
    return {
        "geometry": {
            "tokens": tokens,
            "q_heads": q_heads,
            "kv_heads": kv_heads,
            "head_dim": head_dim,
            "qkv_shape": [tokens, width],
            "cache_shape": [tokens + 2, kv_heads, head_dim],
            "qkv_dtype": "torch.bfloat16",
            "cache_dtype": "torch.float8_e5m2",
            "cache_layout": "NHD",
            "class": "local" if local else "global",
        },
        "correctness": {
            "qkv_vs_accepted_producer": qkv_error,
            "cache_vs_unfused_consumer": cache_match,
            "consumed_cache_checksum": consumed_checksum,
        },
        "timing": {
            "baseline": control,
            "candidate": treatment,
            "median_reduction_fraction": speedup,
        },
        "passed": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=31)
    parser.add_argument(
        "--tokens", type=int, nargs="+", default=[32, 118, 1409, 1631, 2048]
    )
    args = parser.parse_args()

    invocation = args.output.with_name("INVOCATION_STATE.json")
    atomic_json(
        invocation,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": False,
            "scientific_terminal_recorded": False,
            "updated_unix_s": time.time(),
        },
    )
    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    device = torch.cuda.get_device_properties(0)
    if device.major != 9 or "H200" not in device.name:
        raise RuntimeError(f"exact_h200_required:{device.name}:{device.major}.{device.minor}")
    source = pathlib.Path(__file__).with_name("fused_qkv_kv_cache.py")
    if sha256(source) != args.expected_source_sha256:
        raise RuntimeError("candidate_source_hash_mismatch")
    import sglang.srt.mem_cache.memory_pool as memory_pool

    memory_pool_source = pathlib.Path(memory_pool.__file__).resolve()
    if sha256(memory_pool_source) != PINNED_MEMORY_POOL_SHA256:
        raise RuntimeError("pinned_memory_pool_hash_mismatch")
    state = json.loads(invocation.read_text())
    state["candidate_cuda_invocation_started"] = True
    state["updated_unix_s"] = time.time()
    atomic_json(invocation, state)

    cases = []
    for tokens in args.tokens:
        cases.append(
            run_case(
                tokens=tokens,
                kv_heads=16,
                head_dim=256,
                local=True,
                warmups=args.warmups,
                iterations=args.iterations,
            )
        )
        cases.append(
            run_case(
                tokens=tokens,
                kv_heads=4,
                head_dim=512,
                local=False,
                warmups=args.warmups,
                iterations=args.iterations,
            )
        )
    terminal = {
        "schema_version": 1,
        "terminal_type": "fixed_floor_crossop_h200_exact_consumer",
        "model": MODEL,
        "revision": REVISION,
        "sglang_commit": SOURCE_COMMIT,
        "device": {
            "name": device.name,
            "compute_capability": [device.major, device.minor],
            "total_memory_bytes": device.total_memory,
        },
        "source": {
            "candidate": str(source),
            "candidate_sha256": sha256(source),
            "memory_pool": str(memory_pool_source),
            "memory_pool_sha256": sha256(memory_pool_source),
        },
        "cases": cases,
        "passed": all(case["passed"] for case in cases),
    }
    atomic_json(args.output, terminal)
    state["scientific_terminal_recorded"] = True
    state["updated_unix_s"] = time.time()
    atomic_json(invocation, state)
    if not terminal["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
