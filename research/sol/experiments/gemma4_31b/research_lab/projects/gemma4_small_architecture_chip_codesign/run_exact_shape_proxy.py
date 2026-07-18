#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import mmap
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


MODEL = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
LOCAL_LAYERS = (0, 28, 58)
GLOBAL_LAYERS = (5, 29, 59)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


class SafeShard:
    def __init__(self, path):
        self.path = path
        self.handle = path.open("rb")
        self.mapping = mmap.mmap(self.handle.fileno(), 0, access=mmap.ACCESS_READ)
        header_length = struct.unpack("<Q", self.mapping[:8])[0]
        self.data_offset = 8 + header_length
        self.header = json.loads(self.mapping[8 : self.data_offset])

    def close(self):
        self.mapping.close()
        self.handle.close()

    def rows(self, name, start, end):
        metadata = self.header[name]
        rows, columns = metadata["shape"]
        if metadata["dtype"] != "BF16" or not 0 <= start <= end <= rows:
            raise ValueError((name, metadata, start, end))
        begin = self.data_offset + metadata["data_offsets"][0] + start * columns * 2
        count = (end - start) * columns
        bf16 = np.frombuffer(self.mapping, dtype="<u2", count=count, offset=begin)
        return (bf16.astype(np.uint32) << 16).view(np.float32).reshape(end - start, columns)


def tensor_name(layer, projection):
    return f"model.language_model.layers.{layer}.self_attn.{projection}.weight"


def load_index(checkpoint):
    index = json.loads((checkpoint / "model.safetensors.index.json").read_text())
    shards = {}
    for shard_name in sorted(set(index["weight_map"].values())):
        shards[shard_name] = SafeShard(checkpoint / shard_name)
    return index, shards


def tensor_rows(index, shards, name, start, end):
    return shards[index["weight_map"][name]].rows(name, start, end)


def local_kv_pair_metrics(index, shards, layer):
    head_dim = 256
    heads = 16
    projections = ("k_proj", "v_proj")
    pairs = []
    totals = {projection: {"original": 0.0, "retained": 0.0} for projection in projections}
    for projection in projections:
        name = tensor_name(layer, projection)
        for first_head in range(0, heads, 2):
            first = tensor_rows(
                index, shards, name, first_head * head_dim, (first_head + 1) * head_dim
            ).astype(np.float64)
            second = tensor_rows(
                index, shards, name, (first_head + 1) * head_dim, (first_head + 2) * head_dim
            ).astype(np.float64)
            first_energy = float(np.square(first).sum())
            second_energy = float(np.square(second).sum())
            dot = float(np.multiply(first, second).sum())
            original = first_energy + second_energy
            retained = 0.5 * (first_energy + second_energy + 2.0 * dot)
            totals[projection]["original"] += original
            totals[projection]["retained"] += retained
            pairs.append(
                {
                    "projection": projection,
                    "heads": [first_head, first_head + 1],
                    "cosine_similarity": dot / math.sqrt(first_energy * second_energy),
                    "shared_mean_reconstruction_retained_energy": retained / original,
                }
            )
    combined_original = sum(value["original"] for value in totals.values())
    combined_retained = sum(value["retained"] for value in totals.values())
    return {
        "layer": layer,
        "pair_count": len(pairs),
        "adjacent_pair_cosine": quantiles([pair["cosine_similarity"] for pair in pairs]),
        "shared_mean_reconstruction_retained_energy": combined_retained / combined_original,
        "projection_retained_energy": {
            key: value["retained"] / value["original"] for key, value in totals.items()
        },
        "interpretation": "Exact-weight no-training transplant proxy only; it is not a post-training quality estimate.",
    }


def global_dimension_energy(index, shards, layer):
    head_dim = 512
    q_heads = 32
    kv_heads = 4
    q_name = tensor_name(layer, "q_proj")
    k_name = tensor_name(layer, "k_proj")
    o_name = tensor_name(layer, "o_proj")
    energy = np.zeros(head_dim, dtype=np.float64)

    for head in range(q_heads):
        block = tensor_rows(index, shards, q_name, head * head_dim, (head + 1) * head_dim)
        energy += np.square(block, dtype=np.float32).sum(axis=1, dtype=np.float64)
    for head in range(kv_heads):
        block = tensor_rows(index, shards, k_name, head * head_dim, (head + 1) * head_dim)
        energy += 2.0 * np.square(block, dtype=np.float32).sum(axis=1, dtype=np.float64)

    o_rows = shards[index["weight_map"][o_name]].header[o_name]["shape"][0]
    for start in range(0, o_rows, 128):
        block = tensor_rows(index, shards, o_name, start, min(start + 128, o_rows))
        shaped = block.reshape(block.shape[0], q_heads, head_dim)
        energy += np.square(shaped, dtype=np.float32).sum(axis=(0, 1), dtype=np.float64)

    selected = np.argpartition(energy, -256)[-256:]
    fixed_even = np.arange(0, head_dim, 2)
    total = float(energy.sum())
    return {
        "layer": layer,
        "combined_runtime_weight_energy": total,
        "best_shared_256_dimensions_retained_energy": float(energy[selected].sum() / total),
        "even_256_dimensions_retained_energy": float(energy[fixed_even].sum() / total),
        "dimension_energy_coefficient_of_variation": float(energy.std() / energy.mean()),
        "energy_definition": "Q plus runtime-duplicated K/V plus O; one common dimension mask across all heads.",
        "interpretation": "Exact-weight no-training dimension-selection proxy only; it excludes activation covariance and post-training recovery.",
    }


def quantiles(values):
    array = np.asarray(values, dtype=np.float64)
    points = np.quantile(array, [0.0, 0.5, 0.9, 1.0])
    return dict(zip(("min", "p50", "p90", "max"), map(float, points)))


def exact_kv_bytes(prompt_tokens, output_tokens, local_heads, local_dim, global_heads, global_dim):
    local_per_token_layer = local_heads * local_dim * 2 * 2
    global_per_token_layer = global_heads * global_dim * 2 * 2
    local = 0
    global_ = 0
    for offset in range(output_tokens):
        context = prompt_tokens + offset
        local += 50 * min(context, 1024) * local_per_token_layer
        global_ += 10 * context * global_per_token_layer
    return {"local": local, "global": global_, "total": local + global_}


def tile_grid(n, units, tile_n=128):
    blocks = math.ceil(n / tile_n)
    waves = math.ceil(blocks / units)
    return {
        "n": n,
        "tile_n_assumption": tile_n,
        "blocks": blocks,
        "compute_units": units,
        "waves": waves,
        "wave_slot_utilization": blocks / (waves * units),
        "evidence_type": "analytical tile prior; exact kernel tile must be measured",
    }


def measured_row(rows, name, m=32):
    return next(row for row in rows if row["shape"] == name and row["m"] == m)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--runtime-source", type=Path, required=True)
    parser.add_argument("--linear-terminal", type=Path, required=True)
    parser.add_argument("--linear-stage", type=Path, required=True)
    parser.add_argument("--endpoint-terminal", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()

    config = json.loads(args.config.read_text())
    text = config["text_config"]
    linear_terminal = json.loads(args.linear_terminal.read_text())
    linear_stage = json.loads(args.linear_stage.read_text())
    endpoint = json.loads(args.endpoint_terminal.read_text())
    inventory = json.loads(args.inventory.read_text())
    accelerators = {accelerator["id"]: accelerator for accelerator in inventory["accelerators"]}
    h200_units = accelerators["nvidia-h200-sxm"]["execution"]["compute_units"]
    h200_bandwidth = accelerators["nvidia-h200-sxm"]["memory"]["bandwidth_gb_s"] * 1e9

    expected = {
        "architecture": config["architectures"] == ["Gemma4ForConditionalGeneration"],
        "hidden_size": text["hidden_size"] == 5376,
        "layers": text["num_hidden_layers"] == 60,
        "layer_cadence": text["layer_types"].count("sliding_attention") == 50
        and text["layer_types"].count("full_attention") == 10,
        "heads": text["num_attention_heads"] == 32
        and text["num_key_value_heads"] == 16
        and text["num_global_key_value_heads"] == 4,
        "dimensions": text["head_dim"] == 256 and text["global_head_dim"] == 512,
        "window": text["sliding_window"] == 1024,
        "endpoint": endpoint["stock"]["complete_requests"] == 32,
        "measured_gpu": linear_terminal["measurement_validity"]["gpu"] == "NVIDIA H200",
    }
    if not all(expected.values()):
        raise ValueError(expected)

    index, shards = load_index(args.checkpoint)
    try:
        local_weights = [local_kv_pair_metrics(index, shards, layer) for layer in LOCAL_LAYERS]
        global_weights = [global_dimension_energy(index, shards, layer) for layer in GLOBAL_LAYERS]
    finally:
        for shard in shards.values():
            shard.close()

    rows = linear_stage["terminal"]["result"]["rows"]
    local_qkv = measured_row(rows, "sliding_qkv")
    global_qkv = measured_row(rows, "global_qkv")
    global_output = measured_row(rows, "global_output")
    service_seconds = endpoint["stock"]["service_seconds_per_request"]
    output_tokens = 358
    batch = 32

    baseline_kv = exact_kv_bytes(4214, output_tokens, 16, 256, 4, 512)
    local_candidate_kv = exact_kv_bytes(4214, output_tokens, 8, 256, 4, 512)
    global_candidate_kv = exact_kv_bytes(4214, output_tokens, 16, 256, 4, 256)

    def row_request_seconds(row):
        return row["cuda_event_ms"]["p50"] / 1000 * row["multiplicity"] * output_tokens / batch

    local_linear_relevance = row_request_seconds(local_qkv) * 0.25
    global_linear_relevance = (row_request_seconds(global_qkv) + row_request_seconds(global_output)) * 0.5
    local_kv_relevance = (baseline_kv["total"] - local_candidate_kv["total"]) / h200_bandwidth
    global_kv_relevance = (baseline_kv["total"] - global_candidate_kv["total"]) / h200_bandwidth

    projection_elements = 29_286_727_680
    hidden = text["hidden_size"]
    local_projection_delta = 50 * hidden * (2 * 8 * 256)
    global_projection_delta = 10 * hidden * ((32 + 2 * 4 + 32) * 256)

    result = {
        "schema_version": 1,
        "artifact": "gemma4_small_architecture_exact_shape_proxy",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "evidence_boundary": "Measured-anchored exact-shape work-relevance proxy, not candidate throughput or quality evidence.",
        "identities": {
            "model": MODEL,
            "revision": REVISION,
            "config": {"path": str(args.config), "sha256": sha256(args.config)},
            "runtime_source": {"path": str(args.runtime_source), "sha256": sha256(args.runtime_source)},
            "linear_terminal": {"path": str(args.linear_terminal), "sha256": sha256(args.linear_terminal)},
            "linear_stage": {"path": str(args.linear_stage), "sha256": sha256(args.linear_stage)},
            "endpoint_terminal": {"path": str(args.endpoint_terminal), "sha256": sha256(args.endpoint_terminal)},
            "inventory": {"path": str(args.inventory), "sha256": sha256(args.inventory)},
            "geometry_checks": expected,
        },
        "joined_baseline": {
            "geometry": {
                "hidden_size": 5376,
                "intermediate_size": 21504,
                "layers": 60,
                "local_global_cadence": "5:1",
                "local": {"layers": 50, "q_heads": 32, "kv_heads": 16, "head_dim": 256, "window": 1024},
                "global": {"layers": 10, "q_heads": 32, "kv_heads": 4, "head_dim": 512, "k_eq_v": True},
            },
            "runtime_path": "Gemma4Attention -> QKVParallelLinear -> q/k/v split -> per-head norms/RoPE -> RadixAttention -> RowParallelLinear; full-attention K is duplicated into the runtime V shard.",
            "measured_h200": {
                "endpoint_c32_service_seconds_per_request": service_seconds,
                "endpoint_completed_requests_per_second": endpoint["stock"]["completed_requests_per_second"],
                "c32_transformer_linear_seconds_per_request": 0.21676900602411478,
                "c32_head_seconds_per_request": 0.008000583905726671,
                "local_qkv_p50_ms": local_qkv["cuda_event_ms"]["p50"],
                "global_qkv_p50_ms": global_qkv["cuda_event_ms"]["p50"],
                "global_output_p50_ms": global_output["cuda_event_ms"]["p50"],
            },
            "chip": {
                accelerator_id: {
                    "compute_units": accelerators[accelerator_id]["execution"]["compute_units"],
                    "memory_bandwidth_gb_s": accelerators[accelerator_id]["memory"]["bandwidth_gb_s"],
                    "l2_mb": accelerators[accelerator_id]["cache"]["last_level_mb"],
                    "numeric_formats": accelerators[accelerator_id]["numeric_formats"],
                }
                for accelerator_id in ("nvidia-h200-sxm", "nvidia-h100-sxm", "nvidia-l40s", "nvidia-b200-sxm", "amd-mi355x")
            },
            "exact_bf16_decode_kv_read_bytes": baseline_kv,
        },
        "decision": {
            "nomination_count": 1,
            "nominated_change": "local KV heads 16 -> 8 in the 50 sliding-attention layers",
            "reason": "It clears the 5% exact-work relevance screen with an established checkpoint-uptraining method. The global-dimension alternative clears only an optimistic 5.87% sum and lacks a comparably established modest conversion path after weak exact-weight retention.",
        },
        "candidates": [
            {
                "rank": 1,
                "nomination_status": "nominated_for_one_direct_exact_shape_experiment",
                "change": "local KV heads 16 -> 8; retain 32 query heads, head_dim=256, 50 layers, and 8192-wide O projection",
                "mechanism": "Halves local K/V projection rows, cache capacity, writes, and compulsory local paged-attention reads without deleting layers, MLP width, query heads, or residual width.",
                "exact_shapes": {
                    "qkv": {"baseline": [32, 5376, 16384], "candidate": [32, 5376, 12288]},
                    "output": {"baseline_and_candidate": [32, 8192, 5376]},
                    "kv_read_bytes": {"baseline": baseline_kv, "candidate": local_candidate_kv},
                    "h200_qkv_grid": {"baseline": tile_grid(16384, h200_units), "candidate": tile_grid(12288, h200_units)},
                },
                "sampled_exact_weight_proxy": local_weights,
                "projection_element_reduction_fraction": local_projection_delta / projection_elements,
                "measured_anchored_work_relevance": {
                    "linear_seconds_per_request_if_latency_scales_with_removed_qkv_rows": local_linear_relevance,
                    "ideal_h200_bandwidth_seconds_per_request_removed": local_kv_relevance,
                    "combined_fraction_of_measured_endpoint": (local_linear_relevance + local_kv_relevance) / service_seconds,
                    "limit": "The sum is a relevance proxy. Grid underfill, overlap, cache hits, and noncritical work can prevent wall-time realization.",
                },
                "physical_risk": "At an assumed 128-column CTA tile, c32 fused-QKV drops from 128 blocks (97.0% of one H200 SM wave) to 96 (72.7%); fixed/launch latency may erase projection savings.",
                "falsifier": "On the same H200 runtime, exact [32,5376,16384] vs [32,5376,12288] QKV and matched 16-vs-8-head paged-KV rows must reduce combined candidate boundary by >=5% of 0.363303 s/request; DRAM bytes should fall near the exact delta while achieved bandwidth and active-SM waves identify underfill.",
                "post_training": "Initialize each new K/V head by averaging adjacent old heads, distill teacher attention outputs/logits on the campaign prompt distribution, and uptrain before instruction tuning. Ainslie et al. establish GQA checkpoint conversion with 5% of original pretraining compute; this is a credible upper budget, not a Gemma-specific quality transfer.",
                "prior_work": {
                    "title": "GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints",
                    "url": "https://aclanthology.org/2023.emnlp-main.298/",
                    "source_backed_claim": "Checkpoint uptraining to GQA can approach multi-head quality; the paper uses 5% of original pretraining compute.",
                    "transfer_limit": "The paper does not test Gemma 4, hybrid local/global attention, GPQA-Diamond, or TauBench.",
                },
                "quality_path": "Gate perplexity/teacher-KL and 10K retrieval first; then paired exact served checkpoints on GPQA-Diamond and TauBench with raw tool-call traces, identical tokenizer/template/seed, bootstrap uncertainty, and no more than campaign-agreed degradation.",
            },
            {
                "rank": 2,
                "nomination_status": "rejected_no_direct_experiment",
                "change": "global head_dim 512 -> 256 in the ten full-attention layers; retain 32 query heads, 4 KV heads, K=V sharing, cadence, and all MLPs",
                "mechanism": "Halves global Q/K/V/O projection width and full-context KV bytes in only the long-range layers; targets HBM traffic that remains far beyond per-chip L2 at c32.",
                "exact_shapes": {
                    "qkv": {"baseline": [32, 5376, 20480], "candidate": [32, 5376, 10240]},
                    "output": {"baseline": [32, 16384, 5376], "candidate": [32, 8192, 5376]},
                    "kv_read_bytes": {"baseline": baseline_kv, "candidate": global_candidate_kv},
                    "h200_qkv_grid": {"baseline": tile_grid(20480, h200_units), "candidate": tile_grid(10240, h200_units)},
                },
                "sampled_exact_weight_proxy": global_weights,
                "projection_element_reduction_fraction": global_projection_delta / projection_elements,
                "measured_anchored_work_relevance": {
                    "linear_seconds_per_request_if_latency_scales_with_removed_qkv_and_o_rows": global_linear_relevance,
                    "ideal_h200_bandwidth_seconds_per_request_removed": global_kv_relevance,
                    "combined_fraction_of_measured_endpoint": (global_linear_relevance + global_kv_relevance) / service_seconds,
                    "limit": "The sum is a relevance proxy. It omits attention arithmetic benefit but does not prove that removed work is on the endpoint critical path.",
                },
                "physical_risk": "The assumed c32 QKV grid falls from 160 blocks over two H200 waves to 80 blocks in one 60.6%-occupied wave; the unusual 512-head global kernel is already source-specialized, so supported candidate dispatch must be proven.",
                "falsifier": "Exact [32,5376,20480]/[32,16384,5376] versus [32,5376,10240]/[32,8192,5376] linears plus 512-vs-256 full-context paged attention must save >=5% of 0.363303 s/request, with no fallback and measured DRAM bytes/SM waves.",
                "post_training": "Use one common learned 256-D projection per global KV group to initialize Q/K/V and the inverse O map, distill full-attention outputs and logits from the frozen teacher, then short continued pretraining and instruction tuning while local layers remain unchanged initially.",
                "quality_path": "Require 10K/long-context retrieval parity before the same paired exact-server GPQA-Diamond and TauBench protocol; inspect science-answer accuracy separately from tool selection, argument validity, and multi-turn completion.",
                "rejection_reason": "Only 5.87% on an optimistic linear-plus-ideal-HBM relevance sum, while sampled direct dimension selection retains 51.9-56.7% weight energy and no scope-matched modest checkpoint conversion is established. The active H200 profile should not spend a second arm on it.",
            },
        ],
        "rejected_nearby_changes": [
            "Shortening the 1024 local window: prior exact bound caps whole-request QK/AV relevance below 1.75% even at 256 tokens.",
            "K=V global projection specialization alone: prior source-bound measured-row projection is 0.18-0.35% of the service ceiling.",
            "Generic low rank or 2:4: prior exact sampled weights fail the preregistered structure/energy gates.",
            "Changing 5:1 global cadence alone: it removes too little exact full-context work without also changing representational capacity.",
        ],
        "resource_use": {
            "wall_seconds": time.monotonic() - started,
            "provider_spend_usd": 0.0,
            "gpu_used": False,
            "bench_claim": "unavailable: claimed by gemma4_h200_critical_path_profile before this project's atomic claim",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "wall_seconds": result["resource_use"]["wall_seconds"], "candidates": [candidate["change"] for candidate in result["candidates"]]}, indent=2))


if __name__ == "__main__":
    main()
