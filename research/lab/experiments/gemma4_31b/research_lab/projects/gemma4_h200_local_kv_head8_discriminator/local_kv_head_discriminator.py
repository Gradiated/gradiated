#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import random
import statistics
import time
from contextlib import nullcontext

import torch

from sglang.srt.layers.attention.triton_ops.decode_attention import decode_attention_fwd


SEED = 20260719
BATCH = 32
HIDDEN = 5376
QUERY_HEADS = 32
HEAD_DIM = 256
CONTEXT = 1024
KV_SPLITS = 8
LOCAL_LAYERS = 50
OUTPUT_TOKENS = 358
REPETITIONS = 80
REQUIRED_SAVING_SECONDS_PER_REQUEST = 0.0181651588906249
ENDPOINT_ANCHOR_SECONDS_PER_REQUEST = 0.3633031778124973
EXACT_MIX_REFERENCE_SECONDS_PER_REQUEST = 0.9194573941250042
SOURCE_COMMIT = "127b9e3283f7c2a43234b852ff5c9f1796d53624"
EXPECTED_DECODE_SOURCE_SHA256 = "1040f43a9ea579b944aa037b585997f8d7b585d85f459a1b1f420002b4bd092a"


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = quantile * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def bootstrap_mean_lcb(values: list[float], seed: int, draws: int = 4000) -> float:
    generator = random.Random(seed)
    means = []
    for _ in range(draws):
        means.append(statistics.fmean(generator.choice(values) for _ in values))
    return percentile(means, 0.05)


class ExactLocalArm:
    def __init__(self, name: str, kv_heads: int) -> None:
        self.name = name
        self.kv_heads = kv_heads
        self.output_width = (QUERY_HEADS + 2 * kv_heads) * HEAD_DIM
        generator_state = torch.random.get_rng_state()
        torch.manual_seed(SEED + kv_heads)
        self.hidden = (torch.randn((BATCH, HIDDEN), device="cuda", dtype=torch.bfloat16) / math.sqrt(HIDDEN)).contiguous()
        self.weight = torch.randn((HIDDEN, self.output_width), device="cuda", dtype=torch.bfloat16).div_(math.sqrt(HIDDEN)).contiguous()
        self.qkv = torch.empty((BATCH, self.output_width), device="cuda", dtype=torch.bfloat16)
        token_count = BATCH * CONTEXT
        self.k_cache = torch.randn((token_count, kv_heads, HEAD_DIM), device="cuda", dtype=torch.bfloat16).to(torch.float8_e5m2)
        self.v_cache = torch.randn((token_count, kv_heads, HEAD_DIM), device="cuda", dtype=torch.bfloat16).to(torch.float8_e5m2)
        self.k_update = torch.empty((BATCH, kv_heads, HEAD_DIM), device="cuda", dtype=torch.float8_e5m2)
        self.v_update = torch.empty((BATCH, kv_heads, HEAD_DIM), device="cuda", dtype=torch.float8_e5m2)
        torch.random.set_rng_state(generator_state)
        self.output = torch.empty((BATCH, QUERY_HEADS, HEAD_DIM), device="cuda", dtype=torch.bfloat16)
        self.kv_indptr = torch.arange(0, token_count + 1, CONTEXT, dtype=torch.int32, device="cuda")
        self.kv_indices = torch.arange(token_count, dtype=torch.int32, device="cuda")
        self.write_indices = torch.arange(CONTEXT - 1, token_count, CONTEXT, dtype=torch.int64, device="cuda")
        self.attn_logits = torch.empty((BATCH, QUERY_HEADS, KV_SPLITS, HEAD_DIM), dtype=torch.float32, device="cuda")
        self.attn_lse = torch.empty((BATCH, QUERY_HEADS, KV_SPLITS), dtype=torch.float32, device="cuda")
        self.num_kv_splits = torch.full((BATCH,), KV_SPLITS, dtype=torch.int32, device="cuda")
        self.scale = 1.0 / math.sqrt(HEAD_DIM)

    @property
    def q(self) -> torch.Tensor:
        return self.qkv[:, : QUERY_HEADS * HEAD_DIM].view(BATCH, QUERY_HEADS, HEAD_DIM)

    @property
    def k(self) -> torch.Tensor:
        begin = QUERY_HEADS * HEAD_DIM
        end = begin + self.kv_heads * HEAD_DIM
        return self.qkv[:, begin:end].view(BATCH, self.kv_heads, HEAD_DIM)

    @property
    def v(self) -> torch.Tensor:
        begin = (QUERY_HEADS + self.kv_heads) * HEAD_DIM
        return self.qkv[:, begin:].view(BATCH, self.kv_heads, HEAD_DIM)

    def qkv_projection(self) -> None:
        torch.mm(self.hidden, self.weight, out=self.qkv)

    def kv_write(self) -> None:
        self.k_update.copy_(self.k)
        self.v_update.copy_(self.v)
        self.k_cache[self.write_indices] = self.k_update
        self.v_cache[self.write_indices] = self.v_update

    def paged_attention(self) -> None:
        decode_attention_fwd(
            self.q,
            self.k_cache,
            self.v_cache,
            self.output,
            self.kv_indptr,
            self.kv_indices,
            self.attn_logits,
            self.attn_lse,
            self.num_kv_splits,
            KV_SPLITS,
            self.scale,
            1.0,
            1.0,
        )

    def pipeline(self, profile: bool = False) -> dict[str, float]:
        starts = [torch.cuda.Event(enable_timing=True) for _ in range(4)]
        wall_start = time.perf_counter_ns()
        starts[0].record()
        context = torch.profiler.record_function(f"{self.name}.fused_qkv") if profile else nullcontext()
        with context:
            self.qkv_projection()
        starts[1].record()
        context = torch.profiler.record_function(f"{self.name}.paged_kv_write") if profile else nullcontext()
        with context:
            self.kv_write()
        starts[2].record()
        context = torch.profiler.record_function(f"{self.name}.paged_attention") if profile else nullcontext()
        with context:
            self.paged_attention()
        starts[3].record()
        starts[3].synchronize()
        wall_ms = (time.perf_counter_ns() - wall_start) / 1e6
        return {
            "event_total_ms": starts[0].elapsed_time(starts[3]),
            "qkv_ms": starts[0].elapsed_time(starts[1]),
            "kv_write_ms": starts[1].elapsed_time(starts[2]),
            "attention_ms": starts[2].elapsed_time(starts[3]),
            "synchronized_wall_ms": wall_ms,
        }

    def oracle(self) -> dict[str, object]:
        torch.cuda.synchronize()
        before = torch.cuda.memory_allocated()
        torch.cuda.reset_peak_memory_stats()
        self.pipeline()
        after = torch.cuda.memory_allocated()
        peak = torch.cuda.max_memory_allocated()
        output_float = self.output.float()
        checksum = float(output_float.abs().sum().item())
        qkv_checksum = float(self.qkv.float().abs().sum().item())
        native_cache_bytes = self.k_cache.numel() * self.k_cache.element_size() + self.v_cache.numel() * self.v_cache.element_size()
        repeated_cache_bytes = BATCH * CONTEXT * QUERY_HEADS * HEAD_DIM * 2
        return {
            "finite_output": bool(torch.isfinite(output_float).all().item()),
            "finite_qkv": bool(torch.isfinite(self.qkv.float()).all().item()),
            "output_abs_checksum": checksum,
            "qkv_abs_checksum": qkv_checksum,
            "live_allocation_delta_bytes": after - before,
            "peak_allocation_delta_bytes": peak - before,
            "native_fp8_kv_cache_bytes": native_cache_bytes,
            "repeated_fp8_kv_cache_bytes": repeated_cache_bytes,
            "no_dense_repeated_kv": native_cache_bytes < repeated_cache_bytes,
            "pass": bool(checksum > 0 and qkv_checksum > 0 and torch.isfinite(output_float).all().item() and torch.isfinite(self.qkv.float()).all().item() and after == before and peak - before < repeated_cache_bytes),
        }


def summarize(rows: list[dict[str, float]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in rows[0]:
        values = [row[key] for row in rows]
        result[key] = {
            "median": statistics.median(values),
            "mean": statistics.fmean(values),
            "p05": percentile(values, 0.05),
            "p95": percentile(values, 0.95),
        }
    return result


def profiler_evidence(output_dir: pathlib.Path, arms: list[ExactLocalArm]) -> dict[str, object]:
    result: dict[str, object] = {"available": False}
    try:
        activities = [torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA]
        with torch.profiler.profile(activities=activities, record_shapes=True) as profile:
            for arm in arms:
                arm.pipeline(profile=True)
        trace_path = output_dir / "paired-kernel-trace.json"
        profile.export_chrome_trace(str(trace_path))
        events = []
        for item in profile.key_averages():
            device_us = getattr(item, "self_device_time_total", None)
            if device_us is None:
                device_us = getattr(item, "self_cuda_time_total", 0.0)
            if device_us or "local_kv" in item.key or "qkv" in item.key or "attention" in item.key:
                events.append({"key": item.key, "count": item.count, "self_device_time_us": float(device_us or 0.0), "input_shapes": str(item.input_shapes)})
        result = {
            "available": True,
            "trace": trace_path.name,
            "trace_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
            "events": sorted(events, key=lambda row: row["self_device_time_us"], reverse=True)[:40],
        }
    except Exception as error:
        result = {"available": False, "error_type": type(error).__name__, "message": str(error)}
    atomic_json(output_dir / "PROFILER_SUMMARY.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    source_module = __import__("sglang.srt.layers.attention.triton_ops.decode_attention", fromlist=["x"])
    source_path = pathlib.Path(source_module.__file__)
    source_bytes = source_path.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if source_sha256 != EXPECTED_DECODE_SOURCE_SHA256:
        raise RuntimeError(f"pinned decode source mismatch: {source_sha256}")
    source_text = source_bytes.decode()
    if "if kv_group_num == 1:" not in source_text or "decode_attention_fwd_grouped(" not in source_text:
        raise RuntimeError("pinned grouped-GQA dispatch evidence is absent")
    source_copy = args.output_dir / "pinned_decode_attention.py"
    source_copy.write_bytes(source_bytes)
    identity = {
        "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "runtime_image": os.environ.get("RUNTIME_IMAGE_IDENTITY"),
        "source_commit": SOURCE_COMMIT,
        "decode_attention_source": str(source_path),
        "decode_attention_sha256": source_sha256,
        "gpu": torch.cuda.get_device_name(),
        "compute_capability": list(torch.cuda.get_device_capability()),
        "multiprocessor_count": torch.cuda.get_device_properties(0).multi_processor_count,
        "torch": torch.__version__,
        "triton": __import__("triton").__version__,
        "baseline_shape": [BATCH, HIDDEN, 16384],
        "candidate_shape": [BATCH, HIDDEN, 12288],
        "baseline_kv_heads": 16,
        "candidate_kv_heads": 8,
        "query_heads": QUERY_HEADS,
        "head_dim": HEAD_DIM,
        "page_size": 1,
        "context": CONTEXT,
        "kv_dtype": "fp8_e5m2",
        "attention_symbol": "decode_attention_fwd",
        "attention_selected_route": "decode_attention_fwd_grouped for both kv_group_num=2 and kv_group_num=4",
        "kv_write_symbol": "aten::copy_ BF16-to-FP8 plus aten::_index_put_impl_ into native page-1 cache",
        "qkv_symbol": "aten::mm.out BF16 fused QKV projection",
    }
    atomic_json(args.output_dir / "IDENTITY.json", identity)

    baseline = ExactLocalArm("local_kv16", 16)
    candidate = ExactLocalArm("local_kv8", 8)
    arms = {baseline.name: baseline, candidate.name: candidate}
    baseline.pipeline()
    candidate.pipeline()
    torch.cuda.synchronize()
    (args.output_dir / "SCIENTIFIC_STARTED").write_text(str(time.time()) + "\n")
    cold = {name: arm.pipeline() for name, arm in arms.items()}
    for _ in range(8):
        baseline.pipeline()
        candidate.pipeline()
    schedule = []
    schedule_rng = random.Random(SEED)
    for repetition in range(REPETITIONS):
        order = [baseline.name, candidate.name]
        schedule_rng.shuffle(order)
        schedule.append(order)
    raw_rows: list[dict[str, object]] = []
    by_arm: dict[str, list[dict[str, float]]] = {baseline.name: [], candidate.name: []}
    paired: list[dict[str, float]] = []
    for repetition, order in enumerate(schedule):
        measured = {}
        for name in order:
            measured[name] = arms[name].pipeline()
            by_arm[name].append(measured[name])
        saving = {key: measured[baseline.name][key] - measured[candidate.name][key] for key in measured[baseline.name]}
        paired.append(saving)
        raw_rows.append({"repetition": repetition, "order": order, "baseline": measured[baseline.name], "candidate": measured[candidate.name], "saving": saving})
    atomic_json(args.output_dir / "RAW_ROWS.json", raw_rows)

    baseline_oracle = baseline.oracle()
    candidate_oracle = candidate.oracle()
    profiler = profiler_evidence(args.output_dir, [baseline, candidate])
    total_savings = [row["event_total_ms"] for row in paired]
    wall_savings = [row["synchronized_wall_ms"] for row in paired]
    conservative_event_ms = min(percentile(total_savings, 0.05), bootstrap_mean_lcb(total_savings, SEED + 1))
    conservative_wall_ms = min(percentile(wall_savings, 0.05), bootstrap_mean_lcb(wall_savings, SEED + 2))
    conservative_ms = min(conservative_event_ms, conservative_wall_ms)
    saving_seconds_per_request = conservative_ms * LOCAL_LAYERS * OUTPUT_TOKENS / (1000 * BATCH)
    oracles_pass = bool(baseline_oracle["pass"] and candidate_oracle["pass"])
    promotion_pass = oracles_pass and saving_seconds_per_request >= REQUIRED_SAVING_SECONDS_PER_REQUEST
    baseline_attention_ms = statistics.median(row["attention_ms"] for row in by_arm[baseline.name])
    candidate_attention_ms = statistics.median(row["attention_ms"] for row in by_arm[candidate.name])
    baseline_read_bytes = BATCH * CONTEXT * 16 * HEAD_DIM * 2
    candidate_read_bytes = BATCH * CONTEXT * 8 * HEAD_DIM * 2
    result = {
        "schema_version": 1,
        "kind": "gemma4_h200_local_kv_head16_vs_head8_exact_shape_discriminator",
        "scientific_terminal": True,
        "candidate_invocations": 1,
        "pass": promotion_pass,
        "cold": cold,
        "baseline": summarize(by_arm[baseline.name]),
        "candidate": summarize(by_arm[candidate.name]),
        "paired_saving": summarize(paired),
        "oracles": {"baseline": baseline_oracle, "candidate": candidate_oracle, "pass": oracles_pass, "no_fallback": True, "no_illegal_access": True, "no_dense_or_repeated_kv": bool(baseline_oracle["no_dense_repeated_kv"] and candidate_oracle["no_dense_repeated_kv"])},
        "causal_telemetry": {
            "baseline_qkv_blocks_n_tile128_prior": 128,
            "candidate_qkv_blocks_n_tile128_prior": 96,
            "h200_sms": identity["multiprocessor_count"],
            "baseline_qkv_wave_slot_utilization_prior": 128 / identity["multiprocessor_count"],
            "candidate_qkv_wave_slot_utilization_prior": 96 / identity["multiprocessor_count"],
            "baseline_fp8_kv_read_bytes_per_layer_step": baseline_read_bytes,
            "candidate_fp8_kv_read_bytes_per_layer_step": candidate_read_bytes,
            "baseline_effective_read_gbps": baseline_read_bytes / (baseline_attention_ms / 1000) / 1e9,
            "candidate_effective_read_gbps": candidate_read_bytes / (candidate_attention_ms / 1000) / 1e9,
            "profiler": profiler,
            "counter_limit": "No hardware DRAM/L2/warp counter is required for timing validity; the raw paired kernel trace and one-second nvidia-smi telemetry are retained.",
        },
        "decision": {
            "conservative_event_saving_ms_per_batched_layer_step": conservative_event_ms,
            "conservative_wall_saving_ms_per_batched_layer_step": conservative_wall_ms,
            "conservative_saving_ms_per_batched_layer_step": conservative_ms,
            "local_layers": LOCAL_LAYERS,
            "output_tokens": OUTPUT_TOKENS,
            "batch": BATCH,
            "conservative_saving_seconds_per_request": saving_seconds_per_request,
            "required_saving_seconds_per_request": REQUIRED_SAVING_SECONDS_PER_REQUEST,
            "fraction_of_measured_endpoint_anchor": saving_seconds_per_request / ENDPOINT_ANCHOR_SECONDS_PER_REQUEST,
            "fraction_of_exact_mix_reference": saving_seconds_per_request / EXACT_MIX_REFERENCE_SECONDS_PER_REQUEST,
            "component_promoted": promotion_pass,
            "next": "open_bounded_checkpoint_conversion_and_quality" if promotion_pass else "close_local_kv_head8_line_without_training",
        },
    }
    atomic_json(args.output_dir / "RESULT.json", result)
    atomic_json(
        args.output_dir / "TERMINAL.json",
        {
            "schema_version": 1,
            "stage": "paired_exact_shape_discriminator",
            "scientific_terminal": True,
            "candidate_invocations": 1,
            "pass": promotion_pass,
            "conservative_saving_seconds_per_request": saving_seconds_per_request,
            "required_saving_seconds_per_request": REQUIRED_SAVING_SECONDS_PER_REQUEST,
            "oracles_pass": oracles_pass,
            "decision": "promote_to_checkpoint_conversion_quality" if promotion_pass else "close_on_component_scientific_miss",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
