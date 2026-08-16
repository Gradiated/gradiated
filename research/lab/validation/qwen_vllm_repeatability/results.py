from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from .statistics import SampleSummary, paired_ratio_summary, summarize_samples


class CampaignAcceptance(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class RunContext:
    pair_id: str
    concurrency: int
    repeat_index: int
    state: str
    prompt_content_id: str
    source_content_id: str
    isolated: bool


@dataclass(frozen=True)
class RequestResult:
    request_index: int
    request_id: str
    prompt_sha256: str
    input_tokens: int
    output_tokens: int
    queue_seconds: float
    ttft_seconds: float
    tpot_seconds: float
    raw_e2el_seconds: float
    e2el_seconds: float
    start_monotonic_seconds: float
    inter_token_latencies_seconds: tuple[float, ...]
    generated_text: str
    error: str
    success: bool


@dataclass(frozen=True)
class RunResult:
    context: RunContext
    duration_seconds: float
    request_throughput: float
    output_throughput: float
    total_token_throughput: float
    p95_ttft_ms: float
    p95_tpot_ms: float
    requests: tuple[RequestResult, ...]
    accepted: bool
    rejection_reasons: tuple[str, ...]

    def metric(self, name: str) -> float:
        values = {
            "duration_seconds": self.duration_seconds,
            "request_throughput": self.request_throughput,
            "output_throughput": self.output_throughput,
            "total_token_throughput": self.total_token_throughput,
            "p95_ttft_ms": self.p95_ttft_ms,
            "p95_tpot_ms": self.p95_tpot_ms,
        }
        if name not in values:
            raise ValueError(f"unsupported metric {name}")
        return values[name]

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


def run_result_from_mapping(value: Mapping[str, Any]) -> RunResult:
    context = RunContext(**value["context"])
    requests = tuple(
        RequestResult(
            request_index=request["request_index"],
            request_id=request["request_id"],
            prompt_sha256=request["prompt_sha256"],
            input_tokens=request["input_tokens"],
            output_tokens=request["output_tokens"],
            queue_seconds=request["queue_seconds"],
            ttft_seconds=request["ttft_seconds"],
            tpot_seconds=request["tpot_seconds"],
            raw_e2el_seconds=request["raw_e2el_seconds"],
            e2el_seconds=request["e2el_seconds"],
            start_monotonic_seconds=request["start_monotonic_seconds"],
            inter_token_latencies_seconds=tuple(
                request["inter_token_latencies_seconds"]
            ),
            generated_text=request["generated_text"],
            error=request["error"],
            success=request["success"],
        )
        for request in value["requests"]
    )
    return RunResult(
        context=context,
        duration_seconds=value["duration_seconds"],
        request_throughput=value["request_throughput"],
        output_throughput=value["output_throughput"],
        total_token_throughput=value["total_token_throughput"],
        p95_ttft_ms=value["p95_ttft_ms"],
        p95_tpot_ms=value["p95_tpot_ms"],
        requests=requests,
        accepted=value["accepted"],
        rejection_reasons=tuple(value["rejection_reasons"]),
    )


@dataclass(frozen=True)
class CellSummary:
    concurrency: int
    state: str
    metrics: dict[str, SampleSummary]
    accepted: bool
    rejection_reasons: tuple[str, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "concurrency": self.concurrency,
            "state": self.state,
            "metrics": {
                name: summary.to_mapping() for name, summary in self.metrics.items()
            },
            "accepted": self.accepted,
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclass(frozen=True)
class CampaignSummary:
    acceptance: CampaignAcceptance
    rejection_reasons: tuple[str, ...]
    cells: tuple[CellSummary, ...]
    warm_to_cold_ratios: dict[str, dict[int, SampleSummary]]
    claims: dict[str, bool]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "acceptance": self.acceptance.value,
            "rejection_reasons": list(self.rejection_reasons),
            "cells": [cell.to_mapping() for cell in self.cells],
            "warm_to_cold_ratios": {
                metric: {
                    str(concurrency): summary.to_mapping()
                    for concurrency, summary in by_concurrency.items()
                }
                for metric, by_concurrency in self.warm_to_cold_ratios.items()
            },
            "claims": self.claims,
        }


def _sequence(raw: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be an array")
    return value


def _number(raw: Mapping[str, Any], key: str) -> float:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{key} must be finite")
    return result


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires samples")
    position = (len(ordered) - 1) * percentile / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def normalize_vllm_result(
    raw: Mapping[str, Any],
    prompts: Sequence[Mapping[str, Any]],
    context: RunContext,
) -> RunResult:
    reasons: list[str] = []
    try:
        input_lens = _sequence(raw, "input_lens")
        output_lens = _sequence(raw, "output_lens")
        ttfts = _sequence(raw, "ttfts")
        itls = _sequence(raw, "itls")
        start_times = _sequence(raw, "start_times")
        generated_texts = _sequence(raw, "generated_texts")
        errors = _sequence(raw, "errors")
        arrays = {
            "prompts": prompts,
            "input_lens": input_lens,
            "output_lens": output_lens,
            "ttfts": ttfts,
            "itls": itls,
            "start_times": start_times,
            "generated_texts": generated_texts,
            "errors": errors,
        }
        if any(len(value) != 8 for value in arrays.values()):
            reasons.append("detailed result arrays must each contain 8 requests")
        completed = int(_number(raw, "completed"))
        failed = int(_number(raw, "failed"))
        if completed != 8 or failed != 0:
            reasons.append("aggregate completion must be exactly 8 successful requests")
        if int(_number(raw, "total_input_tokens")) != 1024:
            reasons.append("total_input_tokens must equal 1024")
        if int(_number(raw, "total_output_tokens")) != 256:
            reasons.append("total_output_tokens must equal 256")
    except (TypeError, ValueError) as error:
        reasons.append(str(error))
        input_lens = output_lens = ttfts = itls = start_times = generated_texts = (
            errors
        ) = []

    requests: list[RequestResult] = []
    if all(
        len(value) == 8
        for value in (
            prompts,
            input_lens,
            output_lens,
            ttfts,
            itls,
            start_times,
            generated_texts,
            errors,
        )
    ):
        minimum_start = min(float(value) for value in start_times)
        for index in range(8):
            prompt = prompts[index]
            input_tokens = int(input_lens[index])
            output_tokens = int(output_lens[index])
            ttft = float(ttfts[index])
            request_itls = tuple(float(value) for value in itls[index])
            start_time = float(start_times[index])
            queue_seconds = start_time - minimum_start
            error = str(errors[index])
            if input_tokens != 128:
                reasons.append(f"request {index} input_tokens")
            if output_tokens != 32:
                reasons.append(f"request {index} output_tokens")
            if len(request_itls) != max(output_tokens - 1, 0):
                reasons.append(f"request {index} inter_token_latencies")
            if error:
                reasons.append(f"request {index} error")
            if not all(
                math.isfinite(value) and value >= 0 for value in (ttft, *request_itls)
            ):
                reasons.append(f"request {index} non_finite_latency")
            if not math.isfinite(start_time) or queue_seconds < 0:
                reasons.append(f"request {index} invalid_start_time")
            tpot = sum(request_itls) / len(request_itls) if request_itls else 0.0
            raw_e2el = ttft + sum(request_itls)
            requests.append(
                RequestResult(
                    request_index=index,
                    request_id=str(prompt["request_id"]),
                    prompt_sha256=str(prompt["prompt_sha256"]),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    queue_seconds=queue_seconds,
                    ttft_seconds=ttft,
                    tpot_seconds=tpot,
                    raw_e2el_seconds=raw_e2el,
                    e2el_seconds=queue_seconds + raw_e2el,
                    start_monotonic_seconds=start_time,
                    inter_token_latencies_seconds=request_itls,
                    generated_text=str(generated_texts[index]),
                    error=error,
                    success=not error and input_tokens == 128 and output_tokens == 32,
                )
            )
    if not context.isolated:
        reasons.append("host isolation gate failed")

    ttft_values = [
        (request.queue_seconds + request.ttft_seconds) * 1000 for request in requests
    ]
    tpot_values = [request.tpot_seconds * 1000 for request in requests]
    try:
        duration = _number(raw, "duration")
        request_throughput = _number(raw, "request_throughput")
        output_throughput = _number(raw, "output_throughput")
        total_token_throughput = _number(raw, "total_token_throughput")
    except ValueError as error:
        reasons.append(str(error))
        duration = request_throughput = output_throughput = total_token_throughput = 0.0

    return RunResult(
        context=context,
        duration_seconds=duration,
        request_throughput=request_throughput,
        output_throughput=output_throughput,
        total_token_throughput=total_token_throughput,
        p95_ttft_ms=_percentile(ttft_values, 95) if ttft_values else 0.0,
        p95_tpot_ms=_percentile(tpot_values, 95) if tpot_values else 0.0,
        requests=tuple(requests),
        accepted=not reasons,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
    )


def summarize_campaign(
    runs: Sequence[RunResult],
    expected_concurrency: tuple[int, ...],
    minimum_repeats: int,
    primary_metrics: tuple[str, ...],
    maximum_cv: float,
    maximum_relative_ci_half_width: float,
) -> CampaignSummary:
    campaign_reasons: list[str] = []
    expected_count = len(expected_concurrency) * minimum_repeats * 2
    if len(runs) != expected_count:
        campaign_reasons.append(
            f"expected {expected_count} runs but observed {len(runs)}"
        )
    if any(not run.accepted for run in runs):
        campaign_reasons.append("one or more runs failed validation or isolation")
    prompt_ids = {run.context.prompt_content_id for run in runs}
    source_ids = {run.context.source_content_id for run in runs}
    if len(prompt_ids) != 1:
        campaign_reasons.append("prompt identity changed within campaign")
    if len(source_ids) != 1:
        campaign_reasons.append("source identity changed within campaign")

    cells: list[CellSummary] = []
    for concurrency in expected_concurrency:
        for state in ("cold_engine", "warm_engine"):
            cell_runs = [
                run
                for run in runs
                if run.context.concurrency == concurrency and run.context.state == state
            ]
            reasons: list[str] = []
            repeats = {run.context.repeat_index for run in cell_runs}
            if len(cell_runs) != minimum_repeats or len(repeats) != minimum_repeats:
                reasons.append(f"cell requires {minimum_repeats} unique repeats")
            summaries: dict[str, SampleSummary] = {}
            if len(cell_runs) >= 2:
                for metric in primary_metrics:
                    try:
                        summary = summarize_samples(
                            [run.metric(metric) for run in cell_runs]
                        )
                    except ValueError as error:
                        reasons.append(f"{metric} dispersion unavailable: {error}")
                        continue
                    summaries[metric] = summary
                    if summary.coefficient_of_variation > maximum_cv:
                        reasons.append(
                            f"{metric} coefficient_of_variation exceeds limit"
                        )
                    if summary.relative_ci_half_width > maximum_relative_ci_half_width:
                        reasons.append(f"{metric} relative_ci_half_width exceeds limit")
            else:
                reasons.append("cell has too few observations for dispersion")
            cell = CellSummary(
                concurrency=concurrency,
                state=state,
                metrics=summaries,
                accepted=not reasons,
                rejection_reasons=tuple(reasons),
            )
            cells.append(cell)
            if reasons:
                campaign_reasons.append(f"c{concurrency} {state} failed repeatability")

    ratios: dict[str, dict[int, SampleSummary]] = {
        metric: {} for metric in primary_metrics
    }
    for metric in primary_metrics:
        for concurrency in expected_concurrency:
            cold = {
                run.context.repeat_index: run.metric(metric)
                for run in runs
                if run.context.concurrency == concurrency
                and run.context.state == "cold_engine"
            }
            warm = {
                run.context.repeat_index: run.metric(metric)
                for run in runs
                if run.context.concurrency == concurrency
                and run.context.state == "warm_engine"
            }
            if len(cold) >= 2 and set(cold) == set(warm):
                ratios[metric][concurrency] = paired_ratio_summary(cold, warm)

    return CampaignSummary(
        acceptance=(
            CampaignAcceptance.PASS if not campaign_reasons else CampaignAcceptance.FAIL
        ),
        rejection_reasons=tuple(dict.fromkeys(campaign_reasons)),
        cells=tuple(cells),
        warm_to_cold_ratios=ratios,
        claims={
            "provider_comparison": False,
            "gpu_performance": False,
            "simulator_calibration": False,
            "cost_per_token": False,
        },
    )
