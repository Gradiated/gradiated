#!/usr/bin/env python3
"""Deterministic FIFO replica replay for the bound H100 arrival trace."""
import argparse
import hashlib
import heapq
import json
import math
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
SOURCE = PROJECT.parent / "gemma4_h100_v0515_ngram_price_normalized"
TERMINAL = SOURCE / "artifacts/h100-repair5-20260725t0746z/FINAL_TERMINAL.json"
TRACE = SOURCE / "packet/candidate-v0.5.15/inputs/requests.jsonl"
PRICES = PROJECT.parents[5] / "factory/data/gpu_prices.json"
TARGET_USD_PER_MILLION = 0.14
HEADROOM_UTILIZATION = 0.90
ACTUAL_EXPERIMENT_RATE_USD_HOUR = 2.95
SENSITIVITY_FACTORS = (0.8, 1.0, 1.2)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], quantile: float) -> float:
    values = sorted(values)
    position = (len(values) - 1) * quantile
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return values[low]
    return values[low] * (high - position) + values[high] * (position - low)


def load_inputs() -> tuple[dict, list[dict], dict]:
    terminal = json.loads(TERMINAL.read_text())
    rows = [json.loads(line) for line in TRACE.read_text().splitlines() if line]
    prices = json.loads(PRICES.read_text())
    if len(rows) != 1036 or [row["i"] for row in rows] != list(range(1036)):
        raise ValueError("trace must be exactly 1,036 ordered rows")
    if any(set(row) != {"client_started_s", "completed_s", "i", "request_sha256", "scheduled_s", "submitted_s", "timing", "usage"} for row in rows):
        raise ValueError("trace schema differs from the bound request contract")
    if any(row["usage"] != {"prompt_tokens": 4214, "completion_tokens": 358, "total_tokens": 4572} for row in rows):
        raise ValueError("trace token geometry differs from the bound workload")
    if terminal["requests"] != 171 or terminal["total_tokens"] != 781812:
        raise ValueError("settled terminal request or token accounting mismatch")
    if not (terminal["candidate_sample_consumed"] and terminal["endpoint_admitted"]):
        raise ValueError("terminal does not prove the settled discriminator state")
    return terminal, rows, prices


def replay(rows: list[dict], replicas: int, service_seconds: float) -> dict:
    available = [0.0] * replicas
    heapq.heapify(available)
    queue_depth_events: list[tuple[float, int]] = []
    waits, latencies, completions = [], [], []
    for row in rows:
        arrival = row["scheduled_s"]
        free_at = heapq.heappop(available)
        start = max(arrival, free_at)
        complete = start + service_seconds
        heapq.heappush(available, complete)
        waits.append(start - arrival)
        latencies.append(complete - arrival)
        completions.append(complete)
        queue_depth_events.append((arrival, 1))
        queue_depth_events.append((start, -1))
    depth = peak = 0
    for _, delta in sorted(queue_depth_events, key=lambda event: (event[0], event[1])):
        depth += delta
        peak = max(peak, depth)
    arrival_span = rows[-1]["scheduled_s"] - rows[0]["scheduled_s"]
    drain_span = max(completions) - rows[0]["scheduled_s"]
    busy_seconds = len(rows) * service_seconds
    return {
        "replicas": replicas,
        "service_seconds_per_request": service_seconds,
        "arrival_span_seconds": arrival_span,
        "drain_span_seconds": drain_span,
        "average_utilization_over_arrival_span": busy_seconds / (replicas * arrival_span),
        "average_utilization_over_drain_span": busy_seconds / (replicas * drain_span),
        "queue": {
            "peak_waiting_requests": peak,
            "final_waiting_requests": 0,
            "wait_seconds": {"p50": percentile(waits, .50), "p95": percentile(waits, .95), "p99": percentile(waits, .99), "max": max(waits)},
        },
        "latency_seconds": {"p50": percentile(latencies, .50), "p95": percentile(latencies, .95), "p99": percentile(latencies, .99), "max": max(latencies)},
        "completed": len(completions),
    }


def cost_per_million(hourly_rate: float, replicas: int, elapsed_seconds: float, total_tokens: int) -> float:
    return hourly_rate * replicas * elapsed_seconds / 3600 / total_tokens * 1_000_000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=PROJECT / "HEADROOM_RESULT.json")
    args = parser.parse_args()
    terminal, rows, prices = load_inputs()
    accelerator_rows = prices["accelerators"]
    if isinstance(accelerator_rows, dict):
        h100_price = accelerator_rows["nvidia-h100-sxm"]
    else:
        h100_price = next(row for row in accelerator_rows if row["id"] == "nvidia-h100-sxm")
    planning_rate = h100_price["production_planning_usd_per_gpu_hour"]
    central_service = terminal["service_seconds_per_request"]
    total_tokens = sum(row["usage"]["total_tokens"] for row in rows)
    arrival_span = rows[-1]["scheduled_s"] - rows[0]["scheduled_s"]
    rates = {"planning_committed": planning_rate, "actual_experiment": ACTUAL_EXPERIMENT_RATE_USD_HOUR}
    required_replicas = math.ceil(len(rows) * central_service / (HEADROOM_UTILIZATION * arrival_span))
    one_replica_headroom_ceiling = HEADROOM_UTILIZATION * arrival_span / len(rows)
    continuous_ceilings = {
        name: TARGET_USD_PER_MILLION * HEADROOM_UTILIZATION * 3600 * (total_tokens / len(rows)) / (rate * 1_000_000)
        for name, rate in rates.items()
    }
    sensitivity = []
    for factor in SENSITIVITY_FACTORS:
        service = central_service * factor
        minimum_replicas = math.ceil(len(rows) * service / (HEADROOM_UTILIZATION * arrival_span))
        sensitivity.append({
            "factor_of_settled_service_time": factor,
            "minimum_replicas_at_90pct_headroom": minimum_replicas,
            "replay": replay(rows, minimum_replicas, service),
        })
    central = next(row for row in sensitivity if row["factor_of_settled_service_time"] == 1.0)
    discrete_cost = {
        name: cost_per_million(rate, required_replicas, central["replay"]["drain_span_seconds"], total_tokens)
        for name, rate in rates.items()
    }
    capacity_cost = {
        name: rate * central_service / (HEADROOM_UTILIZATION * 3600 * (total_tokens / len(rows))) * 1_000_000
        for name, rate in rates.items()
    }
    result = {
        "schema_version": 1,
        "classification": "analytical_discrete_event_replica_headroom_replay",
        "evidence_type": "deterministic_cpu_simulation_and_derived_economics_not_measured_endpoint",
        "scope_boundary": "No GPU, provider, SSH, live-bench mutation, or replay of the consumed 171-request discriminator occurred.",
        "input_manifest": {
            "settled_terminal": {"path": str(TERMINAL.relative_to(PROJECT.parent)), "sha256": sha256(TERMINAL)},
            "request_trace": {"path": str(TRACE.relative_to(PROJECT.parent)), "sha256": sha256(TRACE)},
            "price_inventory": {"path": str(PRICES.relative_to(PROJECT.parents[6])), "sha256": sha256(PRICES)},
        },
        "settled_discriminator": {
            "requests": terminal["requests"], "total_tokens": terminal["total_tokens"], "service_seconds_per_request": central_service,
            "queue_peak": terminal["queue_peak"], "queue_final": terminal["queue_final"], "failures": len(terminal["failures"]),
        },
        "trace": {"requests": len(rows), "total_tokens": total_tokens, "tokens_per_request": total_tokens / len(rows), "arrival_span_seconds": arrival_span},
        "assumptions": {
            "queue_discipline": "FIFO, dispatch each request to the earliest available identical replica",
            "service_model": "constant service time per request; no invented per-request service distribution",
            "headroom_utilization": HEADROOM_UTILIZATION,
            "sensitivity_factors": list(SENSITIVITY_FACTORS),
            "cost_scope": "GPU-hour only; storage, orchestration, failures, and reloads are excluded because no bound values are available",
        },
        "replica_headroom": {"central_minimum_replicas": required_replicas, "sensitivity": sensitivity},
        "economics_usd_per_million_total_tokens": {
            "continuous_90pct_capacity_model": capacity_cost,
            "trace_provisioned_discrete_replicas": discrete_cost,
            "interpretation": "The capacity model assumes sustained 90% productive utilization. The trace-provisioned model bills the minimum discrete central replica fleet through its observed drain span.",
        },
        "service_time_ceilings_seconds_per_request": {
            "continuous_90pct_capacity_at_0_14_per_million": continuous_ceilings,
            "one_replica_90pct_headroom_on_exact_trace": one_replica_headroom_ceiling,
            "central_service_time": central_service,
            "required_reduction_to_one_replica_fraction": 1 - one_replica_headroom_ceiling / central_service,
        },
        "decision": {
            "continuous_planning_target_passes": capacity_cost["planning_committed"] <= TARGET_USD_PER_MILLION,
            "discrete_trace_provisioned_target_passes": discrete_cost["planning_committed"] <= TARGET_USD_PER_MILLION,
            "summary": "At the settled service time the exact trace needs two replicas to preserve 90% utilization headroom. It passes only the continuous 90%-utilization planning model, not the finite-trace discrete-fleet cost model; a one-replica trace requires service at or below the reported one-replica ceiling.",
            "endpoint_field_most_decisive": "The pending 791-request endpoint's service_seconds_per_request (with its exact arrival trace) is decisive: <= one_replica_90pct_headroom_on_exact_trace removes the discrete two-replica step; otherwise its sustained utilization and queue trajectory determine whether demand can be pooled near 90%.",
        },
        "actual_spend_usd": 0.0,
        "provider_mutation": "none",
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"out": str(args.out), "replicas": required_replicas, "planning_discrete_cost": discrete_cost["planning_committed"], "one_replica_ceiling": one_replica_headroom_ceiling}, sort_keys=True))


if __name__ == "__main__":
    main()
