from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_PHASES = ("allocation", "startup", "warmup", "benchmark", "teardown")
REQUIRED_IDENTITIES = ("run_id", "model", "model_revision", "workload_id", "workload_hash", "slo_id")


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    economic_win_permitted: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    metrics: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _first_number(document: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = document.get(key)
        result = _number(value)
        if result is not None:
            return result
    return None


def _benchmark_metrics(path: Path) -> dict[str, float] | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        document = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict):
        return None
    input_tokens = _first_number(document, "total_input_tokens", "input_tokens", "prompt_tokens")
    output_tokens = _first_number(document, "total_output_tokens", "output_tokens", "completion_tokens")
    duration = _first_number(document, "duration", "duration_seconds", "elapsed_time")
    if input_tokens is None or output_tokens is None or duration is None or duration <= 0:
        return None
    ttft = _first_number(document, "mean_ttft_ms", "median_ttft_ms", "ttft_ms")
    tpot = _first_number(document, "mean_tpot_ms", "median_tpot_ms", "tpot_ms")
    requests = _first_number(document, "completed", "completed_requests", "num_prompts", "request_count")
    errors = _first_number(document, "failed", "failed_requests", "error_count") or 0.0
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_seconds": duration,
        "request_count": requests or 0.0,
        "error_count": errors,
        "ttft_ms": ttft if ttft is not None else math.nan,
        "tpot_ms": tpot if tpot is not None else math.nan,
        "throughput_output_tokens_per_second": output_tokens / duration,
        "throughput_total_tokens_per_second": (input_tokens + output_tokens) / duration,
        "error_rate": errors / (requests or 1.0),
    }


def _telemetry(path: Path, allocation_seconds: float) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {"samples": 0, "phase_summaries": {}, "whole_allocation": None}
    rows: list[dict[str, float | str]] = []
    with path.open(newline="") as handle:
        first = handle.readline()
        handle.seek(0)
        raw_rows = csv.reader(handle) if first and first[:1].isdigit() else None
        source = ({"phase": "unknown", "utilization.gpu": row[3] if len(row) > 3 else "", "power.draw": row[7] if len(row) > 7 else ""} for row in raw_rows) if raw_rows is not None else csv.DictReader(handle)
        for row in source:
            def value(*names: str) -> float | str | None:
                for name in names:
                    if name in row and row[name].strip():
                        parsed = _number(row[name].replace("%", "").replace(" W", ""))
                        return parsed if parsed is not None else row[name].strip()
                return None
            gpu = value("utilization.gpu [%]", "utilization.gpu", "gpu_utilization")
            power = value("power.draw [W]", "power.draw", "power_watts")
            phase = value("phase")
            if isinstance(gpu, (int, float)):
                rows.append({"gpu": gpu, "power": power if isinstance(power, (int, float)) else math.nan, "phase": phase or "unknown"})
    def summary(items: list[dict[str, float | str]]) -> dict[str, Any]:
        gpu = [float(item["gpu"]) for item in items]
        power = [float(item["power"]) for item in items if math.isfinite(float(item["power"]))]
        def ci(values: list[float]) -> dict[str, float] | None:
            if not values:
                return None
            margin = 0.0 if len(values) < 2 else 1.96 * statistics.stdev(values) / math.sqrt(len(values))
            return {"mean": statistics.mean(values), "ci95_half_width": margin, "samples": len(values)}
        return {"hardware_busy_utilization_pct": ci(gpu), "power_watts": ci(power)}
    phases = {str(phase): summary([row for row in rows if row["phase"] == phase]) for phase in {str(row["phase"]) for row in rows}}
    allocation = summary(rows)
    allocation["whole_allocation_utilization_pct"] = (statistics.mean([float(row["gpu"]) for row in rows]) * len(rows) / max(len(rows), allocation_seconds)) if rows else None
    return {"samples": len(rows), "phase_summaries": phases, "whole_allocation": allocation, "commercial_fleet_utilization_pct": None}


def _validate_directory(root: Path, ledger: dict[str, Any] | None = None) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    contract_path = root / "contract.json"
    contract = json.loads(contract_path.read_text()) if contract_path.exists() else {}
    ledger = ledger or {}
    identity = {**ledger.get("identity", {}), **contract.get("identity", {})}
    for key in REQUIRED_IDENTITIES:
        if not identity.get(key):
            errors.append(f"missing identity: {key}")
    provenance = contract.get("provenance", {})
    if provenance.get("result_kind") != "measured":
        errors.append("economic result provenance must be measured")
    if provenance.get("published_inputs_used"):
        errors.append("mixed published/measured provenance blocks economic win claim")
    phases = contract.get("phases", [])
    names = {phase.get("name") for phase in phases if isinstance(phase, dict)}
    for phase in REQUIRED_PHASES:
        item = next((candidate for candidate in phases if candidate.get("name") == phase), None)
        if item is None:
            errors.append(f"missing phase marker: {phase}")
        else:
            if not item.get("started_at") or not item.get("finished_at"):
                errors.append(f"incomplete phase marker: {phase}")
            if phase in {"benchmark", "teardown"} and "missing_counters" not in item:
                errors.append(f"missing explicit missing_counters: {phase}")
            if item.get("missing_counters"):
                errors.append(f"missing counters in phase: {phase}")
    if names and names != set(REQUIRED_PHASES):
        errors.append("phase coverage is not exactly full-allocation coverage")
    if not (contract.get("server", {}).get("healthy") is True):
        errors.append("server failure or missing server health evidence")
    if contract.get("teardown", {}).get("complete") is not True:
        errors.append("incomplete teardown")
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        errors.append("missing artifact manifest")
    else:
        for entry in json.loads(manifest_path.read_text()):
            path = root / entry["name"]
            if not path.exists() or _sha256(path) != entry.get("sha256"):
                errors.append(f"artifact hash mismatch: {entry.get('name')}")
    if not contract.get("workload", {}).get("slo_identity"):
        errors.append("missing workload/SLO identity")
    if not (root / "server.metrics.txt").exists() or (root / "server.metrics.txt").stat().st_size == 0:
        errors.append("missing SGLang serving metrics")
    benchmark = contract.get("benchmark_result")
    result_path = root / benchmark if isinstance(benchmark, str) else None
    result = _benchmark_metrics(result_path) if result_path else None
    if result is None:
        errors.append("missing benchmark result")
    allocation_seconds = _number(ledger.get("allocation_seconds")) or _number(contract.get("allocation_seconds")) or 0.0
    telemetry = _telemetry(root / "telemetry.csv", allocation_seconds)
    if telemetry["samples"] == 0:
        errors.append("missing telemetry samples")
    if telemetry["phase_summaries"] and set(telemetry["phase_summaries"]) != set(REQUIRED_PHASES):
        errors.append("phase-level utilization summaries are incomplete")
    hourly_rate = _number(ledger.get("hourly_rate_usd")) or _number(contract.get("cost", {}).get("hourly_rate_usd"))
    economics: dict[str, Any] = {}
    if result and hourly_rate is not None and allocation_seconds > 0:
        equivalent = result["output_tokens"] + result["input_tokens"] / 8.0
        spend = allocation_seconds * hourly_rate / 3600.0
        economics = {"conservative_spend_usd": spend, "usd_per_input_token": spend / result["input_tokens"], "usd_per_output_token": spend / result["output_tokens"], "usd_per_million_8_to_1_output_equivalent": spend / equivalent * 1_000_000}
    elif not hourly_rate:
        errors.append("missing provider hourly price")
    metrics = {"benchmark": result, "telemetry": telemetry, "economics": economics, "uncertainty": {"telemetry_ci95": telemetry.get("whole_allocation")}}
    return ValidationReport(not errors, not errors and bool(economics), tuple(errors), tuple(warnings), metrics)


def validate_campaign(path: str | Path, ledger_path: str | Path | dict[str, Any] | None = None) -> ValidationReport:
    source = Path(path)
    ledger = ledger_path if isinstance(ledger_path, dict) else (json.loads(Path(ledger_path).read_text()) if ledger_path else None)
    if source.is_dir():
        return _validate_directory(source, ledger)
    with tempfile.TemporaryDirectory() as temporary:
        with tarfile.open(source) as archive:
            destination = Path(temporary).resolve()
            members = archive.getmembers()
            for member in members:
                target = (destination / member.name).resolve()
                if target != destination and destination not in target.parents:
                    raise ValueError("archive contains path traversal")
            archive.extractall(temporary)
        roots = [candidate for candidate in Path(temporary).iterdir() if candidate.is_dir()]
        return _validate_directory(roots[0] if len(roots) == 1 else Path(temporary), ledger)
