#!/usr/bin/env python3
"""Build the offline selective-W4 sustainable session frontier."""
import hashlib, json, math
from pathlib import Path

PROJECT = Path(__file__).parent
DIRECT = PROJECT.parent / "full47_selective_w4_proven_path_direct/artifacts/l40s_full47_selective_w4_proven_path_20260716_r1"
SUMMARY = DIRECT / "summary.json"
ARCHIVE = DIRECT / "vllm-awq-batch.tar.gz"
PRICES = Path("/root/workspace/research/factory/data/gpu_prices.json")
OUT = PROJECT / "artifacts/SUSTAINABLE_W4_SESSION_FRONTIER_2026-07-16.json"
TARGET, THROUGHPUT, ALLOCATION, USEFUL = .514, 630.1953984207183, 1310.638, 159.965
FIXED, BATCH = ALLOCATION - USEFUL, 65536 / THROUGHPUT
RATES, RESERVES = (1.0, 1.1, 1.25), (.01, .02, .03, .05)

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def cell(rate, reserve):
    raw = rate * 1_000_000 / (3600 * THROUGHPUT); budget = TARGET * (1 - reserve)
    out = {"rate": rate, "reserve": reserve, "raw_cogs": raw}
    if raw >= budget:
        out.update(admissible=False, reason="steady_state_gpu_cogs_exceeds_reserved_target")
        return out
    frac = raw / budget; required = FIXED * frac / (1 - frac); batches = math.ceil(required / BATCH)
    productive = batches * BATCH; max_loss = productive * (1 - frac) / frac
    out.update(admissible=True, productive_fraction_required=frac, max_loss_fraction=1-frac,
               required_batches=batches, productive_seconds=productive,
               productive_hours=productive/3600, total_hours_with_measured_loss=(productive+FIXED)/3600,
               max_fixed_loss_seconds_at_integer_threshold=max_loss,
               fixed_loss_slack_seconds=max_loss-FIXED)
    return out

def main():
    summary = json.loads(SUMMARY.read_text())
    assert sha(ARCHIVE) == summary["artifact_sha256"]
    assert summary["allocation_seconds"] == ALLOCATION and summary["useful_gpu_seconds"] == USEFUL
    prices = json.loads(PRICES.read_text())
    l40s = next(x for x in prices["accelerators"] if x["id"] == "nvidia-l40s")
    assert l40s["production_planning_usd_per_gpu_hour"] == 1.1
    result = {
        "schema_version": 1, "classification": "W4_ENVELOPE_EVIDENCE_OPEN",
        "evidence": {"archive_sha256": sha(ARCHIVE), "summary_sha256": sha(SUMMARY),
          "candidate_throughput_tokens_per_second": THROUGHPUT,
          "raw_planning_gpu_usd_per_million_output_tokens_at_1_10": 1.1*1e6/(3600*THROUGHPUT),
          "allocation_seconds_measured": ALLOCATION, "useful_gpu_seconds_measured": USEFUL,
          "fixed_lifecycle_loss_seconds_derived": FIXED, "measured_productive_fraction": USEFUL/ALLOCATION,
          "measured_allocation_cost_usd": summary["cost_usd_derived"],
          "c32_productive_seconds_per_64_request_batch": BATCH, "cleanup_pass": summary["cleanup_pass"],
          "final_instance_count": summary["final_instance_count"], "final_disk_count": summary["final_disk_count"],
          "price_inventory_sha256": sha(PRICES), "price_range_usd_per_gpu_hour": [1.0, 1.25]},
        "method": {"raw_gpu_cogs": "rate * 1e6 / (3600 * measured_tokens_per_second)",
          "reserved_gpu_budget": "0.514 * (1 - reserve)", "all_in_gpu_cogs": "raw_gpu_cogs / productive_fraction",
          "fixed_loss_treatment": "Measured allocation minus useful GPU time, amortized once per hypothetical session; not a production recurrence or reliability policy.",
          "reserve_treatment": "Reserve is withheld from target for storage, transfer, orchestration, interruption, retry, cleanup, and other omitted costs."},
        "frontier": [cell(r, q) for r in RATES for q in RESERVES],
        "interpretation": {"measured_geometry_compatible": False,
          "measured_geometry_reason": "The observed 12.2051% productive fraction is below every admissible required fraction.",
          "decision": "Mathematical cells exist at $1.00/hour and the authoritative $1.10/hour base rate for every requested reserve, so a market-only close is unsupported. No production maximum-session/reliability or recurring omitted-cost bound is evidenced; no conservative sustainable admission is justified.",
          "single_missing_policy_fact": "A production session/reliability policy that selects a maximum session duration and bounds interruption/retry plus recurring storage, transfer, orchestration, and cleanup within one reserve cell.",
          "quality_scope": "This economics result neither establishes quality eligibility nor authorizes spend."}
    }
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
if __name__ == "__main__": main()
