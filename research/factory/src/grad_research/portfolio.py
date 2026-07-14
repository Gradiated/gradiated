from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from .records import FIDELITIES
from .util import (
    ValidationError,
    require_id,
    require_number,
    require_probability,
    require_string_list,
    require_text,
)


SLOTS = {"bottleneck_adjacent", "cross_stack", "model_architecture", "adversarial"}
DEFAULT_QUOTAS = {
    "bottleneck_adjacent": 2,
    "cross_stack": 1,
    "model_architecture": 1,
    "adversarial": 1,
}


def validate_scout(card: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "id",
        "cycle",
        "observation_ids",
        "slot",
        "family",
        "origin",
        "mechanism",
        "change",
        "competing_explanations",
        "falsifier",
        "next_fidelity",
        "plausible_end_to_end_ceiling_fraction",
        "estimated_cost_usd",
        "estimated_minutes",
        "decision_impact",
        "uncertainty",
        "discrimination_power",
        "readiness",
        "transfer_penalty",
        "setup_key",
        "novelty_key",
        "quality_risks",
    }
    if not isinstance(card, dict):
        raise ValidationError("scout must be an object")
    missing = sorted(required - card.keys())
    if missing:
        raise ValidationError(f"scout missing required fields: {', '.join(missing)}")
    if card["schema_version"] != 1:
        raise ValidationError("scout schema_version must be 1")
    require_id("scout.id", card["id"])
    if type(card["cycle"]) is not int or card["cycle"] < 1:
        raise ValidationError("scout.cycle must be a positive integer")
    require_string_list("scout.observation_ids", card["observation_ids"])
    if card["slot"] not in SLOTS:
        raise ValidationError("scout.slot is unsupported")
    for field in ("family", "origin", "mechanism", "change", "falsifier", "setup_key", "novelty_key"):
        require_text(f"scout.{field}", card[field])
    require_string_list("scout.competing_explanations", card["competing_explanations"])
    require_string_list("scout.quality_risks", card["quality_risks"], nonempty=False)
    if card["next_fidelity"] not in FIDELITIES:
        raise ValidationError("scout.next_fidelity is unsupported")
    ceiling = card["plausible_end_to_end_ceiling_fraction"]
    if ceiling != "unknown" and ceiling is not None:
        require_number("scout.plausible_end_to_end_ceiling_fraction", ceiling, nonnegative=True)
    require_number("scout.estimated_cost_usd", card["estimated_cost_usd"], nonnegative=True)
    if type(card["estimated_minutes"]) is not int or card["estimated_minutes"] <= 0:
        raise ValidationError("scout.estimated_minutes must be a positive integer")
    for field in ("decision_impact", "uncertainty", "discrimination_power", "readiness", "transfer_penalty"):
        require_probability(f"scout.{field}", card[field])
    if "revisit_reason" in card:
        require_text("scout.revisit_reason", card["revisit_reason"])
    return card


def decision_value_per_dollar(card: dict[str, Any]) -> float:
    validate_scout(card)
    numerator = (
        float(card["decision_impact"])
        * float(card["uncertainty"])
        * float(card["discrimination_power"])
        * float(card["readiness"])
        * (1.0 - float(card["transfer_penalty"]))
    )
    return numerator / max(float(card["estimated_cost_usd"]), 0.01)


def _rank(card: dict[str, Any], seen_origins: set[str]) -> tuple[float, float, str]:
    origin_bonus = 0.05 if card["origin"] not in seen_origins else 0.0
    return (decision_value_per_dollar(card) + origin_bonus, bool(card.get("revisit_reason")), card["id"])


def select_portfolio(
    cards: Iterable[dict[str, Any]],
    *,
    max_size: int = 5,
    previous_novelty_keys: set[str] | None = None,
    max_per_family: int = 2,
    minimum_origins: int = 3,
) -> dict[str, Any]:
    if max_size <= 0:
        raise ValidationError("max_size must be positive")
    previous = previous_novelty_keys or set()
    deduplicated: dict[str, dict[str, Any]] = {}
    for original in cards:
        card = dict(validate_scout(original))
        if card["novelty_key"] in previous and not card.get("revisit_reason"):
            continue
        key = card["novelty_key"]
        current = deduplicated.get(key)
        if current is None or _rank(card, set()) > _rank(current, set()):
            deduplicated[key] = card

    available = list(deduplicated.values())
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    family_counts: Counter[str] = Counter()
    seen_origins: set[str] = set()

    def choose(slot: str) -> dict[str, Any] | None:
        candidates = [
            card
            for card in available
            if card["id"] not in selected_ids
            and card["slot"] == slot
            and family_counts[card["family"]] < max_per_family
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda card: _rank(card, seen_origins))

    quotas = dict(DEFAULT_QUOTAS)
    if max_size < sum(quotas.values()):
        quotas = {slot: 0 for slot in quotas}
        for slot in ("adversarial", "model_architecture", "cross_stack", "bottleneck_adjacent"):
            if sum(quotas.values()) < max_size:
                quotas[slot] += 1

    for slot, count in quotas.items():
        for _ in range(count):
            candidate = choose(slot)
            if candidate is None:
                break
            candidate = {**candidate, "decision_value_per_dollar": decision_value_per_dollar(candidate)}
            selected.append(candidate)
            selected_ids.add(candidate["id"])
            family_counts[candidate["family"]] += 1
            seen_origins.add(candidate["origin"])

    remaining = sorted(available, key=lambda card: _rank(card, seen_origins), reverse=True)
    for card in remaining:
        if len(selected) >= max_size:
            break
        if card["id"] in selected_ids or any(item["novelty_key"] == card["novelty_key"] for item in selected):
            continue
        if family_counts[card["family"]] >= max_per_family:
            continue
        enriched = {**card, "decision_value_per_dollar": decision_value_per_dollar(card)}
        selected.append(enriched)
        selected_ids.add(card["id"])
        family_counts[card["family"]] += 1
        seen_origins.add(card["origin"])

    slot_counts = Counter(card["slot"] for card in selected)
    gaps = []
    for slot, required in quotas.items():
        if slot_counts[slot] < required:
            gaps.append(f"{slot}:{required - slot_counts[slot]}")
    if len(seen_origins) < min(minimum_origins, len(selected)):
        gaps.append(f"origins:{minimum_origins - len(seen_origins)}")
    return {
        "schema_version": 1,
        "selected": selected,
        "coverage": {
            "slot_counts": dict(sorted(slot_counts.items())),
            "family_counts": dict(sorted(family_counts.items())),
            "origins": sorted(seen_origins),
            "origin_count": len(seen_origins),
            "gaps": gaps,
            "ready": not gaps,
        },
        "ranking_method": "decision_resolution_per_dollar_with_fixed_diversity_slots_v1",
    }


def plan_setup_affine_session(
    cards: Iterable[dict[str, Any]],
    *,
    setup_cost_usd: dict[str, float],
    budget_usd: float,
    max_arms: int,
) -> dict[str, Any]:
    require_number("budget_usd", budget_usd, nonnegative=True)
    if max_arms <= 0:
        raise ValidationError("max_arms must be positive")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for original in cards:
        card = dict(validate_scout(original))
        card["decision_value_per_dollar"] = decision_value_per_dollar(card)
        groups[card["setup_key"]].append(card)

    plans = []
    for setup_key, group in groups.items():
        setup_cost = require_number(
            f"setup_cost_usd[{setup_key}]", setup_cost_usd.get(setup_key, 0.0), nonnegative=True
        )
        cost = setup_cost
        arms = []
        for card in sorted(group, key=lambda row: (-row["decision_value_per_dollar"], row["id"])):
            incremental = float(card["estimated_cost_usd"])
            if len(arms) < max_arms and cost + incremental <= budget_usd:
                arms.append(card)
                cost += incremental
        if arms:
            utility = sum(card["decision_value_per_dollar"] for card in arms)
            plans.append({
                "setup_key": setup_key,
                "setup_cost_usd": setup_cost,
                "arms": arms,
                "arms_per_setup": len(arms),
                "total_planned_cost_usd": cost,
                "utility_per_total_dollar": utility / max(cost, 0.01),
            })
    if not plans:
        raise ValidationError("no setup-affine session fits the budget")
    return max(plans, key=lambda row: (row["utility_per_total_dollar"], row["arms_per_setup"], row["setup_key"]))
