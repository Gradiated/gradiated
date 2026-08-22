#!/usr/bin/env python3
"""Apply the corrected GeluMul -> dynamic-FP8 integration to pinned SGLang."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import pathlib


PROJECT = pathlib.Path(__file__).resolve().parent.parent
EXPECTED = {
    "python/sglang/srt/layers/quantization/fp8.py": (
        "c7368db317513e5823283eb5567d15fdb742c3b01a98bfc483cb500291b4285a"
    ),
    "python/sglang/srt/models/gemma3_causal.py": (
        "a9827bde583c5b8b0abfeaced097c4e9d060fb99ec2961b4f9c66173d3027282"
    ),
}
ASSETS = {
    PROJECT / "candidate/gemma4_gelu_fp8.py": (
        "python/sglang/srt/layers/quantization/gemma4_gelu_fp8.py"
    ),
    PROJECT / "candidate/fused_gelu_mul_dynamic_fp8_sm90.cu": (
        "python/sglang/srt/layers/quantization/fused_gelu_mul_dynamic_fp8_sm90.cu"
    ),
}


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one source match, found {count}")
    return source.replace(old, new, 1)


def transform_fp8(source: str) -> str:
    old = """    def apply(
        self,
        layer: torch.nn.Module,
        x: torch.Tensor,
        bias: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        if self.use_marlin:
"""
    new = """    def apply(
        self,
        layer: torch.nn.Module,
        x: torch.Tensor,
        bias: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        if isinstance(x, tuple):
            from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm

            qinput, x_scale, output_dtype = x
            if self.use_marlin or self.use_mxfp8 or self.block_quant:
                raise RuntimeError(
                    "prequantized GeluMul input requires dense CUTLASS FP8"
                )
            if not self.cutlass_fp8_supported:
                raise RuntimeError(
                    "prequantized GeluMul input requires CUTLASS FP8"
                )
            if layer.input_scale is not None:
                raise RuntimeError(
                    "prequantized GeluMul input requires dynamic activation scale"
                )
            if layer.weight_scale.numel() != layer.weight.shape[1]:
                raise RuntimeError(
                    "prequantized GeluMul input requires per-channel weight scale"
                )
            if qinput.dtype != torch.float8_e4m3fn:
                raise RuntimeError("prequantized GeluMul input dtype mismatch")
            if x_scale.dtype != torch.float32:
                raise RuntimeError("prequantized GeluMul scale dtype mismatch")
            if qinput.shape[-1] != layer.weight.shape[0]:
                raise RuntimeError("prequantized GeluMul K mismatch")
            if x_scale.shape != (*qinput.shape[:-1], 1):
                raise RuntimeError("prequantized GeluMul scale shape mismatch")
            output = fp8_scaled_mm(
                qinput,
                layer.weight,
                x_scale,
                layer.weight_scale,
                out_dtype=output_dtype,
                bias=bias,
            )
            return output.view(*qinput.shape[:-1], layer.weight.shape[1])

        if self.use_marlin:
"""
    return replace_once(source, old, new, "Fp8LinearMethod.apply")


def transform_gemma3(source: str) -> str:
    source = replace_once(
        source,
        "import copy\nfrom typing import Iterable, List, Optional, Set, Tuple\n",
        "import copy\nimport os\nfrom typing import Iterable, List, Optional, Set, Tuple\n",
        "gemma3 os import",
    )
    old_import = """from sglang.srt.layers.linear import (
    MergedColumnParallelLinear,
    QKVParallelLinear,
    RowParallelLinear,
)
from sglang.srt.layers.logits_processor import LogitsProcessor
"""
    new_import = """from sglang.srt.layers.linear import (
    MergedColumnParallelLinear,
    QKVParallelLinear,
    RowParallelLinear,
)
from sglang.srt.layers.logits_processor import LogitsProcessor
from sglang.srt.layers.quantization.gemma4_gelu_fp8 import (
    fused_gelu_mul_dynamic_fp8,
    prepare as prepare_gelu_mul_dynamic_fp8,
)
"""
    source = replace_once(source, old_import, new_import, "gemma3 fusion import")
    old_mlp = """        self.act_fn = GeluAndMul()
        self.prefix = prefix

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        gate_up, _ = self.gate_up_proj(x)
        x = self.act_fn(gate_up)
        x, _ = self.down_proj(x)
        return x
"""
    new_mlp = """        self.act_fn = GeluAndMul()
        self.prefix = prefix
        self.fuse_gelu_mul_dynamic_fp8 = (
            os.environ.get("SGLANG_GEMMA4_GELU_FP8_FUSION") == "1"
            and intermediate_size == 21504
            and self.down_proj.tp_size == 1
            and self.down_proj.quant_method.__class__.__name__
            == "Fp8LinearMethod"
            and not self.down_proj.quant_method.block_quant
            and not self.down_proj.quant_method.use_marlin
            and not self.down_proj.quant_method.use_mxfp8
            and self.down_proj.quant_method.cutlass_fp8_supported
        )
        if self.fuse_gelu_mul_dynamic_fp8:
            prepare_gelu_mul_dynamic_fp8()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        gate_up, _ = self.gate_up_proj(x)
        if (
            self.fuse_gelu_mul_dynamic_fp8
            and gate_up.dim() == 2
            and 0 < gate_up.shape[0] <= 128
        ):
            quantized, scale = fused_gelu_mul_dynamic_fp8(gate_up)
            x, _ = self.down_proj((quantized, scale, gate_up.dtype))
        else:
            x = self.act_fn(gate_up)
            x, _ = self.down_proj(x)
        return x
"""
    return replace_once(source, old_mlp, new_mlp, "Gemma3MLP integration")


def atomic_write(path: pathlib.Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.gemma4-fusion-{os.getpid()}.tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sglang-root", type=pathlib.Path, required=True)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate and render in memory without changing the source tree",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        help="optional path for the JSON validation receipt",
    )
    args = parser.parse_args()
    root = args.sglang_root.resolve()

    rendered: dict[pathlib.Path, bytes] = {}
    transforms = {
        "python/sglang/srt/layers/quantization/fp8.py": transform_fp8,
        "python/sglang/srt/models/gemma3_causal.py": transform_gemma3,
    }
    for relative, expected in EXPECTED.items():
        path = root / relative
        original = path.read_bytes()
        actual = digest_bytes(original)
        if actual != expected:
            raise RuntimeError(
                f"{relative}: pinned hash mismatch: expected {expected}, got {actual}"
            )
        updated = transforms[relative](original.decode()).encode()
        ast.parse(updated, filename=str(path))
        rendered[path] = updated

    for source, relative in ASSETS.items():
        value = source.read_bytes()
        if not value:
            raise RuntimeError(f"empty candidate asset: {source}")
        if source.suffix == ".py":
            ast.parse(value, filename=str(source))
        rendered[root / relative] = value

    if not args.check:
        for path, value in rendered.items():
            atomic_write(path, value)

    receipt = {
        "schema_version": 1,
        "mode": "check" if args.check else "apply",
        "pinned_source_identity_pass": True,
        "source_tree_mutated": not args.check,
        "output_files": {
            str(path.relative_to(root)): digest_bytes(value)
            for path, value in sorted(
                rendered.items(), key=lambda item: str(item[0])
            )
        },
    }
    serialized = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        atomic_write(args.output.resolve(), serialized.encode())
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
