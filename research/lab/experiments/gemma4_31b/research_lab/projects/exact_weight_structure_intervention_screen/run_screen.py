#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import mmap
import os
import re
import resource
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


TARGET = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
PROJECTION_RE = re.compile(
    r"^model\.language_model\.layers\.(\d+)\."
    r"(self_attn\.(q_proj|k_proj|v_proj|o_proj)|mlp\.(gate_proj|up_proj|down_proj))\.weight$"
)
CLASS_SPECS = {
    "sliding_qkv": {"layers": [0, 28, 58], "parts": ["q_proj", "k_proj", "v_proj"], "shape": [16384, 5376], "multiplicity": 50},
    "global_qkv": {"layers": [5, 29, 59], "parts": ["q_proj", "k_proj"], "shape": [18432, 5376], "multiplicity": 10},
    "gate_up": {"layers": [0, 29, 59], "parts": ["gate_proj", "up_proj"], "shape": [43008, 5376], "multiplicity": 60},
    "sliding_o": {"layers": [0, 28, 58], "parts": ["o_proj"], "shape": [5376, 8192], "multiplicity": 50},
    "global_o": {"layers": [5, 29, 59], "parts": ["o_proj"], "shape": [5376, 16384], "multiplicity": 10},
    "down": {"layers": [0, 29, 59], "parts": ["down_proj"], "shape": [5376, 21504], "multiplicity": 60},
}
COMPONENT_SHAPES_LOGICAL = [
    [5376, 16384],
    [5376, 20480],
    [5376, 43008],
    [8192, 5376],
    [16384, 5376],
    [21504, 5376],
]
SPECTRAL_COLUMNS = 384
SPECTRAL_RANKS = [128, 256]
CHUNK_ROWS = 256
MIN_RETAINED_ENERGY = 0.95
MIN_WEIGHT_BYTE_REDUCTION = 0.20
MIN_NATURAL_24_COMPLIANCE = 0.90


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def quantiles(values):
    q = np.quantile(np.asarray(values, dtype=np.float64), [0.0, 0.5, 0.9, 0.99, 1.0])
    return {k: float(v) for k, v in zip(["min", "p50", "p90", "p99", "max"], q)}


class SafeShard:
    def __init__(self, path):
        self.path = path
        self.file = path.open("rb")
        self.mm = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        self.header_len = struct.unpack("<Q", self.mm[:8])[0]
        self.data_base = 8 + self.header_len
        self.header = json.loads(self.mm[8:self.data_base])

    def close(self):
        self.mm.close()
        self.file.close()

    def rows(self, name, start, end):
        meta = self.header[name]
        if meta["dtype"] != "BF16" or len(meta["shape"]) != 2:
            raise ValueError(f"unsupported tensor {name}: {meta}")
        rows, cols = meta["shape"]
        if not (0 <= start <= end <= rows):
            raise ValueError((name, start, end, rows))
        begin = self.data_base + meta["data_offsets"][0] + start * cols * 2
        finish = self.data_base + meta["data_offsets"][0] + end * cols * 2
        raw = np.frombuffer(self.mm, dtype="<u2", count=(end - start) * cols, offset=begin)
        u32 = raw.astype(np.uint32)
        return (u32 << 16).view(np.float32).reshape(end - start, cols)


def tensor_name(layer, part):
    stem = "self_attn" if part in {"q_proj", "k_proj", "v_proj", "o_proj"} else "mlp"
    return f"model.language_model.layers.{layer}.{stem}.{part}.weight"


def evenly_spaced_indices(size, count):
    if count > size:
        raise ValueError((size, count))
    return np.floor((np.arange(count, dtype=np.float64) + 0.5) * size / count).astype(np.int64)


def scan_tensor(shard, name, spectral_indices, deadline):
    shape = shard.header[name]["shape"]
    rows, cols = shape
    total_sq = 0.0
    zero_count = 0
    input_groups = 0
    input_natural = 0
    input_discard_sq = 0.0
    output_groups = 0
    output_natural = 0
    output_discard_sq = 0.0
    row_sq = np.zeros(rows, dtype=np.float64)
    row_discard_input = np.zeros(rows, dtype=np.float64)
    row_discard_output = np.zeros(rows, dtype=np.float64)
    gram = np.zeros((len(spectral_indices), len(spectral_indices)), dtype=np.float64)

    for start in range(0, rows, CHUNK_ROWS):
        if time.monotonic() > deadline:
            raise TimeoutError(f"wall-clock deadline reached while reading {name}")
        end = min(rows, start + CHUNK_ROWS)
        x = shard.rows(name, start, end)
        sq = np.square(x, dtype=np.float32)
        row_energy = sq.sum(axis=1, dtype=np.float64)
        row_sq[start:end] = row_energy
        total_sq += float(row_energy.sum())
        zero_count += int(np.count_nonzero(x == 0.0))

        groups_in = sq.reshape(end - start, cols // 4, 4)
        input_groups += groups_in.shape[0] * groups_in.shape[1]
        input_natural += int(np.count_nonzero(np.count_nonzero(groups_in, axis=2) <= 2))
        dropped_in = np.partition(groups_in, 1, axis=2)[:, :, :2].sum(axis=(1, 2), dtype=np.float64)
        row_discard_input[start:end] = dropped_in
        input_discard_sq += float(dropped_in.sum())

        if (end - start) % 4 != 0:
            raise ValueError(f"row chunk not divisible by four for {name}")
        groups_out = sq.reshape((end - start) // 4, 4, cols)
        output_groups += groups_out.shape[0] * groups_out.shape[2]
        output_natural += int(np.count_nonzero(np.count_nonzero(groups_out, axis=1) <= 2))
        drop_idx = np.argpartition(groups_out, 1, axis=1)[:, :2, :]
        drop_mask = np.zeros(groups_out.shape, dtype=bool)
        np.put_along_axis(drop_mask, drop_idx, True, axis=1)
        dropped_rows = np.where(drop_mask, groups_out, 0.0).sum(axis=2, dtype=np.float64).reshape(-1)
        row_discard_output[start:end] = dropped_rows
        output_discard_sq += float(dropped_rows.sum())

        b = x[:, spectral_indices].astype(np.float64, copy=False)
        gram += b.T @ b

    def layout(discard, row_discard, natural, groups):
        row_rel = np.sqrt(np.divide(row_discard, row_sq, out=np.zeros_like(row_sq), where=row_sq > 0))
        trim_n = max(1, int(math.ceil(rows * 0.001)))
        outliers = np.argpartition(row_sq, -trim_n)[-trim_n:]
        trimmed_total = total_sq - float(row_sq[outliers].sum())
        trimmed_discard = discard - float(row_discard[outliers].sum())
        return {
            "group_count": groups,
            "natural_2of4_compliance": natural / groups,
            "magnitude_2of4_relative_frobenius_error": math.sqrt(discard / total_sq),
            "magnitude_2of4_retained_energy": 1.0 - discard / total_sq,
            "per_row_relative_error_quantiles": quantiles(row_rel),
            "outlier_sensitivity": {
                "definition": "relative Frobenius error after excluding the top 0.1% output rows by original row energy",
                "excluded_rows": trim_n,
                "trimmed_relative_frobenius_error": math.sqrt(trimmed_discard / trimmed_total),
            },
        }

    return {
        "elements": rows * cols,
        "zero_count": zero_count,
        "zero_density": zero_count / (rows * cols),
        "total_squared_frobenius": total_sq,
        "input_contraction_groups": layout(input_discard_sq, row_discard_input, input_natural, input_groups),
        "output_contraction_groups": layout(output_discard_sq, row_discard_output, output_natural, output_groups),
        "_gram": gram,
        "_row_sq": row_sq,
        "_row_discard_input": row_discard_input,
        "_row_discard_output": row_discard_output,
    }


def aggregate_class(class_name, layer, parts, results, gram):
    total_elements = sum(r["elements"] for r in results)
    total_sq = sum(r["total_squared_frobenius"] for r in results)
    zeros = sum(r["zero_count"] for r in results)
    row_sq = np.concatenate([r["_row_sq"] for r in results])
    agg = {
        "class": class_name,
        "layer": layer,
        "tensor_names": [tensor_name(layer, p) for p in parts],
        "shape": CLASS_SPECS[class_name]["shape"],
        "elements": total_elements,
        "zero_density": zeros / total_elements,
    }
    for key, discard_key in [
        ("input_contraction_groups", "_row_discard_input"),
        ("output_contraction_groups", "_row_discard_output"),
    ]:
        groups = sum(r[key]["group_count"] for r in results)
        natural = sum(r[key]["natural_2of4_compliance"] * r[key]["group_count"] for r in results)
        discard = np.concatenate([r[discard_key] for r in results])
        discard_sum = float(discard.sum())
        row_rel = np.sqrt(np.divide(discard, row_sq, out=np.zeros_like(row_sq), where=row_sq > 0))
        trim_n = max(1, int(math.ceil(len(row_sq) * 0.001)))
        outliers = np.argpartition(row_sq, -trim_n)[-trim_n:]
        agg[key] = {
            "group_count": groups,
            "natural_2of4_compliance": natural / groups,
            "magnitude_2of4_relative_frobenius_error": math.sqrt(discard_sum / total_sq),
            "magnitude_2of4_retained_energy": 1.0 - discard_sum / total_sq,
            "per_row_relative_error_quantiles": quantiles(row_rel),
            "outlier_sensitivity": {
                "definition": "relative Frobenius error after excluding the top 0.1% aggregate output rows by original row energy",
                "excluded_rows": trim_n,
                "trimmed_relative_frobenius_error": math.sqrt(
                    (discard_sum - float(discard[outliers].sum())) /
                    (total_sq - float(row_sq[outliers].sum()))
                ),
            },
        }

    eigenvalues = np.linalg.eigvalsh(gram)
    eigenvalues = np.maximum(eigenvalues[::-1], 0.0)
    sketch_energy = float(eigenvalues.sum())
    agg["low_rank_column_sketch"] = {
        "method": "exact eigenspectrum of B^T B where B contains all output rows and 384 deterministic evenly spaced input columns",
        "column_count": SPECTRAL_COLUMNS,
        "evidence_limit": "bounded deterministic spectral sketch; not a full-matrix reconstruction guarantee",
        "curves": [
            {
                "rank": rank,
                "retained_sketch_energy": float(eigenvalues[:rank].sum() / sketch_energy),
                "relative_sketch_frobenius_error": math.sqrt(float(eigenvalues[rank:].sum() / sketch_energy)),
            }
            for rank in SPECTRAL_RANKS
        ],
    }
    return agg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--terminal", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--components", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wall-minutes", type=float, default=48.0)
    args = parser.parse_args()
    started_wall = time.monotonic()
    started_cpu = resource.getrusage(resource.RUSAGE_SELF)
    deadline = started_wall + args.wall_minutes * 60

    terminal = json.loads(args.terminal.read_text())
    geometry = json.loads(args.geometry.read_text())
    components = json.loads(args.components.read_text())
    index_path = args.checkpoint / "model.safetensors.index.json"
    index = json.loads(index_path.read_text())
    terminal_files = {x["path"]: x for x in terminal["files"]}
    assertions = {
        "checkpoint_terminal_pass": terminal["pass"] is True,
        "target_exact": terminal["model"] == TARGET and terminal["revision"] == REVISION,
        "index_hash_matches_terminal": sha256(index_path) == terminal_files[index_path.name]["sha256"],
        "geometry_target_exact": geometry["identities"]["target_model"]["id"] == TARGET and geometry["identities"]["target_model"]["revision"] == REVISION,
        "component_target_exact": components["provenance"]["exact_target"] == f"{TARGET}@{REVISION}",
        "component_shapes_exact": components["scope"]["shapes"] == COMPONENT_SHAPES_LOGICAL,
        "no_cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES") == "",
    }
    if not all(assertions.values()):
        raise RuntimeError(f"identity assertion failed: {assertions}")

    shard_names = sorted(set(index["weight_map"].values()))
    shards = {name: SafeShard(args.checkpoint / name) for name in shard_names}
    try:
        inventory = []
        projection_names = []
        for name, shard_name in sorted(index["weight_map"].items()):
            match = PROJECTION_RE.match(name)
            if not match:
                continue
            meta = shards[shard_name].header[name]
            absolute = [shards[shard_name].data_base + x for x in meta["data_offsets"]]
            inventory.append({
                "name": name,
                "layer": int(match.group(1)),
                "projection": match.group(3) or match.group(4),
                "shape": meta["shape"],
                "dtype": meta["dtype"],
                "shard": shard_name,
                "source_shard_bytes": terminal_files[shard_name]["bytes"],
                "source_shard_sha256": terminal_files[shard_name]["sha256"],
                "data_offsets_relative": meta["data_offsets"],
                "byte_range_absolute_half_open": absolute,
            })
            projection_names.append(name)

        samples = []
        tensor_results = {}
        for class_name, spec in CLASS_SPECS.items():
            expected_rows, expected_cols = spec["shape"]
            spectral_indices = evenly_spaced_indices(expected_cols, SPECTRAL_COLUMNS)
            for layer in spec["layers"]:
                part_results = []
                class_gram = np.zeros((SPECTRAL_COLUMNS, SPECTRAL_COLUMNS), dtype=np.float64)
                actual_rows = 0
                for part in spec["parts"]:
                    name = tensor_name(layer, part)
                    shard_name = index["weight_map"][name]
                    meta = shards[shard_name].header[name]
                    if meta["shape"][1] != expected_cols:
                        raise ValueError(f"class geometry mismatch {class_name} {name} {meta['shape']}")
                    result = scan_tensor(shards[shard_name], name, spectral_indices, deadline)
                    actual_rows += meta["shape"][0]
                    class_gram += result["_gram"]
                    part_results.append(result)
                    tensor_results[name] = {
                        k: v for k, v in result.items() if not k.startswith("_")
                    }
                if actual_rows != expected_rows:
                    raise ValueError(f"class row geometry mismatch {class_name} layer {layer}: {actual_rows} != {expected_rows}")
                samples.append(aggregate_class(class_name, layer, spec["parts"], part_results, class_gram))

        dense_projection_elements = sum(
            spec["multiplicity"] * spec["shape"][0] * spec["shape"][1]
            for spec in CLASS_SPECS.values()
        )
        dense_projection_bytes = 2 * dense_projection_elements
        index_overhead = terminal_files["model.safetensors.index.json"]["bytes"]
        sparse_24_bytes = int(1.125 * dense_projection_elements) + index_overhead
        low_rank = []
        for rank in SPECTRAL_RANKS:
            factor_elements = sum(
                spec["multiplicity"] * rank * (spec["shape"][0] + spec["shape"][1])
                for spec in CLASS_SPECS.values()
            )
            factor_bytes = 2 * factor_elements + index_overhead
            low_rank.append({
                "rank": rank,
                "factor_bf16_bytes_per_decode_step": factor_bytes,
                "weight_byte_reduction_fraction": 1.0 - factor_bytes / dense_projection_bytes,
                "minimum_retained_sketch_energy_across_samples": min(
                    next(c["retained_sketch_energy"] for c in s["low_rank_column_sketch"]["curves"] if c["rank"] == rank)
                    for s in samples
                ),
                "maximum_relative_sketch_error_across_samples": max(
                    next(c["relative_sketch_frobenius_error"] for c in s["low_rank_column_sketch"]["curves"] if c["rank"] == rank)
                    for s in samples
                ),
            })

        sparse_min_natural = min(
            min(s[k]["natural_2of4_compliance"] for k in ["input_contraction_groups", "output_contraction_groups"])
            for s in samples
        )
        sparse_min_retained = min(
            max(s[k]["magnitude_2of4_retained_energy"] for k in ["input_contraction_groups", "output_contraction_groups"])
            for s in samples
        )
        sparse_reduction = 1.0 - sparse_24_bytes / dense_projection_bytes
        sparse_gates = {
            "coverage_complete": len(samples) == 18 and len(tensor_results) == 30,
            "consistent_natural_structure": sparse_min_natural >= MIN_NATURAL_24_COMPLIANCE,
            "magnitude_proxy_retained_energy": sparse_min_retained >= MIN_RETAINED_ENERGY,
            "architecture_weight_byte_reduction": sparse_reduction >= MIN_WEIGHT_BYTE_REDUCTION,
            "concrete_h200_path_named": True,
            "later_quality_plan_named": True,
        }
        low_rank_best = max(low_rank, key=lambda x: x["weight_byte_reduction_fraction"] if x["minimum_retained_sketch_energy_across_samples"] >= MIN_RETAINED_ENERGY else -1)
        low_rank_gates = {
            "coverage_complete": len(samples) == 18,
            "consistent_sketch_energy": low_rank_best["minimum_retained_sketch_energy_across_samples"] >= MIN_RETAINED_ENERGY,
            "architecture_weight_byte_reduction": low_rank_best["weight_byte_reduction_fraction"] >= MIN_WEIGHT_BYTE_REDUCTION,
            "concrete_h200_path_named": True,
            "later_quality_plan_named": True,
        }

        candidate = {"type": "none", "reason": "No intervention passed every preregistered structure/error, byte-reduction, consumer-path, and later-quality gate."}
        if all(sparse_gates.values()):
            candidate = {
                "type": "magnitude_2of4_bf16",
                "consumer_path": "NVIDIA Hopper Sparse Tensor Cores via cuSPARSELt structured 2:4 BF16",
                "quality_plan": "calibrate/prune representative raw requests, fine-tune the exact checkpoint, then run the bound raw-capture normalizer/scorer before any endpoint claim",
            }
        elif all(low_rank_gates.values()):
            candidate = {
                "type": "bf16_low_rank_factorization",
                "rank": low_rank_best["rank"],
                "consumer_path": "two standard BF16 GEMMs on H200, requiring a later exact production-runtime adapter and matched component benchmark",
                "quality_plan": "factorize and fine-tune the exact checkpoint, then run the bound raw-capture normalizer/scorer before any endpoint claim",
            }

        checkpoint_bytes = geometry["target_text_geometry_measured_from_config"]["bf16_weight_bytes_metadata"]
        max_mechanism_reduction = max(
            dense_projection_bytes - sparse_24_bytes,
            *(dense_projection_bytes - x["factor_bf16_bytes_per_decode_step"] for x in low_rank),
        )
        finished_cpu = resource.getrusage(resource.RUSAGE_SELF)
        artifact = {
            "schema_version": 1,
            "artifact": "exact_gemma4_31b_weight_structure_screen",
            "generated_utc": utc_now(),
            "evidence_labels": {
                "inventory_and_2of4": "measured from exact checkpoint bytes",
                "magnitude_pruning": "synthetic deterministic non-quality-preserving proxy",
                "low_rank": "bounded deterministic spectral sketch, not full reconstruction",
                "byte_accounting": "derived analytical upper bound",
                "consumer_paths": "capability prior, untested in this project",
            },
            "scope_limits": [
                "No CUDA, provider mutation, checkpoint write, quality run, performance run, or endpoint claim.",
                "Low-rank energy is measured only on deterministic column sketches and is not extrapolated into full-matrix quality.",
                "Weight-byte savings do not imply equal wall-time or request-cost savings.",
            ],
            "identities": {
                "target": f"{TARGET}@{REVISION}",
                "checkpoint_terminal": str(args.terminal.resolve()),
                "checkpoint_terminal_sha256": sha256(args.terminal),
                "model_index_sha256": terminal_files["model.safetensors.index.json"]["sha256"],
                "source_shards": {k: terminal_files[k] for k in shard_names},
                "geometry_sha256": sha256(args.geometry),
                "component_packet_sha256": sha256(args.components),
                "run_script_sha256": sha256(Path(__file__)),
                "numpy_version": np.__version__,
            },
            "identity_assertions": assertions,
            "method": {
                "sample_policy": CLASS_SPECS,
                "exact_layout_observation": "Full-attention layers contain q_proj [16384,5376] and k_proj [2048,5376] but no v_proj tensor; the measured global aggregate is therefore [18432,5376], while the cited synthetic component packet records logical [5376,20480]. No missing tensor is imputed.",
                "cited_component_shapes_input_output": COMPONENT_SHAPES_LOGICAL,
                "chunk_rows": CHUNK_ROWS,
                "spectral_columns": SPECTRAL_COLUMNS,
                "spectral_column_selection": "floor((i+0.5)*input_width/384), i=0..383",
                "spectral_ranks": SPECTRAL_RANKS,
                "promotion_thresholds": {
                    "minimum_natural_2of4_compliance": MIN_NATURAL_24_COMPLIANCE,
                    "minimum_proxy_or_sketch_retained_energy": MIN_RETAINED_ENERGY,
                    "minimum_architecture_weight_byte_reduction": MIN_WEIGHT_BYTE_REDUCTION,
                },
            },
            "coverage": {
                "included_inventory_tensors": len(inventory),
                "included_inventory_elements": sum(int(np.prod(x["shape"])) for x in inventory),
                "sampled_underlying_tensors": len(tensor_results),
                "sampled_class_layer_aggregates": len(samples),
                "architectural_classes": list(CLASS_SPECS),
            },
            "tensor_inventory": inventory,
            "sampled_tensor_results": tensor_results,
            "class_layer_results": samples,
            "architecture_weighted_byte_upper_bounds": {
                "dense_projection_bf16_bytes_per_decode_step": dense_projection_bytes,
                "sparse_2of4": {
                    "assumption": "two BF16 values plus four metadata bits per group of four dense values, plus the full exact index size conservatively",
                    "represented_bytes_per_decode_step": sparse_24_bytes,
                    "weight_byte_reduction_fraction": sparse_reduction,
                },
                "low_rank": low_rank,
                "exact_model_bf16_weight_bytes_metadata": checkpoint_bytes,
                "maximum_tested_mechanism_reduction_as_fraction_of_whole_model_weight_bytes": max_mechanism_reduction / checkpoint_bytes,
                "campaign_whole_request_relevance_threshold": 0.05,
                "threshold_comparison_limit": "Weight bytes only; this is a maximum relevance upper bound, not a request-time estimate.",
            },
            "promotion": {
                "sparse_2of4_gates": sparse_gates,
                "low_rank_gates": low_rank_gates,
                "future_candidate": candidate,
            },
            "resources": {
                "wall_seconds": time.monotonic() - started_wall,
                "user_cpu_seconds": finished_cpu.ru_utime - started_cpu.ru_utime,
                "system_cpu_seconds": finished_cpu.ru_stime - started_cpu.ru_stime,
                "max_rss_kib": finished_cpu.ru_maxrss,
                "provider_spend_usd": 0,
                "cuda_used": False,
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temp_output = args.output.with_suffix(".json.partial")
        temp_output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
        os.replace(temp_output, args.output)
        print(json.dumps({
            "output": str(args.output),
            "candidate": candidate,
            "coverage": artifact["coverage"],
            "resources": artifact["resources"],
        }, indent=2))
    finally:
        for shard in shards.values():
            shard.close()


if __name__ == "__main__":
    main()
