#!/usr/bin/env python3
"""Build and evaluate a conservative hierarchical exact-MIPS reference."""
from __future__ import annotations

import argparse
import ast
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
WEIGHT_KEY = "model.language_model.embed_tokens.weight"
LEVEL_SIZES = (4096, 256, 32)
SEED = 240729
PROJECTION_DIMENSIONS = 13
EXPECTED_TENSOR_SHA256 = (
    "1053f051b1b894bb5f80eb52cdd434b8028aaad27c3006fcfdec48ac8c46d98d"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    json.loads(temporary.read_text())
    temporary.replace(path)


def gamma(operations: int, unit_roundoff: float = 2.0**-24) -> float:
    product = operations * unit_roundoff
    if product >= 1:
        raise RuntimeError("roundoff_bound_undefined")
    return product / (1.0 - product)


def parse_deadline(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def require_before(deadline: datetime, phase: str) -> None:
    if datetime.now(timezone.utc) >= deadline:
        raise TimeoutError(f"absolute_deadline_reached_before_{phase}")


def select_capture_rows(payload: dict[str, Any]):
    import torch

    hidden = payload["hidden_states"]
    ownership = payload["ownership"]
    if (
        tuple(hidden.shape) != (1536, HIDDEN)
        or hidden.dtype != torch.bfloat16
        or len(ownership) != hidden.shape[0]
        or not bool(torch.isfinite(hidden.float()).all())
    ):
        raise RuntimeError("capture_geometry_dtype_or_finiteness_mismatch")
    request_order = list(dict.fromkeys(str(row["request_id"]) for row in ownership))
    if len(request_order) != REQUESTS:
        raise RuntimeError("capture_request_count_mismatch")
    selected: list[int] = []
    seen: set[str] = set()
    for index, row in enumerate(ownership):
        request_id = str(row["request_id"])
        if request_id not in seen:
            selected.append(index)
            seen.add(request_id)
    if len(selected) != REQUESTS:
        raise RuntimeError("capture_selection_incomplete")
    return hidden[selected].contiguous(), [ownership[index] for index in selected]


def source_line(source: str, fragment: str) -> int:
    for line_number, line in enumerate(source.splitlines(), start=1):
        if fragment in line:
            return line_number
    raise RuntimeError(f"source_fragment_absent:{fragment}")


def recover_stock_sampler(paths: dict[str, Path]) -> dict[str, Any]:
    exact_runner = paths["exact_c32_runner"].read_text()
    sampling_params = paths["sampling_params"].read_text()
    sampling_batch = paths["sampling_batch_info"].read_text()
    sampler = paths["sampler"].read_text()
    min_tokens = paths["min_new_tokens"].read_text()
    protocol = paths["openai_protocol"].read_text()
    logits_processor = paths["logits_processor"].read_text()
    for source in (
        exact_runner,
        sampling_params,
        sampling_batch,
        sampler,
        min_tokens,
        protocol,
        logits_processor,
    ):
        ast.parse(source)

    workload_dicts = []
    for node in ast.walk(ast.parse(exact_runner)):
        if not isinstance(node, ast.Dict):
            continue
        row = {}
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                try:
                    row[key.value] = ast.literal_eval(value)
                except (ValueError, TypeError):
                    row[key.value] = ast.unparse(value)
        if row.get("temperature") == 0 and "prompt" in row:
            workload_dicts.append(row)
    if len(workload_dicts) != 1:
        raise RuntimeError("exact_c32_workload_body_not_unique")
    body = workload_dicts[0]
    required = {
        "temperature": 0,
        "ignore_eos": True,
        "return_token_ids": True,
        "min_tokens": "OUTPUT_TOKENS",
        "max_tokens": "OUTPUT_TOKENS",
    }
    if any(body.get(key) != value for key, value in required.items()):
        raise RuntimeError("exact_c32_sampler_fields_mismatch")
    if any(key in body for key in ("top_k", "top_p", "min_p", "logprobs")):
        raise RuntimeError("unexpected_sampler_truncation_field")

    normalized_params = ast.unparse(ast.parse(sampling_params))
    normalized_batch = ast.unparse(ast.parse(sampling_batch))
    normalized_sampler = ast.unparse(ast.parse(sampler))
    normalized_min_tokens = ast.unparse(ast.parse(min_tokens))
    normalized_protocol = ast.unparse(ast.parse(protocol))
    normalized_logits = ast.unparse(ast.parse(logits_processor))
    structural_requirements = {
        "temperature_zero_sets_top_k_one": "self.top_k = 1" in normalized_params,
        "top_k_one_sets_all_greedy": (
            "is_all_greedy=all((r.sampling_params.top_k <= 1 for r in reqs))"
            in normalized_batch
        ),
        "greedy_returns_argmax": (
            "batch_next_token_ids = torch.argmax(logits, -1)" in normalized_sampler
        ),
        "protocol_maps_min_tokens": (
            "'min_new_tokens': self.min_tokens" in normalized_protocol
        ),
        "min_tokens_masks_stops": (
            "logits[mask] += self.stop_token_penalties[mask]"
            in normalized_min_tokens
        ),
        "softcap_is_monotone_tanh": (
            "self.final_logit_softcapping * torch.tanh("
            in normalized_logits
        ),
    }
    if not all(structural_requirements.values()):
        raise RuntimeError("pinned_stock_sampler_structure_mismatch")

    tokenizer = json.loads(paths["tokenizer"].read_text())
    tokenizer_config = json.loads(paths["tokenizer_config"].read_text())
    token_by_content = {
        str(row["content"]): int(row["id"])
        for row in tokenizer.get("added_tokens", [])
    }
    eos_content = str(tokenizer_config["eos_token"])
    if eos_content not in token_by_content:
        raise RuntimeError("tokenizer_eos_id_not_recoverable")
    stop_ids = {token_by_content[eos_content]}
    if "<|eom_id|>" in token_by_content:
        stop_ids.add(token_by_content["<|eom_id|>"])
    return {
        "classification": "pinned_temperature_zero_greedy_with_min_token_stop_mask",
        "request_body_fields": {key: body[key] for key in sorted(required)},
        "absent_request_fields": ["top_k", "top_p", "min_p", "logprobs"],
        "structural_requirements": structural_requirements,
        "masked_stop_token_ids": sorted(stop_ids),
        "candidate_set_requirement": (
            "Every possible non-stop argmax after monotone softcap and the "
            "min-new-token stop mask must remain in the survivor set."
        ),
        "source_lines": {
            "temperature_zero_normalization": source_line(
                sampling_params, "if 0 <= self.temperature"
            ),
            "all_greedy": source_line(sampling_batch, "is_all_greedy=all"),
            "argmax": source_line(sampler, "torch.argmax(logits, -1)"),
            "min_token_stop_mask": source_line(
                min_tokens, "logits[mask] += self.stop_token_penalties[mask]"
            ),
            "softcap": source_line(
                logits_processor,
                "logits = self.final_logit_softcapping * torch.tanh",
            ),
        },
    }


def balanced_projection_permutation(projection_scores):
    import numpy as np

    scores = projection_scores.numpy()
    permutation = np.arange(VOCAB, dtype=np.int32)
    for depth in range(PROJECTION_DIMENSIONS):
        segment = VOCAB >> depth
        for start in range(0, VOCAB, segment):
            end = start + segment
            ids = permutation[start:end]
            order = np.argsort(scores[ids, depth], kind="stable")
            permutation[start:end] = ids[order]
    return permutation


def build_hierarchy(weight, hidden, deadline: datetime, cache_path: Path):
    import numpy as np
    import torch

    generator = torch.Generator(device="cpu")
    generator.manual_seed(SEED)
    directions = torch.randint(
        0,
        2,
        (HIDDEN, PROJECTION_DIMENSIONS),
        dtype=torch.int8,
        generator=generator,
    )
    directions = directions.float().mul_(2).sub_(1).div_(math.sqrt(HIDDEN))
    projection_scores = torch.empty(
        (VOCAB, PROJECTION_DIMENSIONS), dtype=torch.float32
    )
    full_scores = torch.empty((REQUESTS, VOCAB), dtype=torch.float32)
    row_norm_upper = torch.empty(VOCAB, dtype=torch.float64)
    tensor_digest = hashlib.sha256()
    hidden_float = hidden.float()
    hidden_norm = hidden.double().square().sum(dim=1).sqrt()
    row_chunk = 8192
    scan_started = time.monotonic()
    for row_start in range(0, VOCAB, row_chunk):
        require_before(deadline, "weight_scan")
        row_end = row_start + row_chunk
        block_bf16 = weight[row_start:row_end].contiguous()
        tensor_digest.update(block_bf16.view(torch.uint8).numpy().tobytes())
        block = block_bf16.float()
        projection_scores[row_start:row_end] = block @ directions
        full_scores[:, row_start:row_end] = hidden_float @ block.T
        square_sum = block.square().sum(dim=1)
        row_norm_upper[row_start:row_end] = (
            square_sum.double() / (1.0 - gamma(HIDDEN))
        ).sqrt()
    observed_tensor_digest = tensor_digest.hexdigest()
    if observed_tensor_digest != EXPECTED_TENSOR_SHA256:
        raise RuntimeError("tied_weight_tensor_hash_mismatch")

    require_before(deadline, "projection_partition")
    partition_started = time.monotonic()
    permutation_np = balanced_projection_permutation(projection_scores)
    permutation = torch.from_numpy(permutation_np.astype(np.int64, copy=False))
    if (
        int(torch.unique(permutation).numel()) != VOCAB
        or int(permutation.min()) != 0
        or int(permutation.max()) != VOCAB - 1
    ):
        raise RuntimeError("row_permutation_not_bijective")
    permutation_sha256 = hashlib.sha256(
        permutation_np.astype(np.int32, copy=False).tobytes()
    ).hexdigest()
    del projection_scores

    centers = {
        size: torch.empty((VOCAB // size, HIDDEN), dtype=torch.bfloat16)
        for size in LEVEL_SIZES
    }
    radii = {
        size: torch.empty(VOCAB // size, dtype=torch.float64)
        for size in LEVEL_SIZES
    }
    center_norms = {
        size: torch.empty(VOCAB // size, dtype=torch.float64)
        for size in LEVEL_SIZES
    }
    max_weight_norms = {
        size: torch.empty(VOCAB // size, dtype=torch.float64)
        for size in LEVEL_SIZES
    }
    cluster_started = time.monotonic()
    top_size = LEVEL_SIZES[0]
    for top_start in range(0, VOCAB, top_size):
        require_before(deadline, "cluster_bound_build")
        top_end = top_start + top_size
        ids = permutation[top_start:top_end]
        rows = weight[ids].contiguous().float()
        row_norms = row_norm_upper[ids]
        for size in LEVEL_SIZES:
            groups_per_top = top_size // size
            node_start = top_start // size
            node_end = node_start + groups_per_top
            grouped = rows.reshape(groups_per_top, size, HIDDEN)
            node_centers = grouped.mean(dim=1).to(torch.bfloat16)
            centers[size][node_start:node_end] = node_centers
            residual = grouped - node_centers.float().unsqueeze(1)
            residual_square = residual.square().sum(dim=2)
            radii[size][node_start:node_end] = (
                residual_square.double() / (1.0 - gamma(2 * HIDDEN))
            ).sqrt().max(dim=1).values
            center_square = node_centers.float().square().sum(dim=1)
            center_norms[size][node_start:node_end] = (
                center_square.double() / (1.0 - gamma(HIDDEN))
            ).sqrt()
            max_weight_norms[size][node_start:node_end] = (
                row_norms.reshape(groups_per_top, size).max(dim=1).values
            )
            del residual, residual_square
        del rows

    cache = {
        "schema_version": 1,
        "seed": SEED,
        "projection_dimensions": PROJECTION_DIMENSIONS,
        "level_sizes": LEVEL_SIZES,
        "tied_weight_tensor_sha256": observed_tensor_digest,
        "permutation_sha256": permutation_sha256,
        "permutation": permutation.to(torch.int32),
        "full_scores": full_scores,
        "row_norm_upper": row_norm_upper,
        "hidden_norm": hidden_norm,
        "centers": centers,
        "radii": radii,
        "center_norms": center_norms,
        "max_weight_norms": max_weight_norms,
        "timing": {
            "weight_scan_projection_and_dense_reference_seconds": (
                partition_started - scan_started
            ),
            "balanced_partition_seconds": cluster_started - partition_started,
            "full_vector_cluster_build_seconds": time.monotonic() - cluster_started,
        },
    }
    temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
    torch.save(cache, temporary)
    temporary.replace(cache_path)
    return cache


def load_hierarchy(cache_path: Path):
    import torch

    cache = torch.load(cache_path, map_location="cpu", weights_only=True)
    if (
        cache["schema_version"] != 1
        or tuple(cache["level_sizes"]) != LEVEL_SIZES
        or cache["seed"] != SEED
        or cache["projection_dimensions"] != PROJECTION_DIMENSIONS
        or cache["tied_weight_tensor_sha256"] != EXPECTED_TENSOR_SHA256
    ):
        raise RuntimeError("hierarchy_cache_identity_mismatch")
    return cache


def node_upper_bounds(hidden, hidden_norm, centers, radii, center_norms, max_norms):
    import torch

    center_scores = hidden.float() @ centers.float().T
    center_error = (
        gamma(HIDDEN) * hidden_norm[:, None] * center_norms[None, :]
    )
    exact_real_upper = (
        center_scores.double()
        + center_error
        + hidden_norm[:, None] * radii[None, :]
    )
    accumulation = gamma(HIDDEN) * hidden_norm[:, None] * max_norms[None, :]
    bfloat16_roundoff = 2.0**-8
    output_rounding = (
        bfloat16_roundoff
        / (1.0 - bfloat16_roundoff)
        * (hidden_norm[:, None] * max_norms[None, :] + accumulation)
    )
    return exact_real_upper + accumulation + output_rounding, center_scores


def evaluate_arm(
    name: str,
    lower,
    upper_bounds: dict[int, Any],
    possible_winners,
    dense_reference_ids,
    permutation,
) -> dict[str, Any]:
    import torch

    top_size, middle_size, leaf_size = LEVEL_SIZES
    top_upper = upper_bounds[top_size]
    middle_upper = upper_bounds[middle_size]
    leaf_upper = upper_bounds[leaf_size]
    top_active = top_upper >= lower[:, None]
    middle_parent = torch.arange(middle_upper.shape[1]) // (
        top_size // middle_size
    )
    middle_evaluated = top_active[:, middle_parent]
    middle_active = middle_evaluated & (middle_upper >= lower[:, None])
    leaf_parent = torch.arange(leaf_upper.shape[1]) // (
        middle_size // leaf_size
    )
    leaf_evaluated = middle_active[:, leaf_parent]
    leaf_active = leaf_evaluated & (leaf_upper >= lower[:, None])

    member_active_layout = leaf_active.repeat_interleave(leaf_size, dim=1)
    member_active_token_ids = torch.zeros_like(member_active_layout)
    member_active_token_ids[:, permutation] = member_active_layout
    possible_inside = bool(
        (member_active_token_ids | ~possible_winners).all().item()
    )
    dense_reference_inside = bool(
        member_active_token_ids[
            torch.arange(REQUESTS, dtype=torch.int64), dense_reference_ids
        ]
        .all()
        .item()
    )
    margins = {}
    for size, active, evaluated in (
        (top_size, top_active, torch.ones_like(top_active)),
        (middle_size, middle_active, middle_evaluated),
        (leaf_size, leaf_active, leaf_evaluated),
    ):
        pruned = evaluated & ~active
        values = upper_bounds[size] - lower[:, None]
        margins[str(size)] = (
            float(values[pruned].max().item()) if bool(pruned.any()) else None
        )

    union_leaf = leaf_active.any(dim=0)
    union_member_rows = int(union_leaf.sum().item()) * leaf_size
    logical_member_rows = int(leaf_active.sum().item()) * leaf_size
    dense_weight_bytes = VOCAB * HIDDEN * 2
    member_weight_bytes = union_member_rows * HIDDEN * 2
    node_metadata_bytes = HIDDEN * 2 + 24
    union_middle_metadata = middle_evaluated.any(dim=0)
    union_leaf_metadata = leaf_evaluated.any(dim=0)
    metadata_bytes = (
        top_active.shape[1]
        + int(union_middle_metadata.sum().item())
        + int(union_leaf_metadata.sum().item())
    ) * node_metadata_bytes
    evaluated_node_queries = (
        int(top_active.numel())
        + int(middle_evaluated.sum().item())
        + int(leaf_evaluated.sum().item())
    )
    bound_score_traffic_bytes = evaluated_node_queries * 8
    survivor_token_id_bytes = union_member_rows * 4
    survivor_logit_bytes = logical_member_rows * 4
    candidate_bytes = (
        member_weight_bytes
        + metadata_bytes
        + bound_score_traffic_bytes
        + survivor_token_id_bytes
        + survivor_logit_bytes
    )
    gross_avoidance = 1.0 - member_weight_bytes / dense_weight_bytes
    net_avoidance = 1.0 - candidate_bytes / dense_weight_bytes
    return {
        "name": name,
        "stock_candidate_set_inside_survivors": possible_inside,
        "dense_reference_winner_inside_survivors": dense_reference_inside,
        "pruned_node_max_upper_minus_lower_by_rows": margins,
        "logical_survivor_member_rows": logical_member_rows,
        "logical_survivor_member_fraction": (
            logical_member_rows / (REQUESTS * VOCAB)
        ),
        "physical_union_survivor_leaves": int(union_leaf.sum().item()),
        "physical_union_survivor_member_rows": union_member_rows,
        "physical_union_survivor_member_fraction": union_member_rows / VOCAB,
        "gross_physical_member_weight_bytes_avoided_fraction": gross_avoidance,
        "net_physical_bytes_avoided_fraction": net_avoidance,
        "traffic": {
            "dense_weight_bytes": dense_weight_bytes,
            "member_weight_bytes": member_weight_bytes,
            "centroid_radius_tree_metadata_bytes": metadata_bytes,
            "bound_score_traffic_bytes": bound_score_traffic_bytes,
            "survivor_token_id_bytes": survivor_token_id_bytes,
            "survivor_logit_bytes": survivor_logit_bytes,
            "candidate_total_bytes": candidate_bytes,
            "net_bytes_saved": dense_weight_bytes - candidate_bytes,
            "union_middle_nodes_read": int(union_middle_metadata.sum().item()),
            "union_leaf_nodes_read": int(union_leaf_metadata.sum().item()),
            "evaluated_node_queries": evaluated_node_queries,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-index", action="store_true")
    args = parser.parse_args()

    import torch
    from safetensors import safe_open

    started = time.monotonic()
    contract = json.loads(args.contract.read_text())
    deadline = parse_deadline(contract["absolute_deadline_utc"])
    require_before(deadline, "identity_validation")
    paths = {
        "capture": args.input_dir / "hidden_states.pt",
        "capture_terminal": args.input_dir / "EXACT_CAPTURE_TERMINAL.json",
        "weight_shard": args.input_dir / "model-00001-of-00002.safetensors",
        "index": args.input_dir / "model.safetensors.index.json",
        "config": args.input_dir / "config.json",
        "logits_processor": args.input_dir / "logits_processor.py",
        "exact_c32_runner": args.input_dir / "exact_c32_runner.py",
        "sampler": args.input_dir / "sampler.py",
        "sampling_params": args.input_dir / "sampling_params.py",
        "sampling_batch_info": args.input_dir / "sampling_batch_info.py",
        "min_new_tokens": args.input_dir / "min_new_tokens.py",
        "openai_protocol": args.input_dir / "openai_protocol.py",
        "tokenizer": args.input_dir / "tokenizer.json",
        "tokenizer_config": args.input_dir / "tokenizer_config.json",
    }
    identity_fields = {
        "capture": "capture_sha256",
        "capture_terminal": "capture_terminal_sha256",
        "index": "checkpoint_index_sha256",
        "config": "config_sha256",
        "logits_processor": "logits_processor_sha256",
        "exact_c32_runner": "exact_c32_runner_sha256",
        "sampler": "sampler_sha256",
        "sampling_params": "sampling_params_sha256",
        "sampling_batch_info": "sampling_batch_info_sha256",
        "min_new_tokens": "min_new_tokens_penalizer_sha256",
        "openai_protocol": "openai_protocol_sha256",
        "tokenizer": "tokenizer_sha256",
        "tokenizer_config": "tokenizer_config_sha256",
    }
    identities = {
        name: sha256_file(paths[name]) for name in identity_fields
    }
    for name, contract_field in identity_fields.items():
        if identities[name] != contract["inputs"][contract_field]:
            raise RuntimeError(f"{name}_hash_mismatch")
    identities["contract"] = sha256_file(args.contract)
    identities["runner"] = sha256_file(Path(__file__).resolve())
    identities["weight_shard"] = contract["inputs"]["weight_shard_sha256"]

    stock_sampler = recover_stock_sampler(paths)
    config = json.loads(paths["config"].read_text())
    index = json.loads(paths["index"].read_text())
    text_config = config["text_config"]
    if (
        text_config["hidden_size"] != HIDDEN
        or text_config["vocab_size"] != VOCAB
        or not text_config["tie_word_embeddings"]
        or text_config["final_logit_softcapping"] != 30.0
        or index["weight_map"].get(WEIGHT_KEY) != paths["weight_shard"].name
    ):
        raise RuntimeError("pinned_model_geometry_or_mapping_mismatch")

    payload = torch.load(
        paths["capture"], map_location="cpu", weights_only=True, mmap=True
    )
    hidden, selected_ownership = select_capture_rows(payload)
    with safe_open(paths["weight_shard"], framework="pt", device="cpu") as handle:
        if WEIGHT_KEY not in handle.keys():
            raise RuntimeError("tied_weight_key_absent")
        weight = handle.get_tensor(WEIGHT_KEY)
    if tuple(weight.shape) != (VOCAB, HIDDEN) or weight.dtype != torch.bfloat16:
        raise RuntimeError("tied_weight_geometry_or_dtype_mismatch")

    if args.reuse_index:
        if not args.cache.exists():
            raise RuntimeError("reuse_index_cache_absent")
        cache = load_hierarchy(args.cache)
        cache_reused = True
    else:
        if args.cache.exists():
            raise RuntimeError("index_cache_already_exists")
        cache = build_hierarchy(weight, hidden, deadline, args.cache)
        cache_reused = False
    require_before(deadline, "hierarchy_consumer")

    hidden_norm = cache["hidden_norm"]
    full_scores = cache["full_scores"]
    row_norm = cache["row_norm_upper"]
    permutation = cache["permutation"].long()
    reference_error = gamma(HIDDEN) * hidden_norm[:, None] * row_norm[None, :]
    stock_accumulation = (
        gamma(HIDDEN) * hidden_norm[:, None] * row_norm[None, :]
    )
    bfloat16_roundoff = 2.0**-8
    stock_output_rounding = (
        bfloat16_roundoff
        / (1.0 - bfloat16_roundoff)
        * (
            hidden_norm[:, None] * row_norm[None, :]
            + stock_accumulation
        )
    )
    stock_total_error = (
        reference_error + stock_accumulation + stock_output_rounding
    )
    conservative_excluded = set(stock_sampler["masked_stop_token_ids"])
    config_eos = text_config.get("eos_token_id", [])
    if isinstance(config_eos, int):
        config_eos = [config_eos]
    conservative_excluded.update(int(value) for value in config_eos)
    allowed_incumbent = torch.ones(VOCAB, dtype=torch.bool)
    allowed_incumbent[list(sorted(conservative_excluded))] = False
    lower_matrix = full_scores.double() - stock_total_error
    upper_matrix = full_scores.double() + stock_total_error
    oracle_lower, oracle_ids = lower_matrix.masked_fill(
        ~allowed_incumbent[None, :], float("-inf")
    ).max(dim=1)
    possible_winners = upper_matrix >= oracle_lower[:, None]
    possible_winners[:, stock_sampler["masked_stop_token_ids"]] = False
    dense_reference_ids = full_scores.masked_fill(
        ~allowed_incumbent[None, :], float("-inf")
    ).argmax(dim=1)

    upper_bounds = {}
    centroid_scores = {}
    for size in LEVEL_SIZES:
        upper_bounds[size], centroid_scores[size] = node_upper_bounds(
            hidden,
            hidden_norm,
            cache["centers"][size],
            cache["radii"][size],
            cache["center_norms"][size],
            cache["max_weight_norms"][size],
        )
    leaf_scores = centroid_scores[LEVEL_SIZES[-1]]
    seed_leaves = leaf_scores.argmax(dim=1)
    seed_ids = []
    leaf_size = LEVEL_SIZES[-1]
    for query, leaf in enumerate(seed_leaves.tolist()):
        candidates = permutation[leaf * leaf_size : (leaf + 1) * leaf_size]
        candidates = [
            int(value)
            for value in candidates.tolist()
            if int(value) not in conservative_excluded
        ]
        if not candidates:
            raise RuntimeError("seed_leaf_has_no_definitely_unmasked_row")
        candidate_tensor = torch.tensor(candidates, dtype=torch.int64)
        best = candidate_tensor[
            lower_matrix[query, candidate_tensor].argmax()
        ]
        seed_ids.append(int(best))
    seed_ids_tensor = torch.tensor(seed_ids, dtype=torch.int64)
    seed_lower = lower_matrix[
        torch.arange(REQUESTS, dtype=torch.int64), seed_ids_tensor
    ]

    implementable = evaluate_arm(
        "implementable_seed_incumbent",
        seed_lower,
        upper_bounds,
        possible_winners,
        dense_reference_ids,
        permutation,
    )
    oracle = evaluate_arm(
        "optimistic_oracle_incumbent",
        oracle_lower,
        upper_bounds,
        possible_winners,
        dense_reference_ids,
        permutation,
    )
    correctness = (
        implementable["stock_candidate_set_inside_survivors"]
        and oracle["stock_candidate_set_inside_survivors"]
        and implementable["dense_reference_winner_inside_survivors"]
        and oracle["dense_reference_winner_inside_survivors"]
    )
    gross_gate = (
        oracle["gross_physical_member_weight_bytes_avoided_fraction"] > 0.05
    )
    net_gate = oracle["net_physical_bytes_avoided_fraction"] > 0
    promote = correctness and gross_gate and net_gate
    if not correctness:
        decision = "typed_falsification_stock_candidate_certificate_failed"
    elif not gross_gate:
        decision = "typed_falsification_cluster_radius_union_too_loose"
    elif not net_gate:
        decision = "typed_falsification_cluster_metadata_net_nonpositive"
    else:
        decision = "reference_candidate_promote_h200_exact_consumer_component"

    node_count = sum(VOCAB // size for size in LEVEL_SIZES)
    node_metadata_bytes = HIDDEN * 2 + 24
    dense_weight_bytes = VOCAB * HIDDEN * 2
    permuted_weight_storage_bytes = dense_weight_bytes
    index_storage_bytes = (
        node_count * node_metadata_bytes + VOCAB * 4
    )
    inherited_head_seconds = (
        contract["slo"]["campaign_denominator_seconds_per_request"]
        * contract["slo"]["inherited_output_consumer_interval_fraction"]
    )
    oracle_net_fraction = oracle["net_physical_bytes_avoided_fraction"]
    optimistic_seconds_saved = inherited_head_seconds * oracle_net_fraction
    result = {
        "schema_version": 1,
        "classification": "lossless_output_head_cluster_mips_reference_terminal",
        "decision": decision,
        "promote_to_h200_component": promote,
        "identities": {
            **identities,
            "tied_weight_tensor": cache["tied_weight_tensor_sha256"],
            "permutation": cache["permutation_sha256"],
        },
        "geometry": {
            "model": "google/gemma-4-31B-it",
            "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "weight_key": WEIGHT_KEY,
            "weight_shape": [VOCAB, HIDDEN],
            "weight_dtype": str(weight.dtype),
            "capture_shape": list(payload["hidden_states"].shape),
            "capture_dtype": str(payload["hidden_states"].dtype),
            "sample_rows": REQUESTS,
            "requests": REQUESTS,
            "selected_capture_rows": [
                {
                    "global_row": row["global_row"],
                    "request_id": row["request_id"],
                    "capture_index": row["capture_index"],
                    "depth_index": row["depth_index"],
                    "position": int(
                        payload["positions"][int(row["global_row"])].item()
                    ),
                }
                for row in selected_ownership
            ],
        },
        "stock_consumer": {
            **stock_sampler,
            "softcap": "30 * tanh(pre_softcap_logit / 30), monotone",
            "conservatively_excluded_from_incumbents": sorted(
                conservative_excluded
            ),
            "stock_rounding_scope": (
                "Guarded CPU FP32 reference error plus stock BF16 accumulation "
                "and BF16 output-rounding envelopes."
            ),
        },
        "mechanism": {
            "name": "balanced_random_projection_full_vector_centroid_radius_tree",
            "seed": SEED,
            "projection_dimensions": PROJECTION_DIMENSIONS,
            "level_rows": list(LEVEL_SIZES),
            "leaf_rows": LEVEL_SIZES[-1],
            "layout": (
                "Recursive median partitions define a token-ID-preserving "
                "permutation; each leaf is contiguous in a separate output layout."
            ),
            "bound": (
                "guarded centroid dot + hidden_norm * guarded full-vector radius "
                "+ conservative stock member-error envelope"
            ),
            "all_vocabulary_rows_reachable": True,
        },
        "correctness": {
            "all_inputs_finite": True,
            "row_permutation_bijective": True,
            "stock_candidate_set_inside_all_reported_survivor_sets": correctness,
            "possible_stock_candidate_rows_mean": float(
                possible_winners.sum(dim=1).double().mean().item()
            ),
            "possible_stock_candidate_rows_max": int(
                possible_winners.sum(dim=1).max().item()
            ),
            "dense_reference_ids_sha256": hashlib.sha256(
                dense_reference_ids.to(torch.int32).numpy().tobytes()
            ).hexdigest(),
            "oracle_incumbent_ids_sha256": hashlib.sha256(
                oracle_ids.to(torch.int32).numpy().tobytes()
            ).hexdigest(),
            "seed_incumbent_ids_sha256": hashlib.sha256(
                seed_ids_tensor.to(torch.int32).numpy().tobytes()
            ).hexdigest(),
        },
        "results": {
            "implementable": implementable,
            "optimistic_oracle": oracle,
        },
        "storage": {
            "permuted_output_weight_storage_bytes": permuted_weight_storage_bytes,
            "permuted_output_weight_is_additional_because_embedding_is_tied": True,
            "centroid_radius_tree_and_token_map_bytes": index_storage_bytes,
            "total_additional_runtime_storage_bytes": (
                permuted_weight_storage_bytes + index_storage_bytes
            ),
            "index_build_is_offline": True,
            "project_cache_bytes": args.cache.stat().st_size,
        },
        "economics": {
            "campaign_denominator_seconds_per_request": contract["slo"][
                "campaign_denominator_seconds_per_request"
            ],
            "campaign_target_seconds_per_request": contract["slo"][
                "campaign_target_seconds_per_request"
            ],
            "inherited_output_consumer_interval_fraction": contract["slo"][
                "inherited_output_consumer_interval_fraction"
            ],
            "inherited_output_consumer_seconds_per_request": inherited_head_seconds,
            "optimistic_net_seconds_saved": optimistic_seconds_saved,
            "optimistic_service_seconds_per_request": (
                contract["slo"]["campaign_denominator_seconds_per_request"]
                - optimistic_seconds_saved
            ),
            "interpretation": (
                "The byte-proportional time value deliberately credits every net "
                "saved byte as proportional removal of the inherited full output-"
                "consumer interval and does not charge target-H200 control overhead."
            ),
        },
        "timing": {
            **cache["timing"],
            "cache_reused": cache_reused,
            "total_cpu_reference_seconds": time.monotonic() - started,
            "cpu_threads": torch.get_num_threads(),
            "performance_scope": "diagnostic CPU build/traversal only",
        },
        "resource_use": {
            "actual_spend_usd": 0.0,
            "provider_spend_usd": 0.0,
            "gpu_claimed": False,
            "gpu_invocations": 0,
            "provider_mutation": False,
            "shared_inputs_read_only": True,
        },
        "decision_gate": {
            "gross_physical_member_weight_avoidance_gt_5_percent": gross_gate,
            "optimistic_net_bytes_positive": net_gate,
            "stock_candidate_set_certified": correctness,
            "component_only": True,
            "endpoint_speed_claim": False,
        },
    }
    atomic_json(args.output, result)
    print(
        json.dumps(
            {
                "decision": decision,
                "promote": promote,
                "oracle_gross_avoided_fraction": oracle[
                    "gross_physical_member_weight_bytes_avoided_fraction"
                ],
                "oracle_net_avoided_fraction": oracle[
                    "net_physical_bytes_avoided_fraction"
                ],
                "oracle_union_rows": oracle[
                    "physical_union_survivor_member_rows"
                ],
                "total_seconds": result["timing"]["total_cpu_reference_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
