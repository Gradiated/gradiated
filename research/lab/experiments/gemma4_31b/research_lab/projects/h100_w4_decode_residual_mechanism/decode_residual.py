#!/usr/bin/env python3
"""Checkpoint-free c128 decode residual discriminator on the pinned H100 image."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import os
import statistics
import time
import traceback
from pathlib import Path

import torch
import vllm
from vllm.config import CacheConfig, VllmConfig, set_current_vllm_config
from vllm.forward_context import set_forward_context
from vllm.model_executor.layers.attention.attention import (
    Attention,
    unified_attention_with_output,
    unified_kv_cache_update,
)
from vllm.v1.attention.backends.triton_attn import TritonAttentionMetadata


BATCH = 128
PAGE = 16
STEPS = 358
LOCAL_LAYERS = 50
GLOBAL_LAYERS = 10
ENDPOINT_BATCH_WALL_SECONDS = 210.17596933300013
FIVE_PERCENT_BATCH_SECONDS = ENDPOINT_BATCH_WALL_SECONDS * 0.05
CASES = {
    "local": {"context": 1024, "q_heads": 32, "kv_heads": 16, "head_dim": 256, "window": 1024},
    "global": {"context": 4214, "q_heads": 32, "kv_heads": 4, "head_dim": 512, "window": None},
}


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def source_hash(value: object) -> str:
    return hashlib.sha256(inspect.getsource(value).encode()).hexdigest()


def config() -> VllmConfig:
    value = VllmConfig()
    value.model_config = type(
        "ModelConfig",
        (),
        {"dtype": torch.bfloat16, "head_dtype": None, "is_mm_prefix_lm": False},
    )()
    return value


def metadata(context: int, table: torch.Tensor, slots: torch.Tensor) -> TritonAttentionMetadata:
    return TritonAttentionMetadata(
        num_actual_tokens=BATCH,
        max_query_len=1,
        query_start_loc=torch.arange(BATCH + 1, device="cuda", dtype=torch.int32),
        max_seq_len=context,
        seq_lens=torch.full((BATCH,), context, device="cuda", dtype=torch.int32),
        block_table=table,
        slot_mapping=slots,
        seq_threshold_3D=None,
        num_par_softmax_segments=None,
        softmax_segm_output=None,
        softmax_segm_max=None,
        softmax_segm_expsum=None,
        use_cascade=False,
        common_prefix_len=0,
        cu_prefix_query_lens=None,
        prefix_kv_lens=None,
        suffix_kv_lens=None,
    )


def make_arm(label: str) -> dict:
    geometry = CASES[label]
    context = geometry["context"]
    q_heads = geometry["q_heads"]
    kv_heads = geometry["kv_heads"]
    head_dim = geometry["head_dim"]
    window = geometry["window"]
    name = f"decode_residual_{label}_fp8"
    current = config()
    cache = CacheConfig(
        cache_dtype="fp8_e4m3",
        sliding_window=window,
        enable_prefix_caching=False,
    )
    with set_current_vllm_config(current):
        layer = Attention(
            q_heads,
            head_dim,
            head_dim**-0.5,
            num_kv_heads=kv_heads,
            cache_config=cache,
            per_layer_sliding_window=window,
            prefix=name,
        )
    layer.to("cuda")
    backend = layer.attn_backend
    implementation = type(layer.impl)
    if "TritonAttention" not in implementation.__name__:
        raise RuntimeError(f"expected selected Triton FP8 consumer for {label}, got {implementation}")
    pages = math.ceil(context / PAGE)
    table = torch.arange(BATCH * pages, device="cuda", dtype=torch.int32).reshape(BATCH, pages)
    all_slots = (
        table.to(torch.int64).unsqueeze(-1) * PAGE
        + torch.arange(PAGE, device="cuda", dtype=torch.int64)
    ).reshape(-1)
    decode_slots = table[:, -1].to(torch.int64) * PAGE + (context - 1) % PAGE
    cache_shape = backend.get_kv_cache_shape(BATCH * pages, PAGE, kv_heads, head_dim, cache.cache_dtype)
    layer.kv_cache = torch.empty(cache_shape, dtype=layer.kv_cache_torch_dtype, device="cuda")

    generator = torch.Generator(device="cuda").manual_seed(20260718 + (0 if label == "local" else 1))
    fill_shape = (all_slots.numel(), kv_heads, head_dim)
    fill_key = torch.empty(fill_shape, device="cuda", dtype=torch.bfloat16).uniform_(-0.5, 0.5, generator=generator)
    fill_value = torch.empty(fill_shape, device="cuda", dtype=torch.bfloat16).uniform_(0.125, 0.875, generator=generator)
    fill_metadata = metadata(context, table, all_slots)
    with set_forward_context(
        {name: fill_metadata}, current, num_tokens=all_slots.numel(), slot_mapping={name: all_slots}
    ):
        unified_kv_cache_update(fill_key, fill_value, name)
    del fill_key, fill_value, all_slots
    torch.cuda.synchronize()

    query = torch.empty((BATCH, q_heads, head_dim), device="cuda", dtype=torch.bfloat16).uniform_(
        -0.25, 0.25, generator=generator
    )
    key = torch.empty((BATCH, kv_heads, head_dim), device="cuda", dtype=torch.bfloat16).uniform_(
        -0.5, 0.5, generator=generator
    )
    value = torch.empty((BATCH, kv_heads, head_dim), device="cuda", dtype=torch.bfloat16).uniform_(
        0.125, 0.875, generator=generator
    )
    output = torch.empty_like(query)
    arm = {
        "label": label,
        "name": name,
        "config": current,
        "layer": layer,
        "metadata": metadata(context, table, decode_slots),
        "slots": decode_slots,
        "query": query,
        "key": key,
        "value": value,
        "output": output,
        "identity": {
            **geometry,
            "batch": BATCH,
            "backend": f"{backend.__module__}.{backend.__name__}",
            "implementation": f"{implementation.__module__}.{implementation.__name__}",
            "cache_shape": list(cache_shape),
            "cache_storage_dtype": str(layer.kv_cache.dtype),
            "implementation_window": list(layer.impl.sliding_window),
        },
    }
    combined(arm)
    torch.cuda.synchronize()
    oracle = output_oracle(arm)
    if not oracle["pass"]:
        raise RuntimeError(f"{label} supported-route numerical sentinel failed: {oracle}")
    arm["identity"]["sentinel"] = oracle
    return arm


def context(arm: dict):
    return set_forward_context(
        {arm["name"]: arm["metadata"]},
        arm["config"],
        num_tokens=BATCH,
        slot_mapping={arm["name"]: arm["slots"]},
    )


def update_only(arm: dict) -> None:
    with context(arm):
        unified_kv_cache_update(arm["key"], arm["value"], arm["name"])


def attention_only(arm: dict) -> None:
    with context(arm):
        unified_attention_with_output(
            arm["query"], arm["key"], arm["value"], arm["output"], arm["name"]
        )


def combined(arm: dict) -> None:
    with context(arm):
        dependency = unified_kv_cache_update(arm["key"], arm["value"], arm["name"])
        unified_attention_with_output(
            arm["query"],
            arm["key"],
            arm["value"],
            arm["output"],
            arm["name"],
            kv_cache_dummy_dep=dependency,
        )


def output_oracle(arm: dict) -> dict:
    value = arm["output"].float()
    finite = bool(torch.isfinite(value).all())
    absolute_maximum = float(value.abs().max())
    mean = float(value.mean())
    return {
        "finite": finite,
        "nonzero": absolute_maximum > 1e-4,
        "abs_max": absolute_maximum,
        "mean": mean,
        "positive_mean": mean > 0.01,
        "pass": finite and absolute_maximum > 1e-4 and mean > 0.01,
    }


def timed(callable_value, warmups: int = 5, repetitions: int = 40) -> dict:
    for _ in range(warmups):
        callable_value()
    torch.cuda.synchronize()
    events = []
    walls = []
    for _ in range(repetitions):
        begin = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        started = time.perf_counter()
        begin.record()
        callable_value()
        end.record()
        end.synchronize()
        events.append(begin.elapsed_time(end))
        walls.append((time.perf_counter() - started) * 1000)
    return {
        "repetitions": repetitions,
        "event_ms": events,
        "wall_ms": walls,
        "event_ms_p50": statistics.median(events),
        "wall_ms_p50": statistics.median(walls),
        "finite_positive": all(math.isfinite(value) and value > 0 for value in events + walls),
    }


def mixed_loop(local: dict, global_arm: dict) -> dict:
    begin = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    torch.cuda.synchronize()
    started = time.perf_counter()
    begin.record()
    for _ in range(STEPS):
        for _ in range(LOCAL_LAYERS):
            combined(local)
        for _ in range(GLOBAL_LAYERS):
            combined(global_arm)
    end.record()
    end.synchronize()
    return {
        "calls": STEPS * (LOCAL_LAYERS + GLOBAL_LAYERS),
        "event_seconds": begin.elapsed_time(end) / 1000,
        "wall_seconds": time.perf_counter() - started,
        "local_oracle": output_oracle(local),
        "global_oracle": output_oracle(global_arm),
    }


def control_loops(local: dict) -> dict:
    calls = STEPS * (LOCAL_LAYERS + GLOBAL_LAYERS)
    started = time.perf_counter()
    for _ in range(calls):
        with context(local):
            pass
    scheduler_wall = time.perf_counter() - started

    scalar = torch.zeros((), device="cuda")
    begin = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    torch.cuda.synchronize()
    started = time.perf_counter()
    begin.record()
    for _ in range(calls):
        scalar.add_(1)
    end.record()
    end.synchronize()
    return {
        "calls": calls,
        "scheduler_context_wall_seconds": scheduler_wall,
        "trivial_cuda_launch_event_seconds": begin.elapsed_time(end) / 1000,
        "trivial_cuda_launch_wall_seconds": time.perf_counter() - started,
        "launch_scalar": float(scalar),
        "pass": float(scalar) == calls,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {"schema_version": 1, "stage": "c128_decode_residual", "pass": False}
    started = time.perf_counter()
    try:
        if "H100" not in torch.cuda.get_device_name() or torch.cuda.get_device_capability() != (9, 0):
            raise RuntimeError("expected one H100 SM90")
        torch.manual_seed(20260718)
        torch.cuda.reset_peak_memory_stats()
        result["runtime"] = {
            "gpu": torch.cuda.get_device_name(),
            "capability": list(torch.cuda.get_device_capability()),
            "vllm": vllm.__version__,
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "producer_source_sha256": source_hash(unified_kv_cache_update),
            "consumer_source_sha256": source_hash(unified_attention_with_output),
        }
        local = make_arm("local")
        global_arm = make_arm("global")
        result["routes"] = {"local": local["identity"], "global": global_arm["identity"]}
        components = {}
        for arm in (local, global_arm):
            components[arm["label"]] = {
                "fp8_kv_update": timed(lambda arm=arm: update_only(arm)),
                "paged_attention": timed(lambda arm=arm: attention_only(arm)),
                "combined": timed(lambda arm=arm: combined(arm)),
                "oracle": output_oracle(arm),
            }
        result["components"] = components
        result["controls"] = control_loops(local)
        result["mixed_358_step_layer_loop"] = mixed_loop(local, global_arm)
        estimate_event = STEPS / 1000 * (
            LOCAL_LAYERS
            * (components["local"]["fp8_kv_update"]["event_ms_p50"] + components["local"]["paged_attention"]["event_ms_p50"])
            + GLOBAL_LAYERS
            * (components["global"]["fp8_kv_update"]["event_ms_p50"] + components["global"]["paged_attention"]["event_ms_p50"])
        )
        mixed = result["mixed_358_step_layer_loop"]
        result["decision"] = {
            "component_sum_event_seconds": estimate_event,
            "mixed_event_seconds": mixed["event_seconds"],
            "mixed_wall_seconds": mixed["wall_seconds"],
            "mixed_service_seconds_per_request": mixed["wall_seconds"] / BATCH,
            "mixed_fraction_of_endpoint_batch_wall": mixed["wall_seconds"] / ENDPOINT_BATCH_WALL_SECONDS,
            "five_percent_endpoint_batch_seconds": FIVE_PERCENT_BATCH_SECONDS,
            "component_exceeds_five_percent_hurdle": mixed["wall_seconds"] >= FIVE_PERCENT_BATCH_SECONDS,
            "unexplained_endpoint_batch_seconds": ENDPOINT_BATCH_WALL_SECONDS - mixed["wall_seconds"],
            "launch_control_fraction_of_mixed_wall": result["controls"]["trivial_cuda_launch_wall_seconds"] / mixed["wall_seconds"],
        }
        result["peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
        result["all_actual_consumers_pass"] = all(
            row["oracle"]["pass"] for row in components.values()
        ) and mixed["local_oracle"]["pass"] and mixed["global_oracle"]["pass"]
        result["pass"] = (
            result["all_actual_consumers_pass"]
            and result["controls"]["pass"]
            and all(
                timing["finite_positive"]
                for row in components.values()
                for name, timing in row.items()
                if name in {"fp8_kv_update", "paged_attention", "combined"}
            )
        )
    except Exception as error:
        result["error"] = {
            "type": type(error).__name__,
            "message": str(error)[:3000],
            "traceback": traceback.format_exc()[-12000:],
        }
    result["benchmark_wall_seconds"] = time.perf_counter() - started
    atomic(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
