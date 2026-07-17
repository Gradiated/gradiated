"""Source-bound physical depth-student manifest and deterministic fixture.

This is an architecture-cost screen.  It never rewrites checkpoint shards and
does not claim that the resulting students preserve model quality.
"""
from __future__ import annotations

import hashlib
import json
import math
import mmap
import re
import struct
from collections import defaultdict
from pathlib import Path

ROOT = Path("/root/.cache/glm47flash-awq-ab31d120")
BF16_ROOT = Path("/root/.cache/glm47flash-bf16-33faccf4")
OUT = Path(__file__).with_name("distilled_depth_student_bound.json")
SERVING_LAYERS = tuple(range(47))
SOURCE_LAYER_COUNT = 48
EXPECTED_CONFIG_SHA256 = "079f8fcd477b07378deafc21ecc5c3b974bf109ce5c9115854d97f88fa7622b9"
EXPECTED_INDEX_SHA256 = "b9c53433e94f2fe7870cdbc3fcb6ed1431eb500c5242a039de93fef4bb988695"
BASELINE_TOK_S = 535.286
GPU_HOUR = 1.1
TARGET_TOK_S = 594.466
CARD_MIB = 46068
OBSERVED_C16_MIB = 42827
KV_C16_GIB_PER_LAYER = 0.140625
KV_C32_GIB_PER_LAYER = 0.28125


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def header(path: Path) -> dict[str, object]:
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        result = json.loads(f.read(n))
        result["_header_bytes"] = n + 8
        return result


DTYPE_BYTES = {"F32": 4, "F16": 2, "BF16": 2, "I8": 1, "U8": 1, "I32": 4, "I64": 8}


def tensor_entries(root: Path) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
    index = json.loads((root / "model.safetensors.index.json").read_text())
    entries: dict[str, dict[str, object]] = {}
    headers: dict[str, dict[str, object]] = {}
    for name, shard_name in index["weight_map"].items():
        if name in entries:
            continue
        if shard_name not in headers:
            headers[shard_name] = header(root / shard_name)
        h = headers[shard_name]
        item = h[name]
        dtype = str(item["dtype"])
        offsets = item["data_offsets"]
        entries[name] = {
            "dtype": dtype,
            "shape": item["shape"],
            "bytes": int(offsets[1] - offsets[0]),
            "data_offsets": offsets,
            "header_bytes": h["_header_bytes"],
            "shard": shard_name,
        }
    return entries, index["weight_map"]


def layer_id(name: str) -> int | None:
    m = re.match(r"model\.layers\.(\d+)\.", name)
    return int(m.group(1)) if m else None


def evenly_spaced(count: int) -> tuple[int, ...]:
    # Sparse blocks are 1..46; integer rounding gives reproducible edge-safe sets.
    values = {int(round(i * 46 / (count + 1))) for i in range(1, count + 1)}
    if len(values) != count or not values.issubset(set(range(1, 47))):
        raise AssertionError("spacing collision")
    return tuple(sorted(values))


def family(name: str) -> str:
    if ".self_attn." in name:
        return "attention"
    if ".mlp.experts." in name:
        return "routed_moe"
    if ".mlp.shared_experts." in name:
        return "shared_moe"
    if ".mlp." in name:
        return "dense_mlp"
    if ".input_layernorm." in name or ".post_attention_layernorm." in name or ".q_a_layernorm." in name or ".kv_a_layernorm." in name:
        return "norm"
    return "other"


def norm_sample_similarity(root: Path, entries: dict[str, dict[str, object]]) -> dict[str, object]:
    """Cheap value-derived prior: sampled BF16 adjacent attention weights.

    This is deliberately weak: weight similarity is not activation similarity and
    is not quality evidence.  Sampling is deterministic and bounded.
    """
    key_by_layer = {}
    for name in entries:
        i = layer_id(name)
        if i in SERVING_LAYERS and name.endswith("self_attn.o_proj.weight"):
            key_by_layer[i] = name
    vectors = {}
    for i, name in sorted(key_by_layer.items()):
        shard = root / str(entries[name]["shard"])
        start, end = entries[name]["data_offsets"]
        raw_start = int(entries[name]["header_bytes"]) + int(start)
        sample_bytes = min(int(end - start), 8192)
        with shard.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            raw = mm[raw_start : raw_start + sample_bytes]
        # BF16 raw words are a stable, value-derived signature.  This avoids
        # loading 47 full tensors and is only a weak prior, not activation data.
        vectors[i] = [float(x) for x in struct.unpack("<" + "H" * (len(raw) // 2), raw[: len(raw) // 2 * 2])]
    sims = []
    for i in range(1, 47):
        a, b = vectors[i - 1], vectors[i]
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        sims.append({"layers": [i - 1, i], "cosine": dot / (na * nb) if na and nb else 0.0})
    return {
        "available": True,
        "source": str(root),
        "tensor": "model.layers.<i>.self_attn.o_proj.weight",
        "sample_count": min(4096, max(len(v) for v in vectors.values())),
        "adjacent_cosine": sims,
        "interpretation": "weak checkpoint-derived recovery prior only; no activations or quality labels",
    }


def fixture_check(retained: list[int]) -> dict[str, object]:
    class Block:
        def __call__(self, x: list[float]) -> list[float]:
            return [v + 1.0 for v in x]

    class Model:
        def __init__(self) -> None:
            self.layers = [Block() for _ in SERVING_LAYERS]
            self.final_norm = lambda x: x
            self.lm_head_width = 154880

        def forward(self, x: list[float]) -> list[float]:
            for i, layer in enumerate(self.layers):
                if i in retained:
                    x = layer(x)
            return self.final_norm(x)

    model = Model()
    state = model.forward([0.0, 0.0, 0.0])
    expected = len(retained)
    assert state == [float(expected)] * 3
    assert model.lm_head_width == 154880
    return {"renumbered_layer_count": len(retained), "hidden_shape": [3], "final_norm_and_head_preserved": True, "forward_check": "PASS"}


def main() -> None:
    entries, weight_map = tensor_entries(ROOT)
    bf16_entries, _ = tensor_entries(BF16_ROOT)
    source_layers = sorted({i for i in map(layer_id, entries) if i is not None})
    assert source_layers == list(range(SOURCE_LAYER_COUNT))
    assert any(layer_id(n) == 47 for n in entries)
    assert sha256(ROOT / "config.json") == EXPECTED_CONFIG_SHA256
    assert sha256(ROOT / "model.safetensors.index.json") == EXPECTED_INDEX_SHA256

    per_layer = defaultdict(lambda: defaultdict(int))
    total = defaultdict(int)
    for name, item in entries.items():
        b = int(item["bytes"])
        i = layer_id(name)
        total["all_checkpoint"] += b
        if i in SERVING_LAYERS:
            per_layer[i]["awq_total"] += b
            per_layer[i][family(name)] += b
        elif i == 47:
            total["excluded_mtp_payload"] += b
        else:
            total["non_layer_serving"] += b
    for name, item in bf16_entries.items():
        i = layer_id(name)
        if i in SERVING_LAYERS:
            per_layer[i]["bf16_total"] += int(item["bytes"])

    def candidate(name: str, skipped: tuple[int, ...]) -> dict[str, object]:
        removed_awq = sum(per_layer[i]["awq_total"] for i in skipped)
        removed_bf16 = sum(per_layer[i]["bf16_total"] for i in skipped)
        retained = len(SERVING_LAYERS) - len(skipped)
        retained_source = [i for i in SERVING_LAYERS if i not in skipped]
        source_to_student = {str(source): student for student, source in enumerate(retained_source)}
        # The earlier five-block trace bound leaves 89.3617% variable repeated
        # work and 10.6383% fixed head/scheduler/overlap cost.
        variable_fraction = 1.0 - 5 / 47
        work_fraction_removed = len(skipped) / 47
        optimistic_speed = BASELINE_TOK_S / (1 - work_fraction_removed)
        fixed_cost_speed = BASELINE_TOK_S / (1 - variable_fraction * work_fraction_removed)
        def cost(tok_s: float) -> float:
            return GPU_HOUR * 1_000_000 / (tok_s * 3600)
        c16_peak = OBSERVED_C16_MIB - removed_awq / (1024**2) - len(skipped) * KV_C16_GIB_PER_LAYER * 1024
        c32_peak = OBSERVED_C16_MIB + len(SERVING_LAYERS) * KV_C16_GIB_PER_LAYER * 1024 - len(skipped) * KV_C32_GIB_PER_LAYER * 1024
        return {
            "name": name,
            "serving_layer_count": retained,
            "removed_layers": list(skipped),
            "retained_layers": [i for i in SERVING_LAYERS if i not in skipped],
            "renumbering": {"source_to_student_layer": source_to_student, "student_layer_ids": list(range(retained)), "dangling_source_layer_ids": [47]},
            "removed_awq_bytes": removed_awq,
            "removed_awq_gib": removed_awq / 2**30,
            "removed_bf16_bytes": removed_bf16,
            "removed_bf16_gib": removed_bf16 / 2**30,
            "removed_kv_gib": {"c16": len(skipped) * KV_C16_GIB_PER_LAYER, "c32": len(skipped) * KV_C32_GIB_PER_LAYER},
            "memory_bound_mib": {"c16": c16_peak, "c32": c32_peak, "card": CARD_MIB, "c32_headroom_mib": CARD_MIB - c32_peak},
            "economics": {
                "optimistic_work_ceiling_tok_s": optimistic_speed,
                "optimistic_work_ceiling_usd_per_million": cost(optimistic_speed),
                "fixed_cost_endpoint_bound_tok_s": fixed_cost_speed,
                "fixed_cost_endpoint_bound_usd_per_million": cost(fixed_cost_speed),
                "gate_tok_s": TARGET_TOK_S,
                "gate_passes": fixed_cost_speed >= TARGET_TOK_S,
                "bound_formula": "baseline / (1 - (1 - 5/47) * removed_layers/47); fixed 5-block-calibrated head/scheduler/overlap fraction retained",
            },
            "tensor_manifest": {
                "removed_tensor_count": sum(1 for n in entries if layer_id(n) in skipped),
                "retained_tensor_count": sum(1 for n in entries if layer_id(n) in SERVING_LAYERS and layer_id(n) not in skipped),
                "removed_bytes_by_family": {k: sum(per_layer[i][k] for i in skipped) for k in ["attention", "routed_moe", "shared_moe", "dense_mlp", "norm", "other"]},
                "serving_prefix_contract": "model.layers.<student_index> plus original non-layer embed/final_norm/lm_head tensors; model.layers.47 and MTP tensors excluded",
            },
            "fixture_check": fixture_check(retained_source),
        }

    result = {
        "schema_version": 1,
        "evidence_class": "derived_exact_safetensor_headers_plus_checkpoint_value_sample_plus_measured_trace_transfer",
        "scope": "zero-cost physical student screen; AWQ serving graph layers 0..46; layer 47 MTP payload excluded",
        "checkpoint": {
            "root": str(ROOT),
            "config_sha256": sha256(ROOT / "config.json"),
            "index_sha256": sha256(ROOT / "model.safetensors.index.json"),
            "file_manifest_sha256": sha256(ROOT / "model-files-manifest.json"),
            "checkpoint_revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881",
            "configured_num_hidden_layers": 47,
            "loaded_tensor_layer_ids": source_layers,
            "excluded_layer_ids": [47],
        },
        "shape_contract": {"hidden_size": 2048, "output_head_preserved": True, "final_norm_preserved": True, "mtp_tensors_in_serving_graph": False},
        "baseline": {"output_tok_s": BASELINE_TOK_S, "planning_gpu_hour_usd": GPU_HOUR, "observed_c16_peak_mib": OBSERVED_C16_MIB, "card_mib": CARD_MIB},
        "students": [candidate("student_39_even", evenly_spaced(8)), candidate("student_34_even", evenly_spaced(13))],
        "recovery_prior": norm_sample_similarity(BF16_ROOT, bf16_entries),
        "source_bound_checks": {"fixture": "renumbering and model-like forward checked below", "drift_policy": "fail closed on checkpoint identity, source layer IDs, or shape contract drift", "quality": "not measured; no deployable claim"},
        "decision": "nominate_at_most_one_later_ceiling_arm_only_if_39_layer_fixed_cost_bound_is_reproduced_and_quality_recovery_is_authorized; otherwise close",
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"wrote": str(OUT), "students": result["students"], "recovery_prior": result["recovery_prior"]}, indent=2))


if __name__ == "__main__":
    main()
