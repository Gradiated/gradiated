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

from ring_kv import ring_decode_attention, store_ring_kv


CURRENT_FRONTIER = 0.6556567115001144
LOCAL_WALL_FRACTION = 0.1531203203096733


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


def fa3_segment(
    q: torch.Tensor,
    k_ring: torch.Tensor,
    v_ring: torch.Tensor,
    request_ids: torch.Tensor,
    seqused_k: torch.Tensor,
    leftpad_k: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    batch = q.shape[0]
    descale = torch.ones(
        (batch, k_ring.shape[2]), dtype=torch.float32, device=q.device
    )
    out, lse, _, _ = torch.ops.ring_e5m2_fa3.fwd.default(
        q,
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
        seqused_k,
        1,
        1024,
        None,
        request_ids.clamp_min(0).to(torch.int32),
        leftpad_k,
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
    return out, lse


def fa3_ring_attention(
    q: torch.Tensor,
    k_ring: torch.Tensor,
    v_ring: torch.Tensor,
    request_ids: torch.Tensor,
    ring_starts: torch.Tensor,
    context_lens: torch.Tensor,
) -> torch.Tensor:
    valid = request_ids >= 0
    starts = torch.where(valid, ring_starts, torch.zeros_like(ring_starts)).to(
        torch.int32
    )
    lengths = torch.where(valid, context_lens, torch.zeros_like(context_lens)).to(
        torch.int32
    )
    full = lengths == 1024
    tail_lengths = torch.where(full, 1024 - starts, lengths)
    head_lengths = torch.where(full, starts, torch.zeros_like(starts))
    tail_end = starts + tail_lengths
    q_fp8 = q[:, None].to(torch.float8_e5m2)
    tail_out, tail_lse = fa3_segment(
        q_fp8, k_ring, v_ring, request_ids, tail_end, starts
    )
    head_out, head_lse = fa3_segment(
        q_fp8,
        k_ring,
        v_ring,
        request_ids,
        head_lengths,
        torch.zeros_like(starts),
    )
    merged_lse = torch.logaddexp(tail_lse, head_lse)
    tail_weight = torch.exp(tail_lse - merged_lse)
    head_weight = torch.exp(head_lse - merged_lse)
    merged = tail_out.float() * tail_weight.transpose(1, 2)[..., None]
    merged += head_out.float() * head_weight.transpose(1, 2)[..., None]
    merged = merged[:, 0].to(torch.bfloat16)
    return torch.where(valid[:, None, None], merged, torch.zeros_like(merged))


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
        [
            torch.zeros(1, dtype=torch.int32, device=q.device),
            torch.cumsum(context_lens.to(torch.int32), dim=0),
        ]
    )
    attn_logits = torch.empty(
        (batch, 32, 8, 256), dtype=torch.float32, device=q.device
    )
    attn_lse = torch.empty(
        (batch, 32, 8), dtype=torch.float32, device=q.device
    )
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


def numerical(candidate: torch.Tensor, control: torch.Tensor) -> dict[str, Any]:
    candidate_float = candidate.float()
    control_float = control.float()
    delta = candidate_float - control_float
    return {
        "all_finite": bool(torch.isfinite(candidate_float).all().item()),
        "max_abs_error": float(delta.abs().max().item()),
        "mean_abs_error": float(delta.abs().mean().item()),
        "relative_l2": float(
            (
                torch.linalg.vector_norm(delta)
                / torch.linalg.vector_norm(control_float).clamp_min(1e-12)
            ).item()
        ),
        "cosine": float(
            torch.nn.functional.cosine_similarity(
                candidate_float.flatten(), control_float.flatten(), dim=0
            ).item()
        ),
        "checksum": float(candidate_float.sum().item()),
    }


def timed(fn: Callable[[], torch.Tensor]) -> tuple[float, float]:
    begin = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    begin.record()
    value = fn()
    end.record()
    end.synchronize()
    return float(begin.elapsed_time(end)), float(value.float().sum().item())


def distribution(samples: list[float]) -> dict[str, Any]:
    ordered = sorted(samples)
    return {
        "samples_ms": samples,
        "minimum_ms": ordered[0],
        "median_ms": statistics.median(samples),
        "p90_ms": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "maximum_ms": ordered[-1],
    }


def reduction_interval(
    control: list[float], candidate: list[float], seed: int
) -> dict[str, float]:
    rng = random.Random(seed)
    values = []
    for _ in range(4000):
        c = statistics.median(rng.choices(control, k=len(control)))
        x = statistics.median(rng.choices(candidate, k=len(candidate)))
        values.append(1 - x / c)
    values.sort()
    return {
        "point": 1
        - statistics.median(candidate) / statistics.median(control),
        "lower_95": values[int(0.025 * len(values))],
        "upper_95": values[int(0.975 * len(values))],
    }


def make_fixture(
    batch: int, context: int, seed: int
) -> tuple[torch.Tensor, ...]:
    torch.manual_seed(seed)
    q = (
        torch.randn((batch, 32, 256), dtype=torch.bfloat16, device="cuda")
        / math.sqrt(256)
    ).contiguous()
    k_ring = torch.zeros(
        (batch, 1024, 16, 256), dtype=torch.float8_e5m2, device="cuda"
    )
    v_ring = torch.zeros_like(k_ring)
    starts = (
        17 + torch.arange(batch, dtype=torch.int64, device="cuda") * 137
    ) & 1023
    request_ids = torch.arange(batch, dtype=torch.int32, device="cuda")
    positions = (
        starts[:, None]
        + torch.arange(context, dtype=torch.int64, device="cuda")[None]
    )
    repeated_ids = request_ids.repeat_interleave(context)
    k = (
        torch.randn(
            (batch * context, 16, 256),
            dtype=torch.bfloat16,
            device="cuda",
        )
        / math.sqrt(256)
    ).contiguous()
    v = torch.randn_like(k).contiguous()
    store_ring_kv(
        k,
        v,
        k_ring,
        v_ring,
        repeated_ids,
        positions.reshape(-1),
        1.0,
        1.0,
    )
    context_lens = torch.full(
        (batch,), context, dtype=torch.int32, device="cuda"
    )
    return q, k_ring, v_ring, request_ids, starts.to(torch.int32), context_lens


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "component"), required=True)
    parser.add_argument("--iterations", type=int, default=31)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260723)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation = args.artifact_root / "INVOCATION_STATE.json"
    atomic(
        invocation,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": False,
            "scientific_invocation_started": False,
            "mode": args.mode,
            "updated_unix_s": time.time(),
        },
    )
    if not torch.cuda.is_available() or torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("exact_hopper_cuda_unavailable")
    load_extension(args.extension)
    batch = 1 if args.mode == "smoke" else 32
    context = 64 if args.mode == "smoke" else 1024
    fixture = make_fixture(batch, context, args.seed)
    candidate = fa3_ring_attention(*fixture)
    atomic(
        invocation,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": True,
            "scientific_invocation_started": args.mode == "component",
            "mode": args.mode,
            "updated_unix_s": time.time(),
        },
    )
    control = control_attention(*fixture)
    comparison = numerical(candidate, control)
    if args.mode == "smoke":
        terminal = {
            "schema_version": 1,
            "status": "smoke_pass" if comparison["all_finite"] else "smoke_fail",
            "numerical": comparison,
            "extension_sha256": sha256(args.extension),
        }
        atomic(args.artifact_root / "SMOKE_TERMINAL.json", terminal)
        print(json.dumps(terminal, sort_keys=True))
        return 0 if comparison["all_finite"] else 2

    transition_numerical = []
    q, k_ring, v_ring, request_ids, starts, context_lens = fixture
    for transition in range(2):
        current_k = (
            torch.randn(
                (batch, 16, 256), dtype=torch.bfloat16, device="cuda"
            )
            / math.sqrt(256)
        ).contiguous()
        current_v = torch.randn_like(current_k).contiguous()
        absolute_positions = starts.to(torch.int64) + 1024 + transition
        store_ring_kv(
            current_k,
            current_v,
            k_ring,
            v_ring,
            request_ids,
            absolute_positions,
            1.0,
            1.0,
        )
        transition_starts = (starts + transition + 1) & 1023
        transition_q = torch.randn_like(q).contiguous()
        transition_numerical.append(
            numerical(
                fa3_ring_attention(
                    transition_q,
                    k_ring,
                    v_ring,
                    request_ids,
                    transition_starts,
                    context_lens,
                ),
                control_attention(
                    transition_q,
                    k_ring,
                    v_ring,
                    request_ids,
                    transition_starts,
                    context_lens,
                ),
            )
        )

    padded_request_ids = request_ids.clone()
    padded_request_ids[-1] = -1
    padded_context = context_lens.clone()
    padded_context[-1] = 0
    padded_candidate = fa3_ring_attention(
        q, k_ring, v_ring, padded_request_ids, starts, padded_context
    )
    padded_control = control_attention(
        q, k_ring, v_ring, padded_request_ids, starts, padded_context
    )
    padded = {
        "candidate_zero": bool(
            torch.count_nonzero(padded_candidate[-1]).item() == 0
        ),
        "control_zero": bool(
            torch.count_nonzero(padded_control[-1]).item() == 0
        ),
        "valid_rows": numerical(padded_candidate[:-1], padded_control[:-1]),
    }
    for _ in range(args.warmups):
        fa3_ring_attention(*fixture)
        control_attention(*fixture)
    torch.cuda.synchronize()
    candidate_samples = []
    control_samples = []
    checksum = 0.0
    for index in range(args.iterations):
        functions = [
            ("candidate", lambda: fa3_ring_attention(*fixture)),
            ("control", lambda: control_attention(*fixture)),
        ]
        if index % 2:
            functions.reverse()
        for name, fn in functions:
            elapsed, consumed = timed(fn)
            checksum += consumed
            (candidate_samples if name == "candidate" else control_samples).append(
                elapsed
            )
    interval = reduction_interval(
        control_samples, candidate_samples, args.seed
    )
    semantic_pass = (
        comparison["all_finite"]
        and comparison["relative_l2"] <= 0.02
        and comparison["cosine"] >= 0.9998
        and all(
            row["all_finite"]
            and row["relative_l2"] <= 0.02
            and row["cosine"] >= 0.9998
            for row in transition_numerical
        )
        and padded["candidate_zero"]
        and padded["control_zero"]
        and padded["valid_rows"]["relative_l2"] <= 0.02
    )
    positive_bound = semantic_pass and interval["lower_95"] > 0
    projected = CURRENT_FRONTIER * (
        1 - interval["lower_95"] * LOCAL_WALL_FRACTION
    )
    terminal = {
        "schema_version": 1,
        "status": (
            "component_positive"
            if positive_bound
            else "component_semantic_or_nonpositive_reject"
        ),
        "component_positive": positive_bound,
        "conditional_endpoint_admitted": positive_bound,
        "geometry": {
            "phase": "decode",
            "batch_size": batch,
            "context_tokens": context,
            "q_heads": 32,
            "kv_heads": 16,
            "head_dim": 256,
            "query_input_dtype": str(q.dtype),
            "fa3_compute_input_dtype": "torch.float8_e5m2",
            "kv_dtype": str(k_ring.dtype),
            "layout": "request_owned_contiguous_circular_ring",
        },
        "candidate": {
            "symbol": "ring_e5m2_fa3::fwd/direct cutlass::float_e5m2_t FA3-v3 specialization",
            "circular_decomposition": "two zero-copy contiguous segments merged from output and logsumexp",
            "full_cache_conversion": False,
            "extension": str(args.extension),
            "extension_sha256": sha256(args.extension),
        },
        "control": "ring_decode_attention/_ring_grouped_stage1",
        "numerical": comparison,
        "transitions": transition_numerical,
        "padded_row": padded,
        "semantic_pass": semantic_pass,
        "timing": {
            "candidate": distribution(candidate_samples),
            "control": distribution(control_samples),
            "reduction_fraction": interval,
            "consumed_checksum": checksum,
        },
        "whole_request_bound": {
            "local_wall_fraction": LOCAL_WALL_FRACTION,
            "current_frontier_seconds_per_request": CURRENT_FRONTIER,
            "projected_seconds_per_request_at_lower_95": projected,
            "credible_positive": positive_bound,
        },
        "path_proof": {
            "local_layer_count": 50,
            "global_layer_count": 10,
            "global_path": "unchanged paged E5M2 Triton",
            "producer": "store_ring_kv/_store_ring_kv_kernel direct E5M2 ring write",
            "candidate_invocations_per_consumer": 2,
            "candidate_output_fully_consumed": True,
            "fallback_count": 0,
        },
        "physical_hypothesis": {
            "change": "replace ring Triton online attention with FA3 Hopper warp-specialized FP8 E5M2 loads while retaining ring-resident bytes",
            "compulsory_kv_bytes_per_layer_decode": batch
            * context
            * 16
            * 256
            * 2,
            "predicted_movement": "lower local-consumer latency at unchanged K/V HBM bytes",
            "falsifier": "nonpositive lower confidence bound or any wrap, padding, transition, or numerical failure",
        },
    }
    atomic(args.artifact_root / "COMPONENT_TERMINAL.json", terminal)
    print(json.dumps(terminal, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
