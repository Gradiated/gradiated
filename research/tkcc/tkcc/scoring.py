"""Correctness gate and speedup scoring for candidate jobs."""

from __future__ import annotations

import math
from typing import Any, Mapping

PREFIX_TOKENS = 8
MATCH_MARGIN = 0.25
MIN_LOGPROB_DELTA_LIMIT = 0.08
LOGPROB_DELTA_FACTOR = 1.5
MAX_MEAN_LOGPROB_SHIFT = 0.10
ABSOLUTE_FLOOR = {"prefix_match_rate": 0.75, "mean_prefix_fraction": 0.5, "mean_abs_logprob_delta": 0.10}


def _common_prefix(a: list[int], b: list[int]) -> int:
    length = 0
    for left, right in zip(a, b):
        if left != right:
            break
        length += 1
    return length


def _mean_finite(values) -> float | None:
    finite = [v for v in values if math.isfinite(v)]
    return sum(finite) / len(finite) if finite else None


def compare_outputs(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    self_agreement: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Compare greedy continuations and token logprobs against a reference run.

    The stock engine is not deterministic under greedy decoding, so thresholds
    are set relative to ``self_agreement`` (the stock engine against itself):
    agreement may fall at most ``MATCH_MARGIN`` below it, the logprob drift on
    the common prefix may be at most ``LOGPROB_DELTA_FACTOR`` times the stock
    drift, and the mean logprob of the generated tokens must not shift by more
    than ``MAX_MEAN_LOGPROB_SHIFT`` nats. Without calibration, fixed floors apply.
    """
    ref_tokens = reference["tokens"]
    cand_tokens = candidate["tokens"]
    if len(ref_tokens) != len(cand_tokens) or not ref_tokens:
        return {"pass": False, "reason": "request count mismatch"}
    fractions, prefix_hits, deltas = [], 0, []
    non_finite = 0
    for index, (ref, cand) in enumerate(zip(ref_tokens, cand_tokens)):
        common = _common_prefix(ref, cand)
        fractions.append(common / max(len(ref), 1))
        if common >= min(PREFIX_TOKENS, len(ref)):
            prefix_hits += 1
        ref_lp = reference["logprobs"][index]
        cand_lp = candidate["logprobs"][index]
        non_finite += sum(1 for value in cand_lp if not math.isfinite(value))
        for position in range(min(common, len(ref_lp), len(cand_lp))):
            left, right = ref_lp[position], cand_lp[position]
            if math.isfinite(left) and math.isfinite(right):
                deltas.append(abs(left - right))
    metrics = {
        "mean_prefix_fraction": sum(fractions) / len(fractions),
        "prefix_match_rate": prefix_hits / len(ref_tokens),
        "mean_abs_logprob_delta": sum(deltas) / len(deltas) if deltas else None,
        "mean_logprob": _mean_finite(v for row in candidate["logprobs"] for v in row),
    }
    ref_mean = _mean_finite(v for row in reference["logprobs"] for v in row)
    if self_agreement:
        limits = {
            "prefix_match_rate": self_agreement["prefix_match_rate"] - MATCH_MARGIN,
            "mean_prefix_fraction": self_agreement["mean_prefix_fraction"] - MATCH_MARGIN,
            "mean_abs_logprob_delta": max(MIN_LOGPROB_DELTA_LIMIT, LOGPROB_DELTA_FACTOR * (self_agreement["mean_abs_logprob_delta"] or 0.0)),
        }
    else:
        limits = dict(ABSOLUTE_FLOOR)
    reasons = []
    if non_finite:
        reasons.append(f"{non_finite} non-finite logprobs")
    if metrics["prefix_match_rate"] < limits["prefix_match_rate"]:
        reasons.append(f"first {PREFIX_TOKENS} tokens match on {metrics['prefix_match_rate']:.0%} of requests (limit {limits['prefix_match_rate']:.0%})")
    if metrics["mean_prefix_fraction"] < limits["mean_prefix_fraction"]:
        reasons.append(f"mean common prefix {metrics['mean_prefix_fraction']:.0%} (limit {limits['mean_prefix_fraction']:.0%})")
    delta = metrics["mean_abs_logprob_delta"]
    if delta is None or delta > limits["mean_abs_logprob_delta"]:
        reasons.append(f"mean |dlogprob| {delta} (limit {limits['mean_abs_logprob_delta']:.3f})")
    if ref_mean is not None and metrics["mean_logprob"] is not None and abs(metrics["mean_logprob"] - ref_mean) > MAX_MEAN_LOGPROB_SHIFT:
        reasons.append(f"mean generated logprob {metrics['mean_logprob']:.3f} vs stock {ref_mean:.3f}")
    return {"pass": not reasons, "reason": "; ".join(reasons), "limits": limits, **metrics}


def geomean_speedup(measured: Mapping[str, Mapping[str, float]], baseline: Mapping[str, Mapping[str, float]]) -> float:
    ratios = [measured[key]["tps_per_user"] / baseline[key]["tps_per_user"] for key in baseline]
    if not ratios or any(r <= 0 for r in ratios):
        raise ValueError("speedups must be positive")
    return math.exp(sum(math.log(r) for r in ratios) / len(ratios))
