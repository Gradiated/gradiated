from __future__ import annotations

import os

from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CUDAExtension


os.environ["TORCH_CUDA_ARCH_LIST"] = "8.9"

NVCC_FLAGS = [
    "-O3",
    "-std=c++17",
    "--use_fast_math",
    "--expt-relaxed-constexpr",
    "--expt-extended-lambda",
    "-lineinfo",
    "--ptxas-options=-v",
    "-U__CUDA_NO_HALF_OPERATORS__",
    "-U__CUDA_NO_HALF_CONVERSIONS__",
    "-U__CUDA_NO_BFLOAT16_OPERATORS__",
    "-U__CUDA_NO_BFLOAT16_CONVERSIONS__",
]

setup(
    name="qserve_sm89",
    ext_modules=[
        CUDAExtension(
            name="qserve_sm89",
            sources=[
                "bindings.cpp",
                "qserve_w4a8_gemm.cu",
                "activation_quant.cu",
            ],
            extra_compile_args={
                "cxx": ["-O3", "-std=c++17"],
                "nvcc": NVCC_FLAGS,
            },
        )
    ],
    cmdclass={"build_ext": BuildExtension},
)
