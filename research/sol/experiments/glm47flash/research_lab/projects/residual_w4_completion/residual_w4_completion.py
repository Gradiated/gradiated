"""Zero-cost header, config, and economic screen for the ignored W4 residual."""

import json
import math
import re
import struct
from pathlib import Path


ROOT = Path("/root/.cache/glm47flash-awq-ab31d120")
OUT = Path(__file__).parent / "residual_w4_completion_bound.json"
TARGET = 594.466
STOCK_C16 = 535.2861037029285
STOCK_C16_PEAK_MIB = 44103.0
STOCK_C32_PEAK_MIB = 46875.7
L40S_MIB = 48 * 1024


def headers(index):
    result = {}
    for shard in sorted(set(index.values())):
        with (ROOT / shard).open("rb") as stream:
            size = struct.unpack("<Q", stream.read(8))[0]
            header = json.loads(stream.read(size))
        for name, value in header.items():
            if name != "__metadata__":
                result[name] = {**value, "bytes": value["data_offsets"][1] - value["data_offsets"][0]}
    return result


def layer(name):
    match = re.search(r"model\.layers\.(\d+)\.", name)
    return int(match.group(1)) if match else None


def is_stock_residual(name):
    if name == "lm_head.weight":
        return True
    n = layer(name)
    if n is None or n > 46:
        return False
    return ".mlp.shared_experts." in name or (
        n == 0 and (
            ".self_attn." in name
            or any(f".mlp.{x}.weight" in name for x in ("gate_proj", "up_proj", "down_proj"))
        )
    )


def candidate_tensor(name, info):
    """Return exact native pack-quantized W4 tensors for one BF16 Linear."""
    out, inp = info["shape"]
    packed = out * inp // 2
    scales = out * (inp // 32) * 2  # existing checkpoint uses BF16 scales
    return {
        "source": name,
        "source_shape": info["shape"],
        "source_bytes": info["bytes"],
        "weight_packed": {"dtype": "I32", "shape": [out, inp // 8], "bytes": packed},
        "weight_scale": {"dtype": "BF16", "shape": [out, inp // 32], "bytes": scales},
        "weight_shape": {"dtype": "I64", "shape": [2], "bytes": 16},
        "candidate_bytes": packed + scales + 16,
        "saved_bytes": info["bytes"] - packed - scales - 16,
        "legal_group32": inp % 32 == 0 and out % 128 == 0,
        "legality_reason": None if inp % 32 == 0 and out % 128 == 0 else "output dimension is not a 128-wide Marlin tile",
    }


def main():
    config = json.loads((ROOT / "config.json").read_text())
    index = json.loads((ROOT / "model.safetensors.index.json").read_text())
    info = headers(index["weight_map"])
    residual = [
        candidate_tensor(n, info[n])
        for n in sorted(info)
        if is_stock_residual(n) and n.endswith(".weight") and len(info[n]["shape"]) == 2
    ]

    scopes = {
        "head_only": lambda x: x["source"] == "lm_head.weight",
        "shared_experts_only": lambda x: ".mlp.shared_experts." in x["source"],
        "all_ignored_stock_serving_linears": lambda x: True,
    }
    scope_rows = []
    for name, predicate in scopes.items():
        rows = [x for x in residual if predicate(x)]
        source = sum(x["source_bytes"] for x in rows)
        packed = sum(x["candidate_bytes"] for x in rows)
        scope_rows.append({
            "scope": name,
            "tensor_count": len(rows),
            "source_bf16_bytes": source,
            "source_bf16_mib": source / 2**20,
            "candidate_w4_bytes": packed,
            "candidate_w4_mib": packed / 2**20,
            "saved_bytes": source - packed,
            "saved_mib": (source - packed) / 2**20,
            "all_group32_tile_legal": all(x["legal_group32"] for x in rows),
            "illegal_tensors": [
                {"source": x["source"], "shape": x["source_shape"], "reason": x["legality_reason"]}
                for x in rows
                if not x["legal_group32"]
            ],
            "sample_tensors": rows[:4],
        })

    ignored = set(config["quantization_config"]["ignore"])
    actual_names = {x["source"] for x in residual}
    fixture_names = []
    for row in residual[:3]:
        source = row["source"]
        fixture_names += [source.replace(".weight", suffix) for suffix in (".weight_packed", ".weight_scale", ".weight_shape")]
    fixture = {
        "fixture": "synthetic_exact_shape_source_bound",
        "config_change": {
            "remove_from_ignore": sorted(actual_names & ignored),
            "group_0_targets": config["quantization_config"]["config_groups"]["group_0"]["targets"],
            "format": config["quantization_config"]["format"],
            "group_size": config["quantization_config"]["config_groups"]["group_0"]["weights"]["group_size"],
            "num_bits": config["quantization_config"]["config_groups"]["group_0"]["weights"]["num_bits"],
        },
        "mapping_contract": {
            "source_weight_to_packed_names": fixture_names,
            "shape_tensor_restores_source_shape": True,
            "zero_point": None,
            "activation_order": None,
        },
        "dispatch_contract": {
            "linear": "MarlinLinearKernel_CompressedTensorsWNA16",
            "moe": "CompressedTensorsWNA16MarlinMoE",
            "evidence": "retained vLLM c16 trace and semantic smoke; exact residual candidate still synthetic",
            "l40s_capability": "sm_89; retained runtime uses Marlin W4 on this chip",
        },
        "result": "pass_for_synthetic_config_mapping_and_dispatch_contract",
        "limitation": "does not transform checkpoint or execute a GPU kernel",
    }

    all_row = scope_rows[-1]
    # Two independent ceilings are retained trace interval unions, not measured wall shares.
    head_ceiling = 0.1409
    residual_ceiling = 0.0710
    ideal_saved_fraction = 1 - all_row["candidate_w4_bytes"] / all_row["source_bf16_bytes"]
    ideal_endpoint_tps = STOCK_C16 / (1 - (head_ceiling + residual_ceiling) * ideal_saved_fraction)
    # Linear memory model from the retained c32 bound; this is admission only.
    c32_candidate_mib = STOCK_C32_PEAK_MIB - all_row["saved_mib"]
    result = {
        "inputs": {
            "checkpoint": str(ROOT),
            "checkpoint_total_bytes": index["metadata"]["total_size"],
            "stock_serving_layers": "0-46",
            "excluded_mtp_layer": 47,
            "stock_c16_output_tps": STOCK_C16,
            "promotion_target_output_tps": TARGET,
            "l40s_device_mib": L40S_MIB,
            "stock_c16_peak_mib": STOCK_C16_PEAK_MIB,
            "stock_c32_peak_mib": STOCK_C32_PEAK_MIB,
        },
        "scopes": scope_rows,
        "source_bound_fixture": fixture,
        "economic_screen": {
            "retained_trace_ceiling_head": head_ceiling,
            "retained_trace_ceiling_shared_standard_marlin": residual_ceiling,
            "ideal_w4_payload_fraction_of_bf16": 1 - ideal_saved_fraction,
            "impossible_optimistic_endpoint_tps_if_both_ceilings_transfer": ideal_endpoint_tps,
            "target_reached_by_optimistic_bound": ideal_endpoint_tps >= TARGET,
            "candidate_c32_peak_mib_linear_projection": c32_candidate_mib,
            "candidate_c32_nominal_memory_admission": c32_candidate_mib < L40S_MIB,
            "c32_throughput_evidence": "none; memory admission is not a promotion result",
            "all_scope_dispatch_gate": "fail_exact_shape_layer0_kv_a_proj_with_mqa_576x2048_not_128_tile_legal",
            "decision": "close_without_paid_nomination",
            "reason": "synthetic loader/dispatch contract passes, but the actual checkpoint lacks packed tensors and no scope-matched wall-time transfer supports >=594.466 tok/s; c32 is only a linear memory projection",
        },
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"artifact": str(OUT), "scopes": [{k: v[k] for k in ("scope", "tensor_count", "source_bf16_mib", "candidate_w4_mib", "saved_mib")} for v in scope_rows], "economic": result["economic_screen"]}, indent=2))


if __name__ == "__main__":
    main()
