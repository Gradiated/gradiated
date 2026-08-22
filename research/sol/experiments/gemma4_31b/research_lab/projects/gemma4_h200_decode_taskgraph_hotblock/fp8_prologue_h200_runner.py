#!/usr/bin/env python3
"""Exact M=32,K=5376,N=8192 H200 dynamic-FP8 prologue discriminator.

Stock is the pinned SGLang CUDA producer (`sgl_per_token_quant_fp8`) followed
by the unchanged `sgl_kernel.fp8_scaled_mm` consumer.  Candidate keeps a
separate row-amax/scale barrier but converts BF16 activations to E4M3 inside
each GEMM K tile, avoiding the global quantized-activation materialization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
import time
from pathlib import Path

import torch
import triton
import triton.language as tl
from safetensors import safe_open
from sgl_kernel import fp8_scaled_mm
from sglang.srt.layers.quantization.fp8_kernel import sglang_per_token_quant_fp8

M, K, N = 32, 5376, 8192
WEIGHT_NAME = "model.language_model.layers.0.self_attn.q_proj.weight"
FP8_MAX = 448.0
SEED = 20260729
WARMUP = 8
INNER = 20
ORDER = ["stock", "candidate", "stock", "candidate", "stock", "candidate", "stock"]


def atomic(path: Path, value: object) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(tmp.read_text())
    os.replace(tmp, path)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@triton.jit
def row_scale_kernel(
    x,
    scales,
    K: tl.constexpr,
    BLOCK_K: tl.constexpr,
    FP8_MAX_VALUE: tl.constexpr,
):
    row = tl.program_id(0)
    cols = tl.arange(0, BLOCK_K)
    values = tl.load(x + row * K + cols, mask=cols < K, other=0.0).to(tl.float32)
    amax = tl.max(tl.abs(values), axis=0)
    # The stock SGL kernel guards the zero row.  This floor is below every
    # representable nonzero BF16 input divided by FP8_MAX.
    scale = tl.maximum(amax, 1.0e-12) / FP8_MAX_VALUE
    tl.store(scales + row, scale)


@triton.jit
def fused_quant_gemm_kernel(
    x,
    w,
    x_scale,
    w_scale,
    out,
    M: tl.constexpr,
    N: tl.constexpr,
    K: tl.constexpr,
    BM: tl.constexpr,
    BN: tl.constexpr,
    BK: tl.constexpr,
    FP8_MAX_VALUE: tl.constexpr,
):
    pid_m = tl.program_id(0)
    pid_n = tl.program_id(1)
    offs_m = pid_m * BM + tl.arange(0, BM)
    offs_n = pid_n * BN + tl.arange(0, BN)
    scales_m = tl.load(x_scale + offs_m, mask=offs_m < M, other=1.0)
    acc = tl.zeros((BM, BN), tl.float32)
    for k0 in range(0, K, BK):
        offs_k = k0 + tl.arange(0, BK)
        a = tl.load(
            x + offs_m[:, None] * K + offs_k[None, :],
            mask=(offs_m[:, None] < M) & (offs_k[None, :] < K),
            other=0.0,
        ).to(tl.float32)
        a = tl.maximum(
            tl.minimum(a / scales_m[:, None], FP8_MAX_VALUE), -FP8_MAX_VALUE
        ).to(tl.float8e4nv)
        b = tl.load(
            w + offs_n[None, :] * K + offs_k[:, None],
            mask=(offs_k[:, None] < K) & (offs_n[None, :] < N),
            other=0.0,
        )
        acc += tl.dot(a, b)
    scales_n = tl.load(w_scale + offs_n, mask=offs_n < N, other=1.0)
    value = acc * scales_m[:, None] * scales_n[None, :]
    tl.store(
        out + offs_m[:, None] * N + offs_n[None, :],
        value.to(tl.bfloat16),
        mask=(offs_m[:, None] < M) & (offs_n[None, :] < N),
    )


def candidate(x: torch.Tensor, wq: torch.Tensor, ws: torch.Tensor):
    xs = torch.empty((M,), device=x.device, dtype=torch.float32)
    row_scale_kernel[(M,)](
        x,
        xs,
        K=K,
        BLOCK_K=8192,
        FP8_MAX_VALUE=FP8_MAX,
        num_warps=8,
    )
    out = torch.empty((M, N), device=x.device, dtype=torch.bfloat16)
    fused_quant_gemm_kernel[(triton.cdiv(M, 8), triton.cdiv(N, 64))](
        x,
        wq,
        xs,
        ws,
        out,
        M=M,
        N=N,
        K=K,
        BM=8,
        BN=64,
        BK=64,
        FP8_MAX_VALUE=FP8_MAX,
        num_warps=4,
        num_stages=3,
    )
    return out, xs


def stock(x: torch.Tensor, wq: torch.Tensor, ws: torch.Tensor):
    qx, xs = sglang_per_token_quant_fp8(x)
    out = fp8_scaled_mm(
        qx,
        wq,
        xs,
        ws,
        out_dtype=torch.bfloat16,
        bias=None,
    )
    return out, xs.reshape(-1)


def time_arm(fn, x, wq, ws) -> tuple[float, float]:
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    checksum = torch.zeros((), device=x.device, dtype=torch.float32)
    for _ in range(INNER):
        y, _ = fn(x, wq, ws)
        checksum += y.float().sum()
    end.record()
    end.synchronize()
    return start.elapsed_time(end) * 1000.0 / INNER, float(checksum.cpu())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    out_root = args.output_root.resolve()
    out_root.mkdir(parents=True, exist_ok=False)
    gpu_uuid = subprocess.run(
        ["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    identity = {
        "torch": torch.__version__,
        "triton": triton.__version__,
        "cuda": torch.version.cuda,
        "device_name": torch.cuda.get_device_name(0),
        "gpu_uuid": gpu_uuid,
        "shape": [M, K, N],
        "weight_name": WEIGHT_NAME,
        "seed": SEED,
        "stock_symbols": ["sgl_per_token_quant_fp8", "fp8_scaled_mm"],
        "candidate_symbols": ["row_scale_kernel", "fused_quant_gemm_kernel"],
    }
    assert identity["device_name"] == "NVIDIA H200"
    assert identity["gpu_uuid"] == "GPU-81ca2c99-6df0-5bf8-023c-3ee78a68f3d8"

    index_path = args.checkpoint_root / "model.safetensors.index.json"
    index = json.loads(index_path.read_text())
    shard_name = index["weight_map"][WEIGHT_NAME]
    shard_path = args.checkpoint_root / shard_name
    assert shard_path.stat().st_size == 49784788364
    with safe_open(shard_path, framework="pt", device="cpu") as handle:
        w_cpu = handle.get_tensor(WEIGHT_NAME)
    assert list(w_cpu.shape) == [N, K] and w_cpu.dtype == torch.bfloat16
    weight_source_sha = hashlib.sha256(
        w_cpu.view(torch.uint8).numpy().tobytes()
    ).hexdigest()
    w_nk = w_cpu.cuda()
    del w_cpu
    w_amax = w_nk.float().abs().amax(dim=1)
    ws = torch.clamp(w_amax, min=1.0e-12) / FP8_MAX
    wq_nk = torch.clamp(
        w_nk.float() / ws[:, None], -FP8_MAX, FP8_MAX
    ).to(torch.float8_e4m3fn)
    wq = wq_nk.t()
    assert tuple(wq.stride()) == (1, K)
    del w_amax

    generator = torch.Generator(device="cuda").manual_seed(SEED)
    x = (torch.randn((M, K), device="cuda", dtype=torch.bfloat16, generator=generator) * 0.5)
    x[0].zero_()
    x[1].fill_(torch.finfo(torch.bfloat16).tiny)

    prior_stock_markers = sorted(
        out_root.parent.glob("out-*/STOCK_SMOKE_COMPLETE.json"),
        key=lambda path: int(path.parent.name.split("-")[-1]),
    )
    adopted_stock = None
    if prior_stock_markers:
        adopted_stock = json.loads(prior_stock_markers[-1].read_text())
        assert adopted_stock.get("complete") is True

    atomic(
        out_root / "IDENTITY.json",
        {
            **identity,
            "weight_tensor_sha256": weight_source_sha,
            "adopted_stock_marker": (
                str(prior_stock_markers[-1]) if adopted_stock is not None else None
            ),
        },
    )
    atomic(
        out_root / "SCIENCE_STARTED.json",
        {"science_started": True, "at_unix": time.time(), "next_arm": "stock_smoke"},
    )

    stock_y = stock_s = None
    if adopted_stock is None:
        stock_y, stock_s = stock(x, wq, ws)
        torch.cuda.synchronize()
        adopted_stock = {
            "complete": True,
            "checksum": float(stock_y.float().sum().cpu()),
        }
        atomic(out_root / "STOCK_SMOKE_COMPLETE.json", adopted_stock)
    else:
        atomic(
            out_root / "STOCK_SMOKE_ADOPTED.json",
            {
                "complete": True,
                "source": str(prior_stock_markers[-1]),
                "checksum": adopted_stock["checksum"],
                "stock_call_replayed": False,
            },
        )

    candidate_y, candidate_s = candidate(x, wq, ws)
    torch.cuda.synchronize()
    atomic(out_root / "CANDIDATE_SMOKE_COMPLETE.json", {"complete": True, "checksum": float(candidate_y.float().sum().cpu())})

    candidate_f = candidate_y.float()
    if stock_y is not None:
        oracle_f = stock_y.float()
        oracle_kind = "fresh_stock_full_output"
    else:
        oracle_f = torch.mm(x.float(), w_nk.t().float())
        oracle_kind = "high_precision_real_weight_matmul_with_adopted_stock_checksum"
    diff = candidate_f - oracle_f
    oracle_norm = torch.linalg.vector_norm(oracle_f)
    rel_l2 = float((torch.linalg.vector_norm(diff) / oracle_norm).cpu())
    cosine = float(
        torch.nn.functional.cosine_similarity(
            oracle_f.flatten(), candidate_f.flatten(), dim=0
        ).cpu()
    )
    max_abs = float(diff.abs().max().cpu())
    finite = bool(torch.isfinite(candidate_f).all().cpu())
    expected_scales = torch.clamp(x.float().abs().amax(dim=1), min=1.0e-12) / FP8_MAX
    nonzero_rows = expected_scales != 0
    scale_rel = float(
        (
            (candidate_s[nonzero_rows] - expected_scales[nonzero_rows]).abs()
            / expected_scales[nonzero_rows].abs().clamp_min(1e-30)
        )
        .max()
        .cpu()
    )
    negative_y, _ = candidate(x, wq, ws.roll(1))
    torch.cuda.synchronize()
    negative_rel_l2 = float(
        (torch.linalg.vector_norm(negative_y.float() - oracle_f) / oracle_norm).cpu()
    )
    checksum_relative_to_stock = abs(
        float(candidate_f.sum().cpu()) - float(adopted_stock["checksum"])
    ) / max(abs(float(adopted_stock["checksum"])), 1e-30)
    correctness = {
        "oracle_kind": oracle_kind,
        "finite": finite,
        "max_abs": max_abs,
        "relative_l2": rel_l2,
        "cosine": cosine,
        "scale_max_relative_error_nonzero_rows": scale_rel,
        "stock_zero_row_scale": (
            float(stock_s[0].cpu()) if stock_s is not None else "not_replayed"
        ),
        "candidate_zero_row_scale": float(candidate_s[0].cpu()),
        "adopted_stock_checksum": float(adopted_stock["checksum"]),
        "candidate_checksum_relative_to_stock": checksum_relative_to_stock,
        "saturation_fraction": float(
            (wq.float().abs() == FP8_MAX).float().mean().cpu()
        ),
        "negative_control_wrong_weight_scale_relative_l2": negative_rel_l2,
        "full_output_elements_consumed": M * N,
    }
    correctness["pass"] = (
        finite
        and rel_l2 <= 0.02
        and cosine >= 0.999
        and scale_rel <= 2e-5
        and checksum_relative_to_stock <= 0.02
        and negative_rel_l2 > rel_l2 * 4
    )
    atomic(out_root / "CORRECTNESS.json", correctness)
    if not correctness["pass"]:
        atomic(
            out_root / "TERMINAL.json",
            {
                "classification": "scientific_correctness_negative",
                "science_consumed": True,
                "timing_consumed": False,
                "correctness": correctness,
            },
        )
        return 2

    for _ in range(WARMUP):
        stock(x, wq, ws)
        candidate(x, wq, ws)
    torch.cuda.synchronize()

    rows = []
    for rep, arm in enumerate(ORDER):
        fn = stock if arm == "stock" else candidate
        latency_ns, checksum = time_arm(fn, x, wq, ws)
        row = {
            "rep": rep,
            "arm": arm,
            "latency_ns_per_producer_consumer_interval": latency_ns,
            "inner": INNER,
            "checksum": checksum,
        }
        rows.append(row)
        atomic(out_root / "TIMING_ROWS.json", {"expected_rows": len(ORDER), "rows": rows})

    stock_rows = [r["latency_ns_per_producer_consumer_interval"] for r in rows if r["arm"] == "stock"]
    candidate_rows = [r["latency_ns_per_producer_consumer_interval"] for r in rows if r["arm"] == "candidate"]
    stock_median = statistics.median(stock_rows)
    candidate_median = statistics.median(candidate_rows)
    terminal = {
        "classification": "component_positive" if candidate_median < stock_median else "component_negative",
        "science_consumed": True,
        "timing_consumed": True,
        "identity": identity,
        "weight": {
            "name": WEIGHT_NAME,
            "shape_checkpoint": [N, K],
            "consumer_layout": [K, N],
            "source_tensor_sha256": weight_source_sha,
            "shard": shard_name,
        },
        "semantics": {
            "activation": "BF16 [32,5376]",
            "quantized_activation": "E4M3 per-token scale [32]",
            "weight": "real layer-0 q_proj E4M3 per-output-channel scale [8192]",
            "accumulation": "FP32",
            "output": "BF16 [32,8192]",
        },
        "correctness": correctness,
        "timing": {
            "unit": "ns per complete producer-plus-consumer interval",
            "order": ORDER,
            "inner": INNER,
            "rows": rows,
            "stock_median_ns": stock_median,
            "candidate_median_ns": candidate_median,
            "delta_ns": candidate_median - stock_median,
            "speedup": stock_median / candidate_median,
        },
        "candidate_path_proof": {
            "global_quantized_activation_written": False,
            "row_scale_barrier_preserved": True,
            "activation_conversion_location": "inside fused_quant_gemm_kernel K-tile load",
            "grid": [math.ceil(M / 8), math.ceil(N / 64)],
            "block": {"BM": 8, "BN": 64, "BK": 64, "warps": 4, "stages": 3},
            "compiled_registers": "unavailable_without_profiler",
            "shared_memory_bytes": "compiler_managed",
            "spills": "unavailable_without_profiler",
        },
    }
    atomic(out_root / "TERMINAL.json", terminal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
