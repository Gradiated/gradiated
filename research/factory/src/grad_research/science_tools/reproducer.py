from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from ..util import file_hash, utc_now
from .common import (
    ScienceToolError,
    artifact_identity,
    load_json,
    read_jsonl,
    write_json_atomic,
)


ARTIFACT_ROLES = ("inputs", "reference", "consumer", "candidate")
ROLE_ALIASES = {
    "input": "inputs",
    "inputs": "inputs",
    "reference": "reference",
    "references": "reference",
    "consumer": "consumer",
    "consumers": "consumer",
    "benchmark": "consumer",
    "benchmarks": "consumer",
    "candidate": "candidate",
    "candidates": "candidate",
}
OPERATION_CONTAINERS = ("operations", "ops", "events", "records")


def _json_trace_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        rows = value
    elif isinstance(value, dict):
        rows = next(
            (
                value[name]
                for name in OPERATION_CONTAINERS
                if isinstance(value.get(name), list)
            ),
            [value],
        )
    else:
        raise ScienceToolError("normalized trace must contain JSON objects")
    if not all(isinstance(row, dict) for row in rows):
        raise ScienceToolError("every normalized trace operation must be an object")
    return [dict(row) for row in rows]


def read_trace(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix.lower() == ".jsonl":
        return read_jsonl(source)
    return _json_trace_rows(load_json(source))


def _operation_id(operation: Mapping[str, Any]) -> str | None:
    for key in ("operation_id", "op_id", "id"):
        value = operation.get(key)
        if value is not None:
            return str(value)
    return None


def _lookup(operation: Mapping[str, Any], selector: str) -> Any:
    current: Any = operation
    for component in selector.split("."):
        if not isinstance(current, Mapping) or component not in current:
            break
        current = current[component]
    else:
        return current

    semantic = operation.get("semantic")
    if isinstance(semantic, Mapping):
        current = semantic
        for component in selector.split("."):
            if not isinstance(current, Mapping) or component not in current:
                return None
            current = current[component]
        return current
    return None


def select_operation(
    operations: Sequence[Mapping[str, Any]],
    *,
    operation_id: str | None = None,
    semantic_selectors: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    selectors = dict(semantic_selectors or {})
    if operation_id is None and not selectors:
        raise ScienceToolError("select an operation by ID or semantic selector")
    matches = []
    for operation in operations:
        if operation_id is not None and _operation_id(operation) != str(operation_id):
            continue
        if any(_lookup(operation, key) != value for key, value in selectors.items()):
            continue
        matches.append(operation)
    if not matches:
        raise ScienceToolError("operation selector matched no trace operation")
    if len(matches) > 1:
        raise ScienceToolError(
            f"operation selector is ambiguous: matched {len(matches)} operations"
        )
    return dict(matches[0])


def _safe_relative(value: Any, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ScienceToolError(f"{label} must be a nonempty relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or "\\" in value
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise ScienceToolError(f"{label} is unsafe: {value}")
    return path


def _resolve_declared_artifact(root: Path, value: Any, *, label: str) -> Path:
    relative = _safe_relative(value, label=label)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ScienceToolError(f"{label} traverses a symlink: {relative}")
    resolved = root.joinpath(*relative.parts).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ScienceToolError(f"{label} escapes artifact root: {relative}") from error
    if not resolved.is_file():
        raise ScienceToolError(f"{label} is missing or not a file: {relative}")
    return resolved


def _explicit_artifact(path: str | Path, *, label: str) -> Path:
    source = Path(path).expanduser()
    if source.is_symlink():
        raise ScienceToolError(f"{label} must not be a symlink: {source}")
    resolved = source.resolve()
    if not resolved.is_file():
        raise ScienceToolError(f"{label} is missing or not a file: {source}")
    return resolved


def _artifact_specs(operation: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(role: str, value: Any) -> None:
        normalized_role = ROLE_ALIASES[role]
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str):
                rows.append({"role": normalized_role, "path": item})
            elif isinstance(item, Mapping) and isinstance(item.get("path"), str):
                rows.append({"role": normalized_role, **dict(item)})

    artifacts = operation.get("artifacts")
    if isinstance(artifacts, Mapping):
        for role, value in artifacts.items():
            if not isinstance(role, str) or role not in ROLE_ALIASES:
                raise ScienceToolError(
                    "artifact role must be one of: "
                    + ", ".join(ARTIFACT_ROLES)
                )
            add(role, value)
    elif isinstance(artifacts, list):
        for item in artifacts:
            if not isinstance(item, Mapping):
                raise ScienceToolError("artifact list entries must be objects")
            role = item.get("role")
            if not isinstance(role, str) or role not in ROLE_ALIASES:
                raise ScienceToolError(
                    "artifact role must be one of: "
                    + ", ".join(ARTIFACT_ROLES)
                )
            if not isinstance(item.get("path"), str):
                raise ScienceToolError("artifact entries require a path")
            rows.append({"role": ROLE_ALIASES[role], **dict(item)})

    for alias, role in ROLE_ALIASES.items():
        for field in (f"{alias}_artifacts", f"{alias}_artifact"):
            if field in operation:
                add(alias, operation[field])
        path_field = f"{alias}_path"
        if isinstance(operation.get(path_field), str):
            add(alias, operation[path_field])

    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["role"]), str(row["path"]))
        unique[key] = row
    return list(unique.values())


def _copy_artifact(
    source: Path,
    *,
    role: str,
    destination_name: str,
    temporary: Path,
    expected_sha256: Any = None,
) -> dict[str, Any]:
    relative = _safe_relative(destination_name, label="artifact destination")
    if len(relative.parts) != 1:
        raise ScienceToolError("artifact destination name must not contain directories")
    digest = file_hash(source)
    if expected_sha256 is not None and expected_sha256 != digest:
        raise ScienceToolError(
            f"artifact hash mismatch for {source}: expected {expected_sha256}, got {digest}"
        )
    destination = temporary / role / relative.name
    if destination.exists():
        raise ScienceToolError(f"duplicate artifact destination: {role}/{relative.name}")
    shutil.copy2(source, destination, follow_symlinks=False)
    copied = artifact_identity(destination)
    if copied["sha256"] != digest:
        raise ScienceToolError(f"artifact changed while copying: {source}")
    copied["path"] = destination.relative_to(temporary).as_posix()
    copied["role"] = role
    return copied


def _metadata_field(operation: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = _lookup(operation, name)
        if value is not None:
            return value
    return None


def _wall_share(operation: Mapping[str, Any]) -> float | None:
    value = _metadata_field(
        operation,
        "production_non_overlap_wall_share",
        "non_overlap_wall_share",
        "production.non_overlap_wall_share",
        "production.wall_share",
        "metrics.production_non_overlap_wall_share",
        "metrics.non_overlap_wall_share",
    )
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScienceToolError("production non-overlap wall share must be numeric")
    result = float(value)
    if not 0 <= result <= 1:
        raise ScienceToolError("production non-overlap wall share must be in [0,1]")
    return result


def _validate_exact_shape(value: Any, path: str = "shape") -> None:
    if isinstance(value, bool):
        raise ScienceToolError(f"{path} must contain positive integer dimensions")
    if isinstance(value, int):
        if value <= 0:
            raise ScienceToolError(f"{path} dimensions must be positive")
        return
    if isinstance(value, list):
        if not value:
            raise ScienceToolError(f"{path} must not be empty")
        for index, dimension in enumerate(value):
            _validate_exact_shape(dimension, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        if not value:
            raise ScienceToolError(f"{path} must not be empty")
        for name, shape in value.items():
            if not isinstance(name, str) or not name:
                raise ScienceToolError(f"{path} keys must be nonempty text")
            _validate_exact_shape(shape, f"{path}.{name}")
        return
    raise ScienceToolError(
        f"{path} must contain only concrete positive integer dimensions"
    )


def extract_reproducer(
    trace_path: str | Path | None,
    output_dir: str | Path,
    *,
    operation_id: str | None = None,
    semantic_selectors: Mapping[str, Any] | None = None,
    artifact_root: str | Path | None = None,
    benchmark_path: str | Path | None = None,
    reference_path: str | Path | None = None,
    candidate_path: str | Path | None = None,
    input_paths: Sequence[str | Path] = (),
    generic_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract one production operation into a self-contained repro directory.

    Paths declared by a trace must be safe relative paths below ``artifact_root``.
    Explicit generic-template paths are trusted CLI inputs, but symlinks are still
    rejected and their copied bytes are hashed.
    """

    trace: Path | None = None
    if trace_path is None:
        if benchmark_path is None or reference_path is None:
            raise ScienceToolError(
                "a generic reproducer requires benchmark and reference paths"
            )
        operation = dict(generic_metadata or {})
        operation.setdefault("operation_id", operation_id or "generic")
        selectors = dict(semantic_selectors or {})
        if selectors:
            operation.setdefault("semantic", selectors)
    else:
        trace = Path(trace_path).resolve()
        operations = read_trace(trace)
        operation = select_operation(
            operations,
            operation_id=operation_id,
            semantic_selectors=semantic_selectors,
        )

    destination = Path(output_dir).resolve()
    if destination.exists():
        raise ScienceToolError(f"reproducer destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_root = (
        Path(artifact_root).resolve()
        if artifact_root is not None
        else (trace.parent if trace is not None else Path.cwd().resolve())
    )
    if not source_root.is_dir():
        raise ScienceToolError(f"artifact root is absent: {source_root}")

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        for role in ARTIFACT_ROLES:
            (temporary / role).mkdir()

        copied: dict[str, list[dict[str, Any]]] = {
            role: [] for role in ARTIFACT_ROLES
        }
        for index, spec in enumerate(_artifact_specs(operation)):
            role = str(spec["role"])
            source = _resolve_declared_artifact(
                source_root,
                spec["path"],
                label=f"artifacts[{index}].path",
            )
            name = spec.get("name") or source.name
            copied[role].append(
                _copy_artifact(
                    source,
                    role=role,
                    destination_name=str(name),
                    temporary=temporary,
                    expected_sha256=spec.get("sha256"),
                )
            )

        generic_template: dict[str, Any] | None = None
        explicit = (
            *(
                ("inputs", f"input-{index}", path)
                for index, path in enumerate(input_paths)
            ),
            ("consumer", "benchmark", benchmark_path),
            ("reference", "reference", reference_path),
            ("candidate", "candidate", candidate_path),
        )
        for role, label, path in explicit:
            if path is None:
                continue
            source = _explicit_artifact(path, label=f"{label} path")
            row = _copy_artifact(
                source,
                role=role,
                destination_name=source.name,
                temporary=temporary,
            )
            copied[role].append(row)
            generic_template = generic_template or {}
            generic_template[f"{label}_artifact"] = row["path"]

        shape = _metadata_field(operation, "shape", "shapes")
        if shape is None:
            raise ScienceToolError(
                "an exact-shape reproducer requires operation shape metadata"
            )
        _validate_exact_shape(shape)
        if not copied["inputs"]:
            raise ScienceToolError(
                "an exact-shape reproducer requires at least one captured input artifact"
            )
        metadata: dict[str, Any] = {
            "schema_version": 1,
            "kind": "exact_shape_reproducer",
            "created_at": utc_now(),
            "operation": {
                "id": _operation_id(operation),
                "semantic": operation.get("semantic"),
                "shape": shape,
                "layout": _metadata_field(operation, "layout", "layouts", "strides"),
                "dtype": _metadata_field(operation, "dtype", "dtypes"),
                "scales": _metadata_field(
                    operation, "scales", "scale", "scale_convention"
                ),
                "phase": _metadata_field(operation, "phase", "semantic.phase"),
                "hardware": _metadata_field(
                    operation, "hardware", "device", "accelerator"
                ),
                "production_non_overlap_wall_share": _wall_share(operation),
            },
            "selection": {
                "operation_id": operation_id,
                "semantic": dict(semantic_selectors or {}),
            },
            "artifacts": copied,
        }
        if trace is not None:
            metadata["source_trace"] = artifact_identity(trace)
        if generic_template is not None:
            metadata["generic_template"] = generic_template
        write_json_atomic(temporary / "metadata.json", metadata)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        "schema_version": 1,
        "reproducer": str(destination),
        "metadata": artifact_identity(destination / "metadata.json"),
        "artifact_count": sum(len(rows) for rows in copied.values()),
    }


build_reproducer = extract_reproducer


def _selector(value: str) -> tuple[str, Any]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("semantic selector must be KEY=JSON_VALUE")
    key, raw = value.split("=", 1)
    if not key:
        raise argparse.ArgumentTypeError("semantic selector key is empty")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = raw
    return key, parsed


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="lab-reproducer",
        description="Extract one normalized production operation into an exact repro."
    )
    root.add_argument("--trace")
    root.add_argument("--output", required=True)
    root.add_argument("--operation-id")
    root.add_argument("--semantic", action="append", type=_selector, default=[])
    root.add_argument("--artifact-root")
    root.add_argument("--benchmark", "--benchmark-path", dest="benchmark_path")
    root.add_argument("--reference", "--reference-path", dest="reference_path")
    root.add_argument("--candidate", "--candidate-path", dest="candidate_path")
    root.add_argument(
        "--input",
        dest="input_paths",
        action="append",
        default=[],
        help="captured input artifact for a generic reproducer; repeat as needed",
    )
    root.add_argument(
        "--metadata",
        help="JSON file supplying shape/layout/dtype details for a generic repro.",
    )
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        generic_metadata = load_json(args.metadata) if args.metadata else None
        result = extract_reproducer(
            args.trace,
            args.output,
            operation_id=args.operation_id,
            semantic_selectors=dict(args.semantic),
            artifact_root=args.artifact_root,
            benchmark_path=args.benchmark_path,
            reference_path=args.reference_path,
            candidate_path=args.candidate_path,
            input_paths=args.input_paths,
            generic_metadata=generic_metadata,
        )
    except (ScienceToolError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
