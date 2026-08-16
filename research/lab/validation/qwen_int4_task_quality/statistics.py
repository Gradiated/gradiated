from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PairedOutcomes:
    both_correct: int
    both_wrong: int
    candidate_only_correct: int
    baseline_only_correct: int
    ties: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def paired_outcomes(baseline: list[bool], candidate: list[bool]) -> PairedOutcomes:
    if not baseline or len(baseline) != len(candidate):
        raise ValueError("paired correctness vectors must have equal non-zero length")
    both_correct = sum(a and b for a, b in zip(baseline, candidate, strict=True))
    both_wrong = sum(not a and not b for a, b in zip(baseline, candidate, strict=True))
    candidate_only = sum(not a and b for a, b in zip(baseline, candidate, strict=True))
    baseline_only = sum(a and not b for a, b in zip(baseline, candidate, strict=True))
    return PairedOutcomes(
        both_correct=both_correct,
        both_wrong=both_wrong,
        candidate_only_correct=candidate_only,
        baseline_only_correct=baseline_only,
        ties=both_correct + both_wrong,
    )


def exact_two_sided_mcnemar_p(candidate_only: int, baseline_only: int) -> float:
    if candidate_only < 0 or baseline_only < 0:
        raise ValueError("discordant counts must be non-negative")
    discordant = candidate_only + baseline_only
    if discordant == 0:
        return 1.0
    lower = min(candidate_only, baseline_only)
    tail = sum(math.comb(discordant, value) for value in range(lower + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def paired_bootstrap_accuracy_delta_interval(
    baseline: list[bool],
    candidate: list[bool],
    *,
    samples: int,
    confidence_level: float,
    seed: int,
) -> tuple[float, float]:
    if not baseline or len(baseline) != len(candidate):
        raise ValueError("paired correctness vectors must have equal non-zero length")
    if samples <= 0 or not 0.0 < confidence_level < 1.0:
        raise ValueError("bootstrap configuration is invalid")
    deltas = [
        float(candidate_value) - float(baseline_value)
        for baseline_value, candidate_value in zip(baseline, candidate, strict=True)
    ]
    generator = random.Random(seed)
    count = len(deltas)
    estimates = sorted(
        sum(deltas[generator.randrange(count)] for _ in range(count)) / count
        for _ in range(samples)
    )
    tail = (1.0 - confidence_level) / 2.0
    lower_index = max(0, min(samples - 1, int(tail * samples)))
    upper_index = max(0, min(samples - 1, int((1.0 - tail) * samples) - 1))
    return estimates[lower_index], estimates[upper_index]
