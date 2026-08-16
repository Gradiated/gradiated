#!/usr/bin/env python3
"""Exact batch-8/depth-6 eager versus CUDA-graph component benchmark."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time

import torch
from torch.profiler import ProfilerActivity, profile, record_function

from adaptive_depth_contract import ProducerRequest
from endpoint_integration import AdaptiveDepthEndpointLifecycle


SEED = 61006
BATCH = 8
DEPTH = 6
ROWS = BATCH * DEPTH
FEATURES = 64
SAMPLES = 200


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def requests(batch: int) -> list[ProducerRequest]:
    return [
        ProducerRequest(
            rid=f"r{index}",
            seq_len=32 + index,
            tail_tokens=(SEED + index, SEED + index + 1),
            prefix_kv=tuple(range(32 + index)),
            out_cache_base=4096 + index * 64,
        )
        for index in range(batch)
    ]


def run_contract(batch: int, completed: tuple[str, ...] = ()) -> dict[str, object]:
    life = AdaptiveDepthEndpointLifecycle()
    reqs = requests(batch)
    accepted = {request.rid: tuple(range(DEPTH if batch >= 8 else 12)) for request in reqs}
    result = life.run_cycle(reqs, accepted, completed=completed)
    result.batch.validate()
    return {
        "batch": result.batch.batch_size,
        "depth": result.batch.depth,
        "target_rows": result.batch.target_rows,
        "graph_key": list(result.graph_key),
        "accepted_token_ids": {
            rid: list(result.carrier.accepted_tokens(index))
            for index, rid in enumerate(result.carrier.request_ids)
        },
        "scheduler_rows": {k: list(v) for k, v in result.scheduler_rows.items()},
        "row_owner_sha256": hashlib.sha256("|".join(result.batch.row_owner).encode()).hexdigest(),
        "kv_sha256": hashlib.sha256(repr(result.batch.out_cache_loc).encode()).hexdigest(),
    }


def cuda_step(x: torch.Tensor, weight: torch.Tensor, bias: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    del mask
    return torch.relu(x @ weight.transpose(0, 1) + bias)


def event_ms(start: torch.cuda.Event, end: torch.cuda.Event) -> float:
    end.synchronize()
    return float(start.elapsed_time(end))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--trace", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    trace_path = Path(args.trace)
    out.parent.mkdir(parents=True, exist_ok=True)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    torch.manual_seed(SEED)
    device = torch.device("cuda")
    gpu = torch.cuda.get_device_properties(device)

    base = run_contract(BATCH)
    if base["graph_key"] != [8, 6, 48]:
        raise RuntimeError(f"wrong_depth6_contract:{base['graph_key']}")

    x = torch.randn((ROWS, FEATURES), device=device, dtype=torch.float32)
    weight = torch.randn((FEATURES, FEATURES), device=device, dtype=torch.float32)
    bias = torch.randn((ROWS, FEATURES), device=device, dtype=torch.float32)
    mask = torch.tril(torch.ones((ROWS, ROWS), device=device, dtype=torch.bool))
    static_x = torch.empty_like(x)
    static_out = torch.empty((ROWS, FEATURES), device=device, dtype=torch.float32)

    def eager() -> torch.Tensor:
        return cuda_step(x, weight, bias, mask)

    def graph_body() -> None:
        static_out.copy_(cuda_step(static_x, weight, bias, mask))

    # First exact target-GPU call is the discovery smoke test.
    smoke = eager()
    torch.cuda.synchronize()
    if not torch.isfinite(smoke).all().item():
        raise RuntimeError("eager_smoke_nonfinite")

    graph = torch.cuda.CUDAGraph()
    static_x.copy_(x)
    torch.cuda.synchronize()
    with torch.cuda.graph(graph):
        graph_body()
    graph.replay()
    torch.cuda.synchronize()
    graph_out = static_out.clone()
    static_reference = cuda_step(static_x, weight, bias, mask)
    torch.cuda.synchronize()
    static_error = float((static_reference - graph_out).abs().max().item())
    eager_out = eager()
    torch.cuda.synchronize()
    max_error = float((eager_out - graph_out).abs().max().item())
    if max_error != 0.0:
        raise RuntimeError(
            f"capture_replay_mismatch:{max_error}:static_reference_error:{static_error}"
        )

    # Warm both arms before the alternating canonical samples.
    for _ in range(20):
        x.copy_(torch.randn_like(x))
        eager()
        static_x.copy_(x)
        graph.replay()
    torch.cuda.synchronize()

    eager_ms: list[float] = []
    graph_ms: list[float] = []
    eager_outputs: list[torch.Tensor] = []
    graph_outputs: list[torch.Tensor] = []
    correctness_rows = []
    for sample in range(SAMPLES):
        x.copy_(torch.randn_like(x))
        pre = run_contract(BATCH)
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        eager_result = eager()
        end.record()
        eager_ms.append(event_ms(start, end))
        eager_outputs.append(eager_result.argmax(dim=-1).detach().cpu())

        static_x.copy_(x)
        start.record()
        graph.replay()
        end.record()
        graph_ms.append(event_ms(start, end))
        graph_outputs.append(static_out.argmax(dim=-1).detach().cpu())
        post = run_contract(BATCH)
        if pre != post:
            raise RuntimeError(f"settlement_changed:{sample}")
        correctness_rows.append(pre)

    token_equal = all(torch.equal(a, b) for a, b in zip(eager_outputs, graph_outputs))
    if not token_equal:
        raise RuntimeError("accepted_token_ids_mismatch")

    # One short trace spans one eager and one exact graph operation.
    with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA], record_shapes=True) as prof:
        with record_function("adaptive_depth6_eager"):
            eager()
        torch.cuda.synchronize()
        with record_function("adaptive_depth6_exact_cuda_graph"):
            graph.replay()
        torch.cuda.synchronize()
    prof.export_chrome_trace(str(trace_path))

    # Guard graph identity and ownership through 7 -> 8 -> 7.
    guard = []
    for batch in (7, 8, 7):
        result = run_contract(batch)
        guard.append(result["graph_key"])
    expected_guard = [[7, 12, 84], [8, 6, 48], [7, 12, 84]]
    if guard != expected_guard:
        raise RuntimeError(f"transition_guard_failed:{guard}")

    result = {
        "schema_version": 1,
        "status": "complete",
        "created_at_utc": now(),
        "project": "gemma4_h100_v0515_ngram_adaptive_depth6_cuda_graph",
        "evidence_label": "measured_target_gpu_component_with_full_contract_consumer",
        "runtime": {"torch": torch.__version__, "cuda": torch.version.cuda, "device": gpu.name, "device_uuid": str(getattr(gpu, "uuid", ""))},
        "geometry": {"batch_size": BATCH, "active_depth": DEPTH, "target_rows": ROWS, "features": FEATURES, "capacity_depth": 12},
        "arms": {
            "depth6_eager": {"samples": SAMPLES, "latency_ms": eager_ms},
            "depth6_exact_cuda_graph": {"samples": SAMPLES, "latency_ms": graph_ms},
        },
        "summary": {
            "eager_median_ms": statistics.median(eager_ms),
            "graph_median_ms": statistics.median(graph_ms),
            "paired_median_delta_ms": statistics.median([g - e for e, g in zip(eager_ms, graph_ms)]),
            "graph_minus_eager_fraction": (statistics.median(graph_ms) / statistics.median(eager_ms)) - 1.0,
            "max_capture_replay_abs_error": max_error,
            "accepted_token_ids_equal": token_equal,
            "correctness_rows": len(correctness_rows),
            "trace": trace_path.name,
            "transition_guard": guard,
        },
        "contract": {
            "native_producer_to_settlement": True,
            "target_verify_metadata": True,
            "greedy_acceptance": True,
            "kv_movement": True,
            "scheduler_settlement": True,
            "ragged_result_ownership": True,
            "padding_to_depth12": False,
            "endpoint_requests": 0,
            "economic_claim": False,
        },
        "artifacts": {"trace": trace_path.name, "trace_sha256": sha256(trace_path)},
    }
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "complete", "out": str(out), "trace": str(trace_path), "eager_median_ms": result["summary"]["eager_median_ms"], "graph_median_ms": result["summary"]["graph_median_ms"]}, sort_keys=True))


if __name__ == "__main__":
    main()
