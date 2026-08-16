#!/usr/bin/env python3
"""Pinned-image H100 paged-KV consumer; CUDA-only and fail-closed."""
import argparse, hashlib, inspect, json, math, os, random, statistics, time
from pathlib import Path

import torch
import vllm
from vllm.config import VllmConfig, set_current_vllm_config
from vllm.forward_context import set_forward_context
from vllm.model_executor.layers.attention.attention import (
    Attention, unified_attention_with_output, unified_kv_cache_update,
)

PAGE = 16
CASES = (("local", 1024, 32, 16, 256, 50, 1024),
         ("global4214", 4214, 32, 4, 512, 10, -1),
         ("global4393", 4393, 32, 4, 512, 10, -1),
         ("global4571", 4571, 32, 4, 512, 10, -1))
TARGET = 0.027398761575976767

def atomic(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        json.dump(value, f, indent=2, sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def digest(obj):
    return hashlib.sha256(inspect.getsource(obj).encode()).hexdigest()

def native_layer(name, q_heads, kv_heads, dim, window, cache_dtype):
    cfg = VllmConfig()
    cfg.model_config = type("ModelConfig", (), {"dtype": torch.bfloat16, "head_dtype": None,
                                                 "is_mm_prefix_lm": False})()
    set_current_vllm_config(cfg)
    cache_cfg = type("CacheConfig", (), {"cache_dtype": cache_dtype,
        "calculate_kv_scales": False, "sliding_window": window,
        "kv_cache_dtype_skip_layers": None})()
    layer = Attention(q_heads, dim, dim ** -0.5, num_kv_heads=kv_heads,
                      cache_config=cache_cfg, per_layer_sliding_window=window,
                      prefix=name)
    backend = layer.attn_backend
    shape = backend.get_kv_cache_shape(math.ceil(8 * math.ceil(window / PAGE) if window > 0 else
        8 * math.ceil(4571 / PAGE)), PAGE, kv_heads, dim, cache_dtype)
    layer.kv_cache = torch.empty(shape, dtype=layer.kv_cache_torch_dtype, device="cuda")
    return cfg, layer, backend, shape

def native_metadata(layer, context, batch, table, lengths, slots):
    """Use the pinned backend builder; never hand-author metadata or bypass it."""
    builder_cls = layer.attn_backend.get_builder_cls()
    builder = builder_cls(layer, None)
    if not hasattr(builder, "build_for_flashinfer") and not hasattr(builder, "build"):
        raise RuntimeError("pinned backend has no native metadata builder")
    fn = getattr(builder, "build_for_flashinfer", None) or builder.build
    metadata = fn(num_reqs=batch, num_actual_tokens=batch, max_query_len=1,
                  max_seq_len=context, query_start_loc=torch.arange(batch + 1, device="cuda", dtype=torch.int32),
                  seq_lens=lengths, block_table=table, slot_mapping=slots)
    if metadata is None:
        raise RuntimeError("native metadata builder returned None")
    return metadata

def oracle(candidate, reference):
    a, b = candidate.float().flatten(), reference.float().flatten()
    cosine = float(torch.nn.functional.cosine_similarity(a, b, dim=0))
    nrmse = float(torch.linalg.vector_norm(a - b) / torch.linalg.vector_norm(b).clamp_min(1e-12))
    return {"finite": bool(torch.isfinite(a).all() and torch.isfinite(b).all()),
            "nonzero": bool(a.abs().max() > 1e-4 and b.abs().max() > 1e-4),
            "cosine": cosine, "normalized_rmse": nrmse,
            "pass": cosine >= .99 and nrmse <= .05}

def arm(case, mode, seed):
    name, context, qh, kvh, dim, multiplicity, window = case
    layer_name = f"paged_{name}_{mode}"
    cache_dtype = "auto" if mode == "bf16" else "fp8"
    cfg, layer, backend, cache_shape = native_layer(layer_name, qh, kvh, dim, window, cache_dtype)
    batch = 8; pages = math.ceil(context / PAGE); total = batch * pages
    table = torch.arange(total, device="cuda", dtype=torch.int32).reshape(batch, pages)
    slots = torch.arange(batch, device="cuda", dtype=torch.int64) * pages * PAGE + (context - 1)
    lengths = torch.full((batch,), context, device="cuda", dtype=torch.int32)
    q = torch.linspace(-.73, .81, batch * qh * dim, device="cuda", dtype=torch.bfloat16).reshape(batch, qh, dim)
    k = torch.linspace(-.61, .57, batch * qh * dim, device="cuda", dtype=torch.bfloat16).reshape(batch, qh, dim)
    v = torch.linspace(.43, -.49, batch * qh * dim, device="cuda", dtype=torch.bfloat16).reshape(batch, qh, dim)
    output = torch.empty_like(q)
    metadata = native_metadata(layer, context, batch, table, lengths, slots)
    with set_forward_context({layer_name: metadata}, cfg, num_tokens=batch,
                             slot_mapping={layer_name: slots}):
        dependency = unified_kv_cache_update(k, v, layer_name)
        unified_attention_with_output(q, k, v, output, layer_name, kv_cache_dummy_dep=dependency)
    if not bool(torch.isfinite(output).all()) or float(output.abs().max()) <= 1e-4:
        raise RuntimeError("actual timed consumer output is zero or nonfinite")
    return {"case": name, "mode": mode, "context": context, "batch": batch,
            "query_shape": list(q.shape), "cache_shape": list(cache_shape),
            "cache_dtype": str(layer.kv_cache.dtype), "backend_class": f"{type(backend).__module__}.{type(backend).__name__}",
            "layer_class": f"{type(layer).__module__}.{type(layer).__name__}",
            "producer_symbol": "vllm.model_executor.layers.attention.attention.unified_kv_cache_update",
            "consumer_symbol": "vllm.model_executor.layers.attention.attention.unified_attention_with_output",
            "backend_source_sha256": digest(layer.impl.forward), "output": output.detach(),
            "multiplicity": multiplicity}

def main():
    p = argparse.ArgumentParser(); p.add_argument("--stage", choices=("primary", "sweep"), required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--seed", type=int, default=17); a = p.parse_args()
    result = {"schema_version": 2, "stage": a.stage, "pass": False, "rows": [], "counters": {"pass": False}}
    try:
        if "H100" not in torch.cuda.get_device_name() or torch.cuda.get_device_capability() != (9, 0): raise RuntimeError("expected SM90 H100")
        random.seed(a.seed); torch.manual_seed(a.seed)
        result["runtime"] = {"vllm": vllm.__version__, "gpu": torch.cuda.get_device_name(), "producer_sha256": digest(unified_kv_cache_update), "consumer_sha256": digest(unified_attention_with_output)}
        for case in CASES:
            bf, fp = arm(case, "bf16", a.seed), arm(case, "fp8", a.seed)
            result["rows"].append({"case": case[0], "bf16": {k:v for k,v in bf.items() if k != "output"}, "fp8": {k:v for k,v in fp.items() if k != "output"}, "oracle": oracle(fp["output"], bf["output"]), "pass": oracle(fp["output"], bf["output"])["pass"]})
        if not all(r["pass"] for r in result["rows"]): raise RuntimeError("representation oracle failed")
        if a.stage == "sweep": raise RuntimeError("sweep requires profiler counter attachment before timed rows")
        result["pass"] = True
    except Exception as e:
        result["error"] = {"type": type(e).__name__, "message": str(e)[:3000]}
    atomic(a.output, result); return 0 if result["pass"] else 1

if __name__ == "__main__": raise SystemExit(main())
