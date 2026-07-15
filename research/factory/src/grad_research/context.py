from __future__ import annotations

from typing import Any


def build_coordinator_context(state: dict[str, Any]) -> str:
    cycle = state["current_cycle"]
    latest_portfolio = state["portfolios"].get(str(cycle), {})
    selected_ids = latest_portfolio.get("selected_ids", [])
    selected = [state["scouts"].get(scout_id, {}) for scout_id in selected_ids]
    latest_observations = sorted(
        state["observations"].values(), key=lambda row: (row["cycle"], row["id"]), reverse=True
    )[:5]
    lines = [
        f"# Coordinator context: {state['program_id']}",
        "",
        f"Event head: `{state['event_head_sha256'] or 'none'}`",
        f"Current cycle: {cycle}",
        f"Baseline: `{(state['baseline'] or {}).get('id', 'missing')}`",
        f"Residual bottleneck: {state['residual_bottleneck'] or 'unmeasured'}",
        f"Next action: {state['next_action'] or 'measure the tuned control and generate scouts'}",
        "",
        "## Latest observations",
    ]
    if latest_observations:
        for row in latest_observations:
            lines.append(f"- `{row['id']}` [{row['evidence_class']}]: {row['summary']}")
            for gap in row.get("instrumentation_gaps", []):
                lines.append(
                    f"  - Missing `{gap['signal']}` blocks {gap['decision_blocked']}. "
                    f"Next probe: {gap['next_probe']}"
                )
    else:
        lines.append("- None recorded.")
    observability = state.get("observability", {})
    lines.extend(["", "## Observability health"])
    lines.append(
        f"- Complete evidence bundles: {observability.get('artifact_complete_runs', 0)} / "
        f"{observability.get('admitted_runs', 0)} admitted runs."
    )
    gaps = observability.get("telemetry_gaps", {})
    if gaps:
        for run_id, signals in sorted(gaps.items()):
            lines.append(f"- `{run_id}` instrumentation debt: {', '.join(signals)}")
    else:
        lines.append("- No recorded instrumentation debt.")
    lines.extend(["", "## Active scout portfolio"])
    if selected:
        for card in selected:
            lines.append(
                f"- `{card.get('id')}` — {card.get('slot')} / {card.get('family')} / "
                f"{card.get('origin')}: {card.get('mechanism')} Cheapest falsifier: {card.get('falsifier')}"
            )
    else:
        lines.append("- No portfolio selected for this cycle.")
    coverage = latest_portfolio.get("coverage", {})
    if coverage.get("gaps"):
        lines.append(f"- Exploration debt: {', '.join(coverage['gaps'])}")
    lines.extend(["", "## Mechanism memory"])
    if state["mechanism_beliefs"]:
        for mechanism, belief in sorted(state["mechanism_beliefs"].items()):
            lines.append(
                f"- {mechanism} [{belief['family']}]: +{belief['positive']} / -{belief['negative']} / mixed {belief['mixed']}; "
                f"latest effect {belief['latest_effect_fraction']}; latest prediction error "
                f"{belief['latest_prediction_error_fraction']}"
            )
    else:
        lines.append("- No valid scientific outcomes yet.")
    legacy = state.get("legacy", {})
    if legacy.get("event_count"):
        lines.extend(["", "## Imported campaign guardrails"])
        lines.append(
            f"- Imported {legacy['event_count']} source events; campaign decision "
            f"`{legacy.get('campaign_decision') or 'unknown'}`; lineage decision "
            f"`{legacy.get('lineage_decision') or 'unknown'}`."
        )
        lines.append(
            f"- Last experiment: `{legacy.get('last_experiment_id') or 'unknown'}`; "
            f"imported claims permitted: `{legacy.get('claims_permitted')}`."
        )
        lines.append(
            f"- Imported cumulative spend: ${legacy.get('cumulative_spend_usd', 0.0):.6f}. "
            "Do not repeat a stopped lineage without new scope-matched evidence and an explicit revisit reason."
        )
    return "\n".join(lines) + "\n"
