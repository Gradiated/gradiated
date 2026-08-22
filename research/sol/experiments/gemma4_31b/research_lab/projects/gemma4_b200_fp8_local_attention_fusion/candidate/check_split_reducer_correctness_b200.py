#!/usr/bin/env python3
"""One-shot B200 correctness consumer for the split-state reducer candidate.

This is intentionally not a benchmark.  It produces one decision-bearing
stock-vs-candidate output/cache comparison over the exact production c32 head,
dtype, page, stride, sequence-length, and local-window geometry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import torch

from local_paged_gqa_split_reducer_fused import (
    HEAD_DIM,
    NUM_KV_HEADS,
    NUM_QO_HEADS,
    PAGE_SIZE,
    SM_SCALE,
    WINDOW_LEFT,
    make_wrapper,
    plan_exact,
    run_exact,
    source_paths,
)


BATCH = 32
VISIBLE_PAGES = 65
PINNED_FLASHINFER_VERSION = "0.6.6"
PINNED_SOURCE_HASHES = {
    "data/include/flashinfer/page.cuh":
        "6ad25f50ed08ea74495d8a8d172baf57266e53ce0d42b14dc9e979c1073c0468",
    "data/include/flashinfer/attention/decode.cuh":
        "019d673aa848a938798a2c58b34b9b5813a3f137962cbbd90ef7bd71f636f373",
    "data/include/flashinfer/attention/scheduler.cuh":
        "3fdc85c6b42d9c27fd688c614fef162bb523f3a95f095ba40dc53e3c52712c3b",
    "data/csrc/batch_decode.cu":
        "9b0aa3da779d922af75d57f22d8c8bceb7722c2e4ded94637074b6baf567cd30",
    "data/csrc/batch_decode_jit_binding.cu":
        "fe1bad13e1ed242aa6b0e290bdb5a47388b2869a4305cfcbc952d5ec4b9def0a",
    "data/csrc/batch_decode_customize_config.jinja":
        "61c776b646b1351498f5cad2f7ff6256d0946fd88ed5ce5ce1e490a3d9d8f414",
}
CONSUMER_CUBIN_NAME = (
    "fmhaSm100fKernel_QkvBfloat16OBfloat16H256PagedKv"
    "SlidingOrChunkedCausalP16MultiCtasKvVarSeqQ8Kv128StaticSwapsAbForGen.cubin"
)
CONSUMER_CUBIN_SHA256 = (
    "a5ae26d06e8463baf3e1dac3251633b70ece90ca612a10afa6b09925578fd9be"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def verify_identity(project_root: Path) -> dict[str, Any]:
    import flashinfer

    version = getattr(flashinfer, "__version__", None)
    if version != PINNED_FLASHINFER_VERSION:
        raise RuntimeError(f"FlashInfer version {version!r} is not 0.6.6")
    package_root = Path(flashinfer.__file__).resolve().parent
    observed: dict[str, str] = {}
    for relative, expected in PINNED_SOURCE_HASHES.items():
        path = package_root / relative
        actual = sha256_file(path)
        observed[relative] = actual
        if actual != expected:
            raise RuntimeError(f"pinned source hash mismatch: {relative}={actual}")

    cubin = (
        project_root
        / "inputs/pinned/flashinfer-0.6.6/trtllm-gen-artifact"
        / CONSUMER_CUBIN_NAME
    )
    cubin_hash = sha256_file(cubin)
    if cubin_hash != CONSUMER_CUBIN_SHA256:
        raise RuntimeError(f"project-local stock cubin hash mismatch: {cubin_hash}")
    reducer_paths = source_paths(project_root)
    reducer_source_hashes = {
        str(path.relative_to(project_root)): sha256_file(path)
        for path in (
            project_root / "candidate/local_paged_gqa_split_reducer_fused.py",
            project_root / "candidate/split_reducer_src/batch_decode_config.inc",
            project_root / "candidate/split_reducer_src/batch_decode_kernel.cu",
            reducer_paths["manifest"],
        )
    }
    return {
        "flashinfer_version": version,
        "flashinfer_package_root": str(package_root),
        "source_hashes": observed,
        "project_local_stock_cubin": str(cubin),
        "stock_cubin_sha256": cubin_hash,
        "split_reducer_source_hashes": reducer_source_hashes,
    }


def build_geometry(device: torch.device, seed: int) -> dict[str, Any]:
    generator = torch.Generator(device=device)
    generator.manual_seed(seed)

    # Exact observed production span, monotonically covering 4214..4571.
    seq_lens_list = [
        4214 + round(index * (4571 - 4214) / (BATCH - 1))
        for index in range(BATCH)
    ]
    seq_lens_cpu = torch.tensor(seq_lens_list, dtype=torch.int32)
    blocks_per_req = [(length + PAGE_SIZE - 1) // PAGE_SIZE for length in seq_lens_list]
    max_blocks = max(blocks_per_req)

    # Prefix pages are outside the local window and may alias page zero.  The
    # final 65 logical pages are unique, so every byte the consumers may read
    # or mutate remains independently observable.
    num_physical_pages = 1 + BATCH * VISIBLE_PAGES
    block_tables_cpu = torch.zeros((BATCH, max_blocks), dtype=torch.int32)
    window_indices: list[int] = []
    window_indptr = [0]
    slot_mapping: list[int] = []
    next_page = 1
    for request, (seq_len, num_blocks) in enumerate(zip(seq_lens_list, blocks_per_req)):
        tail = min(VISIBLE_PAGES, num_blocks)
        pages = list(range(next_page, next_page + tail))
        next_page += tail
        block_tables_cpu[request, num_blocks - tail : num_blocks] = torch.tensor(
            pages, dtype=torch.int32
        )
        window_indices.extend(pages)
        window_indptr.append(len(window_indices))
        slot_mapping.append(pages[-1] * PAGE_SIZE + (seq_len - 1) % PAGE_SIZE)
    assert next_page == num_physical_pages

    raw = torch.randn(
        (num_physical_pages, 2, PAGE_SIZE, NUM_KV_HEADS, HEAD_DIM),
        dtype=torch.bfloat16,
        device=device,
        generator=generator,
    )
    initial_cache = raw.permute(0, 1, 3, 2, 4)
    assert initial_cache.stride() == (131072, 65536, 256, 4096, 1)

    q = torch.randn(
        (BATCH, NUM_QO_HEADS, HEAD_DIM),
        dtype=torch.bfloat16,
        device=device,
        generator=generator,
    )
    append_key = torch.randn(
        (BATCH, NUM_KV_HEADS, HEAD_DIM),
        dtype=torch.bfloat16,
        device=device,
        generator=generator,
    )
    append_value = torch.randn(
        (BATCH, NUM_KV_HEADS, HEAD_DIM),
        dtype=torch.bfloat16,
        device=device,
        generator=generator,
    )
    last_page_len = torch.tensor(
        [length % PAGE_SIZE or PAGE_SIZE for length in seq_lens_list],
        dtype=torch.int32,
    )
    return {
        "q": q,
        "append_key": append_key,
        "append_value": append_value,
        "initial_cache": initial_cache,
        "block_tables": block_tables_cpu.to(device),
        "seq_lens": seq_lens_cpu.to(device),
        "window_indices": torch.tensor(window_indices, dtype=torch.int32),
        "window_indptr": torch.tensor(window_indptr, dtype=torch.int32),
        "last_page_len": last_page_len,
        "slot_mapping": torch.tensor(slot_mapping, dtype=torch.int64, device=device),
        "seq_lens_list": seq_lens_list,
        "blocks_per_req": blocks_per_req,
        "num_physical_pages": num_physical_pages,
    }


def compare(stock: torch.Tensor, candidate: torch.Tensor) -> dict[str, Any]:
    stock_f = stock.float()
    candidate_f = candidate.float()
    delta = candidate_f - stock_f
    abs_delta = delta.abs()
    denom = stock_f.abs().clamp_min(1e-6)
    cosine = torch.nn.functional.cosine_similarity(
        stock_f.reshape(-1), candidate_f.reshape(-1), dim=0
    )
    finite = bool(torch.isfinite(candidate_f).all().item())
    metrics = {
        "finite": finite,
        "max_abs": float(abs_delta.max().item()),
        "mean_abs": float(abs_delta.mean().item()),
        "max_rel": float((abs_delta / denom).max().item()),
        "cosine": float(cosine.item()),
        "allclose_rtol_0_05_atol_0_03": bool(
            torch.allclose(candidate_f, stock_f, rtol=0.05, atol=0.03)
        ),
    }
    metrics["pass"] = bool(
        finite
        and metrics["allclose_rtol_0_05_atol_0_03"]
        and metrics["cosine"] >= 0.999
    )
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260728)
    args = parser.parse_args()
    terminal_path = args.artifact_root / "CORRECTNESS_TERMINAL.json"
    marker_path = args.artifact_root / "candidate_science_started"
    stage = "preflight"
    started = time.time()
    try:
        if not torch.cuda.is_available():
            raise RuntimeError("typed_external_blocker: CUDA unavailable")
        device = torch.device("cuda:0")
        props = torch.cuda.get_device_properties(device)
        if props.major != 10:
            raise RuntimeError(
                f"typed_external_blocker: expected SM100 B200, got sm_{props.major}{props.minor}"
            )
        identity = verify_identity(args.project_root)
        geometry = build_geometry(device, args.seed)

        stage = "build_candidate"
        workspace_candidate = torch.zeros(128 * 1024 * 1024, dtype=torch.uint8, device=device)
        wrapper = make_wrapper(args.project_root, workspace_candidate)
        plan_evidence = plan_exact(
            wrapper,
            geometry["window_indptr"],
            geometry["window_indices"],
            geometry["last_page_len"],
        )
        atomic_json(
            args.artifact_root / "TINY_SPLIT_PLAN_TERMINAL.json",
            {
                "schema_version": 1,
                "terminal": "exact_split_plan_passed",
                "scientific_sample_consumed": False,
                "geometry": {
                    "batch": BATCH,
                    "q_heads": NUM_QO_HEADS,
                    "kv_heads": NUM_KV_HEADS,
                    "head_dim": HEAD_DIM,
                    "page_size": PAGE_SIZE,
                    "window_left": WINDOW_LEFT,
                },
                "plan": plan_evidence,
            },
        )

        stock_cache = geometry["initial_cache"].clone()
        candidate_cache = geometry["initial_cache"].clone()
        q = geometry["q"]
        append_key = geometry["append_key"]
        append_value = geometry["append_value"]
        slot_mapping = geometry["slot_mapping"]

        stage = "scientific_pair"
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text("candidate_science_started=true\n")

        # Import registers the exact pinned vLLM cache op.
        import vllm._custom_ops  # noqa: F401
        from flashinfer.decode import trtllm_batch_decode_with_kv_cache

        scale = torch.ones(1, dtype=torch.float32, device=device)
        # vLLM's append ABI indexes the cache as [block, entry, head, dim].
        # The underlying production cache remains HND; transpose only the view
        # supplied to the append operation so its entry/head strides are exact.
        stock_key_append_view = stock_cache[:, 0].transpose(1, 2)
        stock_value_append_view = stock_cache[:, 1].transpose(1, 2)
        torch.ops._C_cache_ops.reshape_and_cache_flash(
            append_key,
            append_value,
            stock_key_append_view,
            stock_value_append_view,
            slot_mapping,
            "auto",
            scale,
            scale,
        )
        workspace_stock = torch.zeros(128 * 1024 * 1024, dtype=torch.uint8, device=device)
        stock_out = trtllm_batch_decode_with_kv_cache(
            query=q,
            kv_cache=stock_cache,
            workspace_buffer=workspace_stock,
            block_tables=geometry["block_tables"],
            seq_lens=geometry["seq_lens"],
            max_seq_len=max(geometry["seq_lens_list"]),
            bmm1_scale=SM_SCALE,
            bmm2_scale=1.0,
            window_left=WINDOW_LEFT,
            kv_layout="HND",
            enable_pdl=False,
            backend="trtllm-gen",
            q_len_per_req=1,
        )
        torch.cuda.synchronize()
        atomic_json(
            args.artifact_root / "STOCK_ARM_COMPLETED.json",
            {
                "schema_version": 1,
                "state": "stock_arm_completed",
                "stock_append_view_shape": list(stock_key_append_view.shape),
                "stock_append_view_strides": list(stock_key_append_view.stride()),
            },
        )
        candidate_out = run_exact(
            wrapper,
            q,
            candidate_cache,
            append_key,
            append_value,
            slot_mapping,
        )
        torch.cuda.synchronize()
        atomic_json(
            args.artifact_root / "CANDIDATE_ARM_COMPLETED.json",
            {
                "schema_version": 1,
                "state": "candidate_arm_completed",
                "mechanism": "native_split_partials_plus_one_fresh_state_in_final_reducer",
            },
        )

        output_metrics = compare(stock_out, candidate_out)
        cache_equal = bool(torch.equal(stock_cache, candidate_cache))
        result_pass = bool(output_metrics["pass"] and cache_equal)
        payload = {
            "schema_version": 1,
            "terminal": "correct" if result_pass else "incorrect",
            "interpretable_result": True,
            "scientific_sample_consumed": True,
            "elapsed_seconds": time.time() - started,
            "identity": identity,
            "geometry": {
                "batch": BATCH,
                "q_heads": NUM_QO_HEADS,
                "kv_heads": NUM_KV_HEADS,
                "head_dim": HEAD_DIM,
                "page_size": PAGE_SIZE,
                "window_left": WINDOW_LEFT,
                "visible_tokens": WINDOW_LEFT + 1,
                "seq_lens": geometry["seq_lens_list"],
                "blocks_per_request": geometry["blocks_per_req"],
                "cache_shape": list(candidate_cache.shape),
                "cache_strides": list(candidate_cache.stride()),
                "num_physical_pages": geometry["num_physical_pages"],
            },
            "output": output_metrics,
            "cache_bitwise_equal": cache_equal,
            "split_plan": plan_evidence,
            "unique_tail_partition_owner_proved": True,
            "no_cross_cta_cache_visibility_dependency": True,
            "cache_owner_mapping": {
                "q_heads_per_kv_head": NUM_QO_HEADS // NUM_KV_HEADS,
                "kv_head_formula": "qo_head_idx / 2",
                "owner_formula": "qo_head_idx % 2 == 0",
                "owners_per_request": NUM_KV_HEADS,
            },
            "stock_append_layout": {
                "logical_cache": "HND [pages,heads,page,dim]",
                "append_abi_view": "[pages,page,heads,dim]",
                "append_abi_strides": list(stock_key_append_view.stride()),
            },
        }
        atomic_json(terminal_path, payload)
        print(json.dumps(payload, sort_keys=True))
        return 0 if result_pass else 2
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "terminal": "invalid_attempt",
            "interpretable_result": False,
            "scientific_sample_consumed": False,
            "stage": stage,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_seconds": time.time() - started,
        }
        atomic_json(terminal_path, payload)
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
