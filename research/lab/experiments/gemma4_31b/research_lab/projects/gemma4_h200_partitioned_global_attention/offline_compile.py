#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import re
import tempfile
from typing import Any

import triton


POINTER_TYPES = {
    "Q_Extend": "*bf16",
    "K_Extend": "*bf16",
    "V_Extend": "*bf16",
    "O_Extend": "*bf16",
    "K_Buffer": "*fp8e5",
    "V_Buffer": "*fp8e5",
    "qo_indptr": "*i32",
    "kv_indptr": "*i32",
    "kv_indices": "*i64",
    "mask_ptr": "*i8",
    "mask_indptr": "*i32",
    "sink_ptr": "*fp32",
    "window_kv_offset_ptr": "*i32",
}

FLOAT_TYPES = {"sm_scale", "k_scale", "v_scale"}

COMMON_CONSTANTS: dict[str, Any] = {
    "SLIDING_WINDOW_SIZE": -1,
    "logit_cap": 0.0,
    "xai_temperature_len": -1,
    "Lq": 512,
    "Lv": 512,
    "BLOCK_DMODEL": 512,
    "BLOCK_DPE": 0,
    "BLOCK_DV": 512,
    "BLOCK_M": 32,
    "BLOCK_N": 64,
    "USE_CUSTOM_MASK": False,
    "IS_CAUSAL": True,
    "SKIP_PREFIX_CUSTOM_MASK": True,
    "STORE_TRANSPOSE": False,
    "HAS_SINK": False,
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_kernel(path: pathlib.Path, temporary_root: pathlib.Path):
    tree = ast.parse(path.read_text())
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"tanh", "_fwd_kernel"}
    }
    if set(functions) != {"tanh", "_fwd_kernel"}:
        raise RuntimeError(f"kernel_extraction_failed:{sorted(functions)}")
    module_text = (
        "import triton\nimport triton.language as tl\n\n"
        + ast.unparse(functions["tanh"])
        + "\n\n"
        + ast.unparse(functions["_fwd_kernel"])
        + "\n"
    )
    module_path = temporary_root / f"kernel_{sha256(path)[:16]}.py"
    module_path.write_text(module_text)
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("kernel_module_spec_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._fwd_kernel


def compile_kernel(
    path: pathlib.Path,
    *,
    block_m: int,
    block_n: int,
    value_splits: int | None,
    maxnreg: int | None = None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="partitioned-attention-compile-") as raw_root:
        kernel = load_kernel(path, pathlib.Path(raw_root))
        constants = dict(COMMON_CONSTANTS)
        constants.update({"BLOCK_M": block_m, "BLOCK_N": block_n})
        if value_splits is not None:
            constants.update(
                {
                    "BLOCK_DV_SLICE": 512 // value_splits,
                    "VALUE_SPLITS": value_splits,
                }
            )
        signature = {}
        for name in kernel.arg_names:
            if name in constants:
                signature[name] = "constexpr"
            elif name in POINTER_TYPES:
                signature[name] = POINTER_TYPES[name]
            elif name in FLOAT_TYPES:
                signature[name] = "fp32"
            else:
                signature[name] = "i32"
        source = triton.compiler.ASTSource(
            fn=kernel,
            signature=signature,
            constexprs=constants,
            attrs={},
        )
        target = triton.backends.compiler.GPUTarget("cuda", 90, 32)
        backend = triton.compiler.make_backend(target)
        options = backend.parse_options(
            {"num_warps": 8, "num_stages": 1, "maxnreg": maxnreg}
        )
        os.environ["TRITON_ALWAYS_COMPILE"] = "1"
        os.environ["TRITON_DUMP_PTXAS_LOG"] = "1"
        ptxas_log = io.StringIO()
        with contextlib.redirect_stdout(ptxas_log):
            compiled = triton.compile(source, target=target, options=options.__dict__)
        metadata = compiled.metadata._asdict()
        register_match = re.search(r"Used (\d+) registers", ptxas_log.getvalue())
        if register_match is None:
            raise RuntimeError(f"ptxas_register_count_missing:{ptxas_log.getvalue()}")
        spill_match = re.search(
            r"(\d+) bytes stack frame, (\d+) bytes spill stores, (\d+) bytes spill loads",
            ptxas_log.getvalue(),
        )
        return {
            "source": str(path.resolve()),
            "source_sha256": sha256(path),
            "num_regs": int(register_match.group(1)),
            "shared": metadata.get("shared"),
            "num_warps": metadata.get("num_warps"),
            "num_stages": metadata.get("num_stages"),
            "name": metadata.get("name"),
            "geometry": {
                "block_m": block_m,
                "block_n": block_n,
                "value_splits": value_splits or 1,
                "value_slice": 512 // (value_splits or 1),
                "maxnreg": maxnreg,
            },
            "stack_frame_bytes": int(spill_match.group(1)) if spill_match else None,
            "spill_store_bytes": int(spill_match.group(2)) if spill_match else None,
            "spill_load_bytes": int(spill_match.group(3)) if spill_match else None,
            "target": {"backend": "cuda", "arch": 90, "warp_size": 32},
            "ptxas_log": ptxas_log.getvalue().strip().splitlines(),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=pathlib.Path, required=True)
    parser.add_argument("--candidate", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    control = compile_kernel(
        args.control, block_m=32, block_n=64, value_splits=None
    )
    variants = []
    for block_m, block_n, value_splits in (
        (32, 64, 2),
        (32, 64, 4),
        (32, 64, 8),
        (16, 64, 2),
        (16, 64, 4),
        (32, 32, 2),
        (16, 32, 2),
        (16, 32, 4),
        (16, 32, 8),
        (8, 32, 4),
        (8, 32, 8),
    ):
        variants.append(
            compile_kernel(
                args.candidate,
                block_m=block_m,
                block_n=block_n,
                value_splits=value_splits,
            )
        )
    forced_residency_variants = [
        compile_kernel(
            args.control,
            block_m=32,
            block_n=64,
            value_splits=None,
            maxnreg=128,
        ),
        compile_kernel(
            args.candidate,
            block_m=32,
            block_n=64,
            value_splits=2,
            maxnreg=128,
        ),
        compile_kernel(
            args.candidate,
            block_m=32,
            block_n=64,
            value_splits=4,
            maxnreg=128,
        ),
    ]
    output = {
        "schema_version": 1,
        "evidence_type": "derived_offline_triton_3_7_1_sm90_compile_proxy",
        "warning": "Compiler metadata is a geometry discriminator, not transferable target-runtime evidence.",
        "triton_version": triton.__version__,
        "shape": {
            "query_tokens": 2048,
            "q_heads": 32,
            "kv_heads": 4,
            "qk_head_dim": 512,
            "v_head_dim": 512,
            "block_m": 32,
            "block_n": 64,
        },
        "control": control,
        "candidates": variants,
        "forced_residency_candidates": forced_residency_variants,
    }
    output["residency_candidates"] = [
        row for row in variants if row["num_regs"] <= 128
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
