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
import sys
import time
import types
from typing import Any

import torch


CONTROL_SHA256 = "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"
BATCH = 32
DRAFT = 12
ORIGINAL_PREFIX = 4214
LOCAL_PREFIX = 1024
QUERY_HEADS = 32
TRACE_ATTENTION_US = 1_488_205.758
TRACE_INTERVAL_UNION_US = 2_216_848.006591797
QUALIFIED_SECONDS_PER_REQUEST = 0.625149101968745


def atomic(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install_control_import_stubs() -> None:
    packages = [
        "sglang",
        "sglang.srt",
        "sglang.srt.layers",
        "sglang.srt.layers.attention",
        "sglang.srt.layers.attention.triton_ops",
    ]
    for package in packages:
        module = types.ModuleType(package)
        module.__path__ = []
        sys.modules[package] = module
    prefill = types.ModuleType(
        "sglang.srt.layers.attention.triton_ops.prefill_attention"
    )
    prefill.context_attention_fwd = lambda *args, **kwargs: None
    sys.modules[prefill.__name__] = prefill
    utilities = types.ModuleType("sglang.srt.utils")
    utilities.is_cuda = lambda: True
    utilities.is_hip = lambda: False
    sys.modules[utilities.__name__] = utilities


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"module_spec_unavailable:{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def distribution(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "samples_ms": values,
        "minimum_ms": ordered[0],
        "p50_ms": statistics.median(ordered),
        "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "maximum_ms": ordered[-1],
    }


def timed_ms(function) -> float:
    begin = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    begin.record()
    function()
    end.record()
    end.synchronize()
    return float(begin.elapsed_time(end))


def tensors(seed: int, *, head_dim: int, kv_heads: int, prefix: int):
    torch.manual_seed(seed)
    tokens = BATCH * DRAFT
    total_pages = BATCH * ORIGINAL_PREFIX
    q = torch.randn(
        (tokens, QUERY_HEADS, head_dim), device="cuda", dtype=torch.bfloat16
    )
    k = torch.randn(
        (tokens, kv_heads, head_dim), device="cuda", dtype=torch.bfloat16
    )
    v = torch.randn(
        (tokens, kv_heads, head_dim), device="cuda", dtype=torch.bfloat16
    )
    k_cache = torch.randn(
        (total_pages, kv_heads, head_dim),
        device="cuda",
        dtype=torch.bfloat16,
    ).to(torch.float8_e4m3fn)
    v_cache = torch.randn(
        (total_pages, kv_heads, head_dim),
        device="cuda",
        dtype=torch.bfloat16,
    ).to(torch.float8_e4m3fn)
    shuffled_pages = torch.randperm(
        total_pages, device="cuda", dtype=torch.int64
    ).view(BATCH, ORIGINAL_PREFIX)
    selected_pages = shuffled_pages[:, -prefix:].contiguous()
    qo_indptr = torch.arange(
        0, (BATCH + 1) * DRAFT, DRAFT, device="cuda", dtype=torch.int32
    )
    kv_indptr = torch.arange(
        0, (BATCH + 1) * prefix, prefix, device="cuda", dtype=torch.int32
    )
    tree = torch.zeros((DRAFT, DRAFT), device="cuda", dtype=torch.bool)
    for row in range(DRAFT):
        tree[row, row] = True
        tree[row, 0] = True
        for column in range(1, row):
            tree[row, column] = column % 3 == row % 3
    masks = []
    for _ in range(BATCH):
        visible_prefix = torch.ones(
            (DRAFT, ORIGINAL_PREFIX), device="cuda", dtype=torch.bool
        )
        masks.append(torch.cat((visible_prefix, tree), dim=1).flatten())
    custom_mask = torch.cat(masks)
    mask_stride = DRAFT * (ORIGINAL_PREFIX + DRAFT)
    mask_indptr = torch.arange(
        0,
        (BATCH + 1) * mask_stride,
        mask_stride,
        device="cuda",
        dtype=torch.int32,
    )
    return {
        "q": q,
        "k": k,
        "v": v,
        "k_cache": k_cache,
        "v_cache": v_cache,
        "qo_indptr": qo_indptr,
        "kv_indptr": kv_indptr,
        "kv_indices": selected_pages.flatten(),
        "custom_mask": custom_mask,
        "mask_indptr": mask_indptr,
        "window_offsets": torch.full(
            (BATCH,),
            ORIGINAL_PREFIX - prefix,
            device="cuda",
            dtype=torch.int32,
        ),
    }


def invoke(module, inputs, output, *, local: bool, head_dim: int) -> None:
    module.extend_attention_fwd(
        inputs["q"],
        inputs["k"],
        inputs["v"],
        output,
        inputs["k_cache"],
        inputs["v_cache"],
        inputs["qo_indptr"],
        inputs["kv_indptr"],
        inputs["kv_indices"],
        inputs["custom_mask"],
        True,
        inputs["mask_indptr"],
        DRAFT,
        1.0,
        1.0,
        1.0 / math.sqrt(head_dim),
        sliding_window_size=LOCAL_PREFIX if local else -1,
        window_kv_offsets=inputs["window_offsets"] if local else None,
    )


def candidate_graph_replay(module, inputs, output, *, local, head_dim) -> bool:
    invoke(module, inputs, output, local=local, head_dim=head_dim)
    torch.cuda.synchronize()
    expected = output.clone()
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        invoke(module, inputs, output, local=local, head_dim=head_dim)
    graph.replay()
    torch.cuda.synchronize()
    return bool(torch.equal(expected, output))


def evaluate_case(
    control,
    candidate,
    *,
    local: bool,
    head_dim: int,
    kv_heads: int,
    prefix: int,
    seed: int,
    warmups: int,
    repetitions: int,
):
    inputs = tensors(seed, head_dim=head_dim, kv_heads=kv_heads, prefix=prefix)
    control_output = torch.empty_like(inputs["q"])
    candidate_output = torch.empty_like(inputs["q"])
    invoke(control, inputs, control_output, local=local, head_dim=head_dim)
    invoke(candidate, inputs, candidate_output, local=local, head_dim=head_dim)
    torch.cuda.synchronize()
    graph_bitwise = candidate_graph_replay(
        candidate,
        inputs,
        candidate_output,
        local=local,
        head_dim=head_dim,
    )
    delta = candidate_output.float() - control_output.float()
    output_consumer = float(candidate_output.float().square().sum().item())
    oracle = {
        "all_finite": bool(torch.isfinite(candidate_output).all().item()),
        "allclose_atol_0_02_rtol_0_005": bool(
            torch.allclose(
                candidate_output.float(),
                control_output.float(),
                atol=0.02,
                rtol=0.005,
            )
        ),
        "max_abs_error": float(delta.abs().max().item()),
        "mean_abs_error": float(delta.abs().mean().item()),
        "relative_l2": float(
            (
                torch.linalg.vector_norm(delta)
                / torch.linalg.vector_norm(control_output.float()).clamp_min(1e-12)
            ).item()
        ),
        "control_l1": float(control_output.float().abs().sum().item()),
        "candidate_l1": float(candidate_output.float().abs().sum().item()),
        "output_consumer_square_sum": output_consumer,
        "candidate_graph_replay_bitwise": graph_bitwise,
    }
    for _ in range(warmups):
        invoke(control, inputs, control_output, local=local, head_dim=head_dim)
        invoke(candidate, inputs, candidate_output, local=local, head_dim=head_dim)
    torch.cuda.synchronize()
    control_samples = []
    candidate_samples = []
    for index in range(repetitions):
        order = (
            ((control, control_output, control_samples), (candidate, candidate_output, candidate_samples))
            if index % 2 == 0
            else ((candidate, candidate_output, candidate_samples), (control, control_output, control_samples))
        )
        for module, output, samples in order:
            samples.append(
                timed_ms(
                    lambda m=module, o=output: invoke(
                        m, inputs, o, local=local, head_dim=head_dim
                    )
                )
            )
    control_distribution = distribution(control_samples)
    candidate_distribution = distribution(candidate_samples)
    return {
        "kind": "local_d256" if local else "global_d512",
        "head_dim": head_dim,
        "query_heads": QUERY_HEADS,
        "kv_heads": kv_heads,
        "prefix_tokens": prefix,
        "partitions": math.ceil(prefix / 512),
        "control": control_distribution,
        "candidate": candidate_distribution,
        "p50_reduction_fraction": (
            1.0
            - candidate_distribution["p50_ms"] / control_distribution["p50_ms"]
        ),
        "p95_reduction_fraction": (
            1.0
            - candidate_distribution["p95_ms"] / control_distribution["p95_ms"]
        ),
        "oracle": oracle,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--candidate", type=pathlib.Path, required=True)
    parser.add_argument("--control", type=pathlib.Path, required=True)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260726)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation_path = args.artifact_root / "INVOCATION_STATE.json"
    atomic(
        invocation_path,
        {
            "schema_version": 1,
            "phase": "pre_science",
            "candidate_cuda_invocation_started": False,
        },
    )
    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    if torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError(
            f"sm90_required:{torch.cuda.get_device_capability()}"
        )
    if digest(args.control) != CONTROL_SHA256:
        raise RuntimeError(f"control_digest_mismatch:{digest(args.control)}")
    install_control_import_stubs()
    control = load_module("packed_m384_control", args.control)
    candidate = load_module("packed_m384_candidate", args.candidate)
    audit_path = args.artifact_root / "CANDIDATE_PATH.jsonl"
    os.environ["PACKED_M384_AUDIT"] = str(audit_path)

    atomic(
        invocation_path,
        {
            "schema_version": 1,
            "phase": "science_started",
            "candidate_cuda_invocation_started": True,
            "started_unix_s": time.time(),
        },
    )
    rows = [
        evaluate_case(
            control,
            candidate,
            local=True,
            head_dim=256,
            kv_heads=16,
            prefix=LOCAL_PREFIX,
            seed=args.seed,
            warmups=args.warmups,
            repetitions=args.repetitions,
        ),
        evaluate_case(
            control,
            candidate,
            local=False,
            head_dim=512,
            kv_heads=4,
            prefix=ORIGINAL_PREFIX,
            seed=args.seed + 1,
            warmups=args.warmups,
            repetitions=args.repetitions,
        ),
    ]
    weighted_control = (
        rows[0]["control"]["p50_ms"] * 50
        + rows[1]["control"]["p50_ms"] * 10
    )
    weighted_candidate = (
        rows[0]["candidate"]["p50_ms"] * 50
        + rows[1]["candidate"]["p50_ms"] * 10
    )
    weighted_reduction = 1.0 - weighted_candidate / weighted_control
    attention_fraction = TRACE_ATTENTION_US / TRACE_INTERVAL_UNION_US
    target_boundary_projection = weighted_reduction * attention_fraction
    request_projection = (
        target_boundary_projection
        * 0.25361708474580313
        * QUALIFIED_SECONDS_PER_REQUEST
    )
    dispatch = candidate.packed_m384_dispatch_audit()
    exact_work = (
        dispatch.get("local_d256", 0) > 0
        and dispatch.get("global_d512", 0) > 0
        and rows[0]["partitions"] == 2
        and rows[1]["partitions"] == 9
    )
    correct = all(
        row["oracle"]["all_finite"]
        and row["oracle"]["allclose_atol_0_02_rtol_0_005"]
        and row["oracle"]["candidate_graph_replay_bitwise"]
        and row["oracle"]["control_l1"] > 0.0
        and row["oracle"]["candidate_l1"] > 0.0
        and row["oracle"]["output_consumer_square_sum"] > 0.0
        for row in rows
    )
    terminal = {
        "schema_version": 1,
        "kind": "hopper_packed_m384_exact_consumer_component",
        "result": (
            "component_positive"
            if correct and exact_work and weighted_reduction > 0
            else "typed_none"
        ),
        "correct": correct,
        "exact_work": exact_work,
        "rows": rows,
        "weighted_attention_p50_reduction_fraction": weighted_reduction,
        "projected_target_boundary_reduction_fraction": target_boundary_projection,
        "projected_seconds_saved_per_qualified_request": request_projection,
        "dispatch": dispatch,
        "physical": {
            "control_query_tile_rows": {"local": 64, "global": 32},
            "candidate_query_tile_rows": 16,
            "context_partition_tokens": 512,
            "candidate_context_partitions": {"local": 2, "global": 9},
            "candidate_score_producer_ctas": {"local": 2048, "global": 9216},
            "candidate_state_merge_ctas": 1024,
            "candidate_value_consumer_ctas": {
                "local": 4096,
                "global": 8192,
            },
            "direct_page_size_one_fp8_kv": True,
            "online_softmax_state": ["max", "normalizer", "output"],
            "persisted_score_dtype": "bfloat16",
            "tma_kv_eligible": False,
            "tma_kv_ineligibility_reason": "page-size-1 shuffled kv_indices require gather loads",
        },
        "identity": {
            "gpu": torch.cuda.get_device_name(),
            "capability": list(torch.cuda.get_device_capability()),
            "torch": torch.__version__,
            "triton": importlib.import_module("triton").__version__,
            "control_sha256": digest(args.control),
            "candidate_sha256": digest(args.candidate),
        },
    }
    atomic(args.artifact_root / "PACKED_M384_VERIFIER_RESULT.json", terminal)
    atomic(
        invocation_path,
        {
            "schema_version": 1,
            "phase": "scientific_terminal_recorded",
            "candidate_cuda_invocation_started": True,
            "terminal": "PACKED_M384_VERIFIER_RESULT.json",
        },
    )
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0 if terminal["result"] == "component_positive" else 2


if __name__ == "__main__":
    raise SystemExit(main())
