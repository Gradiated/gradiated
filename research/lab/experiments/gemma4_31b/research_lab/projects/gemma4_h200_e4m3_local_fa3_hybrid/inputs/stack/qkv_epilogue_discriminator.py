#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import statistics
import subprocess
import time
from collections.abc import Callable

import torch
import torch.nn.functional as F
import triton
import triton.language as tl

from sglang.srt.layers.gemma4_fused_ops import gemma_qkv_rmsnorm
from sglang.srt.layers.rotary_embedding import get_rope
from sglang.srt.server_args import set_global_server_args_for_scheduler


SEED = 20260720
BATCH = 32
FRESH_PROMPT_TOKENS = 117728
PREFILL_CHUNK_TOKENS = 2048
PREFILL_EQUIVALENT_INVOCATIONS = FRESH_PROMPT_TOKENS // PREFILL_CHUNK_TOKENS
OUTPUT_TOKENS = 358
DECODE_INVOCATIONS = OUTPUT_TOKENS - 1
LOCAL_LAYERS = 50
GLOBAL_LAYERS = 10
REQUIRED_SAVING_SECONDS_PER_REQUEST = 0.04597286970625021
SOURCE_COMMIT = "127b9e3283f7c2a43234b852ff5c9f1796d53624"
MODEL = "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4"
_AUDITED_GEOMETRIES: set[tuple[int, int, int]] = set()


class StandaloneServerArgs:
    rl_on_policy_target = None


@triton.jit
def _qkv_norm_rope_inplace_kernel(
    qkv_ptr,
    q_weight_ptr,
    k_weight_ptr,
    positions_ptr,
    cos_sin_cache_ptr,
    stride_token,
    NUM_Q_HEADS: tl.constexpr,
    NUM_KV_HEADS: tl.constexpr,
    HEAD_DIM: tl.constexpr,
    HALF_DIM: tl.constexpr,
    Q_SIZE: tl.constexpr,
    KV_SIZE: tl.constexpr,
    EPS: tl.constexpr,
    BLOCK_HALF: tl.constexpr,
):
    token = tl.program_id(0)
    head_slot = tl.program_id(1)
    half_offsets = tl.arange(0, BLOCK_HALF)
    half_mask = half_offsets < HALF_DIM

    is_q = head_slot < NUM_Q_HEADS
    is_k = (head_slot >= NUM_Q_HEADS) & (
        head_slot < NUM_Q_HEADS + NUM_KV_HEADS
    )
    head = tl.where(
        is_q,
        head_slot,
        tl.where(is_k, head_slot - NUM_Q_HEADS, head_slot - NUM_Q_HEADS - NUM_KV_HEADS),
    )
    segment = tl.where(is_q, 0, tl.where(is_k, Q_SIZE, Q_SIZE + KV_SIZE))
    base = token * stride_token + segment + head * HEAD_DIM

    x0 = tl.load(qkv_ptr + base + half_offsets, mask=half_mask, other=0.0).to(
        tl.float32
    )
    x1 = tl.load(
        qkv_ptr + base + HALF_DIM + half_offsets, mask=half_mask, other=0.0
    ).to(tl.float32)
    sum_squares = tl.sum(x0 * x0 + x1 * x1, axis=0)
    inverse_rms = tl.rsqrt(sum_squares / HEAD_DIM + EPS)

    q_weight0 = tl.load(q_weight_ptr + half_offsets, mask=half_mask, other=0.0).to(
        tl.float32
    )
    q_weight1 = tl.load(
        q_weight_ptr + HALF_DIM + half_offsets, mask=half_mask, other=0.0
    ).to(tl.float32)
    k_weight0 = tl.load(k_weight_ptr + half_offsets, mask=half_mask, other=0.0).to(
        tl.float32
    )
    k_weight1 = tl.load(
        k_weight_ptr + HALF_DIM + half_offsets, mask=half_mask, other=0.0
    ).to(tl.float32)
    weight0 = tl.where(is_q, q_weight0, tl.where(is_k, k_weight0, 1.0))
    weight1 = tl.where(is_q, q_weight1, tl.where(is_k, k_weight1, 1.0))
    normalized0 = x0 * inverse_rms * weight0
    normalized1 = x1 * inverse_rms * weight1

    position = tl.load(positions_ptr + token)
    cache_base = position * HEAD_DIM
    cosine = tl.load(
        cos_sin_cache_ptr + cache_base + half_offsets,
        mask=half_mask,
        other=1.0,
    ).to(tl.float32)
    sine = tl.load(
        cos_sin_cache_ptr + cache_base + HALF_DIM + half_offsets,
        mask=half_mask,
        other=0.0,
    ).to(tl.float32)
    rotated0 = normalized0 * cosine - normalized1 * sine
    rotated1 = normalized1 * cosine + normalized0 * sine
    apply_rope = is_q | is_k
    output0 = tl.where(apply_rope, rotated0, normalized0)
    output1 = tl.where(apply_rope, rotated1, normalized1)

    tl.store(qkv_ptr + base + half_offsets, output0, mask=half_mask)
    tl.store(qkv_ptr + base + HALF_DIM + half_offsets, output1, mask=half_mask)


def qkv_norm_rope_inplace(
    qkv: torch.Tensor,
    q_weight: torch.Tensor,
    k_weight: torch.Tensor,
    positions: torch.Tensor,
    cos_sin_cache: torch.Tensor,
    num_q_heads: int,
    num_kv_heads: int,
    head_dim: int,
    eps: float,
) -> None:
    q_size = num_q_heads * head_dim
    kv_size = num_kv_heads * head_dim
    if qkv.ndim != 2 or qkv.shape[1] != q_size + 2 * kv_size:
        raise ValueError("qkv projection output has the wrong exact shape")
    if qkv.stride(1) != 1 or not qkv.is_cuda:
        raise ValueError("qkv projection output must be contiguous on CUDA")
    if q_weight.shape != (head_dim,) or k_weight.shape != (head_dim,):
        raise ValueError("Q/K normalization weights must match head_dim")
    if positions.shape != (qkv.shape[0],) or positions.dtype != torch.int64:
        raise ValueError("positions must be one int64 value per token")
    if cos_sin_cache.ndim != 2 or cos_sin_cache.shape[1] != head_dim:
        raise ValueError("Gemma 4 cos/sin cache must have one full head per position")
    audit_path = os.environ.get("QKV_EPILOGUE_AUDIT")
    geometry = (num_q_heads, num_kv_heads, head_dim)
    if audit_path and geometry not in _AUDITED_GEOMETRIES:
        with pathlib.Path(audit_path).open("a") as handle:
            handle.write(
                json.dumps(
                    {
                        "candidate_symbol": "_qkv_norm_rope_inplace_kernel",
                        "num_tokens": qkv.shape[0],
                        "num_q_heads": num_q_heads,
                        "num_kv_heads": num_kv_heads,
                        "head_dim": head_dim,
                        "dtype": str(qkv.dtype),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        _AUDITED_GEOMETRIES.add(geometry)
    half_dim = head_dim // 2
    _qkv_norm_rope_inplace_kernel[(qkv.shape[0], num_q_heads + 2 * num_kv_heads)](
        qkv,
        q_weight,
        k_weight,
        positions,
        cos_sin_cache,
        qkv.stride(0),
        NUM_Q_HEADS=num_q_heads,
        NUM_KV_HEADS=num_kv_heads,
        HEAD_DIM=head_dim,
        HALF_DIM=half_dim,
        Q_SIZE=q_size,
        KV_SIZE=kv_size,
        EPS=eps,
        BLOCK_HALF=triton.next_power_of_2(half_dim),
        num_warps=4,
    )


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


def tensor_metrics(actual: torch.Tensor, reference: torch.Tensor) -> dict[str, object]:
    actual_float = actual.float()
    reference_float = reference.float()
    difference = actual_float - reference_float
    reference_rms = torch.sqrt(torch.mean(reference_float * reference_float))
    normalized_rmse = torch.sqrt(torch.mean(difference * difference)) / reference_rms
    cosine = F.cosine_similarity(actual_float.flatten(), reference_float.flatten(), dim=0)
    return {
        "finite": bool(torch.isfinite(actual_float).all().item()),
        "maximum_absolute_error": float(difference.abs().max().item()),
        "normalized_rmse": float(normalized_rmse.item()),
        "cosine_similarity": float(cosine.item()),
    }


def nvidia_smi() -> dict[str, object]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,uuid,clocks.sm,clocks.mem,power.draw,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(command, text=True, capture_output=True)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


class ExactCase:
    def __init__(
        self,
        name: str,
        tokens: int,
        num_kv_heads: int,
        head_dim: int,
        rope_theta: float,
        rope_type: str,
        partial_rotary_factor: float,
        position_mode: str,
    ) -> None:
        self.name = name
        self.tokens = tokens
        self.num_q_heads = 32
        self.num_kv_heads = num_kv_heads
        self.head_dim = head_dim
        self.q_size = self.num_q_heads * head_dim
        self.kv_size = num_kv_heads * head_dim
        self.total_size = self.q_size + 2 * self.kv_size
        self.eps = 1e-6
        torch.manual_seed(SEED + tokens + head_dim + num_kv_heads)
        self.base = (
            torch.randn((tokens, self.total_size), device="cuda", dtype=torch.bfloat16)
            / math.sqrt(head_dim)
        ).contiguous()
        self.stock_buffer = self.base.clone()
        self.candidate_buffer = self.base.clone()
        self.q_weight = (1.0 + 0.02 * torch.randn(head_dim, device="cuda")).to(
            torch.bfloat16
        )
        self.k_weight = (1.0 + 0.02 * torch.randn(head_dim, device="cuda")).to(
            torch.bfloat16
        )
        if position_mode == "decode":
            self.positions = torch.full(
                (tokens,), 4570, device="cuda", dtype=torch.int64
            )
        else:
            self.positions = torch.arange(tokens, device="cuda", dtype=torch.int64)
        self.rope = get_rope(
            head_dim,
            rotary_dim=head_dim,
            max_position=5000,
            base=rope_theta,
            rope_scaling={"rope_type": rope_type},
            partial_rotary_factor=partial_rotary_factor,
            is_neox_style=True,
        )
        self.rope = self.rope.cuda()
        self.rope(self.positions, self.stock_q(), self.stock_k())
        self.stock_buffer.copy_(self.base)

    def stock_q(self) -> torch.Tensor:
        return self.stock_buffer[:, : self.q_size]

    def stock_k(self) -> torch.Tensor:
        return self.stock_buffer[:, self.q_size : self.q_size + self.kv_size]

    def stock_v(self) -> torch.Tensor:
        return self.stock_buffer[:, self.q_size + self.kv_size :]

    def stock(self) -> None:
        q = self.stock_q()
        k = self.stock_k()
        v = self.stock_v()
        gemma_qkv_rmsnorm(
            q,
            k,
            v,
            self.q_weight,
            self.k_weight,
            self.num_q_heads,
            self.num_kv_heads,
            self.head_dim,
            self.eps,
        )
        self.rope(self.positions, q, k)

    def candidate(self) -> None:
        qkv_norm_rope_inplace(
            self.candidate_buffer,
            self.q_weight,
            self.k_weight,
            self.positions,
            self.rope.cos_sin_cache,
            self.num_q_heads,
            self.num_kv_heads,
            self.head_dim,
            self.eps,
        )

    def reference(self) -> torch.Tensor:
        qkv = self.base.float().clone()
        q, k, v = qkv.split([self.q_size, self.kv_size, self.kv_size], dim=-1)
        q = q.view(self.tokens, self.num_q_heads, self.head_dim)
        k = k.view(self.tokens, self.num_kv_heads, self.head_dim)
        v = v.view(self.tokens, self.num_kv_heads, self.head_dim)
        q = q * torch.rsqrt(torch.mean(q * q, dim=-1, keepdim=True) + self.eps)
        q = q * self.q_weight.float()
        k = k * torch.rsqrt(torch.mean(k * k, dim=-1, keepdim=True) + self.eps)
        k = k * self.k_weight.float()
        v = v * torch.rsqrt(torch.mean(v * v, dim=-1, keepdim=True) + self.eps)
        cache = self.rope.cos_sin_cache.index_select(0, self.positions).float()
        cosine, sine = cache.chunk(2, dim=-1)
        cosine = cosine[:, None, :]
        sine = sine[:, None, :]

        def rotate(value: torch.Tensor) -> torch.Tensor:
            first, second = value.chunk(2, dim=-1)
            return torch.cat(
                (first * cosine - second * sine, second * cosine + first * sine),
                dim=-1,
            )

        return torch.cat(
            (
                rotate(q).reshape(self.tokens, self.q_size),
                rotate(k).reshape(self.tokens, self.kv_size),
                v.reshape(self.tokens, self.kv_size),
            ),
            dim=-1,
        ).to(torch.bfloat16)

    def oracle(self) -> dict[str, object]:
        self.stock_buffer.copy_(self.base)
        self.candidate_buffer.copy_(self.base)
        self.stock()
        self.candidate()
        torch.cuda.synchronize()
        reference = self.reference()
        stock_metrics = tensor_metrics(self.stock_buffer, reference)
        candidate_metrics = tensor_metrics(self.candidate_buffer, reference)
        self.candidate_buffer.copy_(self.base)
        self.candidate()
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        before = torch.cuda.memory_allocated()
        pointer_before = self.candidate_buffer.data_ptr()
        self.candidate()
        torch.cuda.synchronize()
        after = torch.cuda.memory_allocated()
        peak = torch.cuda.max_memory_allocated()
        result = {
            "stock": stock_metrics,
            "candidate": candidate_metrics,
            "candidate_buffer_pointer_unchanged": pointer_before
            == self.candidate_buffer.data_ptr(),
            "candidate_dynamic_live_bytes": after - before,
            "candidate_peak_delta_bytes": peak - before,
        }
        result["pass"] = bool(
            stock_metrics["finite"]
            and candidate_metrics["finite"]
            and candidate_metrics["normalized_rmse"] <= 0.005
            and candidate_metrics["cosine_similarity"] >= 0.9999
            and result["candidate_buffer_pointer_unchanged"]
            and result["candidate_dynamic_live_bytes"] == 0
        )
        return result

    def traffic(self) -> dict[str, object]:
        dtype_bytes = self.base.element_size()
        qk_elements = self.q_size + self.kv_size
        stock_minimum_bytes = 2 * dtype_bytes * (self.total_size + qk_elements)
        candidate_minimum_bytes = 2 * dtype_bytes * self.total_size
        return {
            "per_token": {
                "stock_minimum_tensor_bytes": stock_minimum_bytes,
                "candidate_minimum_tensor_bytes": candidate_minimum_bytes,
                "eliminated_intermediate_bytes": stock_minimum_bytes
                - candidate_minimum_bytes,
                "stock_launches": 2,
                "candidate_launches": 1,
            },
            "basis": "Projection output read/write plus the stock normalized Q/K read/write; weights, positions, and RoPE-cache reads are excluded from both minimums.",
        }


def grouped_wall_samples(
    operation: Callable[[], None], inner: int, sample_count: int
) -> list[float]:
    for _ in range(8):
        operation()
    torch.cuda.synchronize()
    samples: list[float] = []
    for _ in range(sample_count):
        torch.cuda.synchronize()
        started = time.perf_counter_ns()
        for _ in range(inner):
            operation()
        torch.cuda.synchronize()
        samples.append((time.perf_counter_ns() - started) / inner / 1e6)
    return samples


def profile_launches(operation: Callable[[], None]) -> dict[str, object]:
    try:
        with torch.profiler.profile(
            activities=[torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA]
        ) as profile:
            operation()
            torch.cuda.synchronize()
        cuda_events = [
            event.name
            for event in profile.events()
            if str(event.device_type).lower().endswith("cuda")
        ]
        return {"pass": True, "cuda_event_count": len(cuda_events), "cuda_events": cuda_events}
    except Exception as error:
        return {"pass": False, "error_type": type(error).__name__, "message": str(error)}


def resource_use(case: ExactCase) -> dict[str, object]:
    properties = torch.cuda.get_device_properties(torch.cuda.current_device())
    candidate_blocks = case.tokens * (case.num_q_heads + 2 * case.num_kv_heads)
    result: dict[str, object] = {
        "gpu_sms": properties.multi_processor_count,
        "stock": {
            "qkv_norm_blocks": case.tokens,
            "rope_blocks": case.tokens,
            "rope_threads_per_block": 512,
            "decode_sm_coverage_fraction_per_launch": min(
                1.0, case.tokens / properties.multi_processor_count
            ),
            "source_basis": "Pinned gemma_qkv_rmsnorm uses grid=(tokens,) and pinned rotary_embedding_kernel uses grid=(tokens,) with min(num_q_heads * rot_dim / 2, 512) threads.",
        },
        "candidate": {
            "blocks": candidate_blocks,
            "threads_per_block": 128,
            "cta_waves": candidate_blocks / properties.multi_processor_count,
            "num_warps": 4,
        },
    }
    try:
        compiled = _qkv_norm_rope_inplace_kernel.warmup(
            case.candidate_buffer,
            case.q_weight,
            case.k_weight,
            case.positions,
            case.rope.cos_sin_cache,
            case.candidate_buffer.stride(0),
            NUM_Q_HEADS=case.num_q_heads,
            NUM_KV_HEADS=case.num_kv_heads,
            HEAD_DIM=case.head_dim,
            HALF_DIM=case.head_dim // 2,
            Q_SIZE=case.q_size,
            KV_SIZE=case.kv_size,
            EPS=case.eps,
            BLOCK_HALF=triton.next_power_of_2(case.head_dim // 2),
            num_warps=4,
            grid=(case.tokens, case.num_q_heads + 2 * case.num_kv_heads),
        )
        metadata = compiled.metadata
        registers_per_thread = int(compiled.n_regs)
        shared_bytes = int(getattr(metadata, "shared", 0))
        threads_per_block = 128
        register_limited_blocks = 65536 // max(1, registers_per_thread * threads_per_block)
        thread_limited_blocks = properties.max_threads_per_multi_processor // threads_per_block
        shared_limited_blocks = (
            properties.shared_memory_per_multiprocessor // shared_bytes
            if shared_bytes
            else 32
        )
        active_blocks = min(32, register_limited_blocks, thread_limited_blocks, shared_limited_blocks)
        result["candidate"].update(
            {
                "compile_metadata_pass": True,
                "registers_per_thread": registers_per_thread,
                "shared_memory_bytes_per_block": shared_bytes,
                "spills": int(getattr(compiled, "n_spills", 0)),
                "analytical_active_blocks_per_sm": active_blocks,
                "analytical_occupancy_fraction": active_blocks * threads_per_block
                / properties.max_threads_per_multi_processor,
            }
        )
    except Exception as error:
        result["candidate"].update(
            {
                "compile_metadata_pass": False,
                "compile_metadata_error_type": type(error).__name__,
                "compile_metadata_message": str(error),
            }
        )
    return result


def benchmark_case(case: ExactCase, inner: int) -> dict[str, object]:
    oracle = case.oracle()
    case.stock_buffer.copy_(case.base)
    case.candidate_buffer.copy_(case.base)
    stock_samples: list[float] = []
    candidate_samples: list[float] = []
    for sample in range(21):
        if sample % 2 == 0:
            stock_samples.extend(grouped_wall_samples(case.stock, inner, 1))
            candidate_samples.extend(grouped_wall_samples(case.candidate, inner, 1))
        else:
            candidate_samples.extend(grouped_wall_samples(case.candidate, inner, 1))
            stock_samples.extend(grouped_wall_samples(case.stock, inner, 1))
    stock_p05 = percentile(stock_samples, 0.05)
    stock_p50 = statistics.median(stock_samples)
    candidate_p50 = statistics.median(candidate_samples)
    candidate_p95 = percentile(candidate_samples, 0.95)
    return {
        "name": case.name,
        "tokens": case.tokens,
        "num_q_heads": case.num_q_heads,
        "num_kv_heads": case.num_kv_heads,
        "head_dim": case.head_dim,
        "qkv_width": case.total_size,
        "timing_boundary": "host monotonic wall around an inner group with CUDA synchronization only at group boundaries",
        "inner_iterations": inner,
        "samples": 21,
        "stock_wall_ms": stock_samples,
        "candidate_wall_ms": candidate_samples,
        "stock_p05_ms": stock_p05,
        "stock_p50_ms": stock_p50,
        "candidate_p50_ms": candidate_p50,
        "candidate_p95_ms": candidate_p95,
        "median_saving_ms": stock_p50 - candidate_p50,
        "conservative_saving_ms": stock_p05 - candidate_p95,
        "oracle": oracle,
        "traffic": case.traffic(),
        "resource_use": resource_use(case),
        "launch_profile": {
            "stock": profile_launches(case.stock),
            "candidate": profile_launches(case.candidate),
        },
    }


def source_identity() -> dict[str, object]:
    modules = {
        "gemma4_fused_ops": __import__(
            "sglang.srt.layers.gemma4_fused_ops", fromlist=["x"]
        ),
        "rotary_embedding_base": __import__(
            "sglang.srt.layers.rotary_embedding.base", fromlist=["x"]
        ),
        "gemma4_causal": __import__("sglang.srt.models.gemma4_causal", fromlist=["x"]),
    }
    result: dict[str, object] = {}
    for name, module in modules.items():
        path = pathlib.Path(module.__file__).resolve()
        source = path.read_bytes()
        result[name] = {"path": str(path), "sha256": hashlib.sha256(source).hexdigest()}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    program_path = pathlib.Path(__file__).resolve()
    program_sha256 = hashlib.sha256(program_path.read_bytes()).hexdigest()
    identity = {
        "model": MODEL,
        "source_commit": SOURCE_COMMIT,
        "runtime_image": os.environ.get("RUNTIME_IMAGE_IDENTITY"),
        "program_path": str(program_path),
        "program_sha256": program_sha256,
        "gpu": torch.cuda.get_device_name(),
        "compute_capability": list(torch.cuda.get_device_capability()),
        "torch": torch.__version__,
        "triton": triton.__version__,
        "pinned_sources": source_identity(),
        "stock_symbols": ["gemma_qkv_rmsnorm", "RotaryEmbedding.forward_cuda"],
        "candidate_symbol": "_qkv_norm_rope_inplace_kernel",
    }
    atomic_json(args.output_dir / "IDENTITY.json", identity)
    atomic_json(args.output_dir / "CLOCKS_BEFORE.json", nvidia_smi())
    (args.output_dir / "SCIENTIFIC_STARTED").write_text(str(time.time()) + "\n")
    set_global_server_args_for_scheduler(StandaloneServerArgs())

    cases = [
        ExactCase("local_decode_c32", BATCH, 16, 256, 10000.0, "default", 1.0, "decode"),
        ExactCase("global_decode_c32", BATCH, 4, 512, 1000000.0, "proportional", 0.25, "decode"),
        ExactCase("local_prefill_chunk2048", PREFILL_CHUNK_TOKENS, 16, 256, 10000.0, "default", 1.0, "prefill"),
        ExactCase("global_prefill_chunk2048", PREFILL_CHUNK_TOKENS, 4, 512, 1000000.0, "proportional", 0.25, "prefill"),
    ]
    rows = [
        benchmark_case(case, 100 if case.tokens == BATCH else 4) for case in cases
    ]
    row_by_name = {row["name"]: row for row in rows}
    decode_saving_ms = (
        LOCAL_LAYERS * row_by_name["local_decode_c32"]["conservative_saving_ms"]
        + GLOBAL_LAYERS * row_by_name["global_decode_c32"]["conservative_saving_ms"]
    ) * DECODE_INVOCATIONS
    prefill_saving_ms = (
        LOCAL_LAYERS
        * row_by_name["local_prefill_chunk2048"]["conservative_saving_ms"]
        + GLOBAL_LAYERS
        * row_by_name["global_prefill_chunk2048"]["conservative_saving_ms"]
    ) * PREFILL_EQUIVALENT_INVOCATIONS
    conservative_saving_seconds_per_request = (
        decode_saving_ms + prefill_saving_ms
    ) / 1000 / BATCH
    numerical_pass = all(bool(row["oracle"]["pass"]) for row in rows)
    no_materialization_pass = all(
        bool(row["oracle"]["candidate_buffer_pointer_unchanged"])
        and int(row["oracle"]["candidate_dynamic_live_bytes"]) == 0
        for row in rows
    )
    component_pass = bool(
        numerical_pass
        and no_materialization_pass
        and conservative_saving_seconds_per_request
        >= REQUIRED_SAVING_SECONDS_PER_REQUEST
    )
    result = {
        "schema_version": 1,
        "kind": "gemma4_h200_qkv_norm_rope_projection_epilogue_discriminator",
        "scientific_terminal": True,
        "candidate_invocations": 1,
        "rows": rows,
        "occurrence_weighting": {
            "local_layers": LOCAL_LAYERS,
            "global_layers": GLOBAL_LAYERS,
            "fresh_prompt_tokens": FRESH_PROMPT_TOKENS,
            "prefill_chunk_tokens": PREFILL_CHUNK_TOKENS,
            "conservative_full_prefill_chunks": PREFILL_EQUIVALENT_INVOCATIONS,
            "output_tokens_per_request": OUTPUT_TOKENS,
            "conservative_decode_invocations": DECODE_INVOCATIONS,
            "batch": BATCH,
            "decode_saving_ms_per_batch": decode_saving_ms,
            "prefill_saving_ms_per_batch": prefill_saving_ms,
        },
        "oracles": {
            "numerical_pass": numerical_pass,
            "no_materialization_pass": no_materialization_pass,
        },
        "decision": {
            "component_pass": component_pass,
            "conservative_saving_seconds_per_request": conservative_saving_seconds_per_request,
            "required_saving_seconds_per_request": REQUIRED_SAVING_SECONDS_PER_REQUEST,
            "conditional_bf16_c32_endpoint_required": component_pass,
            "terminal": (
                "component_pass"
                if component_pass
                else (
                    "numeric_negative"
                    if not numerical_pass
                    else (
                        "path_unproven"
                        if not no_materialization_pass
                        else "component_negative"
                    )
                )
            ),
        },
    }
    atomic_json(args.output_dir / "RESULT.json", result)
    atomic_json(args.output_dir / "CLOCKS_AFTER.json", nvidia_smi())
    terminal = {
        "schema_version": 1,
        "stage": "component",
        "scientific_terminal": True,
        "candidate_invocations": 1,
        "pass": component_pass,
        **result["decision"],
    }
    atomic_json(args.output_dir / "TERMINAL.json", terminal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
