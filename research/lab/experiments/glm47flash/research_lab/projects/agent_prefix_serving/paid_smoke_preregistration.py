#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

from v2_replay_contract import PROJECT


RATE_USD_PER_HOUR = 0.8581222
CLEANUP_RESERVE_USD = 0.07
ALLOCATION_SECONDS = 2700
ALLOCATION_CAP_USD = 0.75


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def paths():
    artifacts = PROJECT / "artifacts"
    return {
        "v2_plan": artifacts / "agent_prefix_c8_v2_tenant_isolated.plan.json",
        "smoke_packet": artifacts / "V2_CACHE_ON_SMOKE_PACKET.json",
        "runner": PROJECT / "v2_cache_smoke_runner.py",
        "contract": PROJECT / "v2_replay_contract.py",
    }


def build_preregistration():
    source_paths = paths()
    phase_rows = [
        {"name": "controller_admission_and_provider_create", "seconds": 90, "gate": "durable_controller_state_and_watchdog_live_before_create"},
        {"name": "identity_and_server_readiness", "seconds": 360, "gate": "exact_V21_identities_and_cache-detail-capability"},
        {"name": "verified_awq_checkpoint_transfer", "seconds": 900, "gate": "checkpoint_transfer_hash_and_awq_manifest_complete"},
        {"name": "warmup_and_cache_reset", "seconds": 180, "gate": "three_warmups_complete_and_flush_cache_succeeds"},
        {"name": "measured_repetition_one", "seconds": 240, "gate": "cache_and_service_evidence_complete"},
        {"name": "measured_repetition_two", "seconds": 240, "gate": "semantic_digest_identity_complete"},
        {"name": "artifact_retrieval_and_hashing", "seconds": 150, "gate": "all_required_artifacts_present_and_hashed"},
        {"name": "teardown_and_inventory_reconciliation", "seconds": 540, "gate": "instance_and_disk_absent"},
    ]
    all_in = ALLOCATION_SECONDS / 3600 * RATE_USD_PER_HOUR + CLEANUP_RESERVE_USD
    return {
        "schema_version": 1,
        "experiment_id": "glm47-agent-prefix-v2-cache-on-smoke",
        "purpose": "first paid tenant-isolated cache-on evidence gate; no cache-off arm is admitted in this allocation",
        "source_identities": {name: {"path": str(path.relative_to(PROJECT)), "sha256": sha256(path)} for name, path in source_paths.items()},
        "budget": {
            "rate_usd_per_hour": RATE_USD_PER_HOUR,
            "allocation_seconds": ALLOCATION_SECONDS,
            "allocation_cap_usd": ALLOCATION_CAP_USD,
            "compute_cap_usd": ALLOCATION_SECONDS / 3600 * RATE_USD_PER_HOUR,
            "cleanup_reserve_usd": CLEANUP_RESERVE_USD,
            "all_in_cap_usd": all_in,
            "project_session_cap_usd": 1.50,
        },
        "phases": {"rows": phase_rows, "total_allocation_seconds": sum(row["seconds"] for row in phase_rows)},
        "controller_lifecycle": {
            "provider_create_gate": "durable_factory_controller_live_and_watchdog_armed",
            "required_preconditions": [
                "later director handoff names agent_prefix_serving as sole provider owner",
                "V31 teardown and fresh provider instance/disk inventory are zero",
                "factory-managed controller state file is persisted outside the Codex process group",
                "controller heartbeat is younger than 30 seconds and absolute deadline is no later than allocation_start_plus_2700_seconds",
                "independent provider cleanup watchdog is armed before instance creation and shares the allocation identity",
            ],
            "live_controller_evidence": [
                "controller-state.json with allocation identity, controller PID, start time, deadline, and heartbeat",
                "watchdog-state.json with watchdog PID, deadline, cleanup target, and heartbeat",
                "provider create event may be emitted only after both records validate and PIDs are live",
            ],
            "turn_scope_rule": "A Codex turn may observe a controller but may not own the only live provider controller, watchdog, transfer, retrieval, or cleanup process.",
            "terminal_reconciliation": [
                "controller terminated or completed with terminal result.json",
                "watchdog cancelled only after cleanup verification",
                "provider instance GET is not-found",
                "fresh named-instance and disk inventories are zero",
                "local artifacts, hashes, and cost evidence are terminal",
            ],
        },
        "stop_rules": [
            "No provider create if any lifecycle precondition is false.",
            "Stop before a cache-off arm if cache counters, per-request cached tokens, tenant salts, semantic identity, or SLO evidence is absent.",
            "Stop and tear down on any phase deadline, all-in cap, controller/watchdog heartbeat failure, or partial artifact retrieval.",
            "Do not repair an untyped paid failure in this allocation; preserve evidence and clean up.",
        ],
        "artifact_contract": [
            "preregistration and source hash manifest",
            "controller-state and watchdog-state lifecycle records",
            "provider create/inventory/cleanup evidence",
            "runner output directory and hash manifest",
            "terminal result and cost reconciliation",
        ],
    }


def validate_preregistration(value):
    if value.get("schema_version") != 1 or value.get("experiment_id") != "glm47-agent-prefix-v2-cache-on-smoke":
        raise ValueError("preregistration identity is invalid")
    budget = value.get("budget")
    if not isinstance(budget, dict) or budget.get("all_in_cap_usd", float("inf")) > ALLOCATION_CAP_USD:
        raise ValueError("all-in budget exceeds the V2 smoke cap")
    phases = value.get("phases")
    if not isinstance(phases, dict) or phases.get("total_allocation_seconds") != ALLOCATION_SECONDS:
        raise ValueError("phase budget does not bind the allocation deadline")
    if sum(row.get("seconds", 0) for row in phases.get("rows", [])) != ALLOCATION_SECONDS:
        raise ValueError("phase rows do not sum to the allocation deadline")
    if not any(row.get("name") == "verified_awq_checkpoint_transfer" for row in phases.get("rows", [])):
        raise ValueError("fresh AWQ checkpoint transfer phase is missing")
    lifecycle = value.get("controller_lifecycle")
    if not isinstance(lifecycle, dict) or lifecycle.get("provider_create_gate") != "durable_factory_controller_live_and_watchdog_armed":
        raise ValueError("provider lifecycle gate is missing")
    for name, record in value.get("source_identities", {}).items():
        path = PROJECT / record["path"]
        if not path.exists() or sha256(path) != record.get("sha256"):
            raise ValueError(f"source identity changed: {name}")
    return value


def main():
    value = validate_preregistration(build_preregistration())
    path = PROJECT / "artifacts" / "V2_CACHE_ON_PAID_PREREGISTRATION.json"
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")
    print(path)


if __name__ == "__main__":
    main()
