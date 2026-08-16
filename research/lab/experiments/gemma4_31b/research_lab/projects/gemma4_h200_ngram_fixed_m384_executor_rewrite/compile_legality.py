from __future__ import annotations

import json

import triton
import triton.language as tl
from triton.compiler.compiler import ASTSource, GPUTarget


@triton.jit
def m8_dot_probe(output):
    lhs = tl.zeros((8, 256), tl.float16)
    rhs = tl.zeros((256, 64), tl.float16)
    value = tl.dot(lhs, rhs, out_dtype=tl.float32)
    tl.store(output, tl.sum(value))


def main() -> None:
    source = ASTSource(m8_dot_probe, {"output": "*fp32"})
    compiled = triton.compile(
        source,
        target=GPUTarget("cuda", 90, 32),
        options={"num_warps": 8, "num_stages": 1},
    )
    print(
        json.dumps(
            {
                "name": compiled.name,
                "metadata": {
                    key: value
                    for key, value in compiled.metadata._asdict().items()
                    if isinstance(value, (str, int, float, bool, type(None)))
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
