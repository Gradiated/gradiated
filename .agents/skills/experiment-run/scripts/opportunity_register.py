#!/usr/bin/env python3
"""Validate and rank a compact measurement-driven opportunity register."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED = {
    "id",
    "observation",
    "evidence_scope",
    "competing_explanations",
    "mechanism",
    "falsifier",
    "next_measurement",
    "cost_usd",
    "decision_impact",
    "uncertainty",
    "discrimination_power",
    "readiness",
    "transfer_penalty",
}


def canonical_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Return the compact ranking view while preserving rich campaign records."""
    if REQUIRED <= entry.keys():
        return entry
    observation = entry.get("observation")
    interpretation = entry.get("bottleneck_interpretation")
    candidate = entry.get("candidate")
    next_measurement = entry.get("next_measurement")
    information_value = entry.get("information_value")
    ranking_inputs = entry.get("ranking_inputs")
    if not all(isinstance(value, dict) for value in (
        observation, interpretation, candidate, next_measurement, information_value, ranking_inputs
    )):
        return entry
    return {
        "id": entry.get("id"),
        "observation": observation.get("summary"),
        "evidence_scope": observation.get("evidence_scope"),
        "competing_explanations": interpretation.get("competing_explanations"),
        "mechanism": candidate.get("intervention"),
        "falsifier": entry.get("falsifier"),
        "next_measurement": next_measurement.get("experiment"),
        "cost_usd": information_value.get("estimated_cost_usd"),
        **ranking_inputs,
    }


def validate_entry(entry: dict[str, Any]) -> list[str]:
    entry = canonical_entry(entry)
    errors = []
    missing = sorted(REQUIRED - entry.keys())
    if missing:
        errors.append(f"{entry.get('id', '<unknown>')}: missing {', '.join(missing)}")
    if not isinstance(entry.get("competing_explanations"), list) or not entry.get("competing_explanations"):
        errors.append(f"{entry.get('id', '<unknown>')}: competing_explanations must be nonempty")
    for field in ("decision_impact", "uncertainty", "discrimination_power", "readiness", "transfer_penalty"):
        value = entry.get(field)
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            errors.append(f"{entry.get('id', '<unknown>')}: {field} must be in [0,1]")
    cost = entry.get("cost_usd")
    if not isinstance(cost, (int, float)) or cost < 0:
        errors.append(f"{entry.get('id', '<unknown>')}: cost_usd must be nonnegative")
    return errors


def score(entry: dict[str, Any]) -> float:
    """Heuristic decision-resolution score; never an effect-size prediction."""
    entry = canonical_entry(entry)
    numerator = (
        float(entry["decision_impact"])
        * float(entry["uncertainty"])
        * float(entry["discrimination_power"])
        * float(entry["readiness"])
        * (1.0 - float(entry["transfer_penalty"]))
    )
    return numerator / max(float(entry["cost_usd"]), 0.01)


def ranked_document(value: dict[str, Any]) -> dict[str, Any]:
    entries = value.get("opportunities")
    if not isinstance(entries, list) or not entries:
        raise ValueError("opportunities must be a nonempty list")
    errors = [error for entry in entries for error in validate_entry(entry)]
    if errors:
        raise ValueError("; ".join(errors))
    ranked = sorted(
        ({**entry, "decision_resolution_per_dollar": score(entry)} for entry in entries),
        key=lambda entry: (-entry["decision_resolution_per_dollar"], entry["id"]),
    )
    return {
        **{key: item for key, item in value.items() if key != "opportunities"},
        "ranking_method": {
            "name": "heuristic_decision_resolution_per_dollar_v1",
            "formula": "impact*uncertainty*discrimination*readiness*(1-transfer_penalty)/cost_usd",
            "claim_limit": "triage heuristic only; inputs are judgments and score is not a performance prediction",
        },
        "opportunities": ranked,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = json.loads(args.input.read_text())
    result = ranked_document(value)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
