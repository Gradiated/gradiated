#!/usr/bin/env python3
"""Collect and validate compositional OpenRouter provider-share models."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import re
import statistics
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


BASE_URL = "https://openrouter.ai"
RANKINGS_PATH = "/api/frontend/v1/rankings/models?view=week"
PRICE_UPTIME_FEATURES = (
    "log_price_non_tool",
    "log_price_tool",
    "uptime_shortfall_99",
    "uptime_degraded",
)
FULL_FEATURES = PRICE_UPTIME_FEATURES + (
    "log_throughput_relative",
    "tool_error_relative",
    "cache_hit_relative",
    "parameter_coverage",
    "context_ratio",
    "log_age_relative",
    "derankable_error_rate",
    "rate_limit_rate",
)
AUTO_EXACTO_FEATURES = (
    "benchmark_gpqa_shortfall_z",
    "benchmark_tau_shortfall_z",
    "benchmark_missing",
)
FULL_AUTO_EXACTO_FEATURES = FULL_FEATURES + AUTO_EXACTO_FEATURES
NOWCAST_FEATURES = FULL_FEATURES + (
    "log_request_count_relative",
    "request_count_missing",
)
AUTO_EXACTO_NOWCAST_FEATURES = FULL_AUTO_EXACTO_FEATURES + (
    "log_request_count_relative",
    "request_count_missing",
)


@dataclass
class EndpointRow:
    model: str
    provider: str
    share: float
    features: dict[str, float]
    price_ratio: float
    uptime: float


@dataclass(frozen=True)
class FittedModel:
    coefficients: dict[str, float]
    feature_names: tuple[str, ...]
    provider_effects: dict[str, float] = field(default_factory=dict)

    @staticmethod
    def group_rows(rows: list[EndpointRow]) -> dict[str, list[EndpointRow]]:
        groups: dict[str, list[EndpointRow]] = {}
        for row in rows:
            groups.setdefault(row.model, []).append(row)
        return groups


def _softmax(logits: list[float]) -> list[float]:
    maximum = max(logits)
    values = [math.exp(value - maximum) for value in logits]
    total = sum(values)
    return [value / total for value in values]


def predict_group(rows: list[EndpointRow], fitted: FittedModel) -> dict[str, float]:
    logits = [
        sum(
            fitted.coefficients[name] * row.features.get(name, 0.0)
            for name in fitted.feature_names
        )
        + fitted.provider_effects.get(row.provider, 0.0)
        for row in rows
    ]
    return {row.provider: value for row, value in zip(rows, _softmax(logits))}


def fit_compositional_model(
    rows: list[EndpointRow],
    *,
    feature_names: tuple[str, ...],
    constrained_nonpositive: set[str],
    constrained_nonnegative: set[str] | None = None,
    iterations: int = 1_200,
    learning_rate: float = 0.03,
    l2: float = 0.02,
    provider_effect_l2: float | None = None,
) -> FittedModel:
    groups = FittedModel.group_rows(rows)
    if len(groups) < 2:
        raise ValueError("at least two model groups are required")
    coefficients = {name: 0.0 for name in feature_names}
    for name in feature_names:
        if name.startswith("log_price"):
            coefficients[name] = -1.0
    nonnegative = constrained_nonnegative or set()
    first_moment = {name: 0.0 for name in feature_names}
    second_moment = {name: 0.0 for name in feature_names}
    provider_effects = (
        {row.provider: 0.0 for row in rows} if provider_effect_l2 is not None else {}
    )
    provider_first = {name: 0.0 for name in provider_effects}
    provider_second = {name: 0.0 for name in provider_effects}
    beta1, beta2 = 0.9, 0.999

    for iteration in range(1, iterations + 1):
        gradient = {name: 0.0 for name in feature_names}
        provider_gradient = {name: 0.0 for name in provider_effects}
        for group in groups.values():
            prediction = predict_group(
                group,
                FittedModel(
                    coefficients=coefficients,
                    feature_names=feature_names,
                    provider_effects=provider_effects,
                ),
            )
            target_total = sum(row.share for row in group)
            for row in group:
                residual = prediction[row.provider] - row.share / target_total
                for name in feature_names:
                    gradient[name] += residual * row.features.get(name, 0.0)
                if row.provider in provider_gradient:
                    provider_gradient[row.provider] += residual
        scale = 1 / len(groups)
        for name in feature_names:
            value = gradient[name] * scale + l2 * coefficients[name]
            first_moment[name] = beta1 * first_moment[name] + (1 - beta1) * value
            second_moment[name] = beta2 * second_moment[name] + (1 - beta2) * value * value
            corrected_first = first_moment[name] / (1 - beta1**iteration)
            corrected_second = second_moment[name] / (1 - beta2**iteration)
            coefficients[name] -= (
                learning_rate * corrected_first / (math.sqrt(corrected_second) + 1e-8)
            )
            if name in constrained_nonpositive:
                coefficients[name] = min(coefficients[name], 0.0)
            if name in nonnegative:
                coefficients[name] = max(coefficients[name], 0.0)
        for provider in provider_effects:
            value = (
                provider_gradient[provider] * scale
                + float(provider_effect_l2) * provider_effects[provider]
            )
            provider_first[provider] = (
                beta1 * provider_first[provider] + (1 - beta1) * value
            )
            provider_second[provider] = (
                beta2 * provider_second[provider] + (1 - beta2) * value * value
            )
            corrected_first = provider_first[provider] / (1 - beta1**iteration)
            corrected_second = provider_second[provider] / (1 - beta2**iteration)
            provider_effects[provider] -= (
                learning_rate * corrected_first / (math.sqrt(corrected_second) + 1e-8)
            )
        if provider_effects:
            center = statistics.mean(provider_effects.values())
            provider_effects = {
                provider: value - center for provider, value in provider_effects.items()
            }
    return FittedModel(
        coefficients=coefficients,
        feature_names=feature_names,
        provider_effects=provider_effects,
    )


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return {name: 1 / len(weights) for name in weights}
    return {name: value / total for name, value in weights.items()}


def inverse_square(rows: list[EndpointRow]) -> dict[str, float]:
    return _normalize({row.provider: row.price_ratio**-2 for row in rows})


def uptime_gated_inverse_square(rows: list[EndpointRow]) -> dict[str, float]:
    def uptime_weight(uptime: float) -> float:
        if uptime >= 95:
            return 1.0
        if uptime >= 80:
            return 0.25
        return 0.05

    return _normalize(
        {
            row.provider: row.price_ratio**-2 * uptime_weight(row.uptime)
            for row in rows
        }
    )


def request_share_nowcast(rows: list[EndpointRow]) -> dict[str, float]:
    """Estimate current token share from the endpoint request-count window.

    This is a nowcast, not a pre-launch forecast: the feature is only available
    after an endpoint has begun receiving routed traffic.
    """
    return _normalize(
        {
            row.provider: max(
                math.exp(row.features.get("log_request_count_relative", 0.0)),
                0.0,
            )
            * (0.0 if row.features.get("request_count_missing", 0.0) else 1.0)
            for row in rows
        }
    )


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2
        for index in order[start:end]:
            ranks[index] = rank
        start = end
    return ranks


def _spearman(actual: list[float], predicted: list[float]) -> float:
    if len(actual) < 2:
        return 0.0
    left, right = _ranks(actual), _ranks(predicted)
    left_mean, right_mean = statistics.mean(left), statistics.mean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = math.sqrt(
        sum((a - left_mean) ** 2 for a in left)
        * sum((b - right_mean) ** 2 for b in right)
    )
    return numerator / denominator if denominator else 0.0


def evaluate_predictions(
    rows: list[EndpointRow], predictions: dict[str, dict[str, float]]
) -> dict[str, float]:
    groups = FittedModel.group_rows(rows)
    total_variations: list[float] = []
    endpoint_errors: list[float] = []
    correlations: list[float] = []
    top_one = 0
    for model, group in groups.items():
        target_total = sum(row.share for row in group)
        actual = [row.share / target_total for row in group]
        predicted = [predictions[model][row.provider] for row in group]
        errors = [abs(a - b) for a, b in zip(actual, predicted)]
        total_variations.append(0.5 * sum(errors))
        endpoint_errors.extend(errors)
        correlations.append(_spearman(actual, predicted))
        top_one += max(range(len(group)), key=lambda i: actual[i]) == max(
            range(len(group)), key=lambda i: predicted[i]
        )
    return {
        "models": len(groups),
        "endpoint_rows": len(rows),
        "mean_total_variation": statistics.mean(total_variations),
        "median_total_variation": statistics.median(total_variations),
        "mean_endpoint_share_absolute_error": statistics.mean(endpoint_errors),
        "mean_spearman": statistics.mean(correlations),
        "top_one_accuracy": top_one / len(groups),
    }


def leave_one_provider_out(
    rows: list[EndpointRow], *, max_providers: int = 20, min_models: int = 3
) -> dict[str, object]:
    """Test prediction for providers whose identity was unseen during fitting."""
    groups = FittedModel.group_rows(rows)
    provider_models: dict[str, set[str]] = {}
    for row in rows:
        provider_models.setdefault(row.provider, set()).add(row.model)
    selected = [
        provider
        for provider, _ in sorted(
            provider_models.items(), key=lambda item: (-len(item[1]), item[0])
        )
        if len(provider_models[provider]) >= min_models
    ][:max_providers]
    methods = (
        "uptime_gated_inverse_square",
        "learned_price_uptime",
        "full_observable",
        "full_auto_exacto",
        "request_share_nowcast",
        "online_request_nowcast",
        "online_auto_exacto_nowcast",
    )
    errors: dict[str, list[float]] = {name: [] for name in methods}
    total_variations: dict[str, list[float]] = {name: [] for name in methods}
    correlations: dict[str, list[float]] = {name: [] for name in methods}
    by_provider: dict[str, object] = {}
    for provider in selected:
        train_rows = [row for row in rows if row.provider != provider]
        fitted = {
            "learned_price_uptime": _candidate_fit(train_rows, PRICE_UPTIME_FEATURES),
            "full_observable": _candidate_fit(train_rows, FULL_FEATURES),
            "full_auto_exacto": _candidate_fit(
                train_rows, FULL_AUTO_EXACTO_FEATURES
            ),
            "online_request_nowcast": _candidate_fit(train_rows, NOWCAST_FEATURES),
            "online_auto_exacto_nowcast": _candidate_fit(
                train_rows, AUTO_EXACTO_NOWCAST_FEATURES
            ),
        }
        provider_errors: dict[str, list[float]] = {name: [] for name in methods}
        for model in provider_models[provider]:
            group = groups[model]
            actual = next(row.share for row in group if row.provider == provider)
            predictions = {
                "uptime_gated_inverse_square": uptime_gated_inverse_square(group),
                "request_share_nowcast": request_share_nowcast(group),
                **{
                    name: predict_group(group, candidate)
                    for name, candidate in fitted.items()
                },
            }
            for name in methods:
                error = abs(actual - predictions[name][provider])
                errors[name].append(error)
                provider_errors[name].append(error)
                target = [row.share for row in group]
                predicted = [predictions[name][row.provider] for row in group]
                total_variations[name].append(
                    0.5 * sum(abs(a - b) for a, b in zip(target, predicted))
                )
                correlations[name].append(_spearman(target, predicted))
        by_provider[provider] = {
            "models": len(provider_models[provider]),
            "mean_absolute_error": {
                name: statistics.mean(values)
                for name, values in provider_errors.items()
            },
        }
    return {
        "protocol": "exclude each provider from all fitting rows; score its share in every model where it appears",
        "providers": len(selected),
        "provider_model_rows": len(errors[methods[0]]),
        "metrics": {
            name: {
                "mean_absolute_error": statistics.mean(values),
                "median_absolute_error": statistics.median(values),
                "mean_total_variation": statistics.mean(total_variations[name]),
                "mean_spearman": statistics.mean(correlations[name]),
            }
            for name, values in errors.items()
        },
        "by_provider": by_provider,
    }


def _fetch(path: str) -> object:
    request = urllib.request.Request(
        BASE_URL + path,
        headers={"User-Agent": "Inference-Foundry-provider-panel/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["data"]


def _signal_value(
    series: list[dict[str, object]], endpoint_id: str, *, weighted: bool = False
) -> float | None:
    values: list[tuple[float, float]] = []
    for point in series:
        y = point.get("y") or {}
        volume = point.get("volume") or {}
        for key, value in y.items():
            if key.split("::", 1)[0] != endpoint_id or value is None:
                continue
            weight = float(volume.get(endpoint_id, volume.get(key, 1.0))) if weighted else 1.0
            if weight > 0:
                values.append((float(value), weight))
    if not values:
        return None
    return sum(value * weight for value, weight in values) / sum(weight for _, weight in values)


def _median_or_none(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _provider_key(name: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    aliases = {
        "alibabacloudint": "alibaba",
        "baiduqianfan": "baidu",
        "novitaai": "novita",
        "weightsbiases": "wandb",
    }
    return aliases.get(key, key)


def _benchmark_match(
    provider: str, scores: dict[str, dict[str, dict[str, float | int]]]
) -> tuple[dict[str, dict[str, float | int]], str | None]:
    key = _provider_key(provider)
    if key in scores:
        return scores[key], "exact"
    if key.endswith("fast") and key[:-4] in scores:
        return scores[key[:-4]], "base_provider_fallback"
    return {}, None


def enrich_panel_benchmarks(
    panel: dict[str, object], *, request_delay: float = 0.08
) -> dict[str, object]:
    matched = 0
    missing = 0
    failures: list[dict[str, str]] = []
    for model in panel["models"]:
        permaslug = str(model["model"])
        query = urllib.parse.urlencode(
            {"permaslug": permaslug, "variant": "standard", "timeRange": "3d"}
        )
        try:
            payload = _fetch(f"/api/frontend/v1/stats/benchmark-scores?{query}")
            by_provider: dict[str, dict[str, dict[str, float | int]]] = {}
            for score in payload.get("scores", []):
                provider_name = str(score["provider_name"])
                if provider_name == "auto-routing":
                    continue
                by_provider.setdefault(_provider_key(provider_name), {})[
                    str(score["benchmark_type"])
                ] = {
                    "score": float(score["score"]),
                    "run_count": int(score["run_count"]),
                }
            for row in model["rows"]:
                provider_scores, match = _benchmark_match(
                    str(row["provider"]), by_provider
                )
                row["benchmark_match"] = match
                for benchmark, field in (
                    ("gpqa_diamond", "benchmark_gpqa"),
                    ("tau_bench_verified_airline", "benchmark_tau"),
                ):
                    value = provider_scores.get(benchmark)
                    row[field + "_score"] = value["score"] if value else None
                    row[field + "_runs"] = value["run_count"] if value else None
                if match:
                    matched += 1
                else:
                    missing += 1
            time.sleep(request_delay)
        except Exception as error:
            failures.append(
                {
                    "model": permaslug,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            for row in model["rows"]:
                row["benchmark_match"] = None
                row["benchmark_gpqa_score"] = None
                row["benchmark_gpqa_runs"] = None
                row["benchmark_tau_score"] = None
                row["benchmark_tau_runs"] = None
                missing += 1
    panel["benchmark_enrichment"] = {
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "matched_rows": matched,
        "missing_rows": missing,
        "failures": failures,
        "provider_matching": "normalized display name with explicit aliases and Fast-to-base fallback",
    }
    return panel


def collect_panel(
    *,
    max_models: int,
    min_endpoints: int,
    max_rank_scan: int,
    share_samples: int,
    request_delay: float,
) -> dict[str, object]:
    rankings = _fetch(RANKINGS_PATH)
    candidates = [
        row
        for row in rankings
        if row["variant"] == "standard"
        and int(row["total_prompt_tokens"]) + int(row["total_completion_tokens"]) > 0
    ]
    candidates.sort(
        key=lambda row: int(row["total_prompt_tokens"])
        + int(row["total_completion_tokens"]),
        reverse=True,
    )
    today = dt.datetime.now(dt.timezone.utc).date()
    models: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []

    for rank, candidate in enumerate(candidates[:max_rank_scan], start=1):
        if len(models) >= max_models:
            break
        permaslug = candidate["model_permaslug"]
        query = urllib.parse.urlencode({"permaslug": permaslug, "variant": "standard"})
        try:
            endpoints = _fetch(f"/api/frontend/v1/stats/endpoint?{query}")
            time.sleep(request_delay)
            if len(endpoints) < min_endpoints:
                continue
            activity = _fetch(f"/api/frontend/v1/stats/model-activity?{query}")["analytics"]
            time.sleep(request_delay)
            complete = [
                row
                for row in activity
                if dt.date.fromisoformat(row["date"][:10]) < today
            ]
            selected = sorted(complete, key=lambda row: row["date"])[-7:]
            if len(selected) < 7:
                continue
            uptime = _fetch(f"/api/frontend/v1/stats/uptime-recent?{query}")
            time.sleep(request_delay)
            signal_query = query + "&timeRange=1w"
            tool_error = _fetch(
                f"/api/frontend/v1/stats/tool-call-error-rate?{signal_query}"
            )
            time.sleep(request_delay)
            cache_hit = _fetch(
                f"/api/frontend/v1/stats/cache-hit-rate-comparison?{signal_query}"
            )
            time.sleep(request_delay)
            throughput = _fetch(
                f"/api/frontend/v1/stats/throughput-comparison?{signal_query}"
            )
            time.sleep(request_delay)
            share_samples_by_name: dict[str, list[float]] = {}
            for sample_index in range(share_samples):
                suffix = urllib.parse.urlencode(
                    {"panel_sample": f"{sample_index}-{random.random()}"}
                )
                summaries = _fetch(
                    f"/api/frontend/v1/stats/effective-pricing?{query}&{suffix}"
                )["providerSummaries"]
                total = sum(int(row["totalTokens"]) for row in summaries)
                if total > 0:
                    for row in summaries:
                        share_samples_by_name.setdefault(row["providerName"], []).append(
                            int(row["totalTokens"]) / total
                        )
                time.sleep(request_delay)
            shares = {
                name: statistics.median(values)
                for name, values in share_samples_by_name.items()
            }

            prompt = sum(int(row["total_prompt_tokens"]) for row in selected)
            cached = sum(int(row["total_native_tokens_cached"]) for row in selected)
            output = sum(int(row["total_completion_tokens"]) for row in selected)
            requests = sum(int(row["count"]) for row in selected)
            tool_calls = sum(int(row["total_tool_calls"]) for row in selected)
            token_total = prompt + output
            if token_total <= 0 or requests <= 0:
                continue
            mix = ((prompt - cached) / token_total, cached / token_total, output / token_total)
            prices: dict[str, float] = {}
            for endpoint in endpoints:
                pricing = endpoint["pricing"]
                values = (
                    float(pricing["prompt"]) * 1_000_000,
                    float(pricing.get("input_cache_read") or pricing["prompt"])
                    * 1_000_000,
                    float(pricing["completion"]) * 1_000_000,
                )
                prices[endpoint["provider_display_name"]] = sum(
                    value * weight for value, weight in zip(values, mix)
                )
            positive_prices = [value for value in prices.values() if value > 0]
            if not positive_prices:
                continue
            cheapest = min(positive_prices)
            union_parameters = set().union(
                *(set(endpoint.get("supported_parameters") or []) for endpoint in endpoints)
            )
            max_context = max(int(endpoint.get("context_length") or 0) for endpoint in endpoints)
            aligned: list[dict[str, object]] = []
            for endpoint in endpoints:
                name = endpoint["provider_display_name"]
                if name not in shares or prices.get(name, 0) <= 0:
                    continue
                endpoint_id = endpoint["id"]
                uptime_values = [
                    float(row["uptime"])
                    for row in uptime.get(endpoint_id, [])
                    if row.get("uptime") is not None
                ]
                status = endpoint.get("status_heuristics_1d") or {}
                success = int(status.get("success") or 0)
                errors = int(status.get("derankableError") or 0)
                rate_limited = int(status.get("rateLimited") or 0)
                attempts = success + errors + rate_limited
                created_at = dt.datetime.fromisoformat(
                    endpoint["created_at"].replace("Z", "+00:00")
                )
                current_stats = endpoint.get("stats") or {}
                throughput_value = _signal_value(throughput, endpoint_id)
                if throughput_value is None and current_stats.get("p50_throughput") is not None:
                    throughput_value = float(current_stats["p50_throughput"])
                aligned.append(
                    {
                        "model": permaslug,
                        "provider": name,
                        "provider_slug": endpoint["provider_slug"],
                        "share": shares[name],
                        "price_per_million": prices[name],
                        "price_ratio": prices[name] / cheapest,
                        "uptime": statistics.mean(uptime_values) if uptime_values else None,
                        "throughput": throughput_value,
                        "tool_error_rate": _signal_value(
                            tool_error, endpoint_id, weighted=True
                        ),
                        "cache_hit_rate": _signal_value(cache_hit, endpoint_id),
                        "parameter_coverage": len(
                            set(endpoint.get("supported_parameters") or [])
                        )
                        / max(len(union_parameters), 1),
                        "context_ratio": int(endpoint.get("context_length") or 0)
                        / max(max_context, 1),
                        "age_days": (
                            dt.datetime.now(dt.timezone.utc) - created_at
                        ).total_seconds()
                        / 86_400,
                        "derankable_error_rate": errors / max(success + errors, 1),
                        "rate_limit_rate": rate_limited / max(attempts, 1),
                        "status": endpoint.get("status"),
                        "request_count_30m": current_stats.get("request_count"),
                    }
                )
            coverage = sum(float(row["share"]) for row in aligned)
            if len(aligned) < min_endpoints or coverage < 0.85:
                failures.append(
                    {
                        "model": permaslug,
                        "error": f"aligned coverage {coverage:.3f} across {len(aligned)} rows",
                    }
                )
                continue
            for row in aligned:
                row["share"] = float(row["share"]) / coverage
                row["tool_fraction"] = min(tool_calls / requests, 1.0)
            models.append(
                {
                    "rank": rank,
                    "model": permaslug,
                    "weekly_tokens": int(candidate["total_prompt_tokens"])
                    + int(candidate["total_completion_tokens"]),
                    "weekly_requests": requests,
                    "tool_fraction_proxy": min(tool_calls / requests, 1.0),
                    "aligned_share_coverage": coverage,
                    "rows": aligned,
                }
            )
        except Exception as error:
            failures.append(
                {
                    "model": permaslug,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    return {
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": BASE_URL + RANKINGS_PATH,
        "configuration": {
            "max_models": max_models,
            "min_endpoints": min_endpoints,
            "max_rank_scan": max_rank_scan,
            "share_samples": share_samples,
            "request_delay": request_delay,
        },
        "models": models,
        "failures": failures,
    }


def _relative(value: float | None, median: float | None, *, log: bool = False) -> float:
    if value is None or median is None:
        return 0.0
    if log:
        return math.log(max(value, 1e-6) / max(median, 1e-6))
    return value - median


def panel_rows(panel: dict[str, object]) -> list[EndpointRow]:
    result: list[EndpointRow] = []
    for model in panel["models"]:
        raw_rows = model["rows"]
        medians = {
            key: _median_or_none(
                [float(row[key]) for row in raw_rows if row.get(key) is not None]
            )
            for key in (
                "throughput",
                "tool_error_rate",
                "cache_hit_rate",
                "age_days",
                "request_count_30m",
                "benchmark_gpqa_score",
                "benchmark_tau_score",
            )
        }
        benchmark_scales = {}
        for key in ("benchmark_gpqa_score", "benchmark_tau_score"):
            values = [float(row[key]) for row in raw_rows if row.get(key) is not None]
            median = medians[key]
            mad = (
                statistics.median(abs(value - float(median)) for value in values)
                if values and median is not None
                else None
            )
            benchmark_scales[key] = max(1.4826 * mad, 1e-6) if mad is not None else None
        tool_fraction = float(model["tool_fraction_proxy"])
        for raw in raw_rows:
            uptime = float(raw["uptime"]) if raw.get("uptime") is not None else 90.0
            log_price = math.log(float(raw["price_ratio"]))
            features = {
                "log_price_non_tool": log_price * (1 - tool_fraction),
                "log_price_tool": log_price * tool_fraction,
                "uptime_shortfall_99": max(0.0, 99.0 - uptime) / 10,
                "uptime_degraded": 1.0 if uptime < 95 else 0.0,
                "log_throughput_relative": _relative(
                    raw.get("throughput"), medians["throughput"], log=True
                ),
                "tool_error_relative": _relative(
                    raw.get("tool_error_rate"), medians["tool_error_rate"], log=True
                )
                * tool_fraction,
                "cache_hit_relative": _relative(
                    raw.get("cache_hit_rate"), medians["cache_hit_rate"]
                )
                / 100,
                "parameter_coverage": float(raw["parameter_coverage"]) - 1.0,
                "context_ratio": float(raw["context_ratio"]) - 1.0,
                "log_age_relative": _relative(
                    raw.get("age_days"), medians["age_days"], log=True
                ),
                "derankable_error_rate": float(raw["derankable_error_rate"]),
                "rate_limit_rate": float(raw["rate_limit_rate"]),
                "log_request_count_relative": _relative(
                    raw.get("request_count_30m"),
                    medians["request_count_30m"],
                    log=True,
                ),
                "request_count_missing": 1.0
                if raw.get("request_count_30m") is None
                else 0.0,
                "benchmark_gpqa_shortfall_z": (
                    max(
                        0.0,
                        (
                            float(medians["benchmark_gpqa_score"])
                            - float(raw["benchmark_gpqa_score"])
                        )
                        / float(benchmark_scales["benchmark_gpqa_score"]),
                    )
                    * tool_fraction
                    if raw.get("benchmark_gpqa_score") is not None
                    and medians["benchmark_gpqa_score"] is not None
                    and benchmark_scales["benchmark_gpqa_score"] is not None
                    else 0.0
                ),
                "benchmark_tau_shortfall_z": (
                    max(
                        0.0,
                        (
                            float(medians["benchmark_tau_score"])
                            - float(raw["benchmark_tau_score"])
                        )
                        / float(benchmark_scales["benchmark_tau_score"]),
                    )
                    * tool_fraction
                    if raw.get("benchmark_tau_score") is not None
                    and medians["benchmark_tau_score"] is not None
                    and benchmark_scales["benchmark_tau_score"] is not None
                    else 0.0
                ),
                "benchmark_missing": (
                    1.0
                    if raw.get("benchmark_gpqa_score") is None
                    or raw.get("benchmark_tau_score") is None
                    else 0.0
                )
                * tool_fraction,
            }
            result.append(
                EndpointRow(
                    model=str(raw["model"]),
                    provider=str(raw["provider"]),
                    share=float(raw["share"]),
                    features=features,
                    price_ratio=float(raw["price_ratio"]),
                    uptime=uptime,
                )
            )
    return result


def _candidate_fit(
    rows: list[EndpointRow], features: tuple[str, ...], *, provider_effects: bool = False
) -> FittedModel:
    return fit_compositional_model(
        rows,
        feature_names=features,
        constrained_nonpositive={
            "log_price_non_tool",
            "log_price_tool",
            "uptime_shortfall_99",
            "uptime_degraded",
            "tool_error_relative",
            "derankable_error_rate",
            "rate_limit_rate",
            "request_count_missing",
            "benchmark_gpqa_shortfall_z",
            "benchmark_tau_shortfall_z",
            "benchmark_missing",
        },
        constrained_nonnegative={
            "log_throughput_relative",
            "cache_hit_relative",
            "parameter_coverage",
            "context_ratio",
            "log_age_relative",
            "log_request_count_relative",
        },
        provider_effect_l2=0.08 if provider_effects else None,
    )


def validate_panel(panel: dict[str, object], holdout_model: str) -> dict[str, object]:
    rows = panel_rows(panel)
    groups = FittedModel.group_rows(rows)
    predictions: dict[str, dict[str, dict[str, float]]] = {
        "equal_share": {},
        "inverse_square": {},
        "uptime_gated_inverse_square": {},
        "learned_price_uptime": {},
        "full_observable": {},
        "full_auto_exacto": {},
        "full_provider_reputation": {},
        "request_share_nowcast": {},
        "online_request_nowcast": {},
        "online_auto_exacto_nowcast": {},
    }
    coefficients: dict[str, list[dict[str, float]]] = {
        "learned_price_uptime": [],
        "full_observable": [],
        "full_auto_exacto": [],
        "full_provider_reputation": [],
        "online_request_nowcast": [],
        "online_auto_exacto_nowcast": [],
    }
    for model, test_rows in groups.items():
        train_rows = [row for row in rows if row.model != model]
        predictions["equal_share"][model] = {
            row.provider: 1 / len(test_rows) for row in test_rows
        }
        predictions["inverse_square"][model] = inverse_square(test_rows)
        predictions["uptime_gated_inverse_square"][model] = (
            uptime_gated_inverse_square(test_rows)
        )
        predictions["request_share_nowcast"][model] = request_share_nowcast(test_rows)
        for name, features in (
            ("learned_price_uptime", PRICE_UPTIME_FEATURES),
            ("full_observable", FULL_FEATURES),
            ("full_auto_exacto", FULL_AUTO_EXACTO_FEATURES),
            ("full_provider_reputation", FULL_FEATURES),
            ("online_request_nowcast", NOWCAST_FEATURES),
            ("online_auto_exacto_nowcast", AUTO_EXACTO_NOWCAST_FEATURES),
        ):
            fitted = _candidate_fit(
                train_rows,
                features,
                provider_effects=name == "full_provider_reputation",
            )
            predictions[name][model] = predict_group(test_rows, fitted)
            coefficients[name].append(fitted.coefficients)
    metrics = {
        name: evaluate_predictions(rows, model_predictions)
        for name, model_predictions in predictions.items()
    }
    coefficient_summary = {
        name: {
            feature: {
                "median": statistics.median(fold[feature] for fold in folds),
                "min": min(fold[feature] for fold in folds),
                "max": max(fold[feature] for fold in folds),
            }
            for feature in folds[0]
        }
        for name, folds in coefficients.items()
    }
    holdout = None
    if holdout_model in groups:
        holdout = {
            name: evaluate_predictions(
                groups[holdout_model], {holdout_model: model_predictions[holdout_model]}
            )
            for name, model_predictions in predictions.items()
        }
        holdout["actual_and_predictions"] = [
            {
                "provider": row.provider,
                "actual_share": row.share,
                **{
                    name: model_predictions[holdout_model][row.provider]
                    for name, model_predictions in predictions.items()
                },
            }
            for row in groups[holdout_model]
        ]
    baseline_tv = metrics["uptime_gated_inverse_square"]["mean_total_variation"]
    candidate_tv = metrics["full_observable"]["mean_total_variation"]
    auto_exacto_tv = metrics["full_auto_exacto"]["mean_total_variation"]
    nowcast_tv = metrics["online_request_nowcast"]["mean_total_variation"]
    auto_exacto_nowcast_tv = metrics["online_auto_exacto_nowcast"][
        "mean_total_variation"
    ]
    new_provider_validation = leave_one_provider_out(rows)
    return {
        "validated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "cross_validation": "leave-one-model-out",
        "models": len(groups),
        "endpoint_rows": len(rows),
        "metrics": metrics,
        "coefficient_summary": coefficient_summary,
        "holdout_model": holdout_model,
        "holdout": holdout,
        "leave_one_provider_out": new_provider_validation,
        "auto_exacto_feature_gate": {
            "stock": "full_observable",
            "candidate": "full_auto_exacto",
            "relative_tv_improvement": (candidate_tv - auto_exacto_tv)
            / candidate_tv,
            "required_direction": "candidate mean TV must be lower than stock",
            "glm_holdout_worsening_limit": 0.01,
            "passed": auto_exacto_tv < candidate_tv
            and holdout is not None
            and holdout["full_auto_exacto"]["mean_total_variation"]
            <= holdout["full_observable"]["mean_total_variation"] + 0.01,
        },
        "promotion_gate": {
            "required_relative_tv_improvement": 0.20,
            "actual_relative_tv_improvement": (baseline_tv - candidate_tv) / baseline_tv,
            "required_holdout_tv_max": 0.15,
            "passed": (baseline_tv - candidate_tv) / baseline_tv >= 0.20
            and holdout is not None
            and holdout["full_observable"]["mean_total_variation"] <= 0.15,
        },
        "incumbent_reputation_gate": {
            "scope": "known providers with cross-model history; not a new-provider forecast",
            "required_relative_tv_improvement": 0.20,
            "actual_relative_tv_improvement": (
                baseline_tv
                - metrics["full_provider_reputation"]["mean_total_variation"]
            )
            / baseline_tv,
            "required_holdout_tv_max": 0.15,
            "passed": (
                baseline_tv
                - metrics["full_provider_reputation"]["mean_total_variation"]
            )
            / baseline_tv
            >= 0.20
            and holdout is not None
            and holdout["full_provider_reputation"]["mean_total_variation"] <= 0.15,
        },
        "online_nowcast_gate": {
            "scope": "post-launch current-share estimate; not a causal price forecast",
            "required_relative_tv_improvement": 0.50,
            "actual_relative_tv_improvement": (baseline_tv - nowcast_tv) / baseline_tv,
            "required_holdout_tv_max": 0.20,
            "passed": (baseline_tv - nowcast_tv) / baseline_tv >= 0.50
            and holdout is not None
            and holdout["online_request_nowcast"]["mean_total_variation"] <= 0.20,
        },
        "auto_exacto_nowcast_feature_gate": {
            "stock": "online_request_nowcast",
            "candidate": "online_auto_exacto_nowcast",
            "relative_tv_improvement": (nowcast_tv - auto_exacto_nowcast_tv)
            / nowcast_tv,
            "passed": auto_exacto_nowcast_tv < nowcast_tv,
        },
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("collect")
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--max-models", type=int, default=30)
    collect.add_argument("--min-endpoints", type=int, default=4)
    collect.add_argument("--max-rank-scan", type=int, default=100)
    collect.add_argument("--share-samples", type=int, default=3)
    collect.add_argument("--request-delay", type=float, default=0.08)
    enrich = subparsers.add_parser("enrich-benchmarks")
    enrich.add_argument("--panel", type=Path, required=True)
    enrich.add_argument("--output", type=Path, required=True)
    enrich.add_argument("--request-delay", type=float, default=0.08)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--panel", type=Path, required=True)
    validate.add_argument("--output", type=Path, required=True)
    validate.add_argument("--holdout-model", default="z-ai/glm-5.2-20260616")
    args = parser.parse_args()
    if args.command == "collect":
        result = collect_panel(
            max_models=args.max_models,
            min_endpoints=args.min_endpoints,
            max_rank_scan=args.max_rank_scan,
            share_samples=args.share_samples,
            request_delay=args.request_delay,
        )
        _write_json(args.output, result)
        print(
            json.dumps(
                {
                    "models": len(result["models"]),
                    "rows": sum(len(model["rows"]) for model in result["models"]),
                    "failures": len(result["failures"]),
                    "output": str(args.output),
                }
            )
        )
    elif args.command == "enrich-benchmarks":
        panel = json.loads(args.panel.read_text())
        result = enrich_panel_benchmarks(panel, request_delay=args.request_delay)
        _write_json(args.output, result)
        enrichment = result["benchmark_enrichment"]
        print(
            json.dumps(
                {
                    "matched_rows": enrichment["matched_rows"],
                    "missing_rows": enrichment["missing_rows"],
                    "failures": len(enrichment["failures"]),
                    "output": str(args.output),
                }
            )
        )
    else:
        panel = json.loads(args.panel.read_text())
        result = validate_panel(panel, args.holdout_model)
        _write_json(args.output, result)
        print(json.dumps({"promotion_gate": result["promotion_gate"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
