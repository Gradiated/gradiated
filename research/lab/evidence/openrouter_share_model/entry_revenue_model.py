#!/usr/bin/env python3
"""Estimate GLM-5.2 OpenRouter entrant share and gross billings by price."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import statistics
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


BASE_URL = "https://openrouter.ai"
PERMASLUG = "z-ai/glm-5.2-20260616"
VARIANT = "standard"
MONTHS_PER_WEEK = 365.25 / 12 / 7
SECONDS_PER_MONTH = 365.25 / 12 * 86_400
DEFAULT_PRICE_RATIOS = (0.75, 1.0, 1.25, 1.5, 2.0)
FITNESS_PERCENTILES = (10, 25, 50, 75, 90)


@dataclass(frozen=True)
class PriceSchedule:
    input: float
    cache: float
    output: float

    def scaled(self, ratio: float) -> PriceSchedule:
        return PriceSchedule(
            input=self.input * ratio,
            cache=self.cache * ratio,
            output=self.output * ratio,
        )

    def blended(self, weights: tuple[float, float, float]) -> float:
        return sum(value * weight for value, weight in zip(asdict(self).values(), weights))


def quantile(values: list[float], percentile: int) -> float:
    if not values:
        raise ValueError("cannot take a quantile of no values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def infer_fitness_scenarios(
    shares: dict[str, float],
    prices: dict[str, dict[str, float]],
    *,
    stable_providers: set[str],
    proxies: tuple[str, ...],
    percentiles: tuple[int, ...] = FITNESS_PERCENTILES,
) -> dict[str, float]:
    common = set(shares) & set(prices) & stable_providers
    if not common:
        raise ValueError("no stable providers have aligned price and share data")
    by_proxy: dict[str, dict[str, float]] = {}
    for proxy in proxies:
        base = min(provider_prices[proxy] for provider_prices in prices.values())
        residuals = [shares[name] * (prices[name][proxy] / base) ** 2 for name in common]
        by_proxy[proxy] = {
            f"p{percentile}": quantile(residuals, percentile)
            for percentile in percentiles
        }
    return {
        f"p{percentile}": statistics.median(
            values[f"p{percentile}"] for values in by_proxy.values()
        )
        for percentile in percentiles
    }


def reprice_share(
    anchor_share: float, anchor_price_ratio: float, price_ratio: float
) -> float:
    if not 0 <= anchor_share < 1:
        raise ValueError("anchor share must be in [0, 1)")
    if anchor_price_ratio <= 0 or price_ratio <= 0:
        raise ValueError("price ratios must be positive")
    if anchor_share == 0:
        return 0.0
    anchor_odds = anchor_share / (1 - anchor_share)
    repriced_odds = anchor_odds * (anchor_price_ratio / price_ratio) ** 2
    return repriced_odds / (1 + repriced_odds)


def cohort_adjusted_share(
    *,
    anchor_share: float,
    anchor_price_ratio: float,
    price_ratio: float,
    tool_fraction: float,
    tool_tier_multiplier: float,
) -> float:
    if not 0 <= tool_fraction <= 1 or tool_tier_multiplier < 0:
        raise ValueError("tool fraction must be in [0, 1] and multiplier non-negative")
    non_tool_share = reprice_share(anchor_share, anchor_price_ratio, price_ratio)
    tool_share = min(anchor_share * tool_tier_multiplier, 1.0)
    return (1 - tool_fraction) * non_tool_share + tool_fraction * tool_share


def _project_at_share(
    *,
    token_share: float,
    price_ratio: float,
    cheapest: PriceSchedule,
    monthly_uncached_prompt_tokens: float,
    monthly_cached_prompt_tokens: float,
    monthly_output_tokens: float,
    monthly_requests: float,
    cogs_ratio: float,
) -> dict[str, object]:
    if not 0 <= token_share <= 1:
        raise ValueError("token share must be in [0, 1]")
    displayed = cheapest.scaled(price_ratio)
    billings = token_share / 1_000_000 * (
        monthly_uncached_prompt_tokens * displayed.input
        + monthly_cached_prompt_tokens * displayed.cache
        + monthly_output_tokens * displayed.output
    )
    baseline_cost = token_share * cogs_ratio / 1_000_000 * (
        monthly_uncached_prompt_tokens * cheapest.input
        + monthly_cached_prompt_tokens * cheapest.cache
        + monthly_output_tokens * cheapest.output
    )
    return {
        "token_share": token_share,
        "gross_endpoint_billings_monthly": billings,
        "inference_cogs_monthly": baseline_cost,
        "gross_margin_before_platform_terms_monthly": billings - baseline_cost,
        "served_requests_monthly": monthly_requests * token_share,
        "served_uncached_prompt_tokens_monthly": monthly_uncached_prompt_tokens
        * token_share,
        "served_cached_prompt_tokens_monthly": monthly_cached_prompt_tokens * token_share,
        "served_output_tokens_monthly": monthly_output_tokens * token_share,
        "required_average_output_tokens_per_second": monthly_output_tokens
        * token_share
        / SECONDS_PER_MONTH,
        "displayed_price_per_million": {
            "input": displayed.input,
            "cache_read": displayed.cache,
            "output": displayed.output,
        },
    }


def project_entry(
    *,
    price_ratio: float,
    fitness: float,
    cheapest: PriceSchedule,
    monthly_uncached_prompt_tokens: float,
    monthly_cached_prompt_tokens: float,
    monthly_output_tokens: float,
    monthly_requests: float,
    cogs_ratio: float,
) -> dict[str, object]:
    if price_ratio <= 0 or fitness < 0 or cogs_ratio <= 0:
        raise ValueError("price and COGS ratios must be positive and fitness non-negative")
    token_share = fitness / (price_ratio * price_ratio + fitness)
    return _project_at_share(
        token_share=token_share,
        price_ratio=price_ratio,
        cheapest=cheapest,
        monthly_uncached_prompt_tokens=monthly_uncached_prompt_tokens,
        monthly_cached_prompt_tokens=monthly_cached_prompt_tokens,
        monthly_output_tokens=monthly_output_tokens,
        monthly_requests=monthly_requests,
        cogs_ratio=cogs_ratio,
    )


def _fetch(path: str) -> object:
    request = urllib.request.Request(
        BASE_URL + path,
        headers={"User-Agent": "Inference-Foundry-entry-revenue-model/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["data"]


def _parse_csv_floats(value: str) -> tuple[float, ...]:
    parsed = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    if not parsed or any(item <= 0 for item in parsed):
        raise argparse.ArgumentTypeError("expected comma-separated positive numbers")
    return parsed


def build_live_model(
    *,
    price_ratios: tuple[float, ...] | None,
    common_prices: tuple[float, ...] | None = None,
    cogs_ratio: float = 1.25,
    share_samples: int,
    sample_delay: float,
) -> dict[str, object]:
    query = urllib.parse.urlencode({"permaslug": PERMASLUG, "variant": VARIANT})
    today = dt.datetime.now(dt.timezone.utc).date()
    analytics = _fetch(f"/api/frontend/v1/stats/model-activity?{query}")["analytics"]
    complete = [row for row in analytics if dt.date.fromisoformat(row["date"][:10]) < today]
    selected = sorted(complete, key=lambda row: row["date"])[-7:]
    if len(selected) != 7:
        raise ValueError("seven complete activity days are not available")

    weekly_requests = sum(int(row["count"]) for row in selected)
    weekly_prompt = sum(int(row["total_prompt_tokens"]) for row in selected)
    weekly_cached = sum(int(row["total_native_tokens_cached"]) for row in selected)
    weekly_output = sum(int(row["total_completion_tokens"]) for row in selected)
    weekly_tool_calls = sum(int(row["total_tool_calls"]) for row in selected)
    monthly_requests = weekly_requests * MONTHS_PER_WEEK
    monthly_uncached = (weekly_prompt - weekly_cached) * MONTHS_PER_WEEK
    monthly_cached = weekly_cached * MONTHS_PER_WEEK
    monthly_output = weekly_output * MONTHS_PER_WEEK
    monthly_total = monthly_uncached + monthly_cached + monthly_output
    weights = (
        monthly_uncached / monthly_total,
        monthly_cached / monthly_total,
        monthly_output / monthly_total,
    )
    proxy_weights = {
        "cache_blend": weights,
        "uncached_blend": (
            weekly_prompt / (weekly_prompt + weekly_output),
            0.0,
            weekly_output / (weekly_prompt + weekly_output),
        ),
        "input": (1.0, 0.0, 0.0),
        "output": (0.0, 0.0, 1.0),
    }

    endpoints = _fetch(f"/api/frontend/v1/stats/endpoint?{query}")
    schedules: dict[str, PriceSchedule] = {}
    endpoint_ids: dict[str, str] = {}
    for endpoint in endpoints:
        pricing = endpoint["pricing"]
        name = endpoint["provider_display_name"]
        endpoint_ids[name] = endpoint["id"]
        schedules[name] = PriceSchedule(
            input=float(pricing["prompt"]) * 1_000_000,
            cache=float(pricing.get("input_cache_read") or pricing["prompt"]) * 1_000_000,
            output=float(pricing["completion"]) * 1_000_000,
        )

    uptime_recent = _fetch(f"/api/frontend/v1/stats/uptime-recent?{query}")
    uptime_means = {
        name: statistics.mean(
            float(row["uptime"])
            for row in uptime_recent.get(endpoint_id, [])
            if row.get("uptime") is not None
        )
        for name, endpoint_id in endpoint_ids.items()
        if any(
            row.get("uptime") is not None
            for row in uptime_recent.get(endpoint_id, [])
        )
    }
    uptime_qualified_providers = {
        name for name, uptime in uptime_means.items() if uptime >= 99.0
    }

    prices = {
        name: {
            proxy: schedule.blended(proxy_weight)
            for proxy, proxy_weight in proxy_weights.items()
        }
        for name, schedule in schedules.items()
    }
    cheapest_name = min(prices, key=lambda name: prices[name]["cache_blend"])
    cheapest = schedules[cheapest_name]
    cheapest_blend = prices[cheapest_name]["cache_blend"]

    sampled_shares: dict[str, list[float]] = {}
    for sample_index in range(share_samples):
        cache_buster = urllib.parse.urlencode(
            {"entry_model_sample": f"{sample_index}-{random.random()}"}
        )
        summaries = _fetch(
            f"/api/frontend/v1/stats/effective-pricing?{query}&{cache_buster}"
        )["providerSummaries"]
        total_tokens = sum(int(row["totalTokens"]) for row in summaries)
        for row in summaries:
            sampled_shares.setdefault(row["providerName"], []).append(
                int(row["totalTokens"]) / total_tokens
            )
        if sample_index + 1 < share_samples:
            time.sleep(sample_delay)
    shares = {name: statistics.median(values) for name, values in sampled_shares.items()}
    scenarios = infer_fitness_scenarios(
        shares,
        prices,
        stable_providers=uptime_qualified_providers,
        proxies=tuple(proxy_weights),
    )

    if common_prices is not None:
        price_ratios = tuple(price / cheapest_blend for price in common_prices)
    elif price_ratios is None:
        price_ratios = DEFAULT_PRICE_RATIOS

    points: list[dict[str, object]] = []
    tool_fraction_proxy = min(weekly_tool_calls / weekly_requests, 1.0)
    request_rate_hourly = weekly_requests / (7 * 24)
    tool_call_rate_hourly = weekly_tool_calls / (7 * 24)
    minimum_general_evaluation_share = 100 / (request_rate_hourly * 0.5)
    minimum_tool_evaluation_share = 200 / (tool_call_rate_hourly * 2)
    for ratio in price_ratios:
        blend = cheapest_blend * ratio
        scenario_points: dict[str, dict[str, object]] = {}
        for scenario, fitness in scenarios.items():
            optimistic = project_entry(
                price_ratio=ratio,
                fitness=fitness,
                cheapest=cheapest,
                monthly_uncached_prompt_tokens=monthly_uncached,
                monthly_cached_prompt_tokens=monthly_cached,
                monthly_output_tokens=monthly_output,
                monthly_requests=monthly_requests,
                cogs_ratio=cogs_ratio,
            )
            anchor_share = fitness / (cogs_ratio * cogs_ratio + fitness)
            for label, multiplier in (
                ("known_good_tool_tier", 1.0),
                ("insufficient_data_tool_lower_bound", 0.0),
            ):
                adjusted_share = cohort_adjusted_share(
                    anchor_share=anchor_share,
                    anchor_price_ratio=cogs_ratio,
                    price_ratio=ratio,
                    tool_fraction=tool_fraction_proxy,
                    tool_tier_multiplier=multiplier,
                )
                optimistic[label] = _project_at_share(
                    token_share=adjusted_share,
                    price_ratio=ratio,
                    cheapest=cheapest,
                    monthly_uncached_prompt_tokens=monthly_uncached,
                    monthly_cached_prompt_tokens=monthly_cached,
                    monthly_output_tokens=monthly_output,
                    monthly_requests=monthly_requests,
                    cogs_ratio=cogs_ratio,
                )
            scenario_points[scenario] = optimistic
        points.append(
            {
                "price_ratio_to_cheapest_listed_schedule": ratio,
                "common_mix_price_per_million": blend,
                "price_rank_after_entry": 1
                + sum(values["cache_blend"] < blend for values in prices.values()),
                "scenarios": scenario_points,
            }
        )

    return {
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "model": "GLM-5.2",
        "permaslug": PERMASLUG,
        "evidence_window": {
            "start": selected[0]["date"][:10],
            "end": selected[-1]["date"][:10],
            "complete_utc_days": 7,
        },
        "assumption": {
            "uptime": ">=99%",
            "routing_status": "stable; 99% clears the documented 95% normal-routing gate",
            "price_change": "input, cache-read, and output prices scale proportionally",
            "demand": "market volume and workload mix remain constant",
            "cogs_ratio_to_cheapest_schedule": cogs_ratio,
            "fitness": "empirical distribution among currently stable incumbent endpoints",
            "tool_request_fraction_proxy": tool_fraction_proxy,
        },
        "interpretation": {
            "revenue": "gross customer-facing endpoint billings before OpenRouter/provider commercial terms",
            "p50": "median stable-incumbent-equivalent planning case after ramp",
            "p10_p90": "empirical stable-incumbent scenario band, not a calibrated confidence interval",
            "not_included": "new-endpoint ramp, capacity ceilings, explicit provider pinning, or guaranteed Auto Exacto tier",
            "top_level_scenario_fields": "optimistic upper-elasticity case where all traffic is price weighted",
            "known_good_tool_tier": "tool cohort holds its anchor share while only non-tool traffic reprices",
            "insufficient_data_tool_lower_bound": "zero tool-cohort share until the endpoint reaches a known-good tier",
        },
        "market": {
            "monthly_requests": monthly_requests,
            "monthly_uncached_prompt_tokens": monthly_uncached,
            "monthly_cached_prompt_tokens": monthly_cached,
            "monthly_output_tokens": monthly_output,
            "monthly_total_tokens": monthly_total,
            "whole_market_billings_at_cheapest_schedule": (
                monthly_uncached * cheapest.input
                + monthly_cached * cheapest.cache
                + monthly_output * cheapest.output
            )
            / 1_000_000,
        },
        "qualification_traffic": {
            "documented_general_minimum": "100 requests in a 30-minute window",
            "documented_tool_minimum": "200 tool-call requests in a 2-hour window",
            "market_requests_per_hour": request_rate_hourly,
            "market_tool_calls_per_hour": tool_call_rate_hourly,
            "minimum_market_share_for_general_threshold": minimum_general_evaluation_share,
            "minimum_market_share_for_tool_threshold_proxy": minimum_tool_evaluation_share,
            "limiting_minimum_market_share": max(
                minimum_general_evaluation_share, minimum_tool_evaluation_share
            ),
        },
        "cheapest_listed_provider": cheapest_name,
        "cheapest_listed_schedule_per_million": asdict(cheapest),
        "cheapest_common_mix_price_per_million": cheapest_blend,
        "endpoint_count_before_entry": len(endpoints),
        "uptime_qualified_incumbent_count": len(
            set(shares) & set(prices) & uptime_qualified_providers
        ),
        "uptime_qualification": {
            "minimum_three_day_mean_percent": 99.0,
            "provider_means_percent": uptime_means,
        },
        "endpoint_age_and_share_snapshot": [
            {
                "provider": endpoint["provider_display_name"],
                "created_at": endpoint["created_at"],
                "age_days": (
                    dt.datetime.now(dt.timezone.utc)
                    - dt.datetime.fromisoformat(endpoint["created_at"].replace("Z", "+00:00"))
                ).total_seconds()
                / 86_400,
                "three_day_mean_uptime_percent": uptime_means.get(
                    endpoint["provider_display_name"]
                ),
                "provider_token_share": shares.get(endpoint["provider_display_name"], 0.0),
                "current_status": endpoint.get("status"),
                "requests_last_30_minutes": (endpoint.get("stats") or {}).get(
                    "request_count"
                ),
            }
            for endpoint in endpoints
        ],
        "fitness_scenarios": scenarios,
        "points": points,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--price-ratios",
        type=_parse_csv_floats,
        help="comma-separated proportional price schedules relative to cheapest listed",
    )
    parser.add_argument(
        "--common-prices",
        type=_parse_csv_floats,
        help="comma-separated common-workload blended prices per million tokens",
    )
    parser.add_argument("--share-samples", type=int, default=12)
    parser.add_argument("--sample-delay", type=float, default=0.05)
    parser.add_argument("--cogs-ratio", type=float, default=1.25)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.share_samples < 1:
        raise SystemExit("share-samples must be positive")
    if args.cogs_ratio <= 0:
        raise SystemExit("cogs-ratio must be positive")
    if args.price_ratios and args.common_prices:
        raise SystemExit("choose price-ratios or common-prices, not both")

    result = build_live_model(
        price_ratios=args.price_ratios,
        common_prices=args.common_prices,
        cogs_ratio=args.cogs_ratio,
        share_samples=args.share_samples,
        sample_delay=args.sample_delay,
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
