#!/usr/bin/env python3
"""Compile the exact grouped kernel for SM90 without requiring a GPU."""

from __future__ import annotations

import json

import triton
from triton.compiler.compiler import ASTSource, GPUTarget

from grouped_lm_head import BATCH, BLOCK_K, BLOCK_N, DEPTHS, HIDDEN, VOCAB
from grouped_lm_head import _triton_symbols


def main() -> None:
    _, kernel = _triton_symbols()
    constants = {
        "hidden_row_stride": HIDDEN,
        "weight_vocab_stride": HIDDEN,
        "output_row_stride": VOCAB,
        "depths": DEPTHS,
        "batch": BATCH,
        "hidden": HIDDEN,
        "vocab": VOCAB,
        "block_n": BLOCK_N,
        "block_k": BLOCK_K,
    }
    signature = {
        "hidden_ptr": "*bf16",
        "weight_ptr": "*bf16",
        "output_ptr": "*bf16",
        **{name: "i32" for name in constants},
    }
    source = ASTSource(kernel, signature, constexprs=constants)
    compiled = triton.compile(
        source,
        target=GPUTarget("cuda", 90, 32),
        options={"num_warps": 8, "num_stages": 3},
    )
    metadata = {
        key: value
        for key, value in compiled.metadata._asdict().items()
        if isinstance(value, (str, int, float, bool, type(None)))
    }
    print(json.dumps({"name": compiled.name, "metadata": metadata}, sort_keys=True))


if __name__ == "__main__":
    main()
