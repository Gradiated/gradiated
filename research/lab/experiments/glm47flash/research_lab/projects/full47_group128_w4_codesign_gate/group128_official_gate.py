#!/usr/bin/env python3
"""Offline official uint4b8 group-128 representation and runtime gate."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import struct
from pathlib import Path

import torch
from safetensors import safe_open
from compressed_tensors.compressors.quantized_compressors.pack_quantized import (
    pack_to_int32,
    unpack_from_int32,
)
from vllm.model_executor.layers.linear import LinearBase
from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead
from vllm.model_executor.layers.fused_moe.layer import FusedMoE
from vllm.model_executor.layers.quantization.compressed_tensors.compressed_tensors import (
    CompressedTensorsConfig,
)


ROOT = Path("/model")
OUT = Path("/out/GROUP128_OFFICIAL_GATE.json")
LIMIT_MIB = 44532.0
STOCK_PEAK_MIB = 46875.7


def nbytes(shape: list[int], dtype: str) -> int:
    sizes = {"BF16": 2, "F16": 2, "F32": 4, "I64": 8, "I32": 4}
    return math.prod(shape) * sizes[dtype]


def tensor(root: Path, index: dict, name: str, rows: int | None = None) -> torch.Tensor:
    with safe_open(str(root / index["weight_map"][name]), framework="pt", device="cpu") as f:
        if rows is None:
            return f.get_tensor(name)
        view = f.get_slice(name)
        return view if len(view.get_shape()) < 2 else view[:rows]


def headers(root: Path, index: dict) -> dict:
    result = {}
    for shard in sorted(set(index["weight_map"].values())):
        with (root / shard).open("rb") as f:
            size = struct.unpack("<Q", f.read(8))[0]
            result.update(json.loads(f.read(size)))
    return result


def select(index: dict, suffix: str) -> str:
    names = sorted(index["weight_map"])
    for name in names:
        if suffix in name:
            return name
    raise RuntimeError(f"missing preregistered tensor family: {suffix}")


def quantize128(weight: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    rows, cols = weight.shape
    if cols % 128:
        raise RuntimeError(f"group128 illegal columns: {list(weight.shape)}")
    grouped = weight.float().reshape(rows, cols // 128, 128)
    scale = grouped.abs().amax(dim=-1).div(7).clamp_min(torch.finfo(torch.float32).tiny)
    raw_q = torch.round(grouped / scale.unsqueeze(-1))
    q = raw_q.clamp(-8, 7).to(torch.int8).reshape(rows, cols)
    packed = pack_to_int32(q, 4)
    restored = unpack_from_int32(packed, 4, torch.Size([rows, cols]))
    depacked = (restored.float().reshape(rows, cols // 128, 128) * scale.unsqueeze(-1)).reshape(rows, cols)
    return packed, scale.to(torch.bfloat16), depacked, int(((raw_q < -8) | (raw_q > 7)).sum().item())


def sample(index: dict, label: str, source_name: str, source_kind: str) -> dict:
    prefix = source_name.removesuffix(".weight")
    if source_kind == "group32":
        packed = tensor(ROOT, index, prefix + ".weight_packed", 128)
        scale = tensor(ROOT, index, prefix + ".weight_scale", 128)
        shape = tensor(ROOT, index, prefix + ".weight_shape")
        shape = shape.clone(); shape[0] = packed.shape[0]
        q = unpack_from_int32(packed, 4, torch.Size(shape.tolist()))
        reference = (q.float().reshape(*scale.shape, 32) * scale.float().unsqueeze(-1)).reshape(*shape.tolist())
    else:
        reference = tensor(ROOT, index, source_name, 128).float()
    packed128, scale128, restored, saturation = quantize128(reference)
    q128 = unpack_from_int32(packed128, 4, reference.shape)
    repacked = pack_to_int32(q128, 4)
    err = restored - reference
    return {
        "family": label,
        "source": source_name,
        "source_kind": source_kind,
        "shape": list(reference.shape),
        "relative_l2": float(torch.linalg.vector_norm(err) / torch.linalg.vector_norm(reference).clamp_min(1e-30)),
        "max_abs_error": float(err.abs().max()),
        "saturation_count": saturation,
        "saturation_fraction": saturation / reference.numel(),
        "packed_shape": list(packed128.shape),
        "scale_shape": list(scale128.shape),
        "official_pack_roundtrip_exact": bool(torch.equal(packed128, repacked)),
        "packed_sha256": hashlib.sha256(packed128.numpy().tobytes()).hexdigest(),
    }


def main() -> None:
    config = json.loads((ROOT / "config.json").read_text())
    index = json.loads((ROOT / "model.safetensors.index.json").read_text())
    wm = index["weight_map"]
    header = headers(ROOT, index)
    group32 = sorted(n.removesuffix(".weight_packed") for n in wm if n.endswith(".weight_packed"))
    converted_bf16 = sorted(n for n in wm if n.endswith(".weight") and (n == "lm_head.weight" or (".mlp.shared_experts." in n and ".layers.47." not in n)))
    if len(converted_bf16) != 139:
        raise RuntimeError(f"expected 139 serving head/shared BF16 tensors, got {len(converted_bf16)}")

    samples = [
        ("routed_gate", select(index, ".mlp.experts.0.gate_proj.weight_packed").removesuffix("_packed"), "group32"),
        ("routed_up", select(index, ".mlp.experts.0.up_proj.weight_packed").removesuffix("_packed"), "group32"),
        ("routed_down", select(index, ".mlp.experts.0.down_proj.weight_packed").removesuffix("_packed"), "group32"),
        ("ordinary_attention", select(index, ".self_attn.q_a_proj.weight_packed").removesuffix("_packed"), "group32"),
        ("ordinary_linear", select(index, ".self_attn.kv_b_proj.weight_packed").removesuffix("_packed"), "group32"),
        ("lm_head", "lm_head.weight", "bf16"),
        ("shared_expert", select(index, ".mlp.shared_experts.gate_proj.weight"), "bf16"),
    ]
    results = [sample(index, *x) for x in samples]

    original_payload = sum(int(item["data_offsets"][1]) - int(item["data_offsets"][0]) for name, item in header.items() if name != "__metadata__")
    final_payload = original_payload
    existing_scale_before = existing_scale_after = 0
    for name in wm:
        item = header[name]
        key_bytes = int(item["data_offsets"][1]) - int(item["data_offsets"][0])
        if name.endswith(".weight_scale") and name.removesuffix(".weight_scale") in group32:
            existing_scale_before += key_bytes
            after = key_bytes // 4
            existing_scale_after += after
            final_payload += after - key_bytes
    added_before = added_after = 0
    for name in converted_bf16:
        rows, cols = header[name]["shape"]
        old = int(header[name]["data_offsets"][1]) - int(header[name]["data_offsets"][0])
        new = rows * (cols // 8) * 4 + rows * (cols // 128) * 2 + 16
        added_before += old
        added_after += new
        final_payload += new - old
    saving = original_payload - final_payload
    peak = STOCK_PEAK_MIB - saving / 2**20
    margin = LIMIT_MIB - peak

    qcfg = copy.deepcopy(config["quantization_config"])
    base = qcfg["config_groups"]["group_0"]
    group128 = copy.deepcopy(base)
    group128["targets"] = ["Linear"]
    group128["weights"]["group_size"] = 128
    head128 = copy.deepcopy(group128)
    head128["targets"] = ["ParallelLMHead"]
    qcfg["config_groups"] = {"group128_linear": group128, "group128_head": head128}
    ct = CompressedTensorsConfig.from_config(qcfg)
    linear, head, moe = object.__new__(LinearBase), object.__new__(ParallelLMHead), object.__new__(FusedMoE)
    moe.hidden_size = 2048
    moe.intermediate_size_per_partition = 1536
    moe.apply_router_weight_on_input = False
    moe.moe_config = None
    dispatch = {
        "ordinary_linear": type(ct.get_quant_method(linear, "model.layers.1.self_attn.q_a_proj")).__name__ if ct.get_quant_method(linear, "model.layers.1.self_attn.q_a_proj") else None,
        "parallel_lm_head": type(ct.get_quant_method(head, "lm_head")).__name__ if ct.get_quant_method(head, "lm_head") else None,
        "fused_moe": type(ct.get_quant_method(moe, "model.layers.1.mlp.experts")).__name__ if ct.get_quant_method(moe, "model.layers.1.mlp.experts") else None,
        "config_group_size": 128,
    }
    numerical_pass = all(r["relative_l2"] <= .10 and r["saturation_count"] == 0 and r["official_pack_roundtrip_exact"] for r in results)
    native_pass = dispatch["ordinary_linear"] == "CompressedTensorsLinearMethod" and dispatch["parallel_lm_head"] == "CompressedTensorsLinearMethod" and dispatch["fused_moe"] == "CompressedTensorsMoEMethod"
    memory_pass = margin >= 64.0
    decision = "NOMINATE_GROUP128_COMBINED" if numerical_pass and native_pass and memory_pass else "RUNTIME_CLOSE_GROUP128_COMBINED" if not native_pass else "NUMERICAL_CLOSE_GROUP128_COMBINED" if not numerical_pass else "MEMORY_CLOSE_GROUP128_COMBINED"
    payload = {"decision": decision, "terminal": True, "checkpoint": str(ROOT), "representation": "official compressed_tensors.pack_to_int32 uint4b8", "samples": results, "numerical_pass": numerical_pass, "dispatch": dispatch, "native_dispatch_pass": native_pass, "payload": {"original_bytes": original_payload, "final_bytes": final_payload, "saving_bytes": saving, "saving_mib": saving / 2**20, "existing_group32_scale_bytes": existing_scale_before, "existing_group128_scale_bytes": existing_scale_after, "head_shared_bf16_bytes": added_before, "head_shared_group128_bytes": added_after, "mandatory_duplicate_or_repack_bytes": 0}, "memory": {"projected_c32_peak_mib": peak, "robust_limit_mib": LIMIT_MIB, "robust_margin_mib": margin, "minimum_margin_mib": 64.0, "pass": memory_pass}, "runtime_note": "Pinned get_quant_method only recognizes LinearBase; ParallelLMHead remains unbound without a source change, which this gate forbids."}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"artifact": str(OUT), "decision": decision, "native_dispatch": dispatch, "margin_mib": margin}))


if __name__ == "__main__":
    main()
