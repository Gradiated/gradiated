#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


MODULE_NAME = "m32_static_scheduler_ext"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--vllm-source", type=Path, required=True)
    parser.add_argument("--cutlass-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    args = parser.parse_args()

    if sha256(args.source) != args.expected_source_sha256:
        raise RuntimeError("candidate_source_hash_mismatch")
    dispatcher = (
        args.vllm_source
        / "csrc/quantization/w8a8/cutlass/c3x/scaled_mm_sm100_fp8_dispatch.cuh"
    )
    scheduler = (
        args.cutlass_source / "include/cutlass/gemm/kernel/tile_scheduler.hpp"
    )
    for required in (dispatcher, scheduler):
        if not required.is_file():
            raise RuntimeError(f"required_source_missing:{required}")

    args.output.mkdir(parents=True, exist_ok=False)
    build_directory = args.output / "build"
    build_directory.mkdir()
    compatibility_header = args.output.parent / "m32_static_vllm_compat.hpp"
    compatibility_header.write_text(
        "#pragma once\n"
        "#include \"/vllm/csrc/cutlass_extensions/common.hpp\"\n"
        "namespace vllm {\n"
        "template <typename Kernel>\n"
        "using enable_sm100f_only = ::enable_sm100f_only<Kernel>;\n"
        "}\n"
    )
    os.environ["TORCH_CUDA_ARCH_LIST"] = "10.0f"

    from torch.utils.cpp_extension import load

    include_paths = [
        str(args.vllm_source / "csrc"),
        str(args.cutlass_source / "include"),
        str(args.cutlass_source / "tools/util/include"),
    ]
    # The pinned runtime image supplies nvcc but omits CUDA development headers.
    # The retained B200 stages its exact host header tree read-only at this packet
    # path; no scientific source, geometry, or runtime dispatch byte changes.
    retained_cuda_headers = Path("/packet/cuda-include")
    if retained_cuda_headers.is_dir():
        include_paths.append(str(retained_cuda_headers))

    module = load(
        name=MODULE_NAME,
        sources=[str(args.source)],
        extra_include_paths=include_paths,
        extra_cflags=["-O3"],
        extra_cuda_cflags=[
            "-O3",
            "-gencode=arch=compute_100f,code=sm_100f",
            "-include",
            str(compatibility_header),
        ],
        build_directory=str(build_directory),
        verbose=True,
    )
    built_module = Path(module.__file__).resolve()
    ninja_file = build_directory / "build.ninja"
    if not ninja_file.is_file():
        raise RuntimeError("build_ninja_missing")
    build_text = ninja_file.read_text()
    sm_codes = sorted(set(re.findall(r"code=sm_([0-9]+f?)", build_text)))
    if sm_codes != ["100f"]:
        raise RuntimeError(f"compiler_arch_fanout:{sm_codes}")
    final_module = args.output / built_module.name
    shutil.copy2(built_module, final_module)
    metadata = dict(module.schedule_metadata())
    required_metadata = {
        "scheduler_tag": "cutlass::gemm::StaticPersistentScheduler",
        "stock_scheduler_resolves_to":
            "cutlass::gemm::PersistentTileSchedulerSm100",
        "mainloop_identical_to_stock": True,
        "epilogue_identical_to_stock": True,
    }
    for key, expected in required_metadata.items():
        if metadata.get(key) != expected:
            raise RuntimeError(f"schedule_metadata_mismatch:{key}")
    atomic_json(
        args.output / "BUILD_MANIFEST.json",
        {
            "schema_version": 1,
            "classification": "sm100_extension_built",
            "module_name": MODULE_NAME,
            "module_path": final_module.name,
            "module_sha256": sha256(final_module),
            "candidate_source_sha256": sha256(args.source),
            "vllm_dispatcher_sha256": sha256(dispatcher),
            "cutlass_scheduler_sha256": sha256(scheduler),
            "torch_cuda_arch_list": "10.0f",
            "nvcc_gencode": "compute_100f,sm_100f",
            "compiled_sm_codes": sm_codes,
            "build_ninja_sha256": sha256(ninja_file),
            "schedule_metadata": metadata,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
