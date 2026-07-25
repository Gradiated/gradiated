#!/usr/bin/env python3
"""One-call M32 gate/up discriminator for a future corrected module.

This deliberately omits timing, M384, the activation, and the down projection.
It answers only whether one sm_90a-targeted candidate invocation commits the
same finite BF16 gate/up tensor as the pinned stock consumer.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import re
import subprocess


M = 32
HIDDEN = 5376
GATE_UP = 43008
EXPECTED_FP8_UTILS_SHA256 = (
    "a3a130f40974047084e3daff2bd0efbbfe69e197d4c9a5ba3fbc5304dd4e43d9"
)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def load_candidate(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("gemma4_fp8_weight_stream", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"candidate module cannot be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def module_arches(path: pathlib.Path) -> tuple[list[str], str]:
    completed = subprocess.run(
        ["cuobjdump", "--dump-resource-usage", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    output = completed.stdout + completed.stderr
    arches = sorted(set(re.findall(r"\barch\s*=\s*(sm_[0-9]+a?)\b", output)))
    return arches, hashlib.sha256(output.encode()).hexdigest()


def make_weight():
    import torch

    weight = torch.empty_strided(
        (HIDDEN, GATE_UP),
        (1, HIDDEN),
        dtype=torch.float8_e4m3fn,
        device="cuda",
    )
    weight.view(torch.uint8).random_(32, 57)
    scale = torch.linspace(1.0 / 512.0, 1.0 / 256.0, GATE_UP, device="cuda")
    return weight, scale


def comparison(reference, candidate) -> dict[str, object]:
    import torch

    reference_f = reference.float()
    candidate_f = candidate.float()
    delta = candidate_f - reference_f
    denominator = torch.linalg.vector_norm(reference_f)
    relative_l2 = (
        torch.linalg.vector_norm(delta) / denominator
        if float(denominator.item()) != 0.0
        else torch.linalg.vector_norm(delta)
    )
    return {
        "bitwise_equal": bool(torch.equal(reference, candidate)),
        "candidate_checksum": float(candidate_f.sum().item()),
        "candidate_nonfinite": int((~torch.isfinite(candidate_f)).sum().item()),
        "max_absolute_error": float(delta.abs().max().item()),
        "reference_checksum": float(reference_f.sum().item()),
        "reference_nonfinite": int((~torch.isfinite(reference_f)).sum().item()),
        "relative_l2": float(relative_l2.item()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", type=pathlib.Path, required=True)
    parser.add_argument("--expected-module-sha256", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--seed", type=int, default=20260757)
    args = parser.parse_args()

    import torch
    from sgl_kernel import fp8_scaled_mm
    from sglang.srt.layers.quantization import fp8_utils
    from sglang.srt.layers.quantization.fp8_kernel import (
        sglang_per_token_quant_fp8,
    )

    module_path = args.module.resolve()
    observed_module_sha256 = sha256(module_path)
    if observed_module_sha256 != args.expected_module_sha256:
        raise RuntimeError(
            f"module hash mismatch: observed {observed_module_sha256}"
        )
    if not torch.cuda.is_available():
        raise RuntimeError("discriminator requires CUDA")
    if torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("discriminator requires SM90")
    if "H200" not in torch.cuda.get_device_name().upper():
        raise RuntimeError("discriminator is bound to NVIDIA H200")
    observed_fp8_utils_sha256 = sha256(pathlib.Path(fp8_utils.__file__))
    if observed_fp8_utils_sha256 != EXPECTED_FP8_UTILS_SHA256:
        raise RuntimeError(
            f"pinned fp8_utils mismatch: {observed_fp8_utils_sha256}"
        )
    arches, resource_usage_sha256 = module_arches(module_path)
    if "sm_90a" not in arches:
        raise RuntimeError(f"corrected module lacks sm_90a code: {arches}")

    torch.manual_seed(args.seed)
    hidden = torch.randn(
        (M, HIDDEN), dtype=torch.bfloat16, device="cuda"
    ) / 8
    weight, weight_scale = make_weight()
    quantized_hidden, hidden_scale = sglang_per_token_quant_fp8(hidden)
    stock = fp8_scaled_mm(
        quantized_hidden,
        weight,
        hidden_scale,
        weight_scale,
        torch.bfloat16,
        None,
    )
    candidate_module = load_candidate(module_path)
    candidate = candidate_module.fp8_weight_stream(
        quantized_hidden,
        weight,
        hidden_scale,
        weight_scale,
    )
    torch.cuda.synchronize()

    observed = comparison(stock, candidate)
    passed = (
        observed["bitwise_equal"]
        and observed["reference_nonfinite"] == 0
        and observed["candidate_nonfinite"] == 0
    )
    atomic_json(
        args.output,
        {
            "schema_version": 1,
            "result": (
                "exact_consumer_pass" if passed else "exact_consumer_mismatch"
            ),
            "candidate_invocations": 1,
            "device": torch.cuda.get_device_name(),
            "device_capability": list(torch.cuda.get_device_capability()),
            "fatbinary_arches": arches,
            "cuobjdump_resource_usage_sha256": resource_usage_sha256,
            "fp8_utils_sha256": observed_fp8_utils_sha256,
            "module": {
                "path": str(module_path),
                "sha256": observed_module_sha256,
            },
            "seed": args.seed,
            "shape": {
                "rows": M,
                "gate_up_mnk": [M, GATE_UP, HIDDEN],
            },
            "comparison": observed,
            "decision_rule": (
                "pass iff the single candidate gate/up output is finite and "
                "bitwise equal to the stock consumer output"
            ),
        },
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
