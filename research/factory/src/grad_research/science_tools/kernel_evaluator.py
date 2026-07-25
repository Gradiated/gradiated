from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..util import utc_now
from .common import (
    ScienceToolError,
    artifact_identity,
    load_json,
    read_jsonl,
    run_command,
    write_json_atomic,
)


def _mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ScienceToolError(f"{label} must be a JSON object")
    return dict(value)


def _command_spec(value: Any, *, label: str) -> dict[str, Any]:
    spec = _mapping(value, label=label)
    command = spec.get("argv", spec.get("command"))
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, (str, int, float)) for part in command)
    ):
        raise ScienceToolError(f"{label}.argv must be a nonempty JSON array")
    spec["argv"] = [str(part) for part in command]
    environment = spec.get("env", {})
    if not isinstance(environment, Mapping):
        raise ScienceToolError(f"{label}.env must be an object")
    spec["env"] = {str(key): str(value) for key, value in environment.items()}
    return spec


def _setup_specs(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [_command_spec(value, label="commands.setup")]
    if not isinstance(value, list):
        raise ScienceToolError("commands.setup must be a command or list of commands")
    if value and all(isinstance(part, (str, int, float)) for part in value):
        return [_command_spec({"argv": value}, label="commands.setup")]
    return [
        _command_spec(item, label=f"commands.setup[{index}]")
        for index, item in enumerate(value)
    ]


def _expand(value: str, variables: Mapping[str, str]) -> str:
    pattern = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
    return pattern.sub(
        lambda match: variables.get(match.group(1), match.group(0)),
        value,
    )


def _resolve_cwd(
    value: Any,
    *,
    variables: Mapping[str, str],
    default_dir: Path,
) -> Path:
    if value is None:
        return default_dir
    if not isinstance(value, str):
        raise ScienceToolError("command cwd must be text")
    expanded = Path(_expand(value, variables)).expanduser()
    return expanded.resolve() if expanded.is_absolute() else (default_dir / expanded).resolve()


def _percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ScienceToolError("cannot summarize an empty timing distribution")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    return {
        "unit": "seconds",
        "count": len(values),
        "samples": list(values),
        "minimum": min(values),
        "maximum": max(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p50": _percentile(values, 0.50),
        "p90": _percentile(values, 0.90),
        "p95": _percentile(values, 0.95),
        "stdev": statistics.pstdev(values),
    }


def _json_path(value: Any, path: str) -> Any:
    current = value
    for component in path.split("."):
        if isinstance(current, Mapping) and component in current:
            current = current[component]
        elif isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ) and component.isdigit() and int(component) < len(current):
            current = current[int(component)]
        else:
            raise ScienceToolError(f"timing value path is absent: {path}")
    return current


def _timing_sample(
    timing_spec: Mapping[str, Any],
    command_result: Mapping[str, Any],
    consumed: Mapping[str, Any],
) -> float:
    source = timing_spec.get("source", "command_wall")
    if source == "command_wall":
        return float(command_result["wall_seconds"])
    if source != "output_json":
        raise ScienceToolError("timing.source must be command_wall or output_json")
    if consumed.get("kind") != "json":
        raise ScienceToolError("output_json timing requires a JSON command output")
    path = timing_spec.get("value_path")
    if not isinstance(path, str) or not path:
        raise ScienceToolError("output_json timing requires timing.value_path")
    value = _json_path(consumed.get("_raw_value", consumed["_value"]), path)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise ScienceToolError("reported timing value must be finite and non-negative")
    units = {
        "seconds": 1.0,
        "milliseconds": 1e-3,
        "microseconds": 1e-6,
        "nanoseconds": 1e-9,
    }
    unit = str(timing_spec.get("unit", "seconds"))
    if unit not in units:
        raise ScienceToolError(
            "timing.unit must be seconds, milliseconds, microseconds, or nanoseconds"
        )
    return float(value) * units[unit]


def _resolve_output_path(
    raw: Any,
    *,
    run_dir: Path,
    repro_dir: Path,
    variables: Mapping[str, str],
) -> Path:
    if not isinstance(raw, str) or not raw:
        raise ScienceToolError("output path must be nonempty text")
    expanded = Path(_expand(raw, variables)).expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    base = repro_dir if str(raw).startswith("{repro_dir}") else run_dir
    return (base / expanded).resolve()


def _file_state(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


def _declared_output_paths(
    command_spec: Mapping[str, Any],
    *,
    run_dir: Path,
    repro_dir: Path,
    variables: Mapping[str, str],
) -> list[Path]:
    raw = command_spec.get("output", {"kind": "json", "source": "stdout"})
    output = _mapping(raw, label="command.output")
    source = str(output.get("source", "path" if "path" in output else "stdout"))
    if source == "stdout":
        return []
    raw_paths = output.get("paths")
    if raw_paths is None and "path" in output:
        raw_paths = [output["path"]]
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ScienceToolError("file output requires path or paths")
    return [
        _resolve_output_path(
            item,
            run_dir=run_dir,
            repro_dir=repro_dir,
            variables=variables,
        )
        for item in raw_paths
    ]


def _require_fresh(path: Path, before: tuple[int, int, int] | None, label: str) -> None:
    after = _file_state(path)
    if after is None:
        raise ScienceToolError(f"{label} was not produced: {path}")
    if before is not None and after == before:
        raise ScienceToolError(f"{label} is stale and was not changed: {path}")


def _output_descriptor(
    command_spec: Mapping[str, Any],
    command_result: Mapping[str, Any],
    *,
    run_dir: Path,
    repro_dir: Path,
    variables: Mapping[str, str],
) -> dict[str, Any]:
    raw = command_spec.get("output", {"kind": "json", "source": "stdout"})
    output = _mapping(raw, label="command.output")
    kind = str(output.get("kind", output.get("format", "json")))
    source = str(output.get("source", "path" if "path" in output else "stdout"))
    if kind == "json" and source == "stdout":
        path = Path(str(command_result["stdout"]["path"]))
        try:
            value = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ScienceToolError(f"command stdout is not complete JSON: {error}") from error
        selected = value
        value_path = output.get("value_path")
        if value_path is not None:
            if not isinstance(value_path, str) or not value_path:
                raise ScienceToolError("command.output.value_path must be text")
            selected = _json_path(value, value_path)
        return {
            "kind": "json",
            "source": "stdout",
            "artifacts": [artifact_identity(path)],
            "_value": selected,
            "_raw_value": value,
            "_primary_path": str(path),
        }

    raw_paths = output.get("paths")
    if raw_paths is None and "path" in output:
        raw_paths = [output["path"]]
    if not isinstance(raw_paths, list) or not raw_paths:
        raise ScienceToolError("file output requires path or paths")
    paths = [
        _resolve_output_path(
            item,
            run_dir=run_dir,
            repro_dir=repro_dir,
            variables=variables,
        )
        for item in raw_paths
    ]
    if not all(path.is_file() for path in paths):
        missing = next(path for path in paths if not path.is_file())
        raise ScienceToolError(f"declared command output is absent: {missing}")
    artifacts = [artifact_identity(path) for path in paths]
    if kind in {"json", "json_file", "json_files"}:
        values = []
        for path in paths:
            try:
                values.append(json.loads(path.read_text()))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ScienceToolError(f"output file is not complete JSON: {path}") from error
        value: Any = values[0] if len(values) == 1 else values
        raw_value = value
        value_path = output.get("value_path")
        if value_path is not None:
            if not isinstance(value_path, str) or not value_path:
                raise ScienceToolError("command.output.value_path must be text")
            value = _json_path(value, value_path)
        normalized_kind = "json"
    elif kind in {"files", "file", "binary"}:
        value = [
            {
                "sha256": artifact["sha256"],
                "size_bytes": artifact["size_bytes"],
            }
            for artifact in artifacts
        ]
        normalized_kind = "files"
    else:
        raise ScienceToolError(f"unsupported command output kind: {kind}")
    result = {
        "kind": normalized_kind,
        "source": "files",
        "artifacts": artifacts,
        "_value": value,
        "_primary_path": str(paths[0]),
    }
    if normalized_kind == "json":
        result["_raw_value"] = raw_value
    return result


def _compare_json(
    reference: Any,
    candidate: Any,
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []
    numeric_count = 0
    max_absolute_error = 0.0
    max_relative_error = 0.0

    def visit(expected: Any, actual: Any, path: str) -> None:
        nonlocal numeric_count, max_absolute_error, max_relative_error
        numeric = (
            isinstance(expected, (int, float))
            and not isinstance(expected, bool)
            and isinstance(actual, (int, float))
            and not isinstance(actual, bool)
        )
        if numeric:
            numeric_count += 1
            expected_float = float(expected)
            actual_float = float(actual)
            if not math.isfinite(expected_float) or not math.isfinite(actual_float):
                if expected_float != actual_float:
                    mismatches.append({"path": path, "reason": "nonfinite_mismatch"})
                return
            absolute_error = abs(actual_float - expected_float)
            relative_error = absolute_error / max(abs(expected_float), 1e-300)
            max_absolute_error = max(max_absolute_error, absolute_error)
            max_relative_error = max(max_relative_error, relative_error)
            if absolute_error > absolute_tolerance + relative_tolerance * abs(
                expected_float
            ):
                mismatches.append(
                    {
                        "path": path,
                        "reason": "numeric_tolerance",
                        "absolute_error": absolute_error,
                        "relative_error": relative_error,
                    }
                )
            return
        if type(expected) is not type(actual):
            mismatches.append(
                {
                    "path": path,
                    "reason": "type",
                    "expected": type(expected).__name__,
                    "actual": type(actual).__name__,
                }
            )
            return
        if isinstance(expected, dict):
            if expected.keys() != actual.keys():
                mismatches.append({"path": path, "reason": "keys"})
                return
            for key in expected:
                visit(expected[key], actual[key], f"{path}.{key}")
            return
        if isinstance(expected, list):
            if len(expected) != len(actual):
                mismatches.append({"path": path, "reason": "length"})
                return
            for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
                visit(left, right, f"{path}[{index}]")
            return
        if expected != actual:
            mismatches.append({"path": path, "reason": "value"})

    visit(reference, candidate, "$")
    return {
        "passed": not mismatches,
        "numeric_value_count": numeric_count,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:100],
        "mismatches_truncated": len(mismatches) > 100,
        "max_absolute_error": max_absolute_error,
        "max_relative_error": max_relative_error,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
    }


def _compare_output(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    if reference["kind"] != candidate["kind"]:
        return {
            "passed": False,
            "mismatch_count": 1,
            "mismatches": [{"path": "$", "reason": "output_kind"}],
        }
    if reference["kind"] == "json":
        return _compare_json(
            reference["_value"],
            candidate["_value"],
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        )
    expected = reference["_value"]
    actual = candidate["_value"]
    mismatches = []
    if len(expected) != len(actual):
        mismatches.append({"path": "$", "reason": "file_count"})
    else:
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            if left != right:
                mismatches.append({"path": f"$[{index}]", "reason": "bytes"})
    return {
        "passed": not mismatches,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
    }


def _public_output(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if not key.startswith("_")}


def _proof_spec(
    config: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any] | None:
    raw = config.get("candidate_path_proof", candidate.get("proof"))
    if raw is None:
        return None
    if isinstance(raw, str):
        return {"path": raw, "required": True}
    return _mapping(raw, label="candidate_path_proof")


def _prepare_proof_path(
    proof: Mapping[str, Any] | None,
    *,
    run_dir: Path,
    repro_dir: Path,
    variables: Mapping[str, str],
) -> Path | None:
    if proof is None:
        return None
    raw = proof.get("path", "candidate-path-proof.json")
    path = _resolve_output_path(
        raw, run_dir=run_dir, repro_dir=repro_dir, variables=variables
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _validate_proof(
    proof: Mapping[str, Any] | None,
    path: Path | None,
) -> dict[str, Any]:
    if proof is None:
        return {"declared": False, "verified": False, "reason": "not_declared"}
    required = bool(proof.get("required", True))
    if path is None or not path.is_file():
        if required:
            raise ScienceToolError("candidate path proof was not produced")
        return {"declared": True, "verified": False, "reason": "absent_optional"}
    identity = artifact_identity(path)
    expected_hash = proof.get("sha256")
    if expected_hash is not None and identity["sha256"] != expected_hash:
        raise ScienceToolError("candidate path proof hash mismatch")
    contains = proof.get("contains")
    if contains is not None:
        if not isinstance(contains, Mapping):
            raise ScienceToolError("candidate path proof contains check requires objects")
        try:
            value = load_json(path)
            rows = [value] if isinstance(value, Mapping) else []
        except ScienceToolError:
            rows = read_jsonl(path)
        matches = [
            row
            for row in rows
            if all(row.get(key) == expected for key, expected in contains.items())
        ]
        if not matches:
            raise ScienceToolError(
                "candidate path proof contains no matching event"
            )
    else:
        rows = []
    return {
        "declared": True,
        "verified": True,
        "artifact": identity,
        "matching_event_count": len(matches) if contains is not None else None,
    }


class _Runner:
    def __init__(
        self,
        *,
        repro_dir: Path,
        output_dir: Path,
        timeout_seconds: float,
    ) -> None:
        self.repro_dir = repro_dir
        self.output_dir = output_dir
        self.timeout_seconds = timeout_seconds
        self.sequence = 0

    def execute(
        self,
        role: str,
        spec: Mapping[str, Any],
        *,
        stage: str,
        iteration: int = 0,
        proof: Mapping[str, Any] | None = None,
        extra_variables: Mapping[str, str] | None = None,
        tolerate_nonzero: bool = False,
        consume_output: bool = True,
    ) -> tuple[dict[str, Any], dict[str, Any] | None, Path | None]:
        self.sequence += 1
        name = f"{self.sequence:04d}-{stage}-{role}-{iteration}"
        run_dir = self.output_dir / "runs" / name
        run_dir.mkdir(parents=True, exist_ok=False)
        variables = {
            "repro_dir": str(self.repro_dir),
            "output_dir": str(self.output_dir),
            "run_dir": str(run_dir),
            "role": role,
            "stage": stage,
            "iteration": str(iteration),
        }
        if extra_variables:
            variables.update(extra_variables)
        command = _command_spec(spec, label=f"commands.{role}")
        proof_path = _prepare_proof_path(
            proof,
            run_dir=run_dir,
            repro_dir=self.repro_dir,
            variables=variables,
        )
        if proof_path is not None:
            variables["candidate_proof_path"] = str(proof_path)
        output_paths = _declared_output_paths(
            command,
            run_dir=run_dir,
            repro_dir=self.repro_dir,
            variables=variables,
        )
        output_states = {path: _file_state(path) for path in output_paths}
        proof_state = _file_state(proof_path) if proof_path is not None else None
        argv = [_expand(part, variables) for part in command["argv"]]
        environment = {
            key: _expand(value, variables) for key, value in command["env"].items()
        }
        environment.update(
            {
                "LAB_REPRO_DIR": str(self.repro_dir),
                "LAB_EVAL_RUN_DIR": str(run_dir),
                "LAB_EVAL_ROLE": role,
                "LAB_EVAL_STAGE": stage,
                "LAB_EVAL_ITERATION": str(iteration),
            }
        )
        if proof_path is not None:
            environment["LAB_CANDIDATE_PROOF_PATH"] = str(proof_path)
        timeout = float(command.get("timeout_seconds", self.timeout_seconds))
        started = time.perf_counter()
        result = run_command(
            argv,
            output_dir=run_dir,
            name="command",
            cwd=_resolve_cwd(
                command.get("cwd"), variables=variables, default_dir=run_dir
            ),
            timeout_seconds=timeout,
            environment=environment,
        )
        result["wall_seconds"] = time.perf_counter() - started
        result["run_dir"] = str(run_dir)
        if result.get("timed_out") and not tolerate_nonzero:
            raise ScienceToolError(
                f"{stage} {role} command exceeded {result['timeout_seconds']:g}s"
            )
        if result["returncode"] != 0 and not tolerate_nonzero:
            raise ScienceToolError(
                f"{stage} {role} command failed with exit {result['returncode']}"
            )
        if result["returncode"] == 0:
            for path in output_paths:
                _require_fresh(path, output_states[path], "declared command output")
            if proof_path is not None:
                _require_fresh(proof_path, proof_state, "candidate path proof")
        output = None
        if result["returncode"] == 0 and stage != "setup" and consume_output:
            output = _output_descriptor(
                command,
                result,
                run_dir=run_dir,
                repro_dir=self.repro_dir,
                variables=variables,
            )
        return result, output, proof_path


def _consumer_comparison(
    runner: _Runner,
    consumer: Mapping[str, Any],
    *,
    reference: Mapping[str, Any],
    target: Mapping[str, Any],
    role: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    variables = {
        "reference_output": str(reference["_primary_path"]),
        "candidate_output": str(target["_primary_path"]),
        "target_output": str(target["_primary_path"]),
    }
    spec = _command_spec(consumer, label="correctness.consumer")
    env = dict(spec.get("env", {}))
    env.update(
        {
            "LAB_REFERENCE_OUTPUT": str(reference["_primary_path"]),
            "LAB_CANDIDATE_OUTPUT": str(target["_primary_path"]),
            "LAB_TARGET_OUTPUT": str(target["_primary_path"]),
        }
    )
    spec["env"] = env
    result, _, _ = runner.execute(
        f"consumer-{role}",
        spec,
        stage="correctness",
        extra_variables=variables,
        tolerate_nonzero=True,
        consume_output=False,
    )
    return (
        {
            "passed": result["returncode"] == 0,
            "mode": "custom_consumer",
            "returncode": result["returncode"],
        },
        result,
    )


def _compiler_artifacts(
    raw: Any,
    *,
    repro_dir: Path,
    output_dir: Path,
) -> list[dict[str, Any]]:
    if raw is None:
        return []
    values = raw if isinstance(raw, list) else [raw]
    rows = []
    variables = {
        "repro_dir": str(repro_dir),
        "output_dir": str(output_dir),
    }
    for index, value in enumerate(values):
        spec = {"path": value} if isinstance(value, str) else _mapping(
            value, label=f"compiler_artifacts[{index}]"
        )
        raw_path = spec.get("path")
        if not isinstance(raw_path, str):
            raise ScienceToolError(f"compiler_artifacts[{index}].path is required")
        expanded = Path(_expand(raw_path, variables)).expanduser()
        path = expanded.resolve() if expanded.is_absolute() else (repro_dir / expanded).resolve()
        identity = artifact_identity(path)
        expected = spec.get("sha256")
        if expected is not None and identity["sha256"] != expected:
            raise ScienceToolError(f"compiler artifact hash mismatch: {path}")
        rows.append(identity)
    return rows


def _opportunity(
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
    timing: Mapping[str, Any],
) -> dict[str, Any]:
    operation = metadata.get("operation", {})
    share = (
        operation.get("production_non_overlap_wall_share")
        if isinstance(operation, Mapping)
        else None
    )
    speed_of_light = config.get("speed_of_light_seconds")
    baseline = float(timing["baseline"]["median"])
    candidate = float(timing["candidate"]["median"])
    measured_change = 1 - candidate / baseline if baseline > 0 else None
    result: dict[str, Any] = {
        "production_non_overlap_wall_share": share,
        "measured_component_reduction_fraction": measured_change,
        "production_weighted_measured_reduction_fraction": (
            measured_change * float(share)
            if measured_change is not None and isinstance(share, (int, float))
            else None
        ),
        "speed_of_light_seconds": speed_of_light,
        "component_headroom_fraction": None,
        "production_weighted_headroom_fraction": None,
    }
    if speed_of_light is not None:
        if (
            isinstance(speed_of_light, bool)
            or not isinstance(speed_of_light, (int, float))
            or not 0 <= float(speed_of_light) <= baseline
        ):
            raise ScienceToolError(
                "speed_of_light_seconds must be in [0, baseline median]"
            )
        headroom = (baseline - float(speed_of_light)) / baseline
        result["component_headroom_fraction"] = headroom
        if isinstance(share, (int, float)):
            result["production_weighted_headroom_fraction"] = headroom * float(share)
    return result


def evaluate_reproducer(
    repro_dir: str | Path,
    command_spec: Mapping[str, Any] | str | Path | None,
    output_dir: str | Path,
    *,
    timeout_seconds: float = 900,
) -> dict[str, Any]:
    """Evaluate explicit reference/baseline/candidate commands without ranking them."""

    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ScienceToolError("timeout_seconds must be finite and positive")
    repro = Path(repro_dir).resolve()
    metadata_path = repro / "metadata.json"
    metadata = _mapping(load_json(metadata_path), label="reproducer metadata")
    operation = metadata.get("operation")
    artifacts = metadata.get("artifacts")
    if (
        metadata.get("kind") != "exact_shape_reproducer"
        or not isinstance(operation, Mapping)
        or operation.get("shape") is None
        or not isinstance(artifacts, Mapping)
        or not isinstance(artifacts.get("inputs"), list)
        or not artifacts["inputs"]
    ):
        raise ScienceToolError(
            "kernel evaluation requires an exact-shape reproducer with shape "
            "metadata and at least one captured input"
        )
    if command_spec is None:
        raw_config = metadata.get("evaluation", metadata.get("command_specs"))
        config = _mapping(raw_config, label="reproducer evaluation")
    elif isinstance(command_spec, (str, Path)):
        config = _mapping(load_json(command_spec), label="evaluation spec")
    else:
        config = _mapping(command_spec, label="evaluation spec")

    commands = config.get("commands", config)
    commands = _mapping(commands, label="commands")
    required = {
        role: _command_spec(commands.get(role), label=f"commands.{role}")
        for role in ("reference", "baseline", "candidate")
    }
    setup = _setup_specs(commands.get("setup", config.get("setup")))
    output = Path(output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise ScienceToolError(f"evaluation output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    runner = _Runner(
        repro_dir=repro,
        output_dir=output,
        timeout_seconds=timeout_seconds,
    )
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "exact_shape_kernel_evaluation",
        "status": "running",
        "started_at": utc_now(),
        "reproducer_metadata": artifact_identity(metadata_path),
        "commands": {},
        "decision": None,
    }
    try:
        setup_results = []
        for index, spec in enumerate(setup):
            command_result, _, _ = runner.execute(
                f"setup-{index}", spec, stage="setup"
            )
            setup_results.append(command_result)
        result["commands"]["setup"] = setup_results
        result["compiler_artifacts"] = _compiler_artifacts(
            config.get("compiler_artifacts"),
            repro_dir=repro,
            output_dir=output,
        )

        reference_result, reference_output, _ = runner.execute(
            "reference", required["reference"], stage="correctness"
        )
        baseline_result, baseline_output, _ = runner.execute(
            "baseline", required["baseline"], stage="correctness"
        )
        proof_spec = _proof_spec(config, required["candidate"])
        if proof_spec is None:
            raise ScienceToolError(
                "declare candidate_path_proof and emit it from every candidate "
                "invocation"
            )

        def candidate_proof(path: Path | None) -> dict[str, Any]:
            return _validate_proof(proof_spec, path)

        candidate_result, candidate_output, candidate_proof_path = runner.execute(
            "candidate",
            required["candidate"],
            stage="correctness",
            proof=proof_spec,
        )
        assert reference_output is not None
        assert baseline_output is not None
        assert candidate_output is not None
        result["commands"].update(
            {
                "reference": reference_result,
                "baseline_correctness": baseline_result,
                "candidate_correctness": candidate_result,
            }
        )
        result["outputs"] = {
            "reference": _public_output(reference_output),
            "baseline": _public_output(baseline_output),
            "candidate": _public_output(candidate_output),
        }
        correctness_proof = candidate_proof(candidate_proof_path)
        proof_executions = [
            {
                "stage": "correctness",
                "iteration": 0,
                **correctness_proof,
            }
        ]
        result["candidate_path_proof"] = {
            **correctness_proof,
            "executions": proof_executions,
        }

        correctness = _mapping(
            config.get("correctness", {}), label="correctness"
        )
        absolute_tolerance = float(
            correctness.get(
                "absolute_tolerance", correctness.get("atol", 0.0)
            )
        )
        relative_tolerance = float(
            correctness.get(
                "relative_tolerance", correctness.get("rtol", 0.0)
            )
        )
        if (
            not math.isfinite(absolute_tolerance)
            or not math.isfinite(relative_tolerance)
            or absolute_tolerance < 0
            or relative_tolerance < 0
        ):
            raise ScienceToolError("correctness tolerances must be finite and nonnegative")
        consumer = correctness.get("consumer", config.get("consumer"))
        consumer_results: dict[str, Any] = {}
        if consumer is not None:
            consumer_spec = _mapping(consumer, label="correctness.consumer")
            baseline_comparison, baseline_consumer = _consumer_comparison(
                runner,
                consumer_spec,
                reference=reference_output,
                target=baseline_output,
                role="baseline",
            )
            candidate_comparison, candidate_consumer = _consumer_comparison(
                runner,
                consumer_spec,
                reference=reference_output,
                target=candidate_output,
                role="candidate",
            )
            consumer_results = {
                "baseline": baseline_consumer,
                "candidate": candidate_consumer,
            }
        else:
            baseline_comparison = _compare_output(
                reference_output,
                baseline_output,
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
            candidate_comparison = _compare_output(
                reference_output,
                candidate_output,
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
        result["correctness"] = {
            "baseline": baseline_comparison,
            "candidate": candidate_comparison,
            "consumer_commands": consumer_results,
            "full_output_consumed": True,
        }

        if not baseline_comparison["passed"] or not candidate_comparison["passed"]:
            result["status"] = "correctness_failed"
            result["timing"] = None
        else:
            timing_spec = _mapping(config.get("timing", {}), label="timing")
            warmup = int(timing_spec.get("warmup", timing_spec.get("warmups", 2)))
            repetitions = int(timing_spec.get("repetitions", 10))
            if warmup < 0 or repetitions <= 0:
                raise ScienceToolError(
                    "timing warmup must be nonnegative and repetitions positive"
                )
            timing_results: dict[str, list[float]] = {
                "baseline": [],
                "candidate": [],
            }
            timing_commands: list[dict[str, Any]] = []
            for iteration in range(warmup):
                for role in ("baseline", "candidate"):
                    command_result, consumed, timing_proof_path = runner.execute(
                        role,
                        required[role],
                        stage="warmup",
                        iteration=iteration,
                        proof=proof_spec if role == "candidate" else None,
                    )
                    assert consumed is not None
                    comparison = _compare_output(
                        reference_output,
                        consumed,
                        absolute_tolerance=absolute_tolerance,
                        relative_tolerance=relative_tolerance,
                    )
                    if not comparison["passed"]:
                        raise ScienceToolError(
                            f"{role} warmup output failed correctness"
                        )
                    if role == "candidate":
                        proof_executions.append(
                            {
                                "stage": "warmup",
                                "iteration": iteration,
                                **candidate_proof(timing_proof_path),
                            }
                        )
                    timing_commands.append(command_result)
            for iteration in range(repetitions):
                order = (
                    ("baseline", "candidate")
                    if iteration % 2 == 0
                    else ("candidate", "baseline")
                )
                for role in order:
                    command_result, consumed, timing_proof_path = runner.execute(
                        role,
                        required[role],
                        stage="timing",
                        iteration=iteration,
                        proof=proof_spec if role == "candidate" else None,
                    )
                    assert consumed is not None
                    comparison = _compare_output(
                        reference_output,
                        consumed,
                        absolute_tolerance=absolute_tolerance,
                        relative_tolerance=relative_tolerance,
                    )
                    if not comparison["passed"]:
                        raise ScienceToolError(
                            f"{role} timed output failed correctness"
                        )
                    if role == "candidate":
                        proof_executions.append(
                            {
                                "stage": "timing",
                                "iteration": iteration,
                                **candidate_proof(timing_proof_path),
                            }
                        )
                    timing_results[role].append(
                        _timing_sample(timing_spec, command_result, consumed)
                    )
                    timing_commands.append(command_result)
            result["candidate_path_proof"]["verified"] = all(
                row["verified"] for row in proof_executions
            )
            result["commands"]["timing"] = timing_commands
            result["timing"] = {
                role: _distribution(values)
                for role, values in timing_results.items()
            }
            result["opportunity"] = _opportunity(
                metadata, config, result["timing"]
            )
            profiler = config.get("profiler")
            if profiler is not None:
                profiler_spec = _command_spec(profiler, label="profiler")
                profiler_result, profiler_output, _ = runner.execute(
                    "profiler",
                    profiler_spec,
                    stage="profiler",
                    consume_output="output" in profiler_spec,
                )
                result["profiler"] = {
                    "command": profiler_result,
                    "output": (
                        None
                        if profiler_output is None
                        else _public_output(profiler_output)
                    ),
                }
            else:
                result["profiler"] = None
            result["status"] = "complete"
    except Exception as error:
        result["status"] = "failed"
        result["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
        result["completed_at"] = utc_now()
        write_json_atomic(output / "evaluation.json", result)
        if isinstance(error, ScienceToolError):
            raise
        raise ScienceToolError(str(error)) from error

    result["completed_at"] = utc_now()
    write_json_atomic(output / "evaluation.json", result)
    return result


run_evaluation = evaluate_reproducer


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="lab-kernel-eval",
        description=(
            "Evaluate explicit reference/baseline/candidate commands for one exact repro."
        )
    )
    root.add_argument("--repro", required=True)
    root.add_argument(
        "--spec",
        help="Evaluation command-spec JSON; omit when metadata embeds evaluation.",
    )
    root.add_argument("--output", required=True)
    root.add_argument("--timeout-seconds", type=float, default=900)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = evaluate_reproducer(
            args.repro,
            args.spec,
            args.output,
            timeout_seconds=args.timeout_seconds,
        )
    except (ScienceToolError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": result["status"],
                "evaluation": str(Path(args.output).resolve() / "evaluation.json"),
            },
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
