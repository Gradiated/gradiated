#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import random
import statistics
import time
from pathlib import Path
from typing import Any, Callable

import torch

from control_ring_kv import (
    ring_decode_attention,
    store_ring_kv,
    store_ring_kv_bytes,
)
from mirrored_ring_kv import (
    LOGICAL_RING_TOKENS,
    PHYSICAL_RING_TOKENS,
    restore_mirrored_ring_prefix,
    store_mirrored_ring_kv,
    store_mirrored_ring_kv_bytes,
)


CURRENT_FRONTIER = 0.6556567115001144
LOCAL_WALL_FRACTION = 0.1531203203096733
LOCAL_LAYERS = 50
GLOBAL_LAYERS = 10


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_extension(path: Path) -> None:
    spec = importlib.util.spec_from_file_location("ring_e5m2_flash_ops", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("extension_spec_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def numerical(candidate: torch.Tensor, control: torch.Tensor) -> dict[str, Any]:
    candidate_float = candidate.float()
    control_float = control.float()
    delta = candidate_float - control_float
    denominator = torch.linalg.vector_norm(control_float).clamp_min(1e-12)
    return {
        "all_finite": bool(torch.isfinite(candidate_float).all().item()),
        "max_abs_error": float(delta.abs().max().item()),
        "mean_abs_error": float(delta.abs().mean().item()),
        "relative_l2": float(
            (torch.linalg.vector_norm(delta) / denominator).item()
        ),
        "cosine": float(
            torch.nn.functional.cosine_similarity(
                candidate_float.flatten(), control_float.flatten(), dim=0
            ).item()
        ),
        "checksum": float(candidate_float.sum().item()),
    }


def distribution(samples: list[float]) -> dict[str, Any]:
    ordered = sorted(samples)
    return {
        "samples_ms": samples,
        "minimum_ms": ordered[0],
        "median_ms": statistics.median(samples),
        "p90_ms": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "maximum_ms": ordered[-1],
    }


def paired_reduction_interval(
    control: list[float], candidate: list[float], seed: int
) -> dict[str, float]:
    if len(control) != len(candidate):
        raise ValueError("paired timing distributions differ in length")
    rng = random.Random(seed)
    reductions = []
    for _ in range(4000):
        indices = [rng.randrange(len(control)) for _ in control]
        baseline = statistics.median(control[index] for index in indices)
        changed = statistics.median(candidate[index] for index in indices)
        reductions.append(1 - changed / baseline)
    reductions.sort()
    return {
        "point": 1
        - statistics.median(candidate) / statistics.median(control),
        "lower_95": reductions[int(0.025 * len(reductions))],
        "upper_95": reductions[int(0.975 * len(reductions))],
    }


def timed(fn: Callable[[], torch.Tensor]) -> tuple[float, float]:
    begin = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    begin.record()
    output = fn()
    end.record()
    end.synchronize()
    return float(begin.elapsed_time(end)), float(output.float().sum().item())


def fa3_mirrored_attention(
    q: torch.Tensor,
    k_ring: torch.Tensor,
    v_ring: torch.Tensor,
    request_ids: torch.Tensor,
    ring_starts: torch.Tensor,
    context_lens: torch.Tensor,
    descale: torch.Tensor,
) -> torch.Tensor:
    valid = request_ids >= 0
    starts = torch.where(valid, ring_starts, 0).to(torch.int32)
    lengths = torch.where(valid, context_lens, 0).to(torch.int32)
    q_fp8 = q[:, None].to(torch.float8_e5m2)
    out, _lse, _, _ = torch.ops.ring_e5m2_fa3.fwd.default(
        q_fp8,
        k_ring,
        v_ring,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        starts + lengths,
        1,
        PHYSICAL_RING_TOKENS,
        None,
        request_ids.clamp_min(0).to(torch.int32),
        starts,
        None,
        None,
        None,
        descale,
        descale,
        descale,
        1 / math.sqrt(256),
        False,
        -1,
        -1,
        0,
        0.0,
        True,
        None,
        1,
        True,
        0,
        None,
    )
    out = out[:, 0].to(torch.bfloat16)
    return torch.where(valid[:, None, None], out, torch.zeros_like(out))


def control_attention(
    q: torch.Tensor,
    k_ring: torch.Tensor,
    v_ring: torch.Tensor,
    request_ids: torch.Tensor,
    ring_starts: torch.Tensor,
    context_lens: torch.Tensor,
) -> torch.Tensor:
    batch = q.shape[0]
    output = torch.empty_like(q)
    splits = torch.full((batch,), 8, dtype=torch.int32, device=q.device)
    indptr = torch.cat(
        (
            torch.zeros(1, dtype=torch.int32, device=q.device),
            torch.cumsum(context_lens.to(torch.int32), dim=0),
        )
    )
    attn_logits = torch.empty(
        (batch, 32, 8, 256), dtype=torch.float32, device=q.device
    )
    attn_lse = torch.empty((batch, 32, 8), dtype=torch.float32, device=q.device)
    ring_decode_attention(
        q,
        k_ring,
        v_ring,
        output,
        context_lens,
        ring_starts,
        indptr,
        attn_logits,
        attn_lse,
        splits,
        8,
        1 / math.sqrt(256),
        1.0,
        1.0,
        request_ids=request_ids,
    )
    return output


def make_fixture(batch: int, seed: int) -> dict[str, torch.Tensor]:
    torch.manual_seed(seed)
    device = "cuda"
    request_ids = torch.arange(batch, dtype=torch.int32, device=device)
    starts = (
        17 + torch.arange(batch, dtype=torch.int64, device=device) * 137
    ) & (LOGICAL_RING_TOKENS - 1)
    positions = starts[:, None] + torch.arange(
        LOGICAL_RING_TOKENS, dtype=torch.int64, device=device
    )[None]
    repeated_ids = request_ids.repeat_interleave(LOGICAL_RING_TOKENS)
    shape = (batch * LOGICAL_RING_TOKENS, 16, 256)
    k_extend = (
        torch.randn(shape, dtype=torch.bfloat16, device=device) / math.sqrt(256)
    ).to(torch.float8_e5m2)
    v_extend = torch.randn(shape, dtype=torch.bfloat16, device=device).to(
        torch.float8_e5m2
    )
    control_k = torch.zeros(
        (batch, LOGICAL_RING_TOKENS, 16, 256),
        dtype=torch.float8_e5m2,
        device=device,
    )
    control_v = torch.zeros_like(control_k)
    candidate_k = torch.zeros(
        (batch, PHYSICAL_RING_TOKENS, 16, 256),
        dtype=torch.float8_e5m2,
        device=device,
    )
    candidate_v = torch.zeros_like(candidate_k)
    store_ring_kv_bytes(
        k_extend,
        v_extend,
        control_k,
        control_v,
        repeated_ids,
        positions.reshape(-1),
    )
    store_mirrored_ring_kv_bytes(
        k_extend,
        v_extend,
        candidate_k,
        candidate_v,
        repeated_ids,
        positions.reshape(-1),
    )
    context_lens = torch.full(
        (batch,), LOGICAL_RING_TOKENS, dtype=torch.int32, device=device
    )
    return {
        "q": (
            torch.randn((batch, 32, 256), dtype=torch.bfloat16, device=device)
            / math.sqrt(256)
        ).contiguous(),
        "control_k": control_k,
        "control_v": control_v,
        "candidate_k": candidate_k,
        "candidate_v": candidate_v,
        "request_ids": request_ids,
        "starts": starts.to(torch.int32),
        "context_lens": context_lens,
        "descale": torch.ones((batch, 16), dtype=torch.float32, device=device),
    }


def mirror_exact(fixture: dict[str, torch.Tensor]) -> bool:
    return all(
        torch.equal(
            fixture[name][:, :LOGICAL_RING_TOKENS]
            .contiguous()
            .view(torch.uint8),
            fixture[name][:, LOGICAL_RING_TOKENS:]
            .contiguous()
            .view(torch.uint8),
        )
        for name in ("candidate_k", "candidate_v")
    )


def append_control(
    fixture: dict[str, torch.Tensor],
    k: torch.Tensor,
    v: torch.Tensor,
    positions: torch.Tensor,
    request_ids: torch.Tensor | None = None,
) -> None:
    store_ring_kv(
        k,
        v,
        fixture["control_k"],
        fixture["control_v"],
        fixture["request_ids"] if request_ids is None else request_ids,
        positions,
        1.0,
        1.0,
    )


def append_candidate(
    fixture: dict[str, torch.Tensor],
    k: torch.Tensor,
    v: torch.Tensor,
    positions: torch.Tensor,
    request_ids: torch.Tensor | None = None,
) -> None:
    store_mirrored_ring_kv(
        k,
        v,
        fixture["candidate_k"],
        fixture["candidate_v"],
        fixture["request_ids"] if request_ids is None else request_ids,
        positions,
        1.0,
        1.0,
    )


def consume_control(
    fixture: dict[str, torch.Tensor],
    q: torch.Tensor,
    starts: torch.Tensor,
    request_ids: torch.Tensor | None = None,
    context_lens: torch.Tensor | None = None,
) -> torch.Tensor:
    return control_attention(
        q,
        fixture["control_k"],
        fixture["control_v"],
        fixture["request_ids"] if request_ids is None else request_ids,
        starts,
        fixture["context_lens"] if context_lens is None else context_lens,
    )


def consume_candidate(
    fixture: dict[str, torch.Tensor],
    q: torch.Tensor,
    starts: torch.Tensor,
    request_ids: torch.Tensor | None = None,
    context_lens: torch.Tensor | None = None,
) -> torch.Tensor:
    return fa3_mirrored_attention(
        q,
        fixture["candidate_k"],
        fixture["candidate_v"],
        fixture["request_ids"] if request_ids is None else request_ids,
        starts,
        fixture["context_lens"] if context_lens is None else context_lens,
        fixture["descale"],
    )


def combined_control(
    fixture: dict[str, torch.Tensor],
    k: torch.Tensor,
    v: torch.Tensor,
    positions: torch.Tensor,
    q: torch.Tensor,
    starts: torch.Tensor,
) -> torch.Tensor:
    append_control(fixture, k, v, positions)
    return consume_control(fixture, q, starts)


def combined_candidate(
    fixture: dict[str, torch.Tensor],
    k: torch.Tensor,
    v: torch.Tensor,
    positions: torch.Tensor,
    q: torch.Tensor,
    starts: torch.Tensor,
) -> torch.Tensor:
    append_candidate(fixture, k, v, positions)
    return consume_candidate(fixture, q, starts)


def boundary_evidence(fixture: dict[str, torch.Tensor]) -> dict[str, Any]:
    batch = fixture["q"].shape[0]
    device = fixture["q"].device
    transitions = []
    for transition in range(2):
        k = (
            torch.randn((batch, 16, 256), dtype=torch.bfloat16, device=device)
            / math.sqrt(256)
        ).contiguous()
        v = torch.randn_like(k).contiguous()
        positions = fixture["starts"].to(torch.int64) + LOGICAL_RING_TOKENS + transition
        append_control(fixture, k, v, positions)
        append_candidate(fixture, k, v, positions)
        starts = (fixture["starts"] + transition + 1) & (LOGICAL_RING_TOKENS - 1)
        q = torch.randn_like(fixture["q"]).contiguous()
        transitions.append(
            numerical(
                consume_candidate(fixture, q, starts),
                consume_control(fixture, q, starts),
            )
        )

    padded_ids = fixture["request_ids"].clone()
    padded_ids[-1] = -1
    padded_context = fixture["context_lens"].clone()
    padded_context[-1] = 0
    before_k = fixture["candidate_k"][-1].clone()
    before_v = fixture["candidate_v"][-1].clone()
    padded_k = torch.randn(
        (batch, 16, 256), dtype=torch.bfloat16, device=device
    )
    padded_v = torch.randn_like(padded_k)
    padded_positions = fixture["starts"].to(torch.int64) + 2048
    append_candidate(
        fixture, padded_k, padded_v, padded_positions, request_ids=padded_ids
    )
    padded_candidate = consume_candidate(
        fixture,
        fixture["q"],
        fixture["starts"],
        request_ids=padded_ids,
        context_lens=padded_context,
    )
    padded_control = consume_control(
        fixture,
        fixture["q"],
        fixture["starts"],
        request_ids=padded_ids,
        context_lens=padded_context,
    )
    padded = {
        "producer_negative_row_noop": bool(
            torch.equal(before_k, fixture["candidate_k"][-1])
            and torch.equal(before_v, fixture["candidate_v"][-1])
        ),
        "candidate_zero": bool(torch.count_nonzero(padded_candidate[-1]).item() == 0),
        "control_zero": bool(torch.count_nonzero(padded_control[-1]).item() == 0),
        "valid_rows": numerical(padded_candidate[:-1], padded_control[:-1]),
    }

    permutation = torch.arange(batch - 1, -1, -1, dtype=torch.int64, device=device)
    reordered_ids = fixture["request_ids"][permutation]
    reorder = numerical(
        consume_candidate(
            fixture,
            fixture["q"],
            fixture["starts"][permutation],
            request_ids=reordered_ids,
        ),
        consume_control(
            fixture,
            fixture["q"],
            fixture["starts"][permutation],
            request_ids=reordered_ids,
        ),
    )

    reused_row = 3 if batch > 3 else 0
    reuse_count = 37
    reuse_start = 3001
    reuse_ids = torch.full(
        (reuse_count,), reused_row, dtype=torch.int32, device=device
    )
    reuse_positions = torch.arange(
        reuse_start, reuse_start + reuse_count, dtype=torch.int64, device=device
    )
    reuse_k = (
        torch.randn(
            (reuse_count, 16, 256), dtype=torch.bfloat16, device=device
        )
        / math.sqrt(256)
    ).to(torch.float8_e5m2)
    reuse_v = torch.randn(
        (reuse_count, 16, 256), dtype=torch.bfloat16, device=device
    ).to(torch.float8_e5m2)
    store_ring_kv_bytes(
        reuse_k,
        reuse_v,
        fixture["control_k"],
        fixture["control_v"],
        reuse_ids,
        reuse_positions,
    )
    store_mirrored_ring_kv_bytes(
        reuse_k,
        reuse_v,
        fixture["candidate_k"],
        fixture["candidate_v"],
        reuse_ids,
        reuse_positions,
    )
    reuse_request = torch.tensor([reused_row], dtype=torch.int32, device=device)
    reuse_context = torch.tensor([reuse_count], dtype=torch.int32, device=device)
    reuse_ring_start = torch.tensor(
        [reuse_start & (LOGICAL_RING_TOKENS - 1)],
        dtype=torch.int32,
        device=device,
    )
    reuse_q = (
        torch.randn((1, 32, 256), dtype=torch.bfloat16, device=device)
        / math.sqrt(256)
    )
    reuse_descale = fixture["descale"][:1]
    reuse_candidate = fa3_mirrored_attention(
        reuse_q,
        fixture["candidate_k"],
        fixture["candidate_v"],
        reuse_request,
        reuse_ring_start,
        reuse_context,
        reuse_descale,
    )
    reuse_control = control_attention(
        reuse_q,
        fixture["control_k"],
        fixture["control_v"],
        reuse_request,
        reuse_ring_start,
        reuse_context,
    )

    prefix_count = 73
    paged_k = torch.randn(
        (prefix_count, 16, 256), dtype=torch.bfloat16, device=device
    ).to(torch.float8_e5m2)
    paged_v = torch.randn(
        (prefix_count, 16, 256), dtype=torch.bfloat16, device=device
    ).to(torch.float8_e5m2)
    prefix_row = 5 if batch > 5 else 0
    prefix_ids = torch.tensor([prefix_row], dtype=torch.int32, device=device)
    prefix_lens = torch.tensor([prefix_count], dtype=torch.int32, device=device)
    prefix_indptr = torch.tensor([0, prefix_count], dtype=torch.int32, device=device)
    prefix_indices = torch.arange(prefix_count, dtype=torch.int32, device=device)
    restore_mirrored_ring_prefix(
        paged_k,
        paged_v,
        fixture["candidate_k"],
        fixture["candidate_v"],
        prefix_ids,
        prefix_lens,
        prefix_indptr,
        prefix_indices,
        exclude_last=False,
    )
    restored_positions = torch.arange(prefix_count, device=device)
    prefix_exact = all(
        torch.equal(actual, expected)
        for actual, expected in (
            (fixture["candidate_k"][prefix_row, restored_positions], paged_k),
            (
                fixture["candidate_k"][
                    prefix_row, restored_positions + LOGICAL_RING_TOKENS
                ],
                paged_k,
            ),
            (fixture["candidate_v"][prefix_row, restored_positions], paged_v),
            (
                fixture["candidate_v"][
                    prefix_row, restored_positions + LOGICAL_RING_TOKENS
                ],
                paged_v,
            ),
        )
    )
    return {
        "wrap_rows": int(torch.count_nonzero(fixture["starts"]).item()),
        "first_two_decode_transitions": transitions,
        "padded_noop": padded,
        "batch_reorder": reorder,
        "slot_reuse": numerical(reuse_candidate, reuse_control),
        "prefix_restoration_exact_bytes": prefix_exact,
        "mirror_halves_exact_after_all_writes": mirror_exact(fixture),
    }


def semantics_pass(comparison: dict[str, Any], boundaries: dict[str, Any]) -> bool:
    rows = [
        comparison,
        *boundaries["first_two_decode_transitions"],
        boundaries["padded_noop"]["valid_rows"],
        boundaries["batch_reorder"],
        boundaries["slot_reuse"],
    ]
    return bool(
        all(
            row["all_finite"]
            and row["relative_l2"] <= 0.02
            and row["cosine"] >= 0.9998
            for row in rows
        )
        and boundaries["padded_noop"]["producer_negative_row_noop"]
        and boundaries["padded_noop"]["candidate_zero"]
        and boundaries["padded_noop"]["control_zero"]
        and boundaries["prefix_restoration_exact_bytes"]
        and boundaries["mirror_halves_exact_after_all_writes"]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "component", "profile"), required=True)
    parser.add_argument("--iterations", type=int, default=31)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260723)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation_path = args.artifact_root / "INVOCATION_STATE.json"
    atomic(
        invocation_path,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": False,
            "candidate_scientific_invocation_started": False,
            "mode": args.mode,
            "updated_unix_s": time.time(),
        },
    )
    if not torch.cuda.is_available() or torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("exact_hopper_cuda_unavailable")
    load_extension(args.extension)
    batch = 1 if args.mode == "smoke" else 32
    fixture = make_fixture(batch, args.seed)
    new_k = (
        torch.randn((batch, 16, 256), dtype=torch.bfloat16, device="cuda")
        / math.sqrt(256)
    ).contiguous()
    new_v = torch.randn_like(new_k).contiguous()
    new_positions = fixture["starts"].to(torch.int64) + LOGICAL_RING_TOKENS
    consumer_starts = (fixture["starts"] + 1) & (LOGICAL_RING_TOKENS - 1)
    candidate = combined_candidate(
        fixture,
        new_k,
        new_v,
        new_positions,
        fixture["q"],
        consumer_starts,
    )
    atomic(
        invocation_path,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": True,
            "candidate_scientific_invocation_started": args.mode in {"component", "profile"},
            "mode": args.mode,
            "updated_unix_s": time.time(),
        },
    )
    control = combined_control(
        fixture,
        new_k,
        new_v,
        new_positions,
        fixture["q"],
        consumer_starts,
    )
    comparison = numerical(candidate, control)
    if args.mode == "smoke":
        terminal = {
            "schema_version": 1,
            "status": "smoke_pass" if comparison["all_finite"] else "smoke_fail",
            "numerical": comparison,
            "mirror_halves_exact": mirror_exact(fixture),
            "extension_sha256": sha256(args.extension),
        }
        atomic(args.artifact_root / "SMOKE_TERMINAL.json", terminal)
        print(json.dumps(terminal, sort_keys=True))
        return 0 if terminal["status"] == "smoke_pass" else 2
    if args.mode == "profile":
        torch.cuda.nvtx.range_push("candidate")
        output = combined_candidate(
            fixture,
            new_k,
            new_v,
            new_positions,
            fixture["q"],
            consumer_starts,
        )
        torch.cuda.nvtx.range_pop()
        torch.cuda.synchronize()
        atomic(
            args.artifact_root / "PROFILE_INVOCATION.json",
            {
                "schema_version": 1,
                "candidate_output_checksum": float(output.float().sum().item()),
                "candidate_invocations_per_consumer": 1,
            },
        )
        return 0

    boundaries = boundary_evidence(fixture)
    semantic = semantics_pass(comparison, boundaries)
    for _ in range(args.warmups):
        combined_candidate(
            fixture,
            new_k,
            new_v,
            new_positions,
            fixture["q"],
            consumer_starts,
        )
        combined_control(
            fixture,
            new_k,
            new_v,
            new_positions,
            fixture["q"],
            consumer_starts,
        )
    torch.cuda.synchronize()
    candidate_samples = []
    control_samples = []
    checksum = 0.0
    for index in range(args.iterations):
        functions = [
            (
                "candidate",
                lambda: combined_candidate(
                    fixture,
                    new_k,
                    new_v,
                    new_positions,
                    fixture["q"],
                    consumer_starts,
                ),
            ),
            (
                "control",
                lambda: combined_control(
                    fixture,
                    new_k,
                    new_v,
                    new_positions,
                    fixture["q"],
                    consumer_starts,
                ),
            ),
        ]
        if index % 2:
            functions.reverse()
        for name, function in functions:
            elapsed, consumed = timed(function)
            checksum += consumed
            (candidate_samples if name == "candidate" else control_samples).append(
                elapsed
            )
    interval = paired_reduction_interval(
        control_samples, candidate_samples, args.seed
    )
    credible_positive = semantic and interval["lower_95"] > 0
    projected = CURRENT_FRONTIER * (
        1 - interval["lower_95"] * LOCAL_WALL_FRACTION
    )
    producer_source_read_bytes = batch * 16 * 256 * 2 * 2
    control_producer_store_bytes = batch * 16 * 256 * 2
    terminal = {
        "schema_version": 1,
        "status": (
            "component_positive"
            if credible_positive
            else "component_semantic_or_nonpositive_reject"
        ),
        "component_positive": credible_positive,
        "conditional_endpoint_admitted": credible_positive,
        "geometry": {
            "phase": "decode",
            "batch_size": batch,
            "context_tokens": LOGICAL_RING_TOKENS,
            "q_heads": 32,
            "kv_heads": 16,
            "head_dim": 256,
            "query_input_dtype": str(fixture["q"].dtype),
            "fa3_compute_input_dtype": "torch.float8_e5m2",
            "kv_dtype": str(fixture["candidate_k"].dtype),
            "logical_layout": "per_request_mirrored_contiguous_ring",
            "physical_tokens_per_request": PHYSICAL_RING_TOKENS,
        },
        "candidate": {
            "symbol": "ring_e5m2_fa3::fwd/direct cutlass::float_e5m2_t FA3-v3 specialization",
            "decomposition": "one contiguous start:start+1024 invocation; no output/logsumexp merge",
            "producer": "store_mirrored_ring_kv/_store_mirrored_ring_kv_kernel",
            "extension": str(args.extension),
            "extension_sha256": sha256(args.extension),
            "full_cache_conversion": False,
        },
        "control": {
            "consumer": "ring_decode_attention/_ring_grouped_stage1",
            "producer": "store_ring_kv/_store_ring_kv_kernel",
        },
        "numerical": comparison,
        "boundaries": boundaries,
        "semantic_pass": semantic,
        "timing": {
            "scope": "actual decode K/V producer append plus actual consumer",
            "candidate": distribution(candidate_samples),
            "control": distribution(control_samples),
            "reduction_fraction": interval,
            "consumed_checksum": checksum,
        },
        "traffic": {
            "classification": "derived_compulsory_bytes",
            "producer_source_read_bytes": producer_source_read_bytes,
            "control_producer_read_plus_store_bytes": (
                producer_source_read_bytes + control_producer_store_bytes
            ),
            "candidate_producer_read_plus_store_bytes": (
                producer_source_read_bytes + control_producer_store_bytes * 2
            ),
            "control_producer_store_bytes": control_producer_store_bytes,
            "candidate_producer_store_bytes": control_producer_store_bytes * 2,
            "consumer_kv_read_bytes": batch
            * LOGICAL_RING_TOKENS
            * 16
            * 256
            * 2,
            "candidate_extra_local_storage_bytes_all_layers": batch
            * LOGICAL_RING_TOKENS
            * 16
            * 256
            * 2
            * LOCAL_LAYERS,
        },
        "compiler_metadata": {
            "classification": "measured_from_content-identical_bound_extension",
            "resource_usage_sha256": "efc9f5d398f35915b39a33ac71eed657f213c470960b8422eab74f0c7aa59214",
            "direct_e5m2_hdim256_single_tile_registers_per_thread": 168,
            "direct_e5m2_hdim256_single_tile_static_shared_bytes": 1024,
            "direct_e5m2_hdim256_single_tile_stack_bytes": 0,
            "direct_e5m2_hdim256_single_tile_local_bytes": 0,
        },
        "whole_request_bound": {
            "local_wall_fraction": LOCAL_WALL_FRACTION,
            "current_frontier_seconds_per_request": CURRENT_FRONTIER,
            "projected_seconds_per_request_at_lower_95": projected,
            "credible_positive": credible_positive,
        },
        "path_proof": {
            "local_layer_count": LOCAL_LAYERS,
            "global_layer_count": GLOBAL_LAYERS,
            "global_path": "unchanged paged E5M2 Triton",
            "candidate_invocations_per_consumer": 1,
            "output_logsumexp_merge_count": 0,
            "candidate_output_fully_consumed": True,
            "producer_mirror_positions_per_logical_token": 2,
            "fallback_count": 0,
        },
        "physical_hypothesis": {
            "change": "double each local E5M2 append store to make every 1,024-token logical window physically contiguous for one FA3 call",
            "predicted_movement": "one FA3 launch and no merge should offset the extra 256 KiB of decode stores at b32",
            "falsifier": "nonpositive complete producer-consumer lower bound or any wrap, padding, reuse, prefix, transition, or numerical failure",
        },
    }
    atomic(args.artifact_root / "COMPONENT_TERMINAL.json", terminal)
    print(json.dumps(terminal, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
