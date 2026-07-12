from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass


_T_CRITICAL_95 = {
    1: 12.706205,
    2: 4.302653,
    3: 3.182446,
    4: 2.776445,
    5: 2.570582,
    6: 2.446912,
    7: 2.364624,
    8: 2.306004,
    9: 2.262157,
    10: 2.228139,
    11: 2.200985,
    12: 2.178813,
    13: 2.160369,
    14: 2.144787,
    15: 2.13145,
    16: 2.119905,
    17: 2.109816,
    18: 2.100922,
    19: 2.093024,
    20: 2.085963,
    21: 2.079614,
    22: 2.073873,
    23: 2.068658,
    24: 2.063899,
    25: 2.059539,
    26: 2.055529,
    27: 2.051831,
    28: 2.048407,
    29: 2.04523,
}


@dataclass(frozen=True)
class SampleSummary:
    count: int
    mean: float
    median: float
    minimum: float
    maximum: float
    sample_standard_deviation: float
    coefficient_of_variation: float
    ci95_low: float
    ci95_high: float
    relative_ci_half_width: float

    def to_mapping(self) -> dict:
        return asdict(self)


def summarize_samples(values: list[float] | tuple[float, ...]) -> SampleSummary:
    samples = tuple(float(value) for value in values)
    if len(samples) < 2 or not all(math.isfinite(value) for value in samples):
        raise ValueError("at least two finite samples are required")
    mean = statistics.fmean(samples)
    if mean == 0:
        raise ValueError("sample mean must be non-zero")
    deviation = statistics.stdev(samples)
    degrees_of_freedom = len(samples) - 1
    critical = _T_CRITICAL_95.get(degrees_of_freedom, 1.959964)
    half_width = critical * deviation / math.sqrt(len(samples))
    return SampleSummary(
        count=len(samples),
        mean=mean,
        median=statistics.median(samples),
        minimum=min(samples),
        maximum=max(samples),
        sample_standard_deviation=deviation,
        coefficient_of_variation=deviation / abs(mean),
        ci95_low=mean - half_width,
        ci95_high=mean + half_width,
        relative_ci_half_width=half_width / abs(mean),
    )


def paired_ratio_summary(
    baseline_by_repeat: dict[int, float], candidate_by_repeat: dict[int, float]
) -> SampleSummary:
    if set(baseline_by_repeat) != set(candidate_by_repeat):
        raise ValueError("paired samples must have identical repeat indices")
    ratios = [
        candidate_by_repeat[index] / baseline_by_repeat[index]
        for index in sorted(baseline_by_repeat)
    ]
    return summarize_samples(ratios)
