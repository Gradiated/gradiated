#!/usr/bin/env python3
"""Derive the calibrated endpoint decision from the immutable replay outputs."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
A = ROOT / "artifacts"
summary = json.loads((A / "POLICY_SUMMARY.json").read_text())
source = json.loads((A / "SOURCE_MANIFEST.json").read_text())
anchor = 0.39375523262767614  # campaign's measured prefill-share trigger
upper = 0.60  # sensitivity assumption, not a measured claim
eff_low, eff_high = 0.80, 1.0  # lookup/queue/eviction net-efficiency range

def row(policy, cap):
    return summary[f"{policy}@{cap:g}GiB"]

affinity = row("affinity", 16)
arbitrary = row("radix_arbitrary", 16)
ideal = row("ideal", 16)
cal = {}
for name, item in (("affinity_16GiB", affinity), ("arbitrary_16GiB", arbitrary), ("ideal_unlimited", ideal),
                   ("affinity_1GiB", row("affinity", 1)), ("affinity_0.5GiB", row("affinity", 0.5))):
    hit = item["hit_fraction_of_total"]
    cal[name] = {"hit_fraction": hit, "avoidable_prefill_fraction_of_total_endpoint_compute_range":
                 [hit * anchor * eff_low, hit * upper * eff_high],
                 "derived_endpoint_cost_reduction_range": [hit * anchor * eff_low, hit * upper * eff_high],
                 "fresh_tokens": item["fresh_tokens"], "resident_hit_tokens": item["hit_tokens"],
                 "reloaded_tokens": item.get("reloaded_tokens", 0), "evictions": item.get("evictions", 0)}

decision = {
    "schema_version": 1,
    "classification": "measured exact-token replay plus derived calibration; synthetic tool results, no endpoint timing",
    "question": "Can tenant-isolated content-addressed persistent KV plausibly reduce endpoint cost by 20% on multi-turn tool traffic?",
    "source": source,
    "workload_order": "interleaved turn rounds across 165 sessions; 905 cumulative model requests",
    "measured_token_totals": {"request_tokens": affinity["request_tokens"], "ideal_repeated_prefix_tokens": ideal["hit_tokens"],
                               "ideal_repeated_prefix_fraction": ideal["hit_fraction_of_total"]},
    "policies": cal,
    "calibration": {"prefill_share_low_anchor": anchor, "prefill_share_upper_sensitivity": upper,
                    "net_prefill_recovery_efficiency_range": [eff_low, eff_high],
                    "formula": "exact_hit_fraction * exposed_prefill_wall_share * net_recovery_efficiency",
                    "anchor_evidence": "campaign trigger from measured endpoint packet; upper share and efficiency are sensitivity assumptions"},
    "capacity_and_transfer": {"kv_bytes_per_token_fp8_derived": 92800,
                               "ideal_hit_kv_bytes_fp8_gib": ideal["hit_tokens"] * 92800 / 1024**3,
                               "affinity_1GiB_reloaded_bytes_fp8_gib": row("affinity", 1)["reloaded_tokens"] * 92800 / 1024**3,
                               "affinity_0.5GiB_reloaded_bytes_fp8_gib": row("affinity", 0.5)["reloaded_tokens"] * 92800 / 1024**3,
                               "bf16_sensitivity_bytes_per_token": 491520},
    "decision_gate": {"avoidable_prefill_threshold": 0.25, "endpoint_cost_threshold": 0.20,
                       "result": "plausible_at_16GiB_or_more_with_affinity; not plausible under arbitrary routing or <=1GiB capacity",
                       "next_action": "nominate one small same-runtime cache-affinity endpoint experiment next paid cycle; no paid work authorized in this project"},
    "limitations": ["tool-result payloads are deterministic synthetic safe placeholders, not real tool execution traces",
                    "no GPU endpoint timing or live cache counters; calibration transfers the campaign prefill-share anchor only",
                    "tenant-isolated fingerprints prevent cross-tenant reuse; no cross-tenant hits were admitted"],
}
(A / "CALIBRATED_DECISION.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n")
packet = {"schema_version": 1, "status": "nominate_next_paid_cycle", "experiment": "same-runtime persistent KV on/off with exact cumulative replay",
          "intervention": "tenant-isolated content-addressed prefix keys plus replica affinity and LRU admission",
          "control": "same requests, arbitrary routing, in-process prefix cache",
          "primary_gate": "raw hit/miss/eviction/reload counters plus non-overlapping prefill/decode/endpoint timing",
          "required_quality": "identical deterministic output/tool-call behavior",
          "trigger": "run only with measured exposed prefill share >= 0.393755 and enough capacity for >=16 GiB persistent KV budget",
          "budget_authority": "separate director-approved paid cycle; current project remains $0 and performs no provider mutation",
          "evidence_basis": "CALIBRATED_DECISION.json"}
(A / "NEXT_CYCLE_PACKET.json").write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
print(json.dumps({"decision": decision["decision_gate"], "calibration": cal}, indent=2, sort_keys=True))
