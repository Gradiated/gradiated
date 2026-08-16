from __future__ import annotations

import os
import pathlib
import threading


_LOCK = threading.Lock()
_EXTENSION = None
_PLAIN_INVOCATIONS = 0
_RESIDUAL_INVOCATIONS = 0


def _load_extension():
    global _EXTENSION
    if _EXTENSION is not None:
        return _EXTENSION
    with _LOCK:
        if _EXTENSION is not None:
            return _EXTENSION
        from torch.utils.cpp_extension import load

        source = pathlib.Path(__file__).with_name("fused_rmsnorm_quant.cu")
        os.environ.setdefault("MAX_JOBS", "4")
        _EXTENSION = load(
            name="gemma4_fused_rmsnorm_quant_sm90",
            sources=[str(source)],
            extra_cflags=["-O3"],
            extra_cuda_cflags=["-O3", "--expt-relaxed-constexpr"],
            with_cuda=True,
            verbose=os.environ.get("RMS_FP8_BUILD_VERBOSE") == "1",
        )
    return _EXTENSION


def rmsnorm_quant(input_tensor, weight, epsilon):
    global _PLAIN_INVOCATIONS
    result = _load_extension().rmsnorm_quant(input_tensor, weight, epsilon)
    _PLAIN_INVOCATIONS += 1
    return result


def fused_add_rmsnorm_quant(input_tensor, residual, weight, epsilon):
    global _RESIDUAL_INVOCATIONS
    result = _load_extension().fused_add_rmsnorm_quant(
        input_tensor, residual, weight, epsilon
    )
    _RESIDUAL_INVOCATIONS += 1
    return result


def prepare() -> None:
    _load_extension()


def invocation_counts() -> dict[str, int]:
    return {
        "plain": _PLAIN_INVOCATIONS,
        "residual": _RESIDUAL_INVOCATIONS,
    }
