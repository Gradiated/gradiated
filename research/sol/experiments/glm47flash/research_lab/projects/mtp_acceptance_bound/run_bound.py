#!/usr/bin/env python3
"""Deterministic MTP acceptance/overhead bound for the GLM c8 control."""

import json
from pathlib import Path


BASE_TPS = 303.95477514818526
K = 4
TARGET_GAIN = 1.05


def speculative_speed(acceptance, verify_cost, draft_cost):
    # One target token is emitted for each verification round, plus accepted drafts.
    return (1.0 + K * acceptance) / (verify_cost + K * draft_cost)


def end_to_end_gain(acceptance, verify_cost, draft_cost, decode_fraction, nondraftable):
    s = speculative_speed(acceptance, verify_cost, draft_cost)
    draftable = decode_fraction * (1.0 - nondraftable)
    return 1.0 / ((1.0 - draftable) + draftable / s)


def threshold(verify_cost, draft_cost, decode_fraction, nondraftable):
    for i in range(10001):
        a = i / 10000
        if end_to_end_gain(a, verify_cost, draft_cost, decode_fraction, nondraftable) >= TARGET_GAIN:
            return a
    return None


def main():
    scenarios = [
        {"name": "optimistic", "verify_cost": 1.00, "draft_cost": 0.10},
        {"name": "moderate", "verify_cost": 1.15, "draft_cost": 0.20},
        {"name": "conservative", "verify_cost": 1.30, "draft_cost": 0.30},
        {"name": "harsh", "verify_cost": 1.50, "draft_cost": 0.50},
    ]
    rows = []
    for scenario in scenarios:
        for decode_fraction in (0.90, 0.95, 1.00):
            for nondraftable in (0.00, 0.10):
                a = threshold(scenario["verify_cost"], scenario["draft_cost"], decode_fraction, nondraftable)
                rows.append({
                    **scenario,
                    "decode_fraction": decode_fraction,
                    "nondraftable_fraction": nondraftable,
                    "minimum_acceptance_fraction": a,
                    "minimum_mean_accepted_draft_tokens": None if a is None else K * a,
                    "predicted_tps_at_threshold": None if a is None else BASE_TPS * end_to_end_gain(a, scenario["verify_cost"], scenario["draft_cost"], decode_fraction, nondraftable),
                })
    result = {
        "schema_version": 1,
        "evidence_label": "derived deterministic simulation",
        "control": {"c8_output_toks_per_s": BASE_TPS, "source": "nebius_h100_reasoning_off_quality_mtp_v8/summary.json", "output_tokens": 1024, "requests": 16},
        "native_configuration_audit": {
            "runtime_source": "SGLang v0.5.15-cu130, source f63458b5beaceabbd9d749b9fc956370e1b649e6",
            "observed_arguments": "EAGLE, draft path=/workspace/model, steps=1, topk=1, draft tokens=2 in retained attempt3 server-mtp stderr",
            "campaign_candidate": "EAGLE, steps=3, topk=1, draft tokens=4",
            "capability_status": "argument parsing supported; checkpoint load and acceptance telemetry not established",
            "falsifier": "retained attempt3 MTP server reaches loader failure after argument parsing; campaign v8-v11 never admitted a valid MTP arm",
        },
        "model": {"draft_width": K, "target_gain": TARGET_GAIN, "formula": "speed=(1+K*a)/(verify_cost+K*draft_cost); end_to_end=1/((1-f)+(f/speed)), f=decode_fraction*(1-nondraftable)"},
        "scenarios": rows,
        "decision": "KILL_FOR_CAMPAIGN",
        "decision_rule": "Thresholds are a prerequisite only. Promote requires supported checkpoint execution, measured acceptance/overhead, and quality admission; those gates are absent.",
    }
    out = Path(__file__).with_name("mtp_acceptance_bound.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"artifact": str(out), "decision": result["decision"], "rows": len(rows)}))


if __name__ == "__main__":
    main()
