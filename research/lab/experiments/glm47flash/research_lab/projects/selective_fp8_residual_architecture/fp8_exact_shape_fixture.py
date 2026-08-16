#!/usr/bin/env python3
"""CPU-safe storage/shape fixture plus pinned vLLM Ada capability probe."""
import json
import argparse
import torch
from vllm import _custom_ops as ops
from vllm.model_executor.layers.quantization.fp8 import Fp8Config

SHAPES = {
    "lm_head_c16": (16, 2048, 154880),
    "dense_layer_0_mlp": (16, 2048, 10240),
    "shared_expert_gate_up": (16, 2048, 1536),
    "shared_expert_down": (16, 1536, 2048),
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    storage = {}
    for name, (m, k, n) in SHAPES.items():
        # Synthetic values are only a layout fixture, never model-quality evidence.
        weight = torch.zeros((n, k), dtype=torch.bfloat16)
        fp8 = weight.to(torch.float8_e4m3fn)
        storage[name] = {"shape": list(fp8.shape), "bytes": fp8.numel(), "dtype": str(fp8.dtype), "m": m, "k": k, "n": n}
    # This is the compiled path's capability predicate, not a GPU timing claim.
    capability = {str(cc): bool(ops.cutlass_scaled_mm_supports_fp8(cc)) for cc in (80, 86, 89, 90)}
    config = Fp8Config(is_checkpoint_fp8_serialized=True, activation_scheme="dynamic")
    result = {
        "evidence_label": "measured pinned-container torch storage fixture and vLLM capability predicate; no GPU execution",
        "torch": torch.__version__,
        "fp8_dtype": str(torch.float8_e4m3fn),
        "shapes": storage,
        "cutlass_fp8_support_by_compute_capability": capability,
        "ada_sm89_supported": capability["89"],
        "vllm_fp8_config": {"class": type(config).__name__, "min_capability": config.get_min_capability(), "activation_scheme": config.activation_scheme},
        "limitation": "The fixture validates one-byte E4M3 storage and the pinned Ada dispatch predicate. It does not execute scaled GEMM because this container has no GPU.",
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        with open(args.output, "w") as stream:
            stream.write(rendered)
    print(rendered, end="")

if __name__ == "__main__":
    main()
