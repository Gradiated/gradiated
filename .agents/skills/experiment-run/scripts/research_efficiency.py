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


def _event_time(rows: list[dict[str, Any]], event: str, *, action: str | None = None) -> datetime | None:
    for row in rows:
        if row.get("event") == event and (action is None or row.get("action") == action):
            timestamp = row.get("timestamp")
            if timestamp:
                return parse_time(timestamp)
    return None


def analyze_campaign(campaign_dir: Path | None, *, since: datetime, now: datetime) -> dict[str, Any]:
    allocations = []
    if campaign_dir is None:
        return {"available": False, "allocations": [], "summary": {}}
    allocation_root = campaign_dir / "allocations"
    if not allocation_root.is_dir():
        return {"available": True, "allocations": [], "summary": {}}
    for directory in sorted(path for path in allocation_root.iterdir() if path.is_dir()):
        events_path = directory / "events.jsonl"
        if not events_path.is_file():
            continue
        events = load_jsonl(events_path)
        parse_error_count = sum("_parse_error" in row for row in events)
        timestamped = [parse_time(row["timestamp"]) for row in events if row.get("timestamp")]
        if not timestamped or max(timestamped) < since or min(timestamped) > now:
            continue
        first, last = min(timestamped), min(max(timestamped), now)
        created = _event_time(events, "instance_created")
        ssh = _event_time(events, "ssh_ready")
        failed = _event_time(events, "experiment_error")
        cleanup_requested = _event_time(events, "factory_lifecycle", action="request-cleanup")
        cleanup_verified = _event_time(events, "cleanup_verified")
        outcome_time = failed or cleanup_requested or cleanup_verified or last
        result_path = directory / "factory-result.json"
        result = json.loads(result_path.read_text()) if result_path.is_file() else {}
        summary_path = directory / "summary.json"
        summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
        outcome = result.get("outcome_class") or summary.get("outcome") or "in_progress"
        cost = summary.get("cost_usd_derived", result.get("cost_usd", 0.0))
        allocations.append(
            {
                "allocation_id": directory.name,
                "start": iso(first),
                "end": iso(cleanup_verified or last),
                "completed": cleanup_verified is not None,
                "outcome": outcome,
                "failure_class": result.get("failure_class"),
                "cost_usd": round(float(cost or 0.0), 9),
                "provider_active_seconds": round(((cleanup_verified or last) - first).total_seconds(), 3),
                "provisioning_seconds": round((created - first).total_seconds(), 3) if created else None,
                "ssh_ready_seconds": round((ssh - created).total_seconds(), 3) if created and ssh else None,
                "remote_execution_seconds": round((outcome_time - ssh).total_seconds(), 3) if ssh else None,
                "cleanup_seconds": (
                    round((cleanup_verified - cleanup_requested).total_seconds(), 3)
                    if cleanup_requested and cleanup_verified
                    else None
                ),
                "useful_gpu_seconds": summary.get("useful_gpu_seconds"),
                "event_parse_errors": parse_error_count,
            }
        )
    completed = [row for row in allocations if row["completed"]]
    scientific = [row for row in completed if str(row["outcome"]).startswith("scientific_")]
    invalid = [row for row in completed if not str(row["outcome"]).startswith("scientific_")]
    total_cost = sum(row["cost_usd"] for row in completed)
    invalid_cost = sum(row["cost_usd"] for row in invalid)
    provider_seconds = sum(row["provider_active_seconds"] for row in completed)
    useful_values = [float(row["useful_gpu_seconds"]) for row in completed if row["useful_gpu_seconds"] is not None]
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
            "allocations_missing_useful_gpu_timing": sum(
                row["useful_gpu_seconds"] is None for row in completed
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
    if campaign_summary.get("allocations_missing_useful_gpu_timing", 0):
        recommendations.append("emit useful_gpu_seconds from model-transfer start through the final scored arm")
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
