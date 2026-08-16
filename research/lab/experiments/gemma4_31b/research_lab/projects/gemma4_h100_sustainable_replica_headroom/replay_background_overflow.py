#!/usr/bin/env python3
"""Hash-bound analytical replay of one H100 with bounded retail overflow."""
import argparse
import hashlib
import json
import math
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
BINDING = PROJECT / "DIRECTOR_BACKGROUND_OVERFLOW_BINDING.json"
WAIT_CAPS_SECONDS = (0.0, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0)
PERIODS = 64
ACTUAL_H100_USD_HOUR = 2.95
WAIT_LEVELS_SECONDS = (1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] if low == high else ordered[low] * (high - index) + ordered[high] * (index - low)


def resolve(binding: dict, key: str) -> Path:
    raw = Path(binding["bound_inputs"][key]["path"])
    return raw if raw.is_absolute() else (PROJECT / raw).resolve()


def verify_inputs(binding: dict) -> dict[str, dict]:
    verified = {}
    for key, row in binding["bound_inputs"].items():
        path = resolve(binding, key)
        observed = sha256(path)
        if observed != row["sha256"]:
            raise ValueError(f"{key} hash mismatch: {observed} != {row['sha256']}")
        verified[key] = {"path": str(path), "sha256": observed}
    return verified


def load_rows(binding: dict) -> list[dict]:
    rows = [json.loads(line) for line in resolve(binding, "request_trace").read_text().splitlines() if line]
    if len(rows) != binding["bound_inputs"]["request_trace"]["requests"]:
        raise ValueError("request count mismatch")
    if [row["i"] for row in rows] != list(range(len(rows))):
        raise ValueError("trace order mismatch")
    if any(row["usage"]["total_tokens"] != 4572 for row in rows):
        raise ValueError("unexpected token geometry")
    if sum(row["usage"]["total_tokens"] for row in rows) != binding["bound_inputs"]["request_trace"]["total_tokens"]:
        raise ValueError("total-token mismatch")
    return rows


def replay(rows: list[dict], service: float, replicas: int = 1, wait_cap: float | None = None, periods: int = 1) -> dict:
    period = rows[-1]["scheduled_s"] - rows[0]["scheduled_s"]
    available = [0.0] * replicas
    local_waits, local_latencies, all_waits, all_latencies = [], [], [], []
    overflow = []
    peak_waiting = 0
    for cycle in range(periods):
        offset = cycle * period
        for row in rows:
            arrival = row["scheduled_s"] + offset
            next_free = min(available)
            wait = max(0.0, next_free - arrival)
            if wait_cap is not None and wait > wait_cap:
                overflow.append({"i": row["i"], "cycle": cycle, "arrival_s": arrival, "tokens": row["usage"]["total_tokens"]})
                continue
            worker = available.index(next_free)
            start = max(arrival, next_free)
            complete = start + service
            available[worker] = complete
            local_waits.append(wait)
            local_latencies.append(complete - arrival)
            all_waits.append(wait)
            all_latencies.append(complete - arrival)
            peak_waiting = max(peak_waiting, sum(1 for free in available if free > arrival))
    end = max(available)
    return {
        "periods": periods,
        "replicas": replicas,
        "wait_cap_seconds": wait_cap,
        "local_requests": len(local_waits),
        "overflow_requests": len(overflow),
        "overflow_tokens": sum(item["tokens"] for item in overflow),
        "overflow": overflow,
        "queue": {
            "peak_in_service_or_waiting": peak_waiting,
            "drain_extension_seconds": max(0.0, end - periods * period),
            "wait_seconds": {"p50": percentile(local_waits, .5), "p95": percentile(local_waits, .95), "p99": percentile(local_waits, .99), "max": max(local_waits)},
            "latency_seconds": {"p50": percentile(local_latencies, .5), "p95": percentile(local_latencies, .95), "p99": percentile(local_latencies, .99), "max": max(local_latencies)},
        },
        "drain_span_seconds": end,
        "all_waits": all_waits,
    }


def compact(result: dict) -> dict:
    return {key: value for key, value in result.items() if key not in {"overflow", "all_waits"}}


def cost_usd_per_million(h100_rate: float, period_seconds: float, total_tokens: int, overflow_tokens: int, retail_rate: float) -> float:
    return (h100_rate * period_seconds / 3600 + overflow_tokens / 1_000_000 * retail_rate) / total_tokens * 1_000_000


def non_dominated(points: list[dict], tier: str) -> list[dict]:
    selected = []
    for point in points:
        wait = point["periodic_sustainability"]["final_wait_seconds"]["max"]
        cost = point["cost_usd_per_million_total_tokens"]["planning_h100_rate"][tier]
        dominated = any(
            other is not point
            and other["periodic_sustainability"]["final_wait_seconds"]["max"] <= wait
            and other["cost_usd_per_million_total_tokens"]["planning_h100_rate"][tier] <= cost
            and (
                other["periodic_sustainability"]["final_wait_seconds"]["max"] < wait
                or other["cost_usd_per_million_total_tokens"]["planning_h100_rate"][tier] < cost
            )
            for other in points
        )
        if not dominated:
            selected.append({"wait_cap_seconds": point["wait_cap_seconds"], "max_wait_seconds": wait, "planning_cost_usd_per_million": cost, "steady_overflow_requests": point["periodic_sustainability"]["last_period_overflow_requests"]})
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=PROJECT / "BACKGROUND_OVERFLOW_RESULT.json")
    args = parser.parse_args()
    binding = json.loads(BINDING.read_text())
    if sha256(BINDING) != "c00e011e821e56455c216a265f3093c3089280c31c4ca32eae4f97a617ea5838":
        raise ValueError("director binding hash mismatch")
    verified = verify_inputs(binding)
    rows = load_rows(binding)
    terminal = json.loads(resolve(binding, "settled_discriminator").read_text())
    headroom = json.loads(resolve(binding, "headroom_result").read_text())
    price_inventory = json.loads(resolve(binding, "price_inventory").read_text())
    h100 = next(row for row in price_inventory["accelerators"] if row["id"] == "nvidia-h100-sxm")
    planning_rate = h100["production_planning_usd_per_gpu_hour"]
    service = terminal["service_seconds_per_request"]
    period = rows[-1]["scheduled_s"] - rows[0]["scheduled_s"]
    total_tokens = sum(row["usage"]["total_tokens"] for row in rows)

    control = replay(rows, service, replicas=2)
    prior = headroom["replica_headroom"]["sensitivity"][1]["replay"]
    if control["local_requests"] != prior["completed"] or abs(control["drain_span_seconds"] - prior["drain_span_seconds"]) > 1e-9:
        raise ValueError("two-replica control fails to reproduce HEADROOM_RESULT")
    finite = replay(rows, service)
    periodic = replay(rows, service, periods=PERIODS)
    waits_by_period = []
    for cycle in range(PERIODS):
        slice_start, slice_end = cycle * len(rows), (cycle + 1) * len(rows)
        waits = periodic["all_waits"][slice_start:slice_end]
        waits_by_period.append({"period": cycle + 1, "p95_wait_seconds": percentile(waits, .95), "max_wait_seconds": max(waits)})
    first_crossing = {}
    for level in WAIT_LEVELS_SECONDS:
        match = next((index for index, value in enumerate(periodic["all_waits"]) if value >= level), None)
        first_crossing[str(level)] = None if match is None else {
            "request_number": match,
            "period": match // len(rows) + 1,
            "arrival_seconds": rows[match % len(rows)]["scheduled_s"] + (match // len(rows)) * period,
        }
    economics = binding["frozen_economics_usd_per_million_total_tokens"]
    tiers = {key.removeprefix("retail_"): value for key, value in economics.items() if key.startswith("retail_")}
    frontier = []
    for wait_cap in WAIT_CAPS_SECONDS:
        policy = replay(rows, service, wait_cap=wait_cap)
        periodic_policy = replay(rows, service, wait_cap=wait_cap, periods=PERIODS)
        final_period_overflow = [item for item in periodic_policy["overflow"] if item["cycle"] == PERIODS - 1]
        steady_overflow_tokens = sum(item["tokens"] for item in final_period_overflow)
        row = compact(policy)
        row["periodic_sustainability"] = {
            "periods": PERIODS,
            "last_period_overflow_requests": len(final_period_overflow),
            "last_period_overflow_tokens": steady_overflow_tokens,
            "final_drain_extension_seconds": periodic_policy["queue"]["drain_extension_seconds"],
            "final_wait_seconds": periodic_policy["queue"]["wait_seconds"],
        }
        row["cost_usd_per_million_total_tokens"] = {
            "planning_h100_rate": {name: cost_usd_per_million(planning_rate, period, total_tokens, steady_overflow_tokens, price) for name, price in tiers.items()},
            "actual_h100_rate": {name: cost_usd_per_million(ACTUAL_H100_USD_HOUR, period, total_tokens, steady_overflow_tokens, price) for name, price in tiers.items()},
        }
        frontier.append(row)
    stability_ceiling = period / len(rows)
    result = {
        "schema_version": 1,
        "classification": "analytical_background_buffering_and_retail_overflow_frontier",
        "evidence_type": "deterministic_cpu_discrete_event_simulation_and_derived_economics_not_measured_endpoint",
        "scope_boundary": "No provider, GPU, SSH, endpoint owner, or live H100 was inspected or mutated.",
        "binding_sha256": sha256(BINDING),
        "verified_inputs": verified,
        "assumptions": {
            "local_policy": "FIFO constant-service single H100; retail receives a request only if accepting it would exceed the selected local FIFO wait cap",
            "minimum_overflow_property": "For a fixed FIFO trace and cap, the greedy policy overflows exactly requests that cannot be accepted locally without violating the cap",
            "retail_completion": "Retail completion latency is intentionally not inferred; only its frozen token price is charged",
            "billed_h100_span": "One H100 is billed for one original arrival period per repeated operating cycle; finite drain is reported separately",
            "missing": "No endpoint service-time distribution, retail latency, failure, reload, storage, or orchestration cost is modeled",
        },
        "trace": {"requests": len(rows), "total_tokens": total_tokens, "period_seconds": period, "arrival_rate_requests_per_second": len(rows) / period},
        "service": {"settled_seconds_per_request": service, "one_replica_average_rate_stability_ceiling_seconds_per_request": stability_ceiling, "one_replica_90pct_headroom_ceiling_seconds_per_request": period * .9 / len(rows)},
        "two_replica_control": compact(control),
        "one_replica_finite_trace": compact(finite),
        "one_replica_periodic_trace": {
            "periods": PERIODS,
            "drain_extension_growth_seconds_per_period": (periodic["queue"]["drain_extension_seconds"] - finite["queue"]["drain_extension_seconds"]) / (PERIODS - 1),
            "final": compact(periodic),
            "wait_by_period": waits_by_period,
            "first_wait_level_crossing": first_crossing,
        },
        "retail_overflow_pareto": {"frozen_tiers_usd_per_million": tiers, "points": frontier, "non_dominated_planning_points_by_tier": {tier: non_dominated(frontier, tier) for tier in tiers}},
        "decision": {
            "terminal_classification": "endpoint_dependent_nominate",
            "finite_buffering_is_not_periodic_sustainability": periodic["queue"]["drain_extension_seconds"] > finite["queue"]["drain_extension_seconds"],
            "capability_listed_tier_beaten": any(point["cost_usd_per_million_total_tokens"]["planning_h100_rate"]["capability_listed"] < tiers["capability_listed"] for point in frontier),
            "methodology_matched_tier_beaten": any(point["cost_usd_per_million_total_tokens"]["planning_h100_rate"]["methodology_matched"] < tiers["methodology_matched"] for point in frontier),
            "endpoint_field_most_decisive": "The pending 791-request endpoint's service_seconds_per_request: <= one_replica_average_rate_stability_ceiling removes periodic overload; <= one_replica_90pct_headroom_ceiling restores the earlier strict headroom condition.",
        },
        "actual_spend_usd": 0.0,
        "provider_mutation": "none",
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"out": str(args.out), "finite_max_wait": finite["queue"]["wait_seconds"]["max"], "periodic_drain_extension": periodic["queue"]["drain_extension_seconds"], "frontier_points": len(frontier)}, sort_keys=True))


if __name__ == "__main__":
    main()
