#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Iterable


COVERAGE_GATE = 0.95
DENSE_SHARE_GATE = 0.20
HOST_SHARE_GATE = 0.10
HOST_VARIANCE_GATE = 0.50
MEMORY_THROUGHPUT_GATE = 0.70
SM_ACTIVE_GATE = 0.65
MEMORY_TO_SM_GATE = 1.25

TABLES = (
    "requests",
    "scheduler_iterations",
    "nvtx_ranges",
    "cuda_activities",
    "host_intervals",
)


class ObserverAnalysisError(ValueError):
    pass


def _integer(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ObserverAnalysisError(f"{name} must be an integer")
    return value


def _number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObserverAnalysisError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ObserverAnalysisError(f"{name} must be finite")
    return result


def _fraction(name: str, value: Any) -> float:
    result = _number(name, value)
    if not 0.0 <= result <= 1.0:
        raise ObserverAnalysisError(f"{name} must be between zero and one")
    return result


def _interval(value: Any, name: str = "interval") -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ObserverAnalysisError(f"{name} must contain start and end")
    start = _integer(f"{name}.start", value[0])
    end = _integer(f"{name}.end", value[1])
    if end < start:
        raise ObserverAnalysisError(f"{name} ends before it starts")
    return start, end


def merge_intervals(
    intervals: Iterable[tuple[int, int] | list[int]],
    *,
    window: tuple[int, int] | None = None,
) -> list[tuple[int, int]]:
    clip = _interval(window, "window") if window is not None else None
    normalized = []
    for index, value in enumerate(intervals):
        start, end = _interval(value, f"intervals[{index}]")
        if clip is not None:
            start = max(start, clip[0])
            end = min(end, clip[1])
        if end > start:
            normalized.append((start, end))
    normalized.sort()
    merged: list[tuple[int, int]] = []
    for start, end in normalized:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def interval_union_ns(
    intervals: Iterable[tuple[int, int] | list[int]],
    *,
    window: tuple[int, int] | None = None,
) -> int:
    return sum(end - start for start, end in merge_intervals(intervals, window=window))


def _rows(fixture: dict[str, Any], name: str) -> list[dict[str, Any]]:
    value = fixture.get(name, [])
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ObserverAnalysisError(f"{name} must be a list of objects")
    return value


def _row_interval(row: dict[str, Any], path: str) -> tuple[int, int]:
    return _interval((row.get("start_ns"), row.get("end_ns")), path)


def _request_ids(value: Any, path: str) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise ObserverAnalysisError(f"{path} is not valid JSON") from error
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ObserverAnalysisError(f"{path} must be a nonempty string list")
    return value


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def correlation_summary(fixture: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(fixture, dict):
        raise ObserverAnalysisError("fixture must be an object")
    request_rows = _rows(fixture, "requests")
    scheduler_rows = _rows(fixture, "scheduler_iterations")
    nvtx_rows = _rows(fixture, "nvtx_ranges")
    cuda_rows = _rows(fixture, "cuda_activities")
    host_rows = _rows(fixture, "host_intervals")

    requests: dict[str, tuple[int, int]] = {}
    for index, row in enumerate(request_rows):
        request_id = row.get("request_id")
        if not isinstance(request_id, str) or not request_id or request_id in requests:
            raise ObserverAnalysisError(f"requests[{index}].request_id is absent or duplicated")
        requests[request_id] = _row_interval(row, f"requests[{index}]")

    nvtx_by_iteration: dict[str, list[tuple[int, int]]] = {}
    for index, row in enumerate(nvtx_rows):
        iteration_id = row.get("iteration_id")
        if not isinstance(iteration_id, str) or not iteration_id:
            raise ObserverAnalysisError(f"nvtx_ranges[{index}].iteration_id is absent")
        nvtx_by_iteration.setdefault(iteration_id, []).append(
            _row_interval(row, f"nvtx_ranges[{index}]")
        )

    cuda_by_iteration: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(cuda_rows):
        iteration_id = row.get("iteration_id")
        correlation_id = row.get("correlation_id")
        family = row.get("family")
        if not isinstance(iteration_id, str) or not iteration_id:
            raise ObserverAnalysisError(f"cuda_activities[{index}].iteration_id is absent")
        if not isinstance(correlation_id, str) or not correlation_id:
            raise ObserverAnalysisError(f"cuda_activities[{index}].correlation_id is absent")
        if not isinstance(family, str) or not family:
            raise ObserverAnalysisError(f"cuda_activities[{index}].family is absent")
        value = dict(row)
        value["interval"] = _row_interval(row, f"cuda_activities[{index}]")
        cuda_by_iteration.setdefault(iteration_id, []).append(value)

    host_by_iteration: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(host_rows):
        iteration_id = row.get("iteration_id")
        category = row.get("category")
        if not isinstance(iteration_id, str) or not iteration_id:
            raise ObserverAnalysisError(f"host_intervals[{index}].iteration_id is absent")
        if not isinstance(category, str) or not category:
            raise ObserverAnalysisError(f"host_intervals[{index}].category is absent")
        value = dict(row)
        value["interval"] = _row_interval(row, f"host_intervals[{index}]")
        host_by_iteration.setdefault(iteration_id, []).append(value)

    eligible = []
    seen_iterations = set()
    for index, row in enumerate(scheduler_rows):
        iteration_id = row.get("iteration_id")
        if not isinstance(iteration_id, str) or not iteration_id or iteration_id in seen_iterations:
            raise ObserverAnalysisError(
                f"scheduler_iterations[{index}].iteration_id is absent or duplicated"
            )
        seen_iterations.add(iteration_id)
        phase = row.get("phase")
        if phase != "decode":
            continue
        eligible.append(
            {
                "iteration_id": iteration_id,
                "request_ids": _request_ids(
                    row.get("request_ids"), f"scheduler_iterations[{index}].request_ids"
                ),
                "interval": _row_interval(row, f"scheduler_iterations[{index}]"),
            }
        )

    covered_ids = []
    uncovered_ids = []
    dependency_intervals = []
    dense_intervals = []
    host_intervals = []
    host_categories: dict[str, list[tuple[int, int]]] = {}
    for iteration in eligible:
        iteration_id = iteration["iteration_id"]
        window = iteration["interval"]
        request_match = all(
            request_id in requests and _overlaps(window, requests[request_id])
            for request_id in iteration["request_ids"]
        )
        nvtx = [value for value in nvtx_by_iteration.get(iteration_id, []) if _overlaps(value, window)]
        cuda = [
            value
            for value in cuda_by_iteration.get(iteration_id, [])
            if _overlaps(value["interval"], window)
            and any(_overlaps(value["interval"], nvtx_interval) for nvtx_interval in nvtx)
        ]
        if not request_match or not nvtx or not cuda:
            uncovered_ids.append(iteration_id)
            continue
        covered_ids.append(iteration_id)
        for value in cuda:
            clipped = merge_intervals([value["interval"]], window=window)
            dependency_intervals.extend(clipped)
            if value["family"] == "dense_gemm_gemv":
                dense_intervals.extend(clipped)
        for value in host_by_iteration.get(iteration_id, []):
            clipped = merge_intervals([value["interval"]], window=window)
            dependency_intervals.extend(clipped)
            host_intervals.extend(clipped)
            host_categories.setdefault(value["category"], []).extend(clipped)

    eligible_count = len(eligible)
    covered_count = len(covered_ids)
    coverage = covered_count / eligible_count if eligible_count else 0.0
    dependency_union = interval_union_ns(dependency_intervals)
    dense_union = interval_union_ns(dense_intervals)
    host_union = interval_union_ns(host_intervals)
    return {
        "schema_version": 1,
        "coverage_method": "decode_iteration_request_scheduler_nvtx_cuda",
        "eligible_iterations": eligible_count,
        "covered_iterations": covered_count,
        "coverage_fraction": coverage,
        "coverage_gate": COVERAGE_GATE,
        "coverage_pass": coverage >= COVERAGE_GATE,
        "covered_iteration_ids": sorted(covered_ids),
        "uncovered_iteration_ids": sorted(uncovered_ids),
        "covered_dependency_union_ns": dependency_union,
        "dense_union_ns": dense_union,
        "host_union_ns": host_union,
        "dense_dependency_share": dense_union / dependency_union if dependency_union else 0.0,
        "host_dependency_share": host_union / dependency_union if dependency_union else 0.0,
        "host_category_union_ns": {
            category: interval_union_ns(intervals)
            for category, intervals in sorted(host_categories.items())
        },
        "claim_limit": (
            "Non-overlapping time-correlated dependency-union diagnostic. Device-wide sampled "
            "metrics are not per-kernel counters and class shares may overlap each other."
        ),
    }


def observer_effect(
    control_before: dict[str, Any],
    observer_on: dict[str, Any],
    control_after: dict[str, Any],
    *,
    throughput_gate: float = 0.03,
    median_latency_gate: float = 0.03,
    tail_latency_gate: float = 0.05,
) -> dict[str, Any]:
    names = ("throughput", "median_latency_ms", "tail_latency_ms")
    controls = {}
    effects = {}
    for name in names:
        before = _number(f"control_before.{name}", control_before.get(name))
        candidate = _number(f"observer_on.{name}", observer_on.get(name))
        after = _number(f"control_after.{name}", control_after.get(name))
        control = (before + after) / 2.0
        if control <= 0 or candidate <= 0:
            raise ObserverAnalysisError(f"observer metric {name} must be positive")
        controls[name] = control
        effect_name = {
            "throughput": "throughput_fraction",
            "median_latency_ms": "median_latency_fraction",
            "tail_latency_ms": "tail_latency_fraction",
        }[name]
        effects[effect_name] = candidate / control - 1.0

    gates = {
        "throughput": _fraction("throughput_gate", throughput_gate),
        "median_latency": _fraction("median_latency_gate", median_latency_gate),
        "tail_latency": _fraction("tail_latency_gate", tail_latency_gate),
    }
    values = {
        "throughput": abs(effects["throughput_fraction"]),
        "median_latency": abs(effects["median_latency_fraction"]),
        "tail_latency": abs(effects["tail_latency_fraction"]),
    }
    breached = sorted(name for name, value in values.items() if value > gates[name])
    return {
        "schema_version": 1,
        "protocol": "A1_observer_off_B1_observer_on_A2_observer_off",
        "control_estimates": controls,
        "effects": effects,
        "absolute_effects": values,
        "gates": gates,
        "breached_gates": breached,
        "pass": not breached,
        "breach_action": (
            None
            if not breached
            else "classify_harness_invalid_and_reduce_duration_or_sampling"
        ),
    }


def select_route(
    *,
    coverage_fraction: float,
    observer_valid: bool,
    dense_dependency_share: float,
    host_dependency_share: float,
    adjusted_r_squared: float,
    memory_throughput_normalized: float | None = None,
    sm_active_normalized: float | None = None,
    memory_to_sm_ratio: float | None = None,
    compute_or_occupancy_dominant: bool = False,
) -> dict[str, Any]:
    coverage = _fraction("coverage_fraction", coverage_fraction)
    dense = _fraction("dense_dependency_share", dense_dependency_share)
    host = _fraction("host_dependency_share", host_dependency_share)
    adjusted_r2 = _number("adjusted_r_squared", adjusted_r_squared)
    if not isinstance(observer_valid, bool):
        raise ObserverAnalysisError("observer_valid must be boolean")
    if not isinstance(compute_or_occupancy_dominant, bool):
        raise ObserverAnalysisError("compute_or_occupancy_dominant must be boolean")

    metrics = {}
    for name, value in (
        ("memory_throughput_normalized", memory_throughput_normalized),
        ("sm_active_normalized", sm_active_normalized),
        ("memory_to_sm_ratio", memory_to_sm_ratio),
    ):
        if value is not None:
            metrics[name] = _number(name, value)

    if not observer_valid or coverage < COVERAGE_GATE:
        route = "instrumentation_failure"
        reason = "observer bracket failed or dependency-union coverage is below 95%"
    elif host >= HOST_SHARE_GATE or adjusted_r2 >= HOST_VARIANCE_GATE:
        route = "host_scheduler_route"
        reason = "host dependency share is at least 10% or host timing explains at least half the variance"
    elif dense < DENSE_SHARE_GATE:
        route = "not_dense_route"
        reason = "dense work is below 20% of the covered dependency union"
    else:
        memory_dominant = (
            memory_throughput_normalized is not None
            and sm_active_normalized is not None
            and memory_throughput_normalized >= MEMORY_THROUGHPUT_GATE
            and sm_active_normalized < SM_ACTIVE_GATE
        ) or (memory_to_sm_ratio is not None and memory_to_sm_ratio >= MEMORY_TO_SM_GATE)
        if memory_dominant:
            route = "dense_memory_route"
            reason = "dense share passes and the normalized memory signature crosses the preregistered gate"
        elif compute_or_occupancy_dominant:
            route = "dense_compute_or_occupancy_route"
            reason = "dense share passes, host share is low, and compute or occupancy is dominant"
        else:
            route = "unresolved_dense_route"
            reason = "dense share passes but the available resource signature does not separate the limiter"
    return {
        "schema_version": 1,
        "route": route,
        "reason": reason,
        "inputs": {
            "coverage_fraction": coverage,
            "observer_valid": observer_valid,
            "dense_dependency_share": dense,
            "host_dependency_share": host,
            "adjusted_r_squared": adjusted_r2,
            "compute_or_occupancy_dominant": compute_or_occupancy_dominant,
            **metrics,
        },
        "thresholds": {
            "coverage_fraction": COVERAGE_GATE,
            "dense_dependency_share": DENSE_SHARE_GATE,
            "host_dependency_share": HOST_SHARE_GATE,
            "adjusted_r_squared": HOST_VARIANCE_GATE,
            "memory_throughput_normalized": MEMORY_THROUGHPUT_GATE,
            "sm_active_normalized": SM_ACTIVE_GATE,
            "memory_to_sm_ratio": MEMORY_TO_SM_GATE,
        },
    }


def load_sqlite_fixture(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ObserverAnalysisError(f"SQLite fixture is absent: {path}")
    fixture: dict[str, Any] = {}
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        existing = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        for table in TABLES:
            if table not in existing:
                fixture[table] = []
                continue
            rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]
            if table == "scheduler_iterations":
                for index, row in enumerate(rows):
                    row["request_ids"] = _request_ids(
                        row.get("request_ids"), f"scheduler_iterations[{index}].request_ids"
                    )
            fixture[table] = rows
    finally:
        connection.close()
    return fixture


def analyze_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    correlation = correlation_summary(fixture)
    arms = fixture.get("observer_arms")
    if not isinstance(arms, dict) or not all(name in arms for name in ("A1", "B1", "A2")):
        raise ObserverAnalysisError("observer_arms must contain A1, B1, and A2")
    bracket = observer_effect(arms["A1"], arms["B1"], arms["A2"])
    resource = fixture.get("resource_metrics", {})
    if not isinstance(resource, dict):
        raise ObserverAnalysisError("resource_metrics must be an object")
    route = select_route(
        coverage_fraction=correlation["coverage_fraction"],
        observer_valid=bracket["pass"],
        dense_dependency_share=correlation["dense_dependency_share"],
        host_dependency_share=correlation["host_dependency_share"],
        adjusted_r_squared=fixture.get("adjusted_r_squared", 0.0),
        memory_throughput_normalized=resource.get("memory_throughput_normalized"),
        sm_active_normalized=resource.get("sm_active_normalized"),
        memory_to_sm_ratio=resource.get("memory_to_sm_ratio"),
        compute_or_occupancy_dominant=resource.get("compute_or_occupancy_dominant", False),
    )
    return {
        "schema_version": 1,
        "evidence_class": "synthetic_or_exported_nsys_diagnostic",
        "correlation": correlation,
        "observer_effect": bracket,
        "route_decision": route,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--json", type=Path)
    source.add_argument("--sqlite", type=Path)
    parser.add_argument("--observer-arms", type=Path)
    parser.add_argument("--resource-metrics", type=Path)
    parser.add_argument("--adjusted-r-squared", type=float, default=0.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.json is not None:
        fixture = json.loads(args.json.read_text())
    else:
        fixture = load_sqlite_fixture(args.sqlite)
        if args.observer_arms is None:
            parser.error("--observer-arms is required with --sqlite")
        fixture["observer_arms"] = json.loads(args.observer_arms.read_text())
        fixture["resource_metrics"] = (
            json.loads(args.resource_metrics.read_text()) if args.resource_metrics is not None else {}
        )
        fixture["adjusted_r_squared"] = args.adjusted_r_squared
    result = analyze_fixture(fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
