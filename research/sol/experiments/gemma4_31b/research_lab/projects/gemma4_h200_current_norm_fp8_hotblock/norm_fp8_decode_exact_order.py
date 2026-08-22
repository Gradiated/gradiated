from __future__ import annotations

import os
import pathlib
import threading
import importlib.util


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
        source = pathlib.Path(__file__).with_name(
            "norm_fp8_decode_exact_order.cu"
        )
        flashinfer_spec = importlib.util.find_spec("flashinfer")
        if (
            flashinfer_spec is None
            or flashinfer_spec.submodule_search_locations is None
        ):
            raise RuntimeError("flashinfer package is required")
        flashinfer_root = pathlib.Path(
            next(iter(flashinfer_spec.submodule_search_locations))
        )
        flashinfer_include = flashinfer_root / "data" / "include"
        if not flashinfer_include.is_dir():
            raise RuntimeError(
                f"flashinfer include directory missing: {flashinfer_include}"
            )
        _EXTENSION = load(
            name="gemma4_h200_decode_norm_fp8_exact_order_sm90a",
            sources=[str(source)],
            extra_include_paths=[str(flashinfer_include)],
            extra_cflags=["-O3"],
            extra_cuda_cflags=[
                "-O3",
                "--expt-relaxed-constexpr",
                "-lineinfo",
                "--ptxas-options=-v",
            ],
            with_cuda=True,
            verbose=os.environ.get("NORM_FP8_BUILD_VERBOSE") == "1",
        )
    return _EXTENSION


def prepare() -> None:
    _load_extension()


def gemma4_decode_norm_fp8_exact_order(input_tensor, weight, epsilon):
    return _load_extension().gemma4_decode_norm_fp8_exact_order(
        input_tensor, weight, epsilon
    )
