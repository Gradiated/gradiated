#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


TARGET = 0.514
TOKENS_PER_BATCH = 65536
BATCH_SECONDS = 89.21845636400008
TOKENS_PER_SECOND = 734.5565331529764
RATES = (1.0, 1.1, 1.25)
RETRY_RATES = (0.0, 0.02, 0.05, 0.10)
UTILIZATIONS = (0.75, 0.80, 0.85, 0.90, 0.95, 1.0)
SESSION_HOURS = (2.0, 8.0, 24.0)

PHASES = (
    ("provider_create", 54.237, "measured"),
    ("ssh_readiness", 44.73, "measured"),
    ("orchestration_between_ssh_and_bootstrap", 2.864416, "measured_interval"),
    ("runtime_bootstrap", 403.513, "measured"),
    ("tiny_checkpoint_probe", 7.45237, "measured_interval"),
    ("checkpoint_transfer", 291.339, "measured"),
    ("repair_input_staging", 7.432157, "measured_interval"),
    ("model_load_compile_warmup", 338.444066272, "derived"),
    ("artifact_retrieval", 2.001646, "measured_interval"),
    ("cleanup", 56.154218, "measured_interval"),
)


def steady_cost(rate):
    return rate * 1_000_000 / (3600 * TOKENS_PER_SECOND)


def all_in_cost(rate, session_seconds, utilization, retry_rate, overhead_seconds):
    productive_seconds = (session_seconds - overhead_seconds) * utilization
    if productive_seconds <= 0:
        return None
    return steady_cost(rate) * session_seconds / (productive_seconds * (1 - retry_rate))


def minimum_utilization(rate, session_seconds, retry_rate, overhead_seconds):
    service_fraction = 1 - overhead_seconds / session_seconds
    if service_fraction <= 0:
        return None
    return steady_cost(rate) / (TARGET * service_fraction * (1 - retry_rate))


def minimum_batches(rate, retry_rate, overhead_seconds):
    denominator = TARGET * (1 - retry_rate) - steady_cost(rate)
    if denominator <= 0:
        return None
    raw = steady_cost(rate) * overhead_seconds / (BATCH_SECONDS * denominator)
    return {"continuous": raw, "whole_batches": int(raw) + (raw % 1 > 0)}


def lifecycle_fraction_frontier(rate, lifecycle_fraction, retry_rate):
    return steady_cost(rate) / (TARGET * (1 - lifecycle_fraction) * (1 - retry_rate))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    overhead_seconds = sum(seconds for _, seconds, _ in PHASES)
    phase_map = [
        {"name": name, "seconds": seconds, "evidence_type": evidence}
        for name, seconds, evidence in PHASES
    ]
    session_grid = []
    for hours in SESSION_HOURS:
        seconds = hours * 3600
        for rate in RATES:
            for utilization in UTILIZATIONS:
                for retry_rate in RETRY_RATES:
                    cost = all_in_cost(rate, seconds, utilization, retry_rate, overhead_seconds)
                    session_grid.append({
                        "session_hours": hours,
                        "rate_usd_per_hour": rate,
                        "background_productive_utilization": utilization,
                        "retry_or_interruption_loss_fraction": retry_rate,
                        "lifecycle_overhead_seconds": overhead_seconds,
                        "lifecycle_overhead_fraction_of_session": overhead_seconds / seconds,
                        "productive_batches_expected": (seconds - overhead_seconds) * utilization / BATCH_SECONDS,
                        "all_in_usd_per_million_output_tokens": cost,
                        "beats_target": cost is not None and cost <= TARGET,
                    })
    frontier = []
    for hours in SESSION_HOURS:
        for rate in RATES:
            for retry_rate in RETRY_RATES:
                frontier.append({
                    "session_hours": hours,
                    "rate_usd_per_hour": rate,
                    "retry_or_interruption_loss_fraction": retry_rate,
                    "minimum_background_productive_utilization": minimum_utilization(
                        rate, hours * 3600, retry_rate, overhead_seconds
                    ),
                    "minimum_batches_if_no_background_idle": minimum_batches(
                        rate, retry_rate, overhead_seconds),
                })
    fraction_sensitivity = []
    for lifecycle_fraction in (0.05, 0.10, 0.20):
        for rate in RATES:
            for retry_rate in RETRY_RATES:
                required = lifecycle_fraction_frontier(rate, lifecycle_fraction, retry_rate)
                fraction_sensitivity.append({
                    "lifecycle_overhead_fraction": lifecycle_fraction,
                    "rate_usd_per_hour": rate,
                    "retry_or_interruption_loss_fraction": retry_rate,
                    "minimum_background_productive_utilization": required,
                    "feasible": required <= 1,
                })
    representative = [
        row for row in session_grid
        if row["background_productive_utilization"] == 0.90
        and row["retry_or_interruption_loss_fraction"] == 0.05
    ]
    result = {
        "schema_version": 1,
        "scope": "zero-provider student39 L40S sustainable lifecycle bound",
        "evidence_labels": {
            "measured": "content-bound event or summary telemetry",
            "derived": "deterministic arithmetic from measured values",
            "inferred": "production-envelope interpretation, not an observed production quote or warm-start result",
        },
        "fixed_measured_inputs": {
            "c32_output_tokens_per_second": TOKENS_PER_SECOND,
            "c32_batch_output_tokens": TOKENS_PER_BATCH,
            "c32_batch_wall_seconds": BATCH_SECONDS,
            "c32_steady_state_usd_per_million_at_1_10": steady_cost(1.1),
            "target_usd_per_million_output_tokens": TARGET,
            "production_rates_usd_per_hour": list(RATES),
        },
        "exact_session_timeline": {
            "valid_retry_allocation_created_at_utc": "2026-07-15T20:56:28.788537Z",
            "valid_c32_repair_started_at_utc": "2026-07-15T21:23:25.979424Z",
            "valid_c32_repair_finished_at_utc": "2026-07-15T21:32:43.947044Z",
            "cleanup_verified_at_utc": "2026-07-15T21:33:42.102908Z",
            "reproducible_cold_path_phases": phase_map,
            "reproducible_cold_path_overhead_seconds": overhead_seconds,
            "productive_profile_phases": [
                {"name": "c16_exploration", "seconds": 48.58667630900004, "evidence_type": "measured"},
                {"name": "c24_exploration", "seconds": 74.28580105499987, "evidence_type": "measured"},
                {"name": "c32_production_unit", "seconds": BATCH_SECONDS, "evidence_type": "measured"},
            ],
            "research_only_failures": [
                {
                    "description": "First allocation ended in artifact-retrieval parser StockError after a successful scientific workload.",
                    "start_at_utc": "2026-07-15T20:37:45.534454Z",
                    "end_at_utc": "2026-07-15T20:54:08.908725Z",
                    "exposure_seconds": 983.374271,
                    "classification": "one_time_research_harness_failure_excluded_from_production_model",
                },
                {
                    "description": "Retry's pre-repair scientific workload did not materialize the valid result; repair reused its resident runtime and checkpoint.",
                    "start_at_utc": "2026-07-15T21:08:58.688577Z",
                    "end_at_utc": "2026-07-15T21:23:25.763024Z",
                    "exposure_seconds": 867.074447,
                    "classification": "one_time_research_harness_failure_excluded_from_production_model",
                },
            ],
        },
        "formula": {
            "all_in_usd_per_million": "steady_state_usd_per_million / (background_productive_utilization * (1 - lifecycle_overhead_seconds/session_seconds) * (1 - retry_or_interruption_loss_fraction))",
            "minimum_utilization": "steady_state_usd_per_million / (target * (1 - lifecycle_overhead_seconds/session_seconds) * (1 - retry_or_interruption_loss_fraction))",
            "retry_interpretation": "fraction of otherwise productive output-time lost to retries or interruptions; no warm-start or provider recovery mechanism is assumed",
        },
        "sustainable_frontier": frontier,
        "session_grid": session_grid,
        "lifecycle_fraction_sensitivity": fraction_sensitivity,
        "representative_90pct_utilization_5pct_retry": representative,
        "portfolio_decision": {
            "decision": "PRESERVE_L40S_AS_CONDITIONAL_RECOVERY_DENOMINATOR",
            "evidence_type": "inferred_from_measured_throughput_and_derived_lifecycle_model",
            "reason": "At $1.10/hour, an 8-hour session at 90% productive utilization and 5% retry loss is below target; the same is true at $1.00/hour. The bound fails for a 2-hour session and does not support $1.25/hour at that representative envelope.",
            "production_boundary": "This is not a production quote, a quality result, or evidence of warm-start/recovery semantics. Any placement claim above $1.10/hour requires materially longer or near-saturated sessions, lower retry loss, or a measured lifecycle reduction.",
        },
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
