"""Correctness gate for forward variants and kernels.

Greedy decoding is not bit-exact even on stock code, so a variant is judged against how well stock
agrees with itself: its greedy continuations may share their prefixes with stock a little less
than stock's own repeats do, and the token logprobs on the shared prefix may drift a little more.
A variant that changes the model's behaviour moves both well past those margins.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

MATCH_MARGIN = 0.25  # how far below stock's own agreement a variant's agreement may fall
LOGPROB_FACTOR = 1.5  # how many times stock's own logprob drift a variant may show
MIN_LOGPROB_LIMIT = 0.08  # nats; stock repeats can agree exactly, which would make the limit zero
PREFIX_TOKENS = 8  # a continuation "matches" if at least this many leading tokens agree
# Below these, stock is too unrepeatable on the probe prompts for any margin to mean anything.
BASELINE_FLOOR = {"prefix_match_rate": 0.75, "mean_prefix_fraction": 0.5}


@dataclass(frozen=True)
class Sample:
    """Greedy continuations of the same prompts: token ids and their logprobs, one row per prompt."""

    tokens: Sequence[Sequence[int]]
    logprobs: Sequence[Sequence[float]]


@dataclass(frozen=True)
class Agreement:
    prefix_match_rate: float  # share of prompts whose first PREFIX_TOKENS tokens agree
    mean_prefix_fraction: float  # mean share of each continuation before the first difference
    mean_abs_logprob_delta: float | None  # on the agreeing prefix
    non_finite: int


def _common(a: Sequence[int], b: Sequence[int]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def agreement(reference: Sample, candidate: Sample) -> Agreement:
    if len(reference.tokens) != len(candidate.tokens) or not reference.tokens:
        raise ValueError("samples must cover the same prompts")
    fractions, matches, deltas, non_finite = [], 0, [], 0
    for ref, cand, ref_lp, cand_lp in zip(reference.tokens, candidate.tokens, reference.logprobs, candidate.logprobs):
        common = _common(ref, cand)
        fractions.append(common / max(len(ref), 1))
        matches += common >= min(PREFIX_TOKENS, len(ref))
        non_finite += sum(not math.isfinite(v) for v in cand_lp)
        deltas += [abs(a - b) for a, b in zip(ref_lp[:common], cand_lp[:common]) if math.isfinite(a) and math.isfinite(b)]
    return Agreement(
        prefix_match_rate=matches / len(reference.tokens),
        mean_prefix_fraction=sum(fractions) / len(fractions),
        mean_abs_logprob_delta=sum(deltas) / len(deltas) if deltas else None,
        non_finite=non_finite,
    )


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reasons: tuple[str, ...]
    stock: Agreement  # stock against itself
    variant: Agreement  # variant against stock


def judge(stock: Sample, stock_again: Sample, variant: Sample) -> Verdict:
    own, theirs = agreement(stock, stock_again), agreement(stock, variant)
    stock_bad = sum(not math.isfinite(v) for sample in (stock, stock_again) for row in sample.logprobs for v in row)
    if stock_bad:
        return Verdict(False, (f"stock produced {stock_bad} non-finite logprobs, so its probabilities cannot anchor the gate",), own, theirs)
    unusable = [f"stock {key} {getattr(own, key):.2f} below {floor}" for key, floor in BASELINE_FLOOR.items() if getattr(own, key) < floor]
    if unusable:
        return Verdict(False, ("stock does not repeat itself well enough to judge a variant: " + "; ".join(unusable),), own, theirs)
    reasons = []
    if theirs.non_finite:
        reasons.append(f"{theirs.non_finite} non-finite logprobs")
    if theirs.prefix_match_rate < own.prefix_match_rate - MATCH_MARGIN:
        reasons.append(f"prefix match {theirs.prefix_match_rate:.2f} against stock's {own.prefix_match_rate:.2f}")
    if theirs.mean_prefix_fraction < own.mean_prefix_fraction - MATCH_MARGIN:
        reasons.append(f"shared continuation {theirs.mean_prefix_fraction:.2f} against stock's {own.mean_prefix_fraction:.2f}")
    limit = max(MIN_LOGPROB_LIMIT, LOGPROB_FACTOR * (own.mean_abs_logprob_delta or 0.0))
    if theirs.mean_abs_logprob_delta is not None and theirs.mean_abs_logprob_delta > limit:
        reasons.append(f"logprob drift {theirs.mean_abs_logprob_delta:.3f} over the {limit:.3f} limit")
    return Verdict(not reasons, tuple(reasons), own, theirs)
