#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import pathlib
import statistics
import time
from typing import Any, Callable

import torch

import two_stage_local_attention as candidate


PINNED_SOURCE_SHA256 = "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def mark(path: pathlib.Path, **updates: Any) -> None:
    value = json.loads(path.read_text()) if path.exists() else {}
    value.update(updates)
    value["updated_unix_s"] = time.time()
    atomic_json(path, value)


def make_case(
    name: str,
    extend_lengths: list[int],
    prefix_lengths: list[int],
    seed: int,
) -> dict[str, Any]:
    if len(extend_lengths) != len(prefix_lengths):
        raise ValueError("case_batch_mismatch")
    torch.manual_seed(seed)
    device = torch.device("cuda")
    query_tokens = sum(extend_lengths)
    prefix_tokens = sum(prefix_lengths)
    cache_slots = prefix_tokens + 37
    q = torch.randn((query_tokens, 32, 256), device=device, dtype=torch.bfloat16) / math.sqrt(256)
    k = torch.randn((query_tokens, 16, 256), device=device, dtype=torch.bfloat16) / math.sqrt(256)
    v = torch.randn((query_tokens, 16, 256), device=device, dtype=torch.bfloat16)
    fp8 = getattr(torch, "float8_e5m2", None)
    if fp8 is None:
        raise RuntimeError("torch_float8_e5m2_unavailable")
    k_buffer = torch.randn((cache_slots, 16, 256), device=device, dtype=torch.bfloat16).to(fp8)
    v_buffer = torch.randn((cache_slots, 16, 256), device=device, dtype=torch.bfloat16).to(fp8)
    qo_indptr = torch.tensor(
        [0, *torch.tensor(extend_lengths).cumsum(0).tolist()],
        device=device,
        dtype=torch.int32,
    )
    kv_indptr = torch.tensor(
        [0, *torch.tensor(prefix_lengths).cumsum(0).tolist()],
        device=device,
        dtype=torch.int32,
    )
    permutation = torch.randperm(cache_slots, device=device, dtype=torch.int64)
    return {
        "name": name,
        "extend_lengths": extend_lengths,
        "prefix_lengths": prefix_lengths,
        "q": q,
        "k": k,
        "v": v,
        "control_o": torch.empty_like(q),
        "candidate_o": torch.empty_like(q),
        "residual": torch.randn_like(q),
        "k_buffer": k_buffer,
        "v_buffer": v_buffer,
        "qo_indptr": qo_indptr,
        "kv_indptr": kv_indptr,
        "kv_indices": permutation[:prefix_tokens],
    }


def call(module: Any, tensors: dict[str, Any], output: torch.Tensor) -> None:
    module.extend_attention_fwd(
        tensors["q"],
        tensors["k"],
        tensors["v"],
        output,
        tensors["k_buffer"],
        tensors["v_buffer"],
        tensors["qo_indptr"],
        tensors["kv_indptr"],
        tensors["kv_indices"],
        None,
        True,
        None,
        max(tensors["extend_lengths"]),
        1.0,
        1.0,
        sliding_window_size=1024,
    )


def timed_ms(function: Callable[[], None]) -> float:
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    function()
    end.record()
    end.synchronize()
    return float(start.elapsed_time(end))


def summary(samples: list[float]) -> dict[str, Any]:
    ordered = sorted(samples)
    return {
        "samples_ms": samples,
        "median_ms": statistics.median(samples),
        "minimum_ms": ordered[0],
        "maximum_ms": ordered[-1],
        "p90_ms": ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)],
    }


def oracle(tensors: dict[str, Any]) -> dict[str, Any]:
    control = tensors["control_o"].float()
    measured = tensors["candidate_o"].float()
    delta = measured - control
    relative_l2 = float(
        torch.linalg.vector_norm(delta)
        / torch.linalg.vector_norm(control).clamp_min(1.0e-12)
    )
    cosine = float(
        torch.nn.functional.cosine_similarity(
            control.flatten(), measured.flatten(), dim=0
        )
    )
    control_downstream = torch.nn.functional.rms_norm(
        control + tensors["residual"].float(), (256,)
    )
    candidate_downstream = torch.nn.functional.rms_norm(
        measured + tensors["residual"].float(), (256,)
    )
    downstream_delta = candidate_downstream - control_downstream
    return {
        "all_finite": bool(torch.isfinite(measured).all().item()),
        "relative_l2": relative_l2,
        "cosine": cosine,
        "max_abs_error": float(delta.abs().max()),
        "mean_abs_error": float(delta.abs().mean()),
        "downstream_relative_l2": float(
            torch.linalg.vector_norm(downstream_delta)
            / torch.linalg.vector_norm(control_downstream).clamp_min(1.0e-12)
        ),
        "downstream_cosine": float(
            torch.nn.functional.cosine_similarity(
                control_downstream.flatten(), candidate_downstream.flatten(), dim=0
            )
        ),
        "downstream_checksum": float(candidate_downstream.abs().sum()),
    }


def run_case(
    baseline: Any,
    tensors: dict[str, Any],
    warmups: int,
    iterations: int,
) -> dict[str, Any]:
    call(baseline, tensors, tensors["control_o"])
    call(candidate, tensors, tensors["candidate_o"])
    torch.cuda.synchronize()
    numerical = oracle(tensors)
    for _ in range(warmups):
        call(baseline, tensors, tensors["control_o"])
        call(candidate, tensors, tensors["candidate_o"])
    torch.cuda.synchronize()
    control_samples: list[float] = []
    candidate_samples: list[float] = []
    for index in range(iterations):
        ordered = (
            (
                (lambda: call(baseline, tensors, tensors["control_o"]), control_samples),
                (lambda: call(candidate, tensors, tensors["candidate_o"]), candidate_samples),
            )
            if index % 2 == 0
            else (
                (lambda: call(candidate, tensors, tensors["candidate_o"]), candidate_samples),
                (lambda: call(baseline, tensors, tensors["control_o"]), control_samples),
            )
        )
        for function, samples in ordered:
            samples.append(timed_ms(function))
    control = summary(control_samples)
    measured = summary(candidate_samples)
    max_len = max(tensors["extend_lengths"])
    return {
        "name": tensors["name"],
        "batch": len(tensors["extend_lengths"]),
        "extend_lengths": tensors["extend_lengths"],
        "prefix_lengths": tensors["prefix_lengths"],
        "control_grid": [len(tensors["extend_lengths"]), 32, math.ceil(max_len / 64)],
        "candidate_stage1_grid": [
            len(tensors["extend_lengths"]),
            32,
            math.ceil(max_len / 64),
        ],
        "candidate_stage2_grid": [
            len(tensors["extend_lengths"]),
            32,
            math.ceil(max_len / 64) * candidate.VALUE_SLICES,
        ],
        "workspace_bytes": candidate.workspace_bytes(
            len(tensors["extend_lengths"]), max_len
        ),
        "control": control,
        "candidate": measured,
        "latency_reduction_fraction": 1.0
        - measured["median_ms"] / control["median_ms"],
        "oracle": numerical,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=15)
    parser.add_argument("--seed", type=int, default=20260723)
    parser.add_argument("--profile-candidate", action="store_true")
    args = parser.parse_args()
    if not torch.cuda.is_available() or tuple(torch.cuda.get_device_capability()) != (9, 0):
        raise RuntimeError("exact_hopper_cuda_unavailable")
    if sha256(args.source) != PINNED_SOURCE_SHA256:
        raise RuntimeError(f"pinned_source_mismatch:{sha256(args.source)}")

    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation = args.artifact_root / "INVOCATION_STATE.json"
    baseline = importlib.import_module(
        "sglang.srt.layers.attention.triton_ops.extend_attention"
    )
    baseline_path = pathlib.Path(baseline.__file__).resolve()
    if sha256(baseline_path) != PINNED_SOURCE_SHA256:
        raise RuntimeError(f"loaded_baseline_source_mismatch:{sha256(baseline_path)}")
    mark(
        invocation,
        candidate_cuda_invocation_started=False,
        scientific_invocation_started=False,
        source_sha256=PINNED_SOURCE_SHA256,
        candidate_module_sha256=sha256(pathlib.Path(candidate.__file__).resolve()),
    )

    smoke = make_case("discovery_boundary", [65, 127], [1023, 1025], args.seed)
    mark(invocation, discovery_cuda_invocation_started=True)
    call(candidate, smoke, smoke["candidate_o"])
    torch.cuda.synchronize()
    if not torch.isfinite(smoke["candidate_o"]).all().item():
        raise RuntimeError("candidate_discovery_nonfinite")
    mark(
        invocation,
        discovery_cuda_invocation_completed=True,
        candidate_cuda_invocation_started=True,
        scientific_invocation_started=True,
    )

    cases = [
        run_case(baseline, smoke, args.warmups, args.iterations),
        run_case(
            baseline,
            make_case("observed_grid_z2", [128], [1024], args.seed + 1),
            args.warmups,
            args.iterations,
        ),
        run_case(
            baseline,
            make_case(
                "observed_grid_z32", [2048, 128], [1024, 1025], args.seed + 2
            ),
            args.warmups,
            args.iterations,
        ),
    ]
    if args.profile_candidate:
        profile_case = make_case(
            "profile_observed_grid_z32", [2048, 128], [1024, 1025], args.seed + 3
        )
        call(candidate, profile_case, profile_case["candidate_o"])
        torch.cuda.synchronize()
        mark(invocation, ncu_control_candidate_capture_started=True)
        torch.cuda.cudart().cudaProfilerStart()
        call(baseline, profile_case, profile_case["control_o"])
        torch.cuda.synchronize()
        call(candidate, profile_case, profile_case["candidate_o"])
        torch.cuda.synchronize()
        torch.cuda.cudart().cudaProfilerStop()
        mark(invocation, ncu_control_candidate_capture_completed=True)

    numerical_pass = all(
        row["oracle"]["all_finite"]
        and row["oracle"]["relative_l2"] <= 0.005
        and row["oracle"]["cosine"] >= 0.9999
        and row["oracle"]["downstream_checksum"] > 0
        for row in cases
    )
    observed = [row for row in cases if row["name"].startswith("observed_")]
    conservative_component_reduction = min(
        row["latency_reduction_fraction"] for row in observed
    )
    local_kernel_fraction = 0.1531203203096733
    whole_request_bound = conservative_component_reduction * local_kernel_fraction
    component_gate = numerical_pass and whole_request_bound >= 0.03
    device = torch.cuda.get_device_properties(0)
    terminal = {
        "schema_version": 2,
        "status": "component_pass" if component_gate else "component_reject",
        "component_pass": component_gate,
        "numerical_pass": numerical_pass,
        "cases": cases,
        "conservative_component_reduction_fraction": conservative_component_reduction,
        "local_kernel_wall_fraction": local_kernel_fraction,
        "whole_request_reduction_bound_fraction": whole_request_bound,
        "whole_request_gate_fraction": 0.03,
        "shape": {
            "q_heads": 32,
            "kv_heads": 16,
            "qk_head_dim": 256,
            "v_head_dim": 256,
            "sliding_window_size": 1024,
            "kv_cache_dtype": "fp8_e5m2",
            "block_m": candidate.BLOCK_M,
            "block_n": candidate.BLOCK_N,
            "key_tiles": candidate.KEY_TILES,
            "value_slices": candidate.VALUE_SLICES,
            "value_slice": candidate.BLOCK_DV_SLICE,
            "intermediate_dtype": "bfloat16",
        },
        "identity": {
            "baseline_source": str(baseline_path),
            "baseline_source_sha256": PINNED_SOURCE_SHA256,
            "candidate_module_sha256": sha256(
                pathlib.Path(candidate.__file__).resolve()
            ),
            "torch": torch.__version__,
            "triton": importlib.import_module("triton").__version__,
            "seed": args.seed,
        },
        "device": {
            "name": device.name,
            "capability": list(torch.cuda.get_device_capability()),
            "sm_count": device.multi_processor_count,
            "total_memory_bytes": device.total_memory,
        },
        "candidate_path": "extend_attention_fwd.local_head256_two_stage_blockprob_vslice2",
        "ncu_control_candidate_capture_requested": args.profile_candidate,
    }
    atomic_json(args.artifact_root / "COMPONENT_TERMINAL.json", terminal)
    mark(invocation, scientific_terminal_recorded=True)
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0 if component_gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
