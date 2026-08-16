import argparse
import copy
import hashlib
import json
from decimal import Decimal
from pathlib import Path


class ArtifactBuildError(ValueError):
    pass


SERVICE_CONTRACT = {
    "max_p95_ttft_ms": 10000,
    "max_p95_itl_ms": 100,
    "min_request_success_fraction": 0.99,
    "silent_truncation_allowed": False,
}

IDENTITY_FIELDS = {
    "artifact_id",
    "experiment_spec_sha256",
    "workload_sha256",
    "model",
    "runtime",
    "hardware",
}


def _require_exact_fields(value, fields, name):
    if not isinstance(value, dict):
        raise ArtifactBuildError(f"{name} must be an object")
    missing = fields - value.keys()
    unknown = value.keys() - fields
    if missing:
        raise ArtifactBuildError(f"{name} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise ArtifactBuildError(f"{name} has unknown fields: {', '.join(sorted(unknown))}")


def write_internal_manifest(bundle_root, output_path):
    bundle_root = Path(bundle_root).resolve()
    output_path = Path(output_path).resolve()
    if output_path != bundle_root and bundle_root not in output_path.parents:
        raise ArtifactBuildError("internal manifest output escapes the bundle")
    rows = []
    for path in sorted(bundle_root.rglob("*")):
        if path.is_file() and path.resolve() != output_path:
            payload = path.read_bytes()
            rows.append(
                {
                    "path": path.relative_to(bundle_root).as_posix(),
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, indent=2) + "\n")
    return rows


def _safe_raw_file(bundle_root, relative_name):
    relative = Path(relative_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ArtifactBuildError(f"raw evidence path escapes bundle: {relative_name}")
    root = bundle_root.resolve()
    target = (root / relative).resolve()
    if target == root or root not in target.parents:
        raise ArtifactBuildError(f"raw evidence path escapes bundle: {relative_name}")
    if not target.is_file():
        raise ArtifactBuildError(f"raw evidence file is missing: {relative_name}")
    payload = target.read_bytes()
    if not payload:
        raise ArtifactBuildError(f"raw evidence file is empty: {relative_name}")
    return relative.as_posix(), payload


def _raw_files(bundle_root, raw_kinds):
    if not isinstance(raw_kinds, dict) or not raw_kinds:
        raise ArtifactBuildError("raw_kinds must map paths to evidence kinds")
    rows = []
    kinds = set()
    normalized_paths = set()
    for relative_name, kind in sorted(raw_kinds.items()):
        if not isinstance(kind, str) or not kind:
            raise ArtifactBuildError(f"raw evidence kind is invalid: {relative_name}")
        normalized, payload = _safe_raw_file(bundle_root, relative_name)
        if normalized in normalized_paths:
            raise ArtifactBuildError(f"duplicate raw evidence path: {normalized}")
        normalized_paths.add(normalized)
        kinds.add(kind)
        rows.append(
            {
                "path": normalized,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
                "kind": kind,
            }
        )
    required = {
        "gpu_samples",
        "request_outcomes",
        "scheduler_samples",
        "startup_timings",
        "provider_billing",
        "profiler_trace",
    }
    missing = required - kinds
    if missing:
        raise ArtifactBuildError(f"raw evidence kinds are missing: {', '.join(sorted(missing))}")
    return rows


def _conservative_cost(allocation):
    try:
        hourly = Decimal(str(allocation["hourly_price_usd"]))
        seconds = Decimal(str(allocation["allocation_seconds"]))
        reported = Decimal(str(allocation["provider_reported_cost_usd"]))
    except (KeyError, ArithmeticError, ValueError) as error:
        raise ArtifactBuildError(f"invalid allocation arithmetic: {error}") from error
    if hourly <= 0 or seconds <= 0 or reported < 0:
        raise ArtifactBuildError("allocation price and duration must be positive")
    return max(reported, hourly * seconds / Decimal(3600))


def build_artifact(
    *,
    bundle_root,
    raw_kinds,
    identity,
    allocation,
    metrics,
    telemetry,
    teardown,
    validated_at,
    input_token_weight,
    non_gpu_sensitivity_fraction,
):
    try:
        from validate_contracts import calculate_economics
    except ImportError:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "specs"))
        from validate_contracts import calculate_economics

    bundle_root = Path(bundle_root)
    _require_exact_fields(identity, IDENTITY_FIELDS, "identity")
    allocation_copy = copy.deepcopy(allocation)
    expected_allocation_fields = {
        "provider_allocation_id",
        "started_at",
        "ended_at",
        "allocation_seconds",
        "hourly_price_usd",
        "provider_reported_cost_usd",
    }
    _require_exact_fields(allocation_copy, expected_allocation_fields, "allocation")
    conservative_cost = _conservative_cost(allocation_copy)
    allocation_copy["conservative_cost_usd"] = float(conservative_cost)

    raw_files = _raw_files(bundle_root, raw_kinds)
    telemetry_copy = copy.deepcopy(telemetry)
    if "raw_files" in telemetry_copy:
        raise ArtifactBuildError("telemetry.raw_files is owned by the artifact builder")
    telemetry_copy["raw_files"] = raw_files

    profiler_hash = telemetry_copy.get("profiler", {}).get("trace_sha256")
    profiler_hashes = {
        row["sha256"] for row in raw_files if row["kind"] == "profiler_trace"
    }
    if profiler_hash not in profiler_hashes:
        raise ArtifactBuildError("profiler trace is not bound to raw profiler evidence")

    artifact = {
        "schema_version": "1.0.0",
        "artifact_id": identity["artifact_id"],
        "experiment_spec_sha256": identity["experiment_spec_sha256"],
        "workload_sha256": identity["workload_sha256"],
        "model": copy.deepcopy(identity["model"]),
        "runtime": copy.deepcopy(identity["runtime"]),
        "hardware": copy.deepcopy(identity["hardware"]),
        "allocation": allocation_copy,
        "service_contract": copy.deepcopy(SERVICE_CONTRACT),
        "metrics": copy.deepcopy(metrics),
        "telemetry": telemetry_copy,
        "teardown": copy.deepcopy(teardown),
        "validator": {
            "name": "campaign_100_validate_contracts",
            "version": "1.0.0",
            "result": "pass",
            "validated_at": validated_at,
        },
    }
    economics = calculate_economics(
        allocation_copy["hourly_price_usd"],
        allocation_copy["allocation_seconds"],
        allocation_copy["provider_reported_cost_usd"],
        metrics["input_tokens"],
        metrics["output_tokens"],
        metrics["slo_input_tokens"],
        metrics["slo_output_tokens"],
        input_token_weight,
        non_gpu_sensitivity_fraction,
    )
    return artifact, economics


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    manifest = subparsers.add_parser("manifest")
    manifest.add_argument("--bundle-root", required=True, type=Path)
    manifest.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.command == "manifest":
        write_internal_manifest(arguments.bundle_root, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
