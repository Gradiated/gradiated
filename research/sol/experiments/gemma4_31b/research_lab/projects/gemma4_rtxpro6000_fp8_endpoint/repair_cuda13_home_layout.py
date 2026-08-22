#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import tempfile
import traceback
from pathlib import Path


SITE = Path("/usr/local/lib/python3.12/dist-packages")
NVIDIA = SITE / "nvidia"
COMPAT = NVIDIA / "cuda_nvcc"
ACTUAL = NVIDIA / "cu13"
ACTIVATION = SITE / "sglang/jit_kernel/activation.py"
ARCH = SITE / "sglang/jit_kernel/utils/arch.py"
ACTIVATION_HEADER = (
    SITE / "sglang/jit_kernel/csrc/elementwise/activation.cuh"
)
REMOTE_RESULT = Path(
    "/workspace/gemma4-rtxpro6000-fp8-endpoint-20260729t0338z/"
    "SM120_CUDA13_HOME_LAYOUT_REPAIR.remote.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        stream.write(value)
        temporary = Path(stream.name)
    temporary.replace(path)


result: dict[str, object] = {
    "schema_version": 1,
    "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "repair_id": "repair-1785300331",
    "science_started": False,
    "science_consumed": False,
    "http_submitted": False,
    "failure_boundary": {
        "consumer": "sglang.jit_kernel.activation.gelu_tanh_and_mul",
        "fatal_error": "cuda_runtime.h: No such file or directory",
        "failed_cuda_home": str(COMPAT),
        "server_log_sha256": (
            "41fe5398bd2ed118b761cd3407670ab642388a98bb0942d7f56fcba82d1f40b8"
        ),
    },
}

try:
    expected_nvcc = COMPAT / "bin/nvcc"
    if (
        COMPAT.is_symlink()
        and COMPAT.resolve() == ACTUAL.resolve()
    ):
        pre_layout = {
            "kind": "symlink",
            "path": str(COMPAT),
            "target": os.readlink(COMPAT),
        }
    else:
        members = sorted(
            str(path.relative_to(COMPAT)) for path in COMPAT.rglob("*")
        )
        if members != ["bin", "bin/nvcc"]:
            raise RuntimeError(f"unexpected_compat_layout:{members}")
        if not expected_nvcc.is_symlink() or os.readlink(expected_nvcc) != "../../cu13/bin/nvcc":
            raise RuntimeError("unexpected_compat_nvcc")
        pre_layout = {
            "kind": "directory",
            "path": str(COMPAT),
            "members": members,
            "nvcc_target": os.readlink(expected_nvcc),
        }
        expected_nvcc.unlink()
        expected_nvcc.parent.rmdir()
        COMPAT.rmdir()
        COMPAT.symlink_to("cu13", target_is_directory=True)

    cuda_runtime = COMPAT / "include/cuda_runtime.h"
    nvcc = COMPAT / "bin/nvcc"
    if COMPAT.resolve() != ACTUAL.resolve() or not cuda_runtime.is_file() or not nvcc.is_file():
        raise RuntimeError("cuda13_compat_root_incomplete")

    version = subprocess.run(
        [str(nvcc), "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    if "release 13.0" not in version.stdout:
        raise RuntimeError(f"unexpected_nvcc_version:{version.stdout}")
    supported_arch = subprocess.run(
        [str(nvcc), "--list-gpu-arch"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    supported_code = subprocess.run(
        [str(nvcc), "--list-gpu-code"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if "compute_120" not in supported_arch or "sm_120" not in supported_code:
        raise RuntimeError("plain_sm120_target_missing")
    if any(value.endswith("120f") for value in supported_arch + supported_code):
        raise RuntimeError("unexpected_sm120f_compiler_target")

    arch_before = ARCH.read_text()
    arch_needle = """    if major == 12:
        if get_cuda_version() < (12, 9):
            return ""
        return "f" if minor == 0 else "a"
"""
    arch_replacement = """    if major == 12:
        if minor == 0:
            return ""
        if get_cuda_version() < (12, 9):
            return ""
        return "a"
"""
    if arch_replacement not in arch_before:
        if arch_needle not in arch_before:
            raise RuntimeError("sm120_arch_mapping_patch_point_missing")
        arch_backup = ARCH.with_suffix(".py.sm120-plain-target.pre")
        if not arch_backup.exists():
            atomic_text(arch_backup, arch_before)
        atomic_text(ARCH, arch_before.replace(arch_needle, arch_replacement, 1))
    else:
        arch_backup = ARCH.with_suffix(".py.sm120-plain-target.pre")
    if not arch_backup.is_file():
        raise RuntimeError("sm120_arch_mapping_backup_missing")

    os.environ["CUDA_HOME"] = str(COMPAT)
    os.environ["NVCC"] = str(nvcc)
    os.environ["PATH"] = f"{COMPAT / 'bin'}:{os.environ['PATH']}"

    import torch
    import torch.nn.functional as functional
    from sglang.jit_kernel.activation import gelu_tanh_and_mul
    from sglang.jit_kernel.utils import get_jit_cuda_arch

    if get_jit_cuda_arch().target_name != "12.0":
        raise RuntimeError(
            f"unexpected_patched_target:{get_jit_cuda_arch().target_name}"
        )

    torch.manual_seed(1785300331)
    tokens = 1
    intermediate_size = 21504
    input_tensor = torch.randn(
        tokens,
        intermediate_size * 2,
        device="cuda",
        dtype=torch.bfloat16,
    )
    candidate = gelu_tanh_and_mul(input_tensor)
    torch.cuda.synchronize()
    gate, up = input_tensor.float().chunk(2, dim=-1)
    reference = functional.gelu(gate, approximate="tanh") * up
    delta = (candidate.float() - reference).abs()
    relative_l2 = float(
        torch.linalg.vector_norm(delta)
        / torch.linalg.vector_norm(reference).clamp_min(1e-12)
    )
    oracle = {
        "dtype": str(input_tensor.dtype),
        "input_shape": list(input_tensor.shape),
        "input_stride": list(input_tensor.stride()),
        "candidate_shape": list(candidate.shape),
        "candidate_stride": list(candidate.stride()),
        "candidate_finite": bool(torch.isfinite(candidate).all()),
        "reference_finite": bool(torch.isfinite(reference).all()),
        "max_abs_error": float(delta.max()),
        "relative_l2_error": relative_l2,
        "envelope": {"max_abs_error": 0.0625, "relative_l2_error": 0.01},
    }
    passed = (
        oracle["candidate_finite"]
        and oracle["reference_finite"]
        and oracle["candidate_shape"] == [tokens, intermediate_size]
        and oracle["max_abs_error"] <= oracle["envelope"]["max_abs_error"]
        and oracle["relative_l2_error"] <= oracle["envelope"]["relative_l2_error"]
    )
    if not passed:
        raise RuntimeError(f"activation_oracle_failed:{oracle}")

    cache_root = Path("~/.cache/tvm-ffi").expanduser()
    modules = sorted(
        str(path)
        for path in cache_root.glob(
            "sgl_kernel_jit_activation_bf16_t_true_*__arch_12.0__tvmffi_0.1.11/*.so"
        )
    )
    if len(modules) != 1:
        raise RuntimeError(f"expected_one_activation_module:{modules}")
    module = Path(modules[0])
    result.update(
        {
            "classification": "recoverable_cuda13_home_layout_repair_pass",
            "causal_amendment": (
                "Replace only the researcher-created partial cuda_nvcc directory "
                "with a symlink to the complete wheel-composed nvidia/cu13 root, "
                "so the unchanged owner's CUDA_HOME includes headers and toolchain."
            ),
            "pre_layout": pre_layout,
            "post_layout": {
                "kind": "symlink",
                "path": str(COMPAT),
                "target": os.readlink(COMPAT),
                "resolved": str(COMPAT.resolve()),
            },
            "toolchain": {
                "cuda_home": str(COMPAT),
                "nvcc": str(nvcc),
                "nvcc_sha256": sha256(nvcc),
                "nvcc_version": version.stdout.strip(),
                "supported_gpu_arch": supported_arch,
                "supported_gpu_code": supported_code,
                "cuda_runtime_header": str(cuda_runtime),
                "cuda_runtime_header_sha256": sha256(cuda_runtime),
            },
            "source_identities": {
                "activation_py_sha256": sha256(ACTIVATION),
                "activation_header_sha256": sha256(ACTIVATION_HEADER),
                "arch_py_pre_sha256": sha256(arch_backup),
                "arch_py_post_sha256": sha256(ARCH),
            },
            "activation_boundary": {
                "consumer": "sglang.jit_kernel.activation.gelu_tanh_and_mul",
                "phase": "production_gemma4_mlp",
                "tokens": tokens,
                "intermediate_size": intermediate_size,
                "oracle": oracle,
                "passed": True,
                "compiled_module": str(module),
                "compiled_module_sha256": sha256(module),
                "jit_target": get_jit_cuda_arch().target_name,
            },
        }
    )
except Exception as error:
    result.update(
        {
            "classification": "recoverable_cuda13_home_layout_repair_failed",
            "error": f"{type(error).__name__}: {error}",
            "traceback": traceback.format_exc(),
        }
    )
    atomic_json(REMOTE_RESULT, result)
    raise

atomic_json(REMOTE_RESULT, result)
print(json.dumps(result, sort_keys=True))
