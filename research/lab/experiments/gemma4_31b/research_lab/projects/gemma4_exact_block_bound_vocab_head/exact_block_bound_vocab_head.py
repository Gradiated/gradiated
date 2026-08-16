#!/usr/bin/env python3
"""Certified coordinate-envelope search for Gemma 4's tied vocabulary head."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

VOCAB = 262144
HIDDEN = 5376
CAPTURE_ROWS = 1536
REQUESTS = 32
WEIGHT_KEY = "model.language_model.embed_tokens.weight"
WEIGHT_SHA256 = "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa"
CAPTURE_SHA256 = "ce7095836aea47701fc34ebacb2f0754c9066066062500a05fbd6136c59b4d54"
CAPTURE_TERMINAL_SHA256 = "fc7297d3bf51e9118e0cf5bde4eec7c2bd22dc2d07a6608c3b19f8b55d55a9bc"
DENSE_TOP1_SHA256 = "27d7de2f664f46b7b743abccc751287414820d3e55175c870b8fdda2f2538816"
DENSE_COMPARATOR_SECONDS = 0.004182975769042969


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def top1_sha256(ids: list[int]) -> str:
    return hashlib.sha256(
        b"".join(int(value).to_bytes(4, "little", signed=False) for value in ids)
    ).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def build_index(weight, block_size: int):
    import torch

    if weight.shape[0] % block_size:
        raise RuntimeError("block_size_must_divide_vocab")
    blocks = weight.shape[0] // block_size
    reshaped = weight.float().reshape(blocks, block_size, weight.shape[1])
    lower = reshaped.amin(dim=1).contiguous()
    upper = reshaped.amax(dim=1).contiguous()
    representatives = weight[::block_size].float().contiguous()
    if not bool(
        (lower[:, None, :] <= reshaped).all()
        and (reshaped <= upper[:, None, :]).all()
    ):
        raise RuntimeError("index_envelope_construction_failed")
    index_bytes = (
        lower.numel() * lower.element_size()
        + upper.numel() * upper.element_size()
        + representatives.numel() * representatives.element_size()
    )
    return lower, upper, representatives, index_bytes


def certified_search(hidden, weight, index, block_size: int):
    import torch

    lower, upper, representatives, _ = index
    query = hidden.float()
    positive = query.clamp_min(0)
    negative = query.clamp_max(0)
    raw_upper = positive @ upper.T + negative @ lower.T
    absolute_envelope = torch.maximum(lower.abs(), upper.abs())
    absolute_sum = query.abs() @ absolute_envelope.T
    unit_roundoff = 2.0**-24
    gamma = (2 * query.shape[1] * unit_roundoff) / (
        1.0 - 2 * query.shape[1] * unit_roundoff
    )
    upper_bound = raw_upper + absolute_sum * (gamma / (1.0 - gamma))
    representative_scores = query @ representatives.T
    seed_scores, seed_blocks = representative_scores.max(dim=1)
    active = upper_bound >= seed_scores[:, None]
    active[:, seed_blocks] = True
    union_blocks = torch.nonzero(active.any(dim=0), as_tuple=False).flatten()
    block_offsets = union_blocks[:, None] * block_size + torch.arange(
        block_size, device=weight.device
    )[None, :]
    row_ids = block_offsets.flatten()
    exact_scores = query @ weight[row_ids].float().T
    logical_active = active[:, union_blocks].repeat_interleave(block_size, dim=1)
    exact_scores = exact_scores.masked_fill(~logical_active, float("-inf"))
    best_scores, local_ids = exact_scores.max(dim=1)
    best_ids = row_ids[local_ids]
    skipped = ~active
    skipped_max = upper_bound.masked_fill(~skipped, float("-inf")).max(dim=1).values
    certificate_gap = best_scores - skipped_max
    if not bool((certificate_gap >= 0).all()):
        raise RuntimeError("unsafe_skipped_block_detected")
    checksum = (
        best_scores.double().sum()
        + best_ids.double().sum()
        + upper_bound.double().sum()
        + active.double().sum()
    )
    metrics = {
        "logical_evaluated_row_fraction": float(active.float().mean().item()),
        "physical_union_evaluated_row_fraction": float(
            union_blocks.numel() / active.shape[1]
        ),
        "pruned_block_fraction": float((~active).float().mean().item()),
        "minimum_certificate_gap": float(certificate_gap.min().item()),
        "active_blocks_per_row": active.sum(dim=1),
        "union_blocks": int(union_blocks.numel()),
        "checksum": checksum,
    }
    return best_scores, best_ids, metrics


def dense_top1(hidden, weight):
    logits = hidden @ weight.T
    values, ids = logits.max(dim=1)
    checksum = logits.float().sum(dtype=__import__("torch").float64)
    return values, ids, checksum


def timed_cuda(callable_, repetitions: int):
    import torch

    times = []
    retained = None
    for _ in range(repetitions):
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(
            enable_timing=True
        )
        start.record()
        retained = callable_()
        end.record()
        end.synchronize()
        times.append(start.elapsed_time(end))
        if isinstance(retained, tuple):
            tail = retained[-1]
            checksum = tail["checksum"] if isinstance(tail, dict) else tail
            float(checksum.item())
    return retained, times


def distribution(values: list[float]) -> dict[str, float | int | list[float]]:
    ordered = sorted(values)
    return {
        "unit": "milliseconds",
        "count": len(values),
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "p10": ordered[max(0, math.ceil(0.10 * len(ordered)) - 1)],
        "p90": ordered[max(0, math.ceil(0.90 * len(ordered)) - 1)],
        "samples": values,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weight", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--capture-terminal", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--science-marker", type=Path, required=True)
    parser.add_argument("--arm-marker-root", type=Path, required=True)
    parser.add_argument("--owner-sha256", required=True)
    parser.add_argument("--block-size", type=int, default=128)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()

    import torch
    from safetensors import safe_open

    if not torch.cuda.is_available():
        raise RuntimeError("target_cuda_required")
    if args.block_size not in (32, 64, 128, 256):
        raise RuntimeError("unsupported_block_size")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_float32_matmul_precision("highest")
    identities = {
        "weight": sha256_file(args.weight),
        "capture": sha256_file(args.capture),
        "capture_terminal": sha256_file(args.capture_terminal),
        "admission": sha256_file(args.admission),
        "scorer": sha256_file(Path(__file__).resolve()),
        "owner": args.owner_sha256,
    }
    if identities["weight"] != WEIGHT_SHA256:
        raise RuntimeError("tied_weight_hash_mismatch")
    if identities["capture"] != CAPTURE_SHA256:
        raise RuntimeError("capture_hash_mismatch")
    if identities["capture_terminal"] != CAPTURE_TERMINAL_SHA256:
        raise RuntimeError("capture_terminal_hash_mismatch")
    payload = torch.load(args.capture, map_location="cpu", weights_only=False)
    hidden_cpu = payload["hidden_states"]
    ownership = payload["ownership"]
    request_ids = [str(row["request_id"]) for row in ownership]
    if (
        tuple(hidden_cpu.shape) != (CAPTURE_ROWS, HIDDEN)
        or hidden_cpu.dtype != torch.bfloat16
        or len(set(request_ids)) != REQUESTS
        or not bool(torch.isfinite(hidden_cpu.float()).all())
    ):
        raise RuntimeError("capture_geometry_or_finiteness_mismatch")
    with safe_open(args.weight, framework="pt", device="cpu") as handle:
        weight_cpu = handle.get_tensor(WEIGHT_KEY)
    if tuple(weight_cpu.shape) != (VOCAB, HIDDEN) or weight_cpu.dtype != torch.bfloat16:
        raise RuntimeError("weight_geometry_or_dtype_mismatch")
    device = torch.device("cuda")
    weight = weight_cpu.to(device)
    del weight_cpu
    torch.cuda.synchronize()
    index_started = time.monotonic()
    index = build_index(weight, args.block_size)
    torch.cuda.synchronize()
    index_seconds = time.monotonic() - index_started

    atomic_json(
        args.science_marker,
        {
            "science_started": True,
            "stage": "exact_block_bound_complete_capture",
            "cuda": True,
            "at_unix_s": time.time(),
        },
    )
    request_order = list(dict.fromkeys(request_ids))
    grouped: list[list[int]] = []
    for request_id in request_order:
        rows = [i for i, value in enumerate(request_ids) if value == request_id]
        grouped.append(rows)
    if sorted(i for rows in grouped for i in rows) != list(range(CAPTURE_ROWS)):
        raise RuntimeError("request_partition_incomplete")

    first = hidden_cpu[grouped[0]].to(device)
    dense_top1(first, weight)
    torch.cuda.synchronize()
    atomic_json(args.arm_marker_root / "dense_first_call.json", {"complete": True})
    certified_search(first, weight, index, args.block_size)
    torch.cuda.synchronize()
    atomic_json(
        args.arm_marker_root / "candidate_first_call.json", {"complete": True}
    )
    for _ in range(args.warmups):
        dense_top1(first, weight)
        certified_search(first, weight, index, args.block_size)
    torch.cuda.synchronize()

    dense_times: list[float] = []
    candidate_times: list[float] = []
    dense_ids: list[int] = []
    candidate_ids: list[int] = []
    logical_fractions: list[float] = []
    physical_fractions: list[float] = []
    pruned_fractions: list[float] = []
    certificate_gaps: list[float] = []
    dense_checksum = 0.0
    candidate_checksum = 0.0
    for rows in grouped:
        hidden = hidden_cpu[rows].to(device)
        dense_result, samples = timed_cuda(
            lambda hidden=hidden: dense_top1(hidden, weight), args.repetitions
        )
        dense_times.extend(samples)
        dense_values, ids, checksum = dense_result
        dense_checksum += float(checksum.item())
        dense_ids.extend(int(value) for value in ids.cpu().tolist())
        candidate_result, samples = timed_cuda(
            lambda hidden=hidden: certified_search(
                hidden, weight, index, args.block_size
            ),
            args.repetitions,
        )
        candidate_times.extend(samples)
        candidate_values, ids, metrics = candidate_result
        candidate_checksum += float(metrics["checksum"].item())
        candidate_ids.extend(int(value) for value in ids.cpu().tolist())
        logical_fractions.append(metrics["logical_evaluated_row_fraction"])
        physical_fractions.append(metrics["physical_union_evaluated_row_fraction"])
        pruned_fractions.append(metrics["pruned_block_fraction"])
        certificate_gaps.append(metrics["minimum_certificate_gap"])
        if not bool(torch.isfinite(dense_values).all() and torch.isfinite(candidate_values).all()):
            raise RuntimeError("nonfinite_consumed_output")

    dense_hash = top1_sha256(dense_ids)
    candidate_hash = top1_sha256(candidate_ids)
    exact_match = dense_ids == candidate_ids
    reference_match = dense_hash == DENSE_TOP1_SHA256
    dense_timing = distribution(dense_times)
    candidate_timing = distribution(candidate_times)
    candidate_faster = candidate_timing["median"] < dense_timing["median"]
    decision = (
        "positive_component"
        if exact_match and reference_match and candidate_faster
        else "close_exact_block_bound_mechanism"
    )
    result = {
        "schema_version": 1,
        "classification": "exact_block_bound_vocab_head_terminal",
        "source_hashes": identities,
        "geometry": {
            "rows": CAPTURE_ROWS,
            "requests": REQUESTS,
            "hidden": HIDDEN,
            "vocab": VOCAB,
            "block_size": args.block_size,
            "blocks": VOCAB // args.block_size,
            "weight_dtype": str(weight.dtype),
            "capture_dtype": str(hidden_cpu.dtype),
        },
        "mechanism": {
            "name": "coordinate_hyperrectangle_block_bound",
            "bound": "h_pos dot block_max + h_neg dot block_min plus FP32 reduction guard",
            "roundoff_gamma": (2 * HIDDEN * 2.0**-24)
            / (1.0 - 2 * HIDDEN * 2.0**-24),
            "semantics": "top1-preserving exact certification",
        },
        "exact_top1_match": exact_match,
        "dense_reference_hash_match": reference_match,
        "dense_top1_ids_sha256": dense_hash,
        "candidate_top1_ids_sha256": candidate_hash,
        "all_scores_finite": True,
        "all_skipped_blocks_certified": min(certificate_gaps) >= 0,
        "minimum_certificate_gap": min(certificate_gaps),
        "dense_timing": dense_timing,
        "candidate_timing": candidate_timing,
        "inherited_dense_comparator_ms": DENSE_COMPARATOR_SECONDS * 1000,
        "candidate_faster_than_measured_dense": candidate_faster,
        "candidate_faster_than_inherited_dense": candidate_timing["median"]
        < DENSE_COMPARATOR_SECONDS * 1000,
        "evaluated_row_fraction": statistics.mean(logical_fractions),
        "physical_union_evaluated_row_fraction": statistics.mean(physical_fractions),
        "pruned_block_fraction": statistics.mean(pruned_fractions),
        "index_bytes": index[3],
        "index_construction_seconds": index_seconds,
        "index_amortization": "resident tied-weight index; construction excluded from warm timing",
        "complete_output_consumption": {
            "dense_logits_checksum": dense_checksum,
            "candidate_outputs_and_bounds_checksum": candidate_checksum,
            "top1_rows_consumed": len(candidate_ids),
        },
        "execution": {
            "cuda": True,
            "device": torch.cuda.get_device_name(),
            "capability": list(torch.cuda.get_device_capability()),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "warmups": args.warmups,
            "timed_repetitions_per_request": args.repetitions,
            "request_groups": len(grouped),
            "submission_count": 1,
            "dense_first_call_marker": True,
            "candidate_first_call_marker": True,
        },
        "spend": {
            "gpu_claimed": True,
            "checkpoint_bytes_transferred": 0,
            "endpoint_requests": 0,
        },
        "decision": {
            "classification": decision,
            "promote_to_endpoint_integration": decision == "positive_component",
        },
    }
    atomic_json(args.output, result)
    print(
        json.dumps(
            {
                "decision": decision,
                "dense_median_ms": dense_timing["median"],
                "candidate_median_ms": candidate_timing["median"],
                "exact": exact_match and reference_match,
                "pruned_block_fraction": result["pruned_block_fraction"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
