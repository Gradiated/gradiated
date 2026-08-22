#!/usr/bin/env python3
"""Deterministic H200 producer and single-shot PQ-MIPS discriminator."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VOCAB = 262144
HIDDEN = 5376
REQUESTS = 32
SUBSPACE_DIMENSIONS = 2
SUBSPACES = HIDDEN // SUBSPACE_DIMENSIONS
SCALAR_LEVELS = 16
CODEBOOK_ROWS = SCALAR_LEVELS**SUBSPACE_DIMENSIONS
WEIGHT_KEY = "model.language_model.embed_tokens.weight"
REFERENCE_SUBSPACES = (0, 1, 17, 511, 1024, 2047, 2687)
REFERENCE_TOKEN_IDS = (0, 1, 106, 255, 4096, 65535, 131071, 262143)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    json.loads(temporary.read_text())
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def raw_tensor_sha256(tensor, torch) -> str:
    value = tensor.detach().contiguous().cpu().view(torch.uint8)
    return hashlib.sha256(value.numpy().tobytes()).hexdigest()


def standard_normal_lloyd_max_levels() -> list[float]:
    normalizer = math.sqrt(2.0 * math.pi)

    def density(value: float) -> float:
        return math.exp(-0.5 * value * value) / normalizer

    def distribution(value: float) -> float:
        return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))

    levels = [
        -2.75,
        -2.10,
        -1.70,
        -1.40,
        -1.14,
        -0.90,
        -0.67,
        -0.44,
        0.44,
        0.67,
        0.90,
        1.14,
        1.40,
        1.70,
        2.10,
        2.75,
    ]
    for _ in range(128):
        boundaries = [
            -math.inf,
            *[(levels[index] + levels[index + 1]) / 2 for index in range(15)],
            math.inf,
        ]
        updated = []
        for lower, upper in zip(boundaries, boundaries[1:]):
            lower_density = 0.0 if math.isinf(lower) else density(lower)
            upper_density = 0.0 if math.isinf(upper) else density(upper)
            lower_mass = 0.0 if lower == -math.inf else distribution(lower)
            upper_mass = 1.0 if upper == math.inf else distribution(upper)
            updated.append((lower_density - upper_density) / (upper_mass - lower_mass))
        if max(abs(left - right) for left, right in zip(levels, updated)) < 1e-13:
            return updated
        levels = updated
    return levels


def codebook_from_stats(means, variances, torch):
    levels = torch.tensor(
        standard_normal_lloyd_max_levels(), dtype=torch.float64, device=means.device
    )
    scales = variances.double().clamp_min(torch.finfo(torch.float64).eps).sqrt()
    scalar = (means.double()[:, None] + scales[:, None] * levels[None, :]).to(
        torch.bfloat16
    )
    thresholds = (scalar[:, :-1].float() + scalar[:, 1:].float()) / 2
    return levels, scalar, thresholds


def expanded_codebooks(scalar, torch):
    low = torch.arange(CODEBOOK_ROWS, device=scalar.device) % SCALAR_LEVELS
    high = torch.arange(CODEBOOK_ROWS, device=scalar.device) // SCALAR_LEVELS
    result = torch.empty(
        (scalar.shape[0] // 2, CODEBOOK_ROWS, 2),
        dtype=torch.bfloat16,
        device=scalar.device,
    )
    result[:, :, 0] = scalar[0::2][:, low]
    result[:, :, 1] = scalar[1::2][:, high]
    return result


def encode_rows(weight, thresholds, torch, row_chunk: int):
    codes = torch.empty(
        (weight.shape[0], weight.shape[1] // 2),
        dtype=torch.uint8,
        device=weight.device,
    )
    for start in range(0, weight.shape[0], row_chunk):
        end = min(weight.shape[0], start + row_chunk)
        quantized = torch.searchsorted(
            thresholds, weight[start:end].float().T.contiguous(), right=False
        ).T
        codes[start:end] = (
            quantized[:, 0::2] + SCALAR_LEVELS * quantized[:, 1::2]
        ).to(torch.uint8)
    return codes


def cpu_reference_check(weight_cpu, means, variances, scalar, codes, torch):
    coordinates = [
        coordinate
        for subspace in REFERENCE_SUBSPACES
        for coordinate in (2 * subspace, 2 * subspace + 1)
    ]
    reference_values = weight_cpu[:, coordinates].float().contiguous()
    reference_variances, reference_means = torch.var_mean(
        reference_values, dim=0, correction=0
    )
    _, reference_scalar, reference_thresholds = codebook_from_stats(
        reference_means, reference_variances, torch
    )
    observed_scalar = scalar[coordinates].detach().cpu()
    codebooks_exact = torch.equal(observed_scalar, reference_scalar)
    selected_values = weight_cpu[list(REFERENCE_TOKEN_IDS)][:, coordinates]
    quantized = torch.searchsorted(
        reference_thresholds, selected_values.float().T.contiguous(), right=False
    ).T
    reference_codes = (
        quantized[:, 0::2] + SCALAR_LEVELS * quantized[:, 1::2]
    ).to(torch.uint8)
    observed_codes = codes[list(REFERENCE_TOKEN_IDS)][:, list(REFERENCE_SUBSPACES)]
    observed_codes = observed_codes.detach().cpu()
    codes_exact = torch.equal(observed_codes, reference_codes)
    mean_max_abs = float(
        (means[coordinates].detach().cpu().float() - reference_means).abs().max()
    )
    variance_max_abs = float(
        (variances[coordinates].detach().cpu().float() - reference_variances)
        .abs()
        .max()
    )
    result = {
        "reference_subspaces": list(REFERENCE_SUBSPACES),
        "reference_token_ids": list(REFERENCE_TOKEN_IDS),
        "sampled_scalar_codebooks_bf16_exact": bool(codebooks_exact),
        "sampled_uint8_codes_exact": bool(codes_exact),
        "mean_max_abs": mean_max_abs,
        "variance_max_abs": variance_max_abs,
        "reference_codes_sha256": raw_tensor_sha256(reference_codes, torch),
        "observed_codes_sha256": raw_tensor_sha256(observed_codes, torch),
        "pass": bool(codebooks_exact and codes_exact),
    }
    if not result["pass"]:
        raise RuntimeError("bounded_cpu_reference_check_failed")
    return result


def asymmetric_scan(hidden, codebooks, codes, torch, query_chunk=32, row_chunk=512):
    subspaces = hidden.shape[1] // 2
    if codebooks.shape[0] != subspaces or codes.shape[1] != subspaces:
        raise RuntimeError("asymmetric_scan_geometry_mismatch")
    queries = hidden.reshape(hidden.shape[0], subspaces, 2).float()
    lookup = torch.einsum("qsd,skd->qsk", queries, codebooks.float())
    scores = torch.empty(
        (hidden.shape[0], codes.shape[0]), dtype=torch.float32, device=hidden.device
    )
    for query_start in range(0, hidden.shape[0], query_chunk):
        query_end = min(hidden.shape[0], query_start + query_chunk)
        for row_start in range(0, codes.shape[0], row_chunk):
            row_end = min(codes.shape[0], row_start + row_chunk)
            index = (
                codes[row_start:row_end]
                .T.to(torch.int64)
                .unsqueeze(0)
                .expand(query_end - query_start, -1, -1)
            )
            values = torch.gather(lookup[query_start:query_end], 2, index)
            scores[query_start:query_end, row_start:row_end] = values.sum(dim=1)
    return scores, lookup


def gamma(operations: int, unit_roundoff: float) -> float:
    product = operations * unit_roundoff
    if product >= 1:
        raise RuntimeError("roundoff_bound_undefined")
    return product / (1.0 - product)


def select_batches(payload: dict[str, Any]) -> tuple[list[list[int]], list[list[int]]]:
    ownership = payload["ownership"]
    grouped: dict[str, list[int]] = {}
    order: list[str] = []
    for index, row in enumerate(ownership):
        request_id = str(row["request_id"])
        if request_id not in grouped:
            grouped[request_id] = []
            order.append(request_id)
        grouped[request_id].append(index)
    if len(order) != REQUESTS or any(len(grouped[item]) < 4 for item in order):
        raise RuntimeError("capture_request_geometry_mismatch")
    prior = [[grouped[item][depth] for item in order] for depth in (0, 1)]
    selected = [[grouped[item][depth] for item in order] for depth in (2, 3)]
    flat = [set(rows) for rows in (*prior, *selected)]
    if any(flat[left] & flat[right] for left in range(4) for right in range(left + 1, 4)):
        raise RuntimeError("capture_row_selection_not_disjoint")
    return prior, selected


def traffic(shortlist: int, union_rows: int) -> dict[str, int | float]:
    dense = VOCAB * HIDDEN * 2
    values = {
        "pq_codes_bytes": VOCAB * SUBSPACES,
        "codebook_bytes": SUBSPACES * CODEBOOK_ROWS * 2 * 2,
        "query_lookup_table_bytes": REQUESTS * SUBSPACES * CODEBOOK_ROWS * 4,
        "score_buffer_bytes": REQUESTS * VOCAB * 4,
        "query_input_bytes": REQUESTS * HIDDEN * 2,
        "candidate_id_bytes": REQUESTS * shortlist * 4,
        "exact_member_weight_bytes": union_rows * HIDDEN * 2,
        "exact_logit_bytes": REQUESTS * shortlist * 4,
    }
    total = sum(values.values())
    return {
        "dense_weight_bytes": dense,
        **values,
        "candidate_total_bytes": total,
        "net_bytes_saved": dense - total,
        "net_bytes_avoided_fraction": (dense - total) / dense,
    }


def event_seconds(action, torch):
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    value = action()
    end.record()
    torch.cuda.synchronize()
    return value, start.elapsed_time(end) / 1000


def exact_union_rescore(hidden, weight_float, ids, torch):
    rescored = []
    unions = []
    for batch in range(2):
        start, end = batch * REQUESTS, (batch + 1) * REQUESTS
        batch_ids = ids[start:end]
        union = torch.unique(batch_ids.flatten(), sorted=True)
        union_scores = hidden[start:end].float() @ weight_float[union].T
        positions = torch.searchsorted(union, batch_ids)
        candidate_scores = union_scores.gather(1, positions)
        rescored.append(
            batch_ids.gather(1, candidate_scores.argmax(1, keepdim=True)).squeeze(1)
        )
        unions.append(union)
    return torch.cat(rescored), unions


def save_index(path: Path, value: dict[str, Any], torch) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        torch.save(value, temporary)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run(args: argparse.Namespace) -> int:
    import torch
    from safetensors import safe_open

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.query_chunk != REQUESTS:
        raise RuntimeError("query_chunk_must_equal_frozen_c32_batch_for_code_scan")
    contract = json.loads(args.contract.read_text())
    expected = contract["inputs"]
    inputs = args.inputs.resolve()
    identities = {
        "contract": sha256_file(args.contract),
        "capture": sha256_file(inputs / "hidden_states.pt"),
        "capture_terminal": sha256_file(inputs / "EXACT_CAPTURE_TERMINAL.json"),
        "checkpoint_index": sha256_file(inputs / "model.safetensors.index.json"),
        "config": sha256_file(inputs / "config.json"),
        "lowrank_terminal": sha256_file(
            inputs / "LOSSLESS_LOWRANK_RESIDUAL_DISJOINT_TERMINAL.json"
        ),
        "weight_snapshot": sha256_file(args.weight),
        "source_weight_shard": expected["weight_shard_sha256"],
        "tied_weight_tensor": expected["tied_weight_tensor_sha256"],
        "worker": sha256_file(Path(__file__).resolve()),
    }
    expected_hashes = {
        "capture": expected["capture_sha256"],
        "capture_terminal": expected["capture_terminal_sha256"],
        "checkpoint_index": expected["checkpoint_index_sha256"],
        "config": expected["config_sha256"],
        "lowrank_terminal": expected["lowrank_terminal_sha256"],
    }
    if any(identities[name] != digest for name, digest in expected_hashes.items()):
        raise RuntimeError("immutable_input_hash_mismatch")
    config = json.loads((inputs / "config.json").read_text())
    if (
        config["text_config"]["hidden_size"] != HIDDEN
        or config["text_config"]["vocab_size"] != VOCAB
        or not config["text_config"]["tie_word_embeddings"]
    ):
        raise RuntimeError("model_geometry_mismatch")
    payload = torch.load(
        inputs / "hidden_states.pt", map_location="cpu", weights_only=True, mmap=True
    )
    if (
        tuple(payload["hidden_states"].shape) != (1536, HIDDEN)
        or payload["hidden_states"].dtype != torch.bfloat16
    ):
        raise RuntimeError("capture_geometry_mismatch")
    _, selected = select_batches(payload)
    if not torch.cuda.is_available():
        raise RuntimeError("cuda_required")
    device = torch.device("cuda:0")
    properties = torch.cuda.get_device_properties(device)
    if "H200" not in properties.name:
        raise RuntimeError(f"nvidia_h200_required:{properties.name}")
    torch.use_deterministic_algorithms(True)
    with safe_open(args.weight, framework="pt", device="cpu") as handle:
        weight_cpu = handle.get_tensor(WEIGHT_KEY)
    if tuple(weight_cpu.shape) != (VOCAB, HIDDEN) or weight_cpu.dtype != torch.bfloat16:
        raise RuntimeError("weight_snapshot_geometry_mismatch")
    if raw_tensor_sha256(weight_cpu, torch) != expected["tied_weight_tensor_sha256"]:
        raise RuntimeError("tied_weight_tensor_hash_mismatch")

    weight, transfer_seconds = event_seconds(lambda: weight_cpu.to(device), torch)
    weight_float, cast_seconds = event_seconds(lambda: weight.float(), torch)
    index_path = output / "frozen_pq_index.pt"
    producer_terminal_path = output / "PRODUCER_TERMINAL.json"
    if args.resume_producer:
        producer_terminal = json.loads(producer_terminal_path.read_text())
        if not (
            producer_terminal.get("classification")
            == "deterministic_vectorized_pq_producer_complete"
            and producer_terminal.get("producer_consumed") is True
            and producer_terminal.get("science_started") is False
            and producer_terminal.get("cpu_reference", {}).get("pass") is True
            and producer_terminal.get("index", {}).get("sha256")
            == sha256_file(index_path)
        ):
            raise RuntimeError("resumed_producer_terminal_invalid")
        index = torch.load(index_path, map_location="cpu", weights_only=True)
        codes = index["codes"].to(device)
        codebooks = index["codebooks"].to(device)
    else:
        atomic_json(
            output / "PRODUCER_STARTED.json",
            {
                "stage": "vectorized_weight_only_producer",
                "producer_started": True,
                "science_started": False,
                "at_utc": datetime.now(timezone.utc).isoformat(),
                "weight_snapshot_sha256": identities["weight_snapshot"],
            },
        )
        stats, statistics_seconds = event_seconds(
            lambda: torch.var_mean(weight_float, dim=0, correction=0), torch
        )
        variances, means = stats
        levels, scalar, thresholds = codebook_from_stats(means, variances, torch)
        codebooks = expanded_codebooks(scalar, torch)
        codes, encoding_seconds = event_seconds(
            lambda: encode_rows(weight, thresholds, torch, args.encode_rows), torch
        )
        reference = cpu_reference_check(
            weight_cpu, means, variances, scalar, codes, torch
        )
        save_index(
            index_path,
            {
                "schema_version": 1,
                "name": contract["candidate"]["index_name"],
                "codes": codes.cpu(),
                "codebooks": codebooks.cpu(),
                "normalized_lloyd_max_levels": levels.cpu(),
                "subspaces": SUBSPACES,
                "dimensions_per_subspace": 2,
                "codebook_rows": CODEBOOK_ROWS,
                "weight_tensor_sha256": expected["tied_weight_tensor_sha256"],
                "capture_rows_used_for_training": 0,
                "training_source": "all_output_weight_rows_only",
            },
            torch,
        )
        producer_terminal = {
            "schema_version": 1,
            "classification": "deterministic_vectorized_pq_producer_complete",
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "science_started": False,
            "producer_consumed": True,
            "identities": identities,
            "index": {
                "path": str(index_path),
                "sha256": sha256_file(index_path),
                "codes_sha256": raw_tensor_sha256(codes, torch),
                "codebooks_sha256": raw_tensor_sha256(codebooks, torch),
                "bytes": index_path.stat().st_size,
            },
            "geometry": {
                "weight_shape": [VOCAB, HIDDEN],
                "weight_dtype": "torch.bfloat16",
                "subspaces": SUBSPACES,
                "dimensions_per_subspace": 2,
                "codebook_rows": CODEBOOK_ROWS,
                "codes_dtype": "torch.uint8",
                "codebooks_dtype": "torch.bfloat16",
            },
            "cpu_reference": reference,
            "h200_seconds": {
                "weight_h2d": transfer_seconds,
                "weight_fp32_cast": cast_seconds,
                "statistics": statistics_seconds,
                "encoding": encoding_seconds,
            },
        }
        atomic_json(producer_terminal_path, producer_terminal)
    atomic_json(
        output / "SCIENCE_STARTED.json",
        {
            "science_started": True,
            "stage": "held_out_pq_mips_discriminator",
            "producer_terminal_sha256": sha256_file(output / "PRODUCER_TERMINAL.json"),
            "at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )

    hidden_cpu = torch.cat(
        [payload["hidden_states"][indices] for indices in selected], dim=0
    ).contiguous()
    selection_provenance = []
    for batch_index, indices in enumerate(selected):
        ownership = [payload["ownership"][index] for index in indices]
        selection_provenance.append(
            {
                "batch_index": batch_index,
                "storage_indices": indices,
                "storage_indices_sha256": hashlib.sha256(
                    json.dumps(indices, separators=(",", ":")).encode()
                ).hexdigest(),
                "ownership_sha256": hashlib.sha256(
                    json.dumps(
                        ownership, sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest(),
                "hidden_bf16_rows_sha256": raw_tensor_sha256(
                    payload["hidden_states"][indices], torch
                ),
            }
        )
    hidden = hidden_cpu.to(device)
    approximate_scores, lookup_seconds = event_seconds(
        lambda: asymmetric_scan(
            hidden,
            codebooks,
            codes,
            torch,
            query_chunk=args.query_chunk,
            row_chunk=args.scan_rows,
        )[0],
        torch,
    )
    exact_scores, dense_seconds = event_seconds(
        lambda: hidden.float() @ weight_float.T, torch
    )
    exact_weight_norm = torch.linalg.vector_norm(weight_float.double(), dim=1)
    qnorm = torch.linalg.vector_norm(hidden.double(), dim=1)
    norm_product = qnorm[:, None] * exact_weight_norm[None, :]
    stock_error = 2 * gamma(HIDDEN, 2.0**-24) * norm_product
    stock_error += (2.0**-8 / (1.0 - 2.0**-8)) * (
        norm_product + gamma(HIDDEN, 2.0**-24) * norm_product
    )
    allowed = torch.ones(VOCAB, dtype=torch.bool, device=device)
    allowed[[1, 106]] = False
    dense_lower = (exact_scores.double() - stock_error).masked_fill(
        ~allowed[None, :], float("-inf")
    ).max(dim=1).values
    possible = exact_scores.double() + stock_error >= dense_lower[:, None]
    possible[:, 1] = False
    dense_ids = exact_scores.masked_fill(~allowed[None, :], float("-inf")).argmax(1)
    ranking_scores = approximate_scores.masked_fill(
        ~allowed[None, :], float("-inf")
    )
    ranking, ranking_seconds = event_seconds(
        lambda: torch.argsort(
            ranking_scores, dim=1, descending=True, stable=True
        )[:, : max(contract["candidate"]["shortlist_sizes"])],
        torch,
    )
    points = []
    exact_rescore_seconds: dict[str, float] = {}
    for shortlist in contract["candidate"]["shortlist_sizes"]:
        ids = ranking[:, :shortlist]
        membership = torch.zeros_like(possible)
        membership.scatter_(1, ids, True)
        stock_counts = possible.sum(1)
        recalled = (possible & membership).sum(1)
        full_recall = recalled == stock_counts
        (rescored_ids, unions), rescore_seconds = event_seconds(
            lambda: exact_union_rescore(hidden, weight_float, ids, torch), torch
        )
        exact_rescore_seconds[str(shortlist)] = rescore_seconds
        agreement = rescored_ids == dense_ids
        cutoff = ranking_scores.gather(1, ids[:, -1:]).squeeze(1)
        missed = possible & ~membership
        missed_margin = (cutoff[:, None] - ranking_scores).masked_fill(
            ~missed, float("-inf")
        )
        batches = []
        for batch in range(2):
            start, end = batch * REQUESTS, (batch + 1) * REQUESTS
            union = unions[batch]
            finite = missed_margin[start:end][missed[start:end]]
            charged = traffic(shortlist, int(union.numel()))
            batches.append(
                {
                    "batch_index": batch,
                    "complete_stock_candidate_recall": bool(
                        full_recall[start:end].all()
                    ),
                    "exact_rescore_greedy_agreement": bool(
                        agreement[start:end].all()
                    ),
                    "stock_candidates_total": int(stock_counts[start:end].sum()),
                    "stock_candidates_recalled": int(recalled[start:end].sum()),
                    "missed_stock_candidates": int(missed[start:end].sum()),
                    "miss_margin_cutoff_minus_candidate_max": (
                        float(finite.max()) if finite.numel() else None
                    ),
                    "physical_union_rows": int(union.numel()),
                    "physical_union_token_ids_sha256": raw_tensor_sha256(
                        union.to(torch.int32), torch
                    ),
                    "exact_rescore_ids_sha256": raw_tensor_sha256(
                        rescored_ids[start:end].to(torch.int32), torch
                    ),
                    "dense_reference_ids_sha256": raw_tensor_sha256(
                        dense_ids[start:end].to(torch.int32), torch
                    ),
                    "traffic": charged,
                    "net_physical_traffic_positive": charged["net_bytes_saved"] > 0,
                }
            )
        points.append(
            {
                "shortlist_size": shortlist,
                "complete_stock_candidate_recall_all_64": bool(full_recall.all()),
                "exact_rescore_greedy_agreement_all_64": bool(agreement.all()),
                "missed_stock_candidates_all_64": int(missed.sum()),
                "batches": batches,
            }
        )
    qualifying = [
        point
        for point in points
        if point["complete_stock_candidate_recall_all_64"]
        and point["exact_rescore_greedy_agreement_all_64"]
        and all(row["net_physical_traffic_positive"] for row in point["batches"])
    ]
    selected_shortlist = min(
        (point["shortlist_size"] for point in qualifying), default=None
    )
    result = {
        "schema_version": 1,
        "classification": (
            "typed_h200_positive_pq_mips_capture_recall_and_traffic"
            if selected_shortlist is not None
            else "typed_h200_falsification_fixed_pq_mips_capture_recall"
        ),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "science_started": True,
        "scientific_samples_consumed": 1,
        "producer_terminal_sha256": sha256_file(output / "PRODUCER_TERMINAL.json"),
        "identities": identities,
        "geometry": {
            "weight_shape": list(weight_cpu.shape),
            "weight_stride": list(weight_cpu.stride()),
            "weight_storage_offset": int(weight_cpu.storage_offset()),
            "weight_dtype": str(weight_cpu.dtype),
            "capture_shape": list(payload["hidden_states"].shape),
            "capture_stride": list(payload["hidden_states"].stride()),
            "capture_storage_offset": int(payload["hidden_states"].storage_offset()),
            "capture_dtype": str(payload["hidden_states"].dtype),
            "selected_batch_rows": selection_provenance,
            "batch_selection": contract["workload"]["batch_selection"],
            "shortlist_sizes": contract["candidate"]["shortlist_sizes"],
        },
        "correctness": {
            "possible_stock_candidate_set_sha256": raw_tensor_sha256(possible, torch),
            "dense_reference_ids_sha256": raw_tensor_sha256(
                dense_ids.to(torch.int32), torch
            ),
            "operating_points": points,
        },
        "decision": {
            "promote_to_h200_exact_consumer_component": selected_shortlist is not None,
            "close_fixed_pq_retrieval_proxy": selected_shortlist is None,
            "selected_shortlist_size": selected_shortlist,
        },
        "h200_component_seconds": {
            "asymmetric_lookup_and_code_scan": lookup_seconds,
            "dense_exact_reference": dense_seconds,
            "stable_full_vocab_ranking": ranking_seconds,
            "exact_union_rescore_by_shortlist": exact_rescore_seconds,
        },
        "resource_use": {
            "gpu": properties.name,
            "cuda": True,
            "endpoint_traffic": False,
            "provider_mutation": False,
        },
    }
    atomic_json(output / "OUTPUT_HEAD_PQ_MIPS_H200_TERMINAL.json", result)
    return 0


def self_test() -> int:
    import torch

    torch.use_deterministic_algorithms(True)
    rows, width = 2048, 16
    base = torch.arange(rows * width, dtype=torch.float32).reshape(rows, width)
    weight = (torch.sin(base * 0.017) * 0.25).to(torch.bfloat16)
    variances, means = torch.var_mean(weight.float(), dim=0, correction=0)
    _, scalar, thresholds = codebook_from_stats(means, variances, torch)
    codes = encode_rows(weight, thresholds, torch, 257)
    reference = []
    for row in weight:
        scalar_codes = [
            int(torch.searchsorted(thresholds[column], row[column].float()))
            for column in range(width)
        ]
        reference.append(
            [
                scalar_codes[column] + 16 * scalar_codes[column + 1]
                for column in range(0, width, 2)
            ]
        )
    reference_codes = torch.tensor(reference, dtype=torch.uint8)
    if not torch.equal(codes, reference_codes):
        raise RuntimeError("offline_scalar_formula_mismatch")
    codebooks = expanded_codebooks(scalar, torch)
    hidden = (
        torch.cos(torch.arange(3 * width).reshape(3, width) * 0.031) * 0.5
    ).to(torch.bfloat16)
    scanned, _ = asymmetric_scan(hidden, codebooks, codes, torch, 2, 509)
    subspaces = torch.arange(width // 2)[None, :]
    reconstructed = codebooks[subspaces, codes.long()].reshape(rows, width)
    reference_scores = hidden.float() @ reconstructed.float().T
    if not torch.equal(scanned, reference_scores):
        maximum = float((scanned - reference_scores).abs().max())
        raise RuntimeError(f"offline_asymmetric_scan_mismatch:{maximum}")
    print(
        json.dumps(
            {
                "pass": True,
                "rows": rows,
                "width": width,
                "codes_sha256": raw_tensor_sha256(codes, torch),
                "scores_sha256": raw_tensor_sha256(scanned, torch),
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--weight", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--encode-rows", type=int, default=16384)
    parser.add_argument("--scan-rows", type=int, default=512)
    parser.add_argument("--query-chunk", type=int, default=32)
    parser.add_argument("--resume-producer", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if any(value is None for value in (args.contract, args.inputs, args.weight, args.output)):
        parser.error("--contract, --inputs, --weight, and --output are required")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
