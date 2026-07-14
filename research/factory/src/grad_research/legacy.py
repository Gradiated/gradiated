from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .events import EventStore
from .util import ValidationError, content_hash, file_hash


HARNESS_MARKERS = (
    "harness",
    "orchestration",
    "oracle_invalidation",
    "observer_failure",
    "quality_observer",
    "wrong_tokenizer",
    "input_identity",
    "manifest_identity",
    "transport_schema",
    "parser_failure",
    "permission_failure",
)
OPERATIONAL_MARKERS = (
    "capacity_failure",
    "placement_failure",
    "provider_500",
    "download_failure",
    "http_401",
    "cuda_driver_runtime",
    "runtime_placement",
    "stock_unavailable",
    "allocation_failure",
    "cold_jit_runtime_timeout",
)
NEGATIVE_MARKERS = (
    "rejected",
    "regression",
    "falsified",
    "below_gate",
    "infeasible",
    "lineage_decision_stop",
    "split8_decision_stop",
    "semantic_smoke_falsified",
)
POSITIVE_MARKERS = (
    "component_lead",
    "small_gain",
    "quality_and_fixed_slo_pass",
    "paired_quality_and_fixed_slo_pass",
    "scientific_positive",
)
CUMULATIVE_SPEND_KEYS = (
    "campaign_conservative_spend_usd",
    "campaign_spend_usd_derived",
    "nebius_reconstructed_spend_usd",
    "nebius_provisional_spend_usd",
    "campaign_additional_spend_usd",
)


def _text(row: dict[str, Any]) -> str:
    fields = [
        row.get("event"),
        row.get("classification"),
        row.get("failure"),
        row.get("hypothesis_result"),
        row.get("decision"),
        row.get("split8_decision"),
        row.get("campaign_decision"),
    ]
    return " ".join(str(value).lower() for value in fields if value is not None)


def classify_legacy_event(row: dict[str, Any]) -> str:
    text = _text(row)
    classification = str(row.get("classification", "")).lower()
    if classification.startswith("valid_") and "failure" in text:
        return "scientific_mixed"
    if any(marker in text for marker in HARNESS_MARKERS):
        return "harness_invalid"
    if any(marker in text for marker in OPERATIONAL_MARKERS):
        return "operational_failure"
    if any(marker in text for marker in NEGATIVE_MARKERS) or row.get("split8_decision") == "STOP":
        return "scientific_negative"
    if any(marker in text for marker in POSITIVE_MARKERS):
        return "scientific_positive"
    return "unclassified"


def cumulative_spend(row: dict[str, Any]) -> float | None:
    values = []
    for key in CUMULATIVE_SPEND_KEYS:
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return max(values) if values else None


def replay_legacy_ledger(path: str | Path, store: EventStore) -> dict[str, Any]:
    ledger = Path(path)
    source_path = str(ledger.resolve())
    source_id = ledger.name
    source_sha256 = file_hash(ledger)
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    existing_rows = {
        event["payload"]["line_number"]: event["payload"]
        for event in store.load()
        if event["event_type"] == "legacy_event_imported"
    }
    existing_sources = {
        payload.get("source_id") or Path(payload.get("source_path", "unknown")).name
        for payload in existing_rows.values()
    }
    if existing_sources and existing_sources != {source_id}:
        raise ValidationError("a program may replay only one canonical legacy ledger")
    if existing_rows and max(existing_rows) > len(rows):
        raise ValidationError("legacy ledger was truncated after import")
    additions = []
    counts: dict[str, int] = {}
    maximum_spend = 0.0
    for line_number, row in enumerate(rows, start=1):
        outcome = classify_legacy_event(row)
        counts[outcome] = counts.get(outcome, 0) + 1
        spend = cumulative_spend(row)
        if spend is not None:
            maximum_spend = max(maximum_spend, spend)
        raw_sha256 = content_hash(row)
        if line_number in existing_rows:
            if existing_rows[line_number].get("raw_sha256") != raw_sha256:
                raise ValidationError(f"legacy ledger line {line_number} changed after import")
            continue
        payload = {
            "schema_version": 1,
            "source_id": source_id,
            "source_path": source_path,
            "source_sha256": source_sha256,
            "line_number": line_number,
            "raw_sha256": raw_sha256,
            "legacy_event": row.get("event", f"line-{line_number}"),
            "outcome_class": outcome,
            "cumulative_spend_usd": spend,
            "raw": row,
        }
        additions.append(("legacy_event_imported", payload, row.get("timestamp")))
    store.append_many(additions)
    return {
        "schema_version": 1,
        "source_sha256": source_sha256,
        "source_event_count": len(rows),
        "events_appended": len(additions),
        "outcome_counts": counts,
        "cumulative_spend_usd": maximum_spend,
    }


def import_legacy_campaign(
    ledger_path: str | Path,
    status_path: str | Path,
    decision_path: str | Path,
    store: EventStore,
) -> dict[str, Any]:
    summary = replay_legacy_ledger(ledger_path, store)
    status_path = Path(status_path)
    decision_path = Path(decision_path)
    status = json.loads(status_path.read_text())
    decision = json.loads(decision_path.read_text())
    snapshot_identity = {
        "status_sha256": file_hash(status_path),
        "decision_sha256": file_hash(decision_path),
    }
    snapshot_sha256 = content_hash(snapshot_identity)
    already_present = any(
        event["event_type"] == "legacy_campaign_snapshot_imported"
        and event["payload"].get("snapshot_sha256") == snapshot_sha256
        for event in store.load()
    )
    if not already_present:
        nebius_budget = status.get("nebius_budget", {})
        payload = {
            "schema_version": 1,
            "snapshot_sha256": snapshot_sha256,
            **snapshot_identity,
            "campaign_decision": decision.get("campaign_decision", status.get("decision")),
            "lineage_decision": decision.get("lineage_decision"),
            "phase": status.get("current_phase"),
            "active_experiment_id": status.get("active_experiment_id"),
            "last_experiment_id": status.get("last_experiment_id"),
            "claims_permitted": status.get("claims_permitted"),
            "residual_bottleneck": decision.get("residual_bottleneck", status.get("active_hypothesis")),
            "next_action": status.get("next_action") or (decision.get("next_actions_ranked") or [None])[0],
            "budgets": {
                "nebius": {
                    "authorized_usd": nebius_budget.get("authorized_usd"),
                    "spent_usd": nebius_budget.get("conservative_spend_usd"),
                    "unspent_usd": nebius_budget.get("unspent_usd"),
                },
                "overall": {
                    "authorized_usd": status.get("campaign_cap_usd"),
                    "spent_usd": status.get("campaign_additional_spend_usd"),
                    "unspent_usd": status.get("unspent_authorization_usd"),
                },
            },
            "cleanup": {
                "active_pods": status.get("active_pod_inventory"),
                "instance_and_disk_zero_verified_at": status.get("zero_active_nebius_instances_and_disks_verified_at"),
                "final_decision_cleanup": decision.get("cleanup"),
            },
        }
        store.append("legacy_campaign_snapshot_imported", payload)
    return {**summary, "snapshot_sha256": snapshot_sha256, "snapshot_appended": not already_present}
