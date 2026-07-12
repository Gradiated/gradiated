from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class EvaluationSums:
    target_tokens: int
    baseline_nll_sum: float
    candidate_nll_sum: float
    squared_logit_error_sum: float
    logit_values: int
    logit_dot_product: float
    baseline_logit_squared_sum: float
    candidate_logit_squared_sum: float
    top1_matches: int
    compared_positions: int


@dataclass(frozen=True)
class EvaluationAggregate:
    target_tokens: int
    compared_positions: int
    baseline_mean_nll: float
    candidate_mean_nll: float
    nll_delta: float
    baseline_perplexity: float
    candidate_perplexity: float
    perplexity_ratio: float
    logit_rmse: float
    logit_cosine_similarity: float
    top1_agreement: float

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


def aggregate_evaluations(evaluations: Iterable[EvaluationSums]) -> EvaluationAggregate:
    records = list(evaluations)
    if not records:
        raise ValueError("at least one evaluation is required")

    target_tokens = sum(record.target_tokens for record in records)
    logit_values = sum(record.logit_values for record in records)
    compared_positions = sum(record.compared_positions for record in records)
    if target_tokens <= 0 or logit_values <= 0 or compared_positions <= 0:
        raise ValueError("evaluation records must have positive counts")

    baseline_nll = sum(record.baseline_nll_sum for record in records) / target_tokens
    candidate_nll = sum(record.candidate_nll_sum for record in records) / target_tokens
    baseline_perplexity = math.exp(baseline_nll)
    candidate_perplexity = math.exp(candidate_nll)
    squared_error = sum(record.squared_logit_error_sum for record in records)
    dot_product = sum(record.logit_dot_product for record in records)
    baseline_squared = sum(record.baseline_logit_squared_sum for record in records)
    candidate_squared = sum(record.candidate_logit_squared_sum for record in records)
    cosine_denominator = math.sqrt(baseline_squared * candidate_squared)
    cosine = dot_product / cosine_denominator if cosine_denominator > 0.0 else 1.0
    top1_matches = sum(record.top1_matches for record in records)

    result = EvaluationAggregate(
        target_tokens=target_tokens,
        compared_positions=compared_positions,
        baseline_mean_nll=baseline_nll,
        candidate_mean_nll=candidate_nll,
        nll_delta=candidate_nll - baseline_nll,
        baseline_perplexity=baseline_perplexity,
        candidate_perplexity=candidate_perplexity,
        perplexity_ratio=candidate_perplexity / baseline_perplexity,
        logit_rmse=math.sqrt(squared_error / logit_values),
        logit_cosine_similarity=cosine,
        top1_agreement=top1_matches / compared_positions,
    )
    if not all(math.isfinite(value) for value in result.to_dict().values()):
        raise ValueError("evaluation produced a non-finite metric")
    return result
