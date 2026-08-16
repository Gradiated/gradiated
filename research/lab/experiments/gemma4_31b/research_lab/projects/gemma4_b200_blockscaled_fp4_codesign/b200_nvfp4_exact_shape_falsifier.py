#!/usr/bin/env python3
"""Reopen-only exact-shape B200 NVFP4-vs-FP8 MLP discriminator.

Run exactly once on an admitted SM100 bench.  The script uses vLLM's current
public custom-op ABI for both arms, times complete gate/up -> SiLU*up -> down
chains at M32 and M384, and emits one compact JSON result.

This is a physical kernel falsifier.  Random tensors cannot establish model
quality or endpoint economics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
from statistics import median
from typing import Callable

import torch

from vllm import _custom_ops as ops


HIDDEN = 5376
INTERMEDIATE = 21504
GATE_UP = 2 * INTERMEDIATE
FLOAT4_MAX = 6.0
FLOAT8_MAX = float(torch.finfo(torch.float8_e4m3fn).max)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def global_fp4_scale(x: torch.Tensor) -> torch.Tensor:
    return ((FLOAT8_MAX * FLOAT4_MAX) / x.abs().max()).to(torch.float32)


def timed_ms(fn: Callable[[], torch.Tensor], warmup: int, repeats: int) -> list[float]:
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    samples: list[float] = []
    for _ in range(repeats):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        output = fn()
        end.record()
        end.synchronize()
        if not torch.isfinite(output).all():
            raise RuntimeError("non-finite timed output")
        samples.append(float(start.elapsed_time(end)))
    return samples


def numeric_metrics(actual: torch.Tensor, reference: torch.Tensor) -> dict[str, float]:
    a = actual.float().flatten()
    b = reference.float().flatten()
    cosine = float(torch.nn.functional.cosine_similarity(a, b, dim=0))
    rmse = float(torch.sqrt(torch.mean((a - b) ** 2)))
    reference_rms = float(torch.sqrt(torch.mean(b**2)))
    return {
        "cosine": cosine,
        "rmse": rmse,
        "reference_rms": reference_rms,
        "normalized_rmse": rmse / max(reference_rms, 1e-12),
        "finite": bool(torch.isfinite(a).all()),
    }


@torch.inference_mode()
def run_shape(
    m: int,
    gate_weight: torch.Tensor,
    down_weight: torch.Tensor,
    warmup: int,
    repeats: int,
) -> dict:
    device = gate_weight.device
    dtype = gate_weight.dtype
    x = torch.randn((m, HIDDEN), device=device, dtype=dtype) * 0.02

    # The BF16 oracle and static global input scales are intentionally outside
    # the timed regions. Current ModelOpt checkpoints store those global
    # scales; only the group-of-16 scales are generated at runtime.
    reference_gate = x @ gate_weight.t()
    reference_gated = torch.nn.functional.silu(
        reference_gate[:, :INTERMEDIATE]
    ) * reference_gate[:, INTERMEDIATE:]
    reference = reference_gated @ down_weight.t()

    gate_fp4_global = global_fp4_scale(gate_weight)
    down_fp4_global = global_fp4_scale(down_weight)
    x_fp4_global = global_fp4_scale(x)
    gated_fp4_global = global_fp4_scale(reference_gated)
    gate_fp4, gate_fp4_sf = ops.scaled_fp4_quant(
        gate_weight, gate_fp4_global, backend="cutlass"
    )
    down_fp4, down_fp4_sf = ops.scaled_fp4_quant(
        down_weight, down_fp4_global, backend="cutlass"
    )
    gate_alpha = 1.0 / (x_fp4_global * gate_fp4_global)
    down_alpha = 1.0 / (gated_fp4_global * down_fp4_global)
    gated_fp4_buffer, gated_fp4_sf_buffer = ops.scaled_fp4_quant(
        reference_gated, gated_fp4_global, backend="cutlass"
    )

    # Static FP8 weights and activations. CUTLASS FP8
    # consumes B as KxN, unlike the packed NVFP4 Nx(K/2) ABI.
    gate_fp8, gate_fp8_scale = ops.scaled_fp8_quant(gate_weight.t().contiguous())
    down_fp8, down_fp8_scale = ops.scaled_fp8_quant(down_weight.t().contiguous())
    _, x_fp8_scale = ops.scaled_fp8_quant(x)
    x_fp8_setup, _ = ops.scaled_fp8_quant(x, x_fp8_scale)
    gate_fp8_setup = ops.cutlass_scaled_mm(
        x_fp8_setup, gate_fp8, x_fp8_scale, gate_fp8_scale, out_dtype=dtype
    )
    gated_fp8_setup = torch.nn.functional.silu(
        gate_fp8_setup[:, :INTERMEDIATE]
    ) * gate_fp8_setup[:, INTERMEDIATE:]
    gated_fp8_buffer, gated_fp8_scale = ops.scaled_fp8_quant(gated_fp8_setup)

    def nvfp4_chain() -> torch.Tensor:
        xq, xsf = ops.scaled_fp4_quant(x, x_fp4_global, backend="cutlass")
        gate = ops.cutlass_scaled_fp4_mm(
            xq, gate_fp4, xsf, gate_fp4_sf, gate_alpha, dtype
        )
        torch.ops._C.silu_and_mul_nvfp4_quant(
            gated_fp4_buffer,
            gated_fp4_sf_buffer,
            gate,
            gated_fp4_global,
        )
        return ops.cutlass_scaled_fp4_mm(
            gated_fp4_buffer,
            down_fp4,
            gated_fp4_sf_buffer,
            down_fp4_sf,
            down_alpha,
            dtype,
        )

    def fp8_chain() -> torch.Tensor:
        xq, xs = ops.scaled_fp8_quant(x, x_fp8_scale)
        gate = ops.cutlass_scaled_mm(
            xq, gate_fp8, xs, gate_fp8_scale, out_dtype=dtype
        )
        torch.ops._C.silu_and_mul_quant(gated_fp8_buffer, gate, gated_fp8_scale)
        return ops.cutlass_scaled_mm(
            gated_fp8_buffer,
            down_fp8,
            gated_fp8_scale,
            down_fp8_scale,
            out_dtype=dtype,
        )

    nvfp4_once = nvfp4_chain()
    fp8_once = fp8_chain()
    candidate_numeric = numeric_metrics(nvfp4_once, reference)
    baseline_numeric = numeric_metrics(fp8_once, reference)
    if (
        not candidate_numeric["finite"]
        or candidate_numeric["cosine"] < 0.98
        or candidate_numeric["normalized_rmse"] > 0.30
    ):
        raise RuntimeError(f"NVFP4 numeric guard failed at M={m}: {candidate_numeric}")

    nvfp4_ms = timed_ms(nvfp4_chain, warmup, repeats)
    fp8_ms = timed_ms(fp8_chain, warmup, repeats)
    return {
        "m": m,
        "gate_up_mnk": [m, GATE_UP, HIDDEN],
        "down_mnk": [m, HIDDEN, INTERMEDIATE],
        "nvfp4_full_mlp_ms": {
            "samples": nvfp4_ms,
            "median": median(nvfp4_ms),
            "minimum": min(nvfp4_ms),
            "maximum": max(nvfp4_ms),
        },
        "fp8_full_mlp_ms": {
            "samples": fp8_ms,
            "median": median(fp8_ms),
            "minimum": min(fp8_ms),
            "maximum": max(fp8_ms),
        },
        "nvfp4_over_fp8_median_ratio": median(nvfp4_ms) / median(fp8_ms),
        "numeric_vs_bf16": {
            "nvfp4": candidate_numeric,
            "fp8": baseline_numeric,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260726)
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    capability = torch.cuda.get_device_capability()
    if capability[0] != 10:
        raise RuntimeError(f"SM100 B200 required, got compute capability {capability}")
    if args.warmup < 1 or args.repeats < 5:
        raise ValueError("require at least one warmup and five measured repeats")

    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    device = torch.device("cuda:0")
    dtype = torch.bfloat16
    gate_weight = torch.randn(
        (GATE_UP, HIDDEN), device=device, dtype=dtype
    ) * 0.02
    down_weight = torch.randn(
        (HIDDEN, INTERMEDIATE), device=device, dtype=dtype
    ) * 0.02

    rows = [
        run_shape(m, gate_weight, down_weight, args.warmup, args.repeats)
        for m in (32, 384)
    ]
    result = {
        "schema_version": 1,
        "result_class": "measured_exact_shape_kernel_falsifier",
        "scientific_scope": (
            "Synthetic exact-shape physical NVFP4-vs-FP8 MLP discriminator; "
            "not endpoint or model-quality evidence"
        ),
        "candidate_science_started": True,
        "rows": rows,
        "guard": {
            "pass": all(
                row["numeric_vs_bf16"]["nvfp4"]["finite"]
                and row["numeric_vs_bf16"]["nvfp4"]["cosine"] >= 0.98
                and row["numeric_vs_bf16"]["nvfp4"]["normalized_rmse"] <= 0.30
                for row in rows
            ),
            "reopen_physical_gate": all(
                row["nvfp4_over_fp8_median_ratio"] <= 0.70 for row in rows
            ),
            "note": (
                "Passing the physical gate does not reopen the project without "
                "quality-backed attention coverage."
            ),
        },
        "environment": {
            "device": torch.cuda.get_device_name(0),
            "compute_capability": list(capability),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "python": platform.python_version(),
            "vllm_revision_required": "d30b1ecd1bdf7c3d92f3b444c4538efd8fbb40ac",
        },
        "runner_sha256": file_sha256(Path(__file__).resolve()),
        "seed": args.seed,
        "warmup": args.warmup,
        "repeats": args.repeats,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "pass": result["guard"]["pass"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
