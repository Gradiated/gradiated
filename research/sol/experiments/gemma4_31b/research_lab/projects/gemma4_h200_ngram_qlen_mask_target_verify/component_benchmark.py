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
TRACE_WINDOW_US = 2_375_141.908
ATTENTION_US = 1_488_205.758
BATCH = 32
DRAFT = 12
PREFIX = 4214
LOCAL_PREFIX = 1024
Q_HEADS = 32
KV_HEADS = 16
HEAD_DIM = 256


def atomic(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("fixed_tree_extend_attention", path)
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


def make_tensors(seed: int) -> dict[str, torch.Tensor]:
    torch.manual_seed(seed)
    device = "cuda"
    tokens = BATCH * DRAFT
    total_pages = BATCH * (PREFIX + DRAFT)
    q = torch.randn((tokens, Q_HEADS, HEAD_DIM), device=device, dtype=torch.bfloat16)
    k = torch.randn((tokens, KV_HEADS, HEAD_DIM), device=device, dtype=torch.bfloat16)
    v = torch.randn((tokens, KV_HEADS, HEAD_DIM), device=device, dtype=torch.bfloat16)
    fp8 = torch.float8_e5m2
    k_buffer = torch.randn(
        (total_pages, KV_HEADS, HEAD_DIM), device=device, dtype=torch.bfloat16
    ).to(fp8)
    v_buffer = torch.randn(
        (total_pages, KV_HEADS, HEAD_DIM), device=device, dtype=torch.bfloat16
    ).to(fp8)
    pages = torch.randperm(total_pages, device=device, dtype=torch.int64).view(
        BATCH, PREFIX + DRAFT
    )
    qo_indptr = torch.arange(
        0, (BATCH + 1) * DRAFT, DRAFT, device=device, dtype=torch.int32
    )
    global_indptr = torch.arange(
        0,
        (BATCH + 1) * (PREFIX + DRAFT),
        PREFIX + DRAFT,
        device=device,
        dtype=torch.int32,
    )
    local_indptr = torch.arange(
        0,
        (BATCH + 1) * (LOCAL_PREFIX + DRAFT),
        LOCAL_PREFIX + DRAFT,
        device=device,
        dtype=torch.int32,
    )
    tree = torch.zeros((DRAFT, DRAFT), device=device, dtype=torch.bool)
    for row in range(DRAFT):
        tree[row, row] = True
        tree[row, 0] = True
        for column in range(1, row):
            tree[row, column] = column % 3 == row % 3
    full_masks = []
    for _ in range(BATCH):
        prefix = torch.ones((DRAFT, PREFIX), device=device, dtype=torch.bool)
        full_masks.append(torch.cat((prefix, tree), dim=1).flatten())
    full_custom_mask = torch.cat(full_masks)
    qlen_custom_mask = tree.flatten().repeat(BATCH)
    full_stride = DRAFT * (PREFIX + DRAFT)
    qlen_stride = DRAFT * DRAFT
    full_mask_indptr = torch.arange(
        0, (BATCH + 1) * full_stride, full_stride, device=device, dtype=torch.int32
    )
    qlen_mask_indptr = torch.arange(
        0, (BATCH + 1) * qlen_stride, qlen_stride, device=device, dtype=torch.int32
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
        "local_indices": torch.cat(
            (pages[:, PREFIX - LOCAL_PREFIX : PREFIX], pages[:, PREFIX:]), dim=1
        ).flatten().contiguous(),
        "tree": tree,
        "full_custom_mask": full_custom_mask,
        "qlen_custom_mask": qlen_custom_mask,
        "full_mask_indptr": full_mask_indptr,
        "qlen_mask_indptr": qlen_mask_indptr,
        "window_offsets": torch.full(
            (BATCH,), PREFIX - LOCAL_PREFIX, device=device, dtype=torch.int32
        ),
    }


def invoke(
    module: Any,
    tensors: dict[str, torch.Tensor],
    output: torch.Tensor,
    local: bool,
    qlen: bool,
) -> None:
    module.extend_attention_fwd_unified(
        tensors["q"],
        output,
        tensors["k_buffer"],
        tensors["v_buffer"],
        1.0,
        1.0,
        tensors["qo_indptr"],
        tensors["local_indptr"] if local else tensors["global_indptr"],
        tensors["local_indices"] if local else tensors["global_indices"],
        torch.full(
            (BATCH,),
            LOCAL_PREFIX if local else PREFIX,
            dtype=torch.int32,
            device="cuda",
        ),
        DRAFT,
        tensors["qlen_custom_mask"] if qlen else tensors["full_custom_mask"],
        tensors["qlen_mask_indptr"] if qlen else tensors["full_mask_indptr"],
        1 / math.sqrt(HEAD_DIM),
        is_causal=True,
        sliding_window_size=1024 if local else -1,
        window_start_pos=tensors["window_offsets"] if local else None,
    )


def row(
    control: Any,
    candidate: Any,
    tensors: dict[str, torch.Tensor],
    local: bool,
    warmups: int,
    iterations: int,
) -> dict[str, Any]:
    control_output = torch.empty_like(tensors["q"])
    candidate_output = torch.empty_like(tensors["q"])
    invoke(control, tensors, control_output, local, False)
    invoke(candidate, tensors, candidate_output, local, True)
    torch.cuda.synchronize()
    delta = candidate_output.float() - control_output.float()
    oracle = {
        "all_finite": bool(torch.isfinite(candidate_output).all().item()),
        "allclose_atol_0_005_rtol_0_005": bool(
            torch.allclose(
                candidate_output.float(),
                control_output.float(),
                atol=0.005,
                rtol=0.005,
            )
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
        invoke(control, tensors, control_output, local, False)
        invoke(candidate, tensors, candidate_output, local, True)
    torch.cuda.synchronize()
    control_values: list[float] = []
    candidate_values: list[float] = []
    for index in range(iterations):
        order = (
            ((control, control_output, control_values), (candidate, candidate_output, candidate_values))
            if index % 2 == 0
            else ((candidate, candidate_output, candidate_values), (control, control_output, control_values))
        )
        for module, output, values in order:
            values.append(
                timed_ms(
                    lambda m=module, o=output: invoke(
                        m, tensors, o, local, m is candidate
                    )
                )
            )
    control_dist = distribution(control_values)
    candidate_dist = distribution(candidate_values)
    return {
        "layer_type": "sliding_window_1024" if local else "full_attention",
        "prefix_tokens_consumed": LOCAL_PREFIX if local else PREFIX,
        "original_sequence_tokens": PREFIX,
        "window_offset": PREFIX - LOCAL_PREFIX if local else 0,
        "control": control_dist,
        "candidate": candidate_dist,
        "latency_reduction_fraction": (
            1 - candidate_dist["median_ms"] / control_dist["median_ms"]
        ),
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
    tensors = make_tensors(args.seed)
    if args.counter_only:
        outputs = [torch.empty_like(tensors["q"]) for _ in range(4)]
        for module, local, output in (
            (control, True, outputs[0]),
            (control, False, outputs[1]),
            (candidate, True, outputs[2]),
            (candidate, False, outputs[3]),
        ):
            invoke(module, tensors, output, local, module is candidate)
        torch.cuda.synchronize()
        torch.cuda.cudart().cudaProfilerStart()
        for module, local, output in (
            (control, True, outputs[0]),
            (control, False, outputs[1]),
            (candidate, True, outputs[2]),
            (candidate, False, outputs[3]),
        ):
            invoke(module, tensors, output, local, module is candidate)
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
    invoke(control, tensors, torch.empty_like(tensors["q"]), True, False)
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
        row(control, candidate, tensors, True, args.warmups, args.iterations),
        row(control, candidate, tensors, False, args.warmups, args.iterations),
    ]
    def prepare_full() -> torch.Tensor:
        masks = []
        for _ in range(BATCH):
            prefix = torch.ones((DRAFT, PREFIX), device="cuda", dtype=torch.bool)
            masks.append(torch.cat((prefix, tensors["tree"]), dim=1).flatten())
        return torch.cat(masks)

    def prepare_qlen() -> torch.Tensor:
        return tensors["tree"].flatten().repeat(BATCH)

    prep_control = [timed_ms(prepare_full) for _ in range(args.iterations)]
    prep_candidate = [timed_ms(prepare_qlen) for _ in range(args.iterations)]
    weighted_control = (
        rows[0]["control"]["median_ms"] * 50
        + rows[1]["control"]["median_ms"] * 10
        + statistics.median(prep_control)
    )
    weighted_candidate = (
        rows[0]["candidate"]["median_ms"] * 50
        + rows[1]["candidate"]["median_ms"] * 10
        + statistics.median(prep_candidate)
    )
    target_verify_reduction = 1 - weighted_candidate / weighted_control
    whole_request_bound = (
        (weighted_control - weighted_candidate) * 15
        / (TRACE_WINDOW_US / 1000)
    )
    correct = all(
        item["oracle"]["all_finite"]
        and item["oracle"]["allclose_atol_0_005_rtol_0_005"]
        and item["oracle"]["control_output_l1"] > 0
        and item["oracle"]["candidate_output_l1"] > 0
        for item in rows
    )
    terminal = {
        "schema_version": 1,
        "kind": "exact_c32_ngram_tree_verify_attention_component",
        "correct": correct,
        "component_pass": correct and target_verify_reduction > 0 and whole_request_bound > 0,
        "rows": rows,
        "weighted_target_verify_reduction_fraction": target_verify_reduction,
        "positive_whole_request_bound_fraction": whole_request_bound,
        "mask_preparation": {
            "control": distribution(prep_control),
            "candidate": distribution(prep_candidate),
            "control_booleans": BATCH * DRAFT * (PREFIX + DRAFT),
            "candidate_booleans": BATCH * DRAFT * DRAFT,
            "control_bytes": tensors["full_custom_mask"].numel(),
            "candidate_bytes": tensors["qlen_custom_mask"].numel(),
            "allocations_per_step_control": BATCH * 2 + 1,
            "allocations_per_step_candidate": 1,
        },
        "trace_attention_fraction": ATTENTION_US / TRACE_WINDOW_US,
        "launches_per_verify_step": {"control": 60, "candidate": 60},
        "launch_grid_per_layer": {"control": [32, 32, 1], "candidate": [32, 32, 1]},
        "physical": {
            "control_block_m": 64,
            "candidate_block_m": 64,
            "block_n": 64,
            "useful_query_lane_fraction_control": DRAFT / 64,
            "useful_query_lane_fraction_candidate": DRAFT / 64,
            "live_accumulator_elements_control": 64 * HEAD_DIM,
            "live_accumulator_elements_candidate": 64 * HEAD_DIM,
            "compulsory_kv_bytes_change": 0,
            "new_sync_boundaries": 0,
            "causal_change": "full-prefix mask representation to QLEN-only suffix mask",
        },
        "shape": {
            "batch": BATCH,
            "draft_tokens_per_request": DRAFT,
            "query_positions": BATCH * DRAFT,
            "query_heads": Q_HEADS,
            "kv_heads": KV_HEADS,
            "head_dim": HEAD_DIM,
            "page_size": 1,
            "kv_dtype": "torch.float8_e5m2",
            "activation_dtype": "torch.bfloat16",
            "control_tree_mask": "adversarial_branching_12x(4214+12)",
            "candidate_tree_mask": "same adversarial branching suffix 12x12",
        },
        "identity": {
            "installed_control_source": str(control_path),
            "control_sha256": digest(control_path),
            "candidate_sha256": digest(args.candidate),
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
