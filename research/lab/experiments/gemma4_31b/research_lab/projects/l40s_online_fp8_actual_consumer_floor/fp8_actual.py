#!/usr/bin/env python3
import argparse
import hashlib
import inspect
import json
import math
import os
import statistics
import time
import types
from pathlib import Path

import torch
import vllm
from vllm import _custom_ops as ops
from vllm.config import VllmConfig, set_current_vllm_config
from vllm.model_executor.layers.linear import UnquantizedLinearMethod
from vllm.model_executor.layers.quantization.fp8 import (
    Fp8Config,
    Fp8KVCacheMethod,
    Fp8LinearMethod,
    Fp8OnlineLinearMethod,
)
from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead


CASES = (
    ("sliding_qkv", 5376, 16384, 50),
    ("global_qkv", 5376, 20480, 10),
    ("sliding_output", 8192, 5376, 50),
    ("global_output", 16384, 5376, 10),
    ("merged_gate_up", 5376, 43008, 60),
    ("down", 21504, 5376, 60),
)
DECODE_MS = (12, 14)
PREFILL_MS = (3679, 8730)
OUTPUT_TOKENS = 358
PLANNING_CEILING = 1.3945806410831811
CONSERVATIVE_CEILING = 0.8632929962
L40S_ENVELOPE_BYTES = int(44.704 * 1024**3)
LINEAR_TOLERANCE = {"absolute": 0.08, "relative": 0.08}
HEAD_TOLERANCE = {"absolute": 0.08, "relative": 0.08}
KV_TOLERANCE = {"absolute": 0.02, "relative": 0.02}


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def distribution(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    return {
        "raw_ms": values,
        "p50_ms": statistics.median(ordered),
        "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "minimum_ms": ordered[0],
        "maximum_ms": ordered[-1],
    }


def time_cuda(fn, warmups: int, iterations: int) -> tuple[dict[str, object], torch.Tensor | None]:
    result = None
    for _ in range(warmups):
        result = fn()
    torch.cuda.synchronize()
    events: list[float] = []
    walls: list[float] = []
    for _ in range(iterations):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        wall_start = time.perf_counter()
        result = fn()
        end.record()
        end.synchronize()
        events.append(start.elapsed_time(end))
        walls.append((time.perf_counter() - wall_start) * 1000)
    return {"warmups": warmups, "iterations": iterations, "cuda_event": distribution(events), "synchronized_wall": distribution(walls)}, result


def config_context():
    config = VllmConfig()
    config.model_config = types.SimpleNamespace(dtype=torch.bfloat16, head_dtype=None)
    return set_current_vllm_config(config)


def kernel_identity(method: object) -> dict[str, object]:
    kernel = getattr(method, "fp8_linear", None)
    if kernel is None:
        raise RuntimeError("actual FP8 method has no concrete fp8_linear kernel")
    parent_source = inspect.getsource(Fp8LinearMethod)
    online_source = inspect.getsource(Fp8OnlineLinearMethod)
    return {
        "method_class": f"{type(method).__module__}.{type(method).__name__}",
        "required_parent_class": f"{Fp8LinearMethod.__module__}.{Fp8LinearMethod.__name__}",
        "kernel_class": f"{type(kernel).__module__}.{type(kernel).__name__}",
        "apply_symbol": f"{Fp8LinearMethod.__module__}.{Fp8LinearMethod.__name__}.apply",
        "producer_symbol": f"{Fp8OnlineLinearMethod.__module__}.{Fp8OnlineLinearMethod.__name__}.process_weights_after_loading",
        "parent_source_sha256": hashlib.sha256(parent_source.encode()).hexdigest(),
        "online_source_sha256": hashlib.sha256(online_source.encode()).hexdigest(),
    }


def make_online_fp8_layer(k: int, n: int, value: float):
    method = Fp8OnlineLinearMethod(Fp8Config(is_checkpoint_fp8_serialized=False, activation_scheme="dynamic"))
    layer = torch.nn.Module()
    method.create_weights(layer, k, [n], k, n, torch.bfloat16)
    layer._parameters["weight"] = torch.nn.Parameter(
        torch.full((n, k), value, device="cuda", dtype=torch.bfloat16),
        requires_grad=False,
    )
    method.process_weights_after_loading(layer)
    if layer.weight.dtype != torch.float8_e4m3fn:
        raise RuntimeError(f"online producer emitted {layer.weight.dtype}, expected float8_e4m3fn")
    return method, layer, kernel_identity(method)


def make_bf16_layer(k: int, n: int, value: float):
    method = UnquantizedLinearMethod()
    layer = torch.nn.Module()
    with torch.device("cuda"):
        method.create_weights(layer, k, [n], k, n, torch.bfloat16, weight_loader=lambda *args, **kwargs: None)
    layer.weight.data.fill_(value)
    method.process_weights_after_loading(layer)
    return method, layer


def error_record(candidate: torch.Tensor, reference: torch.Tensor, tolerance: dict[str, float]) -> dict[str, object]:
    difference = (candidate.float() - reference.float()).abs()
    maximum_absolute = float(difference.max())
    maximum_relative = float((difference / reference.float().abs().clamp_min(0.1)).max())
    finite = bool(torch.isfinite(candidate).all() and torch.isfinite(reference).all())
    nontrivial = bool(float(candidate.float().abs().max()) > 1e-4 and float(reference.float().abs().max()) > 1e-4)
    return {
        "finite": finite,
        "nontrivial": nontrivial,
        "maximum_absolute": maximum_absolute,
        "maximum_relative": maximum_relative,
        "tolerance": tolerance,
        "pass": finite and nontrivial and maximum_absolute <= tolerance["absolute"] and maximum_relative <= tolerance["relative"],
    }


def run_linear(case: tuple[str, int, int, int], m: int) -> dict[str, object]:
    name, k, n, multiplicity = case
    value = 1.0 / math.sqrt(k)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    fp8_method, fp8_layer, identity = make_online_fp8_layer(k, n, value)
    bf16_method, bf16_layer = make_bf16_layer(k, n, value)
    x = torch.full((m, k), value, device="cuda", dtype=torch.bfloat16)
    warmups, iterations = (3, 7) if m in DECODE_MS else (2, 3)
    fp8_timing, fp8_output = time_cuda(lambda: fp8_method.apply(fp8_layer, x), warmups, iterations)
    bf16_timing, bf16_output = time_cuda(lambda: bf16_method.apply(bf16_layer, x), warmups, iterations)
    if fp8_output is None or bf16_output is None:
        raise RuntimeError("timed linear consumer returned no tensor")
    oracle = error_record(fp8_output, bf16_output, LINEAR_TOLERANCE)
    row = {
        "kind": "linear",
        "case": name,
        "m": m,
        "k": k,
        "n": n,
        "architecture_multiplicity": multiplicity,
        "source_weight": {"dtype": "torch.bfloat16", "deterministic_value": value, "elements": n * k},
        "producer_to_timer_connected": True,
        "identity": identity,
        "fp8": fp8_timing,
        "bf16": {
            "method_class": f"{type(bf16_method).__module__}.{type(bf16_method).__name__}",
            "timing": bf16_timing,
        },
        "oracle_from_timed_outputs": oracle,
        "allocator": {
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        },
        "pass": oracle["pass"],
    }
    del x, fp8_output, bf16_output, fp8_layer, bf16_layer
    torch.cuda.empty_cache()
    return row


def run_head(m: int) -> dict[str, object]:
    k = 5376
    value = 1.0 / math.sqrt(k)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    with torch.device("cuda"):
        head = ParallelLMHead(262144, k, params_dtype=torch.bfloat16, prefix="model.lm_head")
    head.weight.data.fill_(value)
    x = torch.full((m, k), value, device="cuda", dtype=torch.bfloat16)
    timing, output = time_cuda(lambda: head.quant_method.apply(head, x, None), 3, 7)
    if output is None:
        raise RuntimeError("timed ParallelLMHead returned no tensor")
    expected_value = float(k * value * value)
    reference = torch.full_like(output, expected_value)
    oracle = error_record(output, reference, HEAD_TOLERANCE)
    row = {
        "kind": "parallel_lm_head",
        "m": m,
        "k": k,
        "n": 262144,
        "consumer_class": f"{type(head).__module__}.{type(head).__name__}",
        "method_class": f"{type(head.quant_method).__module__}.{type(head.quant_method).__name__}",
        "timing": timing,
        "oracle_from_timed_output": oracle,
        "allocator": {
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        },
        "pass": oracle["pass"],
    }
    del x, output, reference, head
    torch.cuda.empty_cache()
    return row


def run_kv(label: str, tokens: int, context: int, heads: int, dimension: int, multiplicity: int, m: int | None) -> dict[str, object]:
    block_size = 16
    if m is None:
        total_slots = context
        slot_mapping = torch.arange(tokens, device="cuda", dtype=torch.int64)
    else:
        total_slots = m * context
        slot_mapping = torch.arange(m, device="cuda", dtype=torch.int64) * context + (context - 1)
    blocks = math.ceil(total_slots / block_size)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    key = torch.full((tokens, heads, dimension), 0.5, device="cuda", dtype=torch.bfloat16)
    value = torch.full((tokens, heads, dimension), -0.25, device="cuda", dtype=torch.bfloat16)
    cache = torch.empty((2, blocks, block_size, heads, dimension), device="cuda", dtype=torch.float8_e4m3fn)
    k_scale = torch.tensor(1.0, device="cuda", dtype=torch.float32)
    v_scale = torch.tensor(1.0, device="cuda", dtype=torch.float32)
    def write():
        ops.reshape_and_cache_flash(key, value, cache[0], cache[1], slot_mapping, "fp8", k_scale, v_scale)
        return None
    warmups, iterations = (3, 7) if m is not None else (2, 3)
    timing, _ = time_cuda(write, warmups, iterations)
    flat_key = cache[0].reshape(-1, heads, dimension)[slot_mapping]
    flat_value = cache[1].reshape(-1, heads, dimension)[slot_mapping]
    key_error = (flat_key.float() - key.float()).abs()
    value_error = (flat_value.float() - value.float()).abs()
    maximum_absolute = max(float(key_error.max()), float(value_error.max()))
    finite = bool(torch.isfinite(flat_key.float()).all() and torch.isfinite(flat_value.float()).all())
    nontrivial = bool(float(flat_key.float().abs().max()) > 1e-4 and float(flat_value.float().abs().max()) > 1e-4)
    oracle = {
        "kind": "cache side effect produced by timed actual writer",
        "maximum_absolute": maximum_absolute,
        "finite": finite,
        "nontrivial": nontrivial,
        "tolerance": KV_TOLERANCE,
        "pass": finite and nontrivial and maximum_absolute <= KV_TOLERANCE["absolute"],
    }
    row = {
        "kind": "fp8_kv_writer",
        "case": label,
        "tokens_written": tokens,
        "m": m,
        "context": context,
        "heads": heads,
        "head_dimension": dimension,
        "architecture_multiplicity": multiplicity,
        "cache_shape": list(cache.shape),
        "cache_dtype": str(cache.dtype),
        "source_dtype": str(key.dtype),
        "writer_symbol": "vllm._custom_ops.reshape_and_cache_flash",
        "writer_source_sha256": hashlib.sha256(inspect.getsource(ops.reshape_and_cache_flash).encode()).hexdigest(),
        "fp8_kv_method_source_sha256": hashlib.sha256(inspect.getsource(Fp8KVCacheMethod).encode()).hexdigest(),
        "timing": timing,
        "oracle_from_timed_cache_side_effect": oracle,
        "allocator": {
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        },
        "pass": oracle["pass"],
    }
    del key, value, cache, flat_key, flat_value, key_error, value_error
    torch.cuda.empty_cache()
    return row


def p50(row: dict[str, object], arm: str = "fp8") -> float:
    if row["kind"] == "linear":
        return float(row[arm]["cuda_event"]["p50_ms"])
    return float(row["timing"]["cuda_event"]["p50_ms"])


def aggregate(linears: list[dict[str, object]], heads: list[dict[str, object]], kv_rows: list[dict[str, object]], concurrency: int) -> dict[str, object]:
    decode_linears = [row for row in linears if row["m"] == concurrency]
    prefill_linears = [row for row in linears if row["m"] == 3679]
    if len(decode_linears) != len(CASES) or len(prefill_linears) != len(CASES):
        raise RuntimeError("aggregation lacks exactly six decode and six primary-prefill linear rows")
    head = next(row for row in heads if row["m"] == concurrency)
    kv_prefill_local = next(row for row in kv_rows if row["case"] == "local_prefill_primary")
    kv_prefill_global = next(row for row in kv_rows if row["case"] == "global_prefill_primary")
    kv_decode_local = next(row for row in kv_rows if row["case"] == f"local_decode_c{concurrency}")
    kv_decode_global = next(row for row in kv_rows if row["case"] == f"global_decode_c{concurrency}_peak")
    prefill_linear_seconds = sum(float(row["architecture_multiplicity"]) * p50(row) for row in prefill_linears) / 1000
    decode_linear_seconds = sum(float(row["architecture_multiplicity"]) * p50(row) for row in decode_linears) * OUTPUT_TOKENS / concurrency / 1000
    head_seconds = p50(head) * OUTPUT_TOKENS / concurrency / 1000
    kv_prefill_seconds = (50 * p50(kv_prefill_local) + 10 * p50(kv_prefill_global)) / 1000
    kv_decode_seconds = (50 * p50(kv_decode_local) + 10 * p50(kv_decode_global)) * OUTPUT_TOKENS / concurrency / 1000
    total = prefill_linear_seconds + decode_linear_seconds + head_seconds + kv_prefill_seconds + kv_decode_seconds
    return {
        "concurrency": concurrency,
        "prefill_linear_seconds_per_request": prefill_linear_seconds,
        "decode_linear_seconds_per_request": decode_linear_seconds,
        "head_seconds_per_request": head_seconds,
        "kv_prefill_write_seconds_per_request": kv_prefill_seconds,
        "kv_decode_write_seconds_per_request": kv_decode_seconds,
        "component_seconds_per_request": total,
        "planning_ceiling_seconds_per_request": PLANNING_CEILING,
        "planning_residual_seconds_per_request": PLANNING_CEILING - total,
        "conservative_ceiling_seconds_per_request": CONSERVATIVE_CEILING,
        "conservative_residual_seconds_per_request": CONSERVATIVE_CEILING - total,
        "decode_division": f"358/{concurrency} exactly once after architecture weighting",
        "prefill_division": "none",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("primary",))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    result: dict[str, object] = {
        "schema_version": 2,
        "stage": args.stage,
        "pass": False,
        "all_actual_consumers_pass": False,
        "economic_both_envelopes_falsified": False,
        "rows": {"linears": [], "head": [], "kv_writer": []},
        "workload": {"fresh_prompt_m": 3679, "ten_k_fresh_prompt_m": 8730, "decode_ms": list(DECODE_MS), "output_tokens": OUTPUT_TOKENS},
        "omitted_work": ["attention read/compute", "RMSNorm", "rotary", "SwiGLU/SiluAndMul", "sampling", "scheduler", "queueing", "reliability", "orchestration", "service overhead"],
    }
    measured_event_ms = 0.0
    try:
        torch.manual_seed(args.seed)
        torch.set_default_dtype(torch.bfloat16)
        with config_context():
            for case in CASES:
                for m in (*DECODE_MS, *PREFILL_MS):
                    result["rows"]["linears"].append(run_linear(case, m))
            for m in DECODE_MS:
                result["rows"]["head"].append(run_head(m))
            kv_specs = (
                ("local_prefill_primary", 3679, 4214, 16, 256, 50, None),
                ("global_prefill_primary", 3679, 4214, 4, 512, 10, None),
                ("local_prefill_10k", 8730, 10000, 16, 256, 50, None),
                ("global_prefill_10k", 8730, 10000, 4, 512, 10, None),
                ("local_decode_c12", 12, 1024, 16, 256, 50, 12),
                ("local_decode_c14", 14, 1024, 16, 256, 50, 14),
                ("global_decode_c12_start", 12, 4214, 4, 512, 10, 12),
                ("global_decode_c12_peak", 12, 4571, 4, 512, 10, 12),
                ("global_decode_c14_start", 14, 4214, 4, 512, 10, 14),
                ("global_decode_c14_peak", 14, 4571, 4, 512, 10, 14),
            )
            for spec in kv_specs:
                result["rows"]["kv_writer"].append(run_kv(*spec))
        all_rows = result["rows"]["linears"] + result["rows"]["head"] + result["rows"]["kv_writer"]
        required_count = len(CASES) * 4 + len(DECODE_MS) + len(kv_specs)
        valid = len(all_rows) == required_count and all(row["pass"] for row in all_rows)
        for row in result["rows"]["linears"]:
            measured_event_ms += sum(row["fp8"]["cuda_event"]["raw_ms"]) + sum(row["bf16"]["timing"]["cuda_event"]["raw_ms"])
        for group in (result["rows"]["head"], result["rows"]["kv_writer"]):
            for row in group:
                measured_event_ms += sum(row["timing"]["cuda_event"]["raw_ms"])
        surfaces = [aggregate(result["rows"]["linears"], result["rows"]["head"], result["rows"]["kv_writer"], concurrency) for concurrency in DECODE_MS]
        peak_reserved = max(int(row["allocator"]["peak_reserved_bytes"]) for row in all_rows)
        positive = [surface for surface in surfaces if surface["planning_residual_seconds_per_request"] > 0]
        best_residual = max((surface["planning_residual_seconds_per_request"] for surface in surfaces), default=-math.inf)
        start_ready_with_ten_minutes = time.time() + 600 < float(os.environ.get("CAMPAIGN_DEADLINE_EPOCH", "0"))
        component_admission = valid and peak_reserved <= L40S_ENVELOPE_BYTES and bool(positive)
        strong_pass = component_admission and best_residual >= 0.35
        w4_trigger = valid and not strong_pass and start_ready_with_ten_minutes
        result.update({
            "runtime": {"vllm": vllm.__version__, "torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(), "capability": torch.cuda.get_device_capability()},
            "required_row_count": required_count,
            "actual_row_count": len(all_rows),
            "surfaces": surfaces,
            "allocator_envelope": {"peak_reserved_bytes": peak_reserved, "l40s_envelope_bytes": L40S_ENVELOPE_BYTES, "transient_component_fit_only": peak_reserved <= L40S_ENVELOPE_BYTES},
            "FP8_COMPONENT_ADMISSION": component_admission,
            "strong_pass_skip_w4": strong_pass,
            "W4_RESIDUAL_TRIGGER": {"pass": w4_trigger, "valid_nonzero_fp8": valid, "strong_pass_absent": not strong_pass, "start_ready_with_ten_provider_minutes": start_ready_with_ten_minutes, "same_owner_session": True},
            "all_actual_consumers_pass": valid,
            "pass": valid,
            "economic_both_envelopes_falsified": not w4_trigger,
        })
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:4000]}
    result["useful_gpu_seconds"] = measured_event_ms / 1000
    result["scientific_wall_seconds"] = time.perf_counter() - started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
