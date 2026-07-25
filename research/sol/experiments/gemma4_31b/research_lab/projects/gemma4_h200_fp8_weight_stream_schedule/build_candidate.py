#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=pathlib.Path, required=True)
    parser.add_argument("--sgl-kernel-root", type=pathlib.Path, required=True)
    parser.add_argument("--cutlass-root", type=pathlib.Path, required=True)
    parser.add_argument("--build-root", type=pathlib.Path, required=True)
    parser.add_argument("--snapshot", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    import torch
    from torch.utils.cpp_extension import load

    source = (args.project_root / "fp8_weight_stream_extension.cu").resolve()
    dispatch = (
        args.sgl_kernel_root
        / "csrc/cutlass_extensions/gemm/fp8_gemm_sm90_dispatch.cuh"
    ).resolve()
    args.build_root.mkdir(parents=True, exist_ok=True)
    module = load(
        name="gemma4_fp8_weight_stream",
        sources=[str(source)],
        build_directory=str(args.build_root.resolve()),
        extra_include_paths=[
            str((args.sgl_kernel_root / "include").resolve()),
            str((args.sgl_kernel_root / "csrc").resolve()),
            str((args.cutlass_root / "include").resolve()),
            str((args.cutlass_root / "tools/util/include").resolve()),
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
    module_path = pathlib.Path(module.__file__).resolve()
    args.snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot_temporary = args.snapshot.with_suffix(args.snapshot.suffix + ".part")
    shutil.copy2(module_path, snapshot_temporary)
    snapshot_temporary.replace(args.snapshot)
    resource = subprocess.run(
        ["cuobjdump", "--dump-resource-usage", str(module_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    atomic_json(
        args.output,
        {
            "schema_version": 1,
            "result": "compile_pass",
            "target": "sm_90",
            "torch_version": torch.__version__,
            "torch_cuda_version": torch.version.cuda,
            "candidate_symbol": "gemma4_fp8_weight_stream.fp8_weight_stream",
            "source": {
                "path": str(source),
                "sha256": sha256(source),
            },
            "pinned_dispatch": {
                "path": str(dispatch),
                "sha256": sha256(dispatch),
            },
            "module": {
                "path": str(module_path),
                "sha256": sha256(module_path),
            },
            "immutable_project_snapshot": {
                "path": str(args.snapshot.resolve()),
                "sha256": sha256(args.snapshot),
            },
            "schedule": dict(module.schedule_metadata()),
            "cuobjdump_resource_usage": resource.stdout + resource.stderr,
            "gpu_was_used": False,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
