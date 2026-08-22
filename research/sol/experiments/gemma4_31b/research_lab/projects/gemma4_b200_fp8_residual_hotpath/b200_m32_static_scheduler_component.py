#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
from typing import Any, Callable


M = 32
DECODE_STEPS = 358
CONCURRENCY = 32
SHAPES = (
    ("sliding_qkv", 5376, 16384, 50),
    ("sliding_o", 8192, 5376, 50),
    ("global_qkv_k_eq_v_materialized", 5376, 20480, 10),
    ("global_o", 16384, 5376, 10),
    ("gate_up", 5376, 43008, 60),
    ("down", 21504, 5376, 60),
)
EXPECTED_FAMILIES = tuple(row[0] for row in SHAPES)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def tensor_hash(torch: Any, tensor: Any) -> str:
    raw = tensor.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes()
    return hashlib.sha256(raw).hexdigest()


def tensor_contract(tensor: Any) -> dict[str, Any]:
    return {
        "shape": list(tensor.shape),
        "stride": list(tensor.stride()),
        "storage_offset": int(tensor.storage_offset()),
        "dtype": str(tensor.dtype),
        "contiguous": bool(tensor.is_contiguous()),
    }


def numeric_metrics(torch: Any, candidate: Any, stock: Any) -> dict[str, Any]:
    candidate_float = candidate.float().flatten()
    stock_float = stock.float().flatten()
    difference = candidate_float - stock_float
    reference_rms = torch.sqrt(torch.mean(stock_float * stock_float)).clamp_min(
        1e-12
    )
    return {
        "finite": bool(torch.isfinite(candidate_float).all()),
        "bitwise_equal": bool(torch.equal(candidate, stock)),
        "cosine": float(
            torch.nn.functional.cosine_similarity(
                candidate_float, stock_float, dim=0
            )
        ),
        "normalized_rmse": float(
            torch.sqrt(torch.mean(difference * difference)) / reference_rms
        ),
        "max_abs": float(difference.abs().max()),
        "candidate_sha256": tensor_hash(torch, candidate),
        "stock_sha256": tensor_hash(torch, stock),
    }


def timed_call(torch: Any, function: Callable[[], Any]) -> tuple[float, float]:
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    output = function()
    end.record()
    end.synchronize()
    elapsed = float(start.elapsed_time(end))
    consumed_value = float(output[0, 0])
    return elapsed, consumed_value


def paired_timings(
    torch: Any,
    stock: Callable[[], Any],
    candidate: Callable[[], Any],
    repeats: int,
) -> tuple[list[dict[str, Any]], float]:
    rows: list[dict[str, Any]] = []
    checksum = 0.0
    for repetition in range(repeats):
        order = ("stock", "candidate") if repetition % 2 == 0 else (
            "candidate",
            "stock",
        )
        values: dict[str, float] = {}
        for arm in order:
            elapsed, consumed = timed_call(
                torch, stock if arm == "stock" else candidate
            )
            values[arm] = elapsed
            checksum += consumed
        rows.append(
            {
                "repetition": repetition,
                "order": list(order),
                "stock_ms": values["stock"],
                "candidate_ms": values["candidate"],
                "saved_ms": values["stock"] - values["candidate"],
            }
        )
    return rows, checksum


def validate_binding(
    binding: dict[str, Any], runner: Path, candidate_source: Path
) -> None:
    hashes = binding["artifact_hashes"]
    if hashes["runner_sha256"] != sha256(runner):
        raise RuntimeError("runner_binding_mismatch")
    if hashes["candidate_source_sha256"] != sha256(candidate_source):
        raise RuntimeError("candidate_source_binding_mismatch")
    if binding["mechanism"]["candidate_scheduler_tag"] != (
        "cutlass::gemm::StaticPersistentScheduler"
    ):
        raise RuntimeError("candidate_scheduler_binding_mismatch")


def local_validation(output: Path) -> int:
    if len(SHAPES) != 6 or sum(row[3] for row in SHAPES) != 240:
        raise RuntimeError("six_family_geometry_invalid")
    if any(k % 128 or n % 128 for _, k, n, _ in SHAPES):
        raise RuntimeError("shape_alignment_invalid")
    atomic_json(
        output,
        {
            "schema_version": 1,
            "classification": "local_contract_validation",
            "cuda_invoked": False,
            "m": M,
            "expected_families": list(EXPECTED_FAMILIES),
            "multiplicity_per_decode_step": sum(row[3] for row in SHAPES),
            "fp8_gemms_over_completion": (
                sum(row[3] for row in SHAPES) * DECODE_STEPS
            ),
            "endpoint_projection_formula": (
                "358 * weighted_saved_ms_per_step / 1000 / 32"
            ),
        },
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--candidate-source", type=Path)
    parser.add_argument("--build-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=31)
    parser.add_argument("--seed", type=int, default=20260729)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--validate-only", type=Path)
    args = parser.parse_args()

    if args.validate_only is not None:
        return local_validation(args.validate_only)
    required = (
        args.binding,
        args.candidate_source,
        args.build_manifest,
        args.output,
    )
    if any(value is None for value in required):
        parser.error(
            "--binding, --candidate-source, --build-manifest, and --output "
            "are required for CUDA execution"
        )
    assert args.binding is not None
    assert args.candidate_source is not None
    assert args.build_manifest is not None
    assert args.output is not None
    if args.warmup < 2 or args.repeats < 9:
        raise ValueError("warmup>=2 and repeats>=9 required")

    binding = load_json(args.binding)
    validate_binding(binding, Path(__file__).resolve(), args.candidate_source)
    build = load_json(args.build_manifest)
    module_path = Path(build["module_path"])
    if not module_path.is_absolute():
        module_path = args.build_manifest.parent / module_path
    if sha256(module_path) != build["module_sha256"]:
        raise RuntimeError("candidate_module_hash_mismatch")
    if build["candidate_source_sha256"] != sha256(args.candidate_source):
        raise RuntimeError("built_source_hash_mismatch")

    if args.output.exists() and not args.resume:
        raise FileExistsError(f"output already exists: {args.output}")
    args.output.mkdir(parents=True, exist_ok=args.resume)
    completed_rows: dict[str, dict[str, Any]] = {}
    for family in EXPECTED_FAMILIES:
        row_path = args.output / f"ROW_{family}.json"
        if row_path.exists():
            if not args.resume:
                raise RuntimeError(f"unexpected_existing_row:{family}")
            row = load_json(row_path)
            if row.get("name") != family or not row.get("row_complete"):
                raise RuntimeError(f"incomplete_existing_row:{family}")
            completed_rows[family] = row

    import torch
    import vllm
    import vllm._C as vllm_extension
    from vllm import _custom_ops as ops

    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    capability = tuple(torch.cuda.get_device_capability())
    if capability != (10, 0):
        raise RuntimeError(f"sm100_required:{capability}")

    spec = importlib.util.spec_from_file_location(
        build["module_name"], module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("candidate_module_spec_failed")
    candidate_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate_module)
    schedule = dict(candidate_module.schedule_metadata())
    expected_schedule = {
        "scheduler_tag": "cutlass::gemm::StaticPersistentScheduler",
        "stock_scheduler_resolves_to":
            "cutlass::gemm::PersistentTileSchedulerSm100",
        "mainloop_identical_to_stock": True,
        "epilogue_identical_to_stock": True,
    }
    for key, expected in expected_schedule.items():
        if schedule.get(key) != expected:
            raise RuntimeError(f"candidate_schedule_mismatch:{key}")

    stock_extension = Path(vllm_extension.__file__).resolve()
    invocation = {
        "schema_version": 1,
        "classification": "component_invocation_state",
        "candidate_science_started": False,
        "candidate_cuda_started": False,
        "current_family": None,
        "completed_families": sorted(completed_rows),
        "expected_families": list(EXPECTED_FAMILIES),
        "runtime": {
            "vllm_python": str(Path(vllm.__file__).resolve()),
            "vllm_extension": str(stock_extension),
            "vllm_extension_sha256": sha256(stock_extension),
            "candidate_module": str(module_path),
            "candidate_module_sha256": sha256(module_path),
            "candidate_source_sha256": sha256(args.candidate_source),
            "device_name": torch.cuda.get_device_name(),
            "capability": list(capability),
        },
        "schedule_metadata": schedule,
    }
    atomic_json(args.output / "INVOCATION_STATE.json", invocation)

    for index, (name, k, n, multiplicity) in enumerate(SHAPES):
        if name in completed_rows:
            continue
        invocation["current_family"] = name
        atomic_json(args.output / "INVOCATION_STATE.json", invocation)
        try:
            torch.manual_seed(args.seed + index)
            torch.cuda.manual_seed_all(args.seed + index)
            activation_bf16 = (
                torch.randn((M, k), device="cuda", dtype=torch.bfloat16)
                * 0.02
            )
            weight_bf16 = (
                torch.randn((n, k), device="cuda", dtype=torch.bfloat16)
                * 0.02
            )
            weight_nk, weight_scale = ops.scaled_fp8_quant(
                weight_bf16, scale=None
            )
            weight_kn = weight_nk.t()
            activation_fp8, activation_scale = ops.scaled_fp8_quant(
                activation_bf16,
                scale=None,
                use_per_token_if_dynamic=True,
            )
            contracts = {
                "activation_bf16": tensor_contract(activation_bf16),
                "activation_fp8": tensor_contract(activation_fp8),
                "activation_scale": tensor_contract(activation_scale),
                "weight_bf16_nk": tensor_contract(weight_bf16),
                "weight_fp8_kn": tensor_contract(weight_kn),
                "weight_scale": tensor_contract(weight_scale),
            }
            if contracts["activation_scale"]["shape"] not in ([M], [M, 1]):
                raise RuntimeError(f"activation_scale_shape:{name}")
            if contracts["weight_scale"]["shape"] not in ([], [1]):
                raise RuntimeError(f"weight_scale_shape:{name}")
            if weight_kn.stride(0) != 1 or weight_kn.storage_offset() != 0:
                raise RuntimeError(f"weight_orientation:{name}")
            operand_hashes = {
                "activation_fp8": tensor_hash(torch, activation_fp8),
                "activation_scale": tensor_hash(torch, activation_scale),
                "weight_fp8_kn": tensor_hash(torch, weight_kn),
                "weight_scale": tensor_hash(torch, weight_scale),
            }

            def stock_gemm() -> Any:
                return ops.cutlass_scaled_mm(
                    activation_fp8,
                    weight_kn,
                    scale_a=activation_scale,
                    scale_b=weight_scale,
                    out_dtype=torch.bfloat16,
                )

            def candidate_gemm() -> Any:
                return candidate_module.m32_static_persistent(
                    activation_fp8,
                    weight_kn,
                    activation_scale,
                    weight_scale,
                )

            def stock_quant_gemm() -> Any:
                quantized, scale = ops.scaled_fp8_quant(
                    activation_bf16,
                    scale=None,
                    use_per_token_if_dynamic=True,
                )
                return ops.cutlass_scaled_mm(
                    quantized,
                    weight_kn,
                    scale_a=scale,
                    scale_b=weight_scale,
                    out_dtype=torch.bfloat16,
                )

            def candidate_quant_gemm() -> Any:
                quantized, scale = ops.scaled_fp8_quant(
                    activation_bf16,
                    scale=None,
                    use_per_token_if_dynamic=True,
                )
                return candidate_module.m32_static_persistent(
                    quantized, weight_kn, scale, weight_scale
                )

            stock_output = stock_gemm()
            torch.cuda.synchronize()
            invocation["stock_first_call_complete"] = name
            atomic_json(args.output / "INVOCATION_STATE.json", invocation)
            invocation["candidate_science_started"] = True
            invocation["candidate_cuda_started"] = True
            atomic_json(args.output / "INVOCATION_STATE.json", invocation)
            candidate_output = candidate_gemm()
            torch.cuda.synchronize()
            invocation["candidate_first_call_complete"] = name
            atomic_json(args.output / "INVOCATION_STATE.json", invocation)
            correctness = numeric_metrics(
                torch, candidate_output, stock_output
            )
            if not correctness["finite"]:
                raise RuntimeError(f"candidate_nonfinite:{name}")
            if not correctness["bitwise_equal"]:
                row = {
                    "schema_version": 1,
                    "row_complete": True,
                    "classification": "component_exactness_stop",
                    "name": name,
                    "m": M,
                    "k": k,
                    "n": n,
                    "multiplicity_per_decode_step": multiplicity,
                    "correctness": correctness,
                    "operand_hashes": operand_hashes,
                    "tensor_contracts": contracts,
                    "timing_rows": [],
                }
                atomic_json(args.output / f"ROW_{name}.json", row)
                completed_rows[name] = row
                terminal = {
                    "schema_version": 1,
                    "classification": "component_exactness_stop",
                    "science_consumed": True,
                    "candidate_science_started": True,
                    "expected_rows": list(EXPECTED_FAMILIES),
                    "completed_rows": sorted(completed_rows),
                    "failed_family": name,
                    "rows": list(completed_rows.values()),
                }
                atomic_json(args.output / "TERMINAL.json", terminal)
                return 0

            for _ in range(args.warmup):
                stock_gemm()
            torch.cuda.synchronize()
            for _ in range(args.warmup):
                candidate_gemm()
            torch.cuda.synchronize()
            gemm_rows, gemm_checksum = paired_timings(
                torch, stock_gemm, candidate_gemm, args.repeats
            )
            for _ in range(args.warmup):
                stock_quant_gemm()
            torch.cuda.synchronize()
            for _ in range(args.warmup):
                candidate_quant_gemm()
            torch.cuda.synchronize()
            quant_rows, quant_checksum = paired_timings(
                torch,
                stock_quant_gemm,
                candidate_quant_gemm,
                args.repeats,
            )
            stock_gemm_values = [row["stock_ms"] for row in gemm_rows]
            candidate_gemm_values = [
                row["candidate_ms"] for row in gemm_rows
            ]
            stock_quant_values = [row["stock_ms"] for row in quant_rows]
            candidate_quant_values = [
                row["candidate_ms"] for row in quant_rows
            ]
            row = {
                "schema_version": 1,
                "row_complete": True,
                "classification": "component_family_measurement",
                "name": name,
                "m": M,
                "k": k,
                "n": n,
                "multiplicity_per_decode_step": multiplicity,
                "correctness": correctness,
                "operand_hashes": operand_hashes,
                "tensor_contracts": contracts,
                "producer_contract": {
                    "activation": (
                        "QuantFP8.forward_cuda -> ops.scaled_fp8_quant("
                        "scale=None,use_per_token_if_dynamic=True)"
                    ),
                    "activation_scale_granularity": "one FP32 scale per token",
                    "weight": (
                        "Fp8OnlineLinearMethod.process_weights_after_loading "
                        "-> ops.scaled_fp8_quant(weight_NK,scale=None).t()"
                    ),
                    "weight_scale_granularity": "one FP32 scale per tensor",
                    "scale_convention": (
                        "forward scale; epilogue multiplies activation and "
                        "weight scales"
                    ),
                    "quantizer_reciprocal": (
                        "input is multiplied by reciprocal(forward scale)"
                    ),
                },
                "candidate_path": {
                    "module_sha256": build["module_sha256"],
                    "source_sha256": build["candidate_source_sha256"],
                    "symbol": schedule["candidate_symbol"],
                    "scheduler": schedule["scheduler_tag"],
                },
                "gemm_timing": {
                    "unit": "milliseconds per one M32 family invocation",
                    "method": "alternating paired profiler-off CUDA events",
                    "rows": gemm_rows,
                    "stock_p50_ms": statistics.median(stock_gemm_values),
                    "candidate_p50_ms":
                        statistics.median(candidate_gemm_values),
                    "paired_saved_p50_ms": statistics.median(
                        row["saved_ms"] for row in gemm_rows
                    ),
                    "consumer_checksum": gemm_checksum,
                },
                "quant_and_gemm_timing": {
                    "unit": "milliseconds per one M32 family invocation",
                    "method": "alternating paired profiler-off CUDA events",
                    "rows": quant_rows,
                    "stock_p50_ms": statistics.median(stock_quant_values),
                    "candidate_p50_ms":
                        statistics.median(candidate_quant_values),
                    "paired_saved_p50_ms": statistics.median(
                        row["saved_ms"] for row in quant_rows
                    ),
                    "consumer_checksum": quant_checksum,
                },
            }
            atomic_json(args.output / f"ROW_{name}.json", row)
            completed_rows[name] = row
            invocation["completed_families"] = sorted(completed_rows)
            atomic_json(args.output / "INVOCATION_STATE.json", invocation)
            del (
                activation_bf16,
                weight_bf16,
                weight_nk,
                weight_scale,
                weight_kn,
                activation_fp8,
                activation_scale,
                stock_output,
                candidate_output,
            )
            torch.cuda.empty_cache()
        except Exception as error:
            diagnostic = {
                "schema_version": 1,
                "classification": "component_attempt_repairable",
                "error_type": type(error).__name__,
                "error": str(error),
                "failed_family": name,
                "completed_families": sorted(completed_rows),
                "candidate_cuda_started": bool(
                    invocation["candidate_cuda_started"]
                ),
                "candidate_science_started": bool(
                    invocation["candidate_science_started"]
                ),
                "retry_scope": f"consumer:{name}",
                "resume_contract": "preserve completed rows and retry only failed family",
            }
            atomic_json(args.output / "REPAIRABLE.json", diagnostic)
            raise

    rows = [completed_rows[name] for name in EXPECTED_FAMILIES]
    if len(rows) != 6:
        raise RuntimeError("required_row_ledger_incomplete")
    weighted_stock_ms = sum(
        row["multiplicity_per_decode_step"]
        * row["quant_and_gemm_timing"]["stock_p50_ms"]
        for row in rows
    )
    weighted_candidate_ms = sum(
        row["multiplicity_per_decode_step"]
        * row["quant_and_gemm_timing"]["candidate_p50_ms"]
        for row in rows
    )
    weighted_saved_ms = weighted_stock_ms - weighted_candidate_ms
    projected_saving = (
        DECODE_STEPS * weighted_saved_ms / 1000.0 / CONCURRENCY
    )
    family_regressions = {
        row["name"]: (
            row["quant_and_gemm_timing"]["candidate_p50_ms"]
            / row["quant_and_gemm_timing"]["stock_p50_ms"]
            - 1.0
        )
        for row in rows
    }
    gates = {
        "six_rows_complete": True,
        "bitwise_correct": all(
            row["correctness"]["bitwise_equal"] for row in rows
        ),
        "no_family_regression_over_5pct": max(family_regressions.values())
        <= 0.05,
        "projected_saving_at_least_0p001_s_per_request": projected_saving
        >= 0.001,
        "weighted_quant_and_gemm_gain_positive": weighted_saved_ms > 0.0,
    }
    classification = (
        "component_positive_for_director_endpoint_disposition"
        if all(gates.values())
        else "component_negative_stop"
    )
    terminal = {
        "schema_version": 1,
        "classification": classification,
        "science_consumed": True,
        "candidate_science_started": True,
        "candidate_cuda_started": True,
        "expected_rows": list(EXPECTED_FAMILIES),
        "completed_rows": list(EXPECTED_FAMILIES),
        "rows": rows,
        "gates": gates,
        "family_quant_and_gemm_regressions": family_regressions,
        "weighted_stock_quant_and_gemm_p50_ms": weighted_stock_ms,
        "weighted_candidate_quant_and_gemm_p50_ms": weighted_candidate_ms,
        "weighted_saved_quant_and_gemm_p50_ms": weighted_saved_ms,
        "weighted_gain_fraction": (
            weighted_saved_ms / weighted_stock_ms
            if weighted_stock_ms
            else math.nan
        ),
        "projected_endpoint_saving_seconds_per_request": projected_saving,
        "endpoint_projection_formula": (
            "358 * weighted_saved_ms_per_decode_step / 1000 / 32"
        ),
        "stock_extension_sha256": sha256(stock_extension),
        "candidate_module_sha256": build["module_sha256"],
        "candidate_source_sha256": build["candidate_source_sha256"],
        "runner_sha256": sha256(Path(__file__).resolve()),
        "oracle": (
            "bitwise stock/candidate BF16 output on the same official "
            "per-token activation and per-tensor weight FP8 operands"
        ),
        "measurement": (
            "31 alternating paired profiler-off warm CUDA-event samples per "
            "family; every timed output consumed outside the event interval"
        ),
    }
    atomic_json(args.output / "TERMINAL.json", terminal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
