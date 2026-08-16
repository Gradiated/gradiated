#!/usr/bin/env python3
"""Reproduce the GLM-5.2 OpenRouter subsidy/MRR sensitivity.

Uses only public OpenRouter endpoints and the Python standard library. It emits
JSON to stdout and does not mutate repository state. Provider token shares are
sampled repeatedly because the public summary is visibly mutable.
"""

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


BASE = "https://openrouter.ai"
PERMASLUG = "z-ai/glm-5.2-20260616"
VARIANT = "standard"
START_DATE = "2026-07-09"
END_DATE = "2026-07-15"
MONTHS_PER_WEEK = 365.25 / 12 / 7
COGS_RATIO = 1.25
TARGET_MRR = 10_000_000 / 12
BUDGETS = [0, 25_000, 50_000, 100_000, 250_000, 500_000, 750_000, 1_000_000, 1_500_000, 2_000_000]


def fetch(path: str) -> object:
    request = urllib.request.Request(
        BASE + path,
        headers={"User-Agent": "Inference-Foundry-public-evidence/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["data"]


def quantile(values: list[float], percentile: int) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def share(fitness: float, price_ratio: float) -> float:
    return fitness / (price_ratio * price_ratio + fitness)


def mrr(market_at_cheapest: float, fitness: float, price_ratio: float) -> float:
    return market_at_cheapest * price_ratio * share(fitness, price_ratio)


def subsidy(market_at_cheapest: float, fitness: float, price_ratio: float) -> float:
    return market_at_cheapest * (COGS_RATIO - price_ratio) * share(fitness, price_ratio)


def optimize_for_budget(market: float, fitness: float, budget: float) -> dict[str, float]:
    revenue_optimum = min(COGS_RATIO, math.sqrt(fitness))
    optimum_subsidy = subsidy(market, fitness, revenue_optimum)
    if optimum_subsidy <= budget:
        price_ratio = revenue_optimum
    else:
        low, high = revenue_optimum, COGS_RATIO
        for _ in range(100):
            middle = (low + high) / 2
            if subsidy(market, fitness, middle) > budget:
                low = middle
            else:
                high = middle
        price_ratio = high
    return {
        "price_ratio_to_cheapest": price_ratio,
        "traffic_share": share(fitness, price_ratio),
        "mrr": mrr(market, fitness, price_ratio),
        "subsidy_used": subsidy(market, fitness, price_ratio),
    }


def target_solution(market: float, fitness: float) -> dict[str, object]:
    if mrr(market, fitness, COGS_RATIO) >= TARGET_MRR:
        return {"attainable": True, "price_ratio_to_cheapest": COGS_RATIO, "subsidy": 0.0}
    fraction = TARGET_MRR / market
    discriminant = fitness * fitness - 4 * fraction * fraction * fitness
    if discriminant < 0:
        return {
            "attainable": False,
            "maximum_mrr": mrr(market, fitness, math.sqrt(fitness)),
        }
    price_ratio = (fitness + math.sqrt(discriminant)) / (2 * fraction)
    return {
        "attainable": True,
        "price_ratio_to_cheapest": price_ratio,
        "traffic_share": share(fitness, price_ratio),
        "subsidy": subsidy(market, fitness, price_ratio),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--share-samples", type=int, default=12)
    parser.add_argument("--sample-delay", type=float, default=0.05)
    args = parser.parse_args()

    query = urllib.parse.urlencode({"permaslug": PERMASLUG, "variant": VARIANT})
    activity = fetch(f"/api/frontend/v1/stats/model-activity?{query}")["analytics"]
    activity = [row for row in activity if START_DATE <= row["date"][:10] <= END_DATE]
    prompt = sum(row["total_prompt_tokens"] for row in activity)
    output = sum(row["total_completion_tokens"] for row in activity)
    cached = sum(row["total_native_tokens_cached"] for row in activity)
    uncached = prompt - cached
    total = prompt + output
    mixes = {
        "cache_blend": (uncached / total, cached / total, output / total),
        "uncached_blend": (prompt / total, 0.0, output / total),
        "input": (1.0, 0.0, 0.0),
        "output": (0.0, 0.0, 1.0),
    }

    endpoints = fetch(f"/api/frontend/v1/stats/endpoint?{query}")
    endpoint_prices: dict[str, dict[str, float]] = {}
    for endpoint in endpoints:
        pricing = endpoint["pricing"]
        # These fields are the already-discounted display prices. pricing_json
        # contains the undiscounted base; do not apply `discount` again.
        endpoint_prices[endpoint["provider_display_name"]] = {
            "input": float(pricing["prompt"]) * 1_000_000,
            "cache": float(pricing.get("input_cache_read") or pricing["prompt"]) * 1_000_000,
            "output": float(pricing["completion"]) * 1_000_000,
        }

    share_samples: dict[str, list[float]] = {}
    for _ in range(args.share_samples):
        cache_buster = random.random()
        summaries = fetch(
            f"/api/frontend/v1/stats/effective-pricing?{query}&_audit={cache_buster}"
        )["providerSummaries"]
        sample_total = sum(row["totalTokens"] for row in summaries)
        for row in summaries:
            share_samples.setdefault(row["providerName"], []).append(
                row["totalTokens"] / sample_total
            )
        time.sleep(args.sample_delay)
    observed_shares = {
        name: statistics.median(values) for name, values in share_samples.items()
    }

    proxy_prices: dict[str, dict[str, float]] = {}
    for provider, prices in endpoint_prices.items():
        proxy_prices[provider] = {}
        for proxy, weights in mixes.items():
            proxy_prices[provider][proxy] = sum(
                weight * price
                for weight, price in zip(
                    weights, (prices["input"], prices["cache"], prices["output"])
                )
            )

    cheapest_provider = min(proxy_prices, key=lambda name: proxy_prices[name]["cache_blend"])
    cheapest_price = proxy_prices[cheapest_provider]["cache_blend"]
    cogs_price = COGS_RATIO * cheapest_price
    hypothetical_rank = 1 + sum(
        prices["cache_blend"] < cogs_price for prices in proxy_prices.values()
    )
    market_at_cheapest = total / 1_000_000 * cheapest_price * MONTHS_PER_WEEK

    proxy_quantiles: dict[str, dict[str, float]] = {}
    for proxy in mixes:
        base = proxy_prices[cheapest_provider][proxy]
        residuals = [
            observed_shares[provider] * (prices[proxy] / base) ** 2
            for provider, prices in proxy_prices.items()
            if observed_shares.get(provider, 0) > 0
        ]
        proxy_quantiles[proxy] = {
            f"p{percentile}": quantile(residuals, percentile)
            for percentile in (25, 50, 75, 90)
        }

    # Median across plausible routing-price proxies makes the scenario band
    # less dependent on an unpublished request-specific price scalar.
    scenarios = {
        name: statistics.median(values[name] for values in proxy_quantiles.values())
        for name in ("p25", "p50", "p75", "p90")
    }

    curve = {
        scenario: {
            "fitness": fitness,
            "points": {
                str(budget): optimize_for_budget(market_at_cheapest, fitness, budget)
                for budget in BUDGETS
            },
            "ten_million_arr_target": target_solution(market_at_cheapest, fitness),
        }
        for scenario, fitness in scenarios.items()
    }

    result = {
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "evidence_window": {"start": START_DATE, "end": END_DATE},
        "traffic": {
            "prompt_tokens": prompt,
            "cached_prompt_tokens": cached,
            "output_tokens": output,
            "total_tokens": total,
        },
        "price_interpretation": "pricing fields already include endpoint discount",
        "cheapest_provider": cheapest_provider,
        "cheapest_common_mix_price_per_million": cheapest_price,
        "cogs_common_mix_price_per_million": cogs_price,
        "hypothetical_price_rank": hypothetical_rank,
        "endpoint_count_after_entry": len(endpoint_prices) + 1,
        "whole_market_monthly_billings_at_cheapest": market_at_cheapest,
        "observed_share_medians": observed_shares,
        "fitness_quantiles_by_price_proxy": proxy_quantiles,
        "scenario_curve": curve,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
