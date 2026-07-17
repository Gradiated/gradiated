#!/usr/bin/env python3
"""Static, source-bound SM90 admission check for the pinned AWQ/vLLM identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


EXPECTED_COMMIT = "f176443446f659dbab5315e056e605d8984fd976"
EXPECTED_CONFIG_SHA256 = "079f8fcd477b07378deafc21ecc5c3b974bf109ce5c9115854d97f88fa7622b9"
REQUIRED_SOURCE = {
    "vllm/model_executor/layers/quantization/utils/marlin_utils.py": [
        "MARLIN_SUPPORTED_GROUP_SIZES = [-1, 32, 64, 128]",
        "if device_capability < 75:",
        "res = [scalar_types.uint4b8, scalar_types.uint8b128]",
    ],
    "vllm/model_executor/layers/quantization/compressed_tensors/schemes/compressed_tensors_wNa16.py": [
        "WNA16_SUPPORTED_TYPES_MAP = {4: scalar_types.uint4b8",
        "def get_min_capability(cls) -> int:",
        "return 75",
    ],
    "vllm/model_executor/layers/quantization/compressed_tensors/compressed_tensors_moe.py": [
        "Using CompressedTensorsWNA16MarlinMoEMethod",
        "return CompressedTensorsWNA16MarlinMoEMethod(",
        "assert weight_quant.symmetric",
    ],
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vllm-source", type=Path, required=True)
    parser.add_argument("--checkpoint-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = args.vllm_source
    commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    config = json.loads(args.checkpoint_config.read_text())
    source_checks = {}
    for relative, needles in REQUIRED_SOURCE.items():
        path = source / relative
        text = path.read_text()
        source_checks[relative] = {
            "sha256": digest(path),
            "required_symbols_present": all(needle in text for needle in needles),
        }
    weights = config["quantization_config"]["config_groups"]["group_0"]["weights"]
    ignored = set(config["quantization_config"]["ignore"])
    geometry = {
        "hidden_size": config["hidden_size"],
        "moe_intermediate_size": config["moe_intermediate_size"],
        "hidden_multiple_of_128": config["hidden_size"] % 128 == 0,
        "moe_intermediate_multiple_of_128": config["moe_intermediate_size"] % 128 == 0,
        "group_size_divides_hidden": config["hidden_size"] % weights["group_size"] == 0,
        "group_size_divides_moe_intermediate": config["moe_intermediate_size"] % weights["group_size"] == 0,
    }
    checkpoint_checks = {
        "config_sha256": digest(args.checkpoint_config),
        "config_sha256_matches_pinned": digest(args.checkpoint_config) == EXPECTED_CONFIG_SHA256,
        "architecture": config["architectures"],
        "model_type": config["model_type"],
        "compressed_tensors": config["quantization_config"]["quant_method"] == "compressed-tensors",
        "packed_w4": weights["num_bits"] == 4 and weights["type"] == "int",
        "symmetric": weights["symmetric"] is True,
        "group_size": weights["group_size"],
        "group_size_is_marlin_legal": weights["group_size"] == 32,
        "moe_is_not_ignored": "model.layers.1.mlp.experts.0.gate_proj" not in ignored,
    }
    passed = (
        commit == EXPECTED_COMMIT
        and all(item["required_symbols_present"] for item in source_checks.values())
        and all(geometry.values())
        and checkpoint_checks["config_sha256_matches_pinned"]
        and checkpoint_checks["compressed_tensors"]
        and checkpoint_checks["packed_w4"]
        and checkpoint_checks["symmetric"]
        and checkpoint_checks["group_size_is_marlin_legal"]
        and checkpoint_checks["moe_is_not_ignored"]
    )
    result = {
        "evidence_label": "source_bound_static_admission_not_gpu_execution",
        "vllm_tag": "v0.15.0",
        "vllm_commit": commit,
        "vllm_commit_matches_pinned_tag": commit == EXPECTED_COMMIT,
        "target_compute_capability": 90,
        "checkpoint": checkpoint_checks,
        "geometry": geometry,
        "source_checks": source_checks,
        "dispatch_conclusion": (
            "PASS: source admits symmetric packed W4/group-32 at SM90 and its "
            "MoE selector prefers CompressedTensorsWNA16MarlinMoEMethod when "
            "geometry is legal. A real H100 model-load remains required to prove "
            "container/image integration and emitted kernels."
            if passed else "FAIL: pinned static source/config admission did not hold."
        ),
        "pass": passed,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
