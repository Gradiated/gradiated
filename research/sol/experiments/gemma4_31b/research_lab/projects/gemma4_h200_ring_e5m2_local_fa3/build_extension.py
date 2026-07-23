#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tarfile
from pathlib import Path

from torch.utils.cpp_extension import load


HERE = Path(__file__).resolve().parent


def extracted_roots(build_directory: Path) -> tuple[Path, Path, Path]:
    source = HERE / "inputs/source"
    if source.is_dir():
        return source / "sgl-kernel", source / "sgl-attn", source / "cutlass"
    vendor = build_directory / "vendor"
    snapshot = HERE / "inputs/gpu-input-snapshot.tar.gz"
    snapshot_root = vendor / "snapshot"
    if snapshot.is_file():
        if not snapshot_root.is_dir():
            snapshot_root.mkdir(parents=True)
            with tarfile.open(snapshot, "r:gz") as handle:
                handle.extractall(snapshot_root, filter="data")
        source = snapshot_root / "inputs/source"
        return source / "sgl-kernel", source / "sgl-attn", source / "cutlass"
    archives = (
        (
            HERE
            / "inputs/sglang-28b095c01005d4a3a2a5b637b7d028b07fba31b2.tar.gz",
            vendor / "sglang",
        ),
        (
            HERE
            / "inputs/sgl-attn-bcf72ccc6816b36a5fae2c5a3c027604629785e0.tar.gz",
            vendor / "sgl-attn",
        ),
        (
            HERE
            / "inputs/cutlass-57e3cfb47a2d9e0d46eb6335c3dc411498efa198.tar.gz",
            vendor / "cutlass",
        ),
    )
    roots = []
    for archive, destination in archives:
        if not destination.is_dir():
            destination.mkdir(parents=True)
            with tarfile.open(archive, "r:gz") as handle:
                handle.extractall(destination, filter="data")
        roots.append(next(path for path in destination.iterdir() if path.is_dir()))
    return roots[0] / "sgl-kernel", roots[1], roots[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-directory", type=Path, required=True)
    parser.add_argument("--flash-ops", type=Path, required=True)
    args = parser.parse_args()
    args.build_directory.mkdir(parents=True, exist_ok=True)

    sgl_kernel, sgl_attn, cutlass = extracted_roots(args.build_directory)
    candidate = HERE / "candidate"
    definitions = [
        "-DNDEBUG",
        "-DOPERATOR_NAMESPACE=ring-e5m2-fa3",
        "-DFLASHATTENTION_DISABLE_BACKWARD",
        "-DFLASHATTENTION_DISABLE_DROPOUT",
        "-DFLASHATTENTION_DISABLE_UNEVEN_K",
        "-DFLASHATTENTION_DISABLE_FP16",
        "-DFLASHATTENTION_DISABLE_HDIM64",
        "-DFLASHATTENTION_DISABLE_HDIM96",
        "-DFLASHATTENTION_DISABLE_HDIM128",
        "-DFLASHATTENTION_DISABLE_HDIM192",
        "-DFLASHATTENTION_DISABLE_HDIMDIFF64",
        "-DFLASHATTENTION_DISABLE_HDIMDIFF192",
    ]
    cuda_flags = [
        *definitions,
        "-O3",
        "-gencode=arch=compute_90a,code=sm_90a",
        "-std=c++17",
        "-DCUTE_USE_PACKED_TUPLE=1",
        "-DCUTLASS_ENABLE_TENSOR_CORE_MMA=1",
        "-DCUTLASS_VERSIONS_GENERATED",
        "-DCUTLASS_TEST_LEVEL=0",
        "-DCUTLASS_TEST_ENABLE_CACHED_RESULTS=1",
        "-DCUTLASS_DEBUG_TRACE_LEVEL=0",
        "-DCUTLASS_ENABLE_GDC_FOR_SM90",
        "-DCUTE_SM90_EXTENDED_MMA_SHAPES_ENABLED",
        "--expt-relaxed-constexpr",
        "--expt-extended-lambda",
        "--use_fast_math",
        "-Xcompiler=-Wconversion",
        "-Xcompiler=-fno-strict-aliasing",
    ]
    module = load(
        name="ring_e5m2_flash_ops",
        sources=[
            str(candidate / "ring_e5m2_flash_extension.cc"),
            str(candidate / "flash_api_e5m2.cpp"),
            str(
                sgl_attn
                / "hopper/flash_prepare_scheduler.cu"
            ),
            str(sgl_attn / "hopper/flash_fwd_combine.cu"),
            str(candidate / "flash_fwd_hdim256_e5m2_packgqa_sm90.cu"),
            str(candidate / "flash_fwd_hdim256_e5m2_split_sm90.cu"),
        ],
        extra_include_paths=[
            str(sgl_kernel / "include"),
            str(sgl_attn / "hopper"),
            str(cutlass / "include"),
            str(cutlass / "tools/util/include"),
        ],
        extra_cflags=[*definitions, "-O3", "-std=c++17"],
        extra_cuda_cflags=cuda_flags,
        extra_ldflags=[
            str(args.flash_ops),
            f"-Wl,-rpath,{args.flash_ops.parent}",
        ],
        build_directory=str(args.build_directory),
        verbose=True,
    )
    output = Path(module.__file__).resolve()
    (args.build_directory / "BUILD_RESULT.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "module": str(output),
                "bytes": output.stat().st_size,
                "max_jobs": os.environ.get("MAX_JOBS"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
