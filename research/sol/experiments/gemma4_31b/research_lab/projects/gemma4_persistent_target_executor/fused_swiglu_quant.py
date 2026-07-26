from __future__ import annotations

import os
import pathlib
import threading


_extension = None
_lock = threading.Lock()
_invocations = 0


def _load():
    global _extension
    if _extension is not None:
        return _extension
    with _lock:
        if _extension is None:
            from torch.utils.cpp_extension import load

            source = pathlib.Path(__file__).with_name("fused_swiglu_quant.cu")
            os.environ.setdefault("MAX_JOBS", "4")
            _extension = load(
                name="gemma4_persistent_swiglu_quant_sm90",
                sources=[str(source)],
                extra_cflags=["-O3"],
                extra_cuda_cflags=["-O3", "--expt-relaxed-constexpr"],
                with_cuda=True,
                verbose=os.environ.get("BUILD_VERBOSE") == "1",
            )
    return _extension


def fused_swiglu_quant(gate_up):
    global _invocations
    result = _load().fused_swiglu_quant(gate_up)
    _invocations += 1
    return result


def prepare() -> None:
    _load()


def invocation_count() -> int:
    return _invocations
