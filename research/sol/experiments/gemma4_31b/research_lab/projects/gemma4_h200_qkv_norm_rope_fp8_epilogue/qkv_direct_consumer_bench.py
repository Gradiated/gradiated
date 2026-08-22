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
from collections.abc import Callable

import torch
import torch.nn.functional as F
import triton
import triton.language as tl

from sglang.srt.layers.attention.triton_ops.decode_attention import (
    decode_attention_fwd,
)
from sglang.srt.layers.gemma4_fused_ops import gemma_qkv_rmsnorm
from sglang.srt.layers.rotary_embedding import get_rope
from sglang.srt.server_args import set_global_server_args_for_scheduler


SEED = 20260729
BATCH = 32
NUM_Q_HEADS = 32
MAX_KV_SPLITS = 8
EPS = 1e-6


class StandaloneServerArgs:
    rl_on_policy_target = None


@triton.jit
def _qkv_norm_rope_direct_fp8_cache_kernel(
    qkv_ptr,
    q_weight_ptr,
    k_weight_ptr,
    positions_ptr,
    cos_sin_cache_ptr,
    cache_locs_ptr,
    q_out_ptr,
    k_cache_ptr,
    v_cache_ptr,
    stride_qkv_token,
    stride_q_token,
    stride_q_head,
    stride_cache_token,
    stride_cache_head,
    NUM_Q_HEADS: tl.constexpr,
    NUM_KV_HEADS: tl.constexpr,
    HEAD_DIM: tl.constexpr,
    ROTARY_DIM: tl.constexpr,
    Q_SIZE: tl.constexpr,
    KV_SIZE: tl.constexpr,
    EPS: tl.constexpr,
    BLOCK: tl.constexpr,
):
    token = tl.program_id(0)
    slot = tl.program_id(1)
    offsets = tl.arange(0, BLOCK)
    mask = offsets < HEAD_DIM
    is_q = slot < NUM_Q_HEADS
    is_k = (slot >= NUM_Q_HEADS) & (slot < NUM_Q_HEADS + NUM_KV_HEADS)
    head = tl.where(
        is_q,
        slot,
        tl.where(
            is_k,
            slot - NUM_Q_HEADS,
            slot - NUM_Q_HEADS - NUM_KV_HEADS,
        ),
    )
    segment = tl.where(is_q, 0, tl.where(is_k, Q_SIZE, Q_SIZE + KV_SIZE))
    base = token * stride_qkv_token + segment + head * HEAD_DIM

    value = tl.load(qkv_ptr + base + offsets, mask=mask, other=0.0).to(tl.float32)
    square_sum = tl.sum(value * value, axis=0)
    inverse_rms = tl.rsqrt(square_sum / HEAD_DIM + EPS)
    q_weight = tl.load(q_weight_ptr + offsets, mask=mask, other=1.0).to(tl.float32)
    k_weight = tl.load(k_weight_ptr + offsets, mask=mask, other=1.0).to(tl.float32)
    weight = tl.where(is_q, q_weight, tl.where(is_k, k_weight, 1.0))
    normalized = (value * inverse_rms * weight).to(tl.bfloat16).to(tl.float32)

    rotary_half = ROTARY_DIM // 2
    pair_offsets = tl.where(offsets < rotary_half, offsets + rotary_half, offsets - rotary_half)
    pair_value = tl.load(
        qkv_ptr + base + pair_offsets,
        mask=mask & (offsets < ROTARY_DIM),
        other=0.0,
    ).to(tl.float32)
    pair_q_weight = tl.load(
        q_weight_ptr + pair_offsets,
        mask=mask & (offsets < ROTARY_DIM),
        other=1.0,
    ).to(tl.float32)
    pair_k_weight = tl.load(
        k_weight_ptr + pair_offsets,
        mask=mask & (offsets < ROTARY_DIM),
        other=1.0,
    ).to(tl.float32)
    pair_weight = tl.where(
        is_q, pair_q_weight, tl.where(is_k, pair_k_weight, 1.0)
    )
    pair_normalized = (
        pair_value * inverse_rms * pair_weight
    ).to(tl.bfloat16).to(tl.float32)
    position = tl.load(positions_ptr + token)
    trig_offset = offsets % rotary_half
    cosine = tl.load(
        cos_sin_cache_ptr + position * ROTARY_DIM + trig_offset,
        mask=mask & (offsets < ROTARY_DIM),
        other=1.0,
    ).to(tl.float32)
    sine = tl.load(
        cos_sin_cache_ptr + position * ROTARY_DIM + rotary_half + trig_offset,
        mask=mask & (offsets < ROTARY_DIM),
        other=0.0,
    ).to(tl.float32)
    rotated = tl.where(
        offsets < rotary_half,
        normalized * cosine - pair_normalized * sine,
        normalized * cosine + pair_normalized * sine,
    )
    output = tl.where((is_q | is_k) & (offsets < ROTARY_DIM), rotated, normalized)
    output = output.to(tl.bfloat16).to(tl.float32)

    q_offset = token * stride_q_token + head * stride_q_head + offsets
    cache_loc = tl.load(cache_locs_ptr + token)
    cache_offset = (
        cache_loc * stride_cache_token + head * stride_cache_head + offsets
    )
    tl.store(q_out_ptr + q_offset, output, mask=mask & is_q)
    tl.store(k_cache_ptr + cache_offset, output, mask=mask & is_k)
    tl.store(v_cache_ptr + cache_offset, output, mask=mask & ~(is_q | is_k))


def direct_epilogue(
    qkv: torch.Tensor,
    q_weight: torch.Tensor,
    k_weight: torch.Tensor,
    positions: torch.Tensor,
    cos_sin_cache: torch.Tensor,
    cache_locs: torch.Tensor,
    q_out: torch.Tensor,
    k_cache: torch.Tensor,
    v_cache: torch.Tensor,
    num_kv_heads: int,
    head_dim: int,
    rotary_dim: int,
) -> None:
    q_size = NUM_Q_HEADS * head_dim
    kv_size = num_kv_heads * head_dim
    assert qkv.shape == (BATCH, q_size + 2 * kv_size)
    assert qkv.stride() == (qkv.shape[1], 1)
    assert q_out.shape == (BATCH, NUM_Q_HEADS, head_dim)
    assert k_cache.dtype == torch.float8_e5m2
    assert v_cache.dtype == torch.float8_e5m2
    _qkv_norm_rope_direct_fp8_cache_kernel[
        (BATCH, NUM_Q_HEADS + 2 * num_kv_heads)
    ](
        qkv,
        q_weight,
        k_weight,
        positions,
        cos_sin_cache,
        cache_locs,
        q_out,
        k_cache,
        v_cache,
        qkv.stride(0),
        q_out.stride(0),
        q_out.stride(1),
        k_cache.stride(0),
        k_cache.stride(1),
        NUM_Q_HEADS=NUM_Q_HEADS,
        NUM_KV_HEADS=num_kv_heads,
        HEAD_DIM=head_dim,
        ROTARY_DIM=rotary_dim,
        Q_SIZE=q_size,
        KV_SIZE=kv_size,
        EPS=EPS,
        BLOCK=triton.next_power_of_2(head_dim),
        num_warps=8 if head_dim == 512 else 4,
    )


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(path)


def distribution(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)

    def percentile(fraction: float) -> float:
        position = fraction * (len(ordered) - 1)
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return ordered[lower]
        return ordered[lower] * (upper - position) + ordered[upper] * (
            position - lower
        )

    return {
        "samples_ms": values,
        "minimum_ms": min(values),
        "p10_ms": percentile(0.1),
        "median_ms": statistics.median(values),
        "mean_ms": statistics.mean(values),
        "p90_ms": percentile(0.9),
        "maximum_ms": max(values),
    }


def relative_l2(actual: torch.Tensor, expected: torch.Tensor) -> float:
    numerator = torch.linalg.vector_norm(actual.float() - expected.float())
    denominator = torch.linalg.vector_norm(expected.float()).clamp_min(1e-12)
    return float((numerator / denominator).item())


class Case:
    def __init__(
        self,
        name: str,
        num_kv_heads: int,
        head_dim: int,
        partial_rotary_factor: float,
        rope_theta: float,
        rope_type: str,
        sequence_length: int,
    ) -> None:
        torch.manual_seed(SEED + head_dim + num_kv_heads)
        self.name = name
        self.num_kv_heads = num_kv_heads
        self.head_dim = head_dim
        self.partial_rotary_factor = partial_rotary_factor
        self.sequence_length = sequence_length
        self.q_size = NUM_Q_HEADS * head_dim
        self.kv_size = num_kv_heads * head_dim
        self.width = self.q_size + 2 * self.kv_size
        self.base = (
            torch.randn((BATCH, self.width), device="cuda", dtype=torch.bfloat16)
            / math.sqrt(head_dim)
        ).contiguous()
        self.stock_work = torch.empty_like(self.base)
        self.candidate_work = torch.empty_like(self.base)
        self.q_weight = (
            1.0 + 0.02 * torch.randn(head_dim, device="cuda", dtype=torch.float32)
        ).to(torch.bfloat16)
        self.k_weight = (
            1.0 + 0.02 * torch.randn(head_dim, device="cuda", dtype=torch.float32)
        ).to(torch.bfloat16)
        self.positions = torch.full(
            (BATCH,), sequence_length - 1, device="cuda", dtype=torch.int64
        )
        self.rope = get_rope(
            head_dim,
            rotary_dim=head_dim,
            max_position=sequence_length + 1,
            base=rope_theta,
            rope_scaling={"rope_type": rope_type},
            partial_rotary_factor=partial_rotary_factor,
            is_neox_style=True,
        ).cuda()
        self.rotary_dim = self.rope.rotary_dim
        self.active_rotary_angles = int(head_dim * partial_rotary_factor / 2)
        slots = BATCH * sequence_length
        self.cache_locs = (
            torch.arange(BATCH, device="cuda", dtype=torch.int64) * sequence_length
            + sequence_length
            - 1
        )
        base_k = torch.randn(
            (slots, num_kv_heads, head_dim),
            device="cuda",
            dtype=torch.bfloat16,
        ).to(torch.float8_e5m2)
        base_v = torch.randn(
            (slots, num_kv_heads, head_dim),
            device="cuda",
            dtype=torch.bfloat16,
        ).to(torch.float8_e5m2)
        self.stock_k = base_k.clone()
        self.stock_v = base_v.clone()
        self.candidate_k = base_k.clone()
        self.candidate_v = base_v.clone()
        self.stock_q = torch.empty(
            (BATCH, NUM_Q_HEADS, head_dim),
            device="cuda",
            dtype=torch.bfloat16,
        )
        self.candidate_q = torch.empty_like(self.stock_q)
        self.stock_out = torch.empty_like(self.stock_q)
        self.candidate_out = torch.empty_like(self.stock_q)
        self.kv_indptr = (
            torch.arange(BATCH + 1, device="cuda", dtype=torch.int32)
            * sequence_length
        )
        self.kv_indices = torch.arange(slots, device="cuda", dtype=torch.int32)
        self.num_kv_splits = torch.full(
            (BATCH,), MAX_KV_SPLITS, device="cuda", dtype=torch.int32
        )
        self.stock_logits = torch.empty(
            (BATCH, NUM_Q_HEADS, MAX_KV_SPLITS, head_dim),
            device="cuda",
            dtype=torch.float32,
        )
        self.candidate_logits = torch.empty_like(self.stock_logits)
        self.stock_lse = torch.empty(
            (BATCH, NUM_Q_HEADS, MAX_KV_SPLITS),
            device="cuda",
            dtype=torch.float32,
        )
        self.candidate_lse = torch.empty_like(self.stock_lse)
        self.stock_invocations = 0
        self.candidate_invocations = 0

    def consume(
        self,
        q: torch.Tensor,
        k_cache: torch.Tensor,
        v_cache: torch.Tensor,
        output: torch.Tensor,
        logits: torch.Tensor,
        lse: torch.Tensor,
    ) -> None:
        decode_attention_fwd(
            q,
            k_cache,
            v_cache,
            output,
            self.kv_indptr,
            self.kv_indices,
            logits,
            lse,
            self.num_kv_splits,
            MAX_KV_SPLITS,
            1.0,
            1.0,
            1.0,
            logit_cap=0.0,
            has_mla=False,
            use_pdl=False,
        )

    def stock(self) -> None:
        self.stock_work.copy_(self.base)
        q, k, v = self.stock_work.split(
            [self.q_size, self.kv_size, self.kv_size], dim=-1
        )
        gemma_qkv_rmsnorm(
            q,
            k,
            v,
            self.q_weight,
            self.k_weight,
            NUM_Q_HEADS,
            self.num_kv_heads,
            self.head_dim,
            EPS,
        )
        self.rope(self.positions, q, k)
        self.stock_q.copy_(q.view_as(self.stock_q))
        self.stock_k[self.cache_locs] = k.view(
            BATCH, self.num_kv_heads, self.head_dim
        ).to(torch.float8_e5m2)
        self.stock_v[self.cache_locs] = v.view(
            BATCH, self.num_kv_heads, self.head_dim
        ).to(torch.float8_e5m2)
        self.consume(
            self.stock_q,
            self.stock_k,
            self.stock_v,
            self.stock_out,
            self.stock_logits,
            self.stock_lse,
        )
        self.stock_invocations += 1

    def candidate(self) -> None:
        self.candidate_work.copy_(self.base)
        direct_epilogue(
            self.candidate_work,
            self.q_weight,
            self.k_weight,
            self.positions,
            self.rope.cos_sin_cache,
            self.cache_locs,
            self.candidate_q,
            self.candidate_k,
            self.candidate_v,
            self.num_kv_heads,
            self.head_dim,
            self.rotary_dim,
        )
        self.consume(
            self.candidate_q,
            self.candidate_k,
            self.candidate_v,
            self.candidate_out,
            self.candidate_logits,
            self.candidate_lse,
        )
        self.candidate_invocations += 1

    def correctness(self) -> dict[str, object]:
        self.stock()
        torch.cuda.synchronize()
        stock_first = self.stock_out.clone()
        self.stock()
        torch.cuda.synchronize()
        stock_second = self.stock_out.clone()
        self.candidate()
        torch.cuda.synchronize()
        candidate = self.candidate_out.clone()
        aa = relative_l2(stock_second, stock_first)
        candidate_rel = relative_l2(candidate, stock_second)
        q_rel = relative_l2(self.candidate_q, self.stock_q)
        k_rel = relative_l2(
            self.candidate_k[self.cache_locs].to(torch.bfloat16),
            self.stock_k[self.cache_locs].to(torch.bfloat16),
        )
        v_rel = relative_l2(
            self.candidate_v[self.cache_locs].to(torch.bfloat16),
            self.stock_v[self.cache_locs].to(torch.bfloat16),
        )
        threshold = max(0.002, 2 * aa)
        return {
            "consumer_output_shape": list(candidate.shape),
            "consumer_output_stride": list(candidate.stride()),
            "consumer_output_dtype": str(candidate.dtype),
            "stock_aa_relative_l2": aa,
            "candidate_vs_stock_relative_l2": candidate_rel,
            "q_relative_l2": q_rel,
            "k_cache_relative_l2": k_rel,
            "v_cache_relative_l2": v_rel,
            "threshold": threshold,
            "stock_finite": bool(torch.isfinite(stock_second).all().item()),
            "candidate_finite": bool(torch.isfinite(candidate).all().item()),
            "cosine_similarity": float(
                F.cosine_similarity(
                    candidate.float().flatten(),
                    stock_second.float().flatten(),
                    dim=0,
                ).item()
            ),
            "pass": bool(
                torch.isfinite(stock_second).all().item()
                and torch.isfinite(candidate).all().item()
                and candidate_rel <= threshold
            ),
        }

    def measure(self) -> dict[str, object]:
        for _ in range(5):
            self.stock()
            self.candidate()
        torch.cuda.synchronize()
        stock_samples: list[float] = []
        candidate_samples: list[float] = []

        def timed(operation: Callable[[], None]) -> float:
            start = torch.cuda.Event(enable_timing=True)
            end = torch.cuda.Event(enable_timing=True)
            start.record()
            operation()
            end.record()
            end.synchronize()
            return float(start.elapsed_time(end))

        for repetition in range(15):
            if repetition % 2 == 0:
                stock_samples.append(timed(self.stock))
                candidate_samples.append(timed(self.candidate))
            else:
                candidate_samples.append(timed(self.candidate))
                stock_samples.append(timed(self.stock))
        stock = distribution(stock_samples)
        candidate = distribution(candidate_samples)
        stock_median = float(stock["median_ms"])
        candidate_median = float(candidate["median_ms"])
        return {
            "timing_boundary": "CUDA events around qkv-output restore, stock or candidate epilogue/cache layout, and installed SGLang decode_attention_fwd; profiler off",
            "alternating_repetitions": 15,
            "stock": stock,
            "candidate": candidate,
            "median_delta_ms": stock_median - candidate_median,
            "median_ratio": candidate_median / stock_median,
        }

    def traffic_prediction(self) -> dict[str, object]:
        bf16_bytes = 2
        fp8_bytes = 1
        q_elements = self.q_size
        kv_elements = self.kv_size
        stock_epilogue_bytes = (
            2 * bf16_bytes * self.width
            + 2 * bf16_bytes * (q_elements + kv_elements)
            + 2 * (bf16_bytes + fp8_bytes) * kv_elements
        ) * BATCH
        candidate_epilogue_bytes = (
            bf16_bytes * self.width
            + bf16_bytes * q_elements
            + 2 * fp8_bytes * kv_elements
        ) * BATCH
        return {
            "prediction": "Direct consumer-layout output removes stock RoPE materialization and separate K/V cache-write launches.",
            "stock_boundary_launches_before_attention": 5,
            "candidate_boundary_launches_before_attention": 1,
            "predicted_launch_reduction": 4,
            "stock_compulsory_epilogue_tensor_bytes": stock_epilogue_bytes,
            "candidate_compulsory_epilogue_tensor_bytes": candidate_epilogue_bytes,
            "predicted_compulsory_byte_reduction": stock_epilogue_bytes
            - candidate_epilogue_bytes,
            "excludes": "common producer-output restore, weights, positions, trig-cache reads, and identical decode-attention traffic",
        }

    def run(self) -> dict[str, object]:
        correctness = self.correctness()
        if not correctness["pass"]:
            return {
                "name": self.name,
                "correctness": correctness,
                "timing": None,
                "prediction": self.traffic_prediction(),
            }
        timing = self.measure()
        return {
            "name": self.name,
            "geometry": {
                "phase": "decode",
                "batch": BATCH,
                "num_q_heads": NUM_Q_HEADS,
                "num_kv_heads": self.num_kv_heads,
                "head_dim": self.head_dim,
                "rotary_dim": self.rotary_dim,
                "partial_rotary_factor": self.partial_rotary_factor,
                "active_rotary_angles_per_half": self.active_rotary_angles,
                "sequence_length": self.sequence_length,
                "qkv_output_shape": [BATCH, self.width],
                "qkv_output_stride": [self.width, 1],
                "qkv_output_dtype": "torch.bfloat16",
                "kv_cache_dtype": "torch.float8_e5m2",
                "kv_cache_scale_convention": "unit k/v descale, matching retained runtime",
            },
            "correctness": correctness,
            "timing": timing,
            "prediction": self.traffic_prediction(),
            "path_proof": {
                "stock_symbols": [
                    "sglang.srt.layers.gemma4_fused_ops.gemma_qkv_rmsnorm",
                    "RotaryEmbedding.forward_cuda",
                    "sglang.srt.layers.attention.triton_ops.decode_attention.decode_attention_fwd",
                ],
                "candidate_symbol": "_qkv_norm_rope_direct_fp8_cache_kernel",
                "consumer_symbol": "decode_attention_fwd",
                "stock_invocations": self.stock_invocations,
                "candidate_invocations": self.candidate_invocations,
                "candidate_q_storage_separate_from_qkv": self.candidate_q.data_ptr()
                != self.candidate_work.data_ptr(),
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=pathlib.Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    set_global_server_args_for_scheduler(StandaloneServerArgs())
    program = pathlib.Path(__file__).resolve()
    identity = {
        "schema_version": 1,
        "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "runtime": "SGLang v0.5.13@28b095c01005d4a3a2a5b637b7d028b07fba31b2",
        "image": os.environ.get("RUNTIME_IMAGE_IDENTITY"),
        "gpu": torch.cuda.get_device_name(),
        "gpu_uuid": os.environ.get("BOUND_GPU_UUID"),
        "torch": torch.__version__,
        "triton": triton.__version__,
        "program": str(program),
        "program_sha256": hashlib.sha256(program.read_bytes()).hexdigest(),
        "installed_sources": {
            "gemma4_causal_sha256": "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989",
            "radix_attention_sha256": "9b1ef7de85b9f0fe9720954edbf94c2b4abd7a57fef7e4dac2500ff3dcdf7be9",
            "triton_backend_sha256": "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d",
            "decode_attention_sha256": "1040f43a9ea579b944aa037b585997f8d7b585d85f459a1b1f420002b4bd092a",
        },
    }
    atomic_json(args.output_dir / "IDENTITY.json", identity)
    started = time.time()
    cases = [
        Case("local_decode_c32", 16, 256, 1.0, 10000.0, "default", 1024),
        Case("global_decode_c32", 4, 512, 0.25, 1000000.0, "proportional", 4570),
    ]
    (args.output_dir / "SCIENTIFIC_STARTED").write_text(f"{time.time()}\n")
    rows: list[dict[str, object]] = []
    for case in cases:
        row = case.run()
        rows.append(row)
        atomic_json(args.output_dir / f"{case.name}.json", row)
    all_correct = all(bool(row["correctness"]["pass"]) for row in rows)
    all_timed = all(row["timing"] is not None for row in rows)
    median_delta = sum(
        float(row["timing"]["median_delta_ms"]) for row in rows if row["timing"]
    )
    classification = (
        "component_positive"
        if all_correct and all_timed and median_delta > 0
        else "component_negative"
        if all_correct and all_timed
        else "numerical_or_structural_invalid"
    )
    result = {
        "schema_version": 1,
        "classification": classification,
        "science_consumed": True,
        "endpoint_submissions": 0,
        "profiler_enabled": False,
        "rows": rows,
        "all_correct": all_correct,
        "all_timed": all_timed,
        "sum_local_global_median_delta_ms_per_layer_pair": median_delta,
        "useful_gpu_seconds": time.time() - started,
    }
    atomic_json(args.output_dir / "RESULT.json", result)
    atomic_json(
        args.output_dir / "TERMINAL.json",
        {
            "schema_version": 1,
            "classification": classification,
            "science_consumed": True,
            "all_correct": all_correct,
            "all_timed": all_timed,
            "result": str(args.output_dir / "RESULT.json"),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
