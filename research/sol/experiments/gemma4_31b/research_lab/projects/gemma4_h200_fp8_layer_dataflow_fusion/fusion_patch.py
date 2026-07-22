from __future__ import annotations

import dataclasses
import json
import os
import pathlib


@dataclasses.dataclass(frozen=True)
class PrequantizedActivation:
    quantized: object
    scales: object
    output_dtype: object


def _append(path: str, row: dict[str, object]) -> None:
    destination = pathlib.Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def install() -> None:
    import torch

    from fused_gelu_quant import fused_gelu_tanh_mul_quant
    from sglang.srt.layers.quantization.fp8 import Fp8LinearMethod
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm
    from sglang.srt.models.gemma3_causal import Gemma3MLP

    if getattr(Gemma3MLP, "_fp8_gelu_fusion_installed", False):
        return

    original_mlp_forward = Gemma3MLP.forward
    original_fp8_apply = Fp8LinearMethod.apply
    audited_prefixes: set[str] = set()

    def fp8_apply(self, layer, x, bias=None):
        if not isinstance(x, PrequantizedActivation):
            return original_fp8_apply(self, layer, x, bias)
        if self.block_quant or self.use_marlin or self.use_mxfp8:
            raise RuntimeError("prequantized activation reached an incompatible FP8 method")
        if not self.cutlass_fp8_supported:
            raise RuntimeError("prequantized activation requires the bound CUTLASS FP8 path")
        if layer.weight_scale.numel() != layer.weight.shape[1]:
            raise RuntimeError("prequantized activation requires per-channel weight scales")
        output = fp8_scaled_mm(
            x.quantized,
            layer.weight,
            x.scales,
            layer.weight_scale,
            out_dtype=x.output_dtype,
            bias=bias,
        )
        return output

    def mlp_forward(self, x):
        gate_up, _ = self.gate_up_proj(x)
        method = getattr(self.down_proj, "quant_method", None)
        exact = (
            gate_up.is_cuda
            and gate_up.dtype is torch.bfloat16
            and gate_up.dim() == 2
            and gate_up.shape[-1] == 43008
            and isinstance(method, Fp8LinearMethod)
            and method.cutlass_fp8_supported
            and not method.block_quant
            and not method.use_marlin
            and not method.use_mxfp8
        )
        if not exact:
            return original_mlp_forward(self, x)
        quantized, scales = fused_gelu_tanh_mul_quant(gate_up.contiguous())
        output, _ = self.down_proj(
            PrequantizedActivation(quantized, scales, gate_up.dtype)
        )
        audit = os.environ.get("FUSION_AUDIT")
        prefix = getattr(self, "prefix", "<unbound>")
        if audit and prefix not in audited_prefixes:
            _append(
                audit,
                {
                    "candidate_symbol": "fused_gelu_tanh_mul_quant_kernel",
                    "prefix": prefix,
                    "gate_up_shape": list(gate_up.shape),
                    "quantized_shape": list(quantized.shape),
                    "scale_shape": list(scales.shape),
                    "input_dtype": str(gate_up.dtype),
                    "quantized_dtype": str(quantized.dtype),
                    "removed_intermediate_dtype": "torch.bfloat16",
                },
            )
            audited_prefixes.add(prefix)
        return output

    Fp8LinearMethod.apply = fp8_apply
    Gemma3MLP.forward = mlp_forward
    Gemma3MLP._fp8_gelu_fusion_installed = True
