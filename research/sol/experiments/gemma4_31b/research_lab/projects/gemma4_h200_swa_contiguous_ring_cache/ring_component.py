#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import torch

from ring_kv import ring_decode_attention, store_ring_kv


SOURCE_HASHES = {
    "decode_attention.py": "1040f43a9ea579b944aa037b585997f8d7b585d85f459a1b1f420002b4bd092a",
    "memory_pool.py": "37f9915a2945c7bb389212eed65eb770cb9e3fa6976d0778b6831d2ac29d7bdd",
    "swa_memory_pool.py": "36830cdb84cc344ffb7bac9ff30ba9a41b488d67893a5015ecbba584e95a9858",
    "triton_backend.py": "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d",
}
LOCAL_WALL_FRACTION = 0.1531203203096733
CURRENT_FRONTIER = 0.6743258590313417
ECONOMIC_CEILING = 0.6381105231
LOCAL_LAYER_IDS = [index for index in range(60) if (index + 1) % 6]
GLOBAL_LAYER_IDS = list(range(5, 60, 6))


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def timed_ms(fn: Callable[[], Any]) -> float:
    begin = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    begin.record()
    fn()
    end.record()
    end.synchronize()
    return float(begin.elapsed_time(end))


def distribution(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "samples_ms": values,
        "minimum_ms": ordered[0],
        "median_ms": statistics.median(values),
        "p90_ms": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "maximum_ms": ordered[-1],
    }


def bootstrap_reduction(
    control: list[float], candidate: list[float], seed: int
) -> dict[str, float]:
    if len(control) != len(candidate):
        raise ValueError("paired distributions have different lengths")
    rng = random.Random(seed)
    reductions = []
    for _ in range(2000):
        indices = [rng.randrange(len(control)) for _ in control]
        control_median = statistics.median(control[index] for index in indices)
        candidate_median = statistics.median(candidate[index] for index in indices)
        reductions.append(1.0 - candidate_median / control_median)
    reductions.sort()
    return {
        "point": 1.0
        - statistics.median(candidate) / statistics.median(control),
        "lower_95": reductions[math.floor(0.025 * len(reductions))],
        "upper_95": reductions[math.ceil(0.975 * len(reductions)) - 1],
    }


def source_identity() -> dict[str, Any]:
    import sglang.srt.layers.attention.triton_backend as triton_backend
    import sglang.srt.layers.attention.triton_ops.decode_attention as decode_attention
    import sglang.srt.mem_cache.memory_pool as memory_pool
    import sglang.srt.mem_cache.swa_memory_pool as swa_memory_pool

    observed = {}
    for module in (decode_attention, memory_pool, swa_memory_pool, triton_backend):
        path = Path(module.__file__).resolve()
        observed[path.name] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    mismatches = {
        name: row["sha256"]
        for name, row in observed.items()
        if SOURCE_HASHES.get(name) != row["sha256"]
    }
    if mismatches:
        raise RuntimeError(f"pinned_source_mismatch:{mismatches}")
    return observed


def make_pool(context: int, batch_size: int):
    from sglang.srt.mem_cache.swa_memory_pool import SWAKVPool

    slots = context * batch_size + 1
    pool = SWAKVPool(
        size=slots,
        size_swa=slots,
        page_size=1,
        dtype=torch.float8_e5m2,
        head_num=4,
        head_dim=512,
        v_head_dim=512,
        swa_head_num=16,
        swa_head_dim=256,
        swa_v_head_dim=256,
        swa_attention_layer_ids=LOCAL_LAYER_IDS,
        full_attention_layer_ids=GLOBAL_LAYER_IDS,
        enable_kvcache_transpose=False,
        enable_alt_stream=False,
        device="cuda",
    )
    pool.register_mapping(torch.arange(slots + 1, dtype=torch.int64, device="cuda"))
    return pool


def make_layer(layer_id: int, local: bool):
    from sglang.srt.layers.radix_attention import RadixAttention

    return RadixAttention(
        num_heads=32,
        head_dim=256 if local else 512,
        scaling=1 / math.sqrt(256 if local else 512),
        num_kv_heads=16 if local else 4,
        layer_id=layer_id,
        v_head_dim=256 if local else 512,
        sliding_window_size=1023 if local else -1,
    ).cuda()


def compiler_metadata(compiled: Any) -> dict[str, Any]:
    if compiled is None:
        return {"available": False}
    metadata = getattr(compiled, "metadata", None)
    result = {
        "available": True,
        "name": getattr(compiled, "name", None),
        "n_regs": getattr(compiled, "n_regs", None),
        "n_spills": getattr(compiled, "n_spills", None),
    }
    if metadata is not None:
        for field in ("num_warps", "num_stages", "shared", "cluster_dims"):
            value = getattr(metadata, field, None)
            if value is not None:
                result[field] = value
    return result


def dequantized_reference(
    q: torch.Tensor,
    k_ring: torch.Tensor,
    v_ring: torch.Tensor,
    ring_starts: torch.Tensor,
) -> torch.Tensor:
    outputs = []
    for request in range(q.shape[0]):
        start = int(ring_starts[request])
        chronological_k = torch.cat(
            (k_ring[request, start:], k_ring[request, :start]), dim=0
        ).float()
        chronological_v = torch.cat(
            (v_ring[request, start:], v_ring[request, :start]), dim=0
        ).float()
        expanded_k = chronological_k.repeat_interleave(2, dim=1)
        expanded_v = chronological_v.repeat_interleave(2, dim=1)
        scores = torch.einsum("hd,thd->ht", q[request].float(), expanded_k)
        scores *= 1 / math.sqrt(256)
        probabilities = torch.softmax(scores, dim=-1)
        outputs.append(torch.einsum("ht,thd->hd", probabilities, expanded_v))
    return torch.stack(outputs).to(torch.bfloat16)


def error_metrics(output: torch.Tensor, reference: torch.Tensor) -> dict[str, Any]:
    delta = output.float() - reference.float()
    return {
        "all_finite": bool(torch.isfinite(output).all().item()),
        "relative_l2": float(
            torch.linalg.vector_norm(delta)
            / torch.linalg.vector_norm(reference.float()).clamp_min(1e-12)
        ),
        "cosine": float(
            torch.nn.functional.cosine_similarity(
                output.float().flatten(), reference.float().flatten(), dim=0
            )
        ),
        "max_abs_error": float(delta.abs().max()),
        "mean_abs_error": float(delta.abs().mean()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--context", type=int, default=1024)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=31)
    parser.add_argument("--seed", type=int, default=20260723)
    args = parser.parse_args()
    if args.batch_size != 32 or args.context != 1024:
        raise ValueError("canonical component is bound to c32 and a 1,024-token window")

    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation_path = args.artifact_root / "INVOCATION_STATE.json"
    atomic(
        invocation_path,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": False,
            "candidate_scientific_invocation_started": False,
            "scientific_terminal_recorded": False,
            "updated_unix_s": time.time(),
        },
    )
    if not torch.cuda.is_available() or torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("exact_hopper_cuda_unavailable")

    sources = source_identity()
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    batch_size = args.batch_size
    context = args.context
    pool = make_pool(context, batch_size)
    local_layer = make_layer(0, local=True)
    global_layer = make_layer(5, local=False)
    if pool.swa_kv_pool.dtype != torch.float8_e5m2:
        raise RuntimeError(f"local_pool_dtype_mismatch:{pool.swa_kv_pool.dtype}")
    if pool.full_kv_pool.dtype != torch.float8_e5m2:
        raise RuntimeError(f"global_pool_dtype_mismatch:{pool.full_kv_pool.dtype}")

    req_to_slots = (
        torch.arange(
            1,
            batch_size * context + 1,
            dtype=torch.int64,
            device="cuda",
        )
        .view(batch_size, context)
        .contiguous()
    )
    request_ids = (
        torch.arange(batch_size, dtype=torch.int32, device="cuda")
        .repeat_interleave(context)
        .contiguous()
    )
    request_starts = (
        torch.arange(batch_size, dtype=torch.int64, device="cuda") * 137 + 897
    )
    absolute_positions = (
        request_starts[:, None]
        + torch.arange(context, dtype=torch.int64, device="cuda")[None, :]
    ).flatten()
    ring_starts = (request_starts & (context - 1)).to(torch.int32)
    current_positions = (request_starts + context - 1).contiguous()
    current_slots = req_to_slots[:, -1]

    q = (
        torch.randn(
            (batch_size, 32, 256), dtype=torch.bfloat16, device="cuda"
        )
        / math.sqrt(256)
    ).contiguous()
    k_prefix = (
        torch.randn(
            (batch_size * context, 16, 256),
            dtype=torch.bfloat16,
            device="cuda",
        )
        / math.sqrt(256)
    ).contiguous()
    v_prefix = torch.randn_like(k_prefix).contiguous()
    k_ring = torch.zeros(
        (batch_size, context, 16, 256),
        dtype=torch.float8_e5m2,
        device="cuda",
    )
    v_ring = torch.zeros_like(k_ring)

    pool.set_kv_buffer(
        local_layer,
        req_to_slots.flatten(),
        k_prefix,
        v_prefix,
        local_layer.k_scale,
        local_layer.v_scale,
        swa_loc=req_to_slots.flatten(),
    )
    global_k = torch.randn(
        (batch_size, 4, 512), dtype=torch.bfloat16, device="cuda"
    ).contiguous()
    global_v = torch.randn_like(global_k)
    pool.set_kv_buffer(
        global_layer,
        current_slots,
        global_k,
        global_v,
        global_layer.k_scale,
        global_layer.v_scale,
    )
    global_before = (
        pool.get_key_buffer(5)[current_slots].view(torch.uint8).clone(),
        pool.get_value_buffer(5)[current_slots].view(torch.uint8).clone(),
    )

    invocation = json.loads(invocation_path.read_text())
    invocation["candidate_cuda_invocation_started"] = True
    invocation["candidate_scientific_invocation_started"] = True
    invocation["updated_unix_s"] = time.time()
    atomic(invocation_path, invocation)
    producer_compiled = store_ring_kv(
        k_prefix,
        v_prefix,
        k_ring,
        v_ring,
        request_ids,
        absolute_positions,
    )
    torch.cuda.synchronize()

    local_control_k = pool.get_key_buffer(0)
    local_control_v = pool.get_value_buffer(0)
    exact_prefix_match = True
    for request in range(batch_size):
        start = int(ring_starts[request])
        candidate_k = torch.cat(
            (k_ring[request, start:], k_ring[request, :start]), dim=0
        ).view(torch.uint8)
        candidate_v = torch.cat(
            (v_ring[request, start:], v_ring[request, :start]), dim=0
        ).view(torch.uint8)
        exact_prefix_match &= bool(
            torch.equal(
                candidate_k,
                local_control_k[req_to_slots[request]].view(torch.uint8),
            )
            and torch.equal(
                candidate_v,
                local_control_v[req_to_slots[request]].view(torch.uint8),
            )
        )
    if not exact_prefix_match:
        raise RuntimeError("ring_prefix_materialization_byte_mismatch")

    ownership_k = torch.zeros(
        (2, context, 16, 256), dtype=torch.float8_e5m2, device="cuda"
    )
    ownership_v = torch.zeros_like(ownership_k)
    shared_k = k_prefix[:context].repeat(2, 1, 1)
    shared_v = v_prefix[:context].repeat(2, 1, 1)
    shared_ids = torch.arange(2, dtype=torch.int32, device="cuda").repeat_interleave(
        context
    )
    shared_positions = torch.arange(
        context, dtype=torch.int64, device="cuda"
    ).repeat(2)
    store_ring_kv(
        shared_k,
        shared_v,
        ownership_k,
        ownership_v,
        shared_ids,
        shared_positions,
    )
    request_one_before = ownership_k[1].view(torch.uint8).clone()
    replacement_k = torch.full(
        (1, 16, 256), 3.25, dtype=torch.bfloat16, device="cuda"
    )
    replacement_v = torch.full_like(replacement_k, -2.5)
    store_ring_kv(
        replacement_k,
        replacement_v,
        ownership_k,
        ownership_v,
        torch.tensor([0], dtype=torch.int32, device="cuda"),
        torch.tensor([context], dtype=torch.int64, device="cuda"),
    )
    ownership_isolated = bool(
        torch.equal(request_one_before, ownership_k[1].view(torch.uint8))
        and not torch.equal(
            ownership_k[0, 0].view(torch.uint8),
            ownership_k[1, 0].view(torch.uint8),
        )
    )

    padding_probe = k_ring[0, 17].view(torch.uint8).clone()
    invalid_k = torch.full(
        (3, 16, 256), 57344.0, dtype=torch.bfloat16, device="cuda"
    )
    invalid_v = torch.full_like(invalid_k, -57344.0)
    store_ring_kv(
        invalid_k,
        invalid_v,
        k_ring,
        v_ring,
        torch.full((3,), -1, dtype=torch.int32, device="cuda"),
        torch.tensor([-1, 0, 2**31], dtype=torch.int64, device="cuda"),
    )
    negative_slot_noop = bool(
        torch.equal(padding_probe, k_ring[0, 17].view(torch.uint8))
    )

    from sglang.srt.layers.attention.triton_ops.decode_attention import (
        decode_attention_fwd,
    )

    kv_indptr = torch.arange(
        0,
        (batch_size + 1) * context,
        context,
        dtype=torch.int32,
        device="cuda",
    )
    kv_indices = req_to_slots.flatten()
    seq_lens = torch.full(
        (batch_size,), context, dtype=torch.int32, device="cuda"
    )
    num_splits = torch.full(
        (batch_size,), 8, dtype=torch.int32, device="cuda"
    )
    control_output = torch.empty_like(q)
    candidate_output = torch.empty_like(q)
    control_logits = torch.empty(
        (batch_size, 32, 8, 256), dtype=torch.float32, device="cuda"
    )
    control_lse = torch.empty(
        (batch_size, 32, 8), dtype=torch.float32, device="cuda"
    )
    candidate_logits = torch.empty_like(control_logits)
    candidate_lse = torch.empty_like(control_lse)

    def control_consumer() -> None:
        decode_attention_fwd(
            q,
            local_control_k,
            local_control_v,
            control_output,
            kv_indptr,
            kv_indices,
            control_logits,
            control_lse,
            num_splits,
            8,
            1 / math.sqrt(256),
            1.0,
            1.0,
        )

    candidate_compiled = None

    def candidate_consumer() -> None:
        nonlocal candidate_compiled
        compiled = ring_decode_attention(
            q,
            k_ring,
            v_ring,
            candidate_output,
            seq_lens,
            ring_starts,
            kv_indptr,
            candidate_logits,
            candidate_lse,
            num_splits,
            8,
            1 / math.sqrt(256),
            1.0,
            1.0,
        )
        if candidate_compiled is None:
            candidate_compiled = compiled

    control_consumer()
    candidate_consumer()
    torch.cuda.synchronize()
    reference = dequantized_reference(q, k_ring, v_ring, ring_starts)
    control_numerical = error_metrics(control_output, reference)
    candidate_numerical = error_metrics(candidate_output, reference)
    direct_delta = error_metrics(candidate_output, control_output)

    padded_batch = 64
    padded_k_ring = torch.zeros(
        (padded_batch, context, 16, 256),
        dtype=torch.float8_e5m2,
        device="cuda",
    )
    padded_v_ring = torch.zeros_like(padded_k_ring)
    padded_k_ring[:batch_size].copy_(k_ring)
    padded_v_ring[:batch_size].copy_(v_ring)
    padded_q = torch.zeros(
        (padded_batch, 32, 256), dtype=torch.bfloat16, device="cuda"
    )
    padded_q[:batch_size].copy_(q)
    padded_seq_lens = torch.cat(
        (
            seq_lens,
            torch.ones(
                padded_batch - batch_size, dtype=torch.int32, device="cuda"
            ),
        )
    )
    padded_ring_starts = torch.cat(
        (
            ring_starts,
            torch.zeros(
                padded_batch - batch_size, dtype=torch.int32, device="cuda"
            ),
        )
    )
    padded_indptr = torch.cat(
        (
            torch.arange(
                0,
                (batch_size + 1) * context,
                context,
                dtype=torch.int32,
                device="cuda",
            ),
            batch_size * context
            + torch.arange(
                1,
                padded_batch - batch_size + 1,
                dtype=torch.int32,
                device="cuda",
            ),
        )
    )
    padded_splits = torch.cat(
        (
            num_splits,
            torch.ones(
                padded_batch - batch_size, dtype=torch.int32, device="cuda"
            ),
        )
    )
    padded_output = torch.empty_like(padded_q)
    padded_logits = torch.empty(
        (padded_batch, 32, 8, 256), dtype=torch.float32, device="cuda"
    )
    padded_lse = torch.empty(
        (padded_batch, 32, 8), dtype=torch.float32, device="cuda"
    )
    ring_decode_attention(
        padded_q,
        padded_k_ring,
        padded_v_ring,
        padded_output,
        padded_seq_lens,
        padded_ring_starts,
        padded_indptr,
        padded_logits,
        padded_lse,
        padded_splits,
        8,
        1 / math.sqrt(256),
        1.0,
        1.0,
    )
    torch.cuda.synchronize()
    padded_graph_pass = bool(
        torch.isfinite(padded_output).all().item()
        and torch.count_nonzero(padded_output[batch_size:]).item() == 0
        and torch.allclose(
            padded_output[:batch_size],
            candidate_output,
            atol=2e-3,
            rtol=2e-3,
        )
    )

    k_current = k_prefix.view(batch_size, context, 16, 256)[:, -1].contiguous()
    v_current = v_prefix.view(batch_size, context, 16, 256)[:, -1].contiguous()

    def control_producer() -> None:
        pool.set_kv_buffer(
            local_layer,
            current_slots,
            k_current,
            v_current,
            local_layer.k_scale,
            local_layer.v_scale,
            swa_loc=current_slots,
        )

    current_request_ids = torch.arange(
        batch_size, dtype=torch.int32, device="cuda"
    )

    def candidate_producer() -> None:
        store_ring_kv(
            k_current,
            v_current,
            k_ring,
            v_ring,
            current_request_ids,
            current_positions,
        )

    def control_boundary() -> None:
        control_producer()
        control_consumer()

    def candidate_boundary() -> None:
        candidate_producer()
        candidate_consumer()

    def control_prefill_producer() -> None:
        pool.set_kv_buffer(
            local_layer,
            req_to_slots.flatten(),
            k_prefix,
            v_prefix,
            local_layer.k_scale,
            local_layer.v_scale,
            swa_loc=req_to_slots.flatten(),
        )

    def candidate_prefill_producer() -> None:
        store_ring_kv(
            k_prefix,
            v_prefix,
            k_ring,
            v_ring,
            request_ids,
            absolute_positions,
        )

    for _ in range(args.warmups):
        control_boundary()
        candidate_boundary()
        control_prefill_producer()
        candidate_prefill_producer()

    samples = {
        "consumer": {"control": [], "candidate": []},
        "decode_boundary": {"control": [], "candidate": []},
        "prefill_producer": {"control": [], "candidate": []},
    }
    functions = {
        "consumer": (control_consumer, candidate_consumer),
        "decode_boundary": (control_boundary, candidate_boundary),
        "prefill_producer": (control_prefill_producer, candidate_prefill_producer),
    }
    for iteration in range(args.iterations):
        order = (0, 1) if iteration % 2 == 0 else (1, 0)
        for boundary_name, pair in functions.items():
            for side in order:
                name = "control" if side == 0 else "candidate"
                samples[boundary_name][name].append(timed_ms(pair[side]))

    timing = {}
    conservative_bounds = []
    for index, (name, row) in enumerate(samples.items()):
        reduction = bootstrap_reduction(
            row["control"], row["candidate"], args.seed + index
        )
        timing[name] = {
            "control": distribution(row["control"]),
            "candidate": distribution(row["candidate"]),
            "reduction_fraction": reduction,
        }
        conservative_bounds.append(reduction["lower_95"])
    conservative_reduction = min(conservative_bounds)
    projected_seconds = CURRENT_FRONTIER * (
        1.0 - LOCAL_WALL_FRACTION * conservative_reduction
    )
    required_reduction = (
        CURRENT_FRONTIER - ECONOMIC_CEILING
    ) / (CURRENT_FRONTIER * LOCAL_WALL_FRACTION)
    numerical_pass = (
        control_numerical["all_finite"]
        and candidate_numerical["all_finite"]
        and candidate_numerical["relative_l2"] <= 0.01
        and candidate_numerical["cosine"] >= 0.999
        and direct_delta["relative_l2"] <= 0.01
        and exact_prefix_match
        and ownership_isolated
        and negative_slot_noop
        and padded_graph_pass
    )
    component_positive = numerical_pass and conservative_reduction > 0
    ceiling_bound_pass = component_positive and projected_seconds < ECONOMIC_CEILING
    status = (
        "component_positive_endpoint_admitted"
        if component_positive
        else "component_insufficient_bound"
        if numerical_pass
        else "component_numerical_or_semantic_reject"
    )

    global_after = (
        pool.get_key_buffer(5)[current_slots].view(torch.uint8),
        pool.get_value_buffer(5)[current_slots].view(torch.uint8),
    )
    global_unchanged = bool(
        torch.equal(global_before[0], global_after[0])
        and torch.equal(global_before[1], global_after[1])
    )
    if not global_unchanged:
        raise RuntimeError("candidate_mutated_global_paged_e5m2_state")

    kv_bytes = batch_size * context * 16 * 256 * 2
    index_bytes = batch_size * context * 8
    terminal = {
        "schema_version": 1,
        "status": status,
        "component_positive": component_positive,
        "conditional_endpoint_admitted": component_positive,
        "ceiling_bound_pass": ceiling_bound_pass,
        "geometry": {
            "phase": ["prefill_materialization", "decode"],
            "batch_size": batch_size,
            "context_tokens": context,
            "page_size_control": 1,
            "ring_tokens_candidate": context,
            "q_heads": 32,
            "kv_heads": 16,
            "head_dim": 256,
            "kv_dtype": "torch.float8_e5m2",
            "query_dtype": "torch.bfloat16",
            "num_kv_splits": 8,
        },
        "physical_model": {
            "control_kv_read_bytes_per_decode": kv_bytes,
            "control_index_read_bytes_per_decode": index_bytes,
            "index_bytes_fraction_of_kv_bytes": index_bytes / kv_bytes,
            "candidate_change": "remove kv_indices load and derive request-owned ring position with a power-of-two wrap",
            "predicted_counter_movement": "fewer global index loads and no scattered request-page lookup; unchanged E5M2 K/V bytes and attention math",
            "falsifier": "non-positive conservative producer-consumer reduction or any prefix/wrap/padding/numerical failure",
        },
        "numerical": {
            "control_vs_dequantized_fp32_reference": control_numerical,
            "candidate_vs_dequantized_fp32_reference": candidate_numerical,
            "candidate_vs_control": direct_delta,
            "pass": numerical_pass,
        },
        "semantic_proof": {
            "prefix_materialization_exact_e5m2_bytes": exact_prefix_match,
            "prefix_ownership": "copy into distinct request-owned ring rows before local consumption",
            "prefix_alias_isolation_pass": ownership_isolated,
            "wrap_start_slots": ring_starts.tolist(),
            "wrap_crossing_requests": int(torch.count_nonzero(ring_starts).item()),
            "negative_slot_noop": negative_slot_noop,
            "padded_cuda_graph_batch": padded_batch,
            "padded_cuda_graph_pass": padded_graph_pass,
            "global_paged_e5m2_unchanged": global_unchanged,
        },
        "path_proof": {
            "producer_control": "SWAKVPool.set_kv_buffer -> MHATokenToKVPool.set_kv_buffer",
            "producer_candidate": "store_ring_kv/_store_ring_kv_kernel",
            "consumer_control": "decode_attention_fwd/_fwd_grouped_kernel_stage1",
            "consumer_candidate": "ring_decode_attention/_ring_grouped_stage1",
            "local_layer_ids": LOCAL_LAYER_IDS,
            "global_layer_ids": GLOBAL_LAYER_IDS,
            "local_layer_count": len(LOCAL_LAYER_IDS),
            "global_layer_count": len(GLOBAL_LAYER_IDS),
            "global_layout": "unchanged SWAKVPool.full_kv_pool paged radix",
            "fallback_count": 0,
            "source": sources,
        },
        "timing": timing,
        "conservative_reduction_fraction": conservative_reduction,
        "current_frontier_seconds_per_request": CURRENT_FRONTIER,
        "economic_ceiling_seconds_per_request": ECONOMIC_CEILING,
        "required_local_reduction_fraction_for_ceiling": required_reduction,
        "projected_seconds_per_request": projected_seconds,
        "estimated_whole_request_reduction_fraction": (
            LOCAL_WALL_FRACTION * conservative_reduction
        ),
        "compiler": {
            "producer": compiler_metadata(producer_compiled),
            "consumer_stage1": compiler_metadata(candidate_compiled),
        },
        "device": {
            "name": torch.cuda.get_device_name(),
            "capability": list(torch.cuda.get_device_capability()),
            "sm_count": torch.cuda.get_device_properties(0).multi_processor_count,
        },
        "identity": {
            "torch": torch.__version__,
            "seed": args.seed,
        },
    }
    atomic(args.artifact_root / "COMPONENT_TERMINAL.json", terminal)
    invocation = json.loads(invocation_path.read_text())
    invocation["scientific_terminal_recorded"] = True
    invocation["updated_unix_s"] = time.time()
    atomic(invocation_path, invocation)
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
