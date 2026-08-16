#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import tempfile
import time
from dataclasses import dataclass

import numpy as np
import torch
from safetensors import safe_open


VOCAB = 262_144
HIDDEN = 5_376
DEPTHS = 12
BATCH = 32
BF16_BYTES = 2
H200_HBM_BYTES_PER_SECOND = 4.8e12
H200_BF16_FLOPS_PER_SECOND = 989.5e12
H200_L2_BYTES = 60 * 1024 * 1024
MEASURED_DENSE_US_PER_STEP = 8_310.9596
MEASURED_HEAD_PROFILE_FRACTION = 0.05248713500841422
QUALIFIED_SECONDS_PER_REQUEST = 0.625149101968745
PLANNING_USD_PER_GPU_HOUR = 3.25


@dataclass(frozen=True)
class Inputs:
    checkpoint: pathlib.Path
    hidden_rows: pathlib.Path
    output: pathlib.Path
    clusters: tuple[int, ...]
    probes: tuple[int, ...]
    projection_dims: int
    kmeans_iterations: int
    seed: int


def sha256(path: pathlib.Path, chunk_bytes: int = 16 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def exact_balanced_split(
    projected: np.ndarray, token_ids: np.ndarray, iterations: int
) -> tuple[np.ndarray, np.ndarray]:
    points = projected[token_ids]
    center = points.mean(axis=0)
    first = int(np.argmax(np.sum((points - center) ** 2, axis=1)))
    second = int(np.argmax(np.sum((points - points[first]) ** 2, axis=1)))
    left_center = points[first].copy()
    right_center = points[second].copy()
    midpoint = len(token_ids) // 2
    for _ in range(iterations):
        direction = right_center - left_center
        if not np.any(direction):
            direction = np.zeros_like(direction)
            direction[0] = 1.0
        scores = points @ direction
        partition = np.argpartition(scores, midpoint)
        left_local = partition[:midpoint]
        right_local = partition[midpoint:]
        left_center = points[left_local].mean(axis=0)
        right_center = points[right_local].mean(axis=0)
    return token_ids[left_local], token_ids[right_local]


def balanced_hierarchical_kmeans(
    projected: np.ndarray, cluster_count: int, iterations: int
) -> np.ndarray:
    if cluster_count <= 0 or cluster_count & (cluster_count - 1):
        raise ValueError("cluster_count must be a positive power of two")
    if len(projected) % cluster_count:
        raise ValueError("rows must divide evenly into cluster_count")
    groups = [np.arange(len(projected), dtype=np.int32)]
    while len(groups) < cluster_count:
        children: list[np.ndarray] = []
        for group in groups:
            children.extend(exact_balanced_split(projected, group, iterations))
        groups = children
    return np.stack(groups)


def centroids_for(
    weight: torch.Tensor, tokens_by_cluster: np.ndarray, group_batch: int = 8
) -> torch.Tensor:
    rows: list[torch.Tensor] = []
    for start in range(0, len(tokens_by_cluster), group_batch):
        token_ids = torch.from_numpy(
            tokens_by_cluster[start : start + group_batch].astype(np.int64)
        )
        rows.append(weight[token_ids].mean(dim=1))
    return torch.cat(rows, dim=0)


def topk_ids(values: torch.Tensor, k: int) -> torch.Tensor:
    return torch.topk(values, k=k, dim=1, sorted=True).indices


def physical_cost(
    *,
    clusters: int,
    probes: int,
    cluster_size: int,
    unique_clusters_per_m32: int,
) -> dict:
    rows = DEPTHS * BATCH
    candidates_per_query = probes * cluster_size
    coarse_flops = 2 * rows * HIDDEN * clusters
    candidate_flops = 2 * rows * HIDDEN * candidates_per_query
    coarse_bytes = (
        clusters * HIDDEN * BF16_BYTES
        + rows * HIDDEN * BF16_BYTES
        + rows * clusters * BF16_BYTES
    )
    candidate_bytes_per_depth = (
        unique_clusters_per_m32 * cluster_size * HIDDEN * BF16_BYTES
        + BATCH * HIDDEN * BF16_BYTES
        + BATCH * candidates_per_query * BF16_BYTES
    )
    total_bytes = coarse_bytes + DEPTHS * candidate_bytes_per_depth
    compute_us = (coarse_flops + candidate_flops) / H200_BF16_FLOPS_PER_SECOND * 1e6
    hbm_us = total_bytes / H200_HBM_BYTES_PER_SECOND * 1e6
    roofline_us = max(compute_us, hbm_us)
    dense_ratio = roofline_us / MEASURED_DENSE_US_PER_STEP
    projected_request_saving = (
        QUALIFIED_SECONDS_PER_REQUEST
        * MEASURED_HEAD_PROFILE_FRACTION
        * max(0.0, 1.0 - dense_ratio)
    )
    projected_seconds_per_request = (
        QUALIFIED_SECONDS_PER_REQUEST - projected_request_saving
    )
    tokens_per_request = (17_120 + 117_728) / 32 + 358
    projected_usd_per_million_tokens = (
        PLANNING_USD_PER_GPU_HOUR
        * projected_seconds_per_request
        / 3_600
        / tokens_per_request
        * 1_000_000
    )
    return {
        "candidate_flops_per_12_depth_step": coarse_flops + candidate_flops,
        "candidate_hbm_bytes_per_12_depth_step": total_bytes,
        "candidate_compute_floor_us": compute_us,
        "candidate_hbm_floor_us": hbm_us,
        "candidate_roofline_floor_us": roofline_us,
        "candidate_to_measured_dense_time_ratio_floor": dense_ratio,
        "cluster_score_flops": coarse_flops,
        "candidate_score_flops": candidate_flops,
        "candidates_per_query": candidates_per_query,
        "unique_candidate_clusters_per_m32_fixture": unique_clusters_per_m32,
        "projected_seconds_per_request_if_floor_transfers": projected_seconds_per_request,
        "projected_usd_per_million_total_tokens_if_floor_transfers": projected_usd_per_million_tokens,
        "launch_model": {
            "dense_12xm32": 12,
            "grouped_exact": 1,
            "retrieval": 4,
            "retrieval_stages": [
                "cluster_score",
                "multiprobe_select",
                "ragged_candidate_score",
                "candidate_topk_or_verifier_decision",
            ],
        },
    }


def evaluate_geometry(
    *,
    fixture: str,
    hidden: torch.Tensor,
    dense_logits: torch.Tensor,
    dense_topk: torch.Tensor,
    weight: torch.Tensor,
    leaf_tokens: np.ndarray,
    leaf_clusters: int,
    clusters: int,
    probes: tuple[int, ...],
    top_k: int,
) -> tuple[list[dict], dict]:
    merge = leaf_clusters // clusters
    tokens_by_cluster = leaf_tokens.reshape(
        clusters, merge * leaf_tokens.shape[1]
    )
    centroid_start = time.perf_counter()
    centroids = centroids_for(weight, tokens_by_cluster)
    centroid_seconds = time.perf_counter() - centroid_start
    cluster_scores = hidden @ centroids.T
    max_probes = min(max(probes), clusters)
    ranked_clusters = topk_ids(cluster_scores, max_probes).numpy()
    dense_topk_np = dense_topk.numpy()
    dense_logits_np = dense_logits.numpy()
    rows: list[dict] = []
    for probe_count in probes:
        if probe_count > clusters:
            continue
        candidate_topk = np.empty_like(dense_topk_np)
        retrieved_dense_topk = 0
        unique_clusters: set[int] = set()
        for query in range(len(hidden)):
            selected_clusters = ranked_clusters[query, :probe_count]
            unique_clusters.update(int(value) for value in selected_clusters)
            candidates = tokens_by_cluster[selected_clusters].reshape(-1)
            candidate_values = dense_logits_np[query, candidates]
            take = min(top_k, len(candidates))
            local = np.argpartition(candidate_values, -take)[-take:]
            ordered = local[np.argsort(candidate_values[local])[::-1]]
            predicted = candidates[ordered]
            if take < top_k:
                predicted = np.pad(predicted, (0, top_k - take), constant_values=-1)
            candidate_topk[query] = predicted
            retrieved_dense_topk += len(
                set(int(x) for x in dense_topk_np[query])
                & set(int(x) for x in candidates)
            )
        top1_matches = candidate_topk[:, 0] == dense_topk_np[:, 0]
        overlap = sum(
            len(set(map(int, candidate_topk[i])) & set(map(int, dense_topk_np[i])))
            for i in range(len(hidden))
        )
        cost = physical_cost(
            clusters=clusters,
            probes=probe_count,
            cluster_size=tokens_by_cluster.shape[1],
            unique_clusters_per_m32=len(unique_clusters),
        )
        rows.append(
            {
                "fixture": fixture,
                "clusters": clusters,
                "cluster_size": int(tokens_by_cluster.shape[1]),
                "probes": probe_count,
                "candidates_per_query": int(
                    probe_count * tokens_by_cluster.shape[1]
                ),
                "candidate_fraction_of_vocabulary": (
                    probe_count * tokens_by_cluster.shape[1] / VOCAB
                ),
                "top1_recall": float(top1_matches.mean()),
                "top10_retrieval_recall": retrieved_dense_topk
                / (len(hidden) * top_k),
                "top10_output_overlap": overlap / (len(hidden) * top_k),
                "verifier_decision_recall": float(top1_matches.mean()),
                "verifier_decision_divergence": float(1.0 - top1_matches.mean()),
                "all_32_positions_equivalent": bool(top1_matches.all()),
                "derived_independent_12_position_equivalence": float(
                    top1_matches.mean() ** DEPTHS
                ),
                "physical_cost_model": cost,
            }
        )
    return rows, {
        "clusters": clusters,
        "cluster_size": int(tokens_by_cluster.shape[1]),
        "centroid_build_seconds": centroid_seconds,
        "centroid_bytes_fp32_offline": int(centroids.numel() * 4),
        "centroid_bytes_bf16_runtime": int(centroids.numel() * BF16_BYTES),
    }


def synthetic_queries(
    weight: torch.Tensor,
    *,
    rows: int,
    target_norm: float,
    seed: int,
    mode: str,
) -> tuple[torch.Tensor, dict]:
    generator = torch.Generator(device="cpu").manual_seed(seed)
    if mode == "embedding_mixture":
        basis_per_query = 4
        token_ids = torch.randperm(VOCAB, generator=generator)[
            : rows * basis_per_query
        ].reshape(rows, basis_per_query)
        coefficients = torch.randn(
            rows, basis_per_query, generator=generator, dtype=torch.float32
        )
        queries = (
            weight[token_ids] * coefficients[:, :, None]
        ).sum(dim=1)
        provenance = {
            "mode": mode,
            "basis_per_query": basis_per_query,
            "token_ids_sha256": hashlib.sha256(
                token_ids.numpy().tobytes()
            ).hexdigest(),
            "coefficients_sha256": hashlib.sha256(
                coefficients.numpy().tobytes()
            ).hexdigest(),
        }
    elif mode == "isotropic":
        queries = torch.randn(
            rows, HIDDEN, generator=generator, dtype=torch.float32
        )
        provenance = {"mode": mode}
    else:
        raise ValueError(f"unsupported synthetic query mode: {mode}")
    queries *= target_norm / queries.norm(dim=1, keepdim=True)
    provenance.update(
        {
            "rows": rows,
            "seed": seed,
            "target_l2_norm": target_norm,
            "query_sha256": hashlib.sha256(
                queries.numpy().tobytes()
            ).hexdigest(),
        }
    )
    return queries, provenance


def grouped_exact_baseline() -> dict:
    useful_flops = 2 * DEPTHS * BATCH * HIDDEN * VOCAB
    activations = DEPTHS * BATCH * HIDDEN * BF16_BYTES
    weight = VOCAB * HIDDEN * BF16_BYTES
    output = DEPTHS * BATCH * VOCAB * BF16_BYTES
    ideal_bytes = weight + activations + output
    compute_us = useful_flops / H200_BF16_FLOPS_PER_SECOND * 1e6
    hbm_us = ideal_bytes / H200_HBM_BYTES_PER_SECOND * 1e6
    return {
        "dense_12xm32_measured": {
            "calls_per_step": 12,
            "measured_us_per_step": MEASURED_DENSE_US_PER_STEP,
            "useful_flops_per_step": useful_flops,
            "sequential_compulsory_bytes_per_step": DEPTHS * weight
            + activations
            + output,
            "measured_profile_window_fraction": MEASURED_HEAD_PROFILE_FRACTION,
        },
        "grouped_exact_ideal_reuse": {
            "calls_per_step": 1,
            "useful_flops_per_step": useful_flops,
            "ideal_bytes_per_step": ideal_bytes,
            "compute_floor_us": compute_us,
            "hbm_floor_us": hbm_us,
            "roofline_floor_us": max(compute_us, hbm_us),
            "status": "analytical floor; the independent grouped project has compiled but not executed",
        },
    }


def run(inputs: Inputs) -> dict:
    torch.set_num_threads(max(1, min(os.cpu_count() or 1, 32)))
    started = time.time()
    timing: dict[str, float] = {}
    with safe_open(inputs.checkpoint, framework="pt", device="cpu") as handle:
        start = time.perf_counter()
        weight_bf16 = handle.get_tensor(
            "model.language_model.embed_tokens.weight"
        )
        weight = weight_bf16.float()
        timing["embedding_load_and_fp32_conversion_seconds"] = (
            time.perf_counter() - start
        )
    hidden_bf16 = torch.load(
        inputs.hidden_rows, map_location="cpu", weights_only=True
    )
    captured_hidden = hidden_bf16.float()
    if tuple(weight.shape) != (VOCAB, HIDDEN):
        raise RuntimeError(f"unexpected embedding shape: {tuple(weight.shape)}")
    if tuple(captured_hidden.shape) != (BATCH, HIDDEN):
        raise RuntimeError(
            f"unexpected hidden shape: {tuple(captured_hidden.shape)}"
        )
    unique_captured_rows = int(torch.unique(captured_hidden, dim=0).shape[0])
    captured_fixture_valid = unique_captured_rows >= BATCH // 2

    generator = torch.Generator(device="cpu").manual_seed(inputs.seed)
    random_projection = torch.randn(
        HIDDEN, inputs.projection_dims, generator=generator, dtype=torch.float32
    ) / math.sqrt(inputs.projection_dims)
    start = time.perf_counter()
    projected = (weight @ random_projection).numpy()
    timing["embedding_projection_seconds"] = time.perf_counter() - start

    maximum_clusters = max(inputs.clusters)
    start = time.perf_counter()
    leaf_tokens = balanced_hierarchical_kmeans(
        projected, maximum_clusters, inputs.kmeans_iterations
    )
    timing["balanced_hierarchical_kmeans_seconds"] = time.perf_counter() - start
    del projected

    target_norm = float(captured_hidden.norm(dim=1).median())
    evaluation_fixtures: dict[str, torch.Tensor] = {}
    fixture_provenance: dict[str, dict] = {}
    if captured_fixture_valid:
        evaluation_fixtures["captured_actual_consumer"] = captured_hidden
        fixture_provenance["captured_actual_consumer"] = {
            "mode": "actual_consumer_capture",
            "rows": len(captured_hidden),
        }
    else:
        for offset, mode in enumerate(("embedding_mixture", "isotropic"), 1):
            query, provenance = synthetic_queries(
                weight,
                rows=BATCH,
                target_norm=target_norm,
                seed=inputs.seed + offset,
                mode=mode,
            )
            evaluation_fixtures[f"synthetic_{mode}"] = query
            fixture_provenance[f"synthetic_{mode}"] = provenance

    dense_oracles: dict[str, tuple[torch.Tensor, torch.Tensor]] = {}
    start = time.perf_counter()
    for fixture, hidden in evaluation_fixtures.items():
        dense_logits = hidden @ weight.T
        dense_oracles[fixture] = (dense_logits, topk_ids(dense_logits, 10))
    timing["dense_oracle_seconds"] = time.perf_counter() - start
    curves: list[dict] = []
    index_geometries: list[dict] = []
    for clusters in inputs.clusters:
        for fixture, hidden in evaluation_fixtures.items():
            dense_logits, dense_topk = dense_oracles[fixture]
            geometry_rows, geometry = evaluate_geometry(
                fixture=fixture,
                hidden=hidden,
                dense_logits=dense_logits,
                dense_topk=dense_topk,
                weight=weight,
                leaf_tokens=leaf_tokens,
                leaf_clusters=maximum_clusters,
                clusters=clusters,
                probes=inputs.probes,
                top_k=10,
            )
            curves.extend(geometry_rows)
            geometry["fixture"] = fixture
            index_geometries.append(geometry)

    geometry_rows: dict[tuple[int, int], list[dict]] = {}
    for row in curves:
        geometry_rows.setdefault((row["clusters"], row["probes"]), []).append(
            row
        )
    structural_passing = [
        rows
        for rows in geometry_rows.values()
        if len(rows) == len(evaluation_fixtures)
        and all(row["top1_recall"] >= 0.96875 for row in rows)
        and all(row["top10_retrieval_recall"] >= 0.9 for row in rows)
        and all(
            row["physical_cost_model"]["candidate_roofline_floor_us"]
            < grouped_exact_baseline()["grouped_exact_ideal_reuse"][
                "roofline_floor_us"
            ]
            for row in rows
        )
    ]
    best_rows = (
        min(
            structural_passing,
            key=lambda rows: (
                max(
                    row["physical_cost_model"]["candidate_roofline_floor_us"]
                    for row in rows
                ),
                rows[0]["candidates_per_query"],
            ),
        )
        if structural_passing
        else None
    )
    timing["total_seconds"] = time.time() - started
    return {
        "schema_version": 1,
        "type": "gemma4_flashhead_offline_clustered_retrieval_result",
        "classification": (
            "representative_target_verify_capture_required_structural_candidate_passes"
            if best_rows
            else "representative_target_verify_capture_required_structural_candidate_fails"
        )
        if not captured_fixture_valid
        else (
            "promising_offline_component_candidate"
            if best_rows
            else "offline_candidate_does_not_beat_grouped_exact_floor_at_recall_gate"
        ),
        "completed_at_unix_s": time.time(),
        "question": "Can balanced clustered retrieval recover dense tied-head decisions with materially lower physical H200 cost than dense 12xM32 and the ideal grouped-exact baseline?",
        "evidence_labels": {
            "recall_curve": (
                "measured on deterministic synthetic structural queries and the exact checkpoint embedding"
                if not captured_fixture_valid
                else "measured on 32 persisted actual-consumer hidden rows and the exact checkpoint embedding"
            ),
            "dense_head_attribution": "measured in the qualified 15-step H200 trace",
            "h200_costs": "analytical roofline using shared inventory vendor priors and measured dense calibration boundary",
            "whole_request_projection": "derived upper-bound transfer, not endpoint measurement",
            "quality": "not measured; no GPQA-Diamond, TauBench, sampling, or OpenRouter feature claim",
        },
        "inputs": {
            "checkpoint_file": str(inputs.checkpoint),
            "checkpoint_file_bytes": inputs.checkpoint.stat().st_size,
            "checkpoint_file_sha256": sha256(inputs.checkpoint),
            "embedding_tensor": "model.language_model.embed_tokens.weight",
            "embedding_shape": list(weight.shape),
            "embedding_dtype": str(weight_bf16.dtype),
            "hidden_rows_file": str(inputs.hidden_rows),
            "hidden_rows_sha256": sha256(inputs.hidden_rows),
            "hidden_rows_shape": list(captured_hidden.shape),
            "hidden_rows_dtype": str(hidden_bf16.dtype),
            "hidden_fixture_boundary": "actual LogitsProcessor._compute_lm_head M32 capture; not a 384-row target-verification capture",
            "hidden_fixture_unique_rows": unique_captured_rows,
            "hidden_fixture_valid_for_recall": captured_fixture_valid,
            "seed": inputs.seed,
        },
        "evaluation_fixtures": fixture_provenance,
        "representation": {
            "method": "balanced hierarchical 2-means over a fixed Gaussian projection of tied BF16 token embeddings",
            "projection_dims": inputs.projection_dims,
            "split_iterations": inputs.kmeans_iterations,
            "maximum_leaf_clusters": maximum_clusters,
            "balance": "exact equal token count per cluster",
            "query_leakage": False,
            "runtime_centroids": "exact FP32 mean of original 5376-D embedding rows, modeled as BF16 storage",
            "candidate_scores": "exact dense BF16-weight dot-product oracle restricted to tokens in selected clusters",
            "sampling_support": "not implemented; the candidate set alone cannot preserve full-distribution sampling",
        },
        "consumer_semantics": {
            "producer": "Gemma4ForCausalLM hidden states after final norm",
            "consumer": "SGLang LogitsProcessor._get_logits -> _compute_lm_head -> final softcap(30) -> target verifier/sampler",
            "qualified_target_verify_layout": "[batch=32, depth=12, hidden=5376] request-major, sliced into 12 independent M32 projections",
            "verifier_decision_metric": "candidate argmax equals dense argmax; this preserves the target token decision for any proposed draft token at that position",
            "softcap_note": "Gemma final softcap is monotone, so it cannot change argmax or top-k IDs",
            "missing_capture": "draft token IDs and 384 matching target-verification hidden rows are absent; accepted-prefix recall is therefore not measured",
        },
        "baselines": grouped_exact_baseline(),
        "index_geometries": index_geometries,
        "curves": curves,
        "decision_gate": {
            "minimum_top1_recall": 0.96875,
            "minimum_top10_retrieval_recall": 0.9,
            "must_beat": "grouped_exact_ideal_reuse_roofline_floor",
            "structural_passing_geometries": len(structural_passing),
            "selected_rows": best_rows,
            "production_decision_allowed": captured_fixture_valid,
        },
        "timing": timing,
        "next_component_if_promising": {
            "capture": "Persist one unseen full target-verification step: 384 post-final-norm BF16 hidden rows, 384 draft token IDs, dense top-10 IDs/values, request/depth mapping, and accepted-prefix result.",
            "experiment": "On the retained H200, build the frozen balanced index once, run cluster-score + multiprobe + ragged exact candidate scoring for the selected geometry, and compare per-position argmax plus per-request accepted-prefix decisions.",
            "minimum_counters": [
                "CUDA-event latency per 12-depth step",
                "kernel launch count",
                "DRAM read bytes",
                "L2 hit rate",
                "candidate count and unique clusters per depth",
            ],
        },
    }


def self_test() -> None:
    rng = np.random.default_rng(7)
    projected = rng.normal(size=(1_024, 8)).astype(np.float32)
    groups = balanced_hierarchical_kmeans(projected, 16, 2)
    assert groups.shape == (16, 64)
    assert len(np.unique(groups)) == 1_024
    cost = physical_cost(
        clusters=1_024,
        probes=4,
        cluster_size=256,
        unique_clusters_per_m32=64,
    )
    assert cost["candidate_roofline_floor_us"] > 0
    print("self-test passed")


def parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=pathlib.Path)
    parser.add_argument("--hidden-rows", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--clusters", default="512,1024,2048")
    parser.add_argument("--probes", default="1,2,4,8,16,32,64")
    parser.add_argument("--projection-dims", type=int, default=32)
    parser.add_argument("--kmeans-iterations", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260725)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse()
    if args.self_test:
        self_test()
        return
    required = {
        "--checkpoint": args.checkpoint,
        "--hidden-rows": args.hidden_rows,
        "--output": args.output,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise SystemExit(f"missing required arguments: {', '.join(missing)}")
    clusters = tuple(int(value) for value in args.clusters.split(","))
    probes = tuple(int(value) for value in args.probes.split(","))
    result = run(
        Inputs(
            checkpoint=args.checkpoint.resolve(),
            hidden_rows=args.hidden_rows.resolve(),
            output=args.output.resolve(),
            clusters=clusters,
            probes=probes,
            projection_dims=args.projection_dims,
            kmeans_iterations=args.kmeans_iterations,
            seed=args.seed,
        )
    )
    atomic_json(args.output, result)
    print(json.dumps({"classification": result["classification"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
