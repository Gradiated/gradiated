"""Offline, header-bound channelwise W4 representation and endpoint gate."""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path

ROOT = Path("/root/.cache/glm47flash-awq-ab31d120")
PROJECT = Path(__file__).parent
OUT = PROJECT / "CHANNELWISE_W4_GATE.json"
TARGET = 606.355


def headers(path: Path) -> dict:
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        return json.loads(f.read(n))


def all_headers(index: dict) -> dict:
    out = {}
    for shard in sorted(set(index["weight_map"].values())):
        h = headers(ROOT / shard)
        for name, meta in h.items():
            if name != "__metadata__":
                out[name] = {**meta, "shard": shard}
    return out


def payload_bytes(meta: dict) -> int:
    return meta["data_offsets"][1] - meta["data_offsets"][0]


def read_tensor(name: str, meta: dict) -> bytes:
    with (ROOT / meta["shard"]).open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        f.seek(8 + n + meta["data_offsets"][0])
        return f.read(payload_bytes(meta))


def fixture(names: dict) -> dict:
    # One real routed-expert gate projection, streamed row-wise.  The source
    # representation is INT32 packed uint4 plus BF16 group scales.
    prefix = "model.layers.1.mlp.experts.0.gate_proj"
    packed, scales, shape = (names[f"{prefix}.{s}"] for s in ("weight_packed", "weight_scale", "weight_shape"))
    rows, cols = struct.unpack("<qq", read_tensor(f"{prefix}.weight_shape", shape))
    p = read_tensor(f"{prefix}.weight_packed", packed)
    sb = read_tensor(f"{prefix}.weight_scale", scales)
    groups = cols // 32
    max_err_group = max_err_channel = mse_group = mse_channel = 0.0
    count = 0
    channel_scales = []
    for r in range(rows):
        # 8 uint4 values per little-endian INT32, matching compressed-tensors
        # pack-quantized storage; signed symmetric reconstruction is q - 8.
        vals = []
        for j in range(cols // 8):
            word = struct.unpack_from("<I", p, (r * (cols // 8) + j) * 4)[0]
            vals.extend(((word >> (4 * k)) & 0xF) - 8 for k in range(8))
        gs = [struct.unpack_from("<e", sb, (r * groups + g) * 2)[0] for g in range(groups)]
        deq = [vals[c] * gs[c // 32] for c in range(cols)]
        scale = max(abs(x) for x in deq) / 7.0
        channel_scales.append(scale)
        q = [max(-8, min(7, int(round(x / scale)))) if scale else 0 for x in deq]
        rg = [vals[c] * gs[c // 32] for c in range(cols)]
        rc = [q[c] * scale for c in range(cols)]
        for a, b, c in zip(deq, rg, rc):
            # b is the groupwise baseline; a and b are identical by construction.
            eg = abs(a - b)
            ec = abs(a - c)
            max_err_group = max(max_err_group, eg)
            max_err_channel = max(max_err_channel, ec)
            mse_group += eg * eg
            mse_channel += ec * ec
            count += 1
    return {
        "tensor": prefix + ".weight",
        "shape": [rows, cols],
        "source_contract": {"packed_dtype": "INT32", "packed_shape": list(packed["shape"]), "scale_dtype": "BF16", "scale_shape": list(scales["shape"]), "shape_dtype": "INT64"},
        "channel_contract": {"packed_dtype": "INT32", "packed_shape": [rows, cols // 8], "scale_dtype": "BF16", "scale_shape": [rows], "shape_dtype": "INT64", "zero_point": None, "group_size": None, "axis": 0},
        "source_bytes": {"packed": payload_bytes(packed), "scales": payload_bytes(scales), "shape": payload_bytes(shape)},
        "channel_bytes": {"packed": rows * cols // 2, "scales": rows * 2, "shape": 16},
        "reconstruction": {"elements": count, "groupwise_max_abs_error": max_err_group, "channelwise_max_abs_error": max_err_channel, "groupwise_mse": mse_group / count, "channelwise_mse": mse_channel / count, "channel_scale_min": min(channel_scales), "channel_scale_max": max(channel_scales)},
    }


def main() -> None:
    config = json.loads((ROOT / "config.json").read_text())
    index = json.loads((ROOT / "model.safetensors.index.json").read_text())
    names = all_headers(index)
    packed_names = [n for n in names if n.endswith(".weight_packed")]
    rows = []
    for n in packed_names:
        base = n.removesuffix(".weight_packed")
        m = names[n]
        shape = m["shape"]
        if len(shape) != 2:
            continue
        out, packed_cols = shape
        scale = names.get(base + ".weight_scale")
        if not scale or scale["shape"] != [out, packed_cols // 4]:
            continue
        old = payload_bytes(scale)
        new = out * 2
        rows.append({"tensor": base, "shape": [out, packed_cols * 8], "packed_bytes": payload_bytes(m), "old_scale_bytes": old, "channel_scale_bytes": new, "saved_scale_bytes": old - new})
    total_old = sum(x["old_scale_bytes"] for x in rows)
    total_new = sum(x["channel_scale_bytes"] for x in rows)
    # Exact source-bound dispatch/config evidence: both retained method names
    # are WNA16 groupwise paths; no channelwise strategy or method is exposed.
    weights = config["quantization_config"]["config_groups"]["group_0"]["weights"]
    dispatch = {
        "ordinary_linear": "MarlinLinearKernel_CompressedTensorsWNA16",
        "fused_moe": "CompressedTensorsWNA16MarlinMoE",
        "ordinary_linear_channelwise": "not exposed by pinned v0.15.0 source-bound evidence",
        "fused_moe_channelwise": "not exposed by pinned v0.15.0 source-bound evidence",
        "config_strategy": weights["strategy"],
        "config_group_size": weights["group_size"],
        "sm89": "existing group-32 WNA16 path is retained; channelwise variant is unbound",
    }
    f = fixture(names)
    savings = total_old - total_new
    full = index["metadata"]["total_size"]
    c32 = 46875.7 - savings / 2**20
    result = {
        "decision": "CHANNELWISE_W4_CLOSE",
        "terminal": True,
        "question": "exact current-AWQ W4 majority tensors with one output-channel scale on ordinary and fused-MoE SM89 Marlin paths",
        "evidence_class": ["measured_safetensor_headers", "measured_streaming_fixture", "source_bound_runtime_audit", "derived_memory", "inferred_endpoint"],
        "checkpoint": {"root": str(ROOT), "revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881", "total_bytes": full, "packed_tensor_count": len(rows)},
        "dispatch": dispatch,
        "fixture": f,
        "representation_accounting": {"existing_scale_bytes": total_old, "channelwise_scale_bytes": total_new, "saved_scale_bytes": savings, "saved_scale_mib": savings / 2**20, "saved_fraction_of_checkpoint": savings / full, "exact_scope": "all tensors with weight_packed + weight_scale and output-channel scale shape"},
        "memory": {"stock_full47_c32_peak_mib": 46875.7, "linear_channelwise_c32_peak_mib": c32, "device_visible_mib": 46068.0, "robust_peak_limit_mib": 44532.0, "nominal_device_fit": c32 < 46068.0, "robust_memory_fit": c32 < 44532.0, "caveat": "scale savings are persistent-weight accounting only; allocator and runtime buffers are unchanged"},
        "endpoint": {"stock_full47_c16_tps": 552.1710554232396, "absolute_gate_tps": 594.466, "robust_gate_tps": TARGET, "required_gain_fraction": TARGET / 552.1710554232396 - 1, "conservative_bound_tps": None, "status": "not_identifiable from retained scope-matched evidence; metadata savings do not establish wall-time transfer"},
        "reason": "Pinned compressed-tensors W4 config and both dispatch families bind groupwise WNA16 only; channelwise scale metadata has no exact loader/kernel contract. The real-tensor fixture is coherent but semantics-changing, and its saved metadata neither robustly admits c32 nor identifies the required 9.813% endpoint gain.",
        "next_move": "No successor under this project contract; retain as a representation falsifier and require a future exact channelwise loader/kernel implementation plus target-GPU measurement before reopening.",
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"decision": result["decision"], "packed_tensor_count": len(rows), "saved_scale_mib": result["representation_accounting"]["saved_scale_mib"], "c32_mib": c32, "fixture": f["reconstruction"]}, indent=2))


if __name__ == "__main__":
    main()
