from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SCHEMA_VERSION = "inference-foundry.timeloop-external-smoke-report.v1"
REQUEST_SCHEMA_VERSION = "inference-foundry.timeloop-external-smoke-request.v1"
PROBE_SCHEMA_VERSION = "inference-foundry.timeloop-external-probe.v1"
TYPE_BITS = {"bf16": 16, "fp16": 16, "fp32": 32}


def build_report(
    request_path: Path,
    export_path: Path,
    probe_path: Path,
    raw_directory: Path,
) -> dict[str, object]:
    request = _load_object(request_path)
    export = _load_object(export_path)
    probe = _load_object(probe_path)
    _require_schema(request, REQUEST_SCHEMA_VERSION, "request")
    _require_schema(probe, PROBE_SCHEMA_VERSION, "probe")
    reconciliation = _reconcile(export, probe)
    frontend = _require_object(probe, "frontend")
    native = _require_object(probe, "native_backend")
    environment = _require_object(probe, "environment")
    native_status = str(native.get("status", "missing"))
    status = (
        "native_output_unvalidated"
        if native_status == "succeeded"
        else "native_backend_blocked"
    )
    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "request_id": str(request["request_id"]),
        "source_identity": {
            "request_path": str(request_path),
            "request_sha256": _sha256_file(request_path),
            "problem_export_path": str(export_path),
            "problem_export_sha256": _sha256_file(export_path),
            "problem_export_content_id": str(export["content_id"]),
            "probe_path": str(probe_path),
            "probe_sha256": _sha256_file(probe_path),
        },
        "tool_identity": {
            "frontend": _require_object(request, "frontend"),
            "accelergy": _require_object(request, "accelergy"),
            "native_backend": _require_object(request, "native_backend"),
        },
        "environment": environment,
        "problem": {
            "shape_name": frontend.get("shape_name"),
            "dimensions": frontend.get("dimensions"),
            "instance": frontend.get("instance"),
            "tensor_types": _require_object(export, "tensor_types"),
        },
        "reconciliation": reconciliation,
        "runtime": {
            "frontend_parse_nanoseconds": _nonnegative_integer(
                frontend.get("runtime_nanoseconds"), "frontend runtime"
            ),
            "native_probe_nanoseconds": _nonnegative_integer(
                native.get("runtime_nanoseconds"), "native runtime"
            ),
        },
        "backend_result": native,
        "input_artifacts": _input_artifacts(probe),
        "raw_artifacts": _raw_artifacts(raw_directory),
        "claims": {
            "problem_contract_claim_permitted": reconciliation["exact_match"],
            "frontend_parse_claim_permitted": frontend.get("status") == "succeeded",
            "native_mapping_claim_permitted": False,
            "cycle_claim_permitted": False,
            "utilization_claim_permitted": False,
            "calibration_claim_permitted": False,
            "energy_claim_permitted": False,
            "area_claim_permitted": False,
            "cost_claim_permitted": False,
            "performance_claim_permitted": False,
            "blockers": _blockers(frontend, native, environment),
        },
    }
    stable = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    report["content_identity_sha256"] = hashlib.sha256(stable).hexdigest()
    return report


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize a Timeloop external smoke probe."
    )
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--raw-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    try:
        report = build_report(
            args.request,
            args.export,
            args.probe,
            args.raw_directory,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(args.output)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "output": str(args.output),
                "content_id": report["content_identity_sha256"],
                "status": report["status"],
            },
            sort_keys=True,
        )
    )
    return 0


def _reconcile(
    export: dict[str, object], probe: dict[str, object]
) -> dict[str, object]:
    dimensions = _require_object(export, "problem_dimensions")
    accounting = _require_object(export, "accounting")
    tensor_types = _require_object(export, "tensor_types")
    batch = _positive_integer(dimensions.get("batch"), "batch")
    m = _positive_integer(dimensions.get("m"), "m")
    n = _positive_integer(dimensions.get("n"), "n")
    k = _positive_integer(dimensions.get("k"), "k")
    multiply_accumulates = batch * m * n * k
    flops = multiply_accumulates * 2
    input_elements = batch * m * k
    weight_elements = n * k
    output_elements = batch * m * n
    input_bytes = _packed_bytes(input_elements, str(tensor_types.get("input", "")))
    weight_bytes = _packed_bytes(weight_elements, str(tensor_types.get("weight", "")))
    output_bytes = _packed_bytes(output_elements, str(tensor_types.get("output", "")))
    expected = {
        "multiply_accumulates": multiply_accumulates,
        "flops": flops,
        "input_elements": input_elements,
        "weight_elements": weight_elements,
        "output_elements": output_elements,
        "input_bytes": input_bytes,
        "weight_bytes": weight_bytes,
        "output_bytes": output_bytes,
    }
    for field, value in expected.items():
        observed = _nonnegative_integer(accounting.get(field), field)
        if observed != value:
            label = "FLOP accounting" if field == "flops" else f"{field} accounting"
            raise ValueError(
                f"{label} does not reconcile: expected {value}, found {observed}"
            )
    frontend = _require_object(probe, "frontend")
    instance = _require_object(frontend, "instance")
    expected_instance = {"B": batch, "M": m, "N": n, "K": k}
    observed_instance = {
        key: _positive_integer(instance.get(key), f"frontend instance {key}")
        for key in expected_instance
    }
    if observed_instance != expected_instance:
        raise ValueError(
            "frontend problem instance does not match the exported dimensions"
        )
    return {
        **expected,
        "total_tensor_bytes": input_bytes + weight_bytes + output_bytes,
        "frontend_instance": observed_instance,
        "exact_match": True,
    }


def _blockers(
    frontend: dict[str, object],
    native: dict[str, object],
    environment: dict[str, object],
) -> list[str]:
    blockers = [
        "native_output_not_normalized",
        "bf16_semantics_not_bound_to_the_official_integer_mac_architecture",
        "architecture_not_calibrated_to_local_or_deployed_hardware",
        "cycles_energy_area_and_cost_unmeasured",
    ]
    if frontend.get("status") != "succeeded":
        blockers.insert(0, "timeloop_frontend_parse_failed")
    if native.get("status") != "succeeded":
        blockers.insert(0, "timeloop_mapper_executable_unavailable")
    dependency_probe = environment.get("native_dependency_probe")
    if isinstance(dependency_probe, dict):
        missing = [
            f"native_dependency_missing:{name}"
            for name, result in sorted(dependency_probe.items())
            if isinstance(result, dict) and result.get("found") is False
        ]
        blockers[1:1] = missing
    return blockers


def _raw_artifacts(directory: Path) -> list[dict[str, object]]:
    if not directory.exists():
        return []
    return [
        {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    ]


def _input_artifacts(probe: dict[str, object]) -> list[dict[str, object]]:
    inputs = _require_object(probe, "inputs")
    expected = {"architecture", "mapper", "problem_yaml"}
    if set(inputs) != expected:
        raise ValueError(
            "probe inputs must contain architecture, mapper, and problem_yaml"
        )
    artifacts = []
    for name in sorted(expected):
        identity = _require_object(inputs, name)
        sha256 = str(identity.get("sha256", ""))
        if len(sha256) != 64 or any(
            value not in "0123456789abcdef" for value in sha256
        ):
            raise ValueError(f"invalid SHA-256 for {name}")
        artifacts.append(
            {
                "name": name,
                "path": str(identity["path"]),
                "bytes": _nonnegative_integer(identity.get("bytes"), f"{name} bytes"),
                "sha256": sha256,
            }
        )
    return artifacts


def _load_object(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return document


def _require_schema(document: dict[str, object], expected: str, label: str) -> None:
    observed = str(document.get("schema_version", ""))
    if observed != expected:
        raise ValueError(f"unsupported {label} schema: {observed}")


def _require_object(document: dict[str, object], key: str) -> dict[str, object]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _positive_integer(value: object, label: str) -> int:
    result = _nonnegative_integer(value, label)
    if result == 0:
        raise ValueError(f"{label} must be positive")
    return result


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _packed_bytes(elements: int, scalar_type: str) -> int:
    try:
        bits = TYPE_BITS[scalar_type]
    except KeyError as error:
        raise ValueError(f"unsupported tensor type: {scalar_type}") from error
    return (elements * bits + 7) // 8


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
