from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import types


INTERMEDIATE = 21504
GATE_UP = 2 * INTERMEDIATE
MAXIMUM_FUSED_ROWS = 32


@dataclasses.dataclass(frozen=True)
class PrequantizedGatedActivation:
    quantized: object
    scales: object
    output_dtype: object


def should_fuse(shape: tuple[int, ...], dtype_name: str, tp_size: int) -> bool:
    return (
        len(shape) == 2
        and 1 <= shape[0] <= MAXIMUM_FUSED_ROWS
        and shape[1] == GATE_UP
        and dtype_name == "torch.bfloat16"
        and tp_size == 1
    )


def _append_audit(row: dict[str, object]) -> None:
    raw_path = os.environ.get("GATED_ACTIVATION_FP8_AUDIT")
    if not raw_path:
        return
    destination = pathlib.Path(raw_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def install() -> None:
    if os.environ.get("GATED_ACTIVATION_FP8_ARM") != "candidate":
        return

    from gated_activation_fp8_decode import (
        gemma4_gated_activation_quant_e4m3,
        prepare,
    )
    from sglang.srt.layers.quantization.fp8 import Fp8LinearMethod
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm
    from sglang.srt.models.gemma4_causal import Gemma4DecoderLayer

    if getattr(Gemma4DecoderLayer, "_gated_activation_fp8_installed", False):
        return

    prepare()
    original_decoder_init = Gemma4DecoderLayer.__init__
    original_fp8_apply = Fp8LinearMethod.apply
    audited_prefixes: set[str] = set()

    def prequantized_apply(self, layer, activation, bias=None):
        if not isinstance(activation, PrequantizedGatedActivation):
            return original_fp8_apply(self, layer, activation, bias)
        if self.block_quant or self.use_marlin or self.use_mxfp8:
            raise RuntimeError(
                "gated-activation FP8 reached an incompatible FP8 method"
            )
        if not self.cutlass_fp8_supported:
            raise RuntimeError("gated-activation FP8 requires CUTLASS FP8")
        if layer.weight.shape != (INTERMEDIATE, 5376):
            raise RuntimeError(
                f"unexpected down-projection weight shape {layer.weight.shape}"
            )
        if layer.weight_scale.numel() != layer.weight.shape[1]:
            raise RuntimeError(
                "gated-activation FP8 requires per-output-channel scales"
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
                        "gemma4_gated_activation_quant_e4m3_kernel"
                    ),
                    "consumer_symbol": "fp8_scaled_mm",
                    "prefix": prefix,
                    "quantized_shape": list(activation.quantized.shape),
                    "quantized_stride": list(activation.quantized.stride()),
                    "quantized_dtype": str(activation.quantized.dtype),
                    "scale_shape": list(activation.scales.shape),
                    "scale_stride": list(activation.scales.stride()),
                    "scale_dtype": str(activation.scales.dtype),
                    "weight_shape": list(layer.weight.shape),
                    "weight_stride": list(layer.weight.stride()),
                    "output_dtype": str(activation.output_dtype),
                }
            )
            audited_prefixes.add(prefix)
        return output

    def bind_mlp(mlp) -> None:
        original_forward = mlp.forward

        def forward(_self, x):
            gate_up, _ = _self.gate_up_proj(x)
            shape = tuple(gate_up.shape)
            tp_size = getattr(_self.down_proj, "tp_size", 1)
            if not gate_up.is_cuda or not should_fuse(
                shape, str(gate_up.dtype), tp_size
            ):
                activated = _self.act_fn(gate_up)
                output, _ = _self.down_proj(activated)
                return output
            quantized, scales = gemma4_gated_activation_quant_e4m3(
                gate_up.contiguous()
            )
            activation = PrequantizedGatedActivation(
                quantized, scales, gate_up.dtype
            )
            output, _ = _self.down_proj(activation)
            return output

        mlp.forward = types.MethodType(forward, mlp)
        mlp._gated_activation_fp8_original_forward = original_forward

    def decoder_init(self, *args, **kwargs):
        original_decoder_init(self, *args, **kwargs)
        bind_mlp(self.mlp)

    Fp8LinearMethod.apply = prequantized_apply
    Gemma4DecoderLayer.__init__ = decoder_init
    Gemma4DecoderLayer._gated_activation_fp8_installed = True
