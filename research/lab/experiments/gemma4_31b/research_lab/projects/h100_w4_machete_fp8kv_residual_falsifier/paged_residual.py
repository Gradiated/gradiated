#!/usr/bin/env python3
"""Actual-image global c32 paged KV producer plus selected attention backend."""
import argparse
import hashlib
import inspect
import json
import math
import os
import random
import statistics
import subprocess
import time
import traceback
from pathlib import Path

import torch
import vllm
from vllm.config import CacheConfig, VllmConfig, set_current_vllm_config
from vllm.forward_context import set_forward_context
from vllm.model_executor.layers.attention.attention import (
    Attention, unified_attention_with_output, unified_kv_cache_update,
)
from vllm.v1.attention.backends.triton_attn import TritonAttentionMetadata

PAGE = 16
BATCH = 32
REPS = 100
WARMUPS = 20
GLOBAL_CASES = (
    ("global4214", 4214, 32, 4, 512, 10, -1),
    ("global4393", 4393, 32, 4, 512, 10, -1),
    ("global4571", 4571, 32, 4, 512, 10, -1),
)


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def source_hash(value: object) -> str:
    return hashlib.sha256(inspect.getsource(value).encode()).hexdigest()


def make_config() -> VllmConfig:
    config = VllmConfig()
    config.model_config = type("ModelConfig", (), {
        "dtype": torch.bfloat16, "head_dtype": None, "is_mm_prefix_lm": False,
    })()
    return config


def metadata(context: int, q_heads: int, kv_heads: int, head_dim: int,
             table: torch.Tensor, slots: torch.Tensor) -> TritonAttentionMetadata:
    starts = torch.arange(BATCH + 1, device="cuda", dtype=torch.int32)
    lengths = torch.full((BATCH,), context, device="cuda", dtype=torch.int32)
    return TritonAttentionMetadata(
        num_actual_tokens=BATCH, max_query_len=1, query_start_loc=starts,
        max_seq_len=context, seq_lens=lengths, block_table=table,
        slot_mapping=slots, seq_threshold_3D=None,
        num_par_softmax_segments=None, softmax_segm_output=None,
        softmax_segm_max=None, softmax_segm_expsum=None,
        use_cascade=False, common_prefix_len=0, cu_prefix_query_lens=None,
        prefix_kv_lens=None, suffix_kv_lens=None,
    )


def cache_sample(layer: Attention, table: torch.Tensor, context: int) -> dict:
    key_cache, value_cache = layer.kv_cache.unbind(1)
    if layer.kv_cache_dtype.startswith("fp8"):
        key_cache = key_cache.view(layer.impl.fp8_dtype)
        value_cache = value_cache.view(layer.impl.fp8_dtype)
    last_offset = (context - 1) % PAGE
    indices = ((int(table[0, 0]), 0), (int(table[0, -1]), last_offset),
               (int(table[-1, -1]), last_offset))
    key_maxima = [float(key_cache[block, offset].float().abs().max()) for block, offset in indices]
    value_maxima = [float(value_cache[block, offset].float().abs().max()) for block, offset in indices]
    return {
        "sampled_physical_slots": [[block, offset] for block, offset in indices],
        "key_abs_maxima": key_maxima,
        "value_abs_maxima": value_maxima,
        "pass": all(value > 1e-4 for value in key_maxima + value_maxima),
    }


def build_arm(case: tuple, mode: str) -> dict:
    case_name, context, q_heads, kv_heads, head_dim, layers, window = case
    name = f"residual_{case_name}_{mode}"
    config = make_config()
    cache = CacheConfig(cache_dtype="auto" if mode == "bf16" else "fp8_e4m3",
                        sliding_window=window, enable_prefix_caching=False)
    with set_current_vllm_config(config):
        layer = Attention(q_heads, head_dim, head_dim ** -0.5,
                          num_kv_heads=kv_heads, cache_config=cache,
                          per_layer_sliding_window=window, prefix=name)
    layer.to("cuda")
    backend = layer.attn_backend
    pages = math.ceil(context / PAGE)
    table = torch.arange(BATCH * pages, device="cuda", dtype=torch.int32).reshape(BATCH, pages)
    decode_slots = table[:, -1].to(torch.int64) * PAGE + (context - 1) % PAGE
    cache_shape = backend.get_kv_cache_shape(BATCH * pages, PAGE, kv_heads,
                                             head_dim, cache.cache_dtype)
    layer.kv_cache = torch.empty(cache_shape, dtype=layer.kv_cache_torch_dtype,
                                 device="cuda")
    fill_slots = (table.to(torch.int64).unsqueeze(-1) * PAGE
                  + torch.arange(PAGE, device="cuda")).reshape(-1)
    fill_k = torch.linspace(-0.75, 0.75, fill_slots.numel() * kv_heads * head_dim,
                            device="cuda", dtype=torch.bfloat16).reshape(-1, kv_heads, head_dim)
    fill_v = torch.linspace(0.61, -0.61, fill_slots.numel() * kv_heads * head_dim,
                            device="cuda", dtype=torch.bfloat16).reshape(-1, kv_heads, head_dim)
    fill_meta = metadata(context, q_heads, kv_heads, head_dim, table, fill_slots)
    with set_forward_context({name: fill_meta}, config, num_tokens=fill_slots.numel(),
                             slot_mapping={name: fill_slots}):
        unified_kv_cache_update(fill_k, fill_v, name)
    del fill_k, fill_v, fill_slots
    torch.cuda.synchronize()
    population = cache_sample(layer, table, context)
    if not population["pass"]:
        raise RuntimeError(f"{name} producer left sampled global pages empty")
    q = torch.linspace(-0.43, 0.47, BATCH * q_heads * head_dim, device="cuda",
                       dtype=torch.bfloat16).reshape(BATCH, q_heads, head_dim)
    k = torch.linspace(-0.31, 0.29, BATCH * kv_heads * head_dim, device="cuda",
                       dtype=torch.bfloat16).reshape(BATCH, kv_heads, head_dim)
    v = torch.linspace(0.23, -0.27, BATCH * kv_heads * head_dim, device="cuda",
                       dtype=torch.bfloat16).reshape(BATCH, kv_heads, head_dim)
    return {
        "case": case_name, "context": context, "layers": layers, "mode": mode,
        "name": name, "config": config, "layer": layer,
        "metadata": metadata(context, q_heads, kv_heads, head_dim, table, decode_slots),
        "slots": decode_slots, "q": q, "k": k, "v": v,
        "output": torch.empty_like(q),
        "backend": f"{backend.__module__}.{backend.__name__}",
        "implementation": f"{type(layer.impl).__module__}.{type(layer.impl).__name__}",
        "cache_shape": list(cache_shape), "cache_dtype": str(layer.kv_cache.dtype),
        "cache_population": population, "dispatch": "2d_no_segmented_scratch",
    }


def call(arm: dict) -> torch.Tensor:
    with set_forward_context({arm["name"]: arm["metadata"]}, arm["config"],
                             num_tokens=BATCH,
                             slot_mapping={arm["name"]: arm["slots"]}):
        dependency = unified_kv_cache_update(arm["k"], arm["v"], arm["name"])
        unified_attention_with_output(arm["q"], arm["k"], arm["v"],
                                      arm["output"], arm["name"],
                                      kv_cache_dummy_dep=dependency)
    return arm["output"]


def output_stats(output: torch.Tensor) -> dict:
    value = output.float()
    return {
        "finite": bool(torch.isfinite(value).all()),
        "abs_max": float(value.abs().max()),
        "l2_norm": float(torch.linalg.vector_norm(value)),
        "nonzero": bool(value.abs().max() > 1e-4),
    }


def time_paired(bf16: dict, fp8: dict, seed: int) -> tuple[dict, dict, str]:
    rng = random.Random(seed)
    for _ in range(WARMUPS):
        pair = [bf16, fp8]
        rng.shuffle(pair)
        for arm in pair:
            call(arm)
    torch.cuda.synchronize()
    values = {"bf16": {"event_ms": [], "wall_ms": []},
              "fp8": {"event_ms": [], "wall_ms": []}}
    order = []
    for _ in range(REPS):
        pair = [bf16, fp8]
        rng.shuffle(pair)
        for arm in pair:
            begin, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            started = time.perf_counter()
            begin.record()
            call(arm)
            end.record()
            end.synchronize()
            label = arm["mode"]
            values[label]["event_ms"].append(begin.elapsed_time(end))
            values[label]["wall_ms"].append((time.perf_counter() - started) * 1000)
            order.append(label)
    for value in values.values():
        value["event_ms_p50"] = statistics.median(value["event_ms"])
        value["wall_ms_p50"] = statistics.median(value["wall_ms"])
        value["interval_union_event_ms"] = sum(value["event_ms"])
    order_hash = hashlib.sha256(",".join(order).encode()).hexdigest()
    return values["bf16"], values["fp8"], order_hash


def oracle(candidate: torch.Tensor, reference: torch.Tensor) -> dict:
    candidate, reference = candidate.float().flatten(), reference.float().flatten()
    cosine = float(torch.nn.functional.cosine_similarity(candidate, reference, dim=0))
    nrmse = float(torch.linalg.vector_norm(candidate - reference)
                  / torch.linalg.vector_norm(reference).clamp_min(1e-12))
    finite = bool(torch.isfinite(candidate).all() and torch.isfinite(reference).all())
    nonzero = bool(candidate.abs().max() > 1e-4 and reference.abs().max() > 1e-4)
    return {"finite": finite, "nonzero": nonzero, "cosine": cosine,
            "normalized_rmse": nrmse,
            "pass": finite and nonzero and cosine >= .99 and nrmse <= .05}


def ncu_state() -> dict:
    found = subprocess.run(["bash", "-lc", "command -v ncu || true"],
                           capture_output=True, text=True).stdout.strip()
    return {"attempted": True, "ncu_path": found or None,
            "requested": ["dram__bytes_read.sum", "lts__t_bytes.sum",
                          "sm__cycles_elapsed.avg", "achieved_active_warps",
                          "launch_count"],
            "status": "deferred_unavailable" if not found else "available_not_collected_in_discovery"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sentinel-output", type=Path, required=True)
    parser.add_argument("--route-packet", type=Path, required=True)
    args = parser.parse_args()
    result = {"schema_version": 2, "stage": "global_c32_residual", "pass": False,
              "rows": [], "useful_gpu_seconds": 0.0}
    started = time.perf_counter()
    try:
        route = json.loads(args.route_packet.read_text())
        if route.get("pass") is not True:
            raise RuntimeError("GLOBAL_ROUTE_PACKET did not pass")
        if "H100" not in torch.cuda.get_device_name() or torch.cuda.get_device_capability() != (9, 0):
            raise RuntimeError("expected one H100 SM90")
        torch.manual_seed(20260717)
        torch.cuda.reset_peak_memory_stats()
        result["runtime"] = {
            "vllm": vllm.__version__, "gpu": torch.cuda.get_device_name(),
            "producer_source_sha256": source_hash(unified_kv_cache_update),
            "consumer_source_sha256": source_hash(unified_attention_with_output),
            "route_packet_sha256": hashlib.sha256(args.route_packet.read_bytes()).hexdigest(),
        }
        result["counters"] = ncu_state()
        bf16_4214 = build_arm(GLOBAL_CASES[0], "bf16")
        sentinel_output = call(bf16_4214).detach().clone()
        sentinel = {
            "schema_version": 1, "stage": "M1_global4214_bf16_nonzero_sentinel",
            "actual_producer": "unified_kv_cache_update",
            "actual_consumer": "unified_attention_with_output",
            "backend": bf16_4214["backend"],
            "implementation": bf16_4214["implementation"],
            "cache_population": bf16_4214["cache_population"],
            "output": output_stats(sentinel_output),
        }
        sentinel["pass"] = (sentinel["cache_population"]["pass"]
                            and sentinel["output"]["finite"]
                            and sentinel["output"]["nonzero"])
        atomic(args.sentinel_output, sentinel)
        if not sentinel["pass"]:
            raise RuntimeError("M1 global4214 BF16 nonzero sentinel failed")
        for case_index, case in enumerate(GLOBAL_CASES):
            bf16 = bf16_4214 if case_index == 0 else build_arm(case, "bf16")
            fp8 = build_arm(case, "fp8")
            bf_output = call(bf16).detach().clone()
            fp_output = call(fp8).detach().clone()
            check = oracle(fp_output, bf_output)
            bf_timing, fp_timing, order_hash = time_paired(
                bf16, fp8, 20260717 + case_index)
            fixed = ("backend", "implementation", "cache_shape", "cache_dtype",
                     "cache_population", "dispatch")
            row = {
                "case": case[0], "context": case[1], "layers": case[5],
                "batch": BATCH,
                "bf16": {key: bf16[key] for key in fixed} | bf_timing,
                "fp8_e4m3": {key: fp8[key] for key in fixed} | fp_timing,
                "oracle": check, "paired_order_sha256": order_hash,
                "actual_producer": "unified_kv_cache_update",
                "actual_consumer": "unified_attention_with_output",
            }
            result["rows"].append(row)
            del bf16, fp8, bf_output, fp_output
            bf16_4214 = None
            torch.cuda.empty_cache()
        if not all(row["oracle"]["pass"] for row in result["rows"]):
            raise RuntimeError("one or more paired global output oracles failed")
        local = route["bound_prior_local_row"]
        global_fp8_ms = statistics.mean(row["fp8_e4m3"]["event_ms_p50"]
                                        for row in result["rows"])
        residual = ((50 * local["fp8_event_ms_p50"] + 10 * global_fp8_ms)
                    * 358 / (1000 * BATCH))
        result["aggregate"] = {
            "equation": "(50*local_fp8_ms + 10*mean(global_fp8_ms))*358/(1000*32)",
            "local_fp8_event_ms_p50": local["fp8_event_ms_p50"],
            "global_fp8_event_ms_p50_mean": global_fp8_ms,
            "fp8_attention_seconds_per_request": residual,
            "residual_ceiling_seconds_per_request": 0.0738631898962037,
            "falsifies_combined_candidate": residual >= 0.0738631898962037,
        }
        result["allocator"] = {
            "memory_allocated_bytes": torch.cuda.memory_allocated(),
            "memory_reserved_bytes": torch.cuda.memory_reserved(),
            "max_memory_allocated_bytes": torch.cuda.max_memory_allocated(),
        }
        result["pass"] = True
        result["all_actual_consumers_pass"] = True
        result["useful_gpu_seconds"] = time.perf_counter() - started
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:4000],
                           "traceback": traceback.format_exc()[-12000:]}
        result["useful_gpu_seconds"] = time.perf_counter() - started
    atomic(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
