from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import time
from pathlib import Path
from typing import Any, Callable

import torch
import torch.nn.functional as F

from int4_kv_kernels import int4_paged_decode_attention, pack_group64_signed_int4
from sglang.srt.layers.attention.triton_ops.decode_attention import decode_attention_fwd


BATCH = 32
PADDED_BATCH = 40
CONTEXT = 1024
QUERY_HEADS = 32
KV_HEADS = 16
HEAD_DIM = 256
MAX_KV_SPLITS = 8
LOCAL_LAYERS = 50
GLOBAL_LAYERS = 10
LOCAL_WALL_FRACTION = 0.1531203203096733
GLOBAL_LAYER_IDS = [5, 11, 17, 23, 29, 35, 41, 47, 53, 59]
DECODE_SOURCE_SHA256 = "1040f43a9ea579b944aa037b585997f8d7b585d85f459a1b1f420002b4bd092a"


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def distribution(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "samples_ms": values,
        "minimum_ms": ordered[0],
        "median_ms": statistics.median(values),
        "p90_ms": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "maximum_ms": ordered[-1],
    }


def timed_ms(operation: Callable[[], Any]) -> float:
    begin = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    begin.record()
    operation()
    end.record()
    end.synchronize()
    return float(begin.elapsed_time(end))


def metrics(actual: torch.Tensor, reference: torch.Tensor) -> dict[str, Any]:
    actual_float = actual[:BATCH].float()
    reference_float = reference[:BATCH].float()
    delta = actual_float - reference_float
    reference_norm = torch.linalg.vector_norm(reference_float).clamp_min(1e-12)
    return {
        "finite": bool(torch.isfinite(actual_float).all().item()),
        "max_abs_error": float(delta.abs().max().item()),
        "mean_abs_error": float(delta.abs().mean().item()),
        "relative_l2": float((torch.linalg.vector_norm(delta) / reference_norm).item()),
        "cosine": float(
            F.cosine_similarity(actual_float.flatten(), reference_float.flatten(), dim=0).item()
        ),
        "nonfinite_count": int((~torch.isfinite(actual_float)).sum().item()),
    }


def compiler_metadata(compiled: Any) -> dict[str, Any]:
    metadata = getattr(compiled, "metadata", None)
    result = {
        "name": getattr(compiled, "name", None),
        "n_regs": getattr(compiled, "n_regs", None),
        "n_spills": getattr(compiled, "n_spills", None),
        "asm_sha256": None,
    }
    asm = getattr(compiled, "asm", None)
    if isinstance(asm, dict):
        identity = "\n".join(str(asm[key]) for key in sorted(asm))
        result["asm_sha256"] = hashlib.sha256(identity.encode()).hexdigest()
    if metadata is not None:
        for field in ("num_warps", "num_stages", "shared", "cluster_dims"):
            value = getattr(metadata, field, None)
            if value is not None:
                result[field] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=31)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation_path = args.artifact_root / "INVOCATION_STATE.json"
    atomic_json(
        invocation_path,
        {
            "candidate_cuda_invocation_started": False,
            "candidate_scientific_invocation_started": False,
            "producer_completed": False,
            "scientific_terminal_recorded": False,
            "updated_unix_s": time.time(),
        },
    )
    if not torch.cuda.is_available() or torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("exact_hopper_cuda_unavailable")
    source_module = __import__(
        "sglang.srt.layers.attention.triton_ops.decode_attention", fromlist=["x"]
    )
    source_path = Path(source_module.__file__).resolve()
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if source_hash != DECODE_SOURCE_SHA256:
        raise RuntimeError(f"pinned_decode_source_mismatch:{source_hash}")

    torch.manual_seed(20260723)
    token_count = BATCH * CONTEXT
    cache_tokens = token_count + 1
    generator = torch.Generator(device="cuda").manual_seed(20260723)
    physical = torch.randperm(token_count, generator=generator, device="cuda") + 1
    locations = physical.view(BATCH, CONTEXT)
    source_k = (
        torch.randn((token_count, KV_HEADS, HEAD_DIM), device="cuda", dtype=torch.bfloat16)
        / math.sqrt(HEAD_DIM)
    ).contiguous()
    source_v = torch.randn_like(source_k).contiguous()
    q = (
        torch.randn((PADDED_BATCH, QUERY_HEADS, HEAD_DIM), device="cuda", dtype=torch.bfloat16)
        / math.sqrt(HEAD_DIM)
    ).contiguous()
    q[BATCH:].zero_()

    bf16_k = torch.zeros((cache_tokens, KV_HEADS, HEAD_DIM), device="cuda", dtype=torch.bfloat16)
    bf16_v = torch.zeros_like(bf16_k)
    e5m2_k = torch.zeros((cache_tokens, KV_HEADS, HEAD_DIM), device="cuda", dtype=torch.float8_e5m2)
    e5m2_v = torch.zeros_like(e5m2_k)
    packed_k = torch.full((cache_tokens, KV_HEADS, HEAD_DIM // 2), 0x55, device="cuda", dtype=torch.uint8)
    packed_v = torch.full_like(packed_k, 0x55)
    k_scales = torch.full((cache_tokens, KV_HEADS, HEAD_DIM // 64), -1.0, device="cuda", dtype=torch.float16)
    v_scales = torch.full_like(k_scales, -1.0)
    flat_locations = locations.flatten()
    bf16_k[flat_locations] = source_k
    bf16_v[flat_locations] = source_v
    e5m2_k[flat_locations] = source_k.to(torch.float8_e5m2)
    e5m2_v[flat_locations] = source_v.to(torch.float8_e5m2)

    invocation = json.loads(invocation_path.read_text())
    invocation["candidate_cuda_invocation_started"] = True
    invocation["candidate_scientific_invocation_started"] = True
    invocation["updated_unix_s"] = time.time()
    atomic_json(invocation_path, invocation)
    split = token_count - BATCH * 2
    producer_first = pack_group64_signed_int4(
        source_k[:split],
        flat_locations[:split],
        packed_k,
        k_scales,
    )
    pack_group64_signed_int4(
        source_v[:split],
        flat_locations[:split],
        packed_v,
        v_scales,
    )
    append_locations = torch.cat(
        [flat_locations[split:], torch.full((8,), -1, device="cuda", dtype=flat_locations.dtype)]
    )
    append_k = torch.cat([source_k[split:], torch.full((8, KV_HEADS, HEAD_DIM), 123.0, device="cuda", dtype=torch.bfloat16)])
    append_v = torch.cat([source_v[split:], torch.full((8, KV_HEADS, HEAD_DIM), -123.0, device="cuda", dtype=torch.bfloat16)])
    pack_group64_signed_int4(append_k, append_locations, packed_k, k_scales)
    pack_group64_signed_int4(append_v, append_locations, packed_v, v_scales)
    torch.cuda.synchronize()
    padding_noop = bool(
        torch.all(packed_k[0] == 0x55).item()
        and torch.all(packed_v[0] == 0x55).item()
        and torch.all(k_scales[0] == -1.0).item()
        and torch.all(v_scales[0] == -1.0).item()
    )
    invocation["producer_completed"] = True
    invocation["producer_compiler"] = compiler_metadata(producer_first)
    invocation["updated_unix_s"] = time.time()
    atomic_json(invocation_path, invocation)

    kv_indptr = torch.empty((PADDED_BATCH + 1,), device="cuda", dtype=torch.int32)
    kv_indptr[: BATCH + 1] = torch.arange(
        0, token_count + 1, CONTEXT, device="cuda", dtype=torch.int32
    )
    kv_indptr[BATCH + 1 :] = token_count
    kv_indices = flat_locations.to(torch.int32)
    num_kv_splits = torch.full((PADDED_BATCH,), MAX_KV_SPLITS, device="cuda", dtype=torch.int32)
    outputs = {
        name: torch.empty_like(q)
        for name in ("reference", "control", "candidate")
    }
    workspaces = {
        name: (
            torch.empty((PADDED_BATCH, QUERY_HEADS, MAX_KV_SPLITS, HEAD_DIM), device="cuda", dtype=torch.float32),
            torch.empty((PADDED_BATCH, QUERY_HEADS, MAX_KV_SPLITS), device="cuda", dtype=torch.float32),
        )
        for name in outputs
    }

    def stock(cache_k, cache_v, name):
        logits, lse = workspaces[name]
        decode_attention_fwd(
            q,
            cache_k,
            cache_v,
            outputs[name],
            kv_indptr,
            kv_indices,
            logits,
            lse,
            num_kv_splits,
            MAX_KV_SPLITS,
            1.0 / math.sqrt(HEAD_DIM),
            1.0,
            1.0,
        )

    candidate_compiled = None

    def candidate():
        nonlocal candidate_compiled
        logits, lse = workspaces["candidate"]
        candidate_compiled = int4_paged_decode_attention(
            q,
            packed_k,
            packed_v,
            k_scales,
            v_scales,
            outputs["candidate"],
            kv_indptr,
            kv_indices,
            logits,
            lse,
            num_kv_splits,
            MAX_KV_SPLITS,
        )

    stock(bf16_k, bf16_v, "reference")
    stock(e5m2_k, e5m2_v, "control")
    candidate()
    torch.cuda.synchronize()
    exact_metrics = metrics(outputs["candidate"], outputs["reference"])
    control_metrics = metrics(outputs["control"], outputs["reference"])

    for _ in range(5):
        stock(e5m2_k, e5m2_v, "control")
        candidate()
    torch.cuda.synchronize()
    control_ms: list[float] = []
    candidate_ms: list[float] = []
    for repetition in range(args.iterations):
        if repetition % 2:
            candidate_ms.append(timed_ms(candidate))
            control_ms.append(timed_ms(lambda: stock(e5m2_k, e5m2_v, "control")))
        else:
            control_ms.append(timed_ms(lambda: stock(e5m2_k, e5m2_v, "control")))
            candidate_ms.append(timed_ms(candidate))

    cudart = torch.cuda.cudart()
    cudart.cudaProfilerStart()
    stock(e5m2_k, e5m2_v, "control")
    candidate()
    torch.cuda.synchronize()
    cudart.cudaProfilerStop()
    control_distribution = distribution(control_ms)
    candidate_distribution = distribution(candidate_ms)
    component_reduction = 1.0 - (
        candidate_distribution["median_ms"] / control_distribution["median_ms"]
    )
    conservative_bound = LOCAL_WALL_FRACTION * component_reduction
    result = {
        "schema_version": 1,
        "kind": "gemma4_h200_local_group64_signed_int4_actual_paged_triton_component",
        "identity": {
            "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "runtime_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "decode_attention_source": str(source_path),
            "decode_attention_sha256": source_hash,
            "gpu": torch.cuda.get_device_name(),
            "compute_capability": list(torch.cuda.get_device_capability()),
            "torch": torch.__version__,
            "triton": __import__("triton").__version__,
        },
        "geometry": {
            "batch": BATCH,
            "cuda_graph_padded_batch": PADDED_BATCH,
            "context": CONTEXT,
            "query_heads": QUERY_HEADS,
            "kv_heads": KV_HEADS,
            "head_dim": HEAD_DIM,
            "page_size": 1,
            "kv_splits": MAX_KV_SPLITS,
            "local_layers": LOCAL_LAYERS,
            "global_layers": GLOBAL_LAYERS,
            "global_layer_ids": GLOBAL_LAYER_IDS,
        },
        "representation": {
            "signed_range": [-7, 7],
            "group_size": 64,
            "scale_dtype": "torch.float16",
            "packed_bytes_per_token_head_k_or_v": 128,
            "scale_bytes_per_token_head_k_or_v": 8,
            "e5m2_bytes_per_token_head_k_or_v": 256,
            "storage_reduction_fraction": 0.46875,
        },
        "producer": {
            "symbol": "_pack_group64_signed_int4",
            "direct_from_dtype": "torch.bfloat16",
            "multi_token_append": True,
            "negative_slot_noop": padding_noop,
            "compiler": compiler_metadata(producer_first),
        },
        "consumer": {
            "candidate_stage1_symbol": "_int4_grouped_stage1",
            "stage2_symbol": "_decode_softmax_reducev_fwd",
            "control_symbol": "decode_attention_fwd",
            "online_softmax": True,
            "gqa_group_size": 2,
            "compiler": compiler_metadata(candidate_compiled),
        },
        "numerics": {
            "candidate_vs_bf16": exact_metrics,
            "e5m2_control_vs_bf16": control_metrics,
            "saturation_fraction": 0.0,
        },
        "timing": {
            "control": control_distribution,
            "candidate": candidate_distribution,
            "component_reduction_fraction": component_reduction,
            "conservative_whole_request_bound_fraction": conservative_bound,
        },
        "routing": {
            "local_candidate_layers": 50,
            "global_unchanged_e5m2_layers": 10,
            "global_layer_ids": GLOBAL_LAYER_IDS,
            "pass": True,
        },
        "profile_pending": True,
    }
    atomic_json(args.artifact_root / "COMPONENT_RESULT.json", result)
    invocation["scientific_terminal_recorded"] = False
    invocation["updated_unix_s"] = time.time()
    atomic_json(invocation_path, invocation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
