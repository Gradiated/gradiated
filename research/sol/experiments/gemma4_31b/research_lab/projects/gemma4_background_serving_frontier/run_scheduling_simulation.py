#!/usr/bin/env python3
import hashlib
import json
import math
import random
import re
from pathlib import Path
from statistics import mean


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parent
ENDPOINT = LAB / "sglang_v0512_h200_gemma4_mtp_endpoint/artifacts/sglang-v0512-h200-mtp-20260718t0925z-owner/stock-repaired"
ENDPOINT_TERMINAL = ENDPOINT / "TERMINAL.json"
METRICS_BEFORE = ENDPOINT / "metrics-before.prom"
METRICS_AFTER = ENDPOINT / "metrics-after.prom"
LINEAR_TERMINAL = LAB / "h200_bf16_exact_linear_floor/artifacts/RECONCILED_TERMINAL.json"
PREFILL = LAB / "h200_c32_prefill_peak_compute_floor/RECONCILIATION.json"
ECONOMIC = LAB / "h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json"
PREFIX = LAB / "prefix_cache_primary_mix_bound/PREFIX_BOUND.json"

SEED = 20260718
REQUESTS = 100_000
PROMPT_TOKENS = 4214
OUTPUT_TOKENS = 358
CAMPAIGN_CACHE_FRACTION = 0.127
PRODUCTION_GPU_USD_HOUR = 3.25
EXPERIMENT_GPU_USD_HOUR = 2.46


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metric(path: Path, name: str, suffix: str) -> float:
    pattern = rf"^{re.escape(name)}_{suffix}\{{[^}}]*\}} ([^\n]+)"
    match = re.search(pattern, path.read_text(), re.MULTILINE)
    if not match:
        raise ValueError(f"missing metric {name}_{suffix} in {path}")
    return float(match.group(1))


def metric_delta(name: str, suffix: str) -> float:
    return metric(METRICS_AFTER, name, suffix) - metric(METRICS_BEFORE, name, suffix)


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lo = math.floor(index)
    hi = math.ceil(index)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - index) + ordered[hi] * (index - lo)


def simulate(batch_size: int, service_seconds_per_request: float, arrival_rate: float) -> dict:
    rng = random.Random(SEED)
    arrivals = []
    now = 0.0
    for _ in range(REQUESTS):
        now += rng.expovariate(arrival_rate)
        arrivals.append(now)

    batch_seconds = batch_size * service_seconds_per_request
    server_free = 0.0
    queue = []
    e2e = []
    completion_times = []
    batch_sizes = []
    for offset in range(0, REQUESTS, batch_size):
        batch = arrivals[offset : offset + batch_size]
        start = max(server_free, batch[-1])
        complete = start + batch_seconds
        queue.extend(start - arrival for arrival in batch)
        e2e.extend(complete - arrival for arrival in batch)
        completion_times.extend([complete] * len(batch))
        batch_sizes.append(len(batch))
        server_free = complete

    capacity = 1.0 / service_seconds_per_request
    arrival_span = arrivals[-1] - arrivals[0]
    completion_span = completion_times[-1] - arrivals[0]
    first_tenth = queue[: REQUESTS // 10]
    last_tenth = queue[-REQUESTS // 10 :]
    return {
        "batch_size": batch_size,
        "requests": REQUESTS,
        "seed": SEED,
        "arrival_rate_requests_per_second": arrival_rate,
        "capacity_requests_per_second": capacity,
        "traffic_intensity": arrival_rate / capacity,
        "stable": arrival_rate < capacity,
        "batch_service_seconds": batch_seconds,
        "service_seconds_per_request": service_seconds_per_request,
        "mean_batch_size": mean(batch_sizes),
        "queue_seconds": {
            "mean": mean(queue),
            "p50": quantile(queue, 0.50),
            "p95": quantile(queue, 0.95),
            "p99": quantile(queue, 0.99),
            "first_tenth_mean": mean(first_tenth),
            "last_tenth_mean": mean(last_tenth),
            "drift_last_minus_first_tenth_mean": mean(last_tenth) - mean(first_tenth),
        },
        "completion_seconds": {
            "mean": mean(e2e),
            "p50": quantile(e2e, 0.50),
            "p95": quantile(e2e, 0.95),
            "p99": quantile(e2e, 0.99),
        },
        "finite_trace": {
            "arrival_span_seconds": arrival_span,
            "drain_span_seconds": completion_span,
            "arrival_throughput_requests_per_second": (REQUESTS - 1) / arrival_span,
            "drained_throughput_requests_per_second": REQUESTS / completion_span,
            "failures": 0,
            "reloads": 0,
        },
    }


def main() -> None:
    endpoint = json.loads(ENDPOINT_TERMINAL.read_text())
    linears = json.loads(LINEAR_TERMINAL.read_text())
    prefill = json.loads(PREFILL.read_text())
    economic = json.loads(ECONOMIC.read_text())
    prefix = json.loads(PREFIX.read_text())

    complete = metric_delta("sglang:e2e_request_latency_seconds", "count")
    prompt = metric_delta("sglang:prompt_tokens_histogram", "sum")
    uncached = metric_delta("sglang:uncached_prompt_tokens_histogram", "sum")
    generation = metric_delta("sglang:generation_tokens_histogram", "sum")
    e2e_sum = metric_delta("sglang:e2e_request_latency_seconds", "sum")
    ttft_sum = metric_delta("sglang:time_to_first_token_seconds", "sum")
    if complete != 32 or prompt != 32 * PROMPT_TOKENS or generation != 32 * OUTPUT_TOKENS:
        raise ValueError("endpoint token/accounting identity mismatch")
    if uncached != 32:
        raise ValueError("expected exactly one uncached prompt token per endpoint request")

    component = {row["m"]: row["combined_seconds_per_request_358_steps"] for row in linears["combined_cuda_event_component_floor"]}
    c16_component = component[16]
    c32_component = component[32]
    prefill_floor = float(prefill["algebra"]["prefill_linear_floor_seconds_per_request"])
    prefill_floor_per_fresh_token = prefill_floor / (PROMPT_TOKENS * (1 - CAMPAIGN_CACHE_FRACTION))
    missing_fresh_tokens = PROMPT_TOKENS * (1 - CAMPAIGN_CACHE_FRACTION) - uncached / complete
    missing_prefill_floor = missing_fresh_tokens * prefill_floor_per_fresh_token
    measured_cached_c32 = endpoint["service_seconds_per_request"]
    calibrated_c32 = measured_cached_c32 + missing_prefill_floor
    calibrated_c16 = calibrated_c32 + c16_component - c32_component

    strict_price = economic["inputs"]["market_request_cost_usd"]["DeepInfra_fp8"]
    strict_required_rate = economic["gate_by_market_target"]["required_completed_requests_per_second"]["DeepInfra_fp8"]["planning_base"][1]
    all_in_factor = strict_price * strict_required_rate / (PRODUCTION_GPU_USD_HOUR / 3600)

    simulations = {
        "c16": simulate(16, calibrated_c16, strict_required_rate),
        "c32": simulate(32, calibrated_c32, strict_required_rate),
    }
    for row in simulations.values():
        capacity = row["capacity_requests_per_second"]
        row["cost_usd_per_complete_request_at_saturation"] = {
            "production_gpu_only": PRODUCTION_GPU_USD_HOUR / 3600 / capacity,
            "production_all_in_gate_factor": PRODUCTION_GPU_USD_HOUR / 3600 / capacity * all_in_factor,
            "experimental_gpu_only_if_remeasured": EXPERIMENT_GPU_USD_HOUR / 3600 / capacity,
        }
        row["strict_market_price_pass_at_saturation"] = row["cost_usd_per_complete_request_at_saturation"]["production_all_in_gate_factor"] <= strict_price

    c16_cost = simulations["c16"]["cost_usd_per_complete_request_at_saturation"]["production_all_in_gate_factor"]
    c32_cost = simulations["c32"]["cost_usd_per_complete_request_at_saturation"]["production_all_in_gate_factor"]
    improvement = 1 - c32_cost / c16_cost
    matched_stable_rate = 0.9 / calibrated_c16
    matched_stable = {
        "purpose": "queueing/latency comparison at a shared load stable for both policies",
        "c16": simulate(16, calibrated_c16, matched_stable_rate),
        "c32": simulate(32, calibrated_c32, matched_stable_rate),
    }

    source_manifest = {
        str(path): sha256(path)
        for path in [ENDPOINT_TERMINAL, METRICS_BEFORE, METRICS_AFTER, LINEAR_TERMINAL, PREFILL, ECONOMIC, PREFIX]
    }
    result = {
        "schema_version": 1,
        "classification": "c32_occupancy_material_but_insufficient_for_strict_h200_economics",
        "evidence_type": "deterministic_cpu_discrete_event_simulation_calibrated_to_actual_sglang_endpoint_and_exact_geometry_floors",
        "source_manifest": source_manifest,
        "endpoint_telemetry": {
            "complete_requests": complete,
            "prompt_tokens_per_request": prompt / complete,
            "uncached_prompt_tokens_per_request": uncached / complete,
            "measured_cache_read_fraction": 1 - uncached / prompt,
            "campaign_cache_read_fraction": CAMPAIGN_CACHE_FRACTION,
            "completion_tokens_per_request": generation / complete,
            "mean_ttft_seconds": ttft_sum / complete,
            "mean_e2e_seconds": e2e_sum / complete,
            "batch_seconds": endpoint["batch_seconds"],
            "service_seconds_per_request": measured_cached_c32,
            "failures": 0,
            "retractions_delta": 0,
            "pauses_delta": 0,
            "startup_available_gpu_memory_gib": 20.69561767578125,
            "power_watts": None,
            "power_boundary": "source endpoint retained no decision-bearing nvidia-smi power samples",
        },
        "service_curve": {
            "method": "actual cached c32 whole-request service + impossible-ideal missing-fresh-prefill floor; c16 adds the exact measured c16-minus-c32 decode-linear/head component gap",
            "missing_fresh_prompt_tokens_per_request": missing_fresh_tokens,
            "missing_prefill_floor_seconds_per_request": missing_prefill_floor,
            "c16_seconds_per_request": calibrated_c16,
            "c32_seconds_per_request": calibrated_c32,
            "boundary": "optimistic cache-corrected proxy, not a measured exact-mix endpoint; overlap and non-linear prefill inefficiency can only weaken the economic conclusion",
        },
        "economic_target": {
            "strict_market_price_usd_per_request": strict_price,
            "strict_required_requests_per_second": strict_required_rate,
            "production_h200_usd_per_hour": PRODUCTION_GPU_USD_HOUR,
            "derived_all_in_factor": all_in_factor,
        },
        "simulations": simulations,
        "matched_stable_queueing": matched_stable,
        "comparison": {
            "c32_vs_c16_saturation_cost_reduction_fraction": improvement,
            "clears_project_5pct_intervention_gate": improvement >= 0.05,
            "c32_capacity_shortfall_vs_strict_target_fraction": 1 - simulations["c32"]["capacity_requests_per_second"] / strict_required_rate,
            "c16_capacity_shortfall_vs_strict_target_fraction": 1 - simulations["c16"]["capacity_requests_per_second"] / strict_required_rate,
            "decision": "retain c32 occupancy as the stock scheduling point, but do not promote scheduling-only H200 economics; even the optimistic cache-corrected c32 proxy is unstable at the strict target and misses strict all-in price",
        },
        "ranking": [
            {"rank": 1, "interaction": "background pooling to c32 instead of c16 occupancy", "reason": "direct c32 endpoint plus exact c16/c32 component gap predicts material cost movement; tested here"},
            {"rank": 2, "interaction": "prefix reuse plus batch ordering", "reason": f"endpoint accidentally realized {1 - uncached / prompt:.6%} cache reads, while campaign is 12.7%; source bound requires {prefix['endpoint_transfer_bound']['best_case_required_prefill_wall_share']:.6%} exposed prefill share"},
            {"rank": 3, "interaction": "chunked prefill with decode-priority or async overlap", "reason": "plausible under mixed arrivals but no matched endpoint phase telemetry; synchronized c32 capture cannot identify overlap benefit"},
            {"rank": 4, "interaction": "CUDA-graph capture geometry", "reason": "production geometry retained graphs and passed c32, but no graph-off comparator exists and snapshot gauge was not decision-bearing"},
            {"rank": 5, "interaction": "hybrid local/global attention-aware scheduling", "reason": "model-specific mechanism is plausible, but no supported scheduler arm or exact component result exists; cheapest falsifier follows only if c32 scheduling survives economics"},
        ],
        "experiment_spend_usd": 0.0,
        "provider_mutation": "none",
    }
    (PROJECT / "SCHEDULING_SIMULATION.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["comparison"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
