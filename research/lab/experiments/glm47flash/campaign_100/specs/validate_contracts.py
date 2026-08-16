#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path


HERE = Path(__file__).resolve().parent
SHA256 = re.compile(r"^[0-9a-f]{64}$")
UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


class ContractError(ValueError):
    pass


def _decimal(name, value, *, positive=False, nonnegative=False):
    if isinstance(value, bool):
        raise ContractError(f"{name} must be decimal-compatible")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ContractError(f"{name} must be decimal-compatible") from None
    if not result.is_finite():
        raise ContractError(f"{name} must be finite")
    if positive and result <= 0:
        raise ContractError(f"{name} must be positive")
    if nonnegative and result < 0:
        raise ContractError(f"{name} must be nonnegative")
    return result


def _format(value):
    return format(value, "f")


def calculate_economics(
    hourly_price_usd,
    allocation_seconds,
    provider_reported_cost_usd,
    input_tokens,
    output_tokens,
    slo_input_tokens,
    slo_output_tokens,
    input_token_weight,
    non_gpu_sensitivity_fraction,
):
    hourly = _decimal("hourly_price_usd", hourly_price_usd, positive=True)
    seconds = _decimal("allocation_seconds", allocation_seconds, positive=True)
    reported = _decimal("provider_reported_cost_usd", provider_reported_cost_usd, nonnegative=True)
    inputs = _decimal("input_tokens", input_tokens, positive=True)
    outputs = _decimal("output_tokens", output_tokens, positive=True)
    slo_inputs = _decimal("slo_input_tokens", slo_input_tokens, nonnegative=True)
    slo_outputs = _decimal("slo_output_tokens", slo_output_tokens, nonnegative=True)
    weight = _decimal("input_token_weight", input_token_weight, nonnegative=True)
    sensitivity = _decimal(
        "non_gpu_sensitivity_fraction", non_gpu_sensitivity_fraction, nonnegative=True
    )
    if slo_inputs > inputs or slo_outputs > outputs:
        raise ContractError("SLO token counts cannot exceed measured token counts")
    measured_floor = hourly * seconds / Decimal(3600)
    gpu_cost = max(reported, measured_floor)
    blended = inputs + outputs
    output_equivalent = outputs + inputs * weight
    slo_blended = slo_inputs + slo_outputs
    if output_equivalent <= 0 or slo_blended <= 0:
        raise ContractError("economic denominators must be positive")
    million = Decimal(1_000_000)
    return {
        "gpu_cost_usd": _format(gpu_cost),
        "gpu_usd_per_million_input_tokens": _format(gpu_cost * million / inputs),
        "gpu_usd_per_million_output_tokens": _format(gpu_cost * million / outputs),
        "gpu_usd_per_million_blended_tokens": _format(gpu_cost * million / blended),
        "gpu_usd_per_million_output_equivalent_tokens": _format(
            gpu_cost * million / output_equivalent
        ),
        "slo_gpu_usd_per_million_blended_tokens": _format(
            gpu_cost * million / slo_blended
        ),
        "input_token_weight": _format(weight),
        "non_gpu_sensitivity_fraction": _format(sensitivity),
        "sensitivity_reserved_usd": _format(gpu_cost * sensitivity),
    }


def _require_exact_keys(value, required, path):
    if not isinstance(value, dict):
        raise ContractError(f"{path} must be an object")
    missing = sorted(set(required) - set(value))
    unknown = sorted(set(value) - set(required))
    if missing:
        raise ContractError(f"{path} missing required fields: {', '.join(missing)}")
    if unknown:
        raise ContractError(f"{path} has unknown fields: {', '.join(unknown)}")


def _require_sha(name, value):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ContractError(f"{name} must be a lowercase SHA-256")


def _require_utc(name, value):
    if not isinstance(value, str) or not UTC.fullmatch(value):
        raise ContractError(f"{name} must be an RFC3339 UTC timestamp")


def _read_bound_json(path, expected_sha256, name):
    if path is None:
        raise ContractError(f"{name} path is required")
    try:
        payload = Path(path).read_bytes()
    except OSError as error:
        raise ContractError(f"cannot read {name}: {error}") from error
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ContractError(f"{name} hash mismatch")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid {name} JSON: {error}") from error
    if not isinstance(value, dict):
        raise ContractError(f"{name} must be an object")
    return value


def _validate_bound_baseline(baseline):
    if baseline.get("schema_version") != 1:
        raise ContractError("campaign baseline schema version must be 1")
    if baseline.get("signed_off") is not True:
        raise ContractError("bound campaign baseline is not signed off")
    if baseline.get("reconciliation_status") not in {"authoritative", "conservative"}:
        raise ContractError("bound campaign baseline reconciliation is invalid")
    if _decimal("baseline.campaign_cap_usd", baseline.get("campaign_cap_usd"), positive=True) != Decimal("100.00"):
        raise ContractError("bound campaign baseline cap must be 100.00 USD")
    _decimal(
        "baseline.campaign_additional_spend_usd",
        baseline.get("campaign_additional_spend_usd"),
        nonnegative=True,
    )


def _validate_bound_inventory(inventory, expected_active_count):
    if inventory.get("schema_version") != 1:
        raise ContractError("inventory snapshot schema version must be 1")
    active = inventory.get("active_campaign_pods")
    if not isinstance(active, list):
        raise ContractError("inventory snapshot requires active_campaign_pods")
    if len(active) != expected_active_count:
        raise ContractError("active campaign pod count differs from bound inventory")


def admit_budget(
    request,
    *,
    baseline_path=None,
    inventory_snapshot_path=None,
    watchdog_contract_path=None,
):
    fields = {
        "schema_version",
        "baseline_sha256",
        "baseline_signed_off",
        "reconciliation_status",
        "campaign_cap_usd",
        "campaign_additional_spend_usd",
        "phase",
        "phase_cumulative_cap_usd",
        "hourly_price_usd",
        "maximum_deadline_seconds",
        "recorded_maximum_deadline_cost_usd",
        "active_campaign_pod_count",
        "inventory_snapshot_sha256",
        "watchdog_contract_sha256",
    }
    _require_exact_keys(request, fields, "budget admission")
    if request["schema_version"] != "1.0.0":
        raise ContractError("unsupported budget admission schema version")
    _require_sha("baseline_sha256", request["baseline_sha256"])
    _require_sha("inventory_snapshot_sha256", request["inventory_snapshot_sha256"])
    _require_sha("watchdog_contract_sha256", request["watchdog_contract_sha256"])
    if request["baseline_signed_off"] is not True:
        raise ContractError("campaign baseline must be signed off")
    if request["reconciliation_status"] not in {"authoritative", "conservative"}:
        raise ContractError("spend reconciliation must be authoritative or conservative")
    if request["phase"] not in {"B", "C", "D", "E", "F", "RESERVE"}:
        raise ContractError("GPU admission is unavailable in this phase")
    if type(request["active_campaign_pod_count"]) is not int:
        raise ContractError("active_campaign_pod_count must be an integer")
    if request["active_campaign_pod_count"] != 0:
        raise ContractError("another campaign pod is active")
    if type(request["maximum_deadline_seconds"]) is not int or not 1 <= request["maximum_deadline_seconds"] <= 7200:
        raise ContractError("maximum_deadline_seconds must be in [1, 7200]")
    cap = _decimal("campaign_cap_usd", request["campaign_cap_usd"], positive=True)
    if cap != Decimal("100.00"):
        raise ContractError("campaign cap must remain exactly 100.00 USD")
    spend = _decimal(
        "campaign_additional_spend_usd",
        request["campaign_additional_spend_usd"],
        nonnegative=True,
    )
    phase_cap = _decimal(
        "phase_cumulative_cap_usd", request["phase_cumulative_cap_usd"], positive=True
    )
    frozen_phase_caps = {
        "B": Decimal("20.00"),
        "C": Decimal("35.00"),
        "D": Decimal("45.00"),
        "E": Decimal("75.00"),
        "F": Decimal("90.00"),
        "RESERVE": Decimal("100.00"),
    }
    if phase_cap != frozen_phase_caps[request["phase"]]:
        raise ContractError("phase cumulative cap differs from the frozen plan")
    hourly = _decimal("hourly_price_usd", request["hourly_price_usd"], positive=True)
    exact_maximum_cost = hourly * Decimal(request["maximum_deadline_seconds"]) / Decimal(3600)
    recorded = _decimal(
        "recorded_maximum_deadline_cost_usd",
        request["recorded_maximum_deadline_cost_usd"],
        nonnegative=True,
    )
    if recorded < exact_maximum_cost:
        raise ContractError("recorded maximum deadline cost rounds below exact exposure")
    baseline = _read_bound_json(
        baseline_path, request["baseline_sha256"], "campaign baseline"
    )
    _validate_bound_baseline(baseline)
    inventory = _read_bound_json(
        inventory_snapshot_path,
        request["inventory_snapshot_sha256"],
        "inventory snapshot",
    )
    _validate_bound_inventory(inventory, request["active_campaign_pod_count"])
    watchdog = _read_bound_json(
        watchdog_contract_path,
        request["watchdog_contract_sha256"],
        "watchdog contract",
    )
    validate_watchdog(watchdog)
    if watchdog["maximum_deadline_seconds"] != request["maximum_deadline_seconds"]:
        raise ContractError("watchdog and admission maximum deadlines differ")
    projected = spend + recorded
    if projected > cap:
        raise ContractError("maximum deadline exposure breaches campaign cap")
    if projected > phase_cap:
        raise ContractError("maximum deadline exposure breaches cumulative phase cap")
    return {
        "decision": "admit",
        "exact_maximum_deadline_cost_usd": _format(exact_maximum_cost),
        "projected_campaign_spend_usd": _format(projected),
    }


def validate_watchdog(contract):
    fields = {
        "schema_version",
        "independent_process",
        "absolute_deadline_utc",
        "maximum_deadline_seconds",
        "delete_on_deadline",
        "delete_on_orchestrator_exit",
        "delete_if_harvest_fails",
        "verify_deleted_via_api",
        "poll_interval_seconds",
        "watchdog_log_path",
    }
    _require_exact_keys(contract, fields, "watchdog")
    if contract["schema_version"] != "1.0.0":
        raise ContractError("unsupported watchdog schema version")
    _require_utc("absolute_deadline_utc", contract["absolute_deadline_utc"])
    for key in (
        "independent_process",
        "delete_on_deadline",
        "delete_on_orchestrator_exit",
        "delete_if_harvest_fails",
        "verify_deleted_via_api",
    ):
        if contract[key] is not True:
            raise ContractError(f"{key} must be true")
    for key in ("maximum_deadline_seconds", "poll_interval_seconds"):
        if type(contract[key]) is not int or contract[key] <= 0:
            raise ContractError(f"{key} must be a positive integer")
    if contract["maximum_deadline_seconds"] > 7200:
        raise ContractError("maximum_deadline_seconds exceeds contract ceiling")
    if contract["poll_interval_seconds"] > 60:
        raise ContractError("watchdog poll interval exceeds 60 seconds")
    path = contract["watchdog_log_path"]
    if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
        raise ContractError("watchdog_log_path must be a safe relative path")


def _percentiles(value, path):
    _require_exact_keys(value, {"p50", "p95", "p99"}, path)
    numbers = []
    for key in ("p50", "p95", "p99"):
        number = _decimal(f"{path}.{key}", value[key], nonnegative=True)
        numbers.append(number)
    if numbers != sorted(numbers):
        raise ContractError(f"{path} percentiles must be monotonic")


def _require_rate(name, observed, numerator, denominator):
    actual = _decimal(name, observed, nonnegative=True)
    expected = Decimal(numerator) / Decimal(str(denominator))
    tolerance = max(Decimal("0.000001"), abs(expected) * Decimal("0.000001"))
    if abs(actual - expected) > tolerance:
        raise ContractError(f"{name} differs from token/request arithmetic")


def _request_latency(row, name, *, required):
    value = row[name]
    if value is None and not required:
        return None
    return _decimal(f"request_outcomes.{name}", value, nonnegative=True)


def _validate_request_outcomes(payload, metrics, service_contract):
    try:
        rows = [json.loads(line) for line in payload.decode().splitlines() if line]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError(f"invalid request_outcomes JSONL: {error}") from error
    fields = {
        "request_id",
        "completed",
        "slo_eligible",
        "slo_compliant",
        "error",
        "silent_truncation",
        "input_tokens",
        "output_tokens",
        "ttft_ms",
        "inter_token_latency_ms",
        "end_to_end_ms",
    }
    request_ids = set()
    derived = {
        "requests_scheduled": len(rows),
        "requests_completed": 0,
        "requests_slo_eligible": 0,
        "requests_slo_compliant": 0,
        "errors": 0,
        "silent_truncations": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "slo_input_tokens": 0,
        "slo_output_tokens": 0,
    }
    for index, row in enumerate(rows):
        _require_exact_keys(row, fields, f"request_outcomes[{index}]")
        request_id = row["request_id"]
        if not isinstance(request_id, str) or not request_id or request_id in request_ids:
            raise ContractError("request outcome IDs must be unique nonempty strings")
        request_ids.add(request_id)
        for name in (
            "completed",
            "slo_eligible",
            "slo_compliant",
            "error",
            "silent_truncation",
        ):
            if type(row[name]) is not bool:
                raise ContractError(f"request_outcomes[{index}].{name} must be boolean")
        for name in ("input_tokens", "output_tokens"):
            if type(row[name]) is not int or row[name] < 0:
                raise ContractError(f"request_outcomes[{index}].{name} must be a nonnegative integer")
        requires_latency = row["completed"] and row["slo_eligible"]
        ttft = _request_latency(row, "ttft_ms", required=requires_latency)
        inter_token = _request_latency(
            row, "inter_token_latency_ms", required=requires_latency
        )
        _request_latency(row, "end_to_end_ms", required=row["completed"])
        is_compliant = (
            requires_latency
            and not row["error"]
            and not row["silent_truncation"]
            and ttft <= Decimal(service_contract["max_p95_ttft_ms"])
            and inter_token <= Decimal(service_contract["max_p95_itl_ms"])
        )
        if row["slo_compliant"] is not is_compliant:
            raise ContractError("request SLO compliance differs from frozen thresholds")
        derived["requests_completed"] += int(row["completed"])
        derived["requests_slo_eligible"] += int(row["slo_eligible"])
        derived["requests_slo_compliant"] += int(is_compliant)
        derived["errors"] += int(row["error"])
        derived["silent_truncations"] += int(row["silent_truncation"])
        derived["input_tokens"] += row["input_tokens"]
        derived["output_tokens"] += row["output_tokens"]
        if is_compliant:
            derived["slo_input_tokens"] += row["input_tokens"]
            derived["slo_output_tokens"] += row["output_tokens"]
    for name, expected in derived.items():
        if metrics[name] != expected:
            raise ContractError(f"metrics.{name} differs from request_outcomes")


def validate_gpu_artifact(artifact_path, bundle_root=None):
    artifact_path = Path(artifact_path)
    bundle_root = Path(bundle_root) if bundle_root else artifact_path.parent
    try:
        artifact = json.loads(artifact_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read artifact JSON: {error}") from error
    top = {
        "schema_version", "artifact_id", "experiment_spec_sha256", "workload_sha256",
        "model", "runtime", "hardware", "allocation", "service_contract", "metrics",
        "telemetry", "teardown", "validator",
    }
    _require_exact_keys(artifact, top, "artifact")
    if artifact["schema_version"] != "1.0.0":
        raise ContractError("unsupported artifact schema version")
    for key in ("experiment_spec_sha256", "workload_sha256"):
        _require_sha(key, artifact[key])
    _require_exact_keys(artifact["model"], {"model_id", "checkpoint_revision", "tokenizer_revision", "representation"}, "model")
    _require_exact_keys(artifact["runtime"], {"name", "source_revision", "image_digest", "command_sha256"}, "runtime")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact["runtime"]["image_digest"]):
        raise ContractError("runtime.image_digest must pin a sha256 digest")
    _require_sha("runtime.command_sha256", artifact["runtime"]["command_sha256"])
    _require_exact_keys(artifact["hardware"], {"provider", "cloud_class", "gpu_model", "gpu_count", "machine_id"}, "hardware")
    if type(artifact["hardware"]["gpu_count"]) is not int or artifact["hardware"]["gpu_count"] <= 0:
        raise ContractError("hardware.gpu_count must be positive")
    allocation_fields = {"provider_allocation_id", "started_at", "ended_at", "allocation_seconds", "hourly_price_usd", "provider_reported_cost_usd", "conservative_cost_usd"}
    _require_exact_keys(artifact["allocation"], allocation_fields, "allocation")
    for key in ("started_at", "ended_at"):
        _require_utc(f"allocation.{key}", artifact["allocation"][key])
    seconds = _decimal("allocation_seconds", artifact["allocation"]["allocation_seconds"], positive=True)
    hourly = _decimal("hourly_price_usd", artifact["allocation"]["hourly_price_usd"], positive=True)
    reported = _decimal("provider_reported_cost_usd", artifact["allocation"]["provider_reported_cost_usd"], nonnegative=True)
    conservative = _decimal("conservative_cost_usd", artifact["allocation"]["conservative_cost_usd"], nonnegative=True)
    if conservative < max(reported, hourly * seconds / Decimal(3600)):
        raise ContractError("conservative cost is below its defensible floor")
    service_fields = {"max_p95_ttft_ms", "max_p95_itl_ms", "min_request_success_fraction", "silent_truncation_allowed"}
    _require_exact_keys(artifact["service_contract"], service_fields, "service_contract")
    if artifact["service_contract"] != {"max_p95_ttft_ms": 10000, "max_p95_itl_ms": 100, "min_request_success_fraction": 0.99, "silent_truncation_allowed": False}:
        raise ContractError("service contract differs from frozen campaign SLO")
    metric_fields = {"requests_scheduled", "requests_completed", "requests_slo_eligible", "requests_slo_compliant", "errors", "silent_truncations", "input_tokens", "output_tokens", "slo_input_tokens", "slo_output_tokens", "wall_seconds", "input_tokens_per_second", "output_tokens_per_second", "total_tokens_per_second", "completed_request_goodput_per_second", "latency_ms"}
    _require_exact_keys(artifact["metrics"], metric_fields, "metrics")
    for key in metric_fields - {"latency_ms"}:
        _decimal(f"metrics.{key}", artifact["metrics"][key], nonnegative=True)
    scheduled = artifact["metrics"]["requests_scheduled"]
    completed = artifact["metrics"]["requests_completed"]
    eligible = artifact["metrics"]["requests_slo_eligible"]
    compliant = artifact["metrics"]["requests_slo_compliant"]
    if not 0 <= compliant <= eligible <= completed <= scheduled:
        raise ContractError("request counters are not internally ordered")
    if artifact["metrics"]["errors"] > scheduled:
        raise ContractError("error count exceeds scheduled requests")
    if artifact["metrics"]["slo_input_tokens"] > artifact["metrics"]["input_tokens"] or artifact["metrics"]["slo_output_tokens"] > artifact["metrics"]["output_tokens"]:
        raise ContractError("SLO token counts exceed total token counts")
    wall_seconds = _decimal(
        "metrics.wall_seconds", artifact["metrics"]["wall_seconds"], positive=True
    )
    _require_rate(
        "metrics.input_tokens_per_second",
        artifact["metrics"]["input_tokens_per_second"],
        artifact["metrics"]["input_tokens"],
        wall_seconds,
    )
    _require_rate(
        "metrics.output_tokens_per_second",
        artifact["metrics"]["output_tokens_per_second"],
        artifact["metrics"]["output_tokens"],
        wall_seconds,
    )
    _require_rate(
        "metrics.total_tokens_per_second",
        artifact["metrics"]["total_tokens_per_second"],
        artifact["metrics"]["input_tokens"] + artifact["metrics"]["output_tokens"],
        wall_seconds,
    )
    _require_rate(
        "metrics.completed_request_goodput_per_second",
        artifact["metrics"]["completed_request_goodput_per_second"],
        artifact["metrics"]["requests_completed"],
        wall_seconds,
    )
    _require_exact_keys(artifact["metrics"]["latency_ms"], {"ttft", "inter_token", "end_to_end"}, "metrics.latency_ms")
    for name, values in artifact["metrics"]["latency_ms"].items():
        _percentiles(values, f"metrics.latency_ms.{name}")
    telemetry_fields = {"cadence_seconds", "gpu", "memory_throughput", "scheduler", "startup", "profiler", "raw_files"}
    _require_exact_keys(artifact["telemetry"], telemetry_fields, "telemetry")
    _decimal("telemetry.cadence_seconds", artifact["telemetry"]["cadence_seconds"], positive=True)
    gpu_fields = {"utilization_percent", "vram_used_bytes", "power_watts", "temperature_celsius", "sm_clock_mhz", "memory_clock_mhz"}
    _require_exact_keys(artifact["telemetry"]["gpu"], gpu_fields, "telemetry.gpu")
    for name, values in artifact["telemetry"]["gpu"].items():
        _percentiles(values, f"telemetry.gpu.{name}")
    memory = artifact["telemetry"]["memory_throughput"]
    _require_exact_keys(memory, {"status", "metric_name", "value", "unit"}, "telemetry.memory_throughput")
    if memory["status"] not in {"measured", "unsupported"}:
        raise ContractError("memory throughput status must be measured or unsupported")
    if memory["status"] == "measured" and (not memory["metric_name"] or memory["value"] is None or not memory["unit"]):
        raise ContractError("measured memory throughput needs a named value and unit")
    if memory["status"] == "unsupported" and (memory["metric_name"] is not None or memory["value"] is not None or memory["unit"] is not None):
        raise ContractError("unsupported memory throughput must use explicit nulls")
    scheduler_fields = {"iteration_count", "batch_size", "prefill_tokens", "decode_tokens", "kv_allocated_tokens_peak", "prefix_cache_hits", "prefix_cache_misses"}
    _require_exact_keys(artifact["telemetry"]["scheduler"], scheduler_fields, "telemetry.scheduler")
    _percentiles(artifact["telemetry"]["scheduler"]["batch_size"], "telemetry.scheduler.batch_size")
    for key in scheduler_fields - {"batch_size"}:
        _decimal(f"telemetry.scheduler.{key}", artifact["telemetry"]["scheduler"][key], nonnegative=True)
    startup_fields = {"container_seconds", "model_load_seconds", "cache_allocation_seconds", "server_ready_seconds"}
    _require_exact_keys(artifact["telemetry"]["startup"], startup_fields, "telemetry.startup")
    for key in startup_fields:
        _decimal(f"telemetry.startup.{key}", artifact["telemetry"]["startup"][key], nonnegative=True)
    profiler = artifact["telemetry"]["profiler"]
    _require_exact_keys(profiler, {"capture_seconds", "overhead_percent", "trace_sha256", "top_kernels"}, "telemetry.profiler")
    _require_sha("telemetry.profiler.trace_sha256", profiler["trace_sha256"])
    if not isinstance(profiler["top_kernels"], list) or not profiler["top_kernels"]:
        raise ContractError("profiler top_kernels must be nonempty")
    for index, kernel in enumerate(profiler["top_kernels"]):
        _require_exact_keys(kernel, {"name", "time_share_fraction"}, f"top_kernels[{index}]")
        share = _decimal("time_share_fraction", kernel["time_share_fraction"], nonnegative=True)
        if share > 1:
            raise ContractError("kernel time share cannot exceed one")
    raw_files = artifact["telemetry"]["raw_files"]
    if not isinstance(raw_files, list) or not raw_files:
        raise ContractError("telemetry.raw_files must be nonempty")
    required_raw_kinds = {
        "gpu_samples",
        "request_outcomes",
        "scheduler_samples",
        "startup_timings",
        "provider_billing",
        "profiler_trace",
    }
    raw_kinds = {raw.get("kind") for raw in raw_files if isinstance(raw, dict)}
    if not required_raw_kinds <= raw_kinds:
        missing = sorted(required_raw_kinds - raw_kinds)
        raise ContractError(f"missing raw evidence kinds: {', '.join(missing)}")
    raw_paths = [raw.get("path") for raw in raw_files if isinstance(raw, dict)]
    if len(raw_paths) != len(set(raw_paths)):
        raise ContractError("raw evidence paths must be unique")
    raw_payloads_by_kind = {}
    for index, raw in enumerate(raw_files):
        _require_exact_keys(raw, {"path", "sha256", "bytes", "kind"}, f"raw_files[{index}]")
        _require_sha(f"raw_files[{index}].sha256", raw["sha256"])
        relative = Path(raw["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ContractError("raw telemetry path must stay inside bundle")
        target = bundle_root / relative
        try:
            payload = target.read_bytes()
        except OSError as error:
            raise ContractError(f"raw telemetry missing: {relative}") from error
        if len(payload) != raw["bytes"] or hashlib.sha256(payload).hexdigest() != raw["sha256"]:
            raise ContractError(f"raw telemetry identity mismatch: {relative}")
        raw_payloads_by_kind.setdefault(raw["kind"], []).append(payload)
    request_outcomes = raw_payloads_by_kind.get("request_outcomes", [])
    if len(request_outcomes) != 1:
        raise ContractError("exactly one request_outcomes raw file is required")
    _validate_request_outcomes(
        request_outcomes[0], artifact["metrics"], artifact["service_contract"]
    )
    raw_hashes = {raw["sha256"] for raw in raw_files}
    if profiler["trace_sha256"] not in raw_hashes:
        raise ContractError("profiler trace hash is not bound to a raw file")
    teardown = artifact["teardown"]
    _require_exact_keys(teardown, {"delete_requested_at", "delete_http_status", "get_http_status", "verified_at", "verification", "watchdog_log_sha256"}, "teardown")
    _require_utc("teardown.delete_requested_at", teardown["delete_requested_at"])
    _require_utc("teardown.verified_at", teardown["verified_at"])
    _require_sha("teardown.watchdog_log_sha256", teardown["watchdog_log_sha256"])
    if teardown["delete_http_status"] != 204:
        raise ContractError("teardown DELETE must return HTTP 204")
    if teardown["get_http_status"] != 404 or teardown["verification"] != "not_found":
        raise ContractError("teardown must be verified by follow-up GET HTTP 404")
    validator = artifact["validator"]
    _require_exact_keys(validator, {"name", "version", "result", "validated_at"}, "validator")
    _require_utc("validator.validated_at", validator["validated_at"])
    if validator["result"] != "pass":
        raise ContractError("artifact validator result is not pass")


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    artifact = subparsers.add_parser("artifact")
    artifact.add_argument("artifact_json")
    artifact.add_argument("--bundle-root")
    budget = subparsers.add_parser("budget")
    budget.add_argument("request_json")
    budget.add_argument("--baseline", required=True)
    budget.add_argument("--inventory-snapshot", required=True)
    budget.add_argument("--watchdog-contract", required=True)
    watchdog = subparsers.add_parser("watchdog")
    watchdog.add_argument("contract_json")
    args = parser.parse_args()
    try:
        if args.command == "artifact":
            validate_gpu_artifact(args.artifact_json, args.bundle_root)
            result = {"result": "pass"}
        elif args.command == "budget":
            result = admit_budget(
                json.loads(Path(args.request_json).read_text()),
                baseline_path=args.baseline,
                inventory_snapshot_path=args.inventory_snapshot,
                watchdog_contract_path=args.watchdog_contract,
            )
        else:
            validate_watchdog(json.loads(Path(args.contract_json).read_text()))
            result = {"result": "pass"}
    except (ContractError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"result": "fail", "error": str(error)}, sort_keys=True))
        raise SystemExit(1)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
