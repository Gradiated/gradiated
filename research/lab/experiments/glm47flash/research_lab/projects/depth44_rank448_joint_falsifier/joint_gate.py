#!/usr/bin/env python3
"""Reconstruct the depth44/rank448 representation and bind its endpoint gate."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


ROOT = Path("/root/.cache/glm47flash-awq-minimal-depth42-v2-5dbf26dc16a1")
PROJECT = Path(__file__).parent
OUT = PROJECT / "artifacts" / "JOINT_PROXY_CLOSE_2026-07-16.json"
D42 = Path("../minimal_depth42_v2_l40s_direct/artifacts/nebius_l40s_minimal_depth42_v2_c16c32_2026-07-16-r2/summary.json")
D43 = Path("../minimal_depth43_v2_l40s_direct/artifacts/nebius_l40s_minimal_depth43_v2_c16c32_2026-07-16-r2/summary.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def header(path: Path, shard: str) -> dict[str, object]:
    with (path / shard).open("rb") as handle:
        return json.loads(handle.read(struct.unpack("<Q", handle.read(8))[0]))


def profile_rate(path: Path) -> float:
    summary = json.loads(path.read_text())["allocation_result"]
    profile = next(item for item in summary["performance"]["profiles"] if item["profile_id"] == "fixed_8k_1k_c32")
    assert profile["exact_geometry_pass"] and profile["success_fraction"] == 1.0
    return float(profile["output_tokens_per_second_conservative"])


def quantized_projection_bytes(rank: int, layers: int) -> int:
    a_out, b_out, hidden, group = rank + 64, 20 * (192 + 256), 2048, 32
    first = 2 * (a_out * hidden + b_out * rank)
    packed = a_out * (hidden // 8) * 4 + a_out * (hidden // group) * 2 + 16
    packed += b_out * (rank // 8) * 4 + b_out * (rank // group) * 2 + 16
    return first + (layers - 1) * packed


def main() -> None:
    config = json.loads((ROOT / "config.json").read_text())
    index = json.loads((ROOT / "model.safetensors.index.json").read_text())["weight_map"]
    probe = header(ROOT, index["model.layers.1.self_attn.kv_a_proj_with_mqa.weight_packed"])
    source = {
        f"{name}{suffix}": probe[f"model.layers.1.self_attn.{name}{suffix}"]
        for name in ("kv_a_proj_with_mqa", "kv_b_proj")
        for suffix in (".weight_packed", ".weight_scale", ".weight_shape")
    }
    assert config["kv_lora_rank"] == 512 and config["num_hidden_layers"] == 42
    assert source["kv_a_proj_with_mqa.weight_packed"]["shape"] == [576, 256]
    assert source["kv_a_proj_with_mqa.weight_scale"]["shape"] == [576, 64]
    assert source["kv_b_proj.weight_packed"]["shape"] == [8960, 64]
    assert source["kv_b_proj.weight_scale"]["shape"] == [8960, 16]
    d42, d43 = profile_rate(PROJECT / D42), profile_rate(PROJECT / D43)
    retention = d43 / d42
    depth44 = d43 * retention
    rank_work_reduction = 64 / 576
    measured_component_reduction, measured_endpoint_reduction = 0.1435, 0.0105
    endpoint_share = measured_endpoint_reduction / measured_component_reduction
    rank448_uplift = rank_work_reduction * endpoint_share
    optimistic_endpoint = depth44 * (1 + rank448_uplift)
    stock_payload = quantized_projection_bytes(512, 44)
    rank448_payload = quantized_projection_bytes(448, 44)
    result = {
        "schema_version": 1,
        "decision": "JOINT_PROXY_CLOSE",
        "question": "Can rank448 make a nested 44-layer W4A16/BF16-KV proxy robustly admissible and retain 606.355 tok/s?",
        "scope": "offline only; no checkpoint write, CUDA, provider, runtime load, quality run, or shared-code mutation",
        "evidence_labels": {"measured": "depth42/depth43 complete c32 profiles and retained MLA split transfer", "source_bound": "local group-32 safetensor headers plus pinned vLLM loader identity", "derived": "rank448 payload, KV and endpoint arithmetic", "inferred": "rank-reduction quality remains deferred"},
        "representation": {
            "source_checkpoint": str(ROOT), "config_sha256": sha256(ROOT / "config.json"), "index_sha256": sha256(ROOT / "model.safetensors.index.json"),
            "pinned_loader": {"vllm": "0.15.0", "image_sha256": "97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543", "contract": "Glm4MoeLiteDecoderLayer passes config.kv_lora_rank to MLA attention; rank448 is group-32 aligned and needs only config plus kv_a/kv_b content-addressed rewrite."},
            "stock_layer1_shapes": {key: value["shape"] for key, value in source.items()},
            "rank448_shapes": {"layer0_kv_a_bf16": [512, 2048], "layer0_kv_b_bf16": [8960, 448], "sparse_kv_a_packed_i32": [512, 256], "sparse_kv_a_scale_bf16": [512, 64], "sparse_kv_b_packed_i32": [8960, 56], "sparse_kv_b_scale_bf16": [8960, 14]},
            "depth44_projection_payload": {"stock_rank512_bytes": stock_payload, "rank448_bytes": rank448_payload, "saved_bytes": stock_payload - rank448_payload, "saved_mib": (stock_payload - rank448_payload) / 2**20},
            "coherent_without_materialization": True,
        },
        "memory": {"layers": 44, "bf16_kv_width_stock": 576, "bf16_kv_width_rank448": 512, "c32_kv_per_layer_stock_mib": 288, "c32_kv_saving_per_layer_mib": 32, "c32_kv_saving_mib": 1408, "projected_peak_mib": 43746.87075805664, "robust_limit_mib": 44532.0, "headroom_mib": 785.1292419433594, "passes": True},
        "endpoint": {"depth42_c32_conservative_tok_s": d42, "depth43_c32_conservative_tok_s": d43, "adjacent_depth_retention": retention, "depth44_nested_projection_tok_s": depth44, "mla_transfer": {"retained_component_reduction": measured_component_reduction, "retained_endpoint_reduction": measured_endpoint_reduction, "scope_matched_endpoint_share": endpoint_share, "rank448_attention_work_reduction": rank_work_reduction, "credited_endpoint_uplift": rank448_uplift}, "optimistic_scope_matched_rank448_endpoint_tok_s": optimistic_endpoint, "robust_gate_tok_s": 606.355, "shortfall_tok_s": 606.355 - optimistic_endpoint, "uncertainty": "No replication-based positive allowance is credited. This is already an optimistic upper bound because it grants the complete retained MLA transfer; any depth extrapolation or rank-rewrite uncertainty can only lower a conservative bound.", "passes": False},
        "closure_reason": "The exact group-32 rewrite geometry and robust memory arithmetic close, but the highest admissible scope-matched endpoint projection is below 606.355 tok/s. Therefore no c32 materialization or provider arm is nominated.",
        "cost_usd": 0.0, "provider_mutation": False, "next_action": "Terminal; no successor.",
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": result["decision"], "memory_headroom_mib": result["memory"]["headroom_mib"], "optimistic_endpoint": optimistic_endpoint, "shortfall": result["endpoint"]["shortfall_tok_s"]}, indent=2))


if __name__ == "__main__":
    main()
