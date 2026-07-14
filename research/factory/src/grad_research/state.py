from __future__ import annotations

from typing import Any

from .records import DIAGNOSTIC_OUTCOMES, OUTCOME_CLASSES, SCIENTIFIC_OUTCOMES


def _initial_state(program_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "program_id": program_id,
        "event_count": 0,
        "event_head_sha256": None,
        "baseline": None,
        "baseline_history": [],
        "current_cycle": 0,
        "observations": {},
        "scouts": {},
        "portfolios": {},
        "runs": {},
        "outcome_counts": {name: 0 for name in sorted(OUTCOME_CLASSES)},
        "mechanism_beliefs": {},
        "family_summary": {},
        "residual_bottleneck": None,
        "next_action": None,
        "research_metrics": {
            "valid_scientific_outcomes": 0,
            "valid_diagnostic_outcomes": 0,
            "harness_invalid_outcomes": 0,
            "operational_failures": 0,
            "prediction_errors_scored": 0,
            "total_result_cost_usd": 0.0,
            "invalid_or_operational_cost_usd": 0.0,
        },
        "observability": {
            "admitted_runs": 0,
            "artifact_complete_runs": 0,
            "scientific_attribution_gate_passes": 0,
            "observer_effect_failures": 0,
            "captured_category_counts": {},
            "telemetry_gaps": {},
        },
        "legacy": {
            "event_count": 0,
            "source_sha256": None,
            "cumulative_spend_usd": 0.0,
            "last_event": None,
            "outcome_counts": {
                **{name: 0 for name in sorted(OUTCOME_CLASSES)},
                "unclassified": 0,
            },
            "campaign_decision": None,
            "lineage_decision": None,
            "phase": None,
            "active_experiment_id": None,
            "last_experiment_id": None,
            "claims_permitted": None,
            "residual_bottleneck": None,
            "next_action": None,
            "budgets": {},
            "cleanup": {},
        },
    }


def project_events(events: list[dict[str, Any]], program_id: str) -> dict[str, Any]:
    state = _initial_state(program_id)
    for event in events:
        payload = event["payload"]
        kind = event["event_type"]
        state["event_count"] += 1
        state["event_head_sha256"] = event["event_hash"]
        if kind == "baseline_frozen":
            state["baseline"] = payload
        elif kind == "baseline_refreshed":
            if state["baseline"] is not None:
                state["baseline_history"].append({
                    "baseline": state["baseline"],
                    "replaced_reason": payload["reason"],
                })
            state["baseline"] = payload["baseline"]
        elif kind == "observation_recorded":
            state["observations"][payload["id"]] = payload
            state["current_cycle"] = max(state["current_cycle"], payload["cycle"])
            gaps = sorted(gap["signal"] for gap in payload.get("instrumentation_gaps", []))
            if gaps:
                state["observability"]["telemetry_gaps"][f"observation:{payload['id']}"] = gaps
        elif kind == "scout_proposed":
            state["scouts"][payload["id"]] = payload
            state["current_cycle"] = max(state["current_cycle"], payload["cycle"])
        elif kind == "portfolio_selected":
            state["portfolios"][str(payload["cycle"])] = payload
            state["current_cycle"] = max(state["current_cycle"], payload["cycle"])
        elif kind == "run_registered":
            state["runs"][payload["spec"]["run_id"]] = {
                "status": "registered",
                "spec": payload["spec"],
                "admission": None,
            }
        elif kind == "run_admitted":
            state["runs"][payload["spec"]["run_id"]] = {
                "status": "admitted",
                "spec": payload["spec"],
                "admission": payload["admission"],
            }
            observability = state["observability"]
            observability["admitted_runs"] += 1
            contract = payload["spec"].get("telemetry_contract", {})
            gaps = []
            for signal in contract.get("signals", []):
                if signal.get("status") == "capture":
                    category = signal.get("category", "unknown")
                    counts = observability["captured_category_counts"]
                    counts[category] = counts.get(category, 0) + 1
                elif signal.get("status") == "unavailable":
                    gaps.append(signal.get("name", "unknown"))
            if gaps:
                observability["telemetry_gaps"][payload["spec"]["run_id"]] = sorted(gaps)
        elif kind == "run_completed":
            result = payload
            run = state["runs"].setdefault(result["run_id"], {})
            run.update({"status": "completed", "result": result})
            outcome = result["outcome_class"]
            state["outcome_counts"][outcome] += 1
            cost = float(result["cost_usd"])
            state["research_metrics"]["total_result_cost_usd"] += cost
            state["next_action"] = result["next_action"]
            observability = state["observability"]
            if result.get("artifact_bundle_sha256"):
                observability["artifact_complete_runs"] += 1
            telemetry = result.get("telemetry_summary", {})
            if telemetry:
                gaps = sorted(
                    set(telemetry.get("unavailable_signals", []))
                    | set(telemetry.get("missing_signals", []))
                )
                if gaps:
                    observability["telemetry_gaps"][result["run_id"]] = gaps
                else:
                    observability["telemetry_gaps"].pop(result["run_id"], None)
                if telemetry.get("observer_effect", {}).get("status") == "failed":
                    observability["observer_effect_failures"] += 1
            if outcome in SCIENTIFIC_OUTCOMES:
                state["research_metrics"]["valid_scientific_outcomes"] += 1
                state["research_metrics"]["prediction_errors_scored"] += 1
                scout = state["scouts"].get(result["scout_id"], {})
                family = scout.get("family", "unknown")
                mechanism_key = scout.get("novelty_key", result["scout_id"])
                belief = state["mechanism_beliefs"].setdefault(
                    mechanism_key,
                    {
                        "family": family,
                        "valid_outcomes": 0,
                        "positive": 0,
                        "negative": 0,
                        "mixed": 0,
                        "latest_effect_fraction": None,
                        "latest_prediction_error_fraction": None,
                        "latest_scout_id": None,
                    },
                )
                belief["valid_outcomes"] += 1
                belief[outcome.removeprefix("scientific_")] += 1
                observed = float(result["observed_effect_fraction"])
                predicted = float(result["predicted_effect_fraction"])
                belief["latest_effect_fraction"] = observed
                belief["latest_prediction_error_fraction"] = observed - predicted
                belief["latest_scout_id"] = result["scout_id"]
                family_belief = state["family_summary"].setdefault(
                    family, {"valid_outcomes": 0, "positive": 0, "negative": 0, "mixed": 0}
                )
                family_belief["valid_outcomes"] += 1
                family_belief[outcome.removeprefix("scientific_")] += 1
                state["residual_bottleneck"] = result["residual_bottleneck"]
                coverage = telemetry.get("attribution_coverage")
                if isinstance(coverage, (int, float)) and coverage >= 0.95:
                    observability["scientific_attribution_gate_passes"] += 1
            elif outcome in DIAGNOSTIC_OUTCOMES:
                state["research_metrics"]["valid_diagnostic_outcomes"] += 1
                state["residual_bottleneck"] = result["residual_bottleneck"]
            elif outcome == "harness_invalid":
                state["research_metrics"]["harness_invalid_outcomes"] += 1
                state["research_metrics"]["invalid_or_operational_cost_usd"] += cost
            elif outcome == "operational_failure":
                state["research_metrics"]["operational_failures"] += 1
                state["research_metrics"]["invalid_or_operational_cost_usd"] += cost
        elif kind == "legacy_event_imported":
            legacy = state["legacy"]
            legacy["event_count"] += 1
            legacy["source_sha256"] = payload["source_sha256"]
            legacy["last_event"] = payload["legacy_event"]
            outcome = payload["outcome_class"]
            legacy["outcome_counts"][outcome] += 1
            cumulative = payload.get("cumulative_spend_usd")
            if cumulative is not None:
                legacy["cumulative_spend_usd"] = max(legacy["cumulative_spend_usd"], float(cumulative))
        elif kind == "legacy_campaign_snapshot_imported":
            legacy = state["legacy"]
            for name in (
                "campaign_decision",
                "lineage_decision",
                "phase",
                "active_experiment_id",
                "last_experiment_id",
                "claims_permitted",
                "residual_bottleneck",
                "next_action",
                "budgets",
                "cleanup",
            ):
                legacy[name] = payload.get(name)
            state["residual_bottleneck"] = payload.get("residual_bottleneck")
            state["next_action"] = payload.get("next_action")
        elif kind == "decision_recorded":
            state["next_action"] = payload.get("next_action", state["next_action"])
            if payload.get("residual_bottleneck"):
                state["residual_bottleneck"] = payload["residual_bottleneck"]

    state["research_metrics"] = {
        key: round(value, 12) if isinstance(value, float) else value
        for key, value in state["research_metrics"].items()
    }
    return state
