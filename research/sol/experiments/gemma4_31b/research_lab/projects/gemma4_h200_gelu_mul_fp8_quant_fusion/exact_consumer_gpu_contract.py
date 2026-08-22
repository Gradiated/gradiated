#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import statistics
import sys


PROJECT = pathlib.Path(__file__).resolve().parent
EXACT_HIDDEN = 5376
EXACT_INTERMEDIATE = 21504
EXACT_GATE_UP = 43008
DOWN_KEY = "model.language_model.layers.0.mlp.down_proj.weight"
ROWS = (1, 7, 31, 32, 33, 118)


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def error_metrics(torch, control, candidate) -> dict:
    control_fp32 = control.float()
    candidate_fp32 = candidate.float()
    difference = candidate_fp32 - control_fp32
    denominator = torch.linalg.vector_norm(control_fp32).clamp_min(1e-12)
    return {
        "max_abs": difference.abs().max().item(),
        "relative_l2": (torch.linalg.vector_norm(difference) / denominator).item(),
        "cosine": torch.nn.functional.cosine_similarity(
            control_fp32.flatten(), candidate_fp32.flatten(), dim=0
        ).item(),
        "nonfinite": (~torch.isfinite(candidate_fp32)).sum().item(),
    }


def consume(torch, result) -> None:
    if isinstance(result, tuple):
        for tensor in result:
            tensor.view(torch.uint8).sum().item()
    else:
        result.float().sum().item()


def sample_pair(torch, control, candidate, repetitions: int = 100):
    for _ in range(20):
        consume(torch, control())
        consume(torch, candidate())
    torch.cuda.synchronize()
    values = {"control": [], "candidate": []}
    functions = {"control": control, "candidate": candidate}
    for repetition in range(repetitions):
        order = (
            ("control", "candidate")
            if repetition % 2 == 0
            else ("candidate", "control")
        )
        for name in order:
            start = torch.cuda.Event(enable_timing=True)
            end = torch.cuda.Event(enable_timing=True)
            start.record()
            result = functions[name]()
            end.record()
            end.synchronize()
            values[name].append(start.elapsed_time(end))
            consume(torch, result)
    return values


def atomic_json(path: pathlib.Path, payload: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=pathlib.Path, required=True)
    parser.add_argument(
        "--checkpoint-manifest", type=pathlib.Path, required=True
    )
    parser.add_argument("--candidate-source", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.checkpoint = args.checkpoint.resolve()
    args.checkpoint_manifest = args.checkpoint_manifest.resolve()
    args.candidate_source = args.candidate_source.resolve()
    try:
        args.checkpoint.relative_to(PROJECT / "inputs")
    except ValueError as error:
        raise RuntimeError(
            "checkpoint must be an immutable project-local snapshot under inputs/"
        ) from error
    if args.checkpoint_manifest.parent != args.checkpoint:
        raise RuntimeError("checkpoint manifest must reside in the snapshot root")
    if args.candidate_source != (
        PROJECT / "candidate/fused_gelu_mul_dynamic_fp8_sm90.cu"
    ):
        raise RuntimeError("candidate source must be the project-local admitted file")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial_path = args.output.with_name(args.output.stem + ".partial.json")
    state_path = args.output.with_name(args.output.stem + ".invocation.json")
    for path in (args.output, partial_path, state_path):
        if path.exists():
            raise RuntimeError(f"refusing to overwrite prior generation: {path}")

    import torch
    from safetensors import safe_open
    from torch.utils.cpp_extension import load

    from sglang.srt.layers.activation import GeluAndMul
    from sglang.srt.layers.quantization.fp8_kernel import (
        per_token_group_quant_fp8,
        sglang_per_token_quant_fp8,
    )
    from sglang.srt.layers.quantization.fp8_utils import fp8_scaled_mm

    if not torch.cuda.is_available():
        raise RuntimeError("exact H200 CUDA is required")
    device = torch.cuda.get_device_properties(0)
    if "H200" not in device.name or (device.major, device.minor) != (9, 0):
        raise RuntimeError(f"exact H200 SM90 required, observed {device}")
    atomic_json(
        state_path,
        {
            "schema_version": 1,
            "pre_science": True,
            "science_started": False,
            "candidate_cuda_started": False,
            "candidate_science_started": False,
            "completed_tokens": [],
        },
    )

    source_sha256 = digest(args.candidate_source)
    extension = load(
        name=f"gemma4_gelu_mul_fp8_{source_sha256[:12]}",
        sources=[str(args.candidate_source)],
        extra_cflags=["-O3"],
        extra_cuda_cflags=["-O3", "-gencode=arch=compute_90,code=sm_90"],
        with_cuda=True,
        verbose=True,
    )

    manifest = json.loads(args.checkpoint_manifest.read_text())
    if manifest.get("model_id") != "google/gemma-4-31B-it":
        raise RuntimeError("checkpoint manifest model mismatch")
    if (
        manifest.get("revision")
        != "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
    ):
        raise RuntimeError("checkpoint manifest revision mismatch")
    admitted_files = manifest.get("files")
    if not isinstance(admitted_files, dict):
        raise RuntimeError("checkpoint manifest files must be a hash mapping")
    index = args.checkpoint / "model.safetensors.index.json"
    if admitted_files.get(index.name) != digest(index):
        raise RuntimeError("checkpoint index hash mismatch")
    index_payload = json.loads(index.read_text())
    try:
        shard_name = index_payload["weight_map"][DOWN_KEY]
    except KeyError as error:
        raise RuntimeError(f"checkpoint index lacks {DOWN_KEY}") from error
    shard = (args.checkpoint / shard_name).resolve()
    if shard.parent != args.checkpoint:
        raise RuntimeError("checkpoint index references a non-local shard")
    if admitted_files.get(shard_name) != digest(shard):
        raise RuntimeError("checkpoint shard hash mismatch")
    with safe_open(str(shard), framework="pt", device="cpu") as handle:
        raw_weight = handle.get_tensor(DOWN_KEY)
    if raw_weight.dtype != torch.bfloat16:
        raise RuntimeError(f"down weight dtype mismatch: {raw_weight.dtype}")
    if tuple(raw_weight.shape) != (EXACT_HIDDEN, EXACT_INTERMEDIATE):
        raise RuntimeError(f"down weight shape mismatch: {raw_weight.shape}")

    raw_weight = raw_weight.cuda()
    weight_q, weight_scale = per_token_group_quant_fp8(
        raw_weight, group_size=EXACT_INTERMEDIATE
    )
    weight_q = weight_q.t()
    weight_scale = weight_scale.t().contiguous()
    if tuple(weight_q.shape) != (EXACT_INTERMEDIATE, EXACT_HIDDEN):
        raise RuntimeError(f"consumer weight shape mismatch: {weight_q.shape}")
    if tuple(weight_q.stride()) != (1, EXACT_INTERMEDIATE):
        raise RuntimeError(f"consumer weight orientation mismatch: {weight_q.stride()}")
    if tuple(weight_scale.shape) != (1, EXACT_HIDDEN):
        raise RuntimeError(f"consumer scale shape mismatch: {weight_scale.shape}")

    activation = GeluAndMul()
    torch.manual_seed(20260730)
    rows = []
    atomic_json(
        state_path,
        {
            "schema_version": 1,
            "pre_science": False,
            "science_started": True,
            "candidate_cuda_started": False,
            "candidate_science_started": False,
            "completed_tokens": [],
        },
    )
    for tokens in ROWS:
        gate_up = torch.empty(
            (tokens, EXACT_GATE_UP), device="cuda", dtype=torch.bfloat16
        ).normal_(0.0, 0.7)

        def stock_boundary():
            return sglang_per_token_quant_fp8(activation(gate_up))

        def candidate_boundary():
            return extension.fused_gelu_mul_dynamic_fp8(gate_up)

        def stock_component():
            quantized, scale = stock_boundary()
            return fp8_scaled_mm(
                quantized,
                weight_q,
                scale,
                weight_scale,
                out_dtype=torch.bfloat16,
                bias=None,
            )

        def candidate_component():
            quantized, scale = candidate_boundary()
            return fp8_scaled_mm(
                quantized,
                weight_q,
                scale,
                weight_scale,
                out_dtype=torch.bfloat16,
                bias=None,
            )

        stock_q, stock_scale = stock_boundary()
        torch.cuda.synchronize()
        if not rows:
            atomic_json(
                state_path,
                {
                    "schema_version": 1,
                    "pre_science": False,
                    "science_started": True,
                    "candidate_cuda_started": True,
                    "candidate_science_started": True,
                    "completed_tokens": [],
                },
            )
        candidate_q, candidate_scale = candidate_boundary()
        torch.cuda.synchronize()
        stock_out = fp8_scaled_mm(
            stock_q,
            weight_q,
            stock_scale,
            weight_scale,
            out_dtype=torch.bfloat16,
            bias=None,
        )
        torch.cuda.synchronize()
        candidate_out = fp8_scaled_mm(
            candidate_q,
            weight_q,
            candidate_scale,
            weight_scale,
            out_dtype=torch.bfloat16,
            bias=None,
        )
        torch.cuda.synchronize()

        q_codes_exact = torch.equal(
            stock_q.view(torch.uint8), candidate_q.view(torch.uint8)
        )
        scales_exact = torch.equal(stock_scale, candidate_scale)
        boundary = sample_pair(torch, stock_boundary, candidate_boundary)
        component = sample_pair(torch, stock_component, candidate_component)
        numerical = error_metrics(torch, stock_out, candidate_out)
        row = {
            "tokens": tokens,
            "gate_up_shape": list(gate_up.shape),
            "gate_up_stride": list(gate_up.stride()),
            "candidate_q_shape": list(candidate_q.shape),
            "candidate_q_stride": list(candidate_q.stride()),
            "candidate_scale_shape": list(candidate_scale.shape),
            "candidate_scale_stride": list(candidate_scale.stride()),
            "q_codes_exact": q_codes_exact,
            "scales_exact": scales_exact,
            "complete_candidate_output_consumed": True,
            "numerical": numerical,
            "boundary_control_median_ms": statistics.median(
                boundary["control"]
            ),
            "boundary_candidate_median_ms": statistics.median(
                boundary["candidate"]
            ),
            "component_control_median_ms": statistics.median(
                component["control"]
            ),
            "component_candidate_median_ms": statistics.median(
                component["candidate"]
            ),
            "numerical_pass": q_codes_exact
            and scales_exact
            and numerical["relative_l2"] == 0.0
            and numerical["max_abs"] == 0.0
            and numerical["nonfinite"] == 0,
        }
        rows.append(row)
        atomic_json(
            partial_path,
            {
                "schema_version": 1,
                "classification": "exact_consumer_partial",
                "expected_tokens": list(ROWS),
                "completed_tokens": [item["tokens"] for item in rows],
                "rows": rows,
            },
        )
        atomic_json(
            state_path,
            {
                "schema_version": 1,
                "pre_science": False,
                "science_started": True,
                "candidate_cuda_started": True,
                "candidate_science_started": True,
                "completed_tokens": [item["tokens"] for item in rows],
            },
        )

    payload = {
        "schema_version": 1,
        "classification": "exact_consumer_component_result",
        "source_sha256": source_sha256,
        "device": {
            "name": device.name,
            "sm_count": device.multi_processor_count,
            "compute_capability": [device.major, device.minor],
        },
        "producer": {
            "stock": "GeluAndMul -> sglang_per_token_quant_fp8",
            "candidate": "fused_gelu_mul_dynamic_fp8",
        },
        "consumer": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm",
        "weight": {
            "model_id": manifest["model_id"],
            "revision": manifest["revision"],
            "manifest_sha256": digest(args.checkpoint_manifest),
            "index_file": index.name,
            "index_sha256": admitted_files[index.name],
            "shard_file": shard_name,
            "shard_sha256": admitted_files[shard_name],
            "checkpoint_key": DOWN_KEY,
            "source_shape": list(raw_weight.shape),
            "candidate_shape": list(weight_q.shape),
            "candidate_stride": list(weight_q.stride()),
            "scale_shape": list(weight_scale.shape),
        },
        "rows": rows,
        "expected_tokens": list(ROWS),
        "completed_tokens": [row["tokens"] for row in rows],
        "pass": all(row["numerical_pass"] for row in rows)
        and [row["tokens"] for row in rows] == list(ROWS)
        and all(
            row["component_candidate_median_ms"]
            < row["component_control_median_ms"]
            for row in rows
        ),
    }
    atomic_json(args.output, payload)
    return 0 if payload["pass"] else 20


if __name__ == "__main__":
    raise SystemExit(main())
