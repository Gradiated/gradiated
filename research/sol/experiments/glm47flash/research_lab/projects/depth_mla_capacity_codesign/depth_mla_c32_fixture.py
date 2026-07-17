#!/usr/bin/env python3
"""Source-bound c32 MLA-rank screen for the 39-layer AWQ student.

This fixture validates tensor/packing contracts only.  It neither writes a
checkpoint nor loads CUDA, so its rank-256 result is architecture-cost evidence
rather than a quality or runtime result.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


ROOT = Path("/root/.cache/glm47flash-awq-student39-183247870f89")
OUT = Path(__file__).with_name("DEPTH_MLA_C32_BOUND.json")
RANKS = (448, 384, 320, 256)
STOCK_RANK = 512
ROPE = 64
GROUP = 32
LAYERS = 39
CARD_MIB = 46_068.0
MIN_HEADROOM_MIB = 3 * 1024
STUDENT_C16_MIB = 38_843.51696777344
STUDENT_C32_MIB = 47_291.0
FIXED_COST_TOK_S = 631.3116785904964
TARGET_TOK_S = 594.466
KV_C16_GIB_PER_LAYER = 0.140625
PINNED_VLLM_SOURCE_SHA256 = "6a984f701d46dfa05389a45d7aedde6a10ef45a6f59e73d3bbfa1e82f556b4a9"
PINNED_VLLM_SOURCE = "https://raw.githubusercontent.com/vllm-project/vllm/v0.15.0/vllm/model_executor/models/glm4_moe_lite.py"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def headers(root: Path, weight_map: dict[str, str]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    by_shard: dict[str, dict[str, object]] = {}
    for name, shard in weight_map.items():
        if shard not in by_shard:
            with (root / shard).open("rb") as f:
                by_shard[shard] = json.loads(f.read(struct.unpack("<Q", f.read(8))[0]))
        result[name] = by_shard[shard][name]
    return result


def tensor_bytes(item: dict[str, object]) -> int:
    offsets = item["data_offsets"]
    return int(offsets[1]) - int(offsets[0])


def original_projection_bytes(items: dict[str, dict[str, object]], layer: int) -> int:
    prefix = f"model.layers.{layer}.self_attn."
    names = ("kv_a_proj_with_mqa", "kv_b_proj")
    return sum(tensor_bytes(items[prefix + name + suffix]) for name in names for suffix in (
        ".weight", ".weight_packed", ".weight_scale", ".weight_shape") if prefix + name + suffix in items)


def transformed_projection_bytes(rank: int, layer: int, heads: int, nope: int, value: int, hidden: int) -> int:
    kv_a_out = rank + ROPE
    kv_b_out = heads * (nope + value)
    if layer == 0:
        return 2 * (kv_a_out * hidden + kv_b_out * rank)
    # compressed-tensors W4: eight values per I32 and one BF16 scale per 32 inputs.
    return (
        kv_a_out * (hidden // 8) * 4
        + kv_a_out * (hidden // GROUP) * 2
        + 16
        + kv_b_out * (rank // 8) * 4
        + kv_b_out * (rank // GROUP) * 2
        + 16
    )


def main() -> None:
    config = json.loads((ROOT / "config.json").read_text())
    index = json.loads((ROOT / "model.safetensors.index.json").read_text())
    weight_map = index["weight_map"]
    items = headers(ROOT, weight_map)
    hidden = int(config["hidden_size"])
    heads = int(config["num_attention_heads"])
    nope = int(config["qk_nope_head_dim"])
    value = int(config["v_head_dim"])
    assert int(config["num_hidden_layers"]) == LAYERS
    assert int(config["kv_lora_rank"]) == STOCK_RANK
    assert all(rank % GROUP == 0 for rank in RANKS)

    source_shapes_ok = True
    source_bytes = 0
    for layer in range(LAYERS):
        prefix = f"model.layers.{layer}.self_attn."
        if layer == 0:
            source_shapes_ok &= items[prefix + "kv_a_proj_with_mqa.weight"]["shape"] == [576, hidden]
            source_shapes_ok &= items[prefix + "kv_b_proj.weight"]["shape"] == [heads * (nope + value), STOCK_RANK]
        else:
            source_shapes_ok &= items[prefix + "kv_a_proj_with_mqa.weight_packed"]["shape"] == [576, hidden // 8]
            source_shapes_ok &= items[prefix + "kv_a_proj_with_mqa.weight_scale"]["shape"] == [576, hidden // GROUP]
            source_shapes_ok &= items[prefix + "kv_b_proj.weight_packed"]["shape"] == [heads * (nope + value), STOCK_RANK // 8]
            source_shapes_ok &= items[prefix + "kv_b_proj.weight_scale"]["shape"] == [heads * (nope + value), STOCK_RANK // GROUP]
        source_bytes += original_projection_bytes(items, layer)
    assert source_shapes_ok

    rows = []
    for rank in RANKS:
        c16_kv_saved_mib = LAYERS * KV_C16_GIB_PER_LAYER * 1024 * (STOCK_RANK - rank) / (STOCK_RANK + ROPE)
        c32_kv_saved_mib = 2 * c16_kv_saved_mib
        transformed_bytes = sum(transformed_projection_bytes(rank, layer, heads, nope, value, hidden) for layer in range(LAYERS))
        weight_saved_mib = (source_bytes - transformed_bytes) / 2**20
        c16_rank_only = STUDENT_C16_MIB - c16_kv_saved_mib
        c32_rank_only = STUDENT_C32_MIB - c32_kv_saved_mib
        c24_rank_only = c16_rank_only + (c32_rank_only - c16_rank_only) / 2
        c32_with_weight_credit = c32_rank_only - weight_saved_mib
        static_shapes = {
            "kv_a_bf16": [rank + ROPE, hidden],
            "kv_b_bf16": [heads * (nope + value), rank],
            "kv_a_w4_packed_i32": [rank + ROPE, hidden // 8],
            "kv_a_w4_scale_bf16": [rank + ROPE, hidden // GROUP],
            "kv_b_w4_packed_i32": [heads * (nope + value), rank // 8],
            "kv_b_w4_scale_bf16": [heads * (nope + value), rank // GROUP],
        }
        loader_static_contract = source_shapes_ok and all(dimension % GROUP == 0 for dimension in (rank, rank + ROPE, hidden))
        rows.append({
            "kv_lora_rank": rank,
            "evidence_class": "derived_exact_safetensor_headers_and_pinned_vllm_source_contract",
            "static_tensor_contract": static_shapes,
            "loader_static_contract_passes": loader_static_contract,
            "requires_checkpoint_rewrite_and_recovery": rank != STOCK_RANK,
            "projection_payload": {
                "stock_bytes": source_bytes,
                "transformed_bytes": transformed_bytes,
                "saved_bytes": source_bytes - transformed_bytes,
                "saved_mib": weight_saved_mib,
            },
            "memory_peak_mib": {
                "c16_rank_only": c16_rank_only,
                "c24_rank_only_linear": c24_rank_only,
                "c32_rank_only": c32_rank_only,
                "c32_with_full_projection_payload_credit": c32_with_weight_credit,
                "c32_headroom_rank_only_mib": CARD_MIB - c32_rank_only,
                "c32_headroom_with_weight_credit_mib": CARD_MIB - c32_with_weight_credit,
            },
            "c32_kv_saved_mib": c32_kv_saved_mib,
            "minimum_headroom_passes_without_weight_credit": CARD_MIB - c32_rank_only >= MIN_HEADROOM_MIB,
            "tile_evidence": "rank-256 only: retained calibrated BLOCK_N=64/stage-2 envelope is 93,440 B <= 101,376 B; compilation remains unmeasured",
        })

    best = next(row for row in rows if row["kv_lora_rank"] == 256)
    required_fraction = TARGET_TOK_S / FIXED_COST_TOK_S
    decision = "NOMINATE_CONDITIONAL_R256_C32_ARM" if best["minimum_headroom_passes_without_weight_credit"] and best["loader_static_contract_passes"] else "CLOSE_AT_ZERO"
    result = {
        "schema_version": 1,
        "question": "Can a minimal MLA reduction make the physical 39-layer student c32-admissible with a credible economic path?",
        "scope": "zero-cost static screen; no checkpoint write, CUDA, provider, runtime load, training, or quality claim",
        "evidence_labels": {
            "measured": "student c16 anchor and retained L40S MLA compiler calibration",
            "source_bound": "student config/index/safetensor headers and vLLM v0.15.0 source",
            "derived": "W4/BF16 payload and c16/c24/c32 memory projections",
            "inferred": "endpoint condition and any later rank-recovery path",
        },
        "checkpoint": {
            "root": str(ROOT),
            "config_sha256": sha256(ROOT / "config.json"),
            "index_sha256": sha256(ROOT / "model.safetensors.index.json"),
            "stock_kv_lora_rank": STOCK_RANK,
            "layers": LAYERS,
            "source_projection_payload_bytes": source_bytes,
        },
        "pinned_loader": {
            "runtime": "vllm/vllm-openai:v0.15.0 sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543",
            "source_url": PINNED_VLLM_SOURCE,
            "source_sha256": PINNED_VLLM_SOURCE_SHA256,
            "contract": "Glm4MoeLiteDecoderLayer reads config.kv_lora_rank and passes it into Glm4MoeLiteMLAAttention; static loading of a rewritten rank-256 checkpoint remains unmeasured",
        },
        "memory_model": {
            "card_mib": CARD_MIB,
            "minimum_c32_headroom_mib": MIN_HEADROOM_MIB,
            "student_c16_mib": STUDENT_C16_MIB,
            "student_c32_mib": STUDENT_C32_MIB,
            "formula": "rank-only c16 KV saving = 39 * 0.140625 GiB * (512-rank)/576; c32 saving is twice c16; c24 linearly interpolates the c16/c32 state projection",
            "conservatism": "admission uses rank-only headroom and grants no transformed-weight allocation credit",
        },
        "rows": rows,
        "economic_condition": {
            "student_fixed_cost_endpoint_bound_tok_s": FIXED_COST_TOK_S,
            "campaign_gate_tok_s": TARGET_TOK_S,
            "required_c32_retention_of_student_bound": required_fraction,
            "maximum_c32_regression_percent_before_gate": (1 - required_fraction) * 100,
            "interpretation": "The rank-256 c32 arm must retain at least 94.16% of the student's derived c16 endpoint bound. This is a conditional path, not a measured throughput claim.",
        },
        "decision": decision,
        "decision_reason": "Ranks 448/384/320 miss the 3-GiB c32 headroom rule without relying on allocator savings. Rank 256 clears it by 3,769 MiB (3.68 GiB) before weight credit and has group-32-aligned source shapes plus a dynamic pinned-loader config path. It still needs a rewritten/recovered checkpoint and a measured c32 endpoint/quality arm before promotion.",
        "next_move": "At most one later rank-256 c32 arm: materialize a content-addressed group-32 W4 rewrite, static-load it with the pinned image, then measure c32 throughput, memory, and recovery quality. Do not grant a cost or quality claim from this fixture.",
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": decision, "r256": best["memory_peak_mib"], "economic": result["economic_condition"]}, indent=2))


if __name__ == "__main__":
    main()
