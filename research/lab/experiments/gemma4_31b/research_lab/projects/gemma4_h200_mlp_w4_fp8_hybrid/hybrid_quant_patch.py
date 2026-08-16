from __future__ import annotations

import json
import os
import pathlib


def append(path: str, row: object) -> None:
    destination = pathlib.Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def install() -> None:
    from sglang.srt.layers.quantization.awq.awq import (
        AWQLinearMethod,
        AWQMarlinConfig,
    )
    from sglang.srt.layers.quantization.fp8 import Fp8Config, Fp8LinearMethod

    if getattr(AWQMarlinConfig, "_gemma4_hybrid_installed", False):
        return
    original_get = AWQMarlinConfig.get_quant_method
    original_awq_process = AWQLinearMethod.process_weights_after_loading
    original_fp8_process = Fp8LinearMethod.process_weights_after_loading
    fp8_config = Fp8Config(
        is_checkpoint_fp8_serialized=False,
        activation_scheme="dynamic",
        ignored_layers=["model.vision_tower", "model.embed_vision"],
    )
    audit = os.environ["HYBRID_QUANT_AUDIT"]

    def hybrid_get(self, layer, prefix):
        if ".mlp.gate_up_proj" in prefix or ".mlp.down_proj" in prefix:
            method = original_get(self, layer, prefix)
            if isinstance(method, AWQLinearMethod):
                method._hybrid_prefix = prefix
            return method
        method = fp8_config.get_quant_method(layer, prefix)
        if isinstance(method, Fp8LinearMethod):
            method._hybrid_prefix = prefix
        return method if method is not None else original_get(self, layer, prefix)

    def awq_process(self, layer):
        original_awq_process(self, layer)
        append(
            audit,
            {
                "prefix": getattr(self, "_hybrid_prefix", None),
                "representation": "awq_marlin_w4a16",
                "consumer_symbol": (
                    "sglang.srt.hardware_backend.gpu.quantization."
                    "awq_kernels.AWQMarlinLinearKernel.apply"
                ),
                "qweight_shape": list(layer.qweight.shape),
                "qweight_dtype": str(layer.qweight.dtype),
                "scales_shape": list(layer.scales.shape),
                "qzeros_shape": list(layer.qzeros.shape),
            },
        )

    def fp8_process(self, layer):
        original_fp8_process(self, layer)
        append(
            audit,
            {
                "prefix": getattr(self, "_hybrid_prefix", None),
                "representation": "dynamic_fp8",
                "consumer_symbol": (
                    "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm"
                ),
                "weight_shape": list(layer.weight.shape),
                "weight_dtype": str(layer.weight.dtype),
                "scale_shape": list(layer.weight_scale.shape),
            },
        )

    AWQMarlinConfig.get_quant_method = hybrid_get
    AWQLinearMethod.process_weights_after_loading = awq_process
    Fp8LinearMethod.process_weights_after_loading = fp8_process
    AWQMarlinConfig._gemma4_hybrid_installed = True
