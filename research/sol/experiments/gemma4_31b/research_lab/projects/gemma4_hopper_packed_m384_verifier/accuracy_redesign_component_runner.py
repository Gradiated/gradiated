#!/usr/bin/env python3
"""Lifecycle-pure H100 runner for the *new* FP32 partitioned candidate.

This process neither claims nor releases a bench and never invokes the closed
V2 implementation.  A lab-owned outer controller may execute it once after a
new director admission.  All path/digest/margin checks happen before the
science marker.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import types
from typing import Any

import torch


BATCH = 32
DRAFT = 12
HEADS = 32
GLOBAL_PREFIX = 4214
LOCAL_PREFIX = 1024
CONTROL_SHA256 = "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"module_spec_unavailable:{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def install_control_import_stubs() -> None:
    for name in (
        "sglang",
        "sglang.srt",
        "sglang.srt.layers",
        "sglang.srt.layers.attention",
        "sglang.srt.layers.attention.triton_ops",
    ):
        module = types.ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
    prefill = types.ModuleType(
        "sglang.srt.layers.attention.triton_ops.prefill_attention"
    )
    prefill.context_attention_fwd = lambda *args, **kwargs: None
    sys.modules[prefill.__name__] = prefill
    utilities = types.ModuleType("sglang.srt.utils")
    utilities.is_cuda = lambda: True
    utilities.is_hip = lambda: False
    sys.modules[utilities.__name__] = utilities


def fixture(*, seed: int, head_dim: int, kv_heads: int, prefix: int):
    torch.manual_seed(seed)
    tokens = BATCH * DRAFT
    total_pages = BATCH * GLOBAL_PREFIX
    q = torch.randn(
        (tokens, HEADS, head_dim), device="cuda", dtype=torch.bfloat16
    )
    k = torch.randn(
        (tokens, kv_heads, head_dim), device="cuda", dtype=torch.bfloat16
    )
    v = torch.randn(
        (tokens, kv_heads, head_dim), device="cuda", dtype=torch.bfloat16
    )
    k_cache = torch.randn(
        (total_pages, kv_heads, head_dim),
        device="cuda",
        dtype=torch.bfloat16,
    ).to(torch.float8_e4m3fn)
    v_cache = torch.randn(
        (total_pages, kv_heads, head_dim),
        device="cuda",
        dtype=torch.bfloat16,
    ).to(torch.float8_e4m3fn)
    pages = torch.randperm(
        total_pages, device="cuda", dtype=torch.int32
    ).view(BATCH, GLOBAL_PREFIX)[:, -prefix:].contiguous()
    qo_indptr = torch.arange(
        0, (BATCH + 1) * DRAFT, DRAFT, device="cuda", dtype=torch.int32
    )
    kv_indptr = torch.arange(
        0, (BATCH + 1) * prefix, prefix, device="cuda", dtype=torch.int32
    )
    tree = torch.zeros((DRAFT, DRAFT), device="cuda", dtype=torch.bool)
    for row in range(DRAFT):
        tree[row, row] = True
        tree[row, 0] = True
        for column in range(1, row):
            tree[row, column] = column % 3 == row % 3
    masks = []
    for _ in range(BATCH):
        visible_prefix = torch.ones(
            (DRAFT, GLOBAL_PREFIX), device="cuda", dtype=torch.bool
        )
        masks.append(torch.cat((visible_prefix, tree), dim=1).flatten())
    custom_mask = torch.cat(masks)
    mask_stride = DRAFT * (GLOBAL_PREFIX + DRAFT)
    mask_indptr = torch.arange(
        0,
        (BATCH + 1) * mask_stride,
        mask_stride,
        device="cuda",
        dtype=torch.int32,
    )
    return {
        "q": q,
        "k": k,
        "v": v,
        "k_cache": k_cache,
        "v_cache": v_cache,
        "qo_indptr": qo_indptr,
        "kv_indptr": kv_indptr,
        "kv_indices": pages.flatten(),
        "custom_mask": custom_mask,
        "mask_indptr": mask_indptr,
        "window_offsets": torch.full(
            (BATCH,),
            GLOBAL_PREFIX - prefix,
            device="cuda",
            dtype=torch.int32,
        ),
    }


def invoke(module, tensors, output, *, local: bool, head_dim: int) -> None:
    module.extend_attention_fwd(
        tensors["q"],
        tensors["k"],
        tensors["v"],
        output,
        tensors["k_cache"],
        tensors["v_cache"],
        tensors["qo_indptr"],
        tensors["kv_indptr"],
        tensors["kv_indices"],
        tensors["custom_mask"],
        True,
        tensors["mask_indptr"],
        DRAFT,
        1.0,
        1.0,
        1.0 / math.sqrt(head_dim),
        sliding_window_size=LOCAL_PREFIX if local else -1,
        window_kv_offsets=tensors["window_offsets"] if local else None,
    )


def high_precision_reference(
    tensors, *, head_dim: int, kv_heads: int, prefix: int, local: bool
) -> torch.Tensor:
    """Complete FP64 output from the same gathered paged-KV producer bytes."""
    output = torch.empty(
        (BATCH * DRAFT, HEADS, head_dim),
        device="cuda",
        dtype=torch.float64,
    )
    kv_group = HEADS // kv_heads
    head_to_kv = torch.arange(HEADS, device="cuda") // kv_group
    scale = 1.0 / math.sqrt(head_dim)
    for sequence in range(BATCH):
        start = sequence * DRAFT
        pages = tensors["kv_indices"][
            sequence * prefix : (sequence + 1) * prefix
        ].long()
        key = tensors["k_cache"][pages].double().permute(1, 0, 2)[head_to_kv]
        value = tensors["v_cache"][pages].double().permute(1, 0, 2)[
            head_to_kv
        ]
        extend_key = tensors["k"][start : start + DRAFT].double().permute(
            1, 0, 2
        )[head_to_kv]
        extend_value = tensors["v"][start : start + DRAFT].double().permute(
            1, 0, 2
        )[head_to_kv]
        key = torch.cat((key, extend_key), dim=1)
        value = torch.cat((value, extend_value), dim=1)
        query = tensors["q"][start : start + DRAFT].double().permute(1, 0, 2)
        score = torch.einsum("hqd,hkd->hqk", query, key) * scale
        visible = torch.zeros(
            (DRAFT, prefix + DRAFT), device="cuda", dtype=torch.bool
        )
        visible[:, :prefix] = True
        if local:
            for row in range(DRAFT):
                visible[row, :row] = False
        tree_offset = sequence * DRAFT * (GLOBAL_PREFIX + DRAFT)
        tree = tensors["custom_mask"][
            tree_offset : tree_offset + DRAFT * (GLOBAL_PREFIX + DRAFT)
        ].view(DRAFT, GLOBAL_PREFIX + DRAFT)[:, GLOBAL_PREFIX:]
        visible[:, prefix:] = tree
        score.masked_fill_(~visible[None, :, :], -torch.inf)
        probability = torch.softmax(score, dim=-1)
        output[start : start + DRAFT] = torch.einsum(
            "hqk,hkd->qhd", probability, value
        )
    return output


def timed_ms(function) -> float:
    begin = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    begin.record()
    function()
    end.record()
    end.synchronize()
    return float(begin.elapsed_time(end))


def distribution(values: list[float]) -> dict[str, object]:
    return {
        "samples_ms": values,
        "minimum_ms": min(values),
        "p50_ms": statistics.median(values),
        "maximum_ms": max(values),
    }


def compiler_resources(module) -> list[dict[str, object]]:
    """Best-effort extraction from Triton's runtime cache; emptiness is fatal."""
    records: list[dict[str, object]] = []
    seen: set[int] = set()

    def visit(value, kernel_name: str, depth: int = 0) -> None:
        if depth > 5 or id(value) in seen:
            return
        seen.add(id(value))
        n_regs = getattr(value, "n_regs", None)
        metadata = getattr(value, "metadata", None)
        if n_regs is not None:
            records.append(
                {
                    "kernel": kernel_name,
                    "registers_per_thread": int(n_regs),
                    "shared_memory_bytes": int(
                        getattr(metadata, "shared", 0) if metadata else 0
                    ),
                    "spill_bytes": getattr(metadata, "spill_bytes", None),
                }
            )
        if isinstance(value, dict):
            for child in value.values():
                visit(child, kernel_name, depth + 1)
        elif isinstance(value, (tuple, list)):
            for child in value:
                visit(child, kernel_name, depth + 1)
        else:
            cache = getattr(value, "cache", None)
            if cache is not None and cache is not value:
                visit(cache, kernel_name, depth + 1)

    for name in (
        "_score_partition_fp32_kernel",
        "_merge_state_fp32_kernel",
        "_partition_value_fp32_kernel",
        "_merge_value_fp32_kernel",
    ):
        visit(getattr(module, name), name)
    if not records:
        raise RuntimeError("compiled_resource_metadata_unavailable")
    return records


def evaluate(
    control,
    candidate,
    *,
    local: bool,
    head_dim: int,
    kv_heads: int,
    prefix: int,
    seed: int,
    repetitions: int,
) -> dict[str, object]:
    tensors = fixture(
        seed=seed, head_dim=head_dim, kv_heads=kv_heads, prefix=prefix
    )
    stock_a = torch.empty_like(tensors["q"])
    stock_b = torch.empty_like(tensors["q"])
    actual = torch.empty_like(tensors["q"])
    invoke(control, tensors, stock_a, local=local, head_dim=head_dim)
    invoke(control, tensors, stock_b, local=local, head_dim=head_dim)
    invoke(candidate, tensors, actual, local=local, head_dim=head_dim)
    torch.cuda.synchronize()
    reference = high_precision_reference(
        tensors,
        head_dim=head_dim,
        kv_heads=kv_heads,
        prefix=prefix,
        local=local,
    )
    delta = actual.double() - reference
    aa_delta = stock_a.float() - stock_b.float()
    candidate_samples = [
        timed_ms(
            lambda: invoke(
                candidate, tensors, actual, local=local, head_dim=head_dim
            )
        )
        for _ in range(repetitions)
    ]
    control_samples = [
        timed_ms(
            lambda: invoke(
                control, tensors, stock_a, local=local, head_dim=head_dim
            )
        )
        for _ in range(repetitions)
    ]
    return {
        "kind": "local_d256" if local else "global_d512",
        "geometry": {
            "batch": BATCH,
            "query_rows": BATCH * DRAFT,
            "query_heads": HEADS,
            "kv_heads": kv_heads,
            "head_dim": head_dim,
            "prefix_tokens": prefix,
            "page_size": 1,
        },
        "stock_aa": {
            "max_abs": float(aa_delta.abs().max().item()),
            "relative_l2": float(
                torch.linalg.vector_norm(aa_delta)
                / torch.linalg.vector_norm(stock_a.float()).clamp_min(1e-30)
            ),
        },
        "candidate_vs_fp64": {
            "max_abs": float(delta.abs().max().item()),
            "relative_l2": float(
                torch.linalg.vector_norm(delta)
                / torch.linalg.vector_norm(reference).clamp_min(1e-30)
            ),
            "all_finite": bool(torch.isfinite(actual).all().item()),
        },
        "unchanged_output_consumer_square_sum": float(
            actual.float().square().sum().item()
        ),
        "control": distribution(control_samples),
        "candidate": distribution(candidate_samples),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--token-margin-oracle", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260726)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation = args.artifact_root / "INVOCATION_STATE.json"
    atomic(
        invocation,
        {
            "schema_version": 1,
            "phase": "pre_science",
            "candidate_cuda_invocation_started": False,
        },
    )
    if digest(args.candidate) != args.candidate_sha256:
        raise RuntimeError("candidate_digest_mismatch")
    if digest(args.control) != CONTROL_SHA256:
        raise RuntimeError("control_digest_mismatch")
    margin_oracle = json.loads(args.token_margin_oracle.read_text())
    if margin_oracle.get("schema_version") != 1:
        raise RuntimeError("token_margin_oracle_schema_mismatch")
    budgets = margin_oracle.get("attention_output_error_budget", {})
    if not all(kind in budgets for kind in ("local_d256", "global_d512")):
        raise RuntimeError("token_margin_oracle_missing_output_budgets")
    if not torch.cuda.is_available() or torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("sm90_cuda_required")
    install_control_import_stubs()
    control = load_module("packed_m384_control", args.control)
    candidate = load_module("packed_m384_fp32_partitioned", args.candidate)
    atomic(
        invocation,
        {
            "schema_version": 1,
            "phase": "science_started",
            "candidate_cuda_invocation_started": True,
            "started_unix_s": time.time(),
        },
    )
    rows = [
        evaluate(
            control,
            candidate,
            local=True,
            head_dim=256,
            kv_heads=16,
            prefix=LOCAL_PREFIX,
            seed=args.seed,
            repetitions=args.repetitions,
        ),
        evaluate(
            control,
            candidate,
            local=False,
            head_dim=512,
            kv_heads=4,
            prefix=GLOBAL_PREFIX,
            seed=args.seed + 1,
            repetitions=args.repetitions,
        ),
    ]
    resources = compiler_resources(candidate)
    for row in rows:
        budget = budgets[row["kind"]]
        row["token_margin_calibrated_pass"] = (
            row["candidate_vs_fp64"]["max_abs"]
            <= float(budget["max_attention_output_abs"])
            and row["candidate_vs_fp64"]["relative_l2"]
            <= float(budget["max_attention_output_relative_l2"])
        )
    correct = all(
        row["candidate_vs_fp64"]["all_finite"]
        and row["token_margin_calibrated_pass"]
        and row["unchanged_output_consumer_square_sum"] > 0.0
        for row in rows
    )
    prior_saved = {
        "local_d256": 1.3924800157546997 - 0.4918079972267151,
        "global_d512": 3.2703680992126465 - 2.910111904144287,
    }
    retains_gain = all(
        row["candidate"]["p50_ms"]
        <= row["control"]["p50_ms"] - 0.8 * prior_saved[row["kind"]]
        for row in rows
    )
    terminal = {
        "schema_version": 1,
        "type": "packed_m384_fp32_partitioned_component_result",
        "result": (
            "component_positive" if correct and retains_gain else "typed_none"
        ),
        "correct": correct,
        "retains_at_least_80pct_prior_time_saved": retains_gain,
        "rows": rows,
        "compiled_resources": resources,
        "identity": {
            "candidate_sha256": digest(args.candidate),
            "control_sha256": digest(args.control),
            "token_margin_oracle_sha256": digest(args.token_margin_oracle),
            "gpu": torch.cuda.get_device_name(),
            "capability": list(torch.cuda.get_device_capability()),
            "torch": torch.__version__,
        },
    }
    terminal_path = args.artifact_root / "PACKED_M384_FP32_COMPONENT_RESULT.json"
    atomic(terminal_path, terminal)
    atomic(
        invocation,
        {
            "schema_version": 1,
            "phase": "scientific_terminal_recorded",
            "candidate_cuda_invocation_started": True,
            "terminal": terminal_path.name,
        },
    )
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0 if terminal["result"] == "component_positive" else 2


if __name__ == "__main__":
    raise SystemExit(main())
