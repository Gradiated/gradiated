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
    module = load(
        name="gemma4_fp8_gate_up_multicast",
        sources=[str(project / "gate_up_multicast_extension.cu")],
        build_directory=str(build_root),
        extra_include_paths=[
            str(project / "inputs" / "sgl-kernel-v0513" / "include"),
            str(project / "inputs" / "sgl-kernel-v0513" / "csrc"),
            str(project / "inputs" / "cutlass-v0513-exact" / "include"),
            str(project / "inputs" / "cutlass-v0513-exact" / "tools" / "util" / "include"),
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
    value = {
        "candidate_symbol": "gemma4_fp8_gate_up_multicast.fp8_gate_up_multicast",
        "cuda_available": torch.cuda.is_available(),
        "device": torch.cuda.get_device_name() if torch.cuda.is_available() else None,
        "module_path": str(pathlib.Path(module.__file__).resolve()),
        "tile_mnk": [128, 128, 128],
        "stock_cluster_mnk": [2, 1, 1],
        "candidate_cluster_mnk": [2, 2, 1],
        "schedule": "KernelTmaWarpSpecializedPingpongFP8FastAccum",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
