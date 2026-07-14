from __future__ import annotations

from typing import Any

from .util import (
    ValidationError,
    content_hash,
    require_id,
    require_number,
    require_probability,
    require_sha256,
    require_string_list,
    require_text,
)


TELEMETRY_CATEGORIES = {
    "provenance",
    "request",
    "scheduler",
    "accelerator",
    "host",
    "model",
    "quality",
    "economics",
}
MANDATORY_CAPTURE_CATEGORIES = {"provenance", "request", "quality", "economics"}
CAPTURE_TIERS = {"always_on", "sampled_trace", "deep_profile"}
SCORING_MODES = {"scoreable", "diagnostic_only"}
UNIVERSAL_RUN_ARTIFACT_ROLES = {
    "run_spec",
    "identities",
    "measurement_summary",
    "telemetry_summary",
    "quality",
    "cost",
    "logs",
}


def _required(value: Any, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{path} must be an object")
    missing = sorted(fields - value.keys())
    if missing:
        raise ValidationError(f"{path} missing required fields: {', '.join(missing)}")
    return value


def _string_list(name: str, value: Any, *, nonempty: bool = True) -> list[str]:
    return require_string_list(name, value, nonempty=nonempty)


def validate_telemetry_contract(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "scoring_mode",
        "clock_basis",
        "correlation_keys",
        "critical_path_method",
        "critical_path_coverage_gate",
        "collection_budget",
        "signals",
        "observer_effect",
    }
    _required(value, required, "telemetry contract")
    if value["schema_version"] != 1:
        raise ValidationError("telemetry contract schema_version must be 1")
    if value["scoring_mode"] not in SCORING_MODES:
        raise ValidationError("telemetry contract scoring_mode is unsupported")
    if value["clock_basis"] not in {
        "monotonic_ns_with_wall_clock_anchor",
        "simulated_clock",
        "not_applicable",
    }:
        raise ValidationError("telemetry contract clock_basis is unsupported")
    correlation_keys = _string_list("telemetry contract.correlation_keys", value["correlation_keys"])
    if value["clock_basis"] == "monotonic_ns_with_wall_clock_anchor":
        for key in ("run_id", "monotonic_ns"):
            if key not in correlation_keys:
                raise ValidationError(f"telemetry contract.correlation_keys must include {key}")
    if value["critical_path_method"] not in {"dependency_union", "simulated_dependency_graph", "not_applicable"}:
        raise ValidationError("telemetry contract critical_path_method is unsupported")
    coverage_gate = require_probability(
        "telemetry contract.critical_path_coverage_gate", value["critical_path_coverage_gate"]
    )
    if value["critical_path_method"] == "dependency_union" and coverage_gate < 0.95:
        raise ValidationError("dependency-union telemetry requires at least 95% attribution coverage")
    collection_budget = _required(
        value["collection_budget"],
        {
            "max_cpu_overhead_fraction",
            "max_event_rate_hz",
            "max_bytes_per_request",
            "max_artifact_bytes",
        },
        "telemetry contract.collection_budget",
    )
    max_cpu_overhead = require_probability(
        "telemetry contract.collection_budget.max_cpu_overhead_fraction",
        collection_budget["max_cpu_overhead_fraction"],
    )
    if value["scoring_mode"] == "scoreable" and max_cpu_overhead > 0.03:
        raise ValidationError("scoreable telemetry CPU-overhead budget cannot exceed 3%")
    for name in ("max_event_rate_hz", "max_bytes_per_request", "max_artifact_bytes"):
        if type(collection_budget[name]) is not int or collection_budget[name] <= 0:
            raise ValidationError(f"telemetry contract.collection_budget.{name} must be a positive integer")

    signals = value["signals"]
    if not isinstance(signals, list) or not signals:
        raise ValidationError("telemetry contract.signals must be a nonempty list")
    names: set[str] = set()
    category_status: dict[str, set[str]] = {category: set() for category in TELEMETRY_CATEGORIES}
    captured: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for index, signal in enumerate(signals):
        path = f"telemetry contract.signals[{index}]"
        _required(signal, {"name", "category", "status"}, path)
        name = require_id(f"{path}.name", signal["name"])
        if name in names:
            raise ValidationError(f"telemetry signal {name} is duplicated")
        names.add(name)
        category = signal["category"]
        if category not in TELEMETRY_CATEGORIES:
            raise ValidationError(f"{path}.category is unsupported")
        status = signal["status"]
        if status not in {"capture", "unavailable"}:
            raise ValidationError(f"{path}.status is unsupported")
        category_status[category].add(status)
        if status == "capture":
            _required(signal, {"tier", "artifact_role", "fields", "sampling"}, path)
            if signal["tier"] not in CAPTURE_TIERS:
                raise ValidationError(f"{path}.tier is unsupported")
            require_id(f"{path}.artifact_role", signal["artifact_role"])
            _string_list(f"{path}.fields", signal["fields"])
            require_text(f"{path}.sampling", signal["sampling"])
            captured.append(signal)
        else:
            _required(signal, {"reason", "next_probe"}, path)
            require_text(f"{path}.reason", signal["reason"])
            require_text(f"{path}.next_probe", signal["next_probe"])
            unavailable.append(signal)

    missing_categories = sorted(category for category, statuses in category_status.items() if not statuses)
    if missing_categories:
        raise ValidationError(
            "telemetry contract omits system categories: " + ", ".join(missing_categories)
        )
    missing_core = sorted(
        category for category in MANDATORY_CAPTURE_CATEGORIES if "capture" not in category_status[category]
    )
    if missing_core:
        raise ValidationError(
            "telemetry contract must capture core categories: " + ", ".join(missing_core)
        )

    observer = _required(
        value["observer_effect"],
        {
            "required",
            "bracket",
            "max_throughput_change_fraction",
            "max_median_latency_change_fraction",
            "max_tail_latency_change_fraction",
            "action_on_breach",
        },
        "telemetry contract.observer_effect",
    )
    if type(observer["required"]) is not bool:
        raise ValidationError("telemetry contract.observer_effect.required must be boolean")
    bracket = _string_list("telemetry contract.observer_effect.bracket", observer["bracket"])
    if observer["required"] and bracket != ["observer_off", "observer_on", "observer_off"]:
        raise ValidationError("required observer measurement must use an observer-off/on/off bracket")
    for name in (
        "max_throughput_change_fraction",
        "max_median_latency_change_fraction",
        "max_tail_latency_change_fraction",
    ):
        threshold = require_number(f"telemetry contract.observer_effect.{name}", observer[name], nonnegative=True)
        if threshold > 0.25:
            raise ValidationError(f"telemetry contract.observer_effect.{name} is not a useful bound")
    require_text("telemetry contract.observer_effect.action_on_breach", observer["action_on_breach"])

    intrusive = [signal for signal in captured if signal["tier"] in {"sampled_trace", "deep_profile"}]
    if intrusive and not observer["required"]:
        raise ValidationError("sampled or deep telemetry requires an observer-effect bracket")
    if intrusive and value["scoring_mode"] == "scoreable":
        raise ValidationError("sampled or deep telemetry cannot be part of a scoreable arm")
    if any(signal["tier"] == "deep_profile" for signal in captured):
        if value["scoring_mode"] != "diagnostic_only":
            raise ValidationError("deep profiler output is diagnostic-only and cannot score an arm")

    capture_categories = sorted({signal["category"] for signal in captured})
    unavailable_categories = sorted({signal["category"] for signal in unavailable})
    return {
        "contract_sha256": content_hash(value),
        "captured_signal_names": sorted(signal["name"] for signal in captured),
        "unavailable_signal_names": sorted(signal["name"] for signal in unavailable),
        "capture_categories": capture_categories,
        "unavailable_categories": unavailable_categories,
        "artifact_roles": sorted({signal["artifact_role"] for signal in captured}),
        "intrusive": bool(intrusive),
    }


def required_artifact_roles(contract: dict[str, Any]) -> set[str]:
    report = validate_telemetry_contract(contract)
    return UNIVERSAL_RUN_ARTIFACT_ROLES | set(report["artifact_roles"])


def validate_telemetry_summary(summary: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    report = validate_telemetry_contract(contract)
    _required(
        summary,
        {
            "schema_version",
            "contract_sha256",
            "captured_signals",
            "missing_signals",
            "unavailable_signals",
            "correlation_status",
            "attribution_coverage",
            "observer_effect",
        },
        "telemetry summary",
    )
    if summary["schema_version"] != 1:
        raise ValidationError("telemetry summary schema_version must be 1")
    require_sha256("telemetry summary.contract_sha256", summary["contract_sha256"])
    if summary["contract_sha256"] != report["contract_sha256"]:
        raise ValidationError("telemetry summary is bound to the wrong contract")
    captured = set(_string_list("telemetry summary.captured_signals", summary["captured_signals"], nonempty=False))
    missing = set(_string_list("telemetry summary.missing_signals", summary["missing_signals"], nonempty=False))
    unavailable = set(
        _string_list("telemetry summary.unavailable_signals", summary["unavailable_signals"], nonempty=False)
    )
    expected_captured = set(report["captured_signal_names"])
    expected_unavailable = set(report["unavailable_signal_names"])
    if captured & missing:
        raise ValidationError("telemetry summary lists a signal as both captured and missing")
    if captured | missing != expected_captured:
        raise ValidationError("telemetry summary does not account for every planned capture signal")
    if unavailable != expected_unavailable:
        raise ValidationError("telemetry summary does not match the contract's unavailable signals")
    if summary["correlation_status"] not in {"pass", "failed", "not_applicable"}:
        raise ValidationError("telemetry summary.correlation_status is unsupported")
    coverage = summary["attribution_coverage"]
    if coverage != "not_applicable":
        coverage = require_probability("telemetry summary.attribution_coverage", coverage)

    observer = _required(
        summary["observer_effect"],
        {
            "status",
            "throughput_change_fraction",
            "median_latency_change_fraction",
            "tail_latency_change_fraction",
        },
        "telemetry summary.observer_effect",
    )
    if observer["status"] not in {"pass", "failed", "not_applicable"}:
        raise ValidationError("telemetry summary.observer_effect.status is unsupported")
    measured_perturbation: dict[str, float | str] = {}
    for name in (
        "throughput_change_fraction",
        "median_latency_change_fraction",
        "tail_latency_change_fraction",
    ):
        value = observer[name]
        if value == "not_applicable":
            measured_perturbation[name] = value
        else:
            measured_perturbation[name] = require_number(
                f"telemetry summary.observer_effect.{name}", value
            )
    observer_contract = contract["observer_effect"]
    if observer_contract["required"]:
        if observer["status"] == "not_applicable" or any(
            value == "not_applicable" for value in measured_perturbation.values()
        ):
            raise ValidationError("required observer-effect measurement is missing")
        thresholds = {
            "throughput_change_fraction": observer_contract["max_throughput_change_fraction"],
            "median_latency_change_fraction": observer_contract["max_median_latency_change_fraction"],
            "tail_latency_change_fraction": observer_contract["max_tail_latency_change_fraction"],
        }
        breached = any(abs(float(measured_perturbation[name])) > thresholds[name] for name in thresholds)
        if observer["status"] == "pass" and breached:
            raise ValidationError("observer-effect status passed despite a preregistered perturbation breach")
    elif observer["status"] == "pass" and all(
        value == "not_applicable" for value in measured_perturbation.values()
    ):
        raise ValidationError("observer-effect pass requires measurements")

    return {
        **summary,
        "captured_signals": sorted(captured),
        "missing_signals": sorted(missing),
        "unavailable_signals": sorted(unavailable),
        "attribution_coverage": coverage,
    }


def build_telemetry_contract(mode: str = "scoreable") -> dict[str, Any]:
    if mode not in SCORING_MODES:
        raise ValidationError("telemetry template mode is unsupported")
    signals: list[dict[str, Any]] = [
        {
            "name": "identity_and_environment",
            "category": "provenance",
            "status": "capture",
            "tier": "always_on",
            "artifact_role": "identities",
            "sampling": "once per run and whenever identity changes",
            "fields": [
                "model",
                "revision",
                "code",
                "runtime",
                "hardware",
                "configuration",
                "operator_shape_dictionary",
            ],
        },
        {
            "name": "request_timeline",
            "category": "request",
            "status": "capture",
            "tier": "always_on",
            "artifact_role": "events",
            "sampling": "one lifecycle record per request",
            "fields": [
                "request_id",
                "arrival_ns",
                "prompt_tokens",
                "output_tokens",
                "queue_ns",
                "ttft_ns",
                "tpot_ns",
                "end_to_end_ns",
                "status",
            ],
        },
        {
            "name": "scheduler_timeline",
            "category": "scheduler",
            "status": "capture",
            "tier": "always_on",
            "artifact_role": "events",
            "sampling": "one aggregate per request plus queue, preemption, and overload state changes",
            "fields": [
                "request_id",
                "iterations",
                "scheduled_prefill_tokens",
                "scheduled_decode_tokens",
                "mean_batch_size",
                "max_waiting_requests",
                "preemptions",
                "kv_occupancy_summary",
            ],
        },
        {
            "name": "accelerator_health",
            "category": "accelerator",
            "status": "capture",
            "tier": "always_on",
            "artifact_role": "system_samples",
            "sampling": "one hertz by default; increase only around a decision boundary",
            "fields": ["monotonic_ns", "utilization", "vram_bytes", "clock_hz", "power_w", "temperature_c"],
        },
        {
            "name": "host_and_transfer_health",
            "category": "host",
            "status": "capture",
            "tier": "always_on",
            "artifact_role": "system_samples",
            "sampling": "one hertz by default plus resource failures",
            "fields": ["monotonic_ns", "cpu_utilization", "rss_bytes", "io_bytes", "network_bytes"],
        },
        {
            "name": "model_structure",
            "category": "model",
            "status": "capture",
            "tier": "always_on",
            "artifact_role": "identities",
            "sampling": "once per run plus architecture-specific aggregate counters",
            "fields": ["module_dictionary", "shape_dictionary", "dtype", "layout", "architecture_aggregates"],
        },
        {
            "name": "quality_and_correctness",
            "category": "quality",
            "status": "capture",
            "tier": "always_on",
            "artifact_role": "quality",
            "sampling": "one record per evaluated sample",
            "fields": ["sample_id", "policy_sha256", "score", "pass", "error"],
        },
        {
            "name": "resource_and_cost_ledger",
            "category": "economics",
            "status": "capture",
            "tier": "always_on",
            "artifact_role": "cost",
            "sampling": "allocation start, stop, and rate or resource changes",
            "fields": ["allocation_id", "start_ns", "end_ns", "gpu_seconds", "rate", "currency", "total_cost"],
        },
    ]
    observer_required = mode == "diagnostic_only"
    if observer_required:
        signals.extend(
            [
                {
                    "name": "scheduler_iteration_trace",
                    "category": "scheduler",
                    "status": "capture",
                    "tier": "sampled_trace",
                    "artifact_role": "deep_trace",
                    "sampling": "one bounded post-warmup window in the observer-on arm",
                    "fields": [
                        "iteration_id",
                        "phase",
                        "start_ns",
                        "end_ns",
                        "scheduled_tokens",
                        "batch_composition",
                        "kv_state",
                    ],
                },
                {
                    "name": "cpu_gpu_dependency_trace",
                    "category": "host",
                    "status": "capture",
                    "tier": "deep_profile",
                    "artifact_role": "deep_trace",
                    "sampling": "one bounded post-warmup window in the observer-on arm",
                    "fields": ["thread_id", "stream_id", "correlation_id", "start_ns", "end_ns", "dependency"],
                },
                {
                    "name": "kernel_resource_trace",
                    "category": "accelerator",
                    "status": "capture",
                    "tier": "deep_profile",
                    "artifact_role": "deep_trace",
                    "sampling": "one bounded post-warmup window in the observer-on arm",
                    "fields": ["kernel", "grid", "block", "registers", "shared_memory", "start_ns", "end_ns"],
                },
            ]
        )
    contract = {
        "schema_version": 1,
        "scoring_mode": mode,
        "clock_basis": "monotonic_ns_with_wall_clock_anchor",
        "correlation_keys": ["run_id", "monotonic_ns", "request_id", "iteration_id"],
        "critical_path_method": "not_applicable" if mode == "scoreable" else "dependency_union",
        "critical_path_coverage_gate": 0.0 if mode == "scoreable" else 0.95,
        "collection_budget": {
            "max_cpu_overhead_fraction": 0.01 if mode == "scoreable" else 0.10,
            "max_event_rate_hz": 2000 if mode == "scoreable" else 200000,
            "max_bytes_per_request": 16384 if mode == "scoreable" else 1048576,
            "max_artifact_bytes": 536870912 if mode == "scoreable" else 8589934592,
        },
        "signals": signals,
        "observer_effect": {
            "required": observer_required,
            "bracket": ["observer_off", "observer_on", "observer_off"],
            "max_throughput_change_fraction": 0.03,
            "max_median_latency_change_fraction": 0.03,
            "max_tail_latency_change_fraction": 0.05,
            "action_on_breach": "classify the trace as harness-invalid and reduce duration or sampling",
        },
    }
    validate_telemetry_contract(contract)
    return contract


def build_complete_telemetry_summary(
    contract: dict[str, Any],
    *,
    attribution_coverage: float | str,
    observer_status: str = "not_applicable",
    throughput_change_fraction: float | str = "not_applicable",
    median_latency_change_fraction: float | str = "not_applicable",
    tail_latency_change_fraction: float | str = "not_applicable",
    correlation_status: str = "pass",
) -> dict[str, Any]:
    report = validate_telemetry_contract(contract)
    summary = {
        "schema_version": 1,
        "contract_sha256": report["contract_sha256"],
        "captured_signals": report["captured_signal_names"],
        "missing_signals": [],
        "unavailable_signals": report["unavailable_signal_names"],
        "correlation_status": correlation_status,
        "attribution_coverage": attribution_coverage,
        "observer_effect": {
            "status": observer_status,
            "throughput_change_fraction": throughput_change_fraction,
            "median_latency_change_fraction": median_latency_change_fraction,
            "tail_latency_change_fraction": tail_latency_change_fraction,
        },
    }
    return validate_telemetry_summary(summary, contract)
