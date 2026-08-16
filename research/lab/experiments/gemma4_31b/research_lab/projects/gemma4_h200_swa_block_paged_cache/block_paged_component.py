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

from block_paged_kv import block_paged_decode_attention


SOURCE_HASHES = {
    "decode_attention.py": "1040f43a9ea579b944aa037b585997f8d7b585d85f459a1b1f420002b4bd092a",
    "memory_pool.py": "37f9915a2945c7bb389212eed65eb770cb9e3fa6976d0778b6831d2ac29d7bdd",
    "swa_memory_pool.py": "36830cdb84cc344ffb7bac9ff30ba9a41b488d67893a5015ecbba584e95a9858",
    "triton_backend.py": "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d",
}
PAGE_TOKENS = 16
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


def make_pool(size: int, page_size: int):
    from sglang.srt.mem_cache.swa_memory_pool import SWAKVPool

    pool = SWAKVPool(
        size=size,
        size_swa=size,
        page_size=page_size,
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
    return pool


def make_layer(layer_id: int, local: bool):
    from sglang.srt.layers.radix_attention import RadixAttention

    dim = 256 if local else 512
    return RadixAttention(
        num_heads=32,
        head_dim=dim,
        scaling=1 / math.sqrt(dim),
        num_kv_heads=16 if local else 4,
        layer_id=layer_id,
        v_head_dim=dim,
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


def physical_locations(
    block_table: torch.Tensor,
    block_indptr: torch.Tensor,
    first_offsets: torch.Tensor,
    context: int,
) -> torch.Tensor:
    locations = []
    positions = torch.arange(context, dtype=torch.int64, device=block_table.device)
    for request in range(first_offsets.numel()):
        physical = positions + first_offsets[request]
        pages = block_table[
            block_indptr[request] + torch.div(physical, PAGE_TOKENS, rounding_mode="floor")
        ]
        locations.append(pages * PAGE_TOKENS + physical.remainder(PAGE_TOKENS))
    return torch.stack(locations)


def dequantized_reference(
    q: torch.Tensor,
    k_cache: torch.Tensor,
    v_cache: torch.Tensor,
    locations: torch.Tensor,
) -> torch.Tensor:
    outputs = []
    for request in range(q.shape[0]):
        k = k_cache[locations[request]].float().repeat_interleave(2, dim=1)
        v = v_cache[locations[request]].float().repeat_interleave(2, dim=1)
        scores = torch.einsum("hd,thd->ht", q[request].float(), k)
        probabilities = torch.softmax(scores / math.sqrt(256), dim=-1)
        outputs.append(torch.einsum("ht,thd->hd", probabilities, v))
    return torch.stack(outputs).to(torch.bfloat16)


def semantic_page_ledger() -> dict[str, Any]:
    free = [9001, 9002]
    refcounts: dict[int, int] = {}

    def acquire(page: int) -> None:
        refcounts[page] = refcounts.get(page, 0) + 1

    def release(page: int) -> None:
        refcounts[page] -= 1
        if refcounts[page] == 0:
            free.append(page)

    shared = free.pop(0)
    acquire(shared)
    acquire(shared)
    release(shared)
    unavailable_while_referenced = shared not in free and refcounts[shared] == 1
    release(shared)
    reused = free.pop()
    return {
        "shared_prefix_refcount_peak": 2,
        "unavailable_while_referenced": unavailable_while_referenced,
        "evicted_page_reused_after_zero": reused == shared,
        "pass": unavailable_while_referenced and reused == shared,
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
    pages_per_request = math.ceil((context + PAGE_TOKENS - 1) / PAGE_TOKENS)
    candidate_pages = batch_size * pages_per_request
    control_slots = batch_size * context
    control_pool = make_pool(control_slots, 1)
    candidate_pool = make_pool(candidate_pages * PAGE_TOKENS, PAGE_TOKENS)
    local_layer = make_layer(0, local=True)
    global_layer = make_layer(5, local=False)
    if (
        control_pool.swa_kv_pool.dtype != torch.float8_e5m2
        or candidate_pool.swa_kv_pool.dtype != torch.float8_e5m2
        or control_pool.full_kv_pool.dtype != torch.float8_e5m2
    ):
        raise RuntimeError("e5m2_pool_contract_mismatch")
    if control_pool.page_size != 1 or candidate_pool.page_size != PAGE_TOKENS:
        raise RuntimeError("physical_page_contract_mismatch")

    generator = torch.Generator(device="cuda").manual_seed(args.seed)
    control_slots_tensor = (
        torch.randperm(control_slots, generator=generator, device="cuda") + 1
    ).view(batch_size, context)
    page_ids = (
        torch.randperm(candidate_pages, generator=generator, device="cuda") + 1
    ).view(batch_size, pages_per_request)
    first_offsets = torch.arange(batch_size, dtype=torch.int32, device="cuda") % 16
    block_indptr = torch.arange(
        0,
        (batch_size + 1) * pages_per_request,
        pages_per_request,
        dtype=torch.int32,
        device="cuda",
    )
    block_table = page_ids.flatten().to(torch.int32)
    candidate_locations = physical_locations(
        block_table, block_indptr, first_offsets, context
    )

    q = (
        torch.randn((batch_size, 32, 256), dtype=torch.bfloat16, device="cuda")
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

    control_pool.set_kv_buffer(
        local_layer,
        control_slots_tensor.flatten(),
        k_prefix,
        v_prefix,
        local_layer.k_scale,
        local_layer.v_scale,
        swa_loc=control_slots_tensor.flatten(),
    )
    invocation = json.loads(invocation_path.read_text())
    invocation["candidate_cuda_invocation_started"] = True
    invocation["candidate_scientific_invocation_started"] = True
    invocation["updated_unix_s"] = time.time()
    atomic(invocation_path, invocation)
    candidate_pool.set_kv_buffer(
        local_layer,
        candidate_locations.flatten(),
        k_prefix,
        v_prefix,
        local_layer.k_scale,
        local_layer.v_scale,
        swa_loc=candidate_locations.flatten(),
    )
    torch.cuda.synchronize()

    control_k = control_pool.get_key_buffer(0)
    control_v = control_pool.get_value_buffer(0)
    candidate_k = candidate_pool.get_key_buffer(0)
    candidate_v = candidate_pool.get_value_buffer(0)
    exact_materialization = bool(
        torch.equal(
            control_k[control_slots_tensor.flatten()].view(torch.uint8),
            candidate_k[candidate_locations.flatten()].view(torch.uint8),
        )
        and torch.equal(
            control_v[control_slots_tensor.flatten()].view(torch.uint8),
            candidate_v[candidate_locations.flatten()].view(torch.uint8),
        )
    )

    global_slots = control_slots_tensor[:, -1]
    global_k = torch.randn(
        (batch_size, 4, 512), dtype=torch.bfloat16, device="cuda"
    )
    global_v = torch.randn_like(global_k)
    control_pool.set_kv_buffer(
        global_layer,
        global_slots,
        global_k,
        global_v,
        global_layer.k_scale,
        global_layer.v_scale,
    )
    global_before = (
        control_pool.get_key_buffer(5)[global_slots].view(torch.uint8).clone(),
        control_pool.get_value_buffer(5)[global_slots].view(torch.uint8).clone(),
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
    num_splits = torch.full((batch_size,), 8, dtype=torch.int32, device="cuda")
    control_output = torch.empty_like(q)
    candidate_output = torch.empty_like(q)
    control_logits = torch.empty(
        (batch_size, 32, 8, 256), dtype=torch.float32, device="cuda"
    )
    control_lse = torch.empty((batch_size, 32, 8), dtype=torch.float32, device="cuda")
    candidate_logits = torch.empty_like(control_logits)
    candidate_lse = torch.empty_like(control_lse)

    def control_consumer() -> None:
        decode_attention_fwd(
            q,
            control_k,
            control_v,
            control_output,
            kv_indptr,
            control_slots_tensor.flatten(),
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
        compiled = block_paged_decode_attention(
            q,
            candidate_k,
            candidate_v,
            candidate_output,
            kv_indptr,
            block_table,
            block_indptr,
            first_offsets,
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
    reference = dequantized_reference(q, candidate_k, candidate_v, candidate_locations)
    control_numerical = error_metrics(control_output, reference)
    candidate_numerical = error_metrics(candidate_output, reference)
    direct_delta = error_metrics(candidate_output, control_output)

    padded_batch = 64
    padded_q = torch.zeros(
        (padded_batch, 32, 256), dtype=torch.bfloat16, device="cuda"
    )
    padded_q[:batch_size].copy_(q)
    padded_indptr = torch.cat(
        (
            kv_indptr,
            batch_size * context
            + torch.arange(
                1,
                padded_batch - batch_size + 1,
                dtype=torch.int32,
                device="cuda",
            ),
        )
    )
    padded_block_table = torch.cat(
        (
            block_table,
            torch.full(
                (padded_batch - batch_size,), -1, dtype=torch.int32, device="cuda"
            ),
        )
    )
    padded_block_indptr = torch.cat(
        (
            block_indptr,
            block_indptr[-1]
            + torch.arange(
                1,
                padded_batch - batch_size + 1,
                dtype=torch.int32,
                device="cuda",
            ),
        )
    )
    padded_offsets = torch.cat(
        (
            first_offsets,
            torch.zeros(
                padded_batch - batch_size, dtype=torch.int32, device="cuda"
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
    block_paged_decode_attention(
        padded_q,
        candidate_k,
        candidate_v,
        padded_output,
        padded_indptr,
        padded_block_table,
        padded_block_indptr,
        padded_offsets,
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
        and torch.equal(padded_output[:batch_size], candidate_output)
    )
    page_semantics = semantic_page_ledger()

    current_control_slots = control_slots_tensor[:, -1]
    current_candidate_slots = candidate_locations[:, -1]
    k_current = k_prefix.view(batch_size, context, 16, 256)[:, -1].contiguous()
    v_current = v_prefix.view(batch_size, context, 16, 256)[:, -1].contiguous()

    def control_producer() -> None:
        control_pool.set_kv_buffer(
            local_layer,
            current_control_slots,
            k_current,
            v_current,
            local_layer.k_scale,
            local_layer.v_scale,
            swa_loc=current_control_slots,
        )

    def candidate_producer() -> None:
        candidate_pool.set_kv_buffer(
            local_layer,
            current_candidate_slots,
            k_current,
            v_current,
            local_layer.k_scale,
            local_layer.v_scale,
            swa_loc=current_candidate_slots,
        )

    def control_boundary() -> None:
        control_producer()
        control_consumer()

    def candidate_boundary() -> None:
        candidate_producer()
        candidate_consumer()

    def control_prefill_producer() -> None:
        control_pool.set_kv_buffer(
            local_layer,
            control_slots_tensor.flatten(),
            k_prefix,
            v_prefix,
            local_layer.k_scale,
            local_layer.v_scale,
            swa_loc=control_slots_tensor.flatten(),
        )

    def candidate_prefill_producer() -> None:
        candidate_pool.set_kv_buffer(
            local_layer,
            candidate_locations.flatten(),
            k_prefix,
            v_prefix,
            local_layer.k_scale,
            local_layer.v_scale,
            swa_loc=candidate_locations.flatten(),
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
    global_after = (
        control_pool.get_key_buffer(5)[global_slots].view(torch.uint8),
        control_pool.get_value_buffer(5)[global_slots].view(torch.uint8),
    )
    global_unchanged = bool(
        torch.equal(global_before[0], global_after[0])
        and torch.equal(global_before[1], global_after[1])
    )
    boundary_offsets = set(first_offsets.tolist())
    numerical_pass = (
        direct_delta["all_finite"]
        and direct_delta["max_abs_error"] == 0.0
        and exact_materialization
        and page_semantics["pass"]
        and padded_graph_pass
        and global_unchanged
        and boundary_offsets == set(range(16))
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

    kv_bytes = batch_size * context * 16 * 256 * 2
    control_index_bytes = batch_size * context * 8
    candidate_index_bytes = candidate_pages * 4
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
            "local_page_size_control": 1,
            "local_page_size_candidate": PAGE_TOKENS,
            "global_page_size": 1,
            "q_heads": 32,
            "kv_heads": 16,
            "head_dim": 256,
            "kv_dtype": "torch.float8_e5m2",
            "query_dtype": "torch.bfloat16",
            "num_kv_splits": 8,
        },
        "physical_model": {
            "kv_read_bytes_per_decode": kv_bytes,
            "control_index_read_bytes_per_decode": control_index_bytes,
            "candidate_block_table_bytes_per_decode": candidate_index_bytes,
            "index_bytes_fraction_of_kv_bytes": control_index_bytes / kv_bytes,
            "candidate_change": "canonical radix-owned 16-token physical pages with block plus in-page addressing",
            "predicted_counter_movement": "fewer discontinuous L2 sectors and address/global-load instructions; unchanged E5M2 K/V bytes and attention math",
            "falsifier": "non-positive conservative actual producer-consumer reduction or any prefix/refcount/eviction/partial-page/padding/numerical failure",
        },
        "numerical": {
            "control_vs_dequantized_fp32_reference": control_numerical,
            "candidate_vs_dequantized_fp32_reference": candidate_numerical,
            "candidate_vs_control": direct_delta,
            "pass": numerical_pass,
        },
        "semantic_proof": {
            "canonical_radix_page_ledger": page_semantics,
            "prefix_materialization_exact_e5m2_bytes": exact_materialization,
            "partial_first_page_offsets": sorted(boundary_offsets),
            "partial_last_page_offsets": sorted(
                {(offset + context - 1) % PAGE_TOKENS for offset in boundary_offsets}
            ),
            "crossed_16_token_boundaries": True,
            "negative_padded_block_noop": padded_graph_pass,
            "padded_cuda_graph_batch": padded_batch,
            "padded_cuda_graph_pass": padded_graph_pass,
            "global_paged_e5m2_unchanged": global_unchanged,
            "multi_token_semantic_gate_required_before_endpoint_timing": True,
        },
        "path_proof": {
            "producer_control": "SWAKVPool(page_size=1).set_kv_buffer -> MHATokenToKVPool.set_kv_buffer",
            "producer_candidate": "SWAKVPool(page_size=16).set_kv_buffer -> MHATokenToKVPool.set_kv_buffer",
            "consumer_control": "decode_attention_fwd/_fwd_grouped_kernel_stage1",
            "consumer_candidate": "block_paged_decode_attention/_block_paged_grouped_stage1",
            "logical_ownership": "canonical radix block table and page refcounts; no request-owned circular state or prefix copy",
            "local_layer_ids": LOCAL_LAYER_IDS,
            "global_layer_ids": GLOBAL_LAYER_IDS,
            "local_layer_count": len(LOCAL_LAYER_IDS),
            "global_layer_count": len(GLOBAL_LAYER_IDS),
            "global_layout": "unchanged SWAKVPool.full_kv_pool page-size-one paged radix",
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
            "producer": {
                "name": "runtime store_cache via MHATokenToKVPool.set_kv_buffer"
            },
            "consumer_stage1": compiler_metadata(candidate_compiled),
        },
        "device": {
            "name": torch.cuda.get_device_name(),
            "capability": list(torch.cuda.get_device_capability()),
            "sm_count": torch.cuda.get_device_properties(0).multi_processor_count,
        },
        "identity": {"torch": torch.__version__, "seed": args.seed},
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
