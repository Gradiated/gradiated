from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AcceleratorInventoryError(ValueError):
    pass


def _timestamp(name: str, value: Any) -> datetime:
    if not isinstance(value, str):
        raise AcceleratorInventoryError(f"{name} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AcceleratorInventoryError(f"{name} must be an RFC3339 UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise AcceleratorInventoryError(f"{name} must be UTC")
    return parsed


def _positive_number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise AcceleratorInventoryError(f"{name} must be a positive number")
    return float(value)


def _source_ids(name: str, value: Any, sources: dict[str, Any]) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(source_id, str) or source_id not in sources for source_id in value)
    ):
        raise AcceleratorInventoryError(f"{name} has missing or unknown source ids")
    return value


def _object_with_keys(name: str, value: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, dict) or any(key not in value for key in keys):
        raise AcceleratorInventoryError(f"{name} must contain: {', '.join(keys)}")
    return value


def load_accelerator_inventory(
    path: Path,
    *,
    now: datetime | None = None,
    vendor: str | None = None,
    min_memory_gb: float | None = None,
    required_format: str | None = None,
    availability: str | None = None,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise AcceleratorInventoryError(f"cannot read accelerator inventory: {error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise AcceleratorInventoryError("accelerator inventory must use schema_version 1")

    reviewed_at = _timestamp("reviewed_at_utc", value.get("reviewed_at_utc"))
    review_interval = value.get("review_interval_days")
    if isinstance(review_interval, bool) or not isinstance(review_interval, int) or not 7 <= review_interval <= 366:
        raise AcceleratorInventoryError("review_interval_days must be an integer in [7,366]")
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise AcceleratorInventoryError("now must be timezone-aware")
    age_days = (current_time.astimezone(timezone.utc) - reviewed_at).total_seconds() / 86400
    if min_memory_gb is not None and min_memory_gb < 0:
        raise AcceleratorInventoryError("min_memory_gb cannot be negative")

    sources = value.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise AcceleratorInventoryError("sources must be a nonempty object")
    for source_id, source in sources.items():
        if not isinstance(source_id, str) or not isinstance(source, dict) or not source.get("url"):
            raise AcceleratorInventoryError("each source must have a string id and URL")
        _timestamp(f"sources.{source_id}.retrieved_at_utc", source.get("retrieved_at_utc"))
        if source.get("evidence_type") not in {"official_documentation", "vendor_reported"}:
            raise AcceleratorInventoryError(f"source {source_id} has an unsupported evidence type")

    profiles = value.get("architecture_profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise AcceleratorInventoryError("architecture_profiles must be a nonempty object")
    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict) or not profile.get("vendor") or not profile.get("family"):
            raise AcceleratorInventoryError(f"architecture profile {profile_id} is incomplete")
        _object_with_keys(
            f"architecture_profiles.{profile_id}",
            profile,
            (
                "programming_target",
                "subgroup_width",
                "max_subgroups_per_unit",
                "max_blocks_per_unit",
                "register_file_per_unit_kib",
                "local_memory_per_unit_kib",
                "max_local_memory_per_block_kib",
                "combined_l1_local_kib",
                "matrix_generation",
                "architecture_features",
                "co_design_levers",
            ),
        )
        _source_ids(f"architecture_profiles.{profile_id}.source_ids", profile.get("source_ids"), sources)
        subgroup = profile.get("subgroup_width")
        if subgroup is not None:
            _positive_number(f"architecture_profiles.{profile_id}.subgroup_width", subgroup)

    rows = value.get("accelerators")
    if not isinstance(rows, list) or not rows:
        raise AcceleratorInventoryError("accelerators must be a nonempty list")
    accelerators: dict[str, Any] = {}
    vendors: dict[str, int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise AcceleratorInventoryError(f"accelerators[{index}] must have an id")
        accelerator_id = row["id"]
        if accelerator_id in accelerators:
            raise AcceleratorInventoryError(f"duplicate accelerator id: {accelerator_id}")
        profile_id = row.get("architecture_profile_id")
        if profile_id not in profiles:
            raise AcceleratorInventoryError(f"{accelerator_id} has unknown architecture profile: {profile_id}")
        source_ids = _source_ids(f"accelerators[{index}].source_ids", row.get("source_ids"), sources)
        execution = _object_with_keys(
            f"{accelerator_id}.execution",
            row.get("execution"),
            ("compute_units", "compute_unit_name", "matrix_units", "matrix_unit_name"),
        )
        if not isinstance(execution["compute_unit_name"], str) or not isinstance(execution["matrix_unit_name"], str):
            raise AcceleratorInventoryError(f"{accelerator_id} execution unit names must be strings")
        memory = _object_with_keys(
            f"{accelerator_id}.memory", row.get("memory"), ("capacity_gb", "type", "bandwidth_gb_s", "ecc")
        )
        capacity_gb = _positive_number(f"{accelerator_id}.memory.capacity_gb", memory.get("capacity_gb"))
        bandwidth_gb_s = _positive_number(f"{accelerator_id}.memory.bandwidth_gb_s", memory.get("bandwidth_gb_s"))
        _object_with_keys(f"{accelerator_id}.cache", row.get("cache"), ("last_level_mb", "on_die_sram_mb"))
        _object_with_keys(f"{accelerator_id}.interconnect", row.get("interconnect"), ("host", "peer", "topology"))
        _object_with_keys(
            f"{accelerator_id}.software", row.get("software"), ("primary", "serving", "maturity")
        )
        if not isinstance(row.get("peak_math"), dict):
            raise AcceleratorInventoryError(f"{accelerator_id}.peak_math must be an object")
        notes = row.get("co_design_notes")
        if not isinstance(notes, list) or not notes or any(not isinstance(note, str) for note in notes):
            raise AcceleratorInventoryError(f"{accelerator_id}.co_design_notes must be nonempty strings")
        for required_key in ("partitioning", "power_w", "price_inventory_id"):
            if required_key not in row:
                raise AcceleratorInventoryError(f"{accelerator_id} is missing {required_key}")
        formats = row.get("numeric_formats")
        if not isinstance(formats, list) or not formats or any(not isinstance(item, str) for item in formats):
            raise AcceleratorInventoryError(f"{accelerator_id} numeric_formats must be nonempty strings")
        row_vendor = row.get("vendor")
        if not isinstance(row_vendor, str) or row_vendor != profiles[profile_id]["vendor"]:
            raise AcceleratorInventoryError(f"{accelerator_id} vendor must match its architecture profile")
        availability_class = row.get("availability", {}).get("class")
        if availability_class not in {"broad_cloud", "specialist_cloud", "platform_cloud", "single_cloud"}:
            raise AcceleratorInventoryError(f"{accelerator_id} has invalid availability class")

        if vendor and row_vendor.casefold() != vendor.casefold():
            continue
        if min_memory_gb is not None and capacity_gb < min_memory_gb:
            continue
        if required_format and required_format.casefold() not in {item.casefold() for item in formats}:
            continue
        if availability and availability_class != availability:
            continue

        normalized = dict(row)
        normalized["source_ids"] = source_ids
        normalized["architecture_profile"] = profiles[profile_id]
        normalized["memory"] = dict(memory) | {
            "capacity_gb": capacity_gb,
            "bandwidth_gb_s": bandwidth_gb_s,
        }
        accelerators[accelerator_id] = normalized
        vendors[row_vendor] = vendors.get(row_vendor, 0) + 1

    return {
        "schema_version": 1,
        "inventory_path": str(path),
        "reviewed_at_utc": value["reviewed_at_utc"],
        "review_interval_days": review_interval,
        "age_days": round(age_days, 6),
        "current": 0 <= age_days <= review_interval,
        "scope": value.get("scope"),
        "sources": sources,
        "vendors": vendors,
        "accelerators": accelerators,
    }
