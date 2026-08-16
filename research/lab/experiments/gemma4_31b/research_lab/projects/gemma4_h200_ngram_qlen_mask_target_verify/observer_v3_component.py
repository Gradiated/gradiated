#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import math
import pathlib
import time

import torch

import component_benchmark as base


def invoke(module, tensors, output, local, qlen):
    module.extend_attention_fwd_unified(
        tensors["q"], output, tensors["k_buffer"], tensors["v_buffer"], 1.0, 1.0,
        tensors["qo_indptr"], tensors["local_indptr"], tensors["local_indices"],
        torch.full((base.BATCH,), base.LOCAL_PREFIX, dtype=torch.int32, device="cuda"),
        base.DRAFT,
        tensors["qlen_custom_mask"] if qlen else tensors["local_full_custom_mask"],
        tensors["qlen_mask_indptr"] if qlen else tensors["local_full_mask_indptr"],
        1 / math.sqrt(base.HEAD_DIM), is_causal=True, sliding_window_size=1024,
        window_start_pos=tensors["window_offsets"],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--candidate", type=pathlib.Path, required=True)
    parser.add_argument("--prior-component", type=pathlib.Path, required=True)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260724)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation = args.artifact_root / "INVOCATION_STATE.json"
    base.atomic(invocation, {"schema_version": 1, "candidate_cuda_invocation_started": False, "scientific_invocation_started": False, "observer": "v3_window_sliced_control"})
    if not torch.cuda.is_available() or torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("exact_sm90_cuda_unavailable")
    control = importlib.import_module("sglang.srt.layers.attention.triton_ops.extend_attention")
    control_path = pathlib.Path(control.__file__).resolve()
    if base.digest(control_path) != base.SOURCE_SHA256:
        raise RuntimeError(f"installed_control_source_mismatch:{base.digest(control_path)}")
    candidate = base.load(args.candidate)
    tensors = base.make_tensors(args.seed)
    local_masks = []
    for _ in range(base.BATCH):
        prefix = torch.ones((base.DRAFT, base.LOCAL_PREFIX), device="cuda", dtype=torch.bool)
        local_masks.append(torch.cat((prefix, tensors["tree"]), dim=1).flatten())
    tensors["local_full_custom_mask"] = torch.cat(local_masks)
    local_stride = base.DRAFT * (base.LOCAL_PREFIX + base.DRAFT)
    tensors["local_full_mask_indptr"] = torch.arange(0, (base.BATCH + 1) * local_stride, local_stride, device="cuda", dtype=torch.int32)
    base.invoke = invoke
    invoke(control, tensors, torch.empty_like(tensors["q"]), True, False)
    torch.cuda.synchronize()
    base.atomic(invocation, {"schema_version": 1, "candidate_cuda_invocation_started": True, "scientific_invocation_started": True, "observer": "v3_window_sliced_control"})
    sliding = base.row(control, candidate, tensors, True, args.warmups, args.iterations)
    prior = json.loads(args.prior_component.read_text())
    full = next(row for row in prior["rows"] if row["layer_type"] == "full_attention")
    prep = prior["mask_preparation"]
    weighted_control = sliding["control"]["median_ms"] * 50 + full["control"]["median_ms"] * 10 + prep["control"]["median_ms"]
    weighted_candidate = sliding["candidate"]["median_ms"] * 50 + full["candidate"]["median_ms"] * 10 + prep["candidate"]["median_ms"]
    bound = (weighted_control - weighted_candidate) * 15 / (base.TRACE_WINDOW_US / 1000)
    correct = sliding["oracle"]["all_finite"] and sliding["oracle"]["allclose_atol_0_005_rtol_0_005"]
    terminal = {"schema_version": 1, "kind": "exact_c32_ngram_unified_sliding_observer_v3", "correct": correct, "component_pass": correct and bound > 0, "sliding_row": sliding, "reused_full_attention_row": full, "reused_mask_preparation": prep, "positive_whole_request_bound_fraction": bound, "control_layout": {"row_stride": base.LOCAL_PREFIX + base.DRAFT, "mask_indptr_stride": local_stride, "prefix_keys": base.LOCAL_PREFIX, "suffix_keys": base.DRAFT}, "identity": {"installed_control_source": str(control_path), "control_sha256": base.digest(control_path), "candidate_sha256": base.digest(args.candidate)}}
    base.atomic(args.artifact_root / "COMPONENT_TERMINAL.json", terminal)
    base.atomic(invocation, {"schema_version": 1, "candidate_cuda_invocation_started": True, "scientific_invocation_started": True, "scientific_terminal_recorded": True, "observer": "v3_window_sliced_control"})
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0 if terminal["component_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
