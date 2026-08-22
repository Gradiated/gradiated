from __future__ import annotations

import os
import pathlib
import threading


_LOCK = threading.Lock()
_EXTENSION = None
_INVOCATIONS = 0


def _load_extension():
    global _EXTENSION
    if _EXTENSION is not None:
        return _EXTENSION
    with _LOCK:
        if _EXTENSION is not None:
            return _EXTENSION
        from torch.utils.cpp_extension import load

        source = pathlib.Path(__file__).with_name(
            "gated_activation_fp8_decode.cu"
        )
        os.environ.setdefault("MAX_JOBS", "4")
        os.environ.setdefault("TORCH_CUDA_ARCH_LIST", "9.0a")
        _EXTENSION = load(
            name="gemma4_gated_activation_fp8_decode_sm90a",
            sources=[str(source)],
            extra_cflags=["-O3"],
            extra_cuda_cflags=[
                "-O3",
                "--expt-relaxed-constexpr",
                "-gencode=arch=compute_90a,code=sm_90a",
            ],
            with_cuda=True,
            verbose=os.environ.get("GATED_ACTIVATION_FP8_BUILD_VERBOSE") == "1",
        )
    return _EXTENSION


def gemma4_gated_activation_quant_e4m3(gate_up):
    global _INVOCATIONS
    result = _load_extension().gemma4_gated_activation_quant_e4m3(gate_up)
    _INVOCATIONS += 1
    return result


def prepare() -> None:
    _load_extension()


def invocation_count() -> int:
    return _INVOCATIONS
