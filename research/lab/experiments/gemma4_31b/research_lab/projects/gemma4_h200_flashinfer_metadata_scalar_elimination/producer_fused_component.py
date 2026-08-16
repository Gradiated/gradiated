#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import time

import torch

from residual_intervention import create_flashinfer_swa_kv_indices_triton
from sglang.srt.layers.attention.triton_ops.kv_indices import (
    create_flashinfer_kv_indices_triton,
)


def tensors(lengths: list[int], context: int = 1280) -> tuple[torch.Tensor, ...]:
    batch_size = len(lengths)
    req_to_token = torch.arange(
        batch_size * context, dtype=torch.int64, device="cuda"
    ).reshape(batch_size, context)
    req_pool_indices = torch.arange(
        batch_size - 1, -1, -1, dtype=torch.int32, device="cuda"
    )
    seq_lens = torch.tensor(lengths, dtype=torch.int32, device="cuda")
    window_lens = torch.minimum(seq_lens, torch.tensor(1024, device="cuda"))
    indptr = torch.zeros(batch_size + 1, dtype=torch.int32, device="cuda")
    indptr[1:] = torch.cumsum(window_lens, dim=0)
    starts = seq_lens - window_lens
    output = torch.full((batch_size * 1024,), -1, dtype=torch.int64, device="cuda")
    mapping = torch.arange(
        batch_size * context + 1, dtype=torch.int64, device="cuda"
    ).mul_(13).add_(7)
    return req_to_token, req_pool_indices, window_lens, indptr, starts, output, mapping


def launch_stock(values: tuple[torch.Tensor, ...], valid_count: int) -> torch.Tensor:
    req_to_token, req_pool_indices, lengths, indptr, starts, output, mapping = values
    create_flashinfer_kv_indices_triton[(len(req_pool_indices),)](
        req_to_token,
        req_pool_indices,
        lengths,
        indptr,
        starts,
        output,
        req_to_token.stride(0),
    )
    output[: indptr[-1]] = mapping[output[: indptr[-1]]]
    return output[:valid_count]


def launch_fused(values: tuple[torch.Tensor, ...], valid_count: int) -> torch.Tensor:
    req_to_token, req_pool_indices, lengths, indptr, starts, output, mapping = values
    create_flashinfer_swa_kv_indices_triton[(len(req_pool_indices),)](
        req_to_token,
        req_pool_indices,
        lengths,
        indptr,
        starts,
        output,
        mapping,
        req_to_token.stride(0),
    )
    return output[:valid_count]


def expected(values: tuple[torch.Tensor, ...], lengths: list[int]) -> torch.Tensor:
    req_to_token, req_pool_indices, _, _, starts, _, mapping = values
    rows = []
    for request, length, start in zip(
        req_pool_indices.cpu().tolist(), lengths, starts.cpu().tolist()
    ):
        window_length = min(length, 1024)
        rows.append(mapping[req_to_token[request, start : start + window_length]])
    return torch.cat(rows) if rows else torch.empty(0, dtype=torch.int64, device="cuda")


def correctness_case(name: str, lengths: list[int]) -> dict[str, object]:
    values = tensors(lengths)
    valid_count = sum(min(x, 1024) for x in lengths)
    reference = expected(values, lengths)
    stock = launch_stock(values, valid_count).clone()
    fused = launch_fused(values, valid_count).clone()
    torch.cuda.synchronize()
    return {
        "name": name,
        "valid_count": valid_count,
        "stock_exact": torch.equal(stock, reference),
        "fused_exact": torch.equal(fused, reference),
        "consumer_checksum": int(fused.sum().item()),
    }


def graph_case() -> dict[str, object]:
    lengths = [1280, 1024, 17, 1] + [1024] * 28
    values = tensors(lengths)
    valid_count = sum(min(x, 1024) for x in lengths)
    launch_fused(values, valid_count)
    torch.cuda.synchronize()
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        launch_fused(values, valid_count)
    new_lengths = [3, 511, 1024, 9] + [1024] * 28
    seq_lens = torch.tensor(new_lengths, dtype=torch.int32, device="cuda")
    values[2].copy_(torch.minimum(seq_lens, torch.tensor(1024, device="cuda")))
    values[3][1:] = torch.cumsum(values[2], dim=0)
    values[4].copy_(seq_lens - values[2])
    graph.replay()
    torch.cuda.synchronize()
    new_valid = sum(min(x, 1024) for x in new_lengths)
    reference = expected(values, new_lengths)
    return {
        "name": "cuda_graph_dynamic_lengths",
        "valid_count": new_valid,
        "fused_exact": torch.equal(values[5][:new_valid], reference),
        "consumer_checksum": int(values[5][:new_valid].sum().item()),
    }


def time_path(function, values: tuple[torch.Tensor, ...], valid_count: int) -> list[float]:
    for _ in range(20):
        function(values, valid_count)
    torch.cuda.synchronize()
    samples = []
    for _ in range(11):
        started = time.perf_counter_ns()
        for _ in range(100):
            function(values, valid_count)
        torch.cuda.synchronize()
        samples.append((time.perf_counter_ns() - started) / 100 / 1000)
    return samples


def summarize(samples: list[float]) -> dict[str, object]:
    ordered = sorted(samples)
    return {
        "unit": "microseconds_per_producer_consumer_call",
        "samples": samples,
        "median": statistics.median(samples),
        "p10": ordered[1],
        "p90": ordered[-2],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    os.environ.pop("RESIDUAL_CANDIDATE_AUDIT", None)
    cases = [
        correctness_case("odd_filter_merge", [1, 3, 17, 1023, 1024, 1280]),
        correctness_case("exact_c32", [1280] * 32),
        graph_case(),
    ]
    production = tensors([1280] * 32)
    valid_count = 32768
    stock = summarize(time_path(launch_stock, production, valid_count))
    fused = summarize(time_path(launch_fused, production, valid_count))
    gain = 1 - float(fused["median"]) / float(stock["median"])
    passed = all(
        row.get("stock_exact", True) and row.get("fused_exact", False) for row in cases
    )
    result = {
        "schema_version": 1,
        "status": "terminal",
        "device": torch.cuda.get_device_name(),
        "operation": "create_flashinfer_kv_indices_triton plus immediate SWAKVPool mapping consumer",
        "geometry": {
            "batch_size": 32,
            "window_tokens": 1024,
            "valid_indices": 32768,
            "page_size": 1,
            "index_dtype": "int64",
            "indptr_dtype": "int32",
        },
        "cases": cases,
        "stock": stock,
        "producer_fused": fused,
        "reduction_fraction": gain,
        "candidate_cuda_started": True,
        "complete_output_consumed": True,
        "pass": passed,
    }
    temporary = args.output.with_suffix(".part")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
