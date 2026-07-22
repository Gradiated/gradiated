#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import errno
import hashlib
import json
import os
import pathlib
import shutil


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
BASE = LAB / "projects/gemma4_h200_v0513_fp8_qkv_residual_profile"
QKV = LAB / "projects/gemma4_h200_qkv_epilogue_fusion"
SOURCE = pathlib.Path("/root/workspace/.agents/runtime/sglang-v0.5.13-source")
FICLONE = 0x40049409


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def copy_small(source: pathlib.Path, destination: pathlib.Path) -> dict[str, object]:
    raw = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(raw)
    os.chmod(temporary, 0o444)
    os.replace(temporary, destination)
    return {
        "path": str(destination.relative_to(PROJECT)),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "source_provenance": str(source),
    }


def reflink(source: pathlib.Path, destination: pathlib.Path, expected: str) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size == source.stat().st_size:
        actual = sha256(destination)
        if actual == expected:
            return {
                "path": str(destination.relative_to(PROJECT)),
                "bytes": destination.stat().st_size,
                "sha256": actual,
                "source_provenance": str(source),
                "materialization": "existing_verified_project_local",
            }
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    try:
        with source.open("rb") as source_handle, temporary.open("wb") as destination_handle:
            fcntl.ioctl(destination_handle.fileno(), FICLONE, source_handle.fileno())
        materialization = "reflink_copy_on_write_verified_project_local"
    except OSError as exception:
        if exception.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EXDEV):
            raise
        temporary.unlink(missing_ok=True)
        shutil.copyfile(source, temporary)
        materialization = "full_byte_copy_verified_project_local"
    os.chmod(temporary, 0o444)
    actual = sha256(temporary)
    if actual != expected:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"checkpoint hash mismatch for {source.name}: {actual} != {expected}")
    os.replace(temporary, destination)
    return {
        "path": str(destination.relative_to(PROJECT)),
        "bytes": destination.stat().st_size,
        "sha256": actual,
        "source_provenance": str(source),
        "materialization": materialization,
    }


def main() -> int:
    base_manifest = json.loads((BASE / "INPUT_MANIFEST.json").read_text())
    checkpoint = []
    for row in base_manifest["checkpoint_files"]:
        source = BASE / "inputs/checkpoint" / row["name"]
        destination = PROJECT / "inputs/checkpoint" / row["name"]
        checkpoint.append(reflink(source, destination, row["sha256"]))

    stack_sources = {
        "proven_v0513_endpoint_entrypoint.py": QKV / "proven_v0513_endpoint_entrypoint.py",
        "fp8_qkv_paired_runner.py": QKV / "fp8_qkv_paired_runner.py",
        "install_endpoint_patch.py": QKV / "install_endpoint_patch.py",
        "qkv_epilogue_discriminator.py": QKV / "qkv_epilogue_discriminator.py",
        "residual_sitecustomize.py": BASE / "residual_sitecustomize.py",
        "attention_intervention.py": BASE / "intervention/attention_deferred_local_kv.py",
    }
    stack = [
        copy_small(source, PROJECT / "inputs/stack" / name)
        for name, source in stack_sources.items()
    ]

    source_files = {
        "gemma3_causal.py": SOURCE / "python/sglang/srt/models/gemma3_causal.py",
        "gemma4_causal.py": SOURCE / "python/sglang/srt/models/gemma4_causal.py",
        "fp8.py": SOURCE / "python/sglang/srt/layers/quantization/fp8.py",
        "fp8_utils.py": SOURCE / "python/sglang/srt/layers/quantization/fp8_utils.py",
        "fp8_kernel.py": SOURCE / "python/sglang/srt/layers/quantization/fp8_kernel.py",
        "per_token_quant_fp8.cu": SOURCE / "sgl-kernel/csrc/gemm/per_token_quant_fp8.cu",
        "activation.cu": SOURCE / "sgl-kernel/csrc/elementwise/activation.cu",
    }
    exact_source = [
        copy_small(source, PROJECT / "inputs/source" / name)
        for name, source in source_files.items()
    ]

    programs = []
    for name in (
        "component_benchmark.py",
        "fused_gelu_quant.cu",
        "fused_gelu_quant.py",
        "fusion_patch.py",
        "sitecustomize.py",
        "remote_fusion_stack.sh",
        "run_bench_owner.py",
    ):
        path = PROJECT / name
        programs.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    manifest = {
        "schema_version": 1,
        "pass": True,
        "runtime": {
            "release": "sglang v0.5.13",
            "commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "image_linux_amd64": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6",
        },
        "model": {
            "id": "google/gemma-4-31B-it",
            "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "checkpoint_index_sha256": "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2",
        },
        "checkpoint": checkpoint,
        "stack": stack,
        "exact_source": exact_source,
        "programs": programs,
        "workload": base_manifest["workload"],
        "representation": base_manifest["representation"],
        "economics": base_manifest["economics"],
        "immutable_transfer_contract": "stage only these project-local bytes; reconcile size and sha256 before atomic remote finalize",
    }
    atomic_json(PROJECT / "GPU_INPUT_MANIFEST.json", manifest)
    shutil.copyfile(PROJECT / "GPU_INPUT_MANIFEST.json", PROJECT / "inputs/stack/GPU_INPUT_MANIFEST.json")
    os.chmod(PROJECT / "inputs/stack/GPU_INPUT_MANIFEST.json", 0o444)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
