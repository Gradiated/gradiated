from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import re
import subprocess
import tempfile

import triton
from triton.compiler.compiler import ASTSource, GPUTarget


PROJECT = pathlib.Path(__file__).resolve().parent


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SIGNATURE = {
    "Q_Extend": "*bf16",
    "K_Extend": "*bf16",
    "V_Extend": "*bf16",
    "O_Extend": "*bf16",
    "K_Buffer": "*fp8e5",
    "V_Buffer": "*fp8e5",
    "qo_indptr": "*i32",
    "kv_indptr": "*i32",
    "kv_indices": "*i64",
    "mask_ptr": "*i1",
    "mask_indptr": "*i32",
    "sink_ptr": "*fp32",
    "window_kv_offset_ptr": "*i32",
    "sm_scale": "fp32",
    "k_scale": "fp32",
    "v_scale": "fp32",
    "kv_group_num": "i32",
    "stride_qbs": "i64",
    "stride_qh": "i64",
    "stride_kbs": "i64",
    "stride_kh": "i64",
    "stride_vbs": "i64",
    "stride_vh": "i64",
    "stride_obs": "i64",
    "stride_oh": "i64",
    "stride_buf_kbs": "i64",
    "stride_buf_kh": "i64",
    "stride_buf_vbs": "i64",
    "stride_buf_vh": "i64",
}

COMMON_CONSTANTS = {
    "SLIDING_WINDOW_SIZE": 1024,
    "logit_cap": 0.0,
    "xai_temperature_len": -1,
    "Lq": 256,
    "Lv": 256,
    "BLOCK_DMODEL": 256,
    "BLOCK_DPE": 0,
    "BLOCK_M": 64,
    "BLOCK_N": 64,
    "USE_CUSTOM_MASK": True,
    "IS_CAUSAL": True,
    "SKIP_PREFIX_CUSTOM_MASK": True,
    "STORE_TRANSPOSE": False,
    "HAS_SINK": False,
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def resource_usage(cubin: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".cubin") as handle:
        handle.write(cubin)
        handle.flush()
        result = subprocess.run(
            ["cuobjdump", "--dump-resource-usage", handle.name],
            check=True,
            capture_output=True,
            text=True,
        )
    return result.stdout


def compile_one(label: str, source_path: pathlib.Path, constants: dict) -> dict:
    module = load_module(source_path, f"stock_order_compile_{label}")
    compiled = triton.compile(
        ASTSource(module._fwd_kernel, SIGNATURE, constants),
        target=GPUTarget("cuda", 90, 32),
        options={"num_warps": 8, "num_stages": 1},
    )
    cubin = compiled.asm["cubin"]
    ptx = compiled.asm["ptx"]
    ttgir = compiled.asm["ttgir"]
    usage = resource_usage(cubin)
    registers = [
        int(value)
        for value in re.findall(r"REG:(\d+)", usage)
    ]
    shared_bytes = [
        int(value)
        for value in re.findall(r"SHARED:(\d+)", usage)
    ]
    dot_lines = [
        line.strip()
        for line in ttgir.splitlines()
        if "dot" in line.lower() or "mma" in line.lower()
    ]
    return {
        "label": label,
        "source": str(source_path.relative_to(PROJECT)),
        "source_sha256": sha256_bytes(source_path.read_bytes()),
        "compiled_name": compiled.name,
        "metadata": {
            key: value
            for key, value in compiled.metadata._asdict().items()
            if isinstance(value, (str, int, float, bool, type(None)))
        },
        "resource_usage": usage,
        "maximum_registers_per_thread": max(registers) if registers else None,
        "maximum_static_shared_bytes": max(shared_bytes) if shared_bytes else None,
        "cubin_sha256": sha256_bytes(cubin),
        "ptx_sha256": sha256_bytes(ptx.encode()),
        "ttgir_sha256": sha256_bytes(ttgir.encode()),
        "dot_lowering_lines": dot_lines,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    stock = compile_one(
        "stock_m64_n64_dv256",
        PROJECT / "inputs/upstream/extend_attention.py",
        {**COMMON_CONSTANTS, "BLOCK_DV": 256},
    )
    rejected_m8 = compile_one(
        "rejected_m8_n64_dv256",
        PROJECT / "intervention/extend_attention_fixed_m384.py",
        {**COMMON_CONSTANTS, "BLOCK_DV": 256, "BLOCK_M": 8},
    )
    candidate = compile_one(
        "stock_order_m64_n64_dv64x4",
        PROJECT / "intervention/extend_attention_stock_order_dv64.py",
        {**COMMON_CONSTANTS, "BLOCK_DV": 64, "VALUE_SPLITS": 4},
    )
    result = {
        "schema_version": 1,
        "kind": "offline_triton_3_6_sm90_stock_order_value_stripe_compile",
        "triton": triton.__version__,
        "target": "cuda-sm90-warp32",
        "stock": stock,
        "rejected_m8": rejected_m8,
        "candidate": candidate,
        "register_change": (
            None
            if stock["maximum_registers_per_thread"] is None
            or candidate["maximum_registers_per_thread"] is None
            else candidate["maximum_registers_per_thread"]
            - stock["maximum_registers_per_thread"]
        ),
        "static_shared_change_bytes": (
            None
            if stock["maximum_static_shared_bytes"] is None
            or candidate["maximum_static_shared_bytes"] is None
            else candidate["maximum_static_shared_bytes"]
            - stock["maximum_static_shared_bytes"]
        ),
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
