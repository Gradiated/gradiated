#!/usr/bin/env python3
"""Finite-stream MI355X phase-aligned microcohort discriminator."""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import run_rolling_batching_screen as physical
from phase_aligned_microcohort_policy import (
    COHORT_SIZE,
    MAX_LIVE_SEQUENCES,
    PREFILL_TOKEN_BUDGET,
    Microcohort,
    PhaseAlignedMicrocohortPolicy,
)


PROJECT_DIR = Path(__file__).resolve().parent
BINDINGS_PATH = PROJECT_DIR / "MICROCOHORT_SOURCE_BINDINGS.json"
DEFAULT_OUTPUT = PROJECT_DIR / "MI355X_MICROCOHORT_BATCHING_SCREEN.json"
ROLLING_SCREEN = PROJECT_DIR / "MI355X_ROLLING_BATCHING_SCREEN.json"
POLICY_PATH = PROJECT_DIR / "phase_aligned_microcohort_policy.py"

FINITE_REQUESTS = 10_008  # 625 full cohorts plus one exact 8-request fallback.
CAPACITY_PROBE_REQUESTS = 6_000
CAPACITY_PROBE_START_COMPLETION = 1_000
CAPACITY_PROBE_END_COMPLETION = 5_000
OFFERED_CAPACITY_FRACTION = 0.90
GENERATED_AT_UTC = "2026-07-26T14:46:26Z"


def _insert_slot(
    slots: list[physical.Request | None], request: physical.Request
) -> None:
    try:
        index = slots.index(None)
    except ValueError:
        slots.append(request)
    else:
        slots[index] = request


def _cohort_alignment(cohort: Microcohort) -> bool:
    prefill = {request.is_prefill for request in cohort.requests}
    outputs = {request.output_tokens for request in cohort.requests}
    return len(prefill) == 1 and len(outputs) == 1


def simulate(requests: list[physical.Request]) -> dict[str, Any]:
    policy = PhaseAlignedMicrocohortPolicy()
    slots: list[physical.Request | None] = []
    waiting: list[physical.Request] = []
    cohorts: list[Microcohort] = []
    next_arrival = 0
    now = 0.0
    completed_count = 0
    completion_milestones: dict[int, float] = {}
    accounting = physical.empty_accounting()
    accounting.update(
        {
            "fill_barrier_request_seconds": 0.0,
            "full_cohorts_admitted": 0.0,
            "partial_fallback_cohorts_admitted": 0.0,
        }
    )
    main_scheduled_width_histogram: dict[int, int] = {}
    main_token_m_histogram: dict[int, int] = {}
    peak_live = 0
    peak_observed_resident_bytes = physical.STATIC_MODEL_BYTES
    peak_target_due = 0
    first_full_width_seconds: float | None = None
    last_arrival = requests[-1].arrival_seconds
    alignment_checks = 0
    target_due_widths: list[int] = []

    while completed_count < len(requests):
        while (
            next_arrival < len(requests)
            and requests[next_arrival].arrival_seconds <= now + 1e-12
        ):
            waiting.append(requests[next_arrival])
            next_arrival += 1

        arrival_stream_closed = next_arrival == len(requests)
        scheduled_rows, admitted = policy.schedule(
            waiting,
            cohorts,
            arrival_stream_closed=arrival_stream_closed,
        )

        if not scheduled_rows:
            if cohorts:
                raise RuntimeError("live cohorts produced no schedulable rows")
            if next_arrival < len(requests):
                # A full cohort is the atomic admission unit.  Jump to its
                # 16th arrival (or the stream's terminal partial cohort).
                needed = min(
                    COHORT_SIZE - len(waiting),
                    len(requests) - next_arrival,
                )
                target_index = next_arrival + needed - 1
                next_time = requests[target_index].arrival_seconds
                idle = max(0.0, next_time - now)
                accounting["idle_seconds"] += idle
                now = max(now, next_time)
                continue
            raise RuntimeError("unfinished requests but no schedulable work")

        admitted_requests: list[physical.Request] = []
        for cohort in admitted:
            if cohort.terminal_partial_fallback:
                accounting["partial_fallback_cohorts_admitted"] += 1
                accounting["fallback_requests"] += cohort.size
            else:
                accounting["full_cohorts_admitted"] += 1
            for request in cohort.requests:
                if request.first_scheduled_seconds is not None:
                    raise RuntimeError("request admitted twice")
                admitted_requests.append(request)
                _insert_slot(slots, request)

        moves, moved_bytes = physical.compact_slots(slots)
        if moves:
            seconds = (
                moves * physical.COMPACTION_FIXED_SECONDS_PER_MOVE
                + moved_bytes / physical.COMPACTION_HOST_BYTES_PER_SECOND
            )
            accounting["compaction_moves"] += moves
            accounting["compaction_bytes"] += moved_bytes
            accounting["compaction_seconds"] += seconds
            now += seconds

        for request in admitted_requests:
            request.first_scheduled_seconds = now
            accounting["fill_barrier_request_seconds"] += (
                now - request.arrival_seconds
            )

        active = sum(request is not None for request in slots)
        scheduled_width = len(scheduled_rows)
        token_m = sum(row.tokens for row in scheduled_rows)
        if active > MAX_LIVE_SEQUENCES:
            raise RuntimeError("live sequence cap exceeded")
        peak_live = max(peak_live, active)
        if active == MAX_LIVE_SEQUENCES and first_full_width_seconds is None:
            first_full_width_seconds = now
        main_scheduled_width_histogram[scheduled_width] = (
            main_scheduled_width_histogram.get(scheduled_width, 0) + 1
        )
        main_token_m_histogram[token_m] = main_token_m_histogram.get(token_m, 0) + 1
        resident = physical.STATIC_MODEL_BYTES + sum(
            physical.kv_resident_bytes(request)
            for request in slots
            if request is not None
        )
        peak_observed_resident_bytes = max(peak_observed_resident_bytes, resident)

        scheduled = [
            (row.request, row.kind, row.tokens) for row in scheduled_rows
        ]
        main_seconds, main_accounting = physical.main_forward_cost(scheduled)
        physical.add_accounting(accounting, main_accounting)
        now += main_seconds

        due: list[physical.Request] = []
        touched_cohort_ids = {row.cohort_id for row in scheduled_rows}
        for row in scheduled_rows:
            request = row.request
            if row.kind == "prefill":
                request.fresh_computed += row.tokens
                if not request.is_prefill:
                    request.output_tokens = 1
            else:
                request.output_tokens += 1
            if request.output_tokens in physical.TARGET_OUTPUT_COUNTS:
                due.append(request)

        for cohort in cohorts:
            if cohort.cohort_id in touched_cohort_ids:
                alignment_checks += 1
                if not _cohort_alignment(cohort):
                    raise RuntimeError("microcohort phase alignment lost")

        if due:
            target_due_widths.append(len(due))
            target_seconds, target_accounting = physical.target_forward_cost(
                len(due)
            )
            physical.add_accounting(accounting, target_accounting)
            now += target_seconds
            peak_target_due = max(peak_target_due, len(due))

        finished_cohorts = [
            cohort
            for cohort in cohorts
            if cohort.output_tokens == physical.OUTPUT_TOKENS
        ]
        if finished_cohorts:
            finished = [
                request
                for cohort in finished_cohorts
                for request in cohort.requests
            ]
            service_seconds = physical.SERVICE_SECONDS_PER_REQUEST * len(finished)
            accounting["service_seconds"] += service_seconds
            now += service_seconds
            finished_ids = {request.request_id for request in finished}
            for index, request in enumerate(slots):
                if request is not None and request.request_id in finished_ids:
                    slots[index] = None
            finished_cohort_ids = {
                cohort.cohort_id for cohort in finished_cohorts
            }
            cohorts = [
                cohort
                for cohort in cohorts
                if cohort.cohort_id not in finished_cohort_ids
            ]
            for request in finished:
                request.completed_seconds = now
                completed_count += 1
                if completed_count in {
                    CAPACITY_PROBE_START_COMPLETION,
                    CAPACITY_PROBE_END_COMPLETION,
                }:
                    completion_milestones[completed_count] = now

    queue = [
        request.first_scheduled_seconds - request.arrival_seconds
        for request in requests
        if request.first_scheduled_seconds is not None
    ]
    completion = [
        request.completed_seconds - request.arrival_seconds
        for request in requests
        if request.completed_seconds is not None
    ]
    if len(queue) != len(requests) or len(completion) != len(requests):
        raise RuntimeError("request accounting incomplete")
    return {
        "accounting": accounting,
        "alignment_checks": alignment_checks,
        "all_requests_completed": completed_count == len(requests),
        "completion_milestones": completion_milestones,
        "completion_p50_seconds": physical.percentile(completion, 0.50),
        "completion_p95_seconds": physical.percentile(completion, 0.95),
        "completion_seconds_max": max(completion),
        "final_completion_seconds": now,
        "first_full_width_seconds": first_full_width_seconds,
        "last_arrival_seconds": last_arrival,
        "main_scheduled_width_histogram": {
            str(key): value
            for key, value in sorted(main_scheduled_width_histogram.items())
        },
        "main_token_m_histogram": {
            str(key): value for key, value in sorted(main_token_m_histogram.items())
        },
        "peak_live_requests": peak_live,
        "peak_observed_resident_bytes": peak_observed_resident_bytes,
        "peak_target_due_requests": peak_target_due,
        "queue_p50_seconds": physical.percentile(queue, 0.50),
        "queue_p95_seconds": physical.percentile(queue, 0.95),
        "queue_seconds_max": max(queue),
        "requests": len(requests),
        "starved_requests": sum(not math.isfinite(value) for value in completion),
        "target_due_width_histogram": {
            str(width): target_due_widths.count(width)
            for width in sorted(set(target_due_widths))
        },
    }


def capacity_probe() -> tuple[float, dict[str, Any]]:
    probe = simulate(physical.make_requests(CAPACITY_PROBE_REQUESTS, 0.0))
    milestones = probe["completion_milestones"]
    elapsed = (
        milestones[CAPACITY_PROBE_END_COMPLETION]
        - milestones[CAPACITY_PROBE_START_COMPLETION]
    )
    capacity = (
        CAPACITY_PROBE_END_COMPLETION - CAPACITY_PROBE_START_COMPLETION
    ) / elapsed
    return capacity, probe


def validate_inputs(bindings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    bound_paths = {
        "accelerator_inventory": Path(bindings["accelerator_inventory"]["path"]),
        "gpu_prices": Path(bindings["gpu_prices"]["path"]),
        "parent_screen": physical.PARENT_SCREEN,
        "preserved_barrier_terminal": physical.BARRIER_SCREEN,
        "preserved_rolling_terminal": ROLLING_SCREEN,
        "preserved_rolling_runner": PROJECT_DIR
        / "run_rolling_batching_screen.py",
        "preserved_rolling_bindings": PROJECT_DIR / "ROLLING_SOURCE_BINDINGS.json",
        "microcohort_policy": POLICY_PATH,
    }
    checks: dict[str, dict[str, Any]] = {}
    for name, path in bound_paths.items():
        expected = bindings[name]["sha256"]
        observed = physical.sha256(path) if path.is_file() else None
        checks[name] = {
            "expected_sha256": expected,
            "observed_sha256": observed,
            "pass": observed == expected,
        }
        if observed != expected:
            raise RuntimeError(f"{name} hash mismatch")
    return checks


def build_artifact(
    bindings: dict[str, Any],
    source_checks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    input_checks = validate_inputs(bindings)
    capacity, probe = capacity_probe()
    offered_rate = capacity * OFFERED_CAPACITY_FRACTION
    finite = simulate(
        physical.make_requests(FINITE_REQUESTS, 1.0 / offered_rate)
    )
    accounting = finite["accounting"]
    memory = physical.configured_memory_screen()
    total_seconds_per_request = finite["final_completion_seconds"] / FINITE_REQUESTS
    queue_pass = finite["queue_p95_seconds"] <= physical.QUEUE_P95_GATE_SECONDS
    completion_pass = (
        finite["completion_p95_seconds"]
        <= physical.COMPLETION_P95_GATE_SECONDS
    )
    economic_pass = (
        total_seconds_per_request <= physical.TARGET_SECONDS_PER_REQUEST
    )
    load_pass = offered_rate <= capacity * 0.90 + 1e-12
    expected_fresh = sum(
        request.fresh_prompt_tokens
        for request in physical.make_requests(FINITE_REQUESTS, 0.0)
    )
    semantic_pass = (
        int(accounting["prefill_tokens"]) == expected_fresh
        and int(accounting["decode_rows"] + accounting["prefill_head_rows"])
        == FINITE_REQUESTS * physical.OUTPUT_TOKENS
        and int(accounting["target_cycles"])
        == FINITE_REQUESTS * physical.TARGET_CYCLES
        and finite["all_requests_completed"]
        and int(accounting["fallback_requests"]) == FINITE_REQUESTS % COHORT_SIZE
    )
    source_pass = all(row["pass"] for row in source_checks.values())
    passes = (
        economic_pass
        and queue_pass
        and completion_pass
        and memory["fits"]
        and load_pass
        and semantic_pass
        and source_pass
        and finite["starved_requests"] == 0
    )
    classification = (
        "source_complete_microcohort_batching_candidate"
        if passes
        else "typed_none"
    )

    bootstrap_boundary = (FINITE_REQUESTS // 20) / offered_rate
    drain_seconds = finite["final_completion_seconds"] - finite["last_arrival_seconds"]
    steady_seconds = finite["last_arrival_seconds"] - bootstrap_boundary
    scheduled_events = {
        int(width): count
        for width, count in finite["main_scheduled_width_histogram"].items()
    }
    mean_scheduled_width = sum(
        width * count for width, count in scheduled_events.items()
    ) / sum(scheduled_events.values())
    target_events = int(accounting["target_forward_events"])
    full_cohorts = FINITE_REQUESTS // COHORT_SIZE

    return {
        "charged_cost_categories": {
            "actual_width_prompt": True,
            "actual_width_decode": True,
            "actual_width_target": True,
            "attention": True,
            "bootstrap": True,
            "compaction": True,
            "compute": True,
            "drain": True,
            "fill_and_barrier": True,
            "idle": True,
            "kv_read_write_and_capacity": True,
            "launch": True,
            "memory": True,
            "partial_final_fallback": True,
            "queue": True,
            "scheduler_and_service": True,
            "tied_head": True,
            "weights_fp8_and_bf16": True,
        },
        "classification": classification,
        "decision": {
            "completion_p95_gate_pass": completion_pass,
            "economic_gate_pass": economic_pass,
            "load_at_most_90_percent_capacity_pass": load_pass,
            "memory_gate_pass": memory["fits"],
            "queue_p95_gate_pass": queue_pass,
            "result": classification,
            "semantic_accounting_pass": semantic_pass,
            "source_binding_pass": source_pass,
            "starvation_gate_pass": finite["starved_requests"] == 0,
        },
        "finite_stream": {
            "arrival_interval_seconds": 1.0 / offered_rate,
            "bootstrap_boundary_seconds_first_5_percent_arrived": bootstrap_boundary,
            "capacity_requests_per_second": capacity,
            "capacity_seconds_per_request": 1.0 / capacity,
            "completion_p50_seconds": finite["completion_p50_seconds"],
            "completion_p95_seconds": finite["completion_p95_seconds"],
            "completion_seconds_max": finite["completion_seconds_max"],
            "drain_seconds_after_last_arrival": drain_seconds,
            "fallback_request_fraction": accounting["fallback_requests"]
            / FINITE_REQUESTS,
            "final_completion_seconds": finite["final_completion_seconds"],
            "first_full_width_seconds": finite["first_full_width_seconds"],
            "load_fraction_of_capacity": offered_rate / capacity,
            "mean_main_event_scheduled_width": mean_scheduled_width,
            "offered_requests_per_second": offered_rate,
            "peak_live_requests": finite["peak_live_requests"],
            "queue_p50_seconds": finite["queue_p50_seconds"],
            "queue_p95_seconds": finite["queue_p95_seconds"],
            "queue_seconds_max": finite["queue_seconds_max"],
            "requests": FINITE_REQUESTS,
            "phase_wall_seconds": {
                "bootstrap_first_5_percent_arrival_window": bootstrap_boundary,
                "drain_after_last_arrival": drain_seconds,
                "steady_arrival_window": steady_seconds,
                "sum_charged_in_all_request_mean": bootstrap_boundary
                + steady_seconds
                + drain_seconds,
            },
            "starved_requests": finite["starved_requests"],
            "total_seconds_per_request_including_bootstrap_and_drain": (
                total_seconds_per_request
            ),
        },
        "generated_from_observation_utc": GENERATED_AT_UTC,
        "identity": {
            "bindings": {
                "path": str(BINDINGS_PATH),
                "sha256": physical.sha256(BINDINGS_PATH),
            },
            "calculator": {
                "path": str(Path(__file__).resolve()),
                "sha256": physical.sha256(Path(__file__).resolve()),
            },
            "campaign": {
                "path": str(physical.LAB_DIR / "CAMPAIGN.md"),
                "sha256": physical.sha256(physical.LAB_DIR / "CAMPAIGN.md"),
            },
            "input_checks": input_checks,
            "microcohort_policy": {
                "path": str(POLICY_PATH),
                "sha256": physical.sha256(POLICY_PATH),
            },
            "parent_screen": {
                "path": str(physical.PARENT_SCREEN),
                "sha256": physical.sha256(physical.PARENT_SCREEN),
            },
            "preserved_barrier_terminal": {
                "path": str(physical.BARRIER_SCREEN),
                "sha256": physical.sha256(physical.BARRIER_SCREEN),
            },
            "preserved_rolling_terminal": {
                "path": str(ROLLING_SCREEN),
                "sha256": physical.sha256(ROLLING_SCREEN),
            },
            "project": {
                "path": str(PROJECT_DIR / "PROJECT.md"),
                "sha256": physical.sha256(PROJECT_DIR / "PROJECT.md"),
            },
            "source_checks": source_checks,
        },
        "memory": {
            **memory,
            "observed_peak_live_requests": finite["peak_live_requests"],
            "observed_peak_resident_bytes_before_two_x_envelope": finite[
                "peak_observed_resident_bytes"
            ],
            "observed_peak_target_due_requests": finite[
                "peak_target_due_requests"
            ],
        },
        "physical_accounting": {
            **accounting,
            "bf16_math_efficiency": 0.20,
            "compaction_host_bandwidth_bytes_per_second": (
                physical.COMPACTION_HOST_BYTES_PER_SECOND
            ),
            "compaction_seconds_per_moved_row": (
                physical.COMPACTION_FIXED_SECONDS_PER_MOVE
            ),
            "enforce_eager": True,
            "fp8_math_efficiency": 0.20,
            "hbm_efficiency": 0.30,
            "internal_tile_underfill_rule": "No extra utilization credit; the settled 20% tensor and 30% HBM efficiencies remain fixed for every actual M.",
            "main_scheduled_width_histogram": finite[
                "main_scheduled_width_histogram"
            ],
            "main_token_m_histogram": finite["main_token_m_histogram"],
            "scheduler_service_seconds_per_request": (
                physical.SERVICE_SECONDS_PER_REQUEST
            ),
            "seconds_per_request_by_critical_path_family": {
                "attention": accounting["attention_seconds"] / FINITE_REQUESTS,
                "compaction": accounting["compaction_seconds"] / FINITE_REQUESTS,
                "head": accounting["head_seconds"] / FINITE_REQUESTS,
                "idle": accounting["idle_seconds"] / FINITE_REQUESTS,
                "launch": accounting["launch_seconds"] / FINITE_REQUESTS,
                "non_gemm_and_kv_write": accounting["non_gemm_seconds"]
                / FINITE_REQUESTS,
                "scheduler_and_service": accounting["service_seconds"]
                / FINITE_REQUESTS,
                "transformer": accounting["transformer_seconds"]
                / FINITE_REQUESTS,
            },
            "target_due_width_histogram": finite[
                "target_due_width_histogram"
            ],
        },
        "physical_interpretation": {
            "capacity_required_to_meet_target_at_90_percent_load_requests_per_second": (
                1.0
                / (
                    OFFERED_CAPACITY_FRACTION
                    * physical.TARGET_SECONDS_PER_REQUEST
                )
            ),
            "capacity_shortfall_fraction": (
                1.0
                - capacity
                * OFFERED_CAPACITY_FRACTION
                * physical.TARGET_SECONDS_PER_REQUEST
            ),
            "observed_mechanism": (
                "Immutable 16-request phases collapse request-relative target "
                "cycles into cohort-width forwards and retain independent "
                "rolling admission, trading one-cohort fill delay for fewer "
                "transformer/head weight streams and launches."
            ),
            "target_cycles_per_target_forward": accounting["target_cycles"]
            / target_events,
            "target_forward_events": target_events,
            "target_head_weight_streams": target_events * physical.TARGET_DEPTH,
            "what_would_falsify_this_explanation": (
                "A target MI355X trace of this exact 16/96/8192/eager policy "
                "showing different completed-request capacity or target "
                "grouping with identical prompt, output, cache, target, and "
                "fallback accounting."
            ),
        },
        "policy": {
            "admission": (
                "FCFS immutable groups of exactly 16; admit independently "
                "when all members are present, capacity and an initial token "
                "map are available. Never wait for all 96."
            ),
            "cache_mix": (
                "Deterministic 1,000-request period: 822 requests cache 535 "
                "tokens and 178 cache 536, preserving the parent mean."
            ),
            "cohort_size": COHORT_SIZE,
            "compaction": (
                "Remove completed cohort rows, fill smallest freed indices, "
                "then apply the bound GPUInputBatch.condense move rule."
            ),
            "fallback": (
                f"The terminal {FINITE_REQUESTS % COHORT_SIZE}-request partial "
                "cohort executes the identical eager exact-row policy after "
                "the arrival stream closes; every token and cost is charged."
            ),
            "full_cohorts": full_cohorts,
            "graph_mode": (
                "enforce_eager; exact prompt/decode/target rows execute "
                "without graph padding, with every launch charged."
            ),
            "max_live_sequences": MAX_LIVE_SEQUENCES,
            "prefill_decode_interleave": (
                "Schedule existing cohorts FCFS before new cohorts. Non-final "
                "prefill chunks advance every member equally; the final "
                "535/536-cache-mixed chunk completes all members together."
            ),
            "prefill_token_budget": PREFILL_TOKEN_BUDGET,
            "sampling_and_ownership": (
                "Membership is immutable while token IDs, positions, KV "
                "block rows, sampling state, completion, and slot reuse remain "
                "per request."
            ),
            "selected_policy_count": 1,
            "target_verification_cadence": (
                "All members execute each of 15 depth-12 cycles together "
                "after output counts ceil(k*358/15); independently aligned "
                "cohorts batch only when due in the same scheduler event."
            ),
        },
        "probe": {
            "end_completion": CAPACITY_PROBE_END_COMPLETION,
            "end_seconds": probe["completion_milestones"][
                CAPACITY_PROBE_END_COMPLETION
            ],
            "peak_live_requests": probe["peak_live_requests"],
            "requests": CAPACITY_PROBE_REQUESTS,
            "saturated_capacity_requests_per_second": capacity,
            "saturated_seconds_per_request": 1.0 / capacity,
            "start_completion": CAPACITY_PROBE_START_COMPLETION,
            "start_seconds": probe["completion_milestones"][
                CAPACITY_PROBE_START_COMPLETION
            ],
        },
        "scope": {
            "accelerator": "one AMD Instinct MI355X, TP1",
            "mode": "text_only_non_reasoning",
            "model": physical.MODEL_ID,
            "provider_spend_usd": 0.0,
            "revision": physical.MODEL_REVISION,
            "tokens_per_request": physical.TOTAL_TOKENS,
        },
        "semantic_accounting": {
            "all_60_layers_preserved": True,
            "all_checkpoint_parameters_preserved": True,
            "all_requests_completed": finite["all_requests_completed"],
            "cache_mix_preserved": True,
            "decode_and_first_sample_rows_expected": FINITE_REQUESTS
            * physical.OUTPUT_TOKENS,
            "decode_and_first_sample_rows_observed": int(
                accounting["decode_rows"] + accounting["prefill_head_rows"]
            ),
            "exact_attention_and_kv_ownership": True,
            "feature_and_sampling_semantics_preserved": True,
            "fresh_prompt_tokens_expected": expected_fresh,
            "fresh_prompt_tokens_observed": int(accounting["prefill_tokens"]),
            "microcohort_alignment_checks": finite["alignment_checks"],
            "partial_fallback_requests_expected": FINITE_REQUESTS % COHORT_SIZE,
            "partial_fallback_requests_observed": int(
                accounting["fallback_requests"]
            ),
            "target_cycles_expected": FINITE_REQUESTS * physical.TARGET_CYCLES,
            "target_cycles_observed": int(accounting["target_cycles"]),
        },
        "terminal": classification,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--vllm-root", type=Path)
    args = parser.parse_args()
    bindings = physical.load_json(BINDINGS_PATH)
    if args.vllm_root is not None:
        source_checks = physical.verify_sources(bindings, args.vllm_root)
        artifact = build_artifact(bindings, source_checks)
    else:
        with tempfile.TemporaryDirectory(prefix="mi355x-microcohort-vllm-") as temp:
            root = Path(temp)
            physical.fetch_vllm(root, bindings)
            source_checks = physical.verify_sources(bindings, root)
            artifact = build_artifact(bindings, source_checks)
    physical.atomic_json(args.output, artifact)
    print(
        json.dumps(
            {
                "capacity_requests_per_second": artifact["finite_stream"][
                    "capacity_requests_per_second"
                ],
                "classification": artifact["classification"],
                "completion_p95_seconds": artifact["finite_stream"][
                    "completion_p95_seconds"
                ],
                "offered_requests_per_second": artifact["finite_stream"][
                    "offered_requests_per_second"
                ],
                "output": str(args.output),
                "queue_p95_seconds": artifact["finite_stream"][
                    "queue_p95_seconds"
                ],
                "seconds_per_request": artifact["finite_stream"][
                    "total_seconds_per_request_including_bootstrap_and_drain"
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
