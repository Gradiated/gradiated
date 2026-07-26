#!/usr/bin/env python3
"""Deterministic, zero-spend screen for latency-relaxed c32 admission.

This deliberately holds the qualified service evidence constant.  It models a
batch as consuming the measured c32 service time even when a deadline causes a
partial batch; this makes partial-fill economics optimistic only with respect
to work (not time), and never claims a smaller-M speed.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

P = Path(__file__).resolve().parent
BOUND = P.parent / "gemma4_h200_ngram_persistent_grouped_lm_head" / "inputs/bound/QUALIFIED_LATEST_TERMINAL.json"
SERVICE = 0.625149101968745
BATCH = 32
BATCH_SECONDS = SERVICE * BATCH
TOKENS_PER_REQUEST = 4214 + 358
BASE_UTILIZATION = 0.90
BASE_USD_PER_M_TOKEN = 0.109725
TARGET_USD_PER_M_TOKEN = BASE_USD_PER_M_TOKEN * 0.80
SEED = 20260726
# 2,000 requests × 12 policy/arrival arms is enough to stabilize the
# discriminator's direction while keeping the bounded local run short.
N = 2000


def q(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    i = (len(xs) - 1) * p
    lo, hi = int(i), math.ceil(i)
    return xs[lo] if lo == hi else xs[lo] * (hi - i) + xs[hi] * (i - lo)


def arrivals(kind: str, rate: float, n: int = N) -> list[float]:
    rng = random.Random(SEED + (0 if kind == "poisson" else 1))
    out, now = [], 0.0
    # A two-state MMPP is an explicitly synthetic burst sensitivity: mean rate
    # remains rate, with 4x bursts lasting 20% of wall time.
    state_until = 0.0
    burst = False
    for _ in range(n):
        if kind == "poisson":
            local = rate
        else:
            if now >= state_until:
                burst = not burst
                state_until = now + (20.0 if burst else 80.0)
            local = rate * (4.0 if burst else 0.25)
        now += rng.expovariate(local)
        out.append(now)
    return out


def screen(arrival_times: list[float], deadline: float | None, replicas: int, one_loss: bool) -> dict:
    """Central-pool, earliest-free-replica event simulation of c32 waves."""
    queue: list[float] = []
    available = [0.0] * replicas
    completions: list[float] = []
    waits: list[float] = []
    partial = 0
    dispatched = 0
    loss_start = arrival_times[len(arrival_times) // 2]
    loss_end = loss_start + 60.0
    i = 0
    while i < len(arrival_times) or queue:
        r = min(range(replicas), key=lambda x: (available[x], x))
        free = available[r]
        while i < len(arrival_times) and arrival_times[i] <= free:
            queue.append(arrival_times[i]); i += 1
        if not queue:
            queue.append(arrival_times[i]); i += 1
            free = max(free, queue[0])
        needed = BATCH - len(queue)
        full_at = arrival_times[i + needed - 1] if needed > 0 and i + needed - 1 < len(arrival_times) else math.inf
        due_at = math.inf if deadline is None else queue[0] + deadline
        # With an unbounded gate, only the terminal incomplete wave may run
        # partial.  It drains after the prior wave rather than waiting for an
        # impossible 32nd arrival.
        start = max(free, queue[0] if full_at == math.inf and deadline is None else min(full_at, due_at))
        if one_loss and r == 0 and free < loss_end and start >= loss_start:
            available[r] = loss_end
            continue
        while i < len(arrival_times) and arrival_times[i] <= start:
            queue.append(arrival_times[i]); i += 1
        take = min(BATCH, len(queue))
        wave = queue[:take]
        del queue[:take]
        done = start + BATCH_SECONDS
        available[r] = done
        dispatched += 1
        partial += take < BATCH
        for arrival in wave:
            waits.append(start - arrival)
            completions.append(done - arrival)
    span = max(arrival_times[-1] - arrival_times[0], 1e-9)
    end = max(available)
    achieved = len(completions) / max(end - arrival_times[0], 1e-9)
    # Fixed hardware price is reconstructed from the locked 90%-utilization
    # planning mapping; factors expose all-in headroom rather than hide it.
    billing_util = min(1.0, achieved * SERVICE / replicas)
    gpu_cost = BASE_USD_PER_M_TOKEN * BASE_UTILIZATION / max(billing_util, 1e-12)
    all_in_factor = 1.05 * 1.03 * 1.03  # orchestration, reliability, reserve
    all_in = gpu_cost * all_in_factor
    p95_wait = q(waits, .95)
    return {
        "requests": len(completions), "replicas": replicas, "deadline_seconds": deadline,
        "one_replica_loss": one_loss, "reload_reserve_seconds": 60 if one_loss else 0,
        "headroom": {"active_replicas": replicas - (1 if one_loss else 0),
                     "loss_reserve_replicas": 1 if one_loss else 0},
        "achieved_rps": achieved, "achieved_utilization_per_replica": billing_util,
        "queue_seconds": {"p50": q(waits, .5), "p95": p95_wait, "p99": q(waits, .99),
                          "p95_budget_met": deadline is None or p95_wait <= deadline},
        "completion_seconds": {"p50": q(completions, .5), "p95": q(completions, .95), "p99": q(completions, .99)},
        "dropped_or_timed_out": 0, "waves": dispatched, "partial_waves": partial,
        "economics_usd_per_m_tokens": {
            "fresh_input": None, "cache_read": None, "output": None,
            "blended_gpu_only": gpu_cost, "blended_all_in": all_in,
            "all_in_factor": all_in_factor,
            "phase_allocation_boundary": "The qualified terminal supplies only whole-request service, so phase-specific fresh-input/cache-read/output dollar allocations are not identifiable and are intentionally null rather than invented.",
        },
    }


def main() -> None:
    bound = json.loads(BOUND.read_text())
    assert abs(bound["candidate_c32_service_seconds_per_request"] - SERVICE) < 1e-15
    rate = BASE_UTILIZATION / SERVICE
    scenarios = []
    for kind in ("poisson", "bursty_mmpp_synthetic"):
        trace = arrivals(kind, rate)
        scenarios.append({"name": f"fixed_c32_90pct_{kind}", "arrival_model": kind,
                          "policy": {"type": "wait_to_fill", "max_queue_delay_seconds": None},
                          "result": screen(trace, None, 1, False)})
        for budget in (5, 15, 30, 60):
            scenarios.append({"name": f"deadline_{budget}s_{kind}", "arrival_model": kind,
                              "policy": {"type": "admission_controlled_c32", "max_queue_delay_seconds": budget,
                                         "route": "least_queued_replica", "partial_batch_charged_at_c32_service": True},
                              "result": screen(trace, budget, 1, False)})
        # A pool needs two active replicas plus one loss reserve to keep c32
        # service available through a loss; both cost and offered load are explicit.
        scenarios.append({"name": f"pooled_2plus1reserve_30s_{kind}", "arrival_model": kind,
                          "policy": {"type": "pooled_admission_c32", "max_queue_delay_seconds": 30,
                                     "route": "least_queued_replica", "active_replicas": 2,
                                     "one_replica_loss": "60s reload; reserve capacity is priced"},
                          "result": screen(trace, 30, 3, True)})
    ideal_floor = BASE_USD_PER_M_TOKEN * BASE_UTILIZATION
    result = {
        "schema_version": 1,
        "classification": "typed_none",
        "typed_reason": "utilization_and_reliability_cannot_close_locked_20pct_cost_gap_without_service_time_gain",
        "question": "Can c32 admission control and pooling close the locked all-in cost target without faster service?",
        "evidence": {"qualified_service": "measured", "arrival_and_failure_models": "synthetic_bounded", "economics": "derived"},
        "source_manifest": {str(BOUND): hashlib.sha256(BOUND.read_bytes()).hexdigest()},
        "locked_inputs": {"service_seconds_per_request": SERVICE, "c32_batch_seconds": BATCH_SECONDS,
                          "planning_utilization": BASE_UTILIZATION, "baseline_usd_per_m_tokens": BASE_USD_PER_M_TOKEN,
                          "target_usd_per_m_tokens": TARGET_USD_PER_M_TOKEN, "tokens_per_request": TOKENS_PER_REQUEST},
        "executable_policy_contract": {"policy": "admission_controlled_c32", "route": "least_queued_healthy_replica",
            "max_queue_delay_grid_seconds": [5, 15, 30, 60], "batch": 32,
            "failure_action": "remove unhealthy replica; retain 60-second reload reserve; do not claim service acceleration"},
        "scenarios": scenarios,
        "hard_bound": {"best_possible_gpu_only_usd_per_m_tokens_at_100pct_utilization": ideal_floor,
                       "target_usd_per_m_tokens": TARGET_USD_PER_M_TOKEN,
                       "best_possible_reduction_fraction": 1 - ideal_floor / BASE_USD_PER_M_TOKEN,
                       "required_utilization_at_unchanged_service": BASE_UTILIZATION / .80,
                       "required_service_seconds_per_request_at_100pct_utilization": SERVICE * .80,
                       "residual_physical_service_speedup_fraction": .20,
                       "interpretation": "112.5% utilization is impossible; all-in factors and loss reserve only increase cost."},
        "decision": {"best_attainable_cost_is_gpu_only_ideal_floor_not_a_deployable_policy": True,
                     "candidate": None, "provider_spend_usd": 0.0, "provider_contact": False,
                     "next_move": "Do not promote scheduling alone. A future candidate needs at least 20% measured service-time reduction before all-in overhead."},
    }
    (P / "LATENCY_RELAXED_POOLING_SCREEN.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["hard_bound"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
