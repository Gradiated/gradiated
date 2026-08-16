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

        source = pathlib.Path(__file__).with_name("fused_gelu_quant.cu")
        os.environ.setdefault("MAX_JOBS", "4")
        _EXTENSION = load(
            name="gemma4_fused_gelu_quant_sm90",
            sources=[str(source)],
            extra_cflags=["-O3"],
            extra_cuda_cflags=["-O3", "--expt-relaxed-constexpr"],
            with_cuda=True,
            verbose=os.environ.get("FUSION_BUILD_VERBOSE") == "1",
        )
    return _EXTENSION


def fused_gelu_tanh_mul_quant(input_tensor):
    global _INVOCATIONS
    result = _load_extension().fused_gelu_tanh_mul_quant(input_tensor)
    _INVOCATIONS += 1
    return result


def prepare() -> None:
    _load_extension()


def invocation_count() -> int:
    return _INVOCATIONS
