#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import mmap
import os
import struct
import time
from pathlib import Path

import torch


MODEL = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
WEIGHT_KEY = "model.language_model.embed_tokens.weight"
EXPECTED_WEIGHT_SHARD_SHA256 = "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa"
EXPECTED_CAPTURE_SHA256 = "ce7095836aea47701fc34ebacb2f0754c9066066062500a05fbd6136c59b4d54"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class SafeTensorView:
    def __init__(self, path: Path, key: str):
        self.file = path.open("rb")
        self.mapping = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        header_bytes = struct.unpack("<Q", self.mapping[:8])[0]
        header = json.loads(self.mapping[8 : 8 + header_bytes])
        spec = header[key]
        if spec["dtype"] != "BF16":
            raise ValueError(f"expected BF16 {key}, found {spec['dtype']}")
        start, stop = spec["data_offsets"]
        self.byte_start = 8 + header_bytes + start
        self.byte_stop = 8 + header_bytes + stop
        count = math.prod(spec["shape"])
        self.tensor = torch.frombuffer(
            self.mapping,
            dtype=torch.bfloat16,
            count=count,
            offset=self.byte_start,
        ).reshape(spec["shape"])

    def tensor_sha256(self) -> str:
        digest = hashlib.sha256()
        view = memoryview(self.mapping)
        for start in range(self.byte_start, self.byte_stop, 16 * 1024 * 1024):
            digest.update(view[start : min(start + 16 * 1024 * 1024, self.byte_stop)])
        return digest.hexdigest()

    def close(self) -> None:
        del self.tensor
        self.mapping.close()
        self.file.close()


def build_index(weight: torch.Tensor, block_size: int, chunk_blocks: int):
    vocab, hidden = weight.shape
    if vocab % block_size:
        raise ValueError("vocabulary must divide evenly into blocks")
    blocks = vocab // block_size
    centers = torch.empty((blocks, hidden), dtype=torch.float32)
    radii = torch.empty(blocks, dtype=torch.float32)
    center_l1 = torch.empty(blocks, dtype=torch.float32)
    token_l1 = torch.empty(vocab, dtype=torch.float32)
    unit_roundoff = 2.0**-24
    gamma = hidden * unit_roundoff / (1.0 - hidden * unit_roundoff)
    radius_guard_factor = 1.0 / (1.0 - 4.0 * gamma)
    started = time.perf_counter()
    for first in range(0, blocks, chunk_blocks):
        last = min(first + chunk_blocks, blocks)
        rows = weight[first * block_size : last * block_size].float()
        shaped = rows.reshape(last - first, block_size, hidden)
        chunk_centers = shaped.mean(dim=1)
        residual = shaped - chunk_centers[:, None, :]
        centers[first:last] = chunk_centers
        radii[first:last] = (
            torch.linalg.vector_norm(residual, dim=2).amax(dim=1) * radius_guard_factor
            + 1e-6
        )
        center_l1[first:last] = chunk_centers.abs().sum(dim=1)
        token_l1[first * block_size : last * block_size] = rows.abs().sum(dim=1)
    return {
        "centers": centers,
        "radii": radii,
        "center_l1": center_l1,
        "token_l1": token_l1,
        "gamma": gamma,
        "radius_guard_factor": radius_guard_factor,
        "construction_seconds": time.perf_counter() - started,
    }


def update_best(scores, token_ids, current_score, current_token):
    value, local = torch.max(scores, dim=0)
    token = int(token_ids[int(local)])
    value = float(value)
    if value > current_score or (value == current_score and token < current_token):
        return value, token
    return current_score, current_token


def certified_top1(
    weight: torch.Tensor,
    hidden: torch.Tensor,
    index,
    block_size: int,
    traversal_batch_blocks: int,
):
    centers = index["centers"]
    radii = index["radii"]
    gamma = index["gamma"]
    h = hidden.float()
    h_norm = float(torch.linalg.vector_norm(h))
    h_inf = float(h.abs().max())
    center_scores = torch.mv(centers, h)
    upper = (
        center_scores
        + gamma * h_inf * index["center_l1"]
        + radii * h_norm
        + 1e-5
    )
    order = torch.argsort(upper, descending=True, stable=True)
    best_score = -math.inf
    best_lower = -math.inf
    best_token = weight.shape[0]
    evaluated = []
    started = time.perf_counter()
    for first in range(0, len(order), traversal_batch_blocks):
        if best_lower > -math.inf and float(upper[int(order[first])]) < best_lower:
            break
        chosen = order[first : first + traversal_batch_blocks]
        for block_tensor in chosen:
            block = int(block_tensor)
            row_start = block * block_size
            row_stop = row_start + block_size
            rows = weight[row_start:row_stop].float()
            scores = torch.mv(rows, h)
            ids = torch.arange(row_start, row_stop, dtype=torch.int64)
            best_score, best_token = update_best(scores, ids, best_score, best_token)
            row_lower = scores - gamma * h_inf * index["token_l1"][row_start:row_stop] - 1e-5
            best_lower = max(best_lower, float(row_lower.max()))
            evaluated.append(block)
    elapsed = time.perf_counter() - started
    evaluated_set = set(evaluated)
    skipped = [block for block in range(len(order)) if block not in evaluated_set]
    maximum_skipped_upper = max((float(upper[block]) for block in skipped), default=-math.inf)
    certified = maximum_skipped_upper < best_lower
    return {
        "top1_id": best_token,
        "top1_score": best_score,
        "best_lower_bound": best_lower,
        "maximum_skipped_upper": maximum_skipped_upper if skipped else None,
        "certificate_gap": best_lower - maximum_skipped_upper if skipped else None,
        "certified": certified,
        "evaluated_blocks": len(evaluated),
        "evaluated_rows": len(evaluated) * block_size,
        "seconds": elapsed,
    }


def dense_top1(weight: torch.Tensor, hidden: torch.Tensor, chunk_rows: int):
    h = hidden.float()
    best_score = -math.inf
    best_token = weight.shape[0]
    started = time.perf_counter()
    for first in range(0, weight.shape[0], chunk_rows):
        last = min(first + chunk_rows, weight.shape[0])
        scores = torch.mv(weight[first:last].float(), h)
        ids = torch.arange(first, last, dtype=torch.int64)
        best_score, best_token = update_best(scores, ids, best_score, best_token)
    return {
        "top1_id": best_token,
        "top1_score": best_score,
        "seconds": time.perf_counter() - started,
    }


def select_request_representative_rows(capture):
    ownership = capture["ownership"]
    selected = [
        row["global_row"]
        for row in ownership
        if row["capture_index"] == 3 and row["depth_index"] == 11
    ]
    if len(selected) != 32:
        raise ValueError(f"expected 32 request-representative rows, found {len(selected)}")
    return selected


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))]


def run(args):
    torch.set_num_threads(args.threads)
    checkpoint = Path(args.checkpoint)
    capture_path = Path(args.capture)
    output = Path(args.output)
    config = json.loads((checkpoint / "config.json").read_text())
    text = config["text_config"]
    if (
        text["hidden_size"] != 5376
        or text["vocab_size"] != 262144
        or not config["tie_word_embeddings"]
        or not text["tie_word_embeddings"]
    ):
        raise ValueError("checkpoint geometry does not match the admitted tied head")
    capture_hash = sha256_file(capture_path)
    if capture_hash != EXPECTED_CAPTURE_SHA256:
        raise ValueError(f"capture hash mismatch: {capture_hash}")
    capture = torch.load(capture_path, map_location="cpu", weights_only=True)
    hidden_states = capture["hidden_states"]
    if tuple(hidden_states.shape) != (1536, 5376) or hidden_states.dtype != torch.bfloat16:
        raise ValueError("capture tensor geometry mismatch")
    weight_view = SafeTensorView(checkpoint / "model-00001-of-00002.safetensors", WEIGHT_KEY)
    try:
        weight = weight_view.tensor
        if tuple(weight.shape) != (262144, 5376):
            raise ValueError("weight tensor geometry mismatch")
        weight_tensor_hash = weight_view.tensor_sha256()
        weight_shard_hash = sha256_file(
            checkpoint / "model-00001-of-00002.safetensors"
        )
        if weight_shard_hash != EXPECTED_WEIGHT_SHARD_SHA256:
            raise ValueError(f"weight shard hash mismatch: {weight_shard_hash}")
        index = build_index(weight, args.block_size, args.chunk_blocks)
        selected = select_request_representative_rows(capture)
        rows = []
        for ordinal, global_row in enumerate(selected):
            candidate = certified_top1(
                weight,
                hidden_states[global_row],
                index,
                args.block_size,
                args.traversal_batch_blocks,
            )
            dense = dense_top1(weight, hidden_states[global_row], args.dense_chunk_rows)
            candidate["dense_top1_id"] = dense["top1_id"]
            candidate["dense_top1_score"] = dense["top1_score"]
            candidate["dense_seconds"] = dense["seconds"]
            candidate["agreement"] = candidate["top1_id"] == dense["top1_id"]
            candidate["global_row"] = global_row
            candidate["request_ordinal"] = ordinal
            rows.append(candidate)
            print(
                json.dumps(
                    {
                        "row": ordinal + 1,
                        "evaluated_fraction": candidate["evaluated_rows"] / weight.shape[0],
                        "agreement": candidate["agreement"],
                        "certified": candidate["certified"],
                    }
                ),
                flush=True,
            )
        vocab = weight.shape[0]
        hidden = weight.shape[1]
        blocks = vocab // args.block_size
        evaluated_fractions = [row["evaluated_rows"] / vocab for row in rows]
        bound_flops = 2 * blocks * hidden + 8 * blocks
        verification_flops = [
            2 * row["evaluated_rows"] * hidden for row in rows
        ]
        total_work_fractions = [
            (bound_flops + verify) / (2 * vocab * hidden)
            for verify in verification_flops
        ]
        candidate_times = [row["seconds"] for row in rows]
        dense_times = [row["dense_seconds"] for row in rows]
        index_bytes = (
            index["centers"].numel() * index["centers"].element_size()
            + index["radii"].numel() * index["radii"].element_size()
            + index["center_l1"].numel() * index["center_l1"].element_size()
            + index["token_l1"].numel() * index["token_l1"].element_size()
        )
        inherited_head_seconds_per_request = 0.010869238160550593
        dense_request_seconds = 0.625149101968745
        ideal_saved_head_fraction = max(0.0, 1.0 - max(total_work_fractions))
        conservative_request_saving_seconds = (
            inherited_head_seconds_per_request * ideal_saved_head_fraction
        )
        result = {
            "schema_version": 1,
            "classification": "centroid_l2_block_discriminator_result",
            "identity": {
                "model": MODEL,
                "revision": REVISION,
                "weight_key": WEIGHT_KEY,
                "weight_shard_sha256": weight_shard_hash,
                "weight_tensor_raw_bf16_sha256": weight_tensor_hash,
                "capture_sha256": capture_hash,
                "capture_provenance": "measured exact H200 c32 final-hidden capture; reused read-only and materialized project-locally",
            },
            "geometry": {
                "vocab": vocab,
                "hidden": hidden,
                "weight_dtype": str(weight.dtype),
                "capture_dtype": str(hidden_states.dtype),
                "capture_rows_total": hidden_states.shape[0],
                "evaluated_rows": len(rows),
                "requests_represented": len(rows),
                "selection": "capture_index=3, depth_index=11, one final-depth row per each of 32 requests",
                "block_size": args.block_size,
                "blocks": blocks,
            },
            "mechanism": {
                "name": "contiguous_centroid_l2_residual_block_bound",
                "semantics": "certified greedy/top-1 only",
                "bound": "h dot centroid + ||h||_2 * max_i ||w_i-centroid||_2 with guarded FP32 reductions",
                "full_softmax_or_sampling_equivalence": False,
                "roundoff_gamma": index["gamma"],
                "radius_guard_factor": index["radius_guard_factor"],
            },
            "agreement": {
                "matching_rows": sum(row["agreement"] for row in rows),
                "total_rows": len(rows),
                "fraction": sum(row["agreement"] for row in rows) / len(rows),
                "all_skips_certified": all(row["certified"] for row in rows),
            },
            "evaluated_vocabulary_fraction": {
                "mean": sum(evaluated_fractions) / len(evaluated_fractions),
                "minimum": min(evaluated_fractions),
                "maximum": max(evaluated_fractions),
                "p50": percentile(evaluated_fractions, 0.5),
                "p90": percentile(evaluated_fractions, 0.9),
            },
            "index": {
                "bytes": index_bytes,
                "gib": index_bytes / 2**30,
                "construction_seconds": index["construction_seconds"],
                "resident_weight_copy_required": False,
            },
            "overhead": {
                "bound_flops_per_row": bound_flops,
                "bound_equivalent_dense_fraction": bound_flops / (2 * vocab * hidden),
                "verification_flops_per_row_mean": sum(verification_flops) / len(rows),
                "total_analytical_head_work_fraction_mean": sum(total_work_fractions)
                / len(rows),
                "total_analytical_head_work_fraction_max": max(total_work_fractions),
                "index_bytes_read_per_row": index_bytes - index["token_l1"].numel() * 4,
                "candidate_cpu_seconds_p50": percentile(candidate_times, 0.5),
                "dense_cpu_seconds_p50": percentile(dense_times, 0.5),
                "timing_scope": "coordinator CPU diagnostic only; not target hardware or endpoint performance",
            },
            "whole_request_relevance": {
                "qualified_dense_seconds_per_request": dense_request_seconds,
                "historical_h200_head_seconds_per_request": inherited_head_seconds_per_request,
                "ideal_head_seconds_saved_under_max_observed_work_fraction": conservative_request_saving_seconds,
                "ideal_whole_request_fraction": conservative_request_saving_seconds
                / dense_request_seconds,
                "interpretation": "conservative component-derived upper bound only; no endpoint claim",
            },
            "rows": rows,
        }
        promote = (
            result["agreement"]["fraction"] == 1.0
            and result["agreement"]["all_skips_certified"]
            and max(total_work_fractions) < 0.8
        )
        result["decision"] = {
            "classification": (
                "advance_target_hardware_component"
                if promote
                else "reject_centroid_l2_block_mechanism"
            ),
            "promote": promote,
            "reason": (
                "certified total analytical head work is below 80% on every measured request"
                if promote
                else "certified candidate coverage plus bound overhead does not remove material head work"
            ),
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, output)
        print(json.dumps(result["decision"]), flush=True)
    finally:
        weight_view.close()


def self_test():
    torch.manual_seed(7)
    weight = torch.randn(32, 12, dtype=torch.float32).to(torch.bfloat16)
    hidden = torch.randn(12, dtype=torch.float32).to(torch.bfloat16)
    index = build_index(weight, 4, 2)
    candidate = certified_top1(weight, hidden, index, 4, 2)
    dense = dense_top1(weight, hidden, 8)
    assert candidate["certified"]
    assert candidate["top1_id"] == dense["top1_id"]
    print(json.dumps({"self_test": "passed", "candidate": candidate, "dense": dense}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint")
    parser.add_argument("--capture")
    parser.add_argument("--output")
    parser.add_argument("--block-size", type=int, default=128)
    parser.add_argument("--chunk-blocks", type=int, default=8)
    parser.add_argument("--traversal-batch-blocks", type=int, default=16)
    parser.add_argument("--dense-chunk-rows", type=int, default=8192)
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    required = (args.checkpoint, args.capture, args.output)
    if not all(required):
        parser.error("--checkpoint, --capture, and --output are required")
    run(args)


if __name__ == "__main__":
    main()
