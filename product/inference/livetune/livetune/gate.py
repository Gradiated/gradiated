"""Correctness gate for forward variants and kernels.

Greedy decoding is not bit-exact even on stock code, so a variant is judged against how well stock
agrees with itself: its greedy continuations may share their prefixes with stock a little less
than stock's own repeats do, and the token logprobs on the shared prefix may drift a little more.
A variant that changes the model's behaviour moves both well past those margins.

Some models do not repeat at all: GLM-5.3 Flash's greedy decoding diverges by token 8 between
identical stock runs, and its sparse attention rules out deterministic inference. There the prompt
itself is scored, teacher-forced, under both. Run-to-run noise moves those logprobs both ways and
cancels in the mean; a real numeric change shifts them one way. A x1.05 logit scale shifted them by
-0.083 nats (z = -14) against stock's own -0.012, while its mean absolute drift (0.29 against 0.21)
hid in the noise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

MATCH_MARGIN = 0.25  # how far below stock's own agreement a variant's agreement may fall
LOGPROB_FACTOR = 1.5  # how many times stock's own logprob drift a variant may show
MIN_LOGPROB_LIMIT = 0.08  # nats; stock repeats can agree exactly, which would make the limit zero
PREFIX_TOKENS = 8  # a continuation "matches" if at least this many leading tokens agree
# Below these, stock is too unrepeatable on the probe prompts for greedy agreement to mean anything.
BASELINE_FLOOR = {"prefix_match_rate": 0.75, "mean_prefix_fraction": 0.5}
BIAS_FACTOR = 3.0  # how many times stock's own mean scored-logprob shift a variant may show
MIN_BIAS_LIMIT = 0.03  # nats
BIAS_Z = 4.0  # and the shift must be this many standard errors from zero to count
# A greedy shortfall must also be unlikely as chance. With 8 prompts on a model that repeats 6 of 8,
# 3 of 8 is within noise (p = 0.16); against a stock that repeats 8 of 8 it is not (p = 0.013), nor is a
# broken kernel's 0 of 8 against 6 (p = 0.004). Probe with 16 prompts or more: 8 leave little power.
MATCH_P = 0.02
FRACTION_Z = 3.0  # paired over the same prompts


@dataclass(frozen=True)
class Sample:
    """Greedy continuations of the same prompts: token ids and their logprobs, one row per prompt."""

    tokens: Sequence[Sequence[int]]
    logprobs: Sequence[Sequence[float]]
    scored: Sequence[Sequence[float]] = ()  # teacher-forced logprobs of each prompt's own tail tokens


@dataclass(frozen=True)
class Agreement:
    prefix_match_rate: float  # share of prompts whose first PREFIX_TOKENS tokens agree
    mean_prefix_fraction: float  # mean share of each continuation before the first difference
    mean_abs_logprob_delta: float | None  # on the agreeing prefix
    non_finite: int
    scored_shift: float | None = None  # mean of candidate minus reference scored logprobs
    scored_shift_se: float | None = None
    matches: int = 0  # prompts whose first PREFIX_TOKENS tokens agree
    prefix_fractions: tuple[float, ...] = ()  # per prompt, the share before the first difference


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
    shifts = [b - a for ref, cand in zip(reference.scored, candidate.scored) for a, b in zip(ref, cand)
              if math.isfinite(a) and math.isfinite(b)]
    non_finite += sum(not math.isfinite(v) for row in candidate.scored for v in row)
    shift = se = None
    if len(shifts) > 1:
        shift = sum(shifts) / len(shifts)
        se = math.sqrt(sum((v - shift) ** 2 for v in shifts) / (len(shifts) - 1) / len(shifts))
    return Agreement(
        prefix_match_rate=matches / len(reference.tokens),
        mean_prefix_fraction=sum(fractions) / len(fractions),
        mean_abs_logprob_delta=sum(deltas) / len(deltas) if deltas else None,
        non_finite=non_finite,
        scored_shift=shift,
        scored_shift_se=se,
        matches=matches,
        prefix_fractions=tuple(fractions),
    )


def fewer_matches_p(variant: int, stock: int, prompts: int) -> float:
    """One-sided Fisher exact p that the variant matches stock less often than stock matches itself."""
    total = variant + stock
    ways = math.comb(2 * prompts, total)
    return sum(math.comb(prompts, x) * math.comb(prompts, total - x) for x in range(0, variant + 1) if total - x <= prompts) / ways


def shorter_continuations_z(stock: Sequence[float], variant: Sequence[float]) -> float:
    """Paired z of how much shorter the variant's agreeing continuations are, prompt by prompt."""
    differences = [a - b for a, b in zip(stock, variant)]
    if len(differences) < 2:
        return 0.0
    mean = sum(differences) / len(differences)
    se = math.sqrt(sum((d - mean) ** 2 for d in differences) / (len(differences) - 1) / len(differences))
    return math.inf if se == 0 and mean > 0 else (mean / se if se else 0.0)


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reasons: tuple[str, ...]
    stock: Agreement  # stock against itself
    variant: Agreement  # variant against stock


def judge(stock: Sample, stock_again: Sample, variant: Sample) -> Verdict:
    own, theirs = agreement(stock, stock_again), agreement(stock, variant)
    stock_bad = sum(not math.isfinite(v) for sample in (stock, stock_again) for rows in (sample.logprobs, sample.scored)
                    for row in rows for v in row)
    if stock_bad:
        return Verdict(False, (f"stock produced {stock_bad} non-finite logprobs, so its probabilities cannot anchor the gate",), own, theirs)
    unusable = [f"stock {key} {getattr(own, key):.2f} below {floor}" for key, floor in BASELINE_FLOOR.items() if getattr(own, key) < floor]
    scored = own.scored_shift is not None and theirs.scored_shift is not None
    if unusable and not scored:
        return Verdict(False, ("stock does not repeat itself well enough to judge a variant: " + "; ".join(unusable),), own, theirs)
    reasons = []
    if theirs.non_finite:
        reasons.append(f"{theirs.non_finite} non-finite logprobs")
    # Greedy agreement is judged only where stock repeats itself; elsewhere the scored prompts decide.
    # A shortfall counts when it is both large and unlikely as run-to-run noise.
    prompts = len(stock.tokens)
    if (not unusable and theirs.prefix_match_rate < own.prefix_match_rate - MATCH_MARGIN
            and (p := fewer_matches_p(theirs.matches, own.matches, prompts)) < MATCH_P):
        reasons.append(f"prefix match {theirs.prefix_match_rate:.2f} against stock's {own.prefix_match_rate:.2f} (p {p:.3f})")
    if (not unusable and theirs.mean_prefix_fraction < own.mean_prefix_fraction - MATCH_MARGIN
            and (z := shorter_continuations_z(own.prefix_fractions, theirs.prefix_fractions)) > FRACTION_Z):
        reasons.append(f"shared continuation {theirs.mean_prefix_fraction:.2f} against stock's {own.mean_prefix_fraction:.2f} (z {z:.1f})")
    if scored:
        limit = max(MIN_BIAS_LIMIT, BIAS_FACTOR * abs(own.scored_shift))
        z = theirs.scored_shift / theirs.scored_shift_se if theirs.scored_shift_se else math.inf
        if abs(theirs.scored_shift) > limit and abs(z) > BIAS_Z:
            reasons.append(f"scored logprobs shifted {theirs.scored_shift:+.3f} (z {z:.1f}) over the {limit:.3f} limit")
    limit = max(MIN_LOGPROB_LIMIT, LOGPROB_FACTOR * (own.mean_abs_logprob_delta or 0.0))
    if theirs.mean_abs_logprob_delta is not None and theirs.mean_abs_logprob_delta > limit:
        reasons.append(f"logprob drift {theirs.mean_abs_logprob_delta:.3f} over the {limit:.3f} limit")
    return Verdict(not reasons, tuple(reasons), own, theirs)
