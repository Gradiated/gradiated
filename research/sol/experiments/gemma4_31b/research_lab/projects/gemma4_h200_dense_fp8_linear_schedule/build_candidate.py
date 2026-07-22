#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent)
    parser.add_argument("--build-root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    import torch
    from torch.utils.cpp_extension import load

    project = args.project_root.resolve()
    build_root = args.build_root.resolve()
    build_root.mkdir(parents=True, exist_ok=True)
    source = project / "down_streamk_extension.cu"
    sgl_kernel = project / "inputs" / "sgl-kernel-v0513"
    cutlass = project / "inputs" / "cutlass-v0513-exact"
    module = load(
        name="gemma4_fp8_down_streamk",
        sources=[str(source)],
        build_directory=str(build_root),
        extra_include_paths=[
            str(sgl_kernel / "include"),
            str(sgl_kernel / "csrc"),
            str(cutlass / "include"),
            str(cutlass / "tools" / "util" / "include"),
        ],
        extra_cflags=["-O3"],
        extra_cuda_cflags=[
            "-O3",
            "-gencode=arch=compute_90,code=sm_90",
            "-DCUTE_USE_PACKED_TUPLE=1",
            "-DCUTLASS_ENABLE_TENSOR_CORE_MMA=1",
            "--expt-relaxed-constexpr",
            "--expt-extended-lambda",
            "--ptxas-options=--verbose",
        ],
        with_cuda=True,
        verbose=True,
    )
    result = {
        "candidate_symbol": "gemma4_fp8_down_streamk.fp8_down_streamk",
        "cuda_available": torch.cuda.is_available(),
        "device": torch.cuda.get_device_name() if torch.cuda.is_available() else None,
        "module_path": str(pathlib.Path(module.__file__).resolve()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
