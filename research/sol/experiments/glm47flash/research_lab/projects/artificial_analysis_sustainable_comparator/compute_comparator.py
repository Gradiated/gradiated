#!/usr/bin/env python3
"""Reproducibly extract the live AA page and calculate campaign-normalized bounds."""
import hashlib
import json
import re
import urllib.request
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
URL = "https://artificialanalysis.ai/models/glm-4-7-flash-non-reasoning/providers"
REASONING_URL = "https://artificialanalysis.ai/models/glm-4-7-flash/providers"
BASE = 0.4453081746916901
RATE = 535.2861037029285
SETUP_SESSION_SECONDS = 1412.452
PRODUCTIVE_BATCH_SECONDS = 61.215861524


def page(url):
    with urllib.request.urlopen(url, timeout=20) as response:
        body = response.read()
    return body, hashlib.sha256(body).hexdigest()


def prices(body):
    text = body.decode("utf-8")
    result = {}
    for provider in ("Amazon", "Novita"):
        match = re.search(r'"label":"' + provider + r'","price":\[(.*?)\]', text)
        if not match:
            raise RuntimeError(f"missing price record for {provider}")
        values = {k: float(v) for k, v in re.findall(r'"name":"(inputPrice|outputPrice)","value":([0-9.]+)', match.group(1))}
        result[provider] = values
    speeds = {k: float(v) for k, v in re.findall(r'"label":"(Amazon|Novita)","medianOutputSpeed":([0-9.]+)', text)}
    blends = {k: float(v) for k, v in re.findall(r'"label":"(Amazon|Novita)","pricePerMillionTokens":([0-9.]+)', text)}
    return result, speeds, blends


def main():
    body, source_hash = page(URL)
    provider_prices, speeds, blends = prices(body)
    # AA's 7:2:1 blend omits cache-hit pricing for these providers; the page's
    # reported .103 is exactly .9*.07 + .1*.40, so cached input is conservatively
    # charged at the uncached input price in the campaign's 8:1 workload.
    workload = {}
    for name, p in provider_prices.items():
        workload[name] = {
            "usd_per_m_output_at_8_to_1": 8 * p["inputPrice"] + p["outputPrice"],
            "usd_per_m_blended_at_7_2_1": 0.9 * p["inputPrice"] + 0.1 * p["outputPrice"],
        }
    snapshot_hurdle = 8 * (7 / 9 * 0.01 + 2 / 9 * 0.06) + 0.4
    snapshot_cache_sensitivity = [
        {"cached_input_fraction": f, "usd_per_m_output": 8 * (f * 0.01 + (1 - f) * 0.06) + 0.4}
        for f in (0.0, 0.5, 7 / 9, 1.0)
    ]
    lifecycle = []
    for batches in (1, 10, 32, 100):
        factor = (SETUP_SESSION_SECONDS + batches * PRODUCTIVE_BATCH_SECONDS) / (batches * PRODUCTIVE_BATCH_SECONDS)
        lifecycle.append({"batches_per_session": batches, "cost_factor_vs_steady_state": factor, "usd_per_m_output": BASE * factor})
    result = {
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"url": URL, "sha256": source_hash, "variant": "GLM-4.7-Flash (Non-reasoning)"},
        "source_facts": {"providers": list(provider_prices), "aa_default_ratio": "7:2:1 cache-hit:input:output", "reported_blended_prices": blends, "output_speed_tokens_per_second_p50_72h": speeds, "cache_hit_price_published": False},
        "campaign_workload": {"input_tokens": 8192, "output_tokens": 1024, "input_output_ratio": "8:1", "non_reasoning_cache_assumption": "cache-hit input is charged at published input price because no cache-hit price is published"},
        "providers": provider_prices,
        "normalized": workload,
        "historical_reasoning_snapshot": {"source_url": REASONING_URL, "deepinfra_components": {"cache_hit": 0.01, "input": 0.06, "output": 0.4}, "campaign_8_to_1_cache_fraction_sensitivity": snapshot_cache_sensitivity, "campaign_8_to_1_usd_per_m_output_at_7_of_9_cached": snapshot_hurdle, "status": "separate reasoning variant; not interchangeable with live non-reasoning page"},
        "c16": {"measured_output_tokens_per_second": RATE, "steady_state_usd_per_m_output": BASE, "session_exposure_seconds": SETUP_SESSION_SECONDS, "productive_c16_batch_seconds": PRODUCTIVE_BATCH_SECONDS, "lifecycle_sensitivity": lifecycle},
        "break_even": {"strict_live_non_reasoning_hurdle_usd_per_m_output": min(v["usd_per_m_output_at_8_to_1"] for v in workload.values()), "historical_reasoning_hurdle_usd_per_m_output": snapshot_hurdle, "minimum_productive_utilization_no_extra_overhead": {"strict_live_non_reasoning": BASE / 0.96, "historical_reasoning": BASE / snapshot_hurdle}, "maximum_lifecycle_overhead_at_100_percent_utilization": {"strict_live_non_reasoning": 0.96 / BASE - 1, "historical_reasoning": snapshot_hurdle / BASE - 1}, "minimum_batches_per_session_to_amortize_measured_setup": {"strict_live_non_reasoning": math.ceil(SETUP_SESSION_SECONDS / (PRODUCTIVE_BATCH_SECONDS * (0.96 / BASE - 1))), "historical_reasoning": math.ceil(SETUP_SESSION_SECONDS / (PRODUCTIVE_BATCH_SECONDS * (snapshot_hurdle / BASE - 1)))}, "sensitivity_formula": "sustainable_usd_per_m_output = 0.4453081747 * (1 + lifecycle_overhead_fraction) / productive_utilization; lifecycle_overhead includes interruption loss, reload, retries, disk/network/orchestration, and idle capacity"},
        "interpretation": "c16 clears the live non-reasoning price hurdle if productive utilization is at least 46.4% with no extra overhead, and clears the historical reasoning hurdle at 78.3%; at 100% utilization it tolerates 115.6% and 27.8% lifecycle overhead respectively. Variant and quality equivalence remain unresolved.",
    }
    out = ROOT / "COMPARATOR_ECONOMICS_2026-07-15.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"artifact": str(out), "source_sha256": source_hash, "strict_live_hurdle": 0.96, "historical_reasoning_hurdle": snapshot_hurdle, "c16_steady_state": BASE}, indent=2))


if __name__ == "__main__":
    main()
