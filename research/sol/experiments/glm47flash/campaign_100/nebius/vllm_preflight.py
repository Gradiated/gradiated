#!/usr/bin/env python3
"""Fail-closed CUDA and checkpoint-config preflight for the derived vLLM image."""

import importlib
import json

import torch
import transformers
import vllm
from transformers import AutoConfig


if transformers.__version__ != "5.3.0.dev0":
    raise SystemExit(f"unexpected transformers version: {transformers.__version__}")
glm4_moe_lite = importlib.import_module("vllm.model_executor.models.glm4_moe_lite")
config = AutoConfig.from_pretrained("/input/model-config-only", local_files_only=True)
if config.model_type != "glm4_moe_lite":
    raise SystemExit(f"unexpected model_type: {config.model_type}")
tensor = torch.ones(1, device="cuda")
print(json.dumps({
    "torch": torch.__version__,
    "cuda": torch.version.cuda,
    "transformers": transformers.__version__,
    "vllm": vllm.__version__,
    "vllm_glm_module": glm4_moe_lite.__name__,
    "model_type": config.model_type,
    "gpu": torch.cuda.get_device_name(),
    "capability": torch.cuda.get_device_capability(),
    "tensor": tensor.item(),
}, indent=2, sort_keys=True))
