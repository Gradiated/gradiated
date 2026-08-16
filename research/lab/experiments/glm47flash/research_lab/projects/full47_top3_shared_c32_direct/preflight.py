#!/usr/bin/env python3
"""Emit the real-artifact contract and measured retained-session budget proof."""
import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
PREDECESSOR = PROJECT.parents[0] / "full47_top2_shared_c32_direct_corrected" / "artifacts" / "l40s_top2_shared_c32_20260716_r2"


def phase_seconds(path: Path) -> float:
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    return round(sum(float(row.get("elapsed_seconds", 0)) for row in rows if row.get("event") == "phase_finished"), 3)


def main() -> None:
    pre = PREDECESSOR / "top4_shared_c32_pre"
    candidate = PREDECESSOR / "top2_shared_c32"
    summary = json.loads((pre / "summary.json").read_text())
    profile = summary["allocation_result"]["performance"]["profiles"][0]
    valid = (
        profile["output_tokens_per_second_conservative"] == 611.7645585359348
        and profile["requests"] == 64 and len(profile["rows"]) == 64
        and profile["prefix_cache_disabled"] is True and profile["prefix_cache_zero_delta"] is True
    )
    bootstrap = float(summary["allocation_seconds"])
    retained = float(json.loads((candidate / "summary.json").read_text())["allocation_seconds"])
    cleanup = 240.0
    projected = round(bootstrap + 2 * retained + cleanup, 3)
    result = {
        "classification": "TOP3_REAL_ARTIFACT_AND_MEASURED_BUDGET_PASS" if valid and projected <= 3000 else "TOP3_PRECREATE_CLOSE",
        "real_artifact": str(pre / "summary.json"),
        "real_artifact_sha256": hashlib.sha256((pre / "summary.json").read_bytes()).hexdigest(),
        "corrected_background_evaluator": {"pass": valid, "conservative_tok_s": profile["output_tokens_per_second_conservative"], "deferred_quality_marker": summary["allocation_result"]["quality"].get("absolute_bf16_quality_failure_carried_forward")},
        "measured_seconds": {"fresh_bootstrap_and_pre_arm": bootstrap, "retained_arm_with_failure_cleanup": retained, "measured_phase_seconds_fresh": phase_seconds(pre / "events.jsonl"), "measured_phase_seconds_retained": phase_seconds(candidate / "events.jsonl"), "planned_top4_top3_top4_plus_cleanup": projected, "absolute_budget": 3000.0, "reserve": round(3000 - projected, 3)},
        "actual_rate_usd_per_hour": 0.8581222,
        "worst_case_cost_usd": round(0.8581222 * 3000 / 3600, 6),
        "authorized_cost_usd": 0.75,
    }
    output = PROJECT / "artifacts" / "PRECREATE_PREFLIGHT.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if result["classification"] != "TOP3_REAL_ARTIFACT_AND_MEASURED_BUDGET_PASS" or result["worst_case_cost_usd"] > result["authorized_cost_usd"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
