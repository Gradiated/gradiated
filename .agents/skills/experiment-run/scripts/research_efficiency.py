#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def overlap_seconds(start: datetime, end: datetime, windows: Iterable[tuple[datetime, datetime]]) -> float:
    return sum(max(0.0, (min(end, right) - max(start, left)).total_seconds()) for left, right in windows)


def union_seconds(intervals: Iterable[tuple[datetime, datetime]]) -> float:
    merged: list[list[datetime]] = []
    for start, end in sorted((start, end) for start, end in intervals if end > start):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        elif end > merged[-1][1]:
            merged[-1][1] = end
    return sum((end - start).total_seconds() for start, end in merged)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            rows.append(
                {
                    "_parse_error": {
                        "line_number": line_number,
                        "error": str(error),
                    }
                }
            )
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _active_windows(
    rows: list[dict[str, Any]], since: datetime, now: datetime
) -> list[tuple[datetime, datetime]]:
    starts: dict[str, datetime] = {}
    windows = []
    last_event = since
    for row in rows:
        timestamp = row.get("timestamp")
        if not timestamp:
            continue
        at = parse_time(timestamp)
        last_event = max(last_event, at)
        payload = row.get("payload", {})
        if row.get("type") != "event_msg" or not isinstance(payload, dict):
            continue
        kind = payload.get("type")
        turn_id = payload.get("turn_id")
        if kind == "task_started" and isinstance(turn_id, str):
            starts[turn_id] = at
        elif kind in {"task_complete", "turn_aborted"} and isinstance(turn_id, str):
            start = starts.pop(turn_id, None)
            if start is not None:
                windows.append((max(start, since), min(at, now)))
    live_end = max(last_event, now)
    windows.extend((max(start, since), min(live_end, now)) for start in starts.values())
    return [(start, end) for start, end in windows if end > start]


def analyze_rollout(path: Path, *, since: datetime, now: datetime) -> dict[str, Any]:
    rows = load_jsonl(path)
    parse_errors = [row["_parse_error"] for row in rows if "_parse_error" in row]
    windows = _active_windows(rows, since, now)
    active_seconds = union_seconds(windows)
    calls: dict[str, tuple[datetime, str]] = {}
    intervals: list[tuple[datetime, datetime, str]] = []
    counts: Counter[str] = Counter()
    context_compactions = 0
    for row in rows:
        timestamp = row.get("timestamp")
        if not timestamp:
            continue
        at = parse_time(timestamp)
        if at < since or at > now:
            continue
        payload = row.get("payload", {})
        if not isinstance(payload, dict):
            continue
        if row.get("type") == "event_msg" and payload.get("type") == "context_compacted":
            context_compactions += 1
        if row.get("type") != "response_item":
            continue
        kind = payload.get("type")
        call_id = payload.get("call_id")
        if kind in {"custom_tool_call", "function_call"} and isinstance(call_id, str):
            name = str(payload.get("name", "unknown"))
            calls[call_id] = (at, name)
            counts[name] += 1
        elif kind in {"custom_tool_call_output", "function_call_output"} and isinstance(call_id, str):
            started = calls.pop(call_id, None)
            if started is not None and at >= started[0]:
                intervals.append((started[0], at, started[1]))
    tool_intervals = []
    by_name_seconds: defaultdict[str, float] = defaultdict(float)
    for start, end, name in intervals:
        clipped_seconds = overlap_seconds(start, end, windows)
        if clipped_seconds:
            by_name_seconds[name] += clipped_seconds
            for left, right in windows:
                clipped_start, clipped_end = max(start, left), min(end, right)
                if clipped_end > clipped_start:
                    tool_intervals.append((clipped_start, clipped_end))
    tool_wait_seconds = union_seconds(tool_intervals)
    model_seconds = max(0.0, active_seconds - tool_wait_seconds)
    thread_match = re.search(r"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", path.name)
    return {
        "rollout_path": str(path),
        "thread_id": thread_match.group(1) if thread_match else None,
        "active_seconds": round(active_seconds, 3),
        "tool_wait_seconds": round(tool_wait_seconds, 3),
        "model_orchestration_seconds": round(model_seconds, 3),
        "model_orchestration_fraction": round(model_seconds / active_seconds, 4) if active_seconds else None,
        "tool_wait_fraction": round(tool_wait_seconds / active_seconds, 4) if active_seconds else None,
        "tool_calls": sum(counts.values()),
        "tool_calls_by_name": dict(sorted(counts.items())),
        "tool_wait_seconds_by_name": {
            name: round(seconds, 3) for name, seconds in sorted(by_name_seconds.items())
        },
        "context_compactions": context_compactions,
        "parse_errors": parse_errors,
        "active_windows": [{"start": iso(start), "end": iso(end)} for start, end in windows],
    }


def analyze_subagents(
    state_db: Path | None,
    parent_thread_id: str | None,
    *,
    since: datetime,
    now: datetime,
) -> dict[str, Any]:
    empty = {
        "available": False,
        "count": 0,
        "parallel_agent_seconds": 0.0,
        "longest_agent_seconds": 0.0,
        "models": {},
        "reasoning_efforts": {},
    }
    if state_db is None or parent_thread_id is None or not state_db.is_file():
        return empty
    connection = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT t.model, t.reasoning_effort, t.created_at_ms, t.updated_at_ms
            FROM thread_spawn_edges e
            JOIN threads t ON t.id = e.child_thread_id
            WHERE e.parent_thread_id = ? AND t.updated_at_ms >= ? AND t.created_at_ms <= ?
            """,
            (parent_thread_id, int(since.timestamp() * 1000), int(now.timestamp() * 1000)),
        ).fetchall()
    finally:
        connection.close()
    durations = []
    models: Counter[str] = Counter()
    efforts: Counter[str] = Counter()
    for row in rows:
        start = max(datetime.fromtimestamp(row["created_at_ms"] / 1000, timezone.utc), since)
        end = min(datetime.fromtimestamp(row["updated_at_ms"] / 1000, timezone.utc), now)
        durations.append(max(0.0, (end - start).total_seconds()))
        models[row["model"] or "unknown"] += 1
        efforts[row["reasoning_effort"] or "unknown"] += 1
    return {
        "available": True,
        "count": len(rows),
        "parallel_agent_seconds": round(sum(durations), 3),
        "longest_agent_seconds": round(max(durations, default=0.0), 3),
        "models": dict(sorted(models.items())),
        "reasoning_efforts": dict(sorted(efforts.items())),
    }


def _campaign_row_time(row: dict[str, Any]) -> datetime | None:
    timestamp = row.get("timestamp") or row.get("timestamp_utc")
    return parse_time(timestamp) if isinstance(timestamp, str) else None


def _event_time(rows: list[dict[str, Any]], event: str, *, action: str | None = None) -> datetime | None:
    for row in rows:
        if row.get("event") == event and (action is None or row.get("action") == action):
            timestamp = _campaign_row_time(row)
            if timestamp is not None:
                return timestamp
    return None


def _allocation_event_paths(campaign_dir: Path) -> list[Path]:
    roots = [campaign_dir / "allocations"]
    if campaign_dir.name == "campaign_100":
        roots.append(campaign_dir.parent / "research_lab" / "projects")
    if campaign_dir.name == "research_lab":
        roots.append(campaign_dir / "projects")
    roots.extend([campaign_dir / "research_lab" / "projects", campaign_dir / "projects"])
    paths = set()
    for root in roots:
        if root.is_dir():
            paths.update(root.rglob("events.jsonl"))
    return sorted(paths)


def _phase_durations(events: list[dict[str, Any]]) -> tuple[dict[str, float], str | None]:
    starts: dict[str, datetime] = {}
    durations: defaultdict[str, float] = defaultdict(float)
    failed_phase = None
    for row in events:
        phase = row.get("phase")
        timestamp = row.get("timestamp")
        if not isinstance(phase, str) or not timestamp:
            continue
        if row.get("event") == "phase_started":
            starts[phase] = parse_time(timestamp)
        elif row.get("event") == "phase_finished":
            start = starts.pop(phase, None)
            if start is not None:
                durations[phase] += max(0.0, (parse_time(timestamp) - start).total_seconds())
            if row.get("outcome") == "FAIL":
                failed_phase = phase
    return ({name: round(seconds, 3) for name, seconds in sorted(durations.items())}, failed_phase)


def _allocation_result_has_harness_error(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if (key == "error" or key.endswith("_error")) and isinstance(child, dict):
                return True
            if _allocation_result_has_harness_error(child):
                return True
    elif isinstance(value, list):
        return any(_allocation_result_has_harness_error(child) for child in value)
    return False


def _profile_useful_gpu_seconds(allocation_result: Any) -> float | None:
    if not isinstance(allocation_result, dict):
        return None
    performance = allocation_result.get("performance")
    profiles = performance.get("profiles") if isinstance(performance, dict) else None
    if not isinstance(profiles, list):
        return None
    seconds = [
        float(row["wall_seconds"])
        for row in profiles
        if isinstance(row, dict) and isinstance(row.get("wall_seconds"), (int, float))
    ]
    return round(sum(seconds), 3) if seconds else None


def _typed_stage_scientific_result(summary: dict[str, Any]) -> bool:
    records = summary.get("stage_records")
    if summary.get("outcome") != "PASS" or not isinstance(records, list) or not records:
        return False
    has_rows = False
    for record in records:
        if not isinstance(record, dict) or record.get("returncode") != 0:
            return False
        terminal = record.get("terminal")
        result = terminal.get("result") if isinstance(terminal, dict) else None
        if (
            not isinstance(terminal, dict)
            or terminal.get("pass") is not True
            or not isinstance(result, dict)
            or result.get("pass") is not True
            or _allocation_result_has_harness_error(result)
        ):
            return False
        rows = result.get("rows")
        has_rows = has_rows or isinstance(rows, list) and bool(rows)
    return has_rows


def _staged_useful_gpu_seconds(summary: dict[str, Any]) -> float | None:
    records = summary.get("stage_records")
    if not isinstance(records, list):
        return None
    seconds = []
    for record in records:
        terminal = record.get("terminal") if isinstance(record, dict) else None
        result = terminal.get("result") if isinstance(terminal, dict) else None
        value = result.get("useful_gpu_seconds") if isinstance(result, dict) else None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            seconds.append(float(value))
    return round(sum(seconds), 3) if seconds else None


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    return []


def _project_rejects_allocation_scope(directory: Path) -> bool:
    if directory.parent.name != "artifacts":
        return False
    status_path = directory.parent.parent / "STATUS.json"
    if not status_path.is_file():
        return False
    status = json.loads(status_path.read_text())
    references = _strings(status.get("terminal_artifact")) + _strings(
        status.get("last_terminal_artifacts")
    )
    if not any(directory.name in reference for reference in references):
        return False
    classification = str(status.get("last_result_classification", "")).lower()
    return any(
        marker in classification
        for marker in ("claim_rejected", "scope_rejected", "generic_")
    )


def analyze_campaign(campaign_dir: Path | None, *, since: datetime, now: datetime) -> dict[str, Any]:
    allocations = []
    if campaign_dir is None:
        return {"available": False, "allocations": [], "summary": {}}
    event_paths = _allocation_event_paths(campaign_dir)
    if not event_paths:
        return {"available": True, "allocations": [], "summary": {}}
    for events_path in event_paths:
        directory = events_path.parent
        events = load_jsonl(events_path)
        parse_error_count = sum("_parse_error" in row for row in events)
        timestamped = [timestamp for row in events if (timestamp := _campaign_row_time(row))]
        if not timestamped or max(timestamped) < since or min(timestamped) > now:
            continue
        first, last = min(timestamped), min(max(timestamped), now)
        created = _event_time(events, "instance_created") or _event_time(events, "provider_created")
        ssh = _event_time(events, "ssh_ready")
        failed = _event_time(events, "experiment_error") or _event_time(events, "owner_error")
        cleanup_requested = _event_time(events, "factory_lifecycle", action="request-cleanup")
        cleanup_verified = _event_time(events, "cleanup_verified")
        cleanup_path = directory / "cleanup.json"
        cleanup = json.loads(cleanup_path.read_text()) if cleanup_path.is_file() else {}
        if cleanup_verified is None and cleanup.get("cleanup_pass") is True:
            verified_at = cleanup.get("verified_at_utc")
            if isinstance(verified_at, str):
                cleanup_verified = min(parse_time(verified_at), now)
        observed_end = cleanup_verified or (now if failed is None else last)
        outcome_time = failed or cleanup_requested or cleanup_verified or observed_end
        result_path = directory / "factory-result.json"
        result = json.loads(result_path.read_text()) if result_path.is_file() else {}
        failure_path = directory / "failure.json"
        failure = json.loads(failure_path.read_text()) if failure_path.is_file() else {}
        summary_path = directory / "summary.json"
        summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
        allocation_result = summary.get("allocation_result")
        outcome = result.get("outcome_class")
        if not outcome and isinstance(allocation_result, dict) and not _allocation_result_has_harness_error(allocation_result):
            outcome = "scientific_result"
        if not outcome and _typed_stage_scientific_result(summary):
            outcome = "scientific_result"
        if outcome == "scientific_result" and _project_rejects_allocation_scope(directory):
            outcome = "scope_rejected_result"
        if not outcome and failure:
            outcome = "operational_failure"
        outcome = outcome or summary.get("outcome") or "in_progress"
        cost = summary.get("cost_usd_derived", result.get("cost_usd", 0.0))
        useful_gpu_seconds = summary.get("useful_gpu_seconds")
        useful_gpu_source = "summary"
        if useful_gpu_seconds is None:
            useful_gpu_seconds = _staged_useful_gpu_seconds(summary)
            useful_gpu_source = (
                "stage_records[].terminal.result.useful_gpu_seconds"
                if useful_gpu_seconds is not None
                else None
            )
        if useful_gpu_seconds is None:
            useful_gpu_seconds = _profile_useful_gpu_seconds(allocation_result)
            useful_gpu_source = "allocation_result.performance.profiles" if useful_gpu_seconds is not None else None
        phase_seconds, failed_phase = _phase_durations(events)
        if failed_phase is None and failure:
            failed_phase = "provider_create" if created is None else "ssh_readiness" if ssh is None else "runtime_bootstrap"
        setup_seconds = sum(
            phase_seconds.get(name, 0.0)
            for name in ("provider_create", "ssh_readiness", "runtime_bootstrap", "checkpoint_transfer")
        )
        try:
            allocation_id = str(directory.relative_to(campaign_dir))
        except ValueError:
            allocation_id = str(directory)
        allocations.append(
            {
                "allocation_id": allocation_id,
                "start": iso(first),
                "end": iso(observed_end),
                "completed": cleanup_verified is not None,
                "outcome": outcome,
                "failure_class": result.get("failure_class") or failure.get("error_type"),
                "cost_usd": round(float(cost or 0.0), 9),
                "provider_active_seconds": round((observed_end - first).total_seconds(), 3),
                "provisioning_seconds": round((created - first).total_seconds(), 3) if created else None,
                "ssh_ready_seconds": round((ssh - created).total_seconds(), 3) if created and ssh else None,
                "remote_execution_seconds": round((outcome_time - ssh).total_seconds(), 3) if ssh else None,
                "cleanup_seconds": (
                    round((cleanup_verified - cleanup_requested).total_seconds(), 3)
                    if cleanup_requested and cleanup_verified
                    else cleanup.get("cleanup_elapsed_seconds")
                ),
                "useful_gpu_seconds": useful_gpu_seconds,
                "useful_gpu_seconds_source": useful_gpu_source,
                "useful_gpu_to_provider_fraction": (
                    round(float(useful_gpu_seconds) / (observed_end - first).total_seconds(), 4)
                    if useful_gpu_seconds is not None and observed_end > first
                    else None
                ),
                "phase_seconds": phase_seconds,
                "setup_phase_seconds": round(setup_seconds, 3),
                "failed_phase": failed_phase,
                "event_parse_errors": parse_error_count,
            }
        )
    completed = [row for row in allocations if row["completed"]]
    scientific = [row for row in completed if str(row["outcome"]).startswith("scientific_")]
    invalid = [row for row in completed if not str(row["outcome"]).startswith("scientific_")]
    total_cost = sum(row["cost_usd"] for row in completed)
    invalid_cost = sum(row["cost_usd"] for row in invalid)
    provider_seconds = sum(row["provider_active_seconds"] for row in completed)
    useful_values = [
        float(row["useful_gpu_seconds"])
        for row in scientific
        if row["useful_gpu_seconds"] is not None
    ]
    aggregate_phases: defaultdict[str, float] = defaultdict(float)
    for row in completed:
        for name, seconds in row["phase_seconds"].items():
            aggregate_phases[name] += seconds
    pre_science_failures = [
        row
        for row in completed
        if row["failed_phase"] in {"provider_create", "ssh_readiness", "runtime_bootstrap", "checkpoint_transfer"}
    ]
    return {
        "available": True,
        "campaign_dir": str(campaign_dir),
        "allocations": allocations,
        "summary": {
            "completed_allocations": len(completed),
            "scientific_outcomes": len(scientific),
            "invalid_or_operational_outcomes": len(invalid),
            "total_cost_usd": round(total_cost, 9),
            "invalid_or_operational_cost_usd": round(invalid_cost, 9),
            "invalid_spend_fraction": round(invalid_cost / total_cost, 4) if total_cost else None,
            "provider_active_seconds": round(provider_seconds, 3),
            "useful_gpu_seconds_observed": round(sum(useful_values), 3),
            "useful_gpu_to_provider_fraction": (
                round(sum(useful_values) / provider_seconds, 4) if provider_seconds else None
            ),
            "allocations_missing_useful_gpu_timing": sum(
                row["useful_gpu_seconds"] is None for row in completed
            ),
            "phase_seconds": {
                name: round(seconds, 3) for name, seconds in sorted(aggregate_phases.items())
            },
            "pre_science_failure_count": len(pre_science_failures),
            "pre_science_failure_provider_seconds": round(
                sum(row["provider_active_seconds"] for row in pre_science_failures), 3
            ),
        },
    }


def build_report(
    rollout: Path,
    *,
    since: datetime,
    now: datetime,
    campaign_dir: Path | None = None,
    state_db: Path | None = None,
) -> dict[str, Any]:
    codex = analyze_rollout(rollout, since=since, now=now)
    subagents = analyze_subagents(
        state_db, codex["thread_id"], since=since, now=now
    )
    campaign = analyze_campaign(campaign_dir, since=since, now=now)
    active_hours = codex["active_seconds"] / 3600
    campaign_summary = campaign["summary"]
    recommendations = []
    if (codex["model_orchestration_fraction"] or 0) >= 0.5:
        recommendations.append("batch mechanical operations and reserve high reasoning for scientific gates")
    high_agents = subagents["reasoning_efforts"].get("high", 0) + subagents["reasoning_efforts"].get("max", 0)
    if high_agents > 1:
        recommendations.append("route routine subagents to a faster model or lower reasoning effort")
    if campaign_summary.get("invalid_or_operational_outcomes", 0):
        recommendations.append("prebuild and locally validate the provider image before another paid allocation")
    if campaign_summary.get("pre_science_failure_count", 0) >= 2:
        recommendations.append("stop project-local lifecycle repair and reuse the last transport that produced a valid model result")
    if campaign_summary.get("allocations_missing_useful_gpu_timing", 0):
        recommendations.append("emit useful_gpu_seconds from model-transfer start through the final scored arm")
    if (
        campaign_summary.get("scientific_outcomes", 0)
        and (campaign_summary.get("useful_gpu_to_provider_fraction") or 0) < 0.01
    ):
        recommendations.append("queue compatible decision-bearing arms in one retained allocation to amortize immutable setup")
    primary = (
        "model_orchestration"
        if (codex["model_orchestration_fraction"] or 0) >= 0.5
        else "tool_or_external_wait"
    )
    completed = campaign_summary.get("completed_allocations", 0)
    scientific = campaign_summary.get("scientific_outcomes", 0)
    return {
        "schema_version": 1,
        "generated_at": iso(now),
        "window": {"since": iso(since), "until": iso(now)},
        "codex": codex,
        "subagents": subagents,
        "campaign": campaign,
        "efficiency": {
            "primary_bottleneck": primary,
            "completed_allocations_per_active_hour": round(completed / active_hours, 4) if active_hours else None,
            "scientific_outcomes_per_active_hour": round(scientific / active_hours, 4) if active_hours else None,
            "tool_calls_per_active_hour": round(codex["tool_calls"] / active_hours, 2) if active_hours else None,
            "recommendations": recommendations,
        },
        "limitations": [
            "model_orchestration is the residual active-turn time outside synchronous tool calls; it includes model inference, reasoning, response construction, and context compaction",
            "provider activity can overlap Codex work and is reported separately rather than forced into the active-turn partition",
            "useful GPU utilization requires the experiment harness to emit useful_gpu_seconds",
            "malformed live JSONL records are excluded and listed under parse_errors",
        ],
    }


def markdown(report: dict[str, Any]) -> str:
    codex = report["codex"]
    campaign = report["campaign"]["summary"]
    efficiency = report["efficiency"]
    lines = [
        f"# Research efficiency — {report['generated_at'][:10]}",
        "",
        f"Window: `{report['window']['since']}` to `{report['window']['until']}`.",
        "",
        f"Primary bottleneck: **{efficiency['primary_bottleneck']}**.",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Active coordinator hours | {codex['active_seconds'] / 3600:.2f} |",
        f"| Model/orchestration share | {(codex['model_orchestration_fraction'] or 0) * 100:.1f}% |",
        f"| Synchronous tool-wait share | {(codex['tool_wait_fraction'] or 0) * 100:.1f}% |",
        f"| Tool calls | {codex['tool_calls']} |",
        f"| Completed allocations | {campaign.get('completed_allocations', 0)} |",
        f"| Scientific outcomes | {campaign.get('scientific_outcomes', 0)} |",
        f"| Invalid/operational spend | ${campaign.get('invalid_or_operational_cost_usd', 0):.4f} |",
        f"| Provider-active minutes | {campaign.get('provider_active_seconds', 0) / 60:.1f} |",
        f"| Useful GPU seconds observed | {campaign.get('useful_gpu_seconds_observed', 0):.1f} |",
        f"| Useful/provider time | {(campaign.get('useful_gpu_to_provider_fraction') or 0) * 100:.2f}% |",
        f"| Pre-science failures | {campaign.get('pre_science_failure_count', 0)} |",
        f"| Pre-science failure minutes | {campaign.get('pre_science_failure_provider_seconds', 0) / 60:.1f} |",
        "",
        "## Actions",
        "",
    ]
    lines.extend(f"- {item}" for item in efficiency["recommendations"] or ["no threshold-triggered action"])
    return "\n".join(lines) + "\n"


def resolve_rollout(
    rollout: Path | None, thread_id: str | None, state_db: Path
) -> Path:
    if rollout is not None:
        return rollout
    if thread_id is None:
        raise ValueError("supply --rollout or --thread-id")
    if not state_db.is_file():
        raise ValueError(f"Codex state database is absent: {state_db}")
    connection = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT rollout_path FROM threads WHERE id = ?", (thread_id,)
        ).fetchone()
    finally:
        connection.close()
    if row is None or not row[0]:
        raise ValueError(f"Codex thread is absent or has no rollout: {thread_id}")
    return Path(row[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure Codex research-loop and provider efficiency")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--rollout", type=Path)
    source.add_argument("--thread-id")
    parser.add_argument("--campaign-dir", type=Path)
    parser.add_argument("--state-db", type=Path, default=Path.home() / ".codex" / "state_5.sqlite")
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--now", help="RFC3339 timestamp; defaults to current UTC")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    since = now - timedelta(hours=args.hours)
    rollout = resolve_rollout(args.rollout, args.thread_id, args.state_db)
    report = build_report(
        rollout,
        since=since,
        now=now,
        campaign_dir=args.campaign_dir,
        state_db=args.state_db,
    )
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        date = now.date().isoformat()
        (args.output_dir / f"{date}.json").write_text(encoded)
        (args.output_dir / f"{date}.md").write_text(markdown(report))
        (args.output_dir / "LATEST.json").write_text(encoded)
        (args.output_dir / "LATEST.md").write_text(markdown(report))
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
