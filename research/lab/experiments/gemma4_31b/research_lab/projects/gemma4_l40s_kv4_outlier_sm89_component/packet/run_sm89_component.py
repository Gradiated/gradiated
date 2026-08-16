#!/usr/bin/env python3
"""One fixed c32 SM89 producer-plus-attention comparison.

The full mode creates the immutable producer snapshot exactly once.  A later
consumer-only repair may reuse that snapshot without replaying either producer.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import traceback


RUNTIME_COMMIT = "c6a6200a1a778a799ba61c395ac292317f01ebc9"
MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
BATCH = 32
QUERY_HEADS = 32
KV_HEADS = 16
HEAD_DIM = 256
WINDOW = 1024
PAGE_SIZE = 1
LOCAL_LAYERS = 50
DECODE_STEPS = 358
MAX_KV_SPLITS = 8
WARMUPS = 5
REPEATS = 31
SEED = 20260727
CANDIDATE_ROW_BYTES = 144
E5M2_ROW_BYTES = 256
EXPECTED = {
    "local_kv4_outlier_cuda.cu": "6d8a84bd5ef5a1fbacbd95a99e1aa7c180b8d39e590ee1fd657d2da51e4e3944",
    "local_kv4_outlier_bindings.cpp": "903ccfd27fb74e21d498aa5c98ce7c179f20e315c4963ab3be1162983aaaebd6",
    "sglang_local_kv4_outlier.py": "16bd6477f1be675bbae83492f057fcb37496026ebf1d7ab9c43e9193d66b8163",
    "runtime_source/decode_attention.py": "7833f6d06115dfd54b384d9ce907a012fa2f568083d90fc0f259e9ef24bf5311",
    "runtime_source/memory_pool.py": "24caf4bf2af6db4f8dc180f65b2ed8153403cdfd87010b70fcac67fe59434a10",
    "runtime_source/triton_backend.py": "e2b0fd4a3ec3c783ae7026f4cb8a7292c1203388a6c9ea5b90e604d3a149f3dc",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def append_jsonl(path: Path, value: object) -> None:
    with path.open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def distribution(values: list[float]) -> dict[str, float]:
    return {
        "minimum": min(values),
        "p05": percentile(values, 0.05),
        "median": statistics.median(values),
        "p95": percentile(values, 0.95),
        "maximum": max(values),
        "mean": statistics.fmean(values),
    }


def verify_packet(root: Path) -> dict[str, str]:
    observed = {}
    for name, expected in EXPECTED.items():
        path = root / name
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"packet_identity_mismatch:{name}:{actual}")
        observed[name] = actual
    return observed


def verify_runtime_sources(root: Path) -> tuple[object, object, object, object]:
    from sglang.kernels.ops.attention import decode_attention as decode_module
    from sglang.kernels.ops.attention.metadata import get_num_kv_splits_triton
    from sglang.srt.layers.attention import triton_backend
    from sglang.srt.mem_cache import memory_pool

    live = {
        "runtime_source/decode_attention.py": Path(inspect.getsourcefile(decode_module)).resolve(),
        "runtime_source/memory_pool.py": Path(inspect.getsourcefile(memory_pool)).resolve(),
        "runtime_source/triton_backend.py": Path(inspect.getsourcefile(triton_backend)).resolve(),
    }
    for name, path in live.items():
        actual = sha256(path)
        if actual != EXPECTED[name] or actual != sha256(root / name):
            raise RuntimeError(f"live_runtime_identity_mismatch:{name}:{actual}")
    return (
        decode_module.decode_attention_fwd,
        get_num_kv_splits_triton,
        memory_pool.MHATokenToKVPool,
        triton_backend.TritonAttnBackend,
    )


def marker(path: Path, arm: str, **fields: object) -> None:
    append_jsonl(
        path,
        {"at_epoch": time.time(), "arm": arm, "completed": True, **fields},
    )


def synchronized_measure(torch, function, consume) -> tuple[float, float, float]:
    torch.cuda.synchronize()
    begin = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    wall_start = time.perf_counter()
    begin.record()
    value = function()
    end.record()
    end.synchronize()
    wall_ms = (time.perf_counter() - wall_start) * 1000.0
    cuda_ms = begin.elapsed_time(end)
    checksum = float(consume(value))
    return wall_ms, cuda_ms, checksum


def rel_l2(torch, candidate, reference) -> float:
    numerator = torch.linalg.vector_norm(candidate.float() - reference.float())
    denominator = torch.linalg.vector_norm(reference.float()).clamp_min(1e-12)
    return float((numerator / denominator).item())


def cosine(torch, candidate, reference) -> float:
    left = candidate.float().flatten()
    right = reference.float().flatten()
    value = torch.nn.functional.cosine_similarity(left, right, dim=0)
    return float(value.item())


def make_reference(torch, q, source_k, source_v, kv_indices):
    output = torch.empty_like(q)
    scale = 1.0 / math.sqrt(HEAD_DIM)
    q_to_kv = torch.arange(QUERY_HEADS, device=q.device) // (
        QUERY_HEADS // KV_HEADS
    )
    rows = kv_indices.view(BATCH, WINDOW)
    for request in range(BATCH):
        keys = source_k[rows[request]][:, q_to_kv, :].float()
        values = source_v[rows[request]][:, q_to_kv, :].float()
        scores = torch.einsum("hd,thd->ht", q[request].float(), keys) * scale
        probability = torch.softmax(scores, dim=-1)
        output[request] = torch.einsum(
            "ht,thd->hd", probability, values
        ).to(output.dtype)
    return output


def resource_usage(extension_path: Path, output: Path) -> dict:
    command = ["cuobjdump", "--dump-resource-usage", str(extension_path)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    raw = result.stdout + result.stderr
    output.write_text(raw)
    functions = []
    current = None
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("Function "):
            current = {"function": stripped}
            functions.append(current)
        elif current is not None and (
            "REG:" in stripped
            or "STACK:" in stripped
            or "SHARED:" in stripped
            or "LOCAL:" in stripped
        ):
            current.setdefault("resource_lines", []).append(stripped)
    return {
        "command": command,
        "returncode": result.returncode,
        "raw_path": output.name,
        "raw_sha256": sha256(output),
        "functions": functions,
    }


def create_pool(torch, pool_class, size: int):
    return pool_class(
        size=size,
        page_size=PAGE_SIZE,
        dtype=torch.float8_e5m2,
        head_num=KV_HEADS,
        head_dim=HEAD_DIM,
        layer_num=1,
        device="cuda",
        enable_memory_saver=False,
        enable_alt_stream=False,
    )


def baseline_attention(
    torch,
    decode_attention_fwd,
    q,
    k_buffer,
    v_buffer,
    kv_indptr,
    kv_indices,
    num_kv_splits,
):
    output = torch.empty_like(q)
    logits = torch.empty(
        (BATCH, QUERY_HEADS, MAX_KV_SPLITS, HEAD_DIM),
        dtype=torch.float32,
        device="cuda",
    )
    lse = torch.empty(
        (BATCH, QUERY_HEADS, MAX_KV_SPLITS),
        dtype=torch.float32,
        device="cuda",
    )
    decode_attention_fwd(
        q,
        k_buffer,
        v_buffer,
        output,
        kv_indptr,
        kv_indices,
        logits,
        lse,
        num_kv_splits,
        MAX_KV_SPLITS,
        1.0 / math.sqrt(HEAD_DIM),
        1.0,
        1.0,
        page_size=PAGE_SIZE,
    )
    return output


def candidate_attention(
    extension,
    q,
    cache_k,
    cache_v,
    qo_indptr,
    kv_indptr,
    kv_indices,
):
    return extension.paged_attention(
        q,
        cache_k,
        cache_v,
        qo_indptr,
        kv_indptr,
        kv_indices,
        WINDOW,
        1,
        1.0 / math.sqrt(HEAD_DIM),
        True,
    )


def isolation_check(adapter, candidate_k, candidate_v) -> dict:
    from types import SimpleNamespace

    method = SimpleNamespace(name=adapter.LocalKV4OutlierKVCacheMethod.name)
    local_pool = SimpleNamespace(
        quant_method=method,
        k_buffer=[candidate_k],
        v_buffer=[candidate_v],
    )
    mixed_pool = SimpleNamespace(
        layers_mapping={0: (0, True), 5: (0, False)},
        swa_kv_pool=local_pool,
    )
    selected = adapter.raw_local_buffers(mixed_pool, 0)
    rejected = False
    try:
        adapter.raw_local_buffers(mixed_pool, 5)
    except ValueError:
        rejected = True
    return {
        "local_selected": selected[0].data_ptr() == candidate_k.data_ptr(),
        "global_rejected": rejected,
        "local_layer": 0,
        "global_layer": 5,
    }


def run_sentinel(
    torch,
    extension,
    decode_attention_fwd,
    pool_class,
    arm_markers: Path,
):
    from types import SimpleNamespace

    generator = torch.Generator(device="cuda").manual_seed(SEED + 1)
    q = torch.randn(
        (1, QUERY_HEADS, HEAD_DIM),
        dtype=torch.bfloat16,
        device="cuda",
        generator=generator,
    )
    k = torch.randn(
        (1, KV_HEADS, HEAD_DIM),
        dtype=torch.bfloat16,
        device="cuda",
        generator=generator,
    )
    v = torch.randn(
        (1, KV_HEADS, HEAD_DIM),
        dtype=torch.bfloat16,
        device="cuda",
        generator=generator,
    )
    loc = torch.zeros(1, dtype=torch.int64, device="cuda")
    baseline_pool = create_pool(torch, pool_class, 1)
    baseline_pool.set_kv_buffer(SimpleNamespace(layer_id=0), loc, k, v)
    torch.cuda.synchronize()
    marker(arm_markers, "sentinel_e5m2_producer")
    candidate_k = torch.full(
        (2, KV_HEADS, CANDIDATE_ROW_BYTES),
        0xA5,
        dtype=torch.uint8,
        device="cuda",
    )
    candidate_v = torch.full_like(candidate_k, 0x5A)
    negative = torch.full((1,), -1, dtype=torch.int64, device="cuda")
    extension.pack(k, negative, candidate_k)
    extension.pack(v, negative, candidate_v)
    torch.cuda.synchronize()
    negative_noop = bool(
        torch.all(candidate_k[0] == 0xA5).item()
        and torch.all(candidate_v[0] == 0x5A).item()
    )
    extension.pack(k, loc, candidate_k)
    extension.pack(v, loc, candidate_v)
    torch.cuda.synchronize()
    marker(
        arm_markers,
        "sentinel_candidate_producer",
        negative_slot_noop=negative_noop,
    )
    indptr = torch.tensor([0, 1], dtype=torch.int32, device="cuda")
    indices = torch.zeros(1, dtype=torch.int64, device="cuda")
    splits = torch.ones(1, dtype=torch.int32, device="cuda")
    baseline = baseline_attention(
        torch,
        decode_attention_fwd,
        q,
        baseline_pool.get_key_buffer(0),
        baseline_pool.get_value_buffer(0),
        indptr,
        indices,
        splits,
    )
    torch.cuda.synchronize()
    marker(
        arm_markers,
        "sentinel_e5m2_consumer",
        finite=bool(torch.isfinite(baseline).all().item()),
    )
    candidate = extension.paged_attention(
        q,
        candidate_k,
        candidate_v,
        indptr,
        indptr,
        indices,
        WINDOW,
        1,
        1.0 / math.sqrt(HEAD_DIM),
        True,
    )
    torch.cuda.synchronize()
    marker(
        arm_markers,
        "sentinel_candidate_consumer",
        finite=bool(torch.isfinite(candidate).all().item()),
    )
    if not negative_noop or not torch.isfinite(candidate).all():
        raise RuntimeError("sentinel_candidate_contract_failed")


def fill_and_measure_producers(
    torch,
    extension,
    pool_class,
    get_num_kv_splits_triton,
    output_root: Path,
):
    from types import SimpleNamespace

    started = time.perf_counter()
    capacity = BATCH * WINDOW
    generator = torch.Generator(device="cuda").manual_seed(SEED)
    source_k = torch.randn(
        (capacity, KV_HEADS, HEAD_DIM),
        dtype=torch.bfloat16,
        device="cuda",
        generator=generator,
    )
    source_v = torch.randn(
        (capacity, KV_HEADS, HEAD_DIM),
        dtype=torch.bfloat16,
        device="cuda",
        generator=generator,
    )
    request_ids = (
        torch.arange(capacity, dtype=torch.int64, device="cuda") % BATCH
    ).to(torch.bfloat16)
    source_k.add_(request_ids[:, None, None] * 0.03125)
    source_v.add_(request_ids[:, None, None] * 2.0)
    q = torch.randn(
        (BATCH, QUERY_HEADS, HEAD_DIM),
        dtype=torch.bfloat16,
        device="cuda",
        generator=generator,
    )
    candidate_k = torch.empty(
        (capacity + PAGE_SIZE, KV_HEADS, CANDIDATE_ROW_BYTES),
        dtype=torch.uint8,
        device="cuda",
    )
    candidate_v = torch.empty_like(candidate_k)
    baseline_pool = create_pool(torch, pool_class, capacity)
    layer = SimpleNamespace(layer_id=0)
    for start in range(0, capacity, 256):
        stop = min(capacity, start + 256)
        locations = torch.arange(start, stop, dtype=torch.int64, device="cuda")
        baseline_pool.set_kv_buffer(
            layer, locations, source_k[start:stop], source_v[start:stop]
        )
        extension.pack(source_k[start:stop], locations, candidate_k)
        extension.pack(source_v[start:stop], locations, candidate_v)
    torch.cuda.synchronize()
    fill_seconds = time.perf_counter() - started

    kv_indices = (
        torch.arange(capacity, dtype=torch.int64, device="cuda")
        .view(WINDOW, BATCH)
        .transpose(0, 1)
        .contiguous()
        .view(-1)
    )
    kv_indptr = torch.arange(
        0, capacity + 1, WINDOW, dtype=torch.int32, device="cuda"
    )
    qo_indptr = torch.arange(BATCH + 1, dtype=torch.int32, device="cuda")
    seq_lens = torch.full((BATCH,), WINDOW, dtype=torch.int32, device="cuda")
    num_kv_splits = torch.empty(BATCH, dtype=torch.int32, device="cuda")
    get_num_kv_splits_triton[(1,)](
        num_kv_splits,
        seq_lens,
        BATCH,
        1,
        QUERY_HEADS,
        KV_HEADS,
        MAX_KV_SPLITS,
        142,
        MAX_NUM_SEQ=256,
    )
    torch.cuda.synchronize()
    if bool((num_kv_splits < 1).any().item()) or bool(
        (num_kv_splits > MAX_KV_SPLITS).any().item()
    ):
        raise RuntimeError("runtime_split_selection_out_of_contract")

    decode_locations = (
        torch.arange(BATCH, dtype=torch.int64, device="cuda")
        + (WINDOW - 1) * BATCH
    )
    decode_k = source_k[decode_locations].contiguous()
    decode_v = source_v[decode_locations].contiguous()

    def e5m2_pack():
        baseline_pool.set_kv_buffer(
            layer, decode_locations, decode_k, decode_v
        )

    def kv4_pack():
        extension.pack(decode_k, decode_locations, candidate_k)
        extension.pack(decode_v, decode_locations, candidate_v)

    for _ in range(WARMUPS):
        e5m2_pack()
        kv4_pack()
    torch.cuda.synchronize()

    values = {
        "e5m2_pack_wall_ms": [],
        "e5m2_pack_cuda_ms": [],
        "kv4_pack_wall_ms": [],
        "kv4_pack_cuda_ms": [],
    }
    checksums = {"e5m2_pack": [], "kv4_pack": []}
    for iteration in range(REPEATS):
        arms = ("e5m2", "kv4") if iteration % 2 == 0 else ("kv4", "e5m2")
        for arm in arms:
            if arm == "e5m2":
                measured = synchronized_measure(
                    torch,
                    e5m2_pack,
                    lambda _: baseline_pool.get_key_buffer(0)
                    .view(torch.uint8)[decode_locations, 0, :8]
                    .sum()
                    .item(),
                )
                values["e5m2_pack_wall_ms"].append(measured[0])
                values["e5m2_pack_cuda_ms"].append(measured[1])
                checksums["e5m2_pack"].append(measured[2])
            else:
                measured = synchronized_measure(
                    torch,
                    kv4_pack,
                    lambda _: candidate_k[decode_locations, 0, :8].sum().item(),
                )
                values["kv4_pack_wall_ms"].append(measured[0])
                values["kv4_pack_cuda_ms"].append(measured[1])
                checksums["kv4_pack"].append(measured[2])

    snapshot = output_root / "PRODUCER_SNAPSHOT.pt"
    torch.save(
        {
            "baseline_k_uint8": baseline_pool.get_key_buffer(0)
            .view(torch.uint8)
            .contiguous(),
            "baseline_v_uint8": baseline_pool.get_value_buffer(0)
            .view(torch.uint8)
            .contiguous(),
            "candidate_k": candidate_k,
            "candidate_v": candidate_v,
            "source_k": source_k,
            "source_v": source_v,
            "q": q,
            "kv_indices": kv_indices,
            "kv_indptr": kv_indptr,
            "qo_indptr": qo_indptr,
            "num_kv_splits": num_kv_splits,
        },
        snapshot,
    )
    producer = {
        "schema_version": 1,
        "kind": "sm89_component_producer_stage",
        "complete": True,
        "snapshot": snapshot.name,
        "snapshot_bytes": snapshot.stat().st_size,
        "snapshot_sha256": sha256(snapshot),
        "fill_setup_seconds": fill_seconds,
        "timing": {name: distribution(rows) for name, rows in values.items()},
        "timing_rows": values,
        "checksums": checksums,
        "selected_num_kv_splits": [int(value) for value in num_kv_splits.cpu()],
        "shape": {
            "batch": BATCH,
            "query_heads": QUERY_HEADS,
            "kv_heads": KV_HEADS,
            "head_dim": HEAD_DIM,
            "window": WINDOW,
            "page_size": PAGE_SIZE,
        },
    }
    atomic_json(output_root / "PRODUCER_STAGE.json", producer)
    return producer, snapshot


def load_snapshot(torch, snapshot: Path, producer_stage: Path):
    producer = json.loads(producer_stage.read_text())
    if (
        producer.get("complete") is not True
        or producer.get("snapshot_sha256") != sha256(snapshot)
        or producer.get("snapshot_bytes") != snapshot.stat().st_size
    ):
        raise RuntimeError("producer_snapshot_identity_mismatch")
    tensors = torch.load(snapshot, map_location="cuda", weights_only=True)
    return producer, tensors


def consume_and_decide(
    torch,
    extension,
    decode_attention_fwd,
    adapter,
    producer: dict,
    tensors: dict,
    output_root: Path,
    arm_markers: Path,
    identities: dict,
    setup: dict,
    resources: dict,
):
    baseline_k = tensors["baseline_k_uint8"].view(torch.float8_e5m2)
    baseline_v = tensors["baseline_v_uint8"].view(torch.float8_e5m2)
    candidate_k = tensors["candidate_k"]
    candidate_v = tensors["candidate_v"]
    q = tensors["q"]
    kv_indptr = tensors["kv_indptr"]
    kv_indices = tensors["kv_indices"]
    qo_indptr = tensors["qo_indptr"]
    num_kv_splits = tensors["num_kv_splits"]

    reference = make_reference(
        torch, q, tensors["source_k"], tensors["source_v"], kv_indices
    )
    baseline = baseline_attention(
        torch,
        decode_attention_fwd,
        q,
        baseline_k,
        baseline_v,
        kv_indptr,
        kv_indices,
        num_kv_splits,
    )
    torch.cuda.synchronize()
    marker(
        arm_markers,
        "production_e5m2_consumer",
        finite=bool(torch.isfinite(baseline).all().item()),
    )
    candidate = candidate_attention(
        extension,
        q,
        candidate_k,
        candidate_v,
        qo_indptr,
        kv_indptr,
        kv_indices,
    )
    torch.cuda.synchronize()
    marker(
        arm_markers,
        "production_candidate_consumer",
        finite=bool(torch.isfinite(candidate).all().item()),
    )

    per_request_candidate = [
        rel_l2(torch, candidate[index], reference[index]) for index in range(BATCH)
    ]
    cross_request_distance = [
        rel_l2(torch, reference[index], reference[(index + 1) % BATCH])
        for index in range(BATCH)
    ]
    numerical = {
        "complete_output_elements_consumed_per_arm": candidate.numel(),
        "reference": "FP32 online attention from the exact BF16 fixture",
        "e5m2": {
            "finite": bool(torch.isfinite(baseline).all().item()),
            "relative_l2": rel_l2(torch, baseline, reference),
            "cosine": cosine(torch, baseline, reference),
            "max_absolute": float(
                (baseline.float() - reference.float()).abs().max().item()
            ),
        },
        "candidate": {
            "finite": bool(torch.isfinite(candidate).all().item()),
            "relative_l2": rel_l2(torch, candidate, reference),
            "cosine": cosine(torch, candidate, reference),
            "max_absolute": float(
                (candidate.float() - reference.float()).abs().max().item()
            ),
            "per_request_relative_l2_max": max(per_request_candidate),
        },
        "request_isolation": {
            "interleaved_physical_slots": True,
            "each_request_slots": WINDOW,
            "minimum_cross_request_reference_relative_l2": min(
                cross_request_distance
            ),
            "maximum_own_request_relative_l2": max(per_request_candidate),
            "pass": all(
                own_error < cross_distance * 0.5
                for own_error, cross_distance in zip(
                    per_request_candidate, cross_request_distance
                )
            ),
        },
        "tolerances": {
            "candidate_relative_l2_max": 0.12,
            "candidate_cosine_min": 0.99,
            "e5m2_relative_l2_max": 0.12,
            "e5m2_cosine_min": 0.99,
            "basis": "the common limit exceeds the inherited 0.101408 focused-boundary relative-L2 by 18.3% while retaining cosine at least 0.99; E5M2 remains the current-runtime comparator rather than an FP32 surrogate",
        },
    }
    isolation = isolation_check(adapter, candidate_k, candidate_v)

    def e5m2_attention():
        return baseline_attention(
            torch,
            decode_attention_fwd,
            q,
            baseline_k,
            baseline_v,
            kv_indptr,
            kv_indices,
            num_kv_splits,
        )

    def kv4_attention():
        return candidate_attention(
            extension,
            q,
            candidate_k,
            candidate_v,
            qo_indptr,
            kv_indptr,
            kv_indices,
        )

    for _ in range(WARMUPS):
        e5m2_attention()
        kv4_attention()
    torch.cuda.synchronize()
    consumer_rows = {
        "e5m2_attention_wall_ms": [],
        "e5m2_attention_cuda_ms": [],
        "kv4_attention_wall_ms": [],
        "kv4_attention_cuda_ms": [],
    }
    checksums = {"e5m2_attention": [], "kv4_attention": []}
    for iteration in range(REPEATS):
        arms = ("e5m2", "kv4") if iteration % 2 == 0 else ("kv4", "e5m2")
        for arm in arms:
            function = e5m2_attention if arm == "e5m2" else kv4_attention
            measured = synchronized_measure(
                torch,
                function,
                lambda value: value.float().sum().item(),
            )
            prefix = "e5m2_attention" if arm == "e5m2" else "kv4_attention"
            consumer_rows[prefix + "_wall_ms"].append(measured[0])
            consumer_rows[prefix + "_cuda_ms"].append(measured[1])
            checksums[prefix].append(measured[2])

    producer_rows = producer["timing_rows"]
    baseline_complete = [
        producer_rows["e5m2_pack_wall_ms"][index]
        + consumer_rows["e5m2_attention_wall_ms"][index]
        for index in range(REPEATS)
    ]
    candidate_complete = [
        producer_rows["kv4_pack_wall_ms"][index]
        + consumer_rows["kv4_attention_wall_ms"][index]
        for index in range(REPEATS)
    ]
    paired_savings = [
        baseline_complete[index] - candidate_complete[index]
        for index in range(REPEATS)
    ]
    conservative_saving_ms = percentile(paired_savings, 0.05)
    locked_multiplier = LOCAL_LAYERS * DECODE_STEPS
    locked_batch_saving_seconds = conservative_saving_ms * locked_multiplier / 1000
    locked_price_normalized_saving_seconds = locked_batch_saving_seconds / BATCH
    timing = {
        "warmups": WARMUPS,
        "repeats": REPEATS,
        "profiler_enabled": False,
        "synchronization": "each wall row includes the dependent end synchronization; no synchronization removal is credited",
        "producer": producer["timing"],
        "consumer": {
            name: distribution(rows) for name, rows in consumer_rows.items()
        },
        "checksums": checksums,
        "complete_producer_plus_consumer_wall_ms": {
            "e5m2": distribution(baseline_complete),
            "candidate": distribution(candidate_complete),
            "paired_e5m2_minus_candidate": distribution(paired_savings),
        },
    }
    locked = {
        "local_layers": LOCAL_LAYERS,
        "decode_steps": DECODE_STEPS,
        "c32_batch_wall_saving_seconds_p05": locked_batch_saving_seconds,
        "price_normalized_seconds_per_request_saving_p05": locked_price_normalized_saving_seconds,
        "formula": "p05(pairwise(e5m2_pack+e5m2_attention-kv4_pack-kv4_attention))*50*358/1000; divide by 32 only for price-normalized GPU-seconds/request",
        "packing_omitted": False,
        "dependent_synchronization_credit_seconds": 0.0,
    }
    correctness_pass = (
        numerical["candidate"]["finite"]
        and numerical["candidate"]["relative_l2"]
        <= numerical["tolerances"]["candidate_relative_l2_max"]
        and numerical["candidate"]["cosine"]
        >= numerical["tolerances"]["candidate_cosine_min"]
        and numerical["e5m2"]["finite"]
        and numerical["e5m2"]["relative_l2"]
        <= numerical["tolerances"]["e5m2_relative_l2_max"]
        and numerical["e5m2"]["cosine"]
        >= numerical["tolerances"]["e5m2_cosine_min"]
        and numerical["request_isolation"]["pass"]
        and isolation["local_selected"]
        and isolation["global_rejected"]
    )
    positive = correctness_pass and conservative_saving_ms > 0.0
    classification = (
        "component_positive"
        if positive
        else "numerical_or_ownership_negative"
        if not correctness_pass
        else "complete_producer_consumer_nonpositive"
    )
    memory = {
        "allocated_bytes": torch.cuda.memory_allocated(),
        "reserved_bytes": torch.cuda.memory_reserved(),
        "max_allocated_bytes": torch.cuda.max_memory_allocated(),
        "max_reserved_bytes": torch.cuda.max_memory_reserved(),
    }
    terminal = {
        "schema_version": 1,
        "kind": "l40s_kv4_outlier_sm89_component_terminal",
        "classification": classification,
        "decision": "positive" if positive else "negative",
        "pass": positive,
        "sample_consumed": True,
        "producer_stage_complete": True,
        "candidate_cuda_executed": True,
        "identities": identities,
        "setup": setup,
        "shape": {
            "phase": "decode",
            "batch": BATCH,
            "query_heads": QUERY_HEADS,
            "kv_heads": KV_HEADS,
            "head_dim": HEAD_DIM,
            "window": WINDOW,
            "page_size": PAGE_SIZE,
            "slot_layout": "token-major interleaved across 32 requests",
        },
        "numerical": numerical,
        "local_to_global_isolation": isolation,
        "timing": timing,
        "locked_request_bound": locked,
        "compiler_resources": resources,
        "cuda_memory": memory,
        "promotion_contract": {
            "requires_correctness": True,
            "requires_p05_complete_saving_positive": True,
            "complete_saving_p05_ms": conservative_saving_ms,
        },
    }
    atomic_json(output_root / "TERMINAL.json", terminal)
    return terminal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("full", "consumer-only"), default="full")
    parser.add_argument("--producer-snapshot", type=Path)
    parser.add_argument("--producer-stage", type=Path)
    args = parser.parse_args()
    if args.artifact_root.exists():
        raise SystemExit("artifact_root_must_not_exist")
    args.artifact_root.mkdir(parents=True)
    packet_root = Path(__file__).resolve().parent
    arm_markers = args.artifact_root / "ARM_MARKERS.jsonl"
    science_started = args.artifact_root / "SCIENCE_STARTED.json"
    producer_complete = args.mode == "consumer-only"
    try:
        packet_hashes = verify_packet(packet_root)
        os.environ["TORCH_CUDA_ARCH_LIST"] = "8.9"
        os.environ.setdefault("MAX_JOBS", "2")
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("typed_hardware_boundary:cuda_unavailable")
        if torch.cuda.device_count() != 1:
            raise RuntimeError("typed_hardware_boundary:exactly_one_gpu_required")
        properties = torch.cuda.get_device_properties(0)
        if torch.cuda.get_device_capability(0) != (8, 9) or "L40S" not in properties.name:
            raise RuntimeError(
                f"typed_hardware_boundary:expected_L40S_SM89:got_{properties.name}"
            )
        (
            decode_attention_fwd,
            get_num_kv_splits_triton,
            pool_class,
            _,
        ) = verify_runtime_sources(packet_root)
        sys.path.insert(0, str(packet_root))
        import sglang_local_kv4_outlier as adapter

        compile_started = time.perf_counter()
        extension = adapter.load_extension()
        torch.cuda.synchronize()
        extension_compile_seconds = time.perf_counter() - compile_started
        resources = resource_usage(
            Path(extension.__file__),
            args.artifact_root / "CANDIDATE_RESOURCE_USAGE.txt",
        )
        identities = {
            "model_revision": MODEL_REVISION,
            "runtime_commit": RUNTIME_COMMIT,
            "packet_hashes": packet_hashes,
            "live_runtime_hashes": {
                name: EXPECTED[name]
                for name in (
                    "runtime_source/decode_attention.py",
                    "runtime_source/memory_pool.py",
                    "runtime_source/triton_backend.py",
                )
            },
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "device": properties.name,
            "compute_capability": list(torch.cuda.get_device_capability(0)),
            "extension_binary_sha256": sha256(Path(extension.__file__)),
        }
        setup = {"extension_compile_load_seconds": extension_compile_seconds}
        torch.cuda.reset_peak_memory_stats()
        if args.mode == "consumer-only":
            if args.producer_snapshot is None or args.producer_stage is None:
                raise RuntimeError("consumer_only_requires_bound_producer_artifacts")
            producer, tensors = load_snapshot(
                torch, args.producer_snapshot, args.producer_stage
            )
            producer_stage_path = args.producer_stage
            setup["reused_producer_snapshot_sha256"] = producer["snapshot_sha256"]
        atomic_json(
            science_started,
            {
                "at_epoch": time.time(),
                "mode": args.mode,
                "operation": "first execution-isolated stock and candidate CUDA submissions",
                "runtime_commit": RUNTIME_COMMIT,
            },
        )

        if args.mode == "full":
            sentinel_started = time.perf_counter()
            run_sentinel(
                torch,
                extension,
                decode_attention_fwd,
                pool_class,
                arm_markers,
            )
            setup["sentinel_seconds"] = time.perf_counter() - sentinel_started
            producer, snapshot = fill_and_measure_producers(
                torch,
                extension,
                pool_class,
                get_num_kv_splits_triton,
                args.artifact_root,
            )
            producer_stage_path = args.artifact_root / "PRODUCER_STAGE.json"
            producer_complete = True
            marker(
                arm_markers,
                "production_producer_stage",
                snapshot_sha256=producer["snapshot_sha256"],
            )
            tensors = torch.load(snapshot, map_location="cuda", weights_only=True)
        else:
            setup["sentinel"] = "skipped_to_preserve_completed_producer_stage"

        terminal = consume_and_decide(
            torch,
            extension,
            decode_attention_fwd,
            adapter,
            producer,
            tensors,
            args.artifact_root,
            arm_markers,
            identities,
            setup,
            resources,
        )
        atomic_json(
            args.artifact_root / "INVOCATION_COMPLETE.json",
            {
                "terminal_sha256": sha256(args.artifact_root / "TERMINAL.json"),
                "producer_stage_sha256": sha256(producer_stage_path),
                "decision": terminal["decision"],
            },
        )
        return 0 if terminal["pass"] else 2
    except Exception as error:
        diagnostic = {
            "schema_version": 1,
            "kind": "recoverable_component_attempt",
            "at_epoch": time.time(),
            "mode": args.mode,
            "error": repr(error),
            "traceback": traceback.format_exc(),
            "science_started": science_started.exists(),
            "producer_stage_complete": producer_complete,
            "candidate_cuda_or_science_path_entered": arm_markers.exists(),
            "retry_scope": (
                "consumer_only_from_bound_producer_snapshot"
                if producer_complete
                else "full_unconsumed_attempt"
            ),
            "sample_consumed": False,
        }
        atomic_json(args.artifact_root / "RECOVERABLE.json", diagnostic)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
