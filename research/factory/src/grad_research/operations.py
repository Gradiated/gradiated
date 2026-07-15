from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .director import ResearchDirector
from .labd import LabDatabase


def _write_json_atomic(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)
    return path


def _artifact_audit(director: ResearchDirector, state: dict[str, Any], *, deep: bool) -> dict[str, Any]:
    checked = 0
    errors = []
    references: set[str] = set()
    for observation in state["observations"].values():
        references.update(observation.get("artifact_refs", []))
    for run in state["runs"].values():
        references.update(run.get("spec", {}).get("artifact_refs", []))
        result = run.get("result", {})
        references.update(result.get("artifact_refs", []))
    for reference in sorted(references):
        try:
            director.artifacts.verify_reference(reference, deep=deep)
            checked += 1
        except Exception as error:
            errors.append({"sha256": reference, "error": str(error)})
    for run_id, run in sorted(state["runs"].items()):
        manifest_sha256 = run.get("result", {}).get("artifact_bundle_sha256")
        if manifest_sha256:
            try:
                director.artifacts.verify_bundle(manifest_sha256, deep=deep)
            except Exception as error:
                errors.append({"run_id": run_id, "manifest_sha256": manifest_sha256, "error": str(error)})
    return {"references_checked": checked, "deep": deep, "errors": errors, "pass": not errors}


def _work_packets(state: dict[str, Any]) -> list[dict[str, Any]]:
    completed_scouts = {
        run["result"]["scout_id"]
        for run in state["runs"].values()
        if run.get("status") == "completed" and run.get("result")
    }
    registered_scouts = {
        run["spec"]["scout_id"]
        for run in state["runs"].values()
        if run.get("status") in {"registered", "admitted"}
    }
    packets = []
    for cycle, portfolio in sorted(state["portfolios"].items(), key=lambda item: int(item[0])):
        for scout_id in portfolio.get("selected_ids", []):
            if scout_id in completed_scouts or scout_id in registered_scouts:
                continue
            scout = state["scouts"][scout_id]
            offline = scout["next_fidelity"] in {
                "bound",
                "analytical",
                "simulation",
                "reference",
                "reduced_replay",
            }
            packets.append(
                {
                    "schema_version": 1,
                    "packet_id": f"cycle-{cycle}:{scout_id}",
                    "cycle": int(cycle),
                    "scout_id": scout_id,
                    "lane": "parallel_offline" if offline else "serialized_setup_affine",
                    "setup_key": scout["setup_key"],
                    "mechanism": scout["mechanism"],
                    "changed_variable": scout["change"],
                    "falsifier": scout["falsifier"],
                    "fidelity": scout["next_fidelity"],
                    "timeout_seconds": scout["estimated_minutes"] * 60,
                    "max_cost_usd": scout["estimated_cost_usd"],
                    "observation_ids": scout["observation_ids"],
                    "output_contract": (
                        "register an immutable local run spec, store raw evidence, then record its typed result"
                        if offline
                        else "prepare a bound paid run spec; do not mutate the provider before fenced admission"
                    ),
                }
            )
    for run_id, run in sorted(state["runs"].items()):
        if run.get("status") == "registered":
            spec = run["spec"]
            packets.append(
                {
                    "schema_version": 1,
                    "packet_id": f"registered:{run_id}",
                    "run_id": run_id,
                    "scout_id": spec["scout_id"],
                    "lane": "parallel_offline",
                    "command": spec["command"],
                    "timeout_seconds": spec["timeout_seconds"],
                    "output_contract": "store result evidence and call record --kind result",
                }
            )
    return packets


def resume_program(
    director: ResearchDirector,
    lab: LabDatabase,
    *,
    owner: str,
    ttl_seconds: int,
    now: datetime,
    deep_artifact_audit: bool = False,
) -> dict[str, Any]:
    timestamp = now.timestamp()
    lease = lab.acquire_coordinator(
        director.program_id,
        owner,
        ttl_seconds=ttl_seconds,
        now=timestamp,
    )
    state = director.state()
    snapshot = lab.snapshot()
    allocations = [
        allocation
        for allocation in snapshot["allocations"]
        if allocation["program_id"] == director.program_id
    ]
    for allocation in allocations:
        if (
            allocation["state"] in {"active", "retained"}
            and allocation["absolute_deadline"] > timestamp
            and (allocation["owner"] != owner or allocation["lease_epoch"] != lease["epoch"])
        ):
            lab.adopt_allocation(
                allocation["allocation_id"],
                owner=owner,
                epoch=lease["epoch"],
                now=timestamp,
            )
    snapshot = lab.snapshot()
    reservations = [
        reservation
        for reservation in snapshot["reservations"]
        if reservation["program_id"] == director.program_id
    ]
    reservation_by_id = {row["reservation_id"]: row for row in reservations}
    allocations = [
        allocation
        for allocation in snapshot["allocations"]
        if allocation["program_id"] == director.program_id
    ]
    allocation_by_reservation = {row["reservation_id"]: row for row in allocations}
    actions = []
    due_ids = {row["allocation_id"] for row in lab.due_cleanup(now=timestamp)}
    for allocation in allocations:
        if allocation["allocation_id"] in due_ids:
            actions.append(
                {
                    "priority": "P0",
                    "action": "cleanup_now",
                    "allocation_id": allocation["allocation_id"],
                    "provider": allocation["provider"],
                    "provider_resource_id": allocation["provider_resource_id"],
                    "reason": "deadline, cleanup request, or owner lease requires provider deletion and two-view absence verification",
                }
            )
    for run_id, run in sorted(state["runs"].items()):
        if run.get("status") != "admitted":
            continue
        admission = run["admission"]
        reservation = reservation_by_id.get(admission["reservation_id"])
        allocation = allocation_by_reservation.get(admission["reservation_id"])
        if reservation and reservation["state"] == "settled":
            continue
        if allocation is None:
            contract = run["spec"]["provider_contract"]
            actions.append(
                {
                    "priority": "P0" if reservation and reservation["expires_at"] <= timestamp else "P1",
                    "action": "reconcile_provider_intent",
                    "run_id": run_id,
                    "provider": contract["provider"],
                    "idempotency_key": contract["idempotency_key"],
                    "resource_tags": contract["resource_tags"],
                    "then": (
                        "delete any matching resource and release only after verified absence"
                        if reservation and reservation["expires_at"] <= timestamp
                        else "register the matching resource or create it once with the same key and tags"
                    ),
                }
            )
        elif allocation["state"] in {"active", "retained"} and allocation["allocation_id"] not in due_ids:
            actions.append(
                {
                    "priority": "P1",
                    "action": "continue_admitted_run",
                    "run_id": run_id,
                    "allocation_id": allocation["allocation_id"],
                    "absolute_deadline": allocation["absolute_deadline"],
                    "resident_manifest_sha256": allocation["resident_manifest_sha256"],
                }
            )
        elif allocation["state"] == "cleaned" and reservation and reservation["state"] == "active":
            actions.append(
                {
                    "priority": "P1",
                    "action": "record_failure_or_result_then_settle",
                    "run_id": run_id,
                    "reservation_id": reservation["reservation_id"],
                }
            )
    for reservation in reservations:
        if reservation["state"] != "active":
            continue
        allocation = allocation_by_reservation.get(reservation["reservation_id"])
        if allocation and allocation["state"] == "cleaned":
            run_completed = any(
                (run.get("admission") or {}).get("reservation_id") == reservation["reservation_id"]
                and run.get("status") == "completed"
                for run in state["runs"].values()
            )
            if run_completed:
                actions.append(
                    {
                        "priority": "P1",
                        "action": "settle_cleaned_session",
                        "reservation_id": reservation["reservation_id"],
                        "requirement": "use provider-metered cost evidence already stored in the run bundle",
                    }
                )
    audit = _artifact_audit(director, state, deep=deep_artifact_audit)
    if not audit["pass"]:
        actions.insert(
            0,
            {
                "priority": "P0",
                "action": "repair_or_restore_artifact_store",
                "errors": audit["errors"],
            },
        )
    work_packets = _work_packets(state)
    if not actions and work_packets:
        actions.append(
            {
                "priority": "P1",
                "action": "dispatch_runnable_packets",
                "parallel_offline": sum(packet["lane"] == "parallel_offline" for packet in work_packets),
                "serialized_setup_affine": sum(
                    packet["lane"] == "serialized_setup_affine" for packet in work_packets
                ),
            }
        )
    director.write_state()
    director.write_coordinator_context()
    resume = {
        "schema_version": 1,
        "program_id": director.program_id,
        "event_head_sha256": state["event_head_sha256"],
        "lease": lease,
        "artifact_audit": audit,
        "actions": actions,
        "work_packets": work_packets,
        "runtime": {
            "reservations": reservations,
            "allocations": allocations,
            "budgets": [
                budget
                for budget in snapshot["budgets"]
                if budget["campaign_id"] in {row["campaign_id"] for row in reservations}
            ],
        },
        "residual_bottleneck": state["residual_bottleneck"],
        "next_action": state["next_action"],
        "safe_to_start_new_provider_mutation": audit["pass"]
        and not due_ids
        and not any(action["priority"] == "P0" for action in actions),
    }
    resume_path = _write_json_atomic(director.store.program_dir / "RESUME.json", resume)
    queue_path = _write_json_atomic(
        director.store.program_dir / "WORK_QUEUE.json",
        {"schema_version": 1, "event_head_sha256": state["event_head_sha256"], "packets": work_packets},
    )
    return {**resume, "resume_path": str(resume_path), "work_queue_path": str(queue_path)}
