#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import subprocess
from pathlib import Path


UPSTREAM_FILES = {
    "vllm/model_executor/models/gemma4.py": (
        "3d63af0ad265d56e09e3244a08102767efb6579a553db2c8213aa8912660b093"
    ),
    "vllm/model_executor/layers/quantization/online/fp8.py": (
        "e7bbca668d3ce6134d24110ff3b5070f51d3fee21852a3fd90c1c83d4a04f2fc"
    ),
    "vllm/model_executor/kernels/linear/scaled_mm/cutlass.py": (
        "d01b6fe09e3c3fa3991045f6ac7b469a58a550c56426ffd8900badbbe7e5355b"
    ),
    "vllm/model_executor/layers/fusion/quant_activation.py": (
        "0b206185e76fc5b793b55bc21806b66d90ede201914de0a8104e4b9cdc91b63f"
    ),
    "csrc/libtorch_stable/quantization/fused_kernels/"
    "fused_layernorm_dynamic_per_token_quant.cu": (
        "f2df61fc5808b795297d79f9b4eda6e1c2d6a76eb1d09f4d8cc9bd281afcb714"
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--project", type=Path, default=Path(__file__).parent)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    observed = {name: sha256(args.upstream / name) for name in UPSTREAM_FILES}
    source_hashes_match = observed == UPSTREAM_FILES
    patch = args.project / "implementation/vllm026_sm120_norm_fp8_fusion.patch"
    apply_check = subprocess.run(
        [
            "git",
            "-C",
            str(args.upstream),
            "apply",
            "--check",
            "--unidiff-zero",
            str(patch),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    oracle = args.project / "sm120_framework_oracle.py"
    py_compile.compile(str(oracle), doraise=True)

    patch_text = patch.read_text()
    required_fragments = [
        "rms_norm_to_fp8_linear",
        "ops.rms_norm_dynamic_per_token_quant",
        "kFp8DynamicTokenSym",
        "expose_input_quant_key(layer, self.fp8_linear)",
        "self.self_attn.qkv_proj",
    ]
    fragments_present = {
        fragment: fragment in patch_text for fragment in required_fragments
    }
    stock_cutlass_source = (args.upstream / "vllm/model_executor/kernels/linear/"
                            "scaled_mm/cutlass.py").read_text()
    stock_gemm_preserved = (
        "output = ops.cutlass_scaled_mm(" in stock_cutlass_source
        and "apply_scaled_mm" not in "\n".join(
            line for line in patch_text.splitlines() if line.startswith(("+", "-"))
        )
    )

    k = 5376
    layers = 60
    physical = []
    for phase, m in (("decode_c32", 32), ("prefill_example", 2048)):
        saved_per_boundary = 4 * m * k
        physical.append(
            {
                "phase": phase,
                "m": m,
                "k": k,
                "saved_bf16_bytes_per_boundary": saved_per_boundary,
                "saved_bf16_bytes_per_60_layer_forward": saved_per_boundary * layers,
                "saved_launches_per_boundary": 1,
                "saved_launches_per_60_layer_forward": layers,
            }
        )

    payload = {
        "schema_version": 1,
        "classification": "offline_source_and_contract_validation",
        "upstream_commit": subprocess.check_output(
            ["git", "-C", str(args.upstream), "rev-parse", "HEAD"], text=True
        ).strip(),
        "source_hashes_match": source_hashes_match,
        "upstream_sha256": observed,
        "patch_sha256": sha256(patch),
        "oracle_sha256": sha256(oracle),
        "git_apply_check": {
            "exit_code": apply_check.returncode,
            "stderr": apply_check.stderr.strip(),
        },
        "required_fragments": fragments_present,
        "stock_cutlass_scaled_mm_preserved": stock_gemm_preserved,
        "physical_prediction": physical,
    }
    payload["passed"] = (
        source_hashes_match
        and apply_check.returncode == 0
        and all(fragments_present.values())
        and stock_gemm_preserved
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(args.output)
    print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
