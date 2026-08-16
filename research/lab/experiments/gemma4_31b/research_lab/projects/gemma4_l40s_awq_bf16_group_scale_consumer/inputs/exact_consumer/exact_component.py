#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import statistics
from typing import Any, Callable


MS = (1, 2, 4, 8, 12, 16, 24, 32)
HIDDEN = 5376
INTERMEDIATE = 21504
GATE_UP = 43008
GROUP_SIZE = 128
LAYERS = 60
DECODE_STEPS = 357
CONTROL_REQUEST_SECONDS = 1.8853265455
SEED = 20260724
PREFIX = "model.language_model.layers.0.mlp"


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(project: pathlib.Path, manifest_path: pathlib.Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    failures = []
    for relative, expected in manifest["files"].items():
        path = project / relative
        observed = sha256(path) if path.is_file() else None
        if observed != expected:
            failures.append(
                {
                    "path": relative,
                    "expected_sha256": expected,
                    "observed_sha256": observed,
                }
            )
    if failures:
        raise RuntimeError(f"immutable_manifest_mismatch:{json.dumps(failures)}")
    return manifest


def distribution(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "raw_ms": values,
        "minimum_ms": ordered[0],
        "p50_ms": statistics.median(ordered),
        "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "maximum_ms": ordered[-1],
    }


def timed(torch, function: Callable[[], Any], warmups: int, iterations: int):
    output = None
    for _ in range(warmups):
        output = function()
    torch.cuda.synchronize()
    values = []
    for _ in range(iterations):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        output = function()
        end.record()
        end.synchronize()
        values.append(float(start.elapsed_time(end)))
    return distribution(values), output


def error_metrics(torch, actual, reference) -> dict[str, Any]:
    actual32 = actual.float()
    reference32 = reference.float()
    delta = actual32 - reference32
    norm = torch.linalg.vector_norm(reference32).clamp_min(1e-12)
    return {
        "maximum_absolute": float(delta.abs().max()),
        "relative_l2": float(torch.linalg.vector_norm(delta) / norm),
        "cosine_similarity": float(
            torch.nn.functional.cosine_similarity(
                actual32.flatten(),
                reference32.flatten(),
                dim=0,
            )
        ),
        "nonfinite_count": int((~torch.isfinite(actual32)).sum()),
        "nontrivial": bool(float(actual32.abs().max()) > 1e-8),
    }


def npy_to_cuda(torch, numpy, path: pathlib.Path, dtype=None):
    array = numpy.load(path, mmap_mode="r", allow_pickle=False)
    tensor = torch.from_numpy(array)
    if dtype is not None:
        tensor = tensor.view(dtype)
    return tensor.cuda().contiguous()


def load_candidate(torch, numpy, root: pathlib.Path, projection: str) -> dict:
    return {
        "qweight": npy_to_cuda(
            torch,
            numpy,
            root / f"{projection}.qweight.npy",
        ),
        "zeros": npy_to_cuda(
            torch,
            numpy,
            root / f"{projection}.zeros.npy",
        ),
        "scales": npy_to_cuda(
            torch,
            numpy,
            root / f"{projection}.scales_bf16_bits.npy",
            torch.bfloat16,
        ),
    }


def load_awq_reference(torch, safe_open, awq_dequantize, source: pathlib.Path):
    tensors = {}
    with safe_open(str(source), framework="pt", device="cpu") as handle:
        for projection in ("gate_proj", "up_proj", "down_proj"):
            base = f"{PREFIX}.{projection}"
            qweight = handle.get_tensor(f"{base}.qweight").cuda()
            qzeros = handle.get_tensor(f"{base}.qzeros").cuda()
            scales = handle.get_tensor(f"{base}.scales").cuda()
            tensors[projection] = awq_dequantize(qweight, scales, qzeros)
    return tensors


def fp8_weight(torch, weight):
    scale = weight.float().abs().amax(dim=0).div(448.0).clamp_min(1e-8)
    return (weight / scale).to(torch.float8_e4m3fn), scale.float()


def chunked_reference_mm(torch, activation, weight, chunk: int = 2048):
    outputs = []
    for start in range(0, weight.size(1), chunk):
        stop = min(start + chunk, weight.size(1))
        outputs.append(
            torch.mm(
                activation.float(),
                weight[:, start:stop].float(),
            )
        )
    return torch.cat(outputs, dim=1)


def profiler_kernel_names(torch, function: Callable[[], Any]) -> list[str]:
    with torch.profiler.profile(
        activities=[torch.profiler.ProfilerActivity.CUDA]
    ) as profile:
        output = function()
        output.float().square().sum().item()
    return sorted(
        {
            event.name
            for event in profile.events()
            if str(event.device_type).lower().endswith("cuda")
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--warmups", type=int, default=10)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument(
        "--counter-probe",
        choices=("candidate", "control"),
        default=None,
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    invocation_path = args.output / "INVOCATION_STATE.json"
    state = {
        "schema_version": 1,
        "candidate_cuda_started": False,
        "candidate_science_started": False,
        "control_science_started": False,
        "completed_m": [],
    }
    atomic_json(invocation_path, state)
    manifest = verify_manifest(args.project, args.manifest)

    import numpy
    import torch
    from safetensors import safe_open
    import exact_awq_sm89
    from sglang.srt.hardware_backend.gpu.quantization import awq_kernels
    from sglang.srt.layers.activation import GeluAndMul
    from sglang.srt.layers.quantization import fp8_utils
    from sglang.srt.layers.quantization.fp8_kernel import (
        sglang_per_token_quant_fp8,
    )

    if not torch.cuda.is_available():
        raise RuntimeError("typed_hardware_blocker:cuda_unavailable")
    properties = torch.cuda.get_device_properties(0)
    if "L40S" not in properties.name or (
        properties.major,
        properties.minor,
    ) != (8, 9):
        raise RuntimeError(
            f"typed_hardware_blocker:exact_l40s_sm89_required:"
            f"{properties.name}:{properties.major}.{properties.minor}"
        )

    producer_root = (
        args.project
        / "inputs/exact_consumer/producer/layer0_exact_compute_v1"
    )
    source = (
        args.project
        / "inputs/exact_consumer/producer/"
        "layer0_mlp_awq-871a79d70b4fe23a.safetensors"
    )
    gate = load_candidate(torch, numpy, producer_root, "gate_proj")
    up = load_candidate(torch, numpy, producer_root, "up_proj")
    down = load_candidate(torch, numpy, producer_root, "down_proj")
    gate_up = {
        name: torch.cat((gate[name], up[name]), dim=1 if name != "qweight" else 0)
        .contiguous()
        for name in ("qweight", "zeros", "scales")
    }
    references = load_awq_reference(
        torch,
        safe_open,
        awq_kernels.awq_dequantize,
        source,
    )
    gate_up_reference = torch.cat(
        (references["gate_proj"], references["up_proj"]),
        dim=1,
    ).contiguous()
    down_reference = references["down_proj"].contiguous()
    gate_up_fp8, gate_up_fp8_scale = fp8_weight(torch, gate_up_reference)
    down_fp8, down_fp8_scale = fp8_weight(torch, down_reference)
    activation = GeluAndMul(approximate="tanh")

    def buffers(m: int) -> dict:
        return {
            "xq": torch.empty(
                (m, HIDDEN),
                device="cuda",
                dtype=torch.int8,
            ),
            "xs": torch.empty((m,), device="cuda", dtype=torch.float16),
            "gate_up": torch.empty(
                (m, GATE_UP),
                device="cuda",
                dtype=torch.bfloat16,
            ),
            "aq": torch.empty(
                (m, INTERMEDIATE),
                device="cuda",
                dtype=torch.int8,
            ),
            "as": torch.empty((m,), device="cuda", dtype=torch.float16),
            "output": torch.empty(
                (m, HIDDEN),
                device="cuda",
                dtype=torch.bfloat16,
            ),
        }

    def candidate_chain(x, work):
        exact_awq_sm89.quantize_bf16_s8(x, work["xq"], work["xs"])
        exact_awq_sm89.exact_awq_w4a8_gemm(
            work["xq"],
            gate_up["qweight"],
            gate_up["zeros"],
            gate_up["scales"],
            work["xs"],
            work["gate_up"],
        )
        exact_awq_sm89.gelu_mul_quant_s8(
            work["gate_up"],
            work["aq"],
            work["as"],
        )
        exact_awq_sm89.exact_awq_w4a8_gemm(
            work["aq"],
            down["qweight"],
            down["zeros"],
            down["scales"],
            work["as"],
            work["output"],
        )
        return work["output"]

    def reference_chain(work):
        dequantized_input = (
            work["xq"].float() * work["xs"].float().unsqueeze(1)
        )
        gate_up_output = chunked_reference_mm(
            torch,
            dequantized_input,
            gate_up_reference,
        ).to(torch.bfloat16)
        reference_aq = torch.empty_like(work["aq"])
        reference_as = torch.empty_like(work["as"])
        exact_awq_sm89.gelu_mul_quant_s8(
            gate_up_output,
            reference_aq,
            reference_as,
        )
        dequantized_activation = (
            reference_aq.float() * reference_as.float().unsqueeze(1)
        )
        return chunked_reference_mm(
            torch,
            dequantized_activation,
            down_reference,
        ).to(torch.bfloat16)

    def control_chain(x):
        xq, xs = sglang_per_token_quant_fp8(x)
        gate_up_output = fp8_utils.fp8_scaled_mm(
            xq,
            gate_up_fp8,
            xs,
            gate_up_fp8_scale,
            out_dtype=torch.bfloat16,
            bias=None,
        )
        activated = activation(gate_up_output)
        aq, activation_scale = sglang_per_token_quant_fp8(activated)
        return fp8_utils.fp8_scaled_mm(
            aq,
            down_fp8,
            activation_scale,
            down_fp8_scale,
            out_dtype=torch.bfloat16,
            bias=None,
        )

    if args.counter_probe is not None:
        generator = torch.Generator(device="cuda").manual_seed(SEED + 32)
        x = torch.empty((32, HIDDEN), device="cuda", dtype=torch.bfloat16)
        x.normal_(mean=0.0, std=0.7, generator=generator)
        work = buffers(32)
        state[f"{args.counter_probe}_science_started"] = True
        state[f"{args.counter_probe}_cuda_started"] = True
        atomic_json(invocation_path, state)
        torch.cuda.cudart().cudaProfilerStart()
        output = (
            candidate_chain(x, work)
            if args.counter_probe == "candidate"
            else control_chain(x)
        )
        torch.cuda.synchronize()
        torch.cuda.cudart().cudaProfilerStop()
        terminal = {
            "schema_version": 1,
            "classification": "counter_probe_complete",
            "arm": args.counter_probe,
            "m": 32,
            "finite": bool(torch.isfinite(output).all()),
            "nontrivial": bool(float(output.float().abs().max()) > 1e-8),
            "output_consumed_sum_squares": float(
                output.float().square().sum()
            ),
        }
        atomic_json(args.output / "COUNTER_TERMINAL.json", terminal)
        return 0

    rows = []
    m32_candidate = None
    m32_control = None
    for m in MS:
        generator = torch.Generator(device="cuda").manual_seed(SEED * 100 + m)
        x = torch.empty((m, HIDDEN), device="cuda", dtype=torch.bfloat16)
        x.normal_(mean=0.0, std=0.7, generator=generator)
        work = buffers(m)

        state["candidate_cuda_started"] = True
        atomic_json(invocation_path, state)
        candidate = candidate_chain(x, work)
        torch.cuda.synchronize()
        state["candidate_science_started"] = True
        atomic_json(invocation_path, state)
        reference = reference_chain(work)
        control = control_chain(x)
        torch.cuda.synchronize()
        state["control_science_started"] = True
        atomic_json(invocation_path, state)
        candidate_timing, candidate = timed(
            torch,
            lambda: candidate_chain(x, work),
            args.warmups,
            args.iterations,
        )
        control_timing, control = timed(
            torch,
            lambda: control_chain(x),
            args.warmups,
            args.iterations,
        )
        candidate_error = error_metrics(torch, candidate, reference)
        control_error = error_metrics(torch, control, reference)
        row = {
            "m": m,
            "shape": {
                "gate_up": [m, HIDDEN, GATE_UP],
                "down": [m, INTERMEDIATE, HIDDEN],
            },
            "candidate": {
                "timing": candidate_timing,
                "vs_original_awq_dequantized_oracle": candidate_error,
                "input_saturation_fraction": float(
                    (work["xq"].abs() == 127).float().mean()
                ),
                "intermediate_saturation_fraction": float(
                    (work["aq"].abs() == 127).float().mean()
                ),
                "output_consumed_sum_squares": float(
                    candidate.float().square().sum()
                ),
            },
            "control": {
                "timing": control_timing,
                "vs_original_awq_dequantized_oracle": control_error,
                "output_consumed_sum_squares": float(
                    control.float().square().sum()
                ),
            },
            "speedup": (
                control_timing["p50_ms"] / candidate_timing["p50_ms"]
            ),
            "correctness_pass": (
                candidate_error["nonfinite_count"] == 0
                and candidate_error["relative_l2"] <= 0.02
                and candidate_error["cosine_similarity"] >= 0.999
            ),
        }
        rows.append(row)
        atomic_json(args.output / f"ROW_M{m}.json", row)
        state["completed_m"].append(m)
        atomic_json(invocation_path, state)
        if m == 32:
            m32_candidate = lambda x=x, work=work: candidate_chain(x, work)
            m32_control = lambda x=x: control_chain(x)

    boundary_rows = []
    for name, value in (
        ("zero", 0.0),
        ("positive_extreme", 4.0),
        ("negative_extreme", -4.0),
    ):
        x = torch.full(
            (1, HIDDEN),
            value,
            device="cuda",
            dtype=torch.bfloat16,
        )
        work = buffers(1)
        output = candidate_chain(x, work)
        torch.cuda.synchronize()
        boundary_rows.append(
            {
                "case": name,
                "finite": bool(torch.isfinite(output).all()),
                "output_sum_squares": float(
                    output.float().square().sum()
                ),
            }
        )

    assert m32_candidate is not None and m32_control is not None
    candidate_kernels = profiler_kernel_names(torch, m32_candidate)
    control_kernels = profiler_kernel_names(torch, m32_control)
    row32 = next(row for row in rows if row["m"] == 32)
    saved_seconds = (
        row32["control"]["timing"]["p50_ms"]
        - row32["candidate"]["timing"]["p50_ms"]
    ) / 1000.0 * LAYERS * DECODE_STEPS / 32
    physical = {
        "useful_flops_m32": int(
            2 * 32 * (HIDDEN * GATE_UP + INTERMEDIATE * HIDDEN)
        ),
        "packed_weight_bytes": int(
            (HIDDEN * GATE_UP + INTERMEDIATE * HIDDEN) / 2
        ),
        "bf16_group_scale_bytes": int(
            2
            * (
                HIDDEN // GROUP_SIZE * GATE_UP
                + INTERMEDIATE // GROUP_SIZE * HIDDEN
            )
        ),
        "fp8_weight_bytes": int(
            HIDDEN * GATE_UP + INTERMEDIATE * HIDDEN
        ),
        "candidate_dynamic_shared_memory_bytes": 32960,
        "candidate_threads_per_block": 128,
        "gate_up_grid_blocks": GATE_UP // 64,
        "gate_up_grid_waves_l40s": (GATE_UP // 64) / 142,
        "down_grid_blocks": HIDDEN // 64,
        "down_grid_waves_l40s": (HIDDEN // 64) / 142,
    }
    terminal = {
        "schema_version": 1,
        "classification": "component_complete",
        "pass": (
            all(row["correctness_pass"] for row in rows)
            and all(row["finite"] for row in boundary_rows)
        ),
        "identity": {
            "gpu": properties.name,
            "capability": [properties.major, properties.minor],
            "sm_count": properties.multi_processor_count,
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "manifest_sha256": sha256(args.manifest),
            "manifest": manifest,
            "candidate_symbols": [
                "exact_awq_sm89.quantize_bf16_s8",
                "exact_awq_sm89.exact_awq_w4a8_gemm",
                "exact_awq_sm89.gelu_mul_quant_s8",
            ],
            "control_symbols": [
                "sglang_per_token_quant_fp8",
                "fp8_scaled_mm",
                "GeluAndMul",
            ],
        },
        "physical_model": physical,
        "candidate_kernel_names_m32": candidate_kernels,
        "control_kernel_names_m32": control_kernels,
        "candidate_path_pass": (
            any("dense_kernel0" in name for name in candidate_kernels)
            and any(
                "gelu_mul_quant_s8_kernel" in name
                for name in candidate_kernels
            )
        ),
        "boundary_rows": boundary_rows,
        "rows": rows,
        "call_weighted_bound": {
            "basis": (
                "M32 p50, 60 MLP layers, 357 post-first-token "
                "decode steps, 32 requests"
            ),
            "saved_seconds_per_request": saved_seconds,
            "whole_request_reduction_fraction": (
                saved_seconds / CONTROL_REQUEST_SECONDS
            ),
            "control_request_seconds": CONTROL_REQUEST_SECONDS,
        },
        "complete_outputs_consumed": True,
    }
    terminal["pass"] = bool(
        terminal["pass"] and terminal["candidate_path_pass"]
    )
    terminal["classification"] = (
        "component_positive"
        if terminal["pass"] and row32["speedup"] > 1.0
        else "component_correct_but_slower"
        if terminal["pass"]
        else "component_reject"
    )
    atomic_json(args.output / "TERMINAL.json", terminal)
    return 0 if terminal["pass"] else 72


if __name__ == "__main__":
    raise SystemExit(main())
