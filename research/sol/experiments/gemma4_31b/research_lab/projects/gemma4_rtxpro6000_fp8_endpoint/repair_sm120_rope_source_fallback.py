#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata as metadata
import inspect
import json
import os
import tempfile
from pathlib import Path


SITE = Path("/usr/local/lib/python3.12/dist-packages")
BASE = SITE / "sglang/srt/layers/rotary_embedding/base.py"
ROPE = SITE / "sglang/jit_kernel/rope.py"
ARCH = SITE / "sglang/jit_kernel/utils/arch.py"
COMPILE = SITE / "sglang/jit_kernel/utils/compile.py"
GEMMA = SITE / "sglang/srt/models/gemma4_causal.py"
NVCC_DIST = SITE / "nvidia_cuda_nvcc-13.0.88.dist-info"
NVCC_ACTUAL = SITE / "nvidia/cu13/bin/nvcc"
NVCC_COMPAT = SITE / "nvidia/cuda_nvcc/bin/nvcc"
REMOTE_RESULT = Path(
    "/workspace/gemma4-rtxpro6000-fp8-endpoint-20260729t0338z/"
    "SM120_ROPE_JIT_SOURCE_FALLBACK.remote.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        stream.write(text)
        temporary = Path(stream.name)
    temporary.replace(path)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def source_identity(path: Path) -> dict[str, object]:
    return {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}


pre = {path.name: source_identity(path) for path in (BASE, ROPE, ARCH, COMPILE, GEMMA)}
base_before = BASE.read_text()
needle = """    ) -> Tuple[torch.Tensor, torch.Tensor]:
        if not self.use_fallback_kernel:
"""
replacement = """    ) -> Tuple[torch.Tensor, torch.Tensor]:
        if torch.cuda.get_device_capability(query.device)[0] == 12:
            if fused_set_kv_buffer_arg is not None:
                raise RuntimeError(
                    "sm120_native_rope_fallback_does_not_support_fused_kv_store"
                )
            return self.forward_native(positions, query, key, offsets)
        if not self.use_fallback_kernel:
"""
if replacement not in base_before:
    if needle not in base_before:
        raise RuntimeError("installed_sglang_forward_cuda_patch_point_missing")
    backup = BASE.with_suffix(".py.sm120-source-fallback.pre")
    if not backup.exists():
        atomic_text(backup, base_before)
    atomic_text(BASE, base_before.replace(needle, replacement, 1))

if metadata.version("nvidia-cuda-nvcc") != "13.0.88":
    raise RuntimeError("cuda13_package_identity_changed")
if not NVCC_ACTUAL.is_file():
    raise RuntimeError("recorded_cuda13_nvcc_missing")
NVCC_COMPAT.parent.mkdir(parents=True, exist_ok=True)
if NVCC_COMPAT.exists() or NVCC_COMPAT.is_symlink():
    if NVCC_COMPAT.resolve() != NVCC_ACTUAL.resolve():
        raise RuntimeError("nvcc_compat_target_conflict")
else:
    NVCC_COMPAT.symlink_to(Path("../../cu13/bin/nvcc"))
record = NVCC_DIST / "RECORD"
record_line = "nvidia/cuda_nvcc/bin/nvcc,,"
record_text = record.read_text()
if record_line not in record_text.splitlines():
    atomic_text(record, record_text.rstrip("\n") + "\n" + record_line + "\n")

import torch
from sglang.srt.runtime_context import get_context
from sglang.srt.layers.rotary_embedding.base import RotaryEmbedding

get_context().override_server_args().install()
torch.manual_seed(1785299364)
tokens = 8192
head_size = 256
q_heads = 32
kv_heads = 16
positions = torch.arange(tokens, device="cuda", dtype=torch.int64)
query_input = torch.randn(
    tokens, q_heads * head_size, device="cuda", dtype=torch.bfloat16
)
key_input = torch.randn(
    tokens, kv_heads * head_size, device="cuda", dtype=torch.bfloat16
)
rotary = RotaryEmbedding(
    head_size=head_size,
    rotary_dim=head_size,
    max_position_embeddings=262144,
    base=10000,
    is_neox_style=True,
    dtype=torch.bfloat16,
).cuda()
query_candidate, key_candidate = rotary(
    positions, query_input.clone(), key_input.clone(), fused_set_kv_buffer_arg=None
)
torch.cuda.synchronize()
query_reference, key_reference = rotary.forward_native(
    positions, query_input.clone(), key_input.clone()
)
torch.cuda.synchronize()


def oracle(candidate: torch.Tensor, reference: torch.Tensor) -> dict[str, object]:
    delta = (candidate.float() - reference.float()).abs()
    relative_l2 = float(
        torch.linalg.vector_norm(delta)
        / torch.linalg.vector_norm(reference.float()).clamp_min(1e-12)
    )
    return {
        "candidate_shape": list(candidate.shape),
        "reference_shape": list(reference.shape),
        "candidate_stride": list(candidate.stride()),
        "reference_stride": list(reference.stride()),
        "candidate_finite": bool(torch.isfinite(candidate).all()),
        "reference_finite": bool(torch.isfinite(reference).all()),
        "max_abs_error": float(delta.max()),
        "relative_l2_error": relative_l2,
    }


q_oracle = oracle(query_candidate, query_reference)
k_oracle = oracle(key_candidate, key_reference)
envelope = {"max_abs_error": 0.03125, "relative_l2_error": 0.01}
passed = all(
    row["candidate_finite"]
    and row["reference_finite"]
    and row["candidate_shape"] == row["reference_shape"]
    and row["candidate_stride"] == row["reference_stride"]
    and row["max_abs_error"] <= envelope["max_abs_error"]
    and row["relative_l2_error"] <= envelope["relative_l2_error"]
    for row in (q_oracle, k_oracle)
)
if not passed:
    raise RuntimeError(f"sm120_rope_framework_oracle_failed:{q_oracle}:{k_oracle}")

post = {
    path.name: source_identity(path)
    for path in (BASE, ROPE, ARCH, COMPILE, GEMMA, record, NVCC_ACTUAL)
}
result = {
    "schema_version": 1,
    "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "classification": "exact_installed_source_sm120_rope_fallback_pass",
    "science_started": False,
    "science_consumed": False,
    "http_submitted": False,
    "repair_id": "repair-1785299364",
    "mechanism": {
        "selected": "official_sglang_rotary_embedding_forward_native_on_sm120",
        "semantics": "preserving",
        "causal_diff": (
            "Route only CUDA capability major 12 through the installed SGLang "
            "RotaryEmbedding.forward_native implementation before fused JIT selection."
        ),
        "production_fused_kv_arg": None,
        "production_fused_kv_source_proof": (
            "gemma4_causal.py sets can_fuse=False and passes fused_arg=None"
        ),
        "pre_patch_source_identities": pre,
        "post_patch_source_identities": post,
    },
    "compiler": {
        "package": "nvidia-cuda-nvcc",
        "package_version": metadata.version("nvidia-cuda-nvcc"),
        "actual_recorded_binary": str(NVCC_ACTUAL),
        "actual_recorded_binary_sha256": sha256(NVCC_ACTUAL),
        "owner_compatibility_symlink": str(NVCC_COMPAT),
        "owner_compatibility_symlink_target": os.readlink(NVCC_COMPAT),
        "compile_command": None,
        "compile_bypassed_by_official_source_fallback": True,
        "prior_failed_command": (
            "/usr/local/cuda/bin/nvcc -gencode=arch=compute_120f,code=sm_120f "
            "... sglang fused_rope cuda.cu"
        ),
    },
    "runtime": {
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "sglang": metadata.version("sglang"),
        "sglang_kernel": metadata.version("sglang-kernel"),
        "device": torch.cuda.get_device_name(0),
        "compute_capability": list(torch.cuda.get_device_capability(0)),
    },
    "production_shape_oracle": {
        "phase": "chunked_prefill",
        "tokens": tokens,
        "dtype": "torch.bfloat16",
        "head_size": head_size,
        "q_heads": q_heads,
        "kv_heads": kv_heads,
        "is_neox_style": True,
        "rope_dim": head_size,
        "base": 10000,
        "query": q_oracle,
        "key": k_oracle,
        "envelope": envelope,
        "passed": passed,
        "consumer": (
            "sglang.srt.layers.rotary_embedding.base.RotaryEmbedding.__call__"
        ),
        "reference": "installed SGLang RotaryEmbedding.forward_native",
    },
}
atomic_json(REMOTE_RESULT, result)
print(json.dumps(result, sort_keys=True))
