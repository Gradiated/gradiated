#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import math
import os
import pathlib
import statistics
import time
from typing import Any

import torch


SOURCE_SHA256 = "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"
TARGET_GPU_UNION_US = 2_216_848.006591797
ATTENTION_US = 1_488_205.758
BATCH = 32
DRAFT = 12
PREFIX = 4214
LOCAL_PREFIX = 1024
Q_HEADS = 32


def atomic(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("fixed_m384_extend_attention", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("candidate_module_spec_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def distribution(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "samples_ms": values,
        "minimum_ms": ordered[0],
        "median_ms": statistics.median(values),
        "p90_ms": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "maximum_ms": ordered[-1],
    }


def timed_ms(fn) -> float:
    begin = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    begin.record()
    fn()
    end.record()
    end.synchronize()
    return float(begin.elapsed_time(end))


def make_tensors(
    seed: int, *, head_dim: int, kv_heads: int
) -> dict[str, torch.Tensor]:
    torch.manual_seed(seed)
    device = "cuda"
    tokens = BATCH * DRAFT
    total_pages = BATCH * PREFIX
    q = torch.randn((tokens, Q_HEADS, head_dim), device=device, dtype=torch.bfloat16)
    k = torch.randn((tokens, kv_heads, head_dim), device=device, dtype=torch.bfloat16)
    v = torch.randn((tokens, kv_heads, head_dim), device=device, dtype=torch.bfloat16)
    fp8 = torch.float8_e5m2
    k_buffer = torch.randn(
        (total_pages, kv_heads, head_dim), device=device, dtype=torch.bfloat16
    ).to(fp8)
    v_buffer = torch.randn(
        (total_pages, kv_heads, head_dim), device=device, dtype=torch.bfloat16
    ).to(fp8)
    pages = torch.randperm(total_pages, device=device, dtype=torch.int64).view(
        BATCH, PREFIX
    )
    qo_indptr = torch.arange(
        0, (BATCH + 1) * DRAFT, DRAFT, device=device, dtype=torch.int32
    )
    global_indptr = torch.arange(
        0, (BATCH + 1) * PREFIX, PREFIX, device=device, dtype=torch.int32
    )
    local_indptr = torch.arange(
        0,
        (BATCH + 1) * LOCAL_PREFIX,
        LOCAL_PREFIX,
        device=device,
        dtype=torch.int32,
    )
    tree = torch.zeros((DRAFT, DRAFT), device=device, dtype=torch.bool)
    for row in range(DRAFT):
        tree[row, row] = True
        tree[row, 0] = True
        for column in range(1, row):
            tree[row, column] = column % 3 == row % 3
    masks = []
    for _ in range(BATCH):
        prefix = torch.ones((DRAFT, PREFIX), device=device, dtype=torch.bool)
        masks.append(torch.cat((prefix, tree), dim=1).flatten())
    custom_mask = torch.cat(masks)
    mask_stride = DRAFT * (PREFIX + DRAFT)
    mask_indptr = torch.arange(
        0, (BATCH + 1) * mask_stride, mask_stride, device=device, dtype=torch.int32
    )
    return {
        "q": q,
        "k": k,
        "v": v,
        "k_buffer": k_buffer,
        "v_buffer": v_buffer,
        "qo_indptr": qo_indptr,
        "global_indptr": global_indptr,
        "local_indptr": local_indptr,
        "global_indices": pages.flatten().contiguous(),
        "local_indices": pages[:, -LOCAL_PREFIX:].flatten().contiguous(),
        "custom_mask": custom_mask,
        "mask_indptr": mask_indptr,
        "window_offsets": torch.full(
            (BATCH,), PREFIX - LOCAL_PREFIX, device=device, dtype=torch.int32
        ),
    }


def invoke(
    module: Any,
    tensors: dict[str, torch.Tensor],
    output: torch.Tensor,
    local: bool,
    head_dim: int,
) -> None:
    module.extend_attention_fwd(
        tensors["q"],
        tensors["k"],
        tensors["v"],
        output,
        tensors["k_buffer"],
        tensors["v_buffer"],
        tensors["qo_indptr"],
        tensors["local_indptr"] if local else tensors["global_indptr"],
        tensors["local_indices"] if local else tensors["global_indices"],
        tensors["custom_mask"],
        True,
        tensors["mask_indptr"],
        DRAFT,
        1.0,
        1.0,
        1 / math.sqrt(head_dim),
        sliding_window_size=1024 if local else -1,
        window_kv_offsets=tensors["window_offsets"] if local else None,
    )


def captured_invocation(
    module: Any,
    tensors: dict[str, torch.Tensor],
    output: torch.Tensor,
    local: bool,
    head_dim: int,
):
    invoke(module, tensors, output, local, head_dim)
    torch.cuda.synchronize()
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        invoke(module, tensors, output, local, head_dim)
    graph.replay()
    torch.cuda.synchronize()
    return graph.replay


def row(
    control: Any,
    candidate: Any,
    tensors: dict[str, torch.Tensor],
    local: bool,
    head_dim: int,
    kv_heads: int,
    warmups: int,
    iterations: int,
) -> dict[str, Any]:
    control_output = torch.empty_like(tensors["q"])
    candidate_output = torch.empty_like(tensors["q"])
    control_replay = captured_invocation(
        control, tensors, control_output, local, head_dim
    )
    candidate_replay = captured_invocation(
        candidate, tensors, candidate_output, local, head_dim
    )
    control_replay()
    candidate_replay()
    torch.cuda.synchronize()
    delta = candidate_output.float() - control_output.float()
    candidate_first = candidate_output.clone()
    candidate_replay()
    torch.cuda.synchronize()
    different = candidate_output != control_output
    different_flat = torch.nonzero(different.flatten(), as_tuple=False).flatten()
    first_differences = []
    for flat_index in different_flat[:16].tolist():
        token_head = Q_HEADS * head_dim
        token = flat_index // token_head
        remainder = flat_index % token_head
        head = remainder // head_dim
        feature = remainder % head_dim
        first_differences.append(
            {
                "coordinate": [token, head, feature],
                "control": float(control_output[token, head, feature]),
                "candidate": float(candidate_output[token, head, feature]),
                "absolute_error": float(delta[token, head, feature].abs()),
            }
        )
    oracle = {
        "all_finite": bool(torch.isfinite(candidate_output).all().item()),
        "bit_exact": bool(torch.equal(candidate_output, control_output)),
        "differing_elements": int(different.sum().item()),
        "first_differences": first_differences,
        "allclose_atol_0_02_rtol_0_005": bool(
            torch.allclose(
                candidate_output.float(),
                control_output.float(),
                atol=0.02,
                rtol=0.005,
            )
        ),
        "candidate_graph_replay_bitwise": bool(
            torch.equal(candidate_first, candidate_output)
        ),
        "max_abs_error": float(delta.abs().max()),
        "mean_abs_error": float(delta.abs().mean()),
        "relative_l2": float(
            torch.linalg.vector_norm(delta)
            / torch.linalg.vector_norm(control_output.float()).clamp_min(1e-12)
        ),
        "control_output_l1": float(control_output.float().abs().sum()),
        "candidate_output_l1": float(candidate_output.float().abs().sum()),
    }
    for _ in range(warmups):
        control_replay()
        candidate_replay()
    torch.cuda.synchronize()
    control_values: list[float] = []
    candidate_values: list[float] = []
    for index in range(iterations):
        order = (
            ((control_replay, control_values), (candidate_replay, candidate_values))
            if index % 2 == 0
            else ((candidate_replay, candidate_values), (control_replay, control_values))
        )
        for replay, values in order:
            values.append(timed_ms(replay))
    control_dist = distribution(control_values)
    candidate_dist = distribution(candidate_values)
    split_reductions = []
    for parity in (0, 1):
        split_control = statistics.median(control_values[parity::2])
        split_candidate = statistics.median(candidate_values[parity::2])
        split_reductions.append(1 - split_candidate / split_control)
    return {
        "layer_type": "sliding_window_1024" if local else "full_attention",
        "head_dim": head_dim,
        "kv_heads": kv_heads,
        "prefix_tokens_consumed": LOCAL_PREFIX if local else PREFIX,
        "original_sequence_tokens": PREFIX,
        "window_offset": PREFIX - LOCAL_PREFIX if local else 0,
        "control": control_dist,
        "candidate": candidate_dist,
        "latency_reduction_fraction": (
            1 - candidate_dist["median_ms"] / control_dist["median_ms"]
        ),
        "split_latency_reduction_fractions": split_reductions,
        "oracle": oracle,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--candidate", type=pathlib.Path, required=True)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260724)
    parser.add_argument("--counter-only", action="store_true")
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation = args.artifact_root / "INVOCATION_STATE.json"
    terminal = args.artifact_root / "COMPONENT_TERMINAL.json"
    if not args.counter_only and terminal.exists() and invocation.exists():
        existing_terminal = json.loads(terminal.read_text())
        existing_invocation = json.loads(invocation.read_text())
        completed_candidate_matches = (
            existing_terminal.get("identity", {}).get("candidate_sha256")
            == digest(args.candidate)
            and existing_terminal.get("component_pass") is True
            and existing_invocation.get("scientific_terminal_recorded") is True
        )
        if completed_candidate_matches:
            print(json.dumps(existing_terminal, indent=2, sort_keys=True))
            return 0
    atomic(
        invocation,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": False,
            "scientific_invocation_started": False,
            "updated_unix_s": time.time(),
        },
    )
    if not torch.cuda.is_available() or torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("exact_sm90_cuda_unavailable")
    control = importlib.import_module(
        "sglang.srt.layers.attention.triton_ops.extend_attention"
    )
    control_path = pathlib.Path(control.__file__).resolve()
    if digest(control_path) != SOURCE_SHA256:
        raise RuntimeError(f"installed_control_source_mismatch:{digest(control_path)}")
    candidate = load(args.candidate)
    local_tensors = make_tensors(args.seed, head_dim=256, kv_heads=16)
    global_tensors = make_tensors(args.seed + 1, head_dim=512, kv_heads=4)
    if args.counter_only:
        invocations = (
            (control, local_tensors, True, 256),
            (control, global_tensors, False, 512),
            (candidate, local_tensors, True, 256),
            (candidate, global_tensors, False, 512),
        )
        outputs = [
            torch.empty_like(tensors["q"])
            for _, tensors, _, _ in invocations
        ]
        for (module, tensors, local, head_dim), output in zip(
            invocations, outputs, strict=True
        ):
            invoke(module, tensors, output, local, head_dim)
        torch.cuda.synchronize()
        torch.cuda.cudart().cudaProfilerStart()
        for (module, tensors, local, head_dim), output in zip(
            invocations, outputs, strict=True
        ):
            invoke(module, tensors, output, local, head_dim)
        torch.cuda.synchronize()
        torch.cuda.cudart().cudaProfilerStop()
        atomic(
            args.artifact_root / "COUNTER_INVOCATION.json",
            {
                "schema_version": 1,
                "launch_order": [
                    "control_local",
                    "control_full",
                    "candidate_local",
                    "candidate_full",
                ],
                "complete": True,
            },
        )
        return 0
    invoke(
        control,
        local_tensors,
        torch.empty_like(local_tensors["q"]),
        True,
        256,
    )
    torch.cuda.synchronize()
    atomic(
        invocation,
        {
            "schema_version": 1,
            "candidate_cuda_invocation_started": True,
            "scientific_invocation_started": True,
            "updated_unix_s": time.time(),
        },
    )
    rows = [
        row(
            control,
            candidate,
            local_tensors,
            True,
            256,
            16,
            args.warmups,
            args.iterations,
        ),
        row(
            control,
            candidate,
            global_tensors,
            False,
            512,
            4,
            args.warmups,
            args.iterations,
        ),
    ]
    weighted_control = rows[0]["control"]["median_ms"] * 50 + rows[1]["control"]["median_ms"] * 10
    weighted_candidate = rows[0]["candidate"]["median_ms"] * 50 + rows[1]["candidate"]["median_ms"] * 10
    attention_reduction = 1 - weighted_candidate / weighted_control
    weighted_split_reductions = []
    for parity in (0, 1):
        split_control = sum(
            statistics.median(item["control"]["samples_ms"][parity::2]) * weight
            for item, weight in zip(rows, (50, 10), strict=True)
        )
        split_candidate = sum(
            statistics.median(item["candidate"]["samples_ms"][parity::2]) * weight
            for item, weight in zip(rows, (50, 10), strict=True)
        )
        weighted_split_reductions.append(1 - split_candidate / split_control)
    target_boundary_bound = attention_reduction * ATTENTION_US / TARGET_GPU_UNION_US
    correct = all(
        item["oracle"]["all_finite"]
        and item["oracle"]["allclose_atol_0_02_rtol_0_005"]
        and item["oracle"]["candidate_graph_replay_bitwise"]
        and item["oracle"]["control_output_l1"] > 0
        and item["oracle"]["candidate_output_l1"] > 0
        for item in rows
    )
    dispatch = candidate.fixed_m384_dispatch_audit()
    mixed_dispatch_pass = (
        dispatch.get("local_m8_qk256_v256", 0) > 0
        and dispatch.get("global_stock_m32_qk512_v512", 0) > 0
        and rows[1]["oracle"]["bit_exact"]
    )
    reproducible_positive = (
        rows[0]["latency_reduction_fraction"] > 0
        and all(value > 0 for value in rows[0]["split_latency_reduction_fractions"])
        and attention_reduction > 0
        and all(value > 0 for value in weighted_split_reductions)
    )
    terminal = {
        "schema_version": 1,
        "kind": "exact_c32_ngram_tree_verify_attention_component",
        "correct": correct,
        "component_pass": (
            correct
            and mixed_dispatch_pass
            and reproducible_positive
            and target_boundary_bound > 0
        ),
        "mixed_dispatch_pass": mixed_dispatch_pass,
        "reproducible_positive": reproducible_positive,
        "rows": rows,
        "weighted_attention_reduction_fraction": attention_reduction,
        "weighted_split_reduction_fractions": weighted_split_reductions,
        "positive_target_boundary_bound_fraction": target_boundary_bound,
        "trace_attention_fraction": ATTENTION_US / TARGET_GPU_UNION_US,
        "launches_per_verify_step": {"control": 60, "candidate": 110},
        "launch_grid_per_layer": {
            "control_local": [32, 32, 1],
            "control_global": [32, 32, 1],
            "candidate_local": [32, 32, 2],
            "candidate_global": [32, 32, 1],
        },
        "physical": {
            "control_block_m": {"local": 64, "global": 32},
            "candidate_block_m": {"local": 8, "global": 32},
            "block_n": 64,
            "padded_query_rows": {
                "control_local": 64,
                "control_global": 32,
                "candidate_local": 16,
                "candidate_global": 32,
            },
            "live_accumulator_elements": {
                "control_local": 64 * 256,
                "control_global": 32 * 512,
                "candidate_local": 8 * 256,
                "candidate_global": 32 * 512,
            },
            "compulsory_kv_bytes_change": 0,
            "new_sync_boundaries": 0,
        },
        "shape": {
            "batch": BATCH,
            "draft_tokens_per_request": DRAFT,
            "query_positions": BATCH * DRAFT,
            "query_heads": Q_HEADS,
            "local_kv_heads": 16,
            "local_head_dim": 256,
            "global_kv_heads": 4,
            "global_head_dim": 512,
            "page_size": 1,
            "kv_dtype": "torch.float8_e5m2",
            "activation_dtype": "torch.bfloat16",
            "tree_mask": "adversarial_branching_12x(4214+12)",
        },
        "identity": {
            "installed_control_source": str(control_path),
            "control_sha256": digest(control_path),
            "candidate_sha256": digest(args.candidate),
            "candidate_dispatch_audit": dispatch,
            "torch": torch.__version__,
            "triton": importlib.import_module("triton").__version__,
        },
    }
    atomic(args.artifact_root / "COMPONENT_TERMINAL.json", terminal)
    atomic(invocation, {**json.loads(invocation.read_text()), "scientific_terminal_recorded": True})
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0 if terminal["component_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
