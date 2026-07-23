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
from typing import Any

import torch


SOURCE_SHA256 = "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"
LOCAL_WALL_FRACTION = 0.1531203203096733


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def make_case(
    name: str, extend_lengths: list[int], prefix_lengths: list[int], seed: int
) -> dict[str, Any]:
    torch.manual_seed(seed)
    query_tokens = sum(extend_lengths)
    prefix_tokens = sum(prefix_lengths)
    cache_slots = prefix_tokens + 37
    fp8 = torch.float8_e5m2
    q = torch.randn(
        (query_tokens, 32, 256), device="cuda", dtype=torch.bfloat16
    ) / math.sqrt(256)
    k = torch.randn(
        (query_tokens, 16, 256), device="cuda", dtype=torch.bfloat16
    ) / math.sqrt(256)
    v = torch.randn(
        (query_tokens, 16, 256), device="cuda", dtype=torch.bfloat16
    )
    k_buffer = torch.randn(
        (cache_slots, 16, 256), device="cuda", dtype=torch.bfloat16
    ).to(fp8)
    v_buffer = torch.randn(
        (cache_slots, 16, 256), device="cuda", dtype=torch.bfloat16
    ).to(fp8)
    qo_indptr = torch.tensor(
        [0, *torch.tensor(extend_lengths).cumsum(0).tolist()],
        device="cuda",
        dtype=torch.int32,
    )
    kv_indptr = torch.tensor(
        [0, *torch.tensor(prefix_lengths).cumsum(0).tolist()],
        device="cuda",
        dtype=torch.int32,
    )
    kv_indices = torch.randperm(
        cache_slots, device="cuda", dtype=torch.int64
    )[:prefix_tokens]
    return {
        "name": name,
        "extend_lengths": extend_lengths,
        "prefix_lengths": prefix_lengths,
        "q": q,
        "k": k,
        "v": v,
        "k_buffer": k_buffer,
        "v_buffer": v_buffer,
        "qo_indptr": qo_indptr,
        "kv_indptr": kv_indptr,
        "kv_indices": kv_indices,
        "control_o": torch.empty_like(q),
        "candidate_o": torch.empty_like(q),
    }


def invoke(
    module: Any, tensors: dict[str, Any], output: torch.Tensor, window: int
) -> None:
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
        sliding_window_size=window,
    )


def reference_512(tensors: dict[str, Any], query_block: int = 32) -> torch.Tensor:
    output = torch.empty_like(tensors["candidate_o"])
    query_offset = 0
    prefix_offset = 0
    fp8 = torch.float8_e5m2
    group_size = 2
    scale = 1 / math.sqrt(256)
    for prefix_length, extend_length in zip(
        tensors["prefix_lengths"], tensors["extend_lengths"]
    ):
        q = tensors["q"][query_offset : query_offset + extend_length]
        k_extend = tensors["k"][query_offset : query_offset + extend_length]
        v_extend = tensors["v"][query_offset : query_offset + extend_length]
        indices = tensors["kv_indices"][
            prefix_offset : prefix_offset + prefix_length
        ]
        k_prefix = tensors["k_buffer"][indices]
        v_prefix = tensors["v_buffer"][indices]
        for start in range(0, extend_length, query_block):
            stop = min(extend_length, start + query_block)
            absolute_queries = prefix_length + torch.arange(
                start, stop, device="cuda"
            )
            key_start = max(0, prefix_length + start - 512)
            key_stop = prefix_length + stop
            prefix_start = min(key_start, prefix_length)
            prefix_stop = min(key_stop, prefix_length)
            extend_start = max(0, key_start - prefix_length)
            extend_stop = max(0, key_stop - prefix_length)
            score_parts = []
            value_parts = []
            absolute_key_parts = []
            q_block = q[start:stop]
            if prefix_start < prefix_stop:
                prefix_k = (
                    k_prefix[prefix_start:prefix_stop]
                    .repeat_interleave(group_size, dim=1)
                    .permute(1, 0, 2)
                    .float()
                )
                q_prefix = q_block.to(fp8).float()
                score_parts.append(
                    torch.einsum("qhd,hkd->qhk", q_prefix, prefix_k) * scale
                )
                value_parts.append(
                    v_prefix[prefix_start:prefix_stop]
                    .repeat_interleave(group_size, dim=1)
                    .permute(1, 0, 2)
                    .float()
                )
                absolute_key_parts.append(
                    torch.arange(prefix_start, prefix_stop, device="cuda")
                )
            if extend_start < extend_stop:
                extend_k = (
                    k_extend[extend_start:extend_stop]
                    .repeat_interleave(group_size, dim=1)
                    .permute(1, 0, 2)
                    .float()
                )
                score_parts.append(
                    torch.einsum("qhd,hkd->qhk", q_block.float(), extend_k)
                    * scale
                )
                value_parts.append(
                    v_extend[extend_start:extend_stop]
                    .repeat_interleave(group_size, dim=1)
                    .permute(1, 0, 2)
                    .float()
                )
                absolute_key_parts.append(
                    prefix_length
                    + torch.arange(extend_start, extend_stop, device="cuda")
                )
            scores = torch.cat(score_parts, dim=-1)
            values = torch.cat(value_parts, dim=1)
            absolute_keys = torch.cat(absolute_key_parts)
            mask = (absolute_keys[None, :] <= absolute_queries[:, None]) & (
                absolute_keys[None, :] >= absolute_queries[:, None] - 512
            )
            probability = torch.softmax(
                scores.masked_fill(~mask[:, None, :], -torch.inf), dim=-1
            )
            prefix_width = max(0, prefix_stop - prefix_start)
            result = torch.zeros(
                (stop - start, 32, 256), device="cuda", dtype=torch.float32
            )
            if prefix_width:
                result += torch.einsum(
                    "qhk,hkd->qhd",
                    probability[:, :, :prefix_width].to(fp8).float(),
                    values[:, :prefix_width],
                )
            if prefix_width < probability.shape[-1]:
                result += torch.einsum(
                    "qhk,hkd->qhd",
                    probability[:, :, prefix_width:].to(torch.bfloat16).float(),
                    values[:, prefix_width:],
                )
            output[query_offset + start : query_offset + stop] = result.to(
                torch.bfloat16
            )
        query_offset += extend_length
        prefix_offset += prefix_length
    return output


def timed_ms(function) -> float:
    start = torch.cuda.Event(enable_timing=True)
    stop = torch.cuda.Event(enable_timing=True)
    start.record()
    function()
    stop.record()
    stop.synchronize()
    return float(start.elapsed_time(stop))


def distribution(samples: list[float]) -> dict[str, Any]:
    ordered = sorted(samples)
    return {
        "samples_ms": samples,
        "median_ms": statistics.median(samples),
        "minimum_ms": ordered[0],
        "maximum_ms": ordered[-1],
        "p90_ms": ordered[math.ceil(0.9 * len(ordered)) - 1],
    }


def run_case(
    module: Any,
    tensors: dict[str, Any],
    warmups: int,
    iterations: int,
) -> dict[str, Any]:
    invoke(module, tensors, tensors["control_o"], 1024)
    invoke(module, tensors, tensors["candidate_o"], 512)
    torch.cuda.synchronize()
    reference = reference_512(tensors)
    candidate = tensors["candidate_o"].float()
    delta = candidate - reference.float()
    numerical = {
        "all_finite": bool(torch.isfinite(candidate).all().item()),
        "relative_l2": float(
            torch.linalg.vector_norm(delta)
            / torch.linalg.vector_norm(reference.float()).clamp_min(1e-12)
        ),
        "cosine": float(
            torch.nn.functional.cosine_similarity(
                candidate.flatten(), reference.float().flatten(), dim=0
            )
        ),
        "max_abs_error": float(delta.abs().max()),
        "mean_abs_error": float(delta.abs().mean()),
        "output_shape": list(tensors["candidate_o"].shape),
        "reference_shape": list(reference.shape),
    }
    for _ in range(warmups):
        invoke(module, tensors, tensors["control_o"], 1024)
        invoke(module, tensors, tensors["candidate_o"], 512)
    control_samples = []
    candidate_samples = []
    for index in range(iterations):
        calls = (
            ((1024, tensors["control_o"], control_samples), (512, tensors["candidate_o"], candidate_samples))
            if index % 2 == 0
            else ((512, tensors["candidate_o"], candidate_samples), (1024, tensors["control_o"], control_samples))
        )
        for window, output, samples in calls:
            samples.append(timed_ms(lambda w=window, o=output: invoke(module, tensors, o, w)))
    control = distribution(control_samples)
    measured = distribution(candidate_samples)
    return {
        "name": tensors["name"],
        "extend_lengths": tensors["extend_lengths"],
        "prefix_lengths": tensors["prefix_lengths"],
        "control_window_tokens": 1024,
        "candidate_window_tokens": 512,
        "control": control,
        "candidate": measured,
        "latency_reduction_fraction": 1 - measured["median_ms"] / control["median_ms"],
        "numerical_512_reference": numerical,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--warmups", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=11)
    parser.add_argument("--seed", type=int, default=20260723)
    args = parser.parse_args()
    if not torch.cuda.is_available() or tuple(torch.cuda.get_device_capability()) != (9, 0):
        raise RuntimeError("exact_hopper_cuda_unavailable")
    module = importlib.import_module(
        "sglang.srt.layers.attention.triton_ops.extend_attention"
    )
    source = pathlib.Path(module.__file__).resolve()
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != SOURCE_SHA256:
        raise RuntimeError(f"pinned_source_mismatch:{actual}")
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation = args.artifact_root / "INVOCATION_STATE.json"
    atomic_json(
        invocation,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": False,
            "scientific_invocation_started": False,
            "source_sha256": actual,
            "updated_unix_s": time.time(),
        },
    )
    smoke = make_case("boundary", [65, 127], [1023, 1025], args.seed)
    invoke(module, smoke, smoke["candidate_o"], 512)
    torch.cuda.synchronize()
    atomic_json(
        invocation,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": True,
            "scientific_invocation_started": True,
            "source_sha256": actual,
            "updated_unix_s": time.time(),
        },
    )
    cases = [
        run_case(module, smoke, args.warmups, args.iterations),
        run_case(
            module,
            make_case("observed_grid_z2", [128], [1024], args.seed + 1),
            args.warmups,
            args.iterations,
        ),
        run_case(
            module,
            make_case(
                "observed_grid_z32", [2048, 128], [1024, 1025], args.seed + 2
            ),
            args.warmups,
            args.iterations,
        ),
    ]
    numerical_pass = all(
        row["numerical_512_reference"]["all_finite"]
        and row["numerical_512_reference"]["relative_l2"] <= 0.02
        and row["numerical_512_reference"]["cosine"] >= 0.999
        and row["numerical_512_reference"]["output_shape"]
        == row["numerical_512_reference"]["reference_shape"]
        for row in cases
    )
    observed = {row["name"]: row for row in cases}
    call_weighted_reduction = (
        0.008214016
        * observed["observed_grid_z2"]["latency_reduction_fraction"]
        + 3.358076267
        * observed["observed_grid_z32"]["latency_reduction_fraction"]
    ) / 3.366290283
    whole_request_estimate = call_weighted_reduction * LOCAL_WALL_FRACTION
    terminal = {
        "schema_version": 1,
        "status": "component_pass" if numerical_pass else "numerical_negative",
        "component_pass": numerical_pass,
        "numerical_pass": numerical_pass,
        "cases": cases,
        "call_weighted_component_reduction_fraction": call_weighted_reduction,
        "estimated_whole_request_reduction_fraction": whole_request_estimate,
        "measured_local_kernel_wall_fraction": LOCAL_WALL_FRACTION,
        "path_proof": {
            "candidate_path": "extend_attention_fwd._fwd_kernel.SLIDING_WINDOW_SIZE_512",
            "control_window_tokens": 1024,
            "candidate_window_tokens": 512,
            "q_heads": 32,
            "kv_heads": 16,
            "qk_head_dim": 256,
            "v_head_dim": 256,
            "kv_dtype": "fp8_e5m2",
            "source": str(source),
            "source_sha256": actual,
            "fallback_window_1024_in_candidate": False,
        },
        "device": {
            "name": torch.cuda.get_device_name(),
            "capability": list(torch.cuda.get_device_capability()),
            "sm_count": torch.cuda.get_device_properties(0).multi_processor_count,
        },
        "identity": {
            "torch": torch.__version__,
            "triton": importlib.import_module("triton").__version__,
            "seed": args.seed,
        },
    }
    atomic_json(args.artifact_root / "COMPONENT_TERMINAL.json", terminal)
    invocation_state = json.loads(invocation.read_text())
    invocation_state["scientific_terminal_recorded"] = True
    invocation_state["updated_unix_s"] = time.time()
    atomic_json(invocation, invocation_state)
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0 if numerical_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
