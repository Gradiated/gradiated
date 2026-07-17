from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PriceInventoryError(ValueError):
    pass


def _number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise PriceInventoryError(f"{name} must be a positive number")
    return float(value)


def _timestamp(name: str, value: Any) -> datetime:
    if not isinstance(value, str):
        raise PriceInventoryError(f"{name} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PriceInventoryError(f"{name} must be an RFC3339 UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise PriceInventoryError(f"{name} must be UTC")
    return parsed


def load_gpu_price_inventory(path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise PriceInventoryError(f"cannot read GPU price inventory: {error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise PriceInventoryError("GPU price inventory must use schema_version 1")

    refreshed_at = _timestamp("refreshed_at_utc", value.get("refreshed_at_utc"))
    interval = value.get("refresh_interval_days")
    if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= 31:
        raise PriceInventoryError("refresh_interval_days must be an integer in [1,31]")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise PriceInventoryError("now must be timezone-aware")
    age_days = (current.astimezone(timezone.utc) - refreshed_at).total_seconds() / 86400

    policy = value.get("production_pricing_policy")
    if not isinstance(policy, dict):
        raise PriceInventoryError("production_pricing_policy must be an object")
    if policy.get("capacity_type") != "committed_non_preemptible":
        raise PriceInventoryError("production pricing must use committed non-preemptible capacity")
    if policy.get("term_months") != [12, 24] or policy.get("scale_gpus") != [8, 64]:
        raise PriceInventoryError("production pricing policy must bind the 12-24 month, 8-64 GPU base case")

    sources = value.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise PriceInventoryError("sources must be a nonempty object")
    for source_id, source in sources.items():
        if not isinstance(source_id, str) or not isinstance(source, dict):
            raise PriceInventoryError("each source must have a string id and object value")
        if not source.get("url") and not source.get("repository_path"):
            raise PriceInventoryError(f"source {source_id} must have a URL or repository path")
        _timestamp(f"sources.{source_id}.retrieved_at_utc", source.get("retrieved_at_utc"))

    rows = value.get("accelerators")
    if not isinstance(rows, list) or not rows:
        raise PriceInventoryError("accelerators must be a nonempty list")
    accelerators: dict[str, Any] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise PriceInventoryError(f"accelerators[{index}] must have an id")
        accelerator_id = row["id"]
        if accelerator_id in accelerators:
            raise PriceInventoryError(f"duplicate accelerator id: {accelerator_id}")
        planning = _number(
            f"accelerators[{index}].production_planning_usd_per_gpu_hour",
            row.get("production_planning_usd_per_gpu_hour"),
        )
        evidence_range = row.get("production_evidence_range_usd_per_gpu_hour")
        if not isinstance(evidence_range, list) or len(evidence_range) != 2:
            raise PriceInventoryError(f"accelerators[{index}] must have a two-value production evidence range")
        lower = _number(f"accelerators[{index}].production_evidence_range[0]", evidence_range[0])
        upper = _number(f"accelerators[{index}].production_evidence_range[1]", evidence_range[1])
        if lower > upper or not lower <= planning <= upper:
            raise PriceInventoryError(f"{accelerator_id} production planning rate must be inside its evidence range")
        source_ids = row.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids or any(source_id not in sources for source_id in source_ids):
            raise PriceInventoryError(f"{accelerator_id} has missing or unknown source ids")
        node_gpus = row.get("default_node_gpus")
        if isinstance(node_gpus, bool) or not isinstance(node_gpus, int) or node_gpus <= 0:
            raise PriceInventoryError(f"{accelerator_id} default_node_gpus must be positive")
        normalized = dict(row)
        normalized["production_planning_usd_per_gpu_hour"] = planning
        normalized["production_evidence_range_usd_per_gpu_hour"] = [lower, upper]
        normalized["production_planning_usd_per_default_node_hour"] = round(planning * node_gpus, 6)
        accelerators[accelerator_id] = normalized

    return {
        "schema_version": 1,
        "inventory_path": str(path),
        "refreshed_at_utc": value["refreshed_at_utc"],
        "refresh_interval_days": interval,
        "age_days": round(age_days, 6),
        "fresh": 0 <= age_days <= interval,
        "production_pricing_policy": policy,
        "sources": sources,
        "accelerators": accelerators,
    }
