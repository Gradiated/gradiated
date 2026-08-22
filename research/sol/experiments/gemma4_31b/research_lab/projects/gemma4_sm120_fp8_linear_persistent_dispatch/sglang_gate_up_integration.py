from __future__ import annotations

from pathlib import Path
from typing import Optional

import torch
from torch.utils.cpp_extension import load


M = 32
K = 5376
N = 43008
SOURCE = Path(__file__).with_name("sm120_pre_ff_gate_up_dispatch.cu")


def load_sm120_dispatch(build_directory: Path) -> None:
    build_directory.mkdir(parents=True, exist_ok=True)
    load(
        name="sm120_fp8_linear_persistent_dispatch",
        sources=[str(SOURCE)],
        build_directory=str(build_directory),
        extra_cuda_cflags=[
            "-O3",
            "--expt-relaxed-constexpr",
            "-gencode=arch=compute_120a,code=sm_120a",
        ],
        extra_cflags=["-O3"],
        with_cuda=True,
        is_python_module=False,
        verbose=True,
    )


def can_dispatch(layer, x: torch.Tensor, residual: torch.Tensor) -> bool:
    weight = getattr(layer, "weight", None)
    weight_scale = getattr(layer, "weight_scale", None)
    return (
        x.is_cuda
        and torch.cuda.get_device_capability(x.device) == (12, 0)
        and x.dtype == torch.bfloat16
        and residual.dtype == torch.bfloat16
        and tuple(x.shape) == (M, K)
        and tuple(residual.shape) == (M, K)
        and weight is not None
        and weight.dtype == torch.float8_e4m3fn
        and tuple(weight.shape) == (K, N)
        and tuple(weight.stride()) == (1, K)
        and weight_scale is not None
        and weight_scale.dtype == torch.float32
        and weight_scale.numel() == N
        and layer.bias is None
    )


def dispatch_pre_ff_gate_up(
    input_tensor: torch.Tensor,
    residual: torch.Tensor,
    norm,
    gate_up_layer,
    normalized_debug: Optional[torch.Tensor] = None,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    if not can_dispatch(gate_up_layer, input_tensor, residual):
        raise ValueError("sm120_pre_ff_gate_up_m32_contract_mismatch")
    return torch.ops.sm120_fp8_linear_persistent_dispatch.gate_up_m32(
        input_tensor,
        residual,
        norm.weight,
        gate_up_layer.weight,
        gate_up_layer.weight_scale,
        norm.variance_epsilon,
        normalized_debug,
    )


def gemma4_dense_mlp_integration(
    decoder_layer,
    hidden_states: torch.Tensor,
    residual: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    gate_up_layer = decoder_layer.mlp.gate_up_proj
    if can_dispatch(gate_up_layer, hidden_states, residual):
        gate_up, _, _ = dispatch_pre_ff_gate_up(
            hidden_states,
            residual,
            decoder_layer.pre_feedforward_layernorm,
            gate_up_layer,
        )
        activated = decoder_layer.mlp.act_fn(gate_up)
        output, _ = decoder_layer.mlp.down_proj(activated)
        return output, residual

    normalized, residual = decoder_layer.pre_feedforward_layernorm(
        hidden_states, residual
    )
    return decoder_layer.mlp(normalized), residual
