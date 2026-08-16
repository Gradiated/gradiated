from __future__ import annotations

import hashlib
import json
import os
import pathlib

import torch
import triton
import triton.language as tl


FP8_UTILS_SHA256 = "a3a130f40974047084e3daff2bd0efbbfe69e197d4c9a5ba3fbc5304dd4e43d9"
GATE_UP_K = 5376
GATE_UP_N = 43008


@triton.jit
def _gate_up_fp8_64x256_kernel(
    a,
    b,
    scale_a,
    scale_b,
    output,
    m,
    stride_am: tl.constexpr,
    stride_ak: tl.constexpr,
    stride_bk: tl.constexpr,
    stride_bn: tl.constexpr,
    stride_om: tl.constexpr,
    stride_on: tl.constexpr,
    GATE_K: tl.constexpr,
    BLOCK_M: tl.constexpr,
    BLOCK_N: tl.constexpr,
    BLOCK_K: tl.constexpr,
):
    pid_m = tl.program_id(0)
    pid_n = tl.program_id(1)
    offs_m = pid_m * BLOCK_M + tl.arange(0, BLOCK_M)
    offs_n = pid_n * BLOCK_N + tl.arange(0, BLOCK_N)
    offs_k = tl.arange(0, BLOCK_K)
    accumulator = tl.zeros((BLOCK_M, BLOCK_N), dtype=tl.float32)
    for k_base in range(0, GATE_K, BLOCK_K):
        k = k_base + offs_k
        a_tile = tl.load(
            a + offs_m[:, None] * stride_am + k[None, :] * stride_ak,
            mask=offs_m[:, None] < m,
            other=0.0,
        )
        b_tile = tl.load(
            b + k[:, None] * stride_bk + offs_n[None, :] * stride_bn
        )
        accumulator += tl.dot(a_tile, b_tile)
    row_scale = tl.load(scale_a + offs_m, mask=offs_m < m, other=0.0)
    column_scale = tl.load(scale_b + offs_n)
    result = accumulator * row_scale[:, None] * column_scale[None, :]
    tl.store(
        output + offs_m[:, None] * stride_om + offs_n[None, :] * stride_on,
        result,
        mask=offs_m[:, None] < m,
    )


def _append_audit(row: dict[str, object]) -> None:
    path = os.environ.get("RESIDUAL_CANDIDATE_AUDIT")
    if not path:
        return
    destination = pathlib.Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def install() -> None:
    from sglang.srt.layers.quantization import fp8_utils

    source = pathlib.Path(fp8_utils.__file__)
    observed = hashlib.sha256(source.read_bytes()).hexdigest()
    if observed != FP8_UTILS_SHA256:
        raise RuntimeError(f"pinned FP8 dispatch source mismatch:{observed}")
    stock = fp8_utils.fp8_scaled_mm
    audited_shapes: set[tuple[int, int, int]] = set()

    def exact_gate_up_scaled_mm(
        mat_a,
        mat_b,
        scales_a,
        scales_b,
        out_dtype,
        bias=None,
    ):
        m, k = mat_a.shape
        n = mat_b.shape[1]
        if (
            m > 128
            and k == GATE_UP_K
            and n == GATE_UP_N
            and out_dtype == torch.bfloat16
            and bias is None
        ):
            output = torch.empty((m, n), device=mat_a.device, dtype=out_dtype)
            _gate_up_fp8_64x256_kernel[
                (triton.cdiv(m, 64), triton.cdiv(n, 256))
            ](
                mat_a,
                mat_b,
                scales_a,
                scales_b,
                output,
                m,
                mat_a.stride(0),
                mat_a.stride(1),
                mat_b.stride(0),
                mat_b.stride(1),
                output.stride(0),
                output.stride(1),
                GATE_K=GATE_UP_K,
                BLOCK_M=64,
                BLOCK_N=256,
                BLOCK_K=128,
                num_warps=8,
                num_stages=4,
            )
            shape = (m, n, k)
            if shape not in audited_shapes:
                _append_audit(
                    {
                        "candidate_path": "fp8_gate_up_exact_shape_64x256x128",
                        "phase": "runtime_invocation",
                        "m": m,
                        "n": n,
                        "k": k,
                        "tile": [64, 256, 128],
                        "num_warps": 8,
                        "num_stages": 4,
                        "stock_fallback_for_other_shapes": True,
                    }
                )
                audited_shapes.add(shape)
            return output
        return stock(mat_a, mat_b, scales_a, scales_b, out_dtype, bias)

    fp8_utils.fp8_scaled_mm = exact_gate_up_scaled_mm
