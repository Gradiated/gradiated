#!/usr/bin/env python3
from __future__ import annotations

import os
import runpy

from sglang.srt.configs.model_config import ModelConfig


_upstream_is_already_quantized = ModelConfig._is_already_quantized


def _local_aware_is_already_quantized(self: ModelConfig) -> bool:
    if not os.path.isdir(self.model_path):
        return _upstream_is_already_quantized(self)
    if getattr(self.hf_config, "quantization_config", None) or getattr(
        self.hf_config, "compression_config", None
    ):
        return True
    return os.path.isfile(os.path.join(self.model_path, "hf_quant_config.json"))


ModelConfig._is_already_quantized = _local_aware_is_already_quantized
runpy.run_path(
    "/sgl-workspace/sglang/examples/usage/modelopt_quantize_and_export.py",
    run_name="__main__",
)
