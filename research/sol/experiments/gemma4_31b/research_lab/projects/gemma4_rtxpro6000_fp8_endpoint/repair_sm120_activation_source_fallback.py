#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata as metadata
import json
import os
import subprocess
import tempfile
from pathlib import Path


SITE = Path("/usr/local/lib/python3.12/dist-packages")
COMPAT = SITE / "nvidia/cuda_nvcc"
ACTUAL = SITE / "nvidia/cu13"
ARCH = SITE / "sglang/jit_kernel/utils/arch.py"
ARCH_BACKUP = ARCH.with_suffix(".py.sm120-plain-target.pre")
ACTIVATION = SITE / "sglang/srt/layers/activation.py"
REMOTE_RESULT = Path(
    "/workspace/gemma4-rtxpro6000-fp8-endpoint-20260729t0338z/"
    "SM120_JIT_ACTIVATION_SOURCE_FALLBACK.remote.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        stream.write(value)
        temporary = Path(stream.name)
    temporary.replace(path)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


if not COMPAT.is_symlink() or COMPAT.resolve() != ACTUAL.resolve():
    raise RuntimeError("complete_cuda13_compat_root_required")
if not ARCH_BACKUP.is_file():
    raise RuntimeError("plain_target_attempt_backup_missing")
if sha256(ARCH_BACKUP) != "fe7f4bbd205b80c064971e66213fdfe478e1134febc783b3d4e7fadb66d10474":
    raise RuntimeError("original_arch_source_identity_changed")
arch_attempt_sha256 = sha256(ARCH)
if arch_attempt_sha256 != sha256(ARCH_BACKUP):
    atomic_text(ARCH, ARCH_BACKUP.read_text())
if sha256(ARCH) != "fe7f4bbd205b80c064971e66213fdfe478e1134febc783b3d4e7fadb66d10474":
    raise RuntimeError("arch_source_restore_failed")

activation_before = ACTIVATION.read_text()
needle = """    def forward_cuda(self, x: torch.Tensor) -> torch.Tensor:
        return self._forward_impl(x)

    def forward_xpu(self, x: torch.Tensor) -> torch.Tensor:
"""
replacement = """    def forward_cuda(self, x: torch.Tensor) -> torch.Tensor:
        if torch.cuda.get_device_capability(x.device)[0] == 12:
            return self.forward_native(x)
        return self._forward_impl(x)

    def forward_xpu(self, x: torch.Tensor) -> torch.Tensor:
"""
activation_backup = ACTIVATION.with_suffix(".py.sm120-native-fallback.pre")
if replacement not in activation_before:
    if needle not in activation_before:
        raise RuntimeError("gelu_forward_cuda_patch_point_missing")
    if not activation_backup.exists():
        atomic_text(activation_backup, activation_before)
    atomic_text(ACTIVATION, activation_before.replace(needle, replacement, 1))
if not activation_backup.is_file():
    raise RuntimeError("activation_source_backup_missing")

os.environ["CUDA_HOME"] = str(COMPAT)
os.environ["NVCC"] = str(COMPAT / "bin/nvcc")
os.environ["PATH"] = f"{COMPAT / 'bin'}:{os.environ['PATH']}"
nvrtc_dir = str(SITE / "nvidia/cu13/lib")
os.environ["LD_LIBRARY_PATH"] = (
    f"{nvrtc_dir}:{os.environ.get('LD_LIBRARY_PATH', '')}"
)

import torch
import torch.nn.functional as functional
import sglang.srt.layers.activation as activation_module
from sglang.srt.layers.activation import GeluAndMul


tripwire_calls = 0
original_jit = activation_module.gelu_tanh_and_mul


def forbidden_jit(*args, **kwargs):
    global tripwire_calls
    tripwire_calls += 1
    raise RuntimeError("sm120_activation_jit_tripwire")


activation_module.gelu_tanh_and_mul = forbidden_jit
torch.manual_seed(1785300331)
tokens = 1
intermediate_size = 21504
input_tensor = torch.randn(
    tokens,
    intermediate_size * 2,
    device="cuda",
    dtype=torch.bfloat16,
)
layer = GeluAndMul(approximate="tanh").cuda()
candidate = layer(input_tensor.clone())
torch.cuda.synchronize()
activation_module.gelu_tanh_and_mul = original_jit
gate, up = input_tensor.chunk(2, dim=-1)
reference = functional.gelu(gate, approximate="tanh") * up
delta = (candidate.float() - reference.float()).abs()
relative_l2 = float(
    torch.linalg.vector_norm(delta)
    / torch.linalg.vector_norm(reference.float()).clamp_min(1e-12)
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
    tripwire_calls == 0
    and oracle["candidate_finite"]
    and oracle["reference_finite"]
    and oracle["candidate_shape"] == [tokens, intermediate_size]
    and oracle["candidate_stride"] == list(reference.stride())
    and oracle["max_abs_error"] <= oracle["envelope"]["max_abs_error"]
    and oracle["relative_l2_error"] <= oracle["envelope"]["relative_l2_error"]
)
if not passed:
    raise RuntimeError(
        f"sm120_activation_source_fallback_failed:{tripwire_calls}:{oracle}"
    )

nvcc_version = subprocess.run(
    [str(COMPAT / "bin/nvcc"), "--version"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
ptxas_version = subprocess.run(
    [str(COMPAT / "bin/ptxas"), "--version"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
result = {
    "schema_version": 1,
    "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "classification": "exact_installed_source_sm120_activation_fallback_pass",
    "repair_id": "repair-1785300331",
    "science_started": False,
    "science_consumed": False,
    "http_submitted": False,
    "mechanism": {
        "selected": "official_sglang_gelu_and_mul_forward_native_on_sm120",
        "semantics": "preserving",
        "source_level_diff": (
            "@@ GeluAndMul.forward_cuda\n"
            "+        if torch.cuda.get_device_capability(x.device)[0] == 12:\n"
            "+            return self.forward_native(x)\n"
            "         return self._forward_impl(x)"
        ),
        "pre_source_sha256": sha256(activation_backup),
        "post_source_sha256": sha256(ACTIVATION),
        "source_path": str(ACTIVATION),
        "jit_tripwire_calls": tripwire_calls,
    },
    "rejected_attempts": {
        "cuda_home_header_repair_attempt_sha256": (
            "d546a95c847b4cd1921978880d28af5b97b34a030a207492fbe2dba772aa8c3f"
        ),
        "plain_sm120_mapping_attempt_sha256": (
            "d787981e7eea6f4f93c39e5f2f9e8fb6596207bd038ac64a23f2c27a677a4e9a"
        ),
        "plain_mapping_post_source_sha256": arch_attempt_sha256,
        "restored_arch_source_sha256": sha256(ARCH),
        "reason": (
            "The wheel-composed CUDA namespace mixed NVVM 13.3.73 PTX 9.3 "
            "with ptxas 13.0.88 PTX 9.0; both 12.0f and plain 12.0 builds "
            "failed before kernel execution."
        ),
    },
    "runtime": {
        "device": torch.cuda.get_device_name(0),
        "compute_capability": list(torch.cuda.get_device_capability(0)),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "sglang": metadata.version("sglang"),
        "sglang_kernel": metadata.version("sglang-kernel"),
        "nvidia_cuda_nvcc": metadata.version("nvidia-cuda-nvcc"),
        "nvidia_nvvm": metadata.version("nvidia-nvvm"),
        "nvcc_version": nvcc_version,
        "ptxas_version": ptxas_version,
    },
    "production_shape_oracle": {
        "consumer": "sglang.srt.layers.activation.GeluAndMul.__call__",
        "reference": "installed SGLang GeluAndMul.forward_native expression",
        "phase": "Gemma4 MLP activation",
        "tokens": tokens,
        "intermediate_size": intermediate_size,
        "approximate": "tanh",
        "oracle": oracle,
        "passed": passed,
    },
}
atomic_json(REMOTE_RESULT, result)
print(json.dumps(result, sort_keys=True))
