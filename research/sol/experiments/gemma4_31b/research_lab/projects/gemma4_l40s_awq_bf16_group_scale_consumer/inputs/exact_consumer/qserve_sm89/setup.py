from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CUDAExtension


setup(
    name="exact_awq_sm89",
    ext_modules=[
        CUDAExtension(
            "exact_awq_sm89",
            [
                "bindings.cpp",
                "activation_quant.cu",
                "exact_awq_w4a8_gemm.cu",
            ],
            extra_compile_args={
                "cxx": ["-O3"],
                "nvcc": [
                    "-O3",
                    "--use_fast_math",
                    "--ptxas-options=-v",
                    "-lineinfo",
                    "-gencode=arch=compute_89,code=sm_89",
                ],
            },
        )
    ],
    cmdclass={"build_ext": BuildExtension},
)
