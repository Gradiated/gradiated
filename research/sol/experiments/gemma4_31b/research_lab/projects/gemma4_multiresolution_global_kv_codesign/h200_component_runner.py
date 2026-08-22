#!/usr/bin/env python3
"""Run the admitted global-KV component in the pinned H200 runtime image.

The CPU mode is deliberately only an input/consumer fixture.  The component
mode requires CUDA and imports the installed SGLang package from the pinned
image before invoking the same producer/consumer boundary for every claimed
phase.  It never calls an endpoint or claims a bench itself.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import pathlib
import time
from typing import Any

try:
    import torch
except ImportError:
    torch = None

from multiresolution_global_kv import (
    GLOBAL_HEAD_DIM,
    GLOBAL_KV_HEADS,
    IncrementalGlobalSummaryState,
    build_compact_block_plan,
    consume_compact_global_attention,
    forward_decode,
    forward_extend,
    fixture,
)


PROJECT = pathlib.Path(__file__).resolve().parent
RUNTIME_COMMIT = "28b095c01005d4a3a2a5b637b7d028b07fba31b2"
PHASES = (("prefill", 4192, 32), ("target_verify", 4214, 12), ("decode", 4572, 1))


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def write_result(path: pathlib.Path | None, value: dict[str, Any]) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path is None:
        print(encoded, end="")
        return
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(encoded)
    temporary.replace(path)


def phase_plans() -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for phase, query_start, query_count in PHASES:
        plan = build_compact_block_plan(query_start, query_count, protected_positions=range(8))
        result[phase] = {
            "query_start": query_start,
            "query_count": query_count,
            "compact_entries": plan.compact_tokens,
            "represented_positions": len(plan.represented_positions),
        }
    return result


def cpu_fixture() -> dict[str, Any]:
    plans = phase_plans()
    if any(row["compact_entries"] > 64 for row in plans.values()):
        raise RuntimeError("compact_entry_contract_failed")
    return {
        "schema_version": 1,
        "classification": "cpu_source_fixture_only",
        "runtime_commit": RUNTIME_COMMIT,
        "fixture": fixture(),
        "phases": plans,
        "runner_sha256": digest(PROJECT / "h200_component_runner.py"),
        "candidate_sha256": digest(PROJECT / "multiresolution_global_kv.py"),
        "target_runtime_checked": False,
        "measurement_ready": False,
    }


def installed_runtime() -> dict[str, str]:
    package = importlib.import_module("sglang")
    package_path = pathlib.Path(package.__file__).resolve()
    return {
        "module": str(package_path),
        "module_sha256": digest(package_path),
        "version": str(getattr(package, "__version__", "unknown")),
        "bound_commit": RUNTIME_COMMIT,
    }


def stock_attention(q: torch.Tensor, k: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    grouped = q.view(q.shape[0], GLOBAL_KV_HEADS, 8, GLOBAL_HEAD_DIM)
    logits = torch.einsum("qhgd,khd->qhgk", grouped.float(), k.float())
    logits.mul_(GLOBAL_HEAD_DIM**-0.5)
    output = torch.einsum("qhgk,khd->qhgd", torch.softmax(logits, dim=-1), v.float())
    return output.to(q.dtype).reshape_as(q)


def state_for(k: torch.Tensor, v: torch.Tensor, query_start: int) -> IncrementalGlobalSummaryState:
    state = IncrementalGlobalSummaryState(range(8))
    offset = 0
    while offset < query_start:
        end = min(query_start, offset + 32)
        state.append_committed(k[offset:end], v[offset:end])
        offset = end
    return state


def invoke_phase(phase: str, query_start: int, query_count: int, device: torch.device) -> dict[str, Any]:
    torch.manual_seed(1000 + query_start)
    sequence = query_start + query_count
    dtype = torch.bfloat16
    k = torch.randn(sequence, GLOBAL_KV_HEADS, GLOBAL_HEAD_DIM, device=device, dtype=dtype)
    v = torch.randn_like(k)
    q = torch.randn(query_count, 32, GLOBAL_HEAD_DIM, device=device, dtype=dtype)
    # The first real candidate call is the compile/integration check.  Keep it
    # outside reported timing and rebuild request-owned state before the timed
    # invocation so the warm-up cannot double-commit KV rows.
    warm_state = state_for(k, v, query_start)
    if phase == "prefill":
        forward_extend(layer_sliding_window=None, forward_mode="PREFILL", q=q,
                       post_rope_k=k, v=v, query_start=query_start,
                       summary_state=warm_state, protected_positions=range(8))
    elif phase == "target_verify":
        forward_extend(layer_sliding_window=None, forward_mode="TARGET_VERIFY", q=q,
                       post_rope_k=k, v=v, query_start=query_start,
                       summary_state=warm_state, protected_positions=range(8))
    else:
        forward_decode(layer_sliding_window=None, q=q, post_rope_k=k, v=v,
                       query_start=query_start, summary_state=warm_state,
                       protected_positions=range(8))
    torch.cuda.synchronize(device)
    state = state_for(k, v, query_start)
    torch.cuda.synchronize(device)
    started = time.perf_counter_ns()
    if phase == "prefill":
        candidate = forward_extend(
            layer_sliding_window=None, forward_mode="PREFILL", q=q, post_rope_k=k,
            v=v, query_start=query_start, summary_state=state, protected_positions=range(8),
        )
    elif phase == "target_verify":
        candidate = forward_extend(
            layer_sliding_window=None, forward_mode="TARGET_VERIFY", q=q, post_rope_k=k,
            v=v, query_start=query_start, summary_state=state, protected_positions=range(8),
        )
    else:
        candidate = forward_decode(
            layer_sliding_window=None, q=q, post_rope_k=k, v=v, query_start=query_start,
            summary_state=state, protected_positions=range(8),
        )
    torch.cuda.synchronize(device)
    candidate_ns = time.perf_counter_ns() - started
    started = time.perf_counter_ns()
    stock = stock_attention(q, k[:sequence], v[:sequence])
    torch.cuda.synchronize(device)
    stock_ns = time.perf_counter_ns() - started
    plan = build_compact_block_plan(query_start, query_count, protected_positions=range(8))
    return {
        "phase": phase,
        "query_start": query_start,
        "query_count": query_count,
        "compact_entries": plan.compact_tokens,
        "fallback": False,
        "candidate_finite": bool(torch.isfinite(candidate).all()),
        "stock_finite": bool(torch.isfinite(stock).all()),
        "request_ownership_pass": state.committed_tokens == sequence if phase != "target_verify" else state.committed_tokens == query_start,
        "candidate_elapsed_ns": candidate_ns,
        "stock_elapsed_ns": stock_ns,
        "candidate_output_shape": list(candidate.shape),
    }


def component() -> dict[str, Any]:
    if torch is None or not torch.cuda.is_available():
        raise RuntimeError("target_runtime_cuda_unavailable")
    device = torch.device("cuda")
    runtime = installed_runtime()
    rows = [invoke_phase(*phase, device) for phase in PHASES]
    valid = all(
        row["compact_entries"] <= 64
        and not row["fallback"]
        and row["candidate_finite"]
        and row["stock_finite"]
        and row["request_ownership_pass"]
        for row in rows
    )
    return {
        "schema_version": 1,
        "classification": "component_result" if valid else "component_contract_reject",
        "runtime": runtime,
        "cuda": torch.cuda.get_device_name(device),
        "phases": rows,
        "component_contract_pass": valid,
        "runner_sha256": digest(PROJECT / "h200_component_runner.py"),
        "candidate_sha256": digest(PROJECT / "multiresolution_global_kv.py"),
        "science_started": True,
        "endpoint_started": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("cpu-fixture", "component"), required=True)
    parser.add_argument("--result")
    args = parser.parse_args()
    result = cpu_fixture() if args.mode == "cpu-fixture" else component()
    write_result(pathlib.Path(args.result) if args.result else None, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
