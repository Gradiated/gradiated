from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


FALSE_CLAIMS = (
    "calibration",
    "cost_per_token",
    "end_to_end_serving",
    "energy",
    "glm_performance",
    "glm_trace_fidelity",
    "gpu_kernel_overhead",
    "model_quality",
    "provider_superiority",
    "pristine_source_execution",
    "tapeout",
    "wall_clock_latency",
)

REPLAY_FIELDS = (
    "controller_cycles",
    "average_read_latency_cycles",
    "total_read_latency_cycles",
    "accepted_read_count",
    "accepted_write_count",
    "memory_system_read_count",
    "memory_system_write_count",
    "served_read_count",
    "served_write_count",
    "driver_accepted_count",
    "driver_completed_count",
    "driver_tick_count",
    "driver_callback_latency_sum",
    "row_hits",
    "row_misses",
    "row_conflicts",
)


def content_identity(document: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in document.items()
        if key != "content_identity_sha256"
    }
    canonical = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _controller(stats: dict[str, Any]) -> dict[str, Any]:
    controller = stats["memory_system"]["controller"]
    if isinstance(controller, list):
        if len(controller) != 1:
            raise ValueError("exactly one controller is required")
        return controller[0]
    return controller


def normalize_stats(stats: dict[str, Any]) -> dict[str, Any]:
    memory = stats["memory_system"]
    controller = _controller(stats)
    row_hits = int(controller["row_hits"])
    row_misses = int(controller["row_misses"])
    row_conflicts = int(controller["row_conflicts"])
    row_outcomes = row_hits + row_misses + row_conflicts
    accepted_read = int(controller["num_read_reqs"])
    accepted_write = int(controller["num_write_reqs"])
    served_read = int(controller["num_read_reqs_served"])
    served_write = int(controller["num_write_reqs_served"])
    accepted = accepted_read + accepted_write
    served = served_read + served_write
    driver = stats.get("driver", {})
    return {
        "controller_cycles": int(controller["cycles"]),
        "average_read_latency_cycles": float(controller["avg_read_latency"]),
        "total_read_latency_cycles": int(controller["read_latency"]),
        "accepted_read_count": accepted_read,
        "accepted_write_count": accepted_write,
        "accepted_request_count": accepted,
        "memory_system_read_count": int(memory["total_num_read_requests"]),
        "memory_system_write_count": int(memory["total_num_write_requests"]),
        "served_read_count": served_read,
        "served_write_count": served_write,
        "served_request_count": served,
        "driver_accepted_count": int(driver.get("accepted_request_count", accepted)),
        "driver_completed_count": int(driver.get("completed_request_count", served)),
        "driver_tick_count": int(driver.get("tick_count", 0)),
        "driver_callback_latency_sum": int(driver.get("callback_latency_sum", 0)),
        "completion_fraction": served / accepted if accepted else 0.0,
        "row_hits": row_hits,
        "row_misses": row_misses,
        "row_conflicts": row_conflicts,
        "row_outcome_count": row_outcomes,
        "row_outcome_coverage": row_outcomes / accepted if accepted else 0.0,
        "row_hit_fraction": row_hits / row_outcomes if row_outcomes else 0.0,
    }


def _acceptance_conserved(summary: dict[str, Any], run: dict[str, Any]) -> bool:
    return (
        run["accepted_request_count"] == summary["request_count"]
        and run["accepted_read_count"] == summary["read_count"]
        and run["accepted_write_count"] == summary["write_count"]
        and run["memory_system_read_count"] == summary["read_count"]
        and run["memory_system_write_count"] == summary["write_count"]
        and run["driver_accepted_count"] == summary["request_count"]
    )


def _all_served(summary: dict[str, Any], run: dict[str, Any]) -> bool:
    return (
        run["served_request_count"] == summary["request_count"]
        and run["served_read_count"] == summary["read_count"]
        and run["served_write_count"] == summary["write_count"]
        and run["driver_completed_count"] == summary["request_count"]
    )


def _drain_accounted(run: dict[str, Any]) -> bool:
    return (
        run["driver_tick_count"] == run["controller_cycles"]
        and run["driver_callback_latency_sum"] == run["total_read_latency_cycles"]
    )


def _replayed(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return all(first[field] == second[field] for field in REPLAY_FIELDS)


def build_report(
    source_identity: dict[str, Any],
    build: dict[str, Any],
    cases: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_cases = []
    for case in cases:
        normalized = deepcopy(case)
        runs = normalized.get("runs", [])
        summary = normalized["trace_summary"]
        normalized["request_acceptance_conservation_passed"] = bool(runs) and all(
            _acceptance_conserved(summary, run) for run in runs
        )
        normalized["all_requests_served"] = bool(runs) and all(
            _all_served(summary, run) for run in runs
        )
        normalized["request_conservation_passed"] = (
            normalized["request_acceptance_conservation_passed"]
            and normalized["all_requests_served"]
        )
        normalized["native_drain_accounting_passed"] = bool(runs) and all(
            _drain_accounted(run) for run in runs
        )
        normalized["deterministic_replay_passed"] = len(runs) == 2 and _replayed(
            runs[0], runs[1]
        )
        normalized["comparison_run"] = runs[0] if runs else None
        normalized_cases.append(normalized)
    native_succeeded = build.get("status") == "succeeded" and bool(normalized_cases)
    report = {
        "schema_version": "inference-foundry.ramulator2-hbm3-synthetic-oracle.v2",
        "status": (
            "patched_native_sweep_succeeded"
            if native_succeeded and build.get("pristine_source_build") is False
            else "native_sweep_succeeded"
            if native_succeeded
            else "blocked"
        ),
        "source_identity": deepcopy(source_identity),
        "build": deepcopy(build),
        "metadata": deepcopy(metadata or {}),
        "cases": normalized_cases,
        "claims": {
            "native_oracle_operability": native_succeeded,
            "synthetic_hbm3_sensitivity": native_succeeded,
            **{claim: False for claim in FALSE_CLAIMS},
        },
    }
    report["content_identity_sha256"] = content_identity(report)
    return report


def validate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("content_identity_sha256") != content_identity(report):
        errors.append("content identity mismatch")
    for claim in FALSE_CLAIMS:
        if report.get("claims", {}).get(claim) is not False:
            errors.append(f"{claim}: claim must remain false")
    cases = report.get("cases", [])
    for case in cases:
        pattern_id = case.get("pattern_id", "<missing>")
        if not case.get("request_conservation_passed"):
            errors.append(f"{pattern_id}: request conservation failed")
        if not case.get("deterministic_replay_passed"):
            errors.append(f"{pattern_id}: deterministic replay failed")
        if not case.get("native_drain_accounting_passed"):
            errors.append(f"{pattern_id}: native drain accounting failed")
    workload = report.get("metadata", {}).get("workload", {})
    expected_geometries = workload.get("geometries", {})
    expected_patterns = workload.get("executable_pattern_ids", [])
    geometries: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        geometries.setdefault(case.get("geometry_id", "default"), []).append(case)
    if expected_geometries and set(geometries) != set(expected_geometries):
        errors.append("geometry case set does not match the declared workload")
    for geometry_id, geometry_cases in geometries.items():
        pattern_ids = [case.get("pattern_id") for case in geometry_cases]
        if len(pattern_ids) != len(set(pattern_ids)):
            errors.append(f"{geometry_id}: duplicate pattern cases")
        if expected_patterns and set(pattern_ids) != set(expected_patterns):
            errors.append(f"{geometry_id}: pattern case set is incomplete")
        expected_geometry = expected_geometries.get(geometry_id)
        work = {
            (
                case["trace_summary"]["request_count"],
                case["trace_summary"]["read_count"],
                case["trace_summary"]["write_count"],
                case["trace_summary"]["request_bytes"],
                case["trace_summary"]["total_bytes"],
                case["trace_summary"].get("selected_token_count"),
                case["trace_summary"].get("unique_token_count"),
                case["trace_summary"].get("transactions_per_selected_token"),
                case["trace_summary"].get("bytes_per_selected_token"),
            )
            for case in geometry_cases
        }
        if len(work) > 1:
            errors.append(f"{geometry_id}: case work is not identical")
        for case in geometry_cases:
            summary = case["trace_summary"]
            pattern_id = case.get("pattern_id", "<missing>")
            if (
                expected_geometry is not None
                and case.get("geometry_contract") != expected_geometry
            ):
                errors.append(f"{geometry_id}/{pattern_id}: geometry contract mismatch")
            selected = summary.get("selected_token_count")
            transactions = summary.get("transactions_per_selected_token")
            request_bytes = summary.get("request_bytes")
            if (
                selected is not None
                and transactions is not None
                and summary.get("request_count") != selected * transactions
            ):
                errors.append(f"{geometry_id}/{pattern_id}: token work mismatch")
            if (
                transactions is not None
                and request_bytes is not None
                and summary.get("bytes_per_selected_token")
                != transactions * request_bytes
            ):
                errors.append(f"{geometry_id}/{pattern_id}: token byte mismatch")
            if (
                request_bytes is not None
                and summary.get("total_bytes")
                != summary.get("request_count") * request_bytes
            ):
                errors.append(f"{geometry_id}/{pattern_id}: total byte mismatch")
            if summary.get("read_count") + summary.get("write_count") != summary.get(
                "request_count"
            ):
                errors.append(f"{geometry_id}/{pattern_id}: request mix mismatch")
            if selected is not None and summary.get("unique_token_count") != selected:
                errors.append(
                    f"{geometry_id}/{pattern_id}: selected tokens are not unique"
                )
            if expected_geometry is not None and (
                transactions != expected_geometry.get("transactions_per_selected_token")
                or summary.get("bytes_per_selected_token")
                != expected_geometry.get("bytes_per_selected_token")
            ):
                errors.append(f"{geometry_id}/{pattern_id}: trace geometry mismatch")
            if workload.get(
                "selected_token_count"
            ) is not None and selected != workload.get("selected_token_count"):
                errors.append(
                    f"{geometry_id}/{pattern_id}: selected token count mismatch"
                )
            if workload.get(
                "request_bytes"
            ) is not None and request_bytes != workload.get("request_bytes"):
                errors.append(f"{geometry_id}/{pattern_id}: request byte size mismatch")
        by_pattern = {case["pattern_id"]: case for case in geometry_cases}
        score = by_pattern.get("gather_score_order")
        sorted_case = by_pattern.get("gather_address_sorted")
        if score and sorted_case:
            score_set = score["trace_summary"].get("selected_positions_sha256")
            sorted_set = sorted_case["trace_summary"].get("selected_positions_sha256")
            if score_set != sorted_set:
                errors.append(
                    f"{geometry_id}: score-order and address-sorted selected sets differ"
                )
    return errors
