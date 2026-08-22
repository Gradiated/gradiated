from __future__ import annotations

import os
import pathlib
import threading


_LOCK = threading.Lock()
_EXTENSION = None


def prepare() -> None:
    _extension()


def fused_gelu_mul_dynamic_fp8(gate_up):
    return _extension().fused_gelu_mul_dynamic_fp8(gate_up)


def _extension():
    global _EXTENSION
    if _EXTENSION is not None:
        return _EXTENSION
    with _LOCK:
        if _EXTENSION is not None:
            return _EXTENSION
        from torch.utils.cpp_extension import load

        source = pathlib.Path(__file__).with_name(
            "fused_gelu_mul_dynamic_fp8_sm90.cu"
        )
        os.environ.setdefault("MAX_JOBS", "4")
        _EXTENSION = load(
            name="gemma4_gelu_mul_dynamic_fp8_sm90",
            sources=[str(source)],
            extra_cflags=["-O3"],
            extra_cuda_cflags=[
                "-O3",
                "-gencode=arch=compute_90,code=sm_90",
            ],
            with_cuda=True,
            verbose=os.environ.get("FUSION_BUILD_VERBOSE") == "1",
        )
        return _EXTENSION
