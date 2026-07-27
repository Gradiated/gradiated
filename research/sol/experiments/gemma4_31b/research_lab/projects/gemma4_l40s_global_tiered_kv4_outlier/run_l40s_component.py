#!/usr/bin/env python3
"""Run the later exact SM89 producer-plus-consumer comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time

import torch

from sglang_global_tiered_kv4 import (
    CONCURRENCY,
    HEAD_DIM,
    KV_HEADS,
    PEAK_PHYSICAL_ROWS,
    QUERY_HEADS,
    allocate_candidate,
    build_locked_c32_layout,
    candidate_decode_step,
    load_extension,
    materialize_candidate,
)


PINNED_COMMIT = "c6a6200a1a778a799ba61c395ac292317f01ebc9"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timed(callable_, repetitions: int) -> list[float]:
    samples = []
    for _ in range(repetitions):
        start = torch.cuda.Event(enable_timing=True)
        stop = torch.cuda.Event(enable_timing=True)
        start.record()
        output = callable_()
        output.float().sum().item()
        stop.record()
        stop.synchronize()
        samples.append(float(start.elapsed_time(stop)))
    return samples


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=20)
    args = parser.parse_args()
    observed_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=args.source_root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    if observed_commit != PINNED_COMMIT:
        raise RuntimeError(f"SGLang commit mismatch: {observed_commit}")
    if not torch.cuda.is_available():
        raise RuntimeError("typed_target_unavailable: CUDA is required")
    device = torch.device("cuda")
    if torch.cuda.get_device_capability(device) != (8, 9):
        raise RuntimeError("typed_target_mismatch: the component is frozen to SM89")

    layout = build_locked_c32_layout(4571)
    generator = torch.Generator(device=device).manual_seed(20260727)
    keys = torch.randn(
        (PEAK_PHYSICAL_ROWS, KV_HEADS, HEAD_DIM),
        dtype=torch.bfloat16,
        device=device,
        generator=generator,
    )
    values = torch.randn(
        keys.shape, dtype=torch.bfloat16, device=device, generator=generator
    )
    query = torch.randn(
        (CONCURRENCY, QUERY_HEADS, HEAD_DIM),
        dtype=torch.bfloat16,
        device=device,
        generator=generator,
    )
    candidate = allocate_candidate(device)

    from sglang.kernels.ops.attention.decode_attention import decode_attention_fwd

    baseline_k = keys.to(torch.float8_e5m2).view(torch.uint8)
    baseline_v = values.to(torch.float8_e5m2).view(torch.uint8)
    kv_indptr = torch.as_tensor(layout.kv_indptr, device=device)
    kv_indices = torch.as_tensor(layout.kv_indices, device=device)
    max_splits = 8
    attn_logits = torch.empty(
        (CONCURRENCY, QUERY_HEADS, max_splits, HEAD_DIM),
        dtype=torch.float32,
        device=device,
    )
    attn_lse = torch.empty(
        (CONCURRENCY, QUERY_HEADS, max_splits),
        dtype=torch.float32,
        device=device,
    )
    num_splits = torch.full(
        (CONCURRENCY,), max_splits, dtype=torch.int32, device=device
    )

    def baseline_call():
        new_physical = torch.as_tensor(layout.new_physical, device=device)
        baseline_k.index_copy_(
            0, new_physical, keys.index_select(0, new_physical).to(torch.float8_e5m2).view(torch.uint8)
        )
        baseline_v.index_copy_(
            0,
            new_physical,
            values.index_select(0, new_physical).to(torch.float8_e5m2).view(torch.uint8),
        )
        output = torch.empty_like(query)
        decode_attention_fwd(
            query,
            baseline_k,
            baseline_v,
            output,
            kv_indptr,
            kv_indices,
            attn_logits,
            attn_lse,
            num_splits,
            max_splits,
            1.0 / HEAD_DIM**0.5,
            1.0,
            1.0,
            page_size=1,
        )
        return output

    def candidate_call():
        return candidate_decode_step(
            query, keys, values, layout=layout, candidate=candidate
        )

    extension = load_extension()
    materialize_candidate(keys, values, layout=layout, candidate=candidate)
    resource_process = subprocess.run(
        ["cuobjdump", "--dump-resource-usage", extension.__file__],
        text=True,
        capture_output=True,
        check=True,
    )
    compiler_resource_usage = resource_process.stdout + resource_process.stderr
    progress = args.output.with_suffix(".progress.json")
    baseline_output = baseline_call()
    torch.cuda.synchronize()
    progress.parent.mkdir(parents=True, exist_ok=True)
    progress.write_text(
        json.dumps(
            {
                "science_started": True,
                "baseline_first_untimed_complete": True,
                "baseline_output_sum": float(baseline_output.float().sum()),
                "candidate_first_untimed_complete": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    candidate_output = candidate_call()
    torch.cuda.synchronize()
    relative_l2 = float(
        torch.linalg.vector_norm(
            candidate_output.float() - baseline_output.float()
        )
        / torch.linalg.vector_norm(baseline_output.float())
    )
    cosine = float(
        torch.nn.functional.cosine_similarity(
            candidate_output.float().reshape(1, -1),
            baseline_output.float().reshape(1, -1),
        )
    )
    progress.write_text(
        json.dumps(
            {
                "science_started": True,
                "baseline_first_untimed_complete": True,
                "baseline_output_sum": float(baseline_output.float().sum()),
                "candidate_first_untimed_complete": True,
                "candidate_output_sum": float(candidate_output.float().sum()),
                "relative_l2": relative_l2,
                "cosine": cosine,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if not torch.isfinite(candidate_output).all() or relative_l2 > 0.08 or cosine < 0.995:
        raise RuntimeError(
            f"numerical gate failed: relative_l2={relative_l2}, cosine={cosine}"
        )
    for _ in range(args.warmup):
        baseline_call()
        candidate_call()
    torch.cuda.synchronize()
    baseline_ms = timed(baseline_call, args.repetitions)
    candidate_ms = timed(candidate_call, args.repetitions)
    result = {
        "kind": "l40s_global_tiered_kv4_outlier_component",
        "created_at_unix": time.time(),
        "hardware": torch.cuda.get_device_name(device),
        "capability": list(torch.cuda.get_device_capability(device)),
        "sglang_commit": observed_commit,
        "full_producer_plus_consumer": True,
        "baseline_current_runtime_e5m2_consumer": True,
        "shape": {
            "batch": CONCURRENCY,
            "sequence_length": layout.sequence_length,
            "physical_rows": PEAK_PHYSICAL_ROWS,
            "query_heads": QUERY_HEADS,
            "kv_heads": KV_HEADS,
            "head_dim": HEAD_DIM,
            "page_size": 1,
        },
        "numerical": {"relative_l2": relative_l2, "cosine": cosine},
        "baseline_ms": {
            "samples": baseline_ms,
            "median": statistics.median(baseline_ms),
        },
        "candidate_ms": {
            "samples": candidate_ms,
            "median": statistics.median(candidate_ms),
        },
        "compiler_resource_usage": compiler_resource_usage,
        "extension_binary": {
            "path": extension.__file__,
            "sha256": sha256(Path(extension.__file__)),
        },
        "implementation_hashes": {
            path.name: sha256(path)
            for path in (
                Path(__file__),
                Path(__file__).with_name("sglang_global_tiered_kv4.py"),
                Path(__file__).with_name("global_tiered_kv4_cuda.cu"),
                Path(__file__).with_name("global_tiered_kv4_bindings.cpp"),
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
