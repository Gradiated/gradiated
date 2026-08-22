#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata as metadata
import json
import os
import tempfile
from pathlib import Path


SITE = Path("/usr/local/lib/python3.12/dist-packages")
CLAMP = SITE / "sglang/jit_kernel/clamp_position.py"
ACTIVATION = SITE / "sglang/srt/layers/activation.py"
REMOTE_RESULT = Path(
    "/workspace/gemma4-rtxpro6000-fp8-endpoint-20260729t0338z/"
    "SM120_CLAMP_POSITION_SOURCE_FALLBACK.remote.json"
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


clamp_before = CLAMP.read_text()
needle = """def clamp_position_cuda(seq_lens: torch.Tensor) -> torch.Tensor:
    \"\"\"Compute positions = clamp(seq_lens - 1, min=0) on CUDA.

    Supported dtypes: torch.int32, torch.int64.
    \"\"\"
    dst = torch.empty_like(seq_lens)
"""
replacement = """def clamp_position_cuda(seq_lens: torch.Tensor) -> torch.Tensor:
    \"\"\"Compute positions = clamp(seq_lens - 1, min=0) on CUDA.

    Supported dtypes: torch.int32, torch.int64.
    \"\"\"
    if torch.cuda.get_device_capability(seq_lens.device)[0] == 12:
        return torch.clamp(seq_lens - 1, min=0)
    dst = torch.empty_like(seq_lens)
"""
backup = CLAMP.with_suffix(".py.sm120-torch-fallback.pre")
if replacement not in clamp_before:
    if needle not in clamp_before:
        raise RuntimeError("clamp_position_patch_point_missing")
    if not backup.exists():
        atomic_text(backup, clamp_before)
    atomic_text(CLAMP, clamp_before.replace(needle, replacement, 1))
if not backup.is_file():
    raise RuntimeError("clamp_position_backup_missing")

nvrtc_dir = str(SITE / "nvidia/cu13/lib")
os.environ["LD_LIBRARY_PATH"] = (
    f"{nvrtc_dir}:{os.environ.get('LD_LIBRARY_PATH', '')}"
)

import torch
import sglang.jit_kernel.clamp_position as clamp_module


tripwire_calls = 0
original_jit = clamp_module._jit_clamp_position_module


def forbidden_jit(*args, **kwargs):
    global tripwire_calls
    tripwire_calls += 1
    raise RuntimeError("sm120_clamp_position_jit_tripwire")


clamp_module._jit_clamp_position_module = forbidden_jit
values = [
    0,
    1,
    2,
    4214,
    4215,
    4571,
    4572,
    5000,
] * 4
seq_lens = torch.tensor(values, device="cuda", dtype=torch.int64)
candidate = clamp_module.clamp_position_cuda(seq_lens)
torch.cuda.synchronize()
clamp_module._jit_clamp_position_module = original_jit
reference = torch.clamp(seq_lens - 1, min=0)
passed = (
    tripwire_calls == 0
    and candidate.dtype == torch.int64
    and list(candidate.shape) == [32]
    and list(candidate.stride()) == list(reference.stride())
    and torch.equal(candidate, reference)
)
if not passed:
    raise RuntimeError("sm120_clamp_position_source_fallback_failed")

result = {
    "schema_version": 1,
    "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "classification": "exact_installed_source_sm120_clamp_position_fallback_pass",
    "repair_id": "repair-1785301035",
    "science_started": False,
    "science_consumed": False,
    "http_submitted": False,
    "mechanism": {
        "selected": "torch_clamp_seq_lens_minus_one_on_sm120",
        "semantics": "preserving",
        "source_level_diff": (
            "@@ clamp_position_cuda\n"
            "+    if torch.cuda.get_device_capability(seq_lens.device)[0] == 12:\n"
            "+        return torch.clamp(seq_lens - 1, min=0)"
        ),
        "pre_source_sha256": sha256(backup),
        "post_source_sha256": sha256(CLAMP),
        "source_path": str(CLAMP),
        "jit_tripwire_calls": tripwire_calls,
    },
    "settled_dependency": {
        "activation_source_sha256": sha256(ACTIVATION),
        "expected_activation_source_sha256": (
            "5d2e8a2ec0bd0bbdfa4732633144f3c287914d5d04a5a54142c9c4b04c5109d7"
        ),
    },
    "runtime": {
        "device": torch.cuda.get_device_name(0),
        "compute_capability": list(torch.cuda.get_device_capability(0)),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "sglang": metadata.version("sglang"),
    },
    "production_shape_oracle": {
        "consumer": "sglang.jit_kernel.clamp_position.clamp_position_cuda",
        "downstream_consumer": "ForwardBatch.init_new decode/target position initialization",
        "dtype": str(seq_lens.dtype),
        "shape": list(seq_lens.shape),
        "stride": list(seq_lens.stride()),
        "input_values": values,
        "output_values": candidate.tolist(),
        "reference": "torch.clamp(seq_lens - 1, min=0)",
        "exact_equal": bool(torch.equal(candidate, reference)),
        "passed": passed,
    },
}
if (
    result["settled_dependency"]["activation_source_sha256"]
    != result["settled_dependency"]["expected_activation_source_sha256"]
):
    raise RuntimeError("settled_activation_source_identity_changed")
atomic_json(REMOTE_RESULT, result)
print(json.dumps(result, sort_keys=True))
