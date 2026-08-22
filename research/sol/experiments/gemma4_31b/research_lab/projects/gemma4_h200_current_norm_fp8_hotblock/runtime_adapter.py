from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import types


HIDDEN = 5376
MAXIMUM_FUSED_ROWS = 32


@dataclasses.dataclass(frozen=True)
class PrequantizedActivation:
    quantized: object
    scales: object
    output_dtype: object


def _append_audit(row: dict[str, object]) -> None:
    raw_path = os.environ.get("NORM_FP8_AUDIT")
    if not raw_path:
        return
    destination = pathlib.Path(raw_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def should_fuse(shape: tuple[int, ...], dtype_name: str) -> bool:
    return (
        len(shape) == 2
        and 1 <= shape[0] <= MAXIMUM_FUSED_ROWS
        and shape[1] == HIDDEN
        and dtype_name == "torch.bfloat16"
    )


def install() -> None:
    if os.environ.get("NORM_FP8_ARM") != "candidate":
        return

    import torch

    from norm_fp8_decode_exact_order import (
        gemma4_decode_norm_fp8_exact_order,
        prepare,
    )
    from sglang.srt.layers.quantization.fp8 import Fp8LinearMethod
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm
    from sglang.srt.models.gemma4_causal import Gemma4DecoderLayer

    if getattr(Gemma4DecoderLayer, "_decode_norm_fp8_installed", False):
        return

    prepare()
    original_decoder_init = Gemma4DecoderLayer.__init__
    original_fp8_apply = Fp8LinearMethod.apply
    audited_prefixes: set[str] = set()

    def prequantized_apply(self, layer, activation, bias=None):
        if not isinstance(activation, PrequantizedActivation):
            return original_fp8_apply(self, layer, activation, bias)
        if self.block_quant or self.use_marlin or self.use_mxfp8:
            raise RuntimeError(
                "decode norm/FP8 activation reached an incompatible FP8 method"
            )
        if not self.cutlass_fp8_supported:
            raise RuntimeError("decode norm/FP8 requires CUTLASS FP8")
        if layer.weight_scale.numel() != layer.weight.shape[1]:
            raise RuntimeError(
                "decode norm/FP8 requires per-output-channel weight scales"
            )
        output = fp8_scaled_mm(
            activation.quantized,
            layer.weight,
            activation.scales,
            layer.weight_scale,
            out_dtype=activation.output_dtype,
            bias=bias,
        )
        prefix = getattr(layer, "prefix", "<unbound>")
        if prefix not in audited_prefixes:
            _append_audit(
                {
                    "candidate_symbol": (
                        "gemma4_decode_rmsnorm_quant_e4m3_exact_order"
                    ),
                    "consumer_symbol": "fp8_scaled_mm",
                    "prefix": prefix,
                    "quantized_shape": list(activation.quantized.shape),
                    "quantized_stride": list(activation.quantized.stride()),
                    "quantized_dtype": str(activation.quantized.dtype),
                    "scale_shape": list(activation.scales.shape),
                    "scale_stride": list(activation.scales.stride()),
                    "scale_dtype": str(activation.scales.dtype),
                    "output_dtype": str(activation.output_dtype),
                }
            )
            audited_prefixes.add(prefix)
        return output

    def bind_decode_input_norm(norm) -> None:
        original_forward = norm.forward

        def forward(_self, x, residual=None, post_residual_addition=None):
            if residual is not None or post_residual_addition is not None:
                return original_forward(
                    x,
                    residual=residual,
                    post_residual_addition=post_residual_addition,
                )
            shape = tuple(x.shape)
            if not x.is_cuda or not should_fuse(shape, str(x.dtype)):
                return original_forward(x)
            quantized, scales = gemma4_decode_norm_fp8_exact_order(
                x.contiguous(), _self.weight.data, _self.variance_epsilon
            )
            return PrequantizedActivation(quantized, scales, x.dtype)

        norm.forward = types.MethodType(forward, norm)

    def decoder_init(self, *args, **kwargs):
        original_decoder_init(self, *args, **kwargs)
        bind_decode_input_norm(self.input_layernorm)

    Fp8LinearMethod.apply = prequantized_apply
    Gemma4DecoderLayer.__init__ = decoder_init
    Gemma4DecoderLayer._decode_norm_fp8_installed = True
