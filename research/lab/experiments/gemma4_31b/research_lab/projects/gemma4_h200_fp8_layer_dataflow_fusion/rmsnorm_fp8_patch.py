from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import types


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
    if os.environ.get("RMS_FP8_ARM") != "candidate":
        return

    import torch

    from fused_rmsnorm_quant import fused_add_rmsnorm_quant, rmsnorm_quant
    from sglang.srt.layers.quantization.fp8 import Fp8LinearMethod
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm
    from sglang.srt.models.gemma4_causal import Gemma4DecoderLayer

    if getattr(Gemma4DecoderLayer, "_rms_fp8_fusion_installed", False):
        return

    original_init = Gemma4DecoderLayer.__init__
    original_fp8_apply = Fp8LinearMethod.apply
    audited_prefixes: set[str] = set()

    def prequantized_apply(self, layer, x, bias=None):
        if not isinstance(x, PrequantizedActivation):
            return original_fp8_apply(self, layer, x, bias)
        if self.block_quant or self.use_marlin or self.use_mxfp8:
            raise RuntimeError("RMSNorm prequantized activation reached incompatible FP8 method")
        if not self.cutlass_fp8_supported:
            raise RuntimeError("RMSNorm prequantized activation requires CUTLASS FP8")
        if layer.weight_scale.numel() != layer.weight.shape[1]:
            raise RuntimeError("RMSNorm prequantized activation requires per-channel weights")
        output = fp8_scaled_mm(
            x.quantized,
            layer.weight,
            x.scales,
            layer.weight_scale,
            out_dtype=x.output_dtype,
            bias=bias,
        )
        audit = os.environ.get("RMS_FP8_AUDIT")
        prefix = getattr(layer, "prefix", "<unbound>")
        if audit and prefix not in audited_prefixes:
            _append(
                audit,
                {
                    "candidate_symbol": "rmsnorm_quant_kernel",
                    "consumer_symbol": "fp8_scaled_mm",
                    "prefix": prefix,
                    "quantized_dtype": str(x.quantized.dtype),
                    "quantized_shape": list(x.quantized.shape),
                    "scale_dtype": str(x.scales.dtype),
                    "scale_shape": list(x.scales.shape),
                    "output_dtype": str(x.output_dtype),
                },
            )
            audited_prefixes.add(prefix)
        return output

    def bind_plain(norm):
        def forward(_self, x, residual=None, post_residual_addition=None):
            if residual is not None or post_residual_addition is not None:
                raise RuntimeError("plain RMSNorm-to-FP8 received a residual")
            if (
                not x.is_cuda
                or x.dtype is not torch.bfloat16
                or x.dim() != 2
                or x.shape[-1] != 5376
            ):
                raise RuntimeError(f"plain RMSNorm-to-FP8 shape contract failed:{x.shape}:{x.dtype}")
            quantized, scales = rmsnorm_quant(
                x.contiguous(), _self.weight.data, _self.variance_epsilon
            )
            return PrequantizedActivation(quantized, scales, x.dtype)

        norm.forward = types.MethodType(forward, norm)

    def bind_residual(norm):
        def forward(_self, x, residual=None, post_residual_addition=None):
            if residual is None or post_residual_addition is not None:
                raise RuntimeError("residual RMSNorm-to-FP8 contract failed")
            if (
                not x.is_cuda
                or x.dtype is not torch.bfloat16
                or x.dim() != 2
                or x.shape[-1] != 5376
                or not residual.is_contiguous()
            ):
                raise RuntimeError(f"residual RMSNorm-to-FP8 shape contract failed:{x.shape}:{x.dtype}")
            quantized, scales, residual_out = fused_add_rmsnorm_quant(
                x.contiguous(),
                residual,
                _self.weight.data,
                _self.variance_epsilon,
            )
            return PrequantizedActivation(quantized, scales, x.dtype), residual_out

        norm.forward = types.MethodType(forward, norm)

    def decoder_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if self.enable_moe_block or self.has_ple:
            raise RuntimeError("RMSNorm-to-FP8 candidate excludes MoE and PLE")
        bind_plain(self.input_layernorm)
        bind_residual(self.pre_feedforward_layernorm)

    Fp8LinearMethod.apply = prequantized_apply
    Gemma4DecoderLayer.__init__ = decoder_init
    Gemma4DecoderLayer._rms_fp8_fusion_installed = True
