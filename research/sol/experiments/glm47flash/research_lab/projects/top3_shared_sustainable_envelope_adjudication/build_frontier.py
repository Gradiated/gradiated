#!/usr/bin/env python3
"""Build the deterministic top-3/shared session-length economics frontier."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(__file__).resolve().parent
DIRECT = ROOT / "projects/full47_top3_shared_c32_direct/artifacts/l40s_top3_shared_c32_20260716_r1"
LIFECYCLE = ROOT / "projects/full47_stock_frontier_sustainable_cogs/artifacts/SUSTAINABLE_COGS_DECISION_2026-07-16.json"
PRICES = Path("/root/workspace/research/factory/data/gpu_prices.json")
OUTPUT = PROJECT / "artifacts/SUSTAINABLE_ENVELOPE_FRONTIER_2026-07-16.json"

TARGET = 0.514
THROUGHPUT_TOKENS_PER_SECOND = 644.31800498966
FIXED_LIFECYCLE_LOSS_SECONDS = 1151.243
PRODUCTIVE_SECONDS_PER_BATCH = 101.713749255
RATES = (1.00, 1.10, 1.25)
RESERVES = (0.01, 0.02, 0.03, 0.05)
EXPECTED_ARCHIVES = {
    "top4_shared_c32_pre": "8070ea8b1bb8af12628c1f7d8fa3d1ecace82f892802ae5f9780f44e482ea765",
    "top3_shared_c32": "7d232e1637cb2b7ea03f1890880598a14b26fd8cc8683b8b5723420eda77e10d",
    "top4_shared_c32_post": "b7a7a5392e3792ddfbe79412fcf3e86fce38d7d3d33154322e93c858b2c47eaf",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_gpu_cogs(rate: float) -> float:
    return rate * 1_000_000 / (3600 * THROUGHPUT_TOKENS_PER_SECOND)


def frontier_cell(rate: float, reserve: float) -> dict[str, object]:
    raw = raw_gpu_cogs(rate)
    gpu_budget = TARGET * (1 - reserve)
    if raw >= gpu_budget:
        return {
            "planning_rate_usd_per_gpu_hour": rate,
            "omitted_cost_reserve_fraction_of_target": reserve,
            "gpu_budget_usd_per_million_output_tokens": gpu_budget,
            "raw_gpu_usd_per_million_output_tokens": raw,
            "admissible": False,
            "reason": "steady_state_gpu_cogs_exhausts_reserved_target_before_lifecycle",
        }
    productive_fraction = raw / gpu_budget
    productive_seconds_required = (
        FIXED_LIFECYCLE_LOSS_SECONDS * productive_fraction / (1 - productive_fraction)
    )
    batches = math.ceil(productive_seconds_required / PRODUCTIVE_SECONDS_PER_BATCH)
    productive_seconds = batches * PRODUCTIVE_SECONDS_PER_BATCH
    maximum_fixed_loss = productive_seconds * (1 - productive_fraction) / productive_fraction
    total_session_seconds = productive_seconds + FIXED_LIFECYCLE_LOSS_SECONDS
    return {
        "planning_rate_usd_per_gpu_hour": rate,
        "omitted_cost_reserve_fraction_of_target": reserve,
        "gpu_budget_usd_per_million_output_tokens": gpu_budget,
        "raw_gpu_usd_per_million_output_tokens": raw,
        "admissible": True,
        "minimum_productive_fraction": productive_fraction,
        "maximum_total_lifecycle_loss_fraction": 1 - productive_fraction,
        "required_productive_batches_64_requests": batches,
        "required_productive_seconds": productive_seconds,
        "required_productive_hours": productive_seconds / 3600,
        "minimum_total_session_hours_with_measured_fixed_loss": total_session_seconds / 3600,
        "measured_fixed_lifecycle_loss_seconds": FIXED_LIFECYCLE_LOSS_SECONDS,
        "maximum_fixed_lifecycle_loss_seconds_at_integer_batch_count": maximum_fixed_loss,
        "fixed_loss_slack_seconds_at_integer_batch_count": maximum_fixed_loss - FIXED_LIFECYCLE_LOSS_SECONDS,
    }


def main() -> None:
    archive_digests = {
        arm: digest(DIRECT / arm / "vllm-awq-batch.tar.gz") for arm in EXPECTED_ARCHIVES
    }
    if archive_digests != EXPECTED_ARCHIVES:
        raise SystemExit(f"immutable archive verification failed: {archive_digests}")
    lifecycle = json.loads(LIFECYCLE.read_text())
    measured_loss = lifecycle["measured_lifecycle_components_seconds"]
    measured_session = lifecycle["inputs"]["measured_maxseq36"]
    if measured_loss["checkpoint_transfer_attempts"] != 1:
        raise SystemExit("unexpected lifecycle transfer-attempt count")
    lifecycle_difference = (
        measured_session["allocation_seconds_at_retrieval"]
        - measured_session["scored_profile_seconds_c32_plus_c36"]
    )
    if abs(lifecycle_difference - FIXED_LIFECYCLE_LOSS_SECONDS) > 1e-6:
        raise SystemExit("recorded lifecycle difference does not match frozen fixed loss")
    prices = json.loads(PRICES.read_text())
    l40s = next(item for item in prices["accelerators"] if item["id"] == "nvidia-l40s")
    if l40s["production_planning_usd_per_gpu_hour"] != 1.10 or l40s["production_evidence_range_usd_per_gpu_hour"] != [1.0, 1.25]:
        raise SystemExit("shared L40S rate bracket changed")

    cells = [frontier_cell(rate, reserve) for rate in RATES for reserve in RESERVES]
    admissible = [cell for cell in cells if cell["admissible"]]
    result = {
        "schema_version": 1,
        "classification": "ENVELOPE_EVIDENCE_OPEN",
        "question": "Can the measured top-3/shared arm support a conservative long-session sustainable COGS envelope?",
        "evidence": {
            "archive_sha256": archive_digests,
            "candidate_throughput_tokens_per_second": THROUGHPUT_TOKENS_PER_SECOND,
            "measured_fixed_lifecycle_loss_seconds": FIXED_LIFECYCLE_LOSS_SECONDS,
            "productive_seconds_per_64_request_batch": PRODUCTIVE_SECONDS_PER_BATCH,
            "lifecycle_source_sha256": digest(LIFECYCLE),
            "price_inventory_sha256": digest(PRICES),
            "price_policy": {"base_rate_usd_per_gpu_hour": 1.10, "range_usd_per_gpu_hour": [1.0, 1.25]},
        },
        "method": {
            "all_in_gpu_cogs": "raw_gpu_cogs / productive_fraction",
            "raw_gpu_cogs": "rate * 1e6 / (3600 * measured_tokens_per_second)",
            "reserve_treatment": "Each reserve is withheld from the $0.514/M target for unpriced storage, transfer, orchestration, interruption, retry, cleanup, and other omitted costs.",
            "fixed_loss_treatment": "The settled 1,151.243 seconds is amortized once per session. It is measured experiment lifecycle loss, not a production recurrence or reliability policy.",
        },
        "frontier": cells,
        "interpretation": {
            "admissible_cell_count": len(admissible),
            "inadmissible_rate": 1.25,
            "inadmissible_rate_reason": "Its $0.538899/M steady-state GPU COGS exceeds the $0.514/M target before any reserve or lifecycle loss.",
            "base_rate_admissible_reserves": [cell["omitted_cost_reserve_fraction_of_target"] for cell in admissible if cell["planning_rate_usd_per_gpu_hour"] == 1.10],
            "decision": "Mathematical envelopes exist at $1.00 and $1.10/hour with explicit 1–5% omitted-cost reserves, so MARKET_ONLY_HEADROOM_CONFIRMED is unsupported. No measured maximum session duration, interruption/retry distribution, production queue-fill/reliability policy, or priced/bounded omitted-cost recurrence exists, so no named conservative envelope can be admitted.",
            "single_missing_policy_fact": "A production session/reliability policy that sets a maximum session duration and bounds interruption/retry plus the recurrence and cost of storage, transfer, orchestration, and cleanup within one selected reserve cell.",
        },
        "quality_scope": "QUALITY_ARTIFACT_CLOSE remains separate; this economics result neither repairs quality evidence nor authorizes paid work.",
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
