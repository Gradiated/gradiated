#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib

import torch

from residual_intervention import translate_valid_swa_indices_inplace
from sglang.srt.layers.attention.triton_ops.kv_indices import (
    create_flashinfer_kv_indices_triton,
)


CASES = {
    "empty": [],
    "odd_lengths": [1, 3, 17],
    "cache_hit_reorder": [1024, 7, 511, 1],
    "page_boundary": [1023, 1024, 1025],
    "filter_merge": [31, 2, 513, 9, 1024],
    "maximum_exact_workload": [1024] * 32,
}


def run_case(name: str, lengths: list[int]) -> dict[str, object]:
    batch_size = len(lengths)
    max_context = max(max(lengths, default=0), 1)
    pool_rows = max(batch_size, 1)
    req_to_token = torch.arange(
        pool_rows * max_context, dtype=torch.int64, device="cuda"
    ).reshape(pool_rows, max_context)
    req_pool_indices = torch.arange(batch_size - 1, -1, -1, device="cuda", dtype=torch.int32)
    seq_lens = torch.tensor(lengths, dtype=torch.int32, device="cuda")
    kv_indptr = torch.zeros(batch_size + 1, dtype=torch.int32, device="cuda")
    if batch_size:
        kv_indptr[1:] = torch.cumsum(seq_lens, dim=0)
    capacity = max(sum(lengths), 1)
    candidate = torch.full((capacity,), -1, dtype=torch.int64, device="cuda")
    if batch_size:
        create_flashinfer_kv_indices_triton[(batch_size,)](
            req_to_token,
            req_pool_indices,
            seq_lens,
            kv_indptr,
            None,
            candidate,
            req_to_token.stride(0),
        )
    mapping = torch.arange(pool_rows * max_context + 1, dtype=torch.int64, device="cuda")
    mapping = mapping.mul_(7).add_(11)
    torch.cuda.synchronize()
    full_reference = candidate.clone()
    valid_count = sum(lengths)
    expected = mapping[full_reference[:valid_count]]
    translate_valid_swa_indices_inplace(candidate, kv_indptr, batch_size, mapping)
    consumed_candidate = candidate[:valid_count].to(torch.int64).sum()
    consumed_expected = expected.to(torch.int64).sum()
    torch.cuda.synchronize()
    exact = torch.equal(candidate[:valid_count], expected)
    consumed = bool((consumed_candidate == consumed_expected).item())
    return {
        "name": name,
        "batch_size": batch_size,
        "capacity": capacity,
        "valid_count": valid_count,
        "exact": exact,
        "consumer_exact": consumed,
        "pass": exact and consumed,
    }


def graph_replay_case() -> dict[str, object]:
    batch_size = 4
    max_context = 1025
    capacity = batch_size * max_context
    req_to_token = torch.arange(batch_size * max_context, dtype=torch.int64, device="cuda").reshape(batch_size, max_context)
    req_pool_indices = torch.arange(batch_size, dtype=torch.int32, device="cuda")
    seq_lens = torch.tensor([1025, 1024, 17, 1], dtype=torch.int32, device="cuda")
    kv_indptr = torch.zeros(batch_size + 1, dtype=torch.int32, device="cuda")
    output = torch.full((capacity,), -1, dtype=torch.int64, device="cuda")
    mapping = torch.arange(batch_size * max_context + 1, dtype=torch.int64, device="cuda").mul_(3).add_(5)

    def launch() -> None:
        kv_indptr[1:] = torch.cumsum(seq_lens, dim=0)
        create_flashinfer_kv_indices_triton[(batch_size,)](
            req_to_token,
            req_pool_indices,
            seq_lens,
            kv_indptr,
            None,
            output,
            req_to_token.stride(0),
        )
        translate_valid_swa_indices_inplace(output, kv_indptr, batch_size, mapping)

    launch()
    torch.cuda.synchronize()
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        launch()
    seq_lens.copy_(torch.tensor([3, 511, 1024, 9], dtype=torch.int32, device="cuda"))
    graph.replay()
    torch.cuda.synchronize()
    lengths = [3, 511, 1024, 9]
    full = torch.cat([req_to_token[row, :length] for row, length in enumerate(lengths)])
    expected = mapping[full]
    exact = torch.equal(output[: sum(lengths)], expected)
    return {"name": "cuda_graph_replay_dynamic_lengths", "valid_count": sum(lengths), "exact": exact, "pass": exact}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    rows = [run_case(name, lengths) for name, lengths in CASES.items()]
    rows.append(graph_replay_case())
    value = {
        "schema_version": 1,
        "device": torch.cuda.get_device_name(),
        "cases": rows,
        "candidate_cuda_started": True,
        "pass": all(row["pass"] for row in rows),
    }
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0 if value["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
