from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import pathlib
import statistics


EXPECTED_FP8_UTILS_SHA256 = "a3a130f40974047084e3daff2bd0efbbfe69e197d4c9a5ba3fbc5304dd4e43d9"


def append(value: object) -> None:
    path = pathlib.Path(os.environ["M384_AUDIT"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def family(prefix: str) -> str:
    leaf = prefix.rsplit(".", 1)[-1]
    return leaf if leaf in {"qkv_proj", "gate_up_proj", "down_proj", "o_proj", "lm_head"} else prefix


def summarize(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "minimum_us": ordered[0],
        "median_us": statistics.median(ordered),
        "p90_us": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "maximum_us": ordered[-1],
        "mean_us": statistics.fmean(ordered),
    }


def timed(callable, repetitions: int = 20) -> list[float]:
    import torch

    for _ in range(4):
        callable()
    torch.cuda.synchronize()
    values = []
    for _ in range(repetitions):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        callable()
        end.record()
        end.synchronize()
        values.append(float(start.elapsed_time(end)) * 1000.0)
    return values


def load_candidate():
    path = pathlib.Path(os.environ["M384_MODULE"])
    spec = importlib.util.spec_from_file_location("gemma4_fp8_m384_cluster_n", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"candidate module cannot be loaded:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install() -> None:
    import torch
    from sglang.srt.layers.quantization import fp8_utils
    from sglang.srt.layers.quantization.fp8 import Fp8LinearMethod

    observed = hashlib.sha256(pathlib.Path(fp8_utils.__file__).read_bytes()).hexdigest()
    if observed != EXPECTED_FP8_UTILS_SHA256:
        raise RuntimeError(f"pinned FP8 consumer mismatch:{observed}")
    mode = os.environ["M384_MODE"]
    if mode not in {"component", "endpoint"}:
        raise RuntimeError(f"invalid M384_MODE:{mode}")
    candidate = load_candidate()
    original_apply = Fp8LinearMethod.apply
    stock = fp8_utils.fp8_scaled_mm
    active_prefix = "<unbound>"
    measured: set[tuple[str, int, int]] = set()
    observed_paths: set[tuple[str, int, int]] = set()

    def apply(self, layer, x, bias=None):
        nonlocal active_prefix
        previous = active_prefix
        active_prefix = getattr(self, "_bound_prefix", "<unbound>")
        try:
            return original_apply(self, layer, x, bias)
        finally:
            active_prefix = previous

    def selected(mat_a, mat_b, scales_a, scales_b, out_dtype, bias=None):
        m, k = mat_a.shape
        n = mat_b.shape[1]
        if m != 384 or out_dtype != torch.bfloat16 or bias is not None:
            return stock(mat_a, mat_b, scales_a, scales_b, out_dtype, bias)
        if mode == "component" and not pathlib.Path(
            os.environ["M384_COMPONENT_ENABLE"]
        ).exists():
            return stock(mat_a, mat_b, scales_a, scales_b, out_dtype, bias)
        key = (family(active_prefix), n, k)
        if key not in observed_paths:
            append(
                {
                    "phase": "production_candidate_path",
                    "mode": mode,
                    "prefix": active_prefix,
                    "family": key[0],
                    "shape_mnk": [m, n, k],
                    "candidate_symbol": "gemma4_fp8_m384_cluster_n.fp8_m384_cluster_n",
                    "cluster_mnk": [1, 2, 1],
                    "stock_cluster_mnk": [2, 1, 1],
                    "tile_mnk": [128, 128, 128],
                    "stock_grid_ctas": math.ceil(m / 128 / 2) * 2 * math.ceil(n / 128),
                    "candidate_grid_ctas": math.ceil(m / 128) * math.ceil(n / 128 / 2) * 2,
                }
            )
            observed_paths.add(key)
        if mode == "endpoint" or key in measured:
            return candidate.fp8_m384_cluster_n(mat_a, mat_b, scales_a, scales_b)

        reference = stock(mat_a, mat_b, scales_a, scales_b, out_dtype, bias)
        output = candidate.fp8_m384_cluster_n(mat_a, mat_b, scales_a, scales_b)
        torch.cuda.synchronize()
        difference = output.float() - reference.float()
        denominator = torch.linalg.vector_norm(reference.float())
        stock_us = timed(lambda: stock(mat_a, mat_b, scales_a, scales_b, out_dtype, bias))
        candidate_us = timed(
            lambda: candidate.fp8_m384_cluster_n(mat_a, mat_b, scales_a, scales_b)
        )
        append(
            {
                "phase": "exact_real_weight_component",
                "prefix": active_prefix,
                "family": key[0],
                "shape_mnk": [m, n, k],
                "projection": {
                    "bitwise_equal": bool(torch.equal(reference, output)),
                    "max_absolute_error": float(difference.abs().max().item()),
                    "relative_l2": float(
                        (torch.linalg.vector_norm(difference) / denominator).item()
                    ),
                    "reference_nonfinite": int((~torch.isfinite(reference.float())).sum().item()),
                    "candidate_nonfinite": int((~torch.isfinite(output.float())).sum().item()),
                },
                "stock": summarize(stock_us),
                "candidate": summarize(candidate_us),
                "candidate_speedup_fraction": 1
                - statistics.median(candidate_us) / statistics.median(stock_us),
                "repetitions": len(candidate_us),
                "returned_to_unchanged_consumer": True,
            }
        )
        measured.add(key)
        return output

    Fp8LinearMethod.apply = apply
    fp8_utils.fp8_scaled_mm = selected
