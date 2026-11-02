"""Plan disjoint synthetic training worlds and varied, evidence-bound analytical requests.

This is an authoring plan, not an accepted dataset. Each world needs a live audit and each
task needs independent validation. No benchmark scores participate in task selection.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from scenario_project import build, identifier, write_project


VARIANTS = {
    "anomaly_investigation": (
        "Decompose the before/after failure-rate change into traffic-mix and within-segment changes, with a fixed reference mix.",
        "Locate the change point from daily rates, compare an affected segment with an unaffected control, and assess denominator sensitivity.",
        "Prioritize browser/OS segments by excess failed attempts relative to their own baseline; separate volume from risk and quantify coverage.",
    ),
    "attribution_marketing": (
        "Compare mature signup-to-paid conversion and paid-customer yield across acquisition sources; explain how rankings change with the denominator.",
        "Compare source-level seven-day report adoption with device-standardized rates; distinguish composition from within-device performance.",
        "Compare acquisition cohorts' repeat product use and subscriptions with equal follow-up windows; treat low-count and immature groups explicitly.",
    ),
    "build_insight_dashboard": (
        "Persist an acquisition-quality dashboard containing mature person-cohort conversion and equal-follow-up engagement tables.",
        "Persist a product-adoption dashboard with ordered milestone conversion and an elapsed-day retention table, including explicit maturity filters.",
        "Persist an operations dashboard with report export reliability, AI spend and subscription receipts as separately defined saved queries.",
    ),
    "entity_lookup": (
        "Select a real customer with two invoices in a calendar month and reconcile the dated subscription/payment records; explain whether observed invoice IDs establish a duplicate.",
        "Select a paying customer with AI usage and reconcile their subscription charges versus backend model costs by model and calendar period. Internal cost is not a customer charge.",
        "Resolve a named customer and account, then reconstruct first payment, renewals and paid-feature usage over an explicit interval; state what the records cannot prove about bank debits.",
    ),
    "flags_experiments": (
        "Estimate guided-minus-control onboarding and paid-conversion risk differences with approximate 95% intervals in one mature cohort; explicitly request missing/conflicting assignment checks.",
        "Compare device-stratified and overall guided-minus-control adoption differences, with uncertainty and assignment QA on exactly the same eligible people.",
        "Assess whether sample size and effect uncertainty justify a rollout decision using a declared mature-cohort endpoint, attrition counts and exposure consistency.",
    ),
    "funnel_conversion": (
        "Use completed signups as entrants and compute ordered onboarding, report creation and successful-export conversion within seven days, segmented by device.",
        "Compare guided/control completed-signup cohorts' ordered report adoption within one versus seven days; separate delay from observed non-adoption.",
        "Find the largest absolute and conditional losses in a mature completed-signup-to-report-to-export journey by source, with explicit elapsed-time deadlines.",
    ),
    "llm_analytics": (
        "Reconcile input/output token costs by model and report type; price a fixed-token switch to the cheaper model while explicitly holding tokens and usage fixed.",
        "Decompose monthly AI spend change into generation volume, model mix and mean per-generation cost using an explicit reference month.",
        "Rank report types by model usage and cost, then calculate savings under a precisely defined partial routing policy; do not infer answer-quality equivalence.",
    ),
    "retention_engagement": (
        "Compare elapsed day-1/day-7 active-event retention for completed-signup cohorts by acquisition source, using equal follow-up and explicit denominators.",
        "Compare day-7 retention across immutable first flag-exposure cohorts and separately among onboarding completers; explain selection and causal limits.",
        "Compare weekly repeat report activity across mature signup cohorts; distinguish exact-day retention, rolling return and active-days frequency.",
    ),
    "sql_help": (
        "Repair an average-of-daily-p95 query: compute the exact pooled percentile, both invalid daily averages and a strict latency-threshold exceedance count.",
        "Repair a weighted-average-of-model-p95 query: reconstruct the pooled tail from raw generations and reconcile model-specific exceedance counts.",
        "Implement and explain an elapsed-time ordered person funnel query that wrongly counts unordered event existence; report both definitions on a mature cohort.",
    ),
    "tracking_quality": (
        "Reconcile export attempts and terminal outcomes by identifiers and chronology, including orphans, repeated outcomes and the trustworthiness of rate denominators.",
        "Check recorded export durations against attempt/outcome timestamp differences, segment coverage and timeout semantics; report clean checks honestly.",
        "Audit paid AI event sequences, token-cost arithmetic and entitlement chronology, separating missing telemetry from evidence of real product failure.",
    ),
    "trend_breakdown": (
        "Reconcile month-over-month subscription receipts into first payments and renewals, then forecast the next 30 days under explicit unchanged-price/no-churn/no-new-sales assumptions.",
        "Forecast weekly renewal receipts for the next four full weeks from observed invoice cadence and current accounts; reconcile the total and state boundary conventions.",
        "Compare mature first-payment cohorts' renewal contribution and calculate the conditional receipts impact of a user-specified churn scenario without claiming observed churn.",
    ),
    "warehouse": (
        "Join current paid accounts to exports and invoices without fanout to quantify account-level failure exposure and associated monthly subscription value.",
        "Reconcile warehouse invoices with subscription event IDs and amounts by month; protect person/account joins and distinguish duplicate joins from duplicate billing records.",
        "Compare acquisition-source subscription receipts and paying-account export reliability using independently aggregated invoices/events before joining.",
    ),
}


def plan(train_worlds: int = 20, dev_worlds: int = 2, first_seed: int = 1101,
         now: str = "2026-11-02T00:00:00+00:00") -> dict:
    if train_worlds < 1 or dev_worlds < 1 or first_seed < 1000:
        raise ValueError("Use positive train/dev counts and a new seed range starting at 1000 or above")
    anchor = dt.datetime.fromisoformat(now)
    if anchor.tzinfo is None or any((anchor.hour, anchor.minute, anchor.second, anchor.microsecond)):
        raise ValueError("Use an explicit UTC-midnight data cutoff")
    if anchor.utcoffset() != dt.timedelta(0):
        raise ValueError("Data cutoff must be UTC")
    worlds = []
    for i in range(train_worlds + dev_worlds):
        split = "train" if i < train_worlds else "dev"
        seed = first_seed + i
        focus = {}
        for j, (family, variants) in enumerate(VARIANTS.items()):
            variant = (i + j) % len(variants)
            # Prefixes are workflow boundaries; variants deliberately replace the older central request.
            focus[family] = variants[variant] + (
                " Verify every premise in this world. Use exact UTC calendar boundaries and mature follow-up. "
                "Only grade requirements explicitly requested by the user. Do not supply reference answers in the request. "
                "Historical onboarding assignment must come from the first recorded flag-exposure event's immutable "
                "response, never latest person properties. Exposure follows registration, so do not segment anonymous "
                "signup starts by a later assignment. Do not infer retries, occupations, causal effects or bank debits."
            )
        worlds.append({"seed": seed, "twin_id": identifier(seed, "project"), "split": split,
                       "people": (700, 850, 1000, 1150)[i % 4], "days": (84, 105, 126)[i % 3],
                       "anonymous_ratio": (1.5, 2.0, 2.5)[i % 3], "difficulty_target": 3 if i % 3 == 0 else 4,
                       "focus_variant": i % 3, "family_focus": focus})
    return {"version": 1, "evidence": "synthetic authoring plan; not task acceptance or measured difficulty",
            "raw_now": anchor.isoformat(), "worlds": worlds, "families": list(VARIANTS),
            "expected_training_candidates": train_worlds * len(VARIANTS),
            "expected_development_candidates": dev_worlds * len(VARIANTS),
            "admission": {"training_tasks": [150, 300], "independent_sample": 30, "required_sound": 28,
                          "requires_live_global_audit": True, "requires_primary_and_gate": True},
            "scope": "One reporting-product archetype, varied populations/history and three question scopes per family; not independent product archetypes"}


def generate(p: dict, root: Path) -> list[dict]:
    summaries = []
    for world in p["worlds"]:
        data = build(world["seed"], dt.datetime.fromisoformat(p["raw_now"]), world["people"],
                     world["days"], world["split"], world["anonymous_ratio"])
        data["manifest"]["family_focus"] = world["family_focus"]
        data["manifest"]["supported_families"] = list(VARIANTS)
        data["manifest"]["training_recipe"] = {k: world[k] for k in ("seed", "difficulty_target", "focus_variant")}
        path = write_project(data, root)
        summaries.append({"project": str(path), "split": world["split"], **data["manifest"]["counts"]})
    return summaries


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--train-worlds", type=int, default=20)
    ap.add_argument("--dev-worlds", type=int, default=2)
    ap.add_argument("--first-seed", type=int, default=1101)
    ap.add_argument("--now", default="2026-11-02T00:00:00+00:00")
    ap.add_argument("--generate", action="store_true", help="host-only: write synthetic Parquet worlds")
    args = ap.parse_args()
    p = plan(args.train_worlds, args.dev_worlds, args.first_seed, args.now)
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / "authoring_plan.json"
    if target.exists() and json.loads(target.read_text()) != p:
        raise ValueError("Existing authoring plan differs; use a new output root")
    target.write_text(json.dumps(p, indent=2))
    if args.generate:
        summaries = generate(p, args.out / "projects")
        (args.out / "generation.json").write_text(json.dumps(summaries, indent=2))
    print(json.dumps({k: p[k] for k in ("expected_training_candidates", "expected_development_candidates", "scope")}))


if __name__ == "__main__":
    main()
