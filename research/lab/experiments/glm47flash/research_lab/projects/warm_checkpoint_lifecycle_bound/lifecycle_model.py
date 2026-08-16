"""Reproducible zero-provider lifecycle bound for the measured AWQ c16 point."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).parent
RATE_USD_H = 0.8581222
DISK_USD_H = 0.0097222
TOKENS_PER_C16_ARM = 16 * 1024 * 2
ARM_SECONDS = 61.216
BASE_USD_M = 0.4453081747
HURDLE_USD_M = 0.5688888888888889


def seconds(start: str, end: str) -> float:
    return (datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()


def economics(overhead: float, batches: int, retained_idle_hours: float = 0.0) -> dict:
    active = overhead + batches * ARM_SECONDS
    cost = active / 3600 * RATE_USD_H + retained_idle_hours * RATE_USD_H
    output_m = batches * TOKENS_PER_C16_ARM / 1_000_000
    return {
        "batches": batches,
        "active_seconds": round(active, 6),
        "productive_utilization": round(batches * ARM_SECONDS / active, 9),
        "cost_usd": round(cost, 9),
        "usd_per_m_output": round(cost / output_m, 9),
    }


def min_batches(overhead: float, hurdle: float = HURDLE_USD_M) -> int:
    n = 1
    while economics(overhead, n)["usd_per_m_output"] > hurdle:
        n += 1
    return n


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "LIFECYCLE_MODEL_2026-07-15.json")
    args = parser.parse_args()

    # Content-bound event timestamps from the successful r2 session. The
    # post-load interval is deliberately interval-censored: it contains the
    # remaining c1/c8/c16 arms, retrieval, and orchestration.
    phases = [
        {"name": "allocation", "seconds": seconds("2026-07-15T11:57:14.151309Z", "2026-07-15T11:57:58.444344Z"), "evidence": "measured events.jsonl"},
        {"name": "ssh_cloud_init", "seconds": seconds("2026-07-15T11:57:58.444344Z", "2026-07-15T11:58:43.808624Z"), "evidence": "measured events.jsonl"},
        {"name": "image_bootstrap_and_preflight", "seconds": seconds("2026-07-15T11:58:43.808624Z", "2026-07-15T12:05:29.948598Z"), "evidence": "measured events.jsonl; phase boundary includes bootstrap"},
        {"name": "checkpoint_transfer_and_integrity", "seconds": seconds("2026-07-15T12:05:29.948598Z", "2026-07-15T12:13:16.427620Z"), "evidence": "measured events.jsonl; includes 7.592 s tiny probe"},
        {"name": "model_load_compile_warmup", "seconds": seconds("2026-07-15T12:15:21Z", "2026-07-15T12:17:11Z"), "evidence": "measured runner progress; model identity is separated"},
        {"name": "science_c16", "seconds": ARM_SECONDS, "evidence": "measured summary: c16 arm"},
        {"name": "remaining_arms_retrieval", "seconds": seconds("2026-07-15T12:17:11Z", "2026-07-15T12:20:46.245616Z"), "evidence": "interval-censored measured event boundary"},
        {"name": "cleanup", "seconds": seconds("2026-07-15T12:20:46.245616Z", "2026-07-15T12:21:39.415076Z"), "evidence": "measured events.jsonl"},
    ]
    # The comparator's 84-batch bound treats the observed 1,412.452 s
    # provider-active session as lifecycle overhead added to future arms.
    # This is intentionally conservative: it retains retrieval and cleanup,
    # which are not yet separable from a one-arm production session.
    measured_setup = 1412.452
    scenarios = []
    for name, removed, status in [
        ("ephemeral_staging", 0.0, "measured baseline"),
        ("persistent_disk_attach_only", 458.887, "conditional: removes AWQ network transfer only; attach/restore rate unmeasured"),
        ("custom_image_or_snapshot", 458.887 + 406.140, "conditional: removes transfer and image/bootstrap work; clone/restore and image semantics unmeasured"),
        ("retained_warm_allocation", 1196.769, "conditional: avoids measured allocation through model-load path; idle retention and preemption behavior unmeasured"),
    ]:
        overhead = measured_setup - removed
        n = min_batches(overhead)
        scenarios.append({
            "mechanism": name,
            "status": status,
            "removed_seconds_assumed": removed,
            "remaining_overhead_seconds": round(overhead, 6),
            "minimum_batches_to_hurdle": n,
            "economics_at_minimum": economics(overhead, n),
            "economics_at_84_batches": economics(overhead, 84),
            "best_case_100_batch_utilization": economics(overhead, 100),
        })

    independent_transfer = {
        "checkpoint": "V35 BF16",
        "bytes_staged": 46988963759,
        "bytes_total": 62444175504,
        "observation_window_seconds": 900.0,
        "staged_fraction": 46988963759 / 62444175504,
        "observed_rate_mb_s_decimal": 46988963759 / 900 / 1_000_000,
        "full_transfer_seconds_at_observed_rate": 62444175504 / (46988963759 / 900),
        "evidence": "quality_gate_calibration RESEARCH_LOG.md, read-only observations at 12:46:52Z and 13:01:52Z",
        "label": "measured transfer only; not serving-throughput evidence",
    }
    result = {
        "schema_version": 1,
        "scope": "zero-provider warm checkpoint lifecycle bound",
        "checkpoint": {"revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881", "bytes": 20170199928, "manifest_sha256": "e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86"},
        "inputs": {"rate_usd_per_hour": RATE_USD_H, "boot_disk_rate_usd_per_hour": DISK_USD_H, "arm_seconds": ARM_SECONDS, "tokens_per_arm": TOKENS_PER_C16_ARM, "steady_state_usd_per_m_output": BASE_USD_M, "strict_hurdle_usd_per_m_output": HURDLE_USD_M, "measured_session_seconds": 1412.452, "measured_lifecycle_overhead_seconds": measured_setup, "measured_setup_before_c16_seconds": 1351.236},
        "phases": phases,
        "independent_transfer": independent_transfer,
        "mechanism_catalog": [
            {"mechanism": "persistent managed disk", "current_evidence": "100-GiB boot disk rate only; no current attach/restore benchmark", "production_boundary": "provider-specific attach, regional, preemption, integrity and deletion contract required"},
            {"mechanism": "snapshot/clone", "current_evidence": "no content-bound current catalog or rate in repository", "production_boundary": "must prove atomic clone/restore and hash verification"},
            {"mechanism": "custom image", "current_evidence": "runtime image is built during bootstrap; no model-bearing image artifact", "production_boundary": "image publication, region, refresh, and immutable checkpoint identity required"},
            {"mechanism": "regional object/cache staging", "current_evidence": "no content-bound provider cache evidence", "production_boundary": "must measure cache-hit transfer and egress/storage"},
            {"mechanism": "retained warm allocation", "current_evidence": "V19 amendment documents reuse intent; no current recovery measurement", "production_boundary": "idle cost, preemption, watchdog ownership and cleanup dominate"},
        ],
        "scenarios": scenarios,
        "decision": "CLOSE_WARM_TOPOLOGY_NO_CANARY",
        "decision_rule": "No later canary: zero-cost evidence does not bind a current executable provider warm path or prove >=5% measured setup/recovery reduction.",
        "next_move": "Treat >=84 c16 batches per fresh ephemeral session and >=78.3% productive utilization as the conservative production requirement; revisit only after a provider-supported warm path has current rates, semantics, and an authorized canary.",
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"artifact": str(args.output), "decision": result["decision"], "baseline_min_batches": scenarios[0]["minimum_batches_to_hurdle"]}, indent=2))


if __name__ == "__main__":
    main()
