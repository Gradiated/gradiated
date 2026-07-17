#!/usr/bin/env python3
"""Fail closed on CUDA/WNA16 selection before the full endpoint load."""
import copy
import json
import os
from pathlib import Path

import torch
from vllm.model_executor.layers.linear import LinearBase
from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead
from vllm.model_executor.layers.quantization.compressed_tensors.compressed_tensors import CompressedTensorsConfig

root = Path("/workspace/model-awq")
scope = os.environ.get("GLM_SELECTIVE_W4_SCOPE", "combined")
if scope not in {"combined", "head_only", "shared_only"}:
    raise RuntimeError(f"unsupported selective-W4 scope: {scope}")
config = json.loads((root / "config.json").read_text())["quantization_config"]
ct = CompressedTensorsConfig.from_config(copy.deepcopy(config))
head, shared = object.__new__(ParallelLMHead), object.__new__(LinearBase)
head_method = ct.get_quant_method(head, "lm_head")
shared_method = ct.get_quant_method(shared, "model.layers.1.mlp.shared_experts.gate_proj")
if not torch.cuda.is_available() or torch.cuda.get_device_capability()[0] < 8:
    raise RuntimeError("CUDA SM89-or-better WNA16 oracle unavailable")
head_selected = scope in {"combined", "head_only"}
shared_selected = scope in {"combined", "shared_only"}
head_pass = (
    type(head_method).__name__ == "CompressedTensorsLinearMethod"
    and type(getattr(head, "scheme", None)).__name__ == "CompressedTensorsWNA16"
) if head_selected else head_method is None
shared_pass = (
    type(shared_method).__name__ == "CompressedTensorsLinearMethod"
    and type(getattr(shared, "scheme", None)).__name__ == "CompressedTensorsWNA16"
) if shared_selected else shared_method is None
if not head_pass:
    raise RuntimeError(f"ParallelLMHead scope mismatch for {scope}")
if not shared_pass:
    raise RuntimeError(f"shared linear scope mismatch for {scope}")
print(json.dumps({"pass": True, "scope": scope, "cuda_capability": torch.cuda.get_device_capability(), "head_method": type(head_method).__name__, "head_scheme": type(getattr(head, "scheme", None)).__name__, "shared_method": type(shared_method).__name__, "shared_scheme": type(getattr(shared, "scheme", None)).__name__}, sort_keys=True))
