#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import pathlib
import random
import statistics
from collections.abc import Callable


HIDDEN = 5376
INTERMEDIATE = 21504
GATE_UP = 2 * INTERMEDIATE
EXPECTED_FP8_UTILS_SHA256 = (
    "a3a130f40974047084e3daff2bd0efbbfe69e197d4c9a5ba3fbc5304dd4e43d9"
)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def summarize(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "minimum_us": ordered[0],
        "median_us": statistics.median(ordered),
        "p90_us": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "maximum_us": ordered[-1],
        "mean_us": statistics.fmean(ordered),
    }


def paired_bootstrap_lower_95(
    stock_us: list[float], candidate_us: list[float], seed: int
) -> float:
    deltas = [a - b for a, b in zip(stock_us, candidate_us, strict=True)]
    rng = random.Random(seed)
    medians = []
    for _ in range(10_000):
        sample = [deltas[rng.randrange(len(deltas))] for _ in deltas]
        medians.append(statistics.median(sample))
    medians.sort()
    return medians[math.floor(0.025 * len(medians))]


def load_candidate(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("gemma4_fp8_weight_stream", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"candidate module cannot be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_weight(k: int, n: int, seed: int):
    import torch

    torch.manual_seed(seed)
    weight = torch.empty_strided(
        (k, n), (1, k), dtype=torch.float8_e4m3fn, device="cuda"
    )
    # All generated E4M3 bit patterns are finite positive normals. Values do
    # not affect GEMM scheduling, while varied bytes catch layout mistakes.
    weight.view(torch.uint8).random_(32, 57)
    scale = torch.linspace(1.0 / 512.0, 1.0 / 256.0, n, device="cuda")
    return weight, scale


def compare(reference, candidate) -> dict[str, float | int | bool]:
    import torch

    delta = candidate.float() - reference.float()
    reference_f = reference.float()
    denominator = torch.linalg.vector_norm(reference_f)
    relative_l2 = (
        torch.linalg.vector_norm(delta) / denominator
        if float(denominator.item()) != 0.0
        else torch.linalg.vector_norm(delta)
    )
    return {
        "bitwise_equal": bool(torch.equal(reference, candidate)),
        "max_absolute_error": float(delta.abs().max().item()),
        "relative_l2": float(relative_l2.item()),
        "reference_nonfinite": int((~torch.isfinite(reference_f)).sum().item()),
        "candidate_nonfinite": int(
            (~torch.isfinite(candidate.float())).sum().item()
        ),
    }


def timed_pairs(
    stock: Callable[[], object],
    candidate: Callable[[], object],
    repetitions: int,
) -> tuple[list[float], list[float]]:
    import torch

    for _ in range(5):
        stock()
        candidate()
    torch.cuda.synchronize()
    stock_us: list[float] = []
    candidate_us: list[float] = []
    for index in range(repetitions):
        order = ((stock, stock_us), (candidate, candidate_us))
        if index % 2:
            order = tuple(reversed(order))
        for call, values in order:
            start = torch.cuda.Event(enable_timing=True)
            end = torch.cuda.Event(enable_timing=True)
            start.record()
            output = call()
            end.record()
            end.synchronize()
            # Consume the returned tensor after timing so a bad wrapper cannot
            # report an unexecuted or partial chain as a scientific sample.
            if not hasattr(output, "shape"):
                raise RuntimeError("MLP chain did not return a tensor")
            values.append(float(start.elapsed_time(end)) * 1000.0)
    return stock_us, candidate_us


def run_shape(module, m: int, repetitions: int, seed: int) -> dict[str, object]:
    import torch
    from sgl_kernel import fp8_scaled_mm
    from sglang.srt.layers.activation import GeluAndMul
    from sglang.srt.layers.quantization.fp8_kernel import (
        sglang_per_token_quant_fp8,
    )

    torch.manual_seed(seed)
    hidden = torch.randn((m, HIDDEN), dtype=torch.bfloat16, device="cuda") / 8
    gate_weight, gate_scale = make_weight(HIDDEN, GATE_UP, seed + 1)
    down_weight, down_scale = make_weight(INTERMEDIATE, HIDDEN, seed + 2)
    activation = GeluAndMul(approximate="tanh")

    def chain(gemm: Callable[..., object]):
        q_hidden, hidden_scale = sglang_per_token_quant_fp8(hidden)
        gate = gemm(q_hidden, gate_weight, hidden_scale, gate_scale)
        activated = activation(gate)
        q_activated, activated_scale = sglang_per_token_quant_fp8(activated)
        output = gemm(q_activated, down_weight, activated_scale, down_scale)
        return gate, activated, q_activated, activated_scale, output

    def stock_gemm(mat_a, mat_b, scales_a, scales_b):
        return fp8_scaled_mm(
            mat_a, mat_b, scales_a, scales_b, torch.bfloat16, None
        )

    candidate_gemm = module.fp8_weight_stream
    stock_stages = chain(stock_gemm)
    candidate_stages = chain(candidate_gemm)
    torch.cuda.synchronize()
    correctness = {
        name: compare(stock_stages[index], candidate_stages[index])
        for index, name in enumerate(
            ("gate_up_bf16", "gelu_product_bf16", "down_input_fp8", "down_scale")
        )
    }
    correctness["final_bf16"] = compare(stock_stages[-1], candidate_stages[-1])
    if not all(
        stage["bitwise_equal"]
        and stage["reference_nonfinite"] == 0
        and stage["candidate_nonfinite"] == 0
        for stage in correctness.values()
    ):
        raise RuntimeError(f"exact output mismatch for M={m}: {correctness}")

    def stock_chain():
        return chain(stock_gemm)[-1]

    def candidate_chain():
        return chain(candidate_gemm)[-1]

    stock_us, candidate_us = timed_pairs(stock_chain, candidate_chain, repetitions)
    lower = paired_bootstrap_lower_95(stock_us, candidate_us, seed)
    delta_median = statistics.median(
        [a - b for a, b in zip(stock_us, candidate_us, strict=True)]
    )
    final = candidate_chain()
    torch.cuda.synchronize()
    return {
        "shape": {
            "rows": m,
            "gate_up_mnk": [m, GATE_UP, HIDDEN],
            "down_mnk": [m, HIDDEN, INTERMEDIATE],
        },
        "correctness": correctness,
        "timing": {
            "scope": "quantize -> gate/up -> GELU(tanh)*up -> quantize -> down",
            "stock": summarize(stock_us),
            "candidate": summarize(candidate_us),
            "paired_median_saved_us": delta_median,
            "paired_bootstrap_lower_95_saved_us": lower,
            "statistically_positive": lower > 0.0,
            "repetitions": repetitions,
            "order": "alternating paired CUDA events",
        },
        "consumer": {
            "final_shape": list(final.shape),
            "final_dtype": str(final.dtype),
            "final_checksum": float(final.float().sum().item()),
            "complete_result_persisted": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--rows", choices=("32", "384", "both"), default="both")
    parser.add_argument("--repetitions", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260725)
    args = parser.parse_args()
    if args.repetitions < 20:
        raise ValueError("at least 20 repetitions are required")

    import torch
    from sglang.srt.layers.quantization import fp8_utils

    if not torch.cuda.is_available():
        raise RuntimeError("runner requires CUDA")
    if torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("runner requires SM90")
    if "H200" not in torch.cuda.get_device_name().upper():
        raise RuntimeError("runner is bound to NVIDIA H200")
    observed = sha256(pathlib.Path(fp8_utils.__file__))
    if observed != EXPECTED_FP8_UTILS_SHA256:
        raise RuntimeError(f"pinned fp8_utils mismatch: {observed}")

    module = load_candidate(args.module.resolve())
    rows = (32, 384) if args.rows == "both" else (int(args.rows),)
    results = [
        run_shape(module, m, args.repetitions, args.seed + m) for m in rows
    ]
    atomic_json(
        args.output,
        {
            "schema_version": 1,
            "result": "complete_exact_consumer_sample",
            "device": torch.cuda.get_device_name(),
            "device_capability": list(torch.cuda.get_device_capability()),
            "module": {
                "path": str(args.module.resolve()),
                "sha256": sha256(args.module.resolve()),
            },
            "fp8_utils_sha256": observed,
            "seed": args.seed,
            "results": results,
            "decision_rule": {
                "correctness": "every persisted stage is bitwise equal",
                "timing": (
                    "worth one endpoint confirmation iff both exact row geometries "
                    "have a positive paired-bootstrap 95% lower bound; no fixed "
                    "percentage threshold"
                ),
            },
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
