from __future__ import annotations

import os
import pathlib
import threading


_LOCK = threading.Lock()
_EXTENSION = None


def _load_extension():
    global _EXTENSION
    if _EXTENSION is not None:
        return _EXTENSION
    with _LOCK:
        if _EXTENSION is not None:
            return _EXTENSION
        from torch.utils.cpp_extension import load

        os.environ["TORCH_CUDA_ARCH_LIST"] = "9.0a"
        os.environ.setdefault("MAX_JOBS", "4")
        source = pathlib.Path(__file__).with_name("norm_fp8_decode.cu")
        _EXTENSION = load(
            name="gemma4_h200_decode_norm_fp8_sm90a",
            sources=[str(source)],
            extra_cflags=["-O3"],
            extra_cuda_cflags=[
                "-O3",
                "--expt-relaxed-constexpr",
                "-lineinfo",
            ],
            with_cuda=True,
            verbose=os.environ.get("NORM_FP8_BUILD_VERBOSE") == "1",
        )
    return _EXTENSION


def prepare() -> None:
    _load_extension()


def gemma4_decode_norm_fp8(input_tensor, weight, epsilon):
    return _load_extension().gemma4_decode_norm_fp8(
        input_tensor, weight, epsilon
    )
