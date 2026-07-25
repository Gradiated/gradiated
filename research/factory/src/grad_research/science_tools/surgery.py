from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..util import content_hash, utc_now
from .common import (
    ScienceToolError,
    artifact_identity,
    load_json,
    read_jsonl,
    run_command,
    write_json_atomic,
    write_jsonl_atomic,
)


PHASES = ("capture", "replace", "recover", "export", "evaluate")


def _require_mapping(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScienceToolError(f"{name} must be a JSON object")
    return dict(value)


def _path_identity(path: Path) -> dict[str, Any]:
    if path.is_file():
        return {"kind": "file", **artifact_identity(path)}
    if not path.is_dir():
        raise ScienceToolError(f"expected output is absent: {path}")
    files: list[dict[str, Any]] = []
    for member in sorted(path.rglob("*")):
        relative = member.relative_to(path).as_posix()
        if member.is_symlink():
            files.append(
                {
                    "kind": "symlink",
                    "path": relative,
                    "target": os.readlink(member),
                }
            )
        elif member.is_file():
            identity = artifact_identity(member)
            files.append(
                {
                    "kind": "file",
                    "path": relative,
                    "sha256": identity["sha256"],
                    "size_bytes": identity["size_bytes"],
                }
            )
    return {
        "kind": "directory",
        "path": str(path),
        "sha256": content_hash(files),
        "file_count": sum(row["kind"] == "file" for row in files),
        "entries": files,
    }


def _resolve_path(value: str, cwd: Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    return candidate.resolve()


def _expected_output_specs(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ScienceToolError("expected_outputs must be a list")
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if isinstance(item, str) and item:
            result.append({"path": item, "label": Path(item).name})
            continue
        if (
            isinstance(item, dict)
            and isinstance(item.get("path"), str)
            and item["path"]
        ):
            label = item.get("label", Path(item["path"]).name)
            if not isinstance(label, str) or not label:
                raise ScienceToolError(
                    f"expected_outputs[{index}].label must be nonempty text"
                )
            result.append({"path": item["path"], "label": label})
            continue
        raise ScienceToolError(
            f"expected_outputs[{index}] must be a path or path object"
        )
    return result


def _phase_spec(name: str, raw: Any, base: Path) -> dict[str, Any]:
    phase = _require_mapping(f"phases.{name}", raw)
    argv = phase.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(part, str) or not part for part in argv)
    ):
        raise ScienceToolError(f"phases.{name}.argv must be a nonempty string list")
    cwd_value = phase.get("cwd")
    if not isinstance(cwd_value, str) or not cwd_value:
        raise ScienceToolError(f"phases.{name}.cwd must be nonempty text")
    cwd = _resolve_path(cwd_value, base)
    environment = phase.get("env")
    if not isinstance(environment, dict) or any(
        not isinstance(key, str)
        or not key
        or not isinstance(value, str)
        for key, value in environment.items()
    ):
        raise ScienceToolError(f"phases.{name}.env must map strings to strings")
    timeout = phase.get("timeout_seconds")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ScienceToolError(
            f"phases.{name}.timeout_seconds must be a positive number"
        )
    metrics = phase.get("metrics_jsonl")
    if metrics is not None and (not isinstance(metrics, str) or not metrics):
        raise ScienceToolError(f"phases.{name}.metrics_jsonl must be a path")
    outputs = _expected_output_specs(phase.get("expected_outputs"))
    identity = {
        "argv": argv,
        "cwd": str(cwd),
        "environment_keys": sorted(environment),
        "environment_sha256": content_hash(environment),
        "timeout_seconds": float(timeout),
        "expected_outputs": outputs,
        "metrics_jsonl": metrics,
    }
    return {
        "name": name,
        "argv": argv,
        "cwd": cwd,
        "env": environment,
        "timeout_seconds": float(timeout),
        "expected_outputs": outputs,
        "metrics_jsonl": metrics,
        "command_identity": identity,
        "phase_sha256": content_hash(identity),
    }


def load_config(path: str | Path) -> tuple[dict[str, Any], Path]:
    source = Path(path).expanduser().resolve()
    raw = _require_mapping("config", load_json(source))
    raw_phases = raw.get("phases", raw)
    phases = _require_mapping("phases", raw_phases)
    unknown = sorted(set(phases) - set(PHASES))
    if unknown:
        raise ScienceToolError(f"unknown surgery phases: {', '.join(unknown)}")
    parsed: dict[str, Any] = {}
    for name in PHASES:
        if name in phases:
            parsed[name] = _phase_spec(name, phases[name], source.parent)
    if not parsed:
        raise ScienceToolError("config must define at least one surgery phase")
    return parsed, source


def _collect_outputs(phase: Mapping[str, Any]) -> list[dict[str, Any]]:
    results = []
    cwd = Path(phase["cwd"])
    for output in phase["expected_outputs"]:
        identity = _path_identity(_resolve_path(output["path"], cwd))
        identity["label"] = output["label"]
        results.append(identity)
    return results


def _identity_still_matches(recorded: Mapping[str, Any]) -> bool:
    try:
        current = _path_identity(Path(str(recorded["path"])))
    except (ScienceToolError, OSError):
        return False
    return (
        current.get("kind") == recorded.get("kind")
        and current.get("sha256") == recorded.get("sha256")
        and current.get("size_bytes") == recorded.get("size_bytes")
        and current.get("file_count") == recorded.get("file_count")
    )


def _valid_terminal(
    path: Path,
    phase: Mapping[str, Any],
    upstream_identity: str | None,
) -> bool:
    if not path.is_file():
        return False
    try:
        record = _require_mapping("terminal record", load_json(path))
    except ScienceToolError:
        return False
    if (
        record.get("schema_version") != 1
        or record.get("status") != "succeeded"
        or record.get("phase") != phase["name"]
        or record.get("phase_sha256") != phase["phase_sha256"]
        or record.get("upstream_identity") != upstream_identity
    ):
        return False
    outputs = record.get("outputs")
    if not isinstance(outputs, list) or not all(
        isinstance(output, dict) and _identity_still_matches(output)
        for output in outputs
    ):
        return False
    metrics = record.get("metrics_source")
    return metrics is None or (
        isinstance(metrics, dict) and _identity_still_matches(metrics)
    )


def _phase_record(
    phase: Mapping[str, Any],
    command_record: Mapping[str, Any] | None,
    *,
    status: str,
    upstream_identity: str | None,
    outputs: list[dict[str, Any]] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": 1,
        "phase": phase["name"],
        "phase_sha256": phase["phase_sha256"],
        "upstream_identity": upstream_identity,
        "status": status,
        "completed_at": utc_now(),
        "command_identity": phase["command_identity"],
        "command": command_record,
        "outputs": outputs or [],
    }
    if error is not None:
        record["error"] = error
    return record


def _run_phase(
    phase: Mapping[str, Any],
    phase_dir: Path,
    upstream_identity: str | None,
) -> dict[str, Any]:
    command_record: dict[str, Any] | None = None
    try:
        command_record = run_command(
            phase["argv"],
            output_dir=phase_dir,
            name="command",
            cwd=phase["cwd"],
            timeout_seconds=phase["timeout_seconds"],
            environment=phase["env"],
        )
        if command_record.get("timed_out"):
            raise ScienceToolError(
                f"{phase['name']} exceeded {command_record['timeout_seconds']:g}s"
            )
        if command_record["returncode"] != 0:
            raise ScienceToolError(
                f"{phase['name']} exited with {command_record['returncode']}"
            )
        outputs = _collect_outputs(phase)
        record = _phase_record(
            phase,
            command_record,
            status="succeeded",
            upstream_identity=upstream_identity,
            outputs=outputs,
        )
        metrics_value = phase["metrics_jsonl"]
        if metrics_value is not None:
            metrics_source = _resolve_path(metrics_value, Path(phase["cwd"]))
            rows = read_jsonl(metrics_source)
            captured = write_jsonl_atomic(phase_dir / "metrics.jsonl", rows)
            record["metrics_source"] = _path_identity(metrics_source)
            record["metrics"] = artifact_identity(captured)
            record["recovery_curve"] = rows
        if phase["name"] == "recover":
            record["checkpoint_identities"] = outputs
        elif phase["name"] == "export":
            record["export_identities"] = outputs
        return record
    except (OSError, ScienceToolError) as error:
        if command_record is None:
            partial: dict[str, Any] = {
                "schema_version": 1,
                "name": "command",
                "command": phase["argv"],
                "cwd": str(phase["cwd"]),
                "returncode": None,
            }
            for stream in ("stdout", "stderr"):
                path = phase_dir / f"command.{stream}.log"
                if path.is_file():
                    partial[stream] = artifact_identity(path)
            command_record = partial
        return _phase_record(
            phase,
            command_record,
            status="failed",
            upstream_identity=upstream_identity,
            error=str(error),
        )


def _terminal_identity(record: Mapping[str, Any]) -> str:
    return content_hash(
        {
            "phase": record.get("phase"),
            "phase_sha256": record.get("phase_sha256"),
            "upstream_identity": record.get("upstream_identity"),
            "outputs": record.get("outputs", []),
            "metrics_source": record.get("metrics_source"),
        }
    )


def execute(
    config_path: str | Path,
    output_dir: str | Path,
    *,
    from_phase: str | None = None,
    dry_run: bool = False,
) -> tuple[int, dict[str, Any]]:
    phases, source = load_config(config_path)
    selected = list(phases)
    if from_phase is not None:
        start = PHASES.index(from_phase)
        selected = [name for name in selected if PHASES.index(name) >= start]
    plan = {
        "schema_version": 1,
        "config": str(source),
        "config_sha256": artifact_identity(source)["sha256"],
        "output_dir": str(Path(output_dir).expanduser().resolve()),
        "dry_run": dry_run,
        "phases": [
            {
                "phase": name,
                "phase_sha256": phases[name]["phase_sha256"],
                "command_identity": phases[name]["command_identity"],
            }
            for name in selected
        ],
    }
    if dry_run:
        return 0, plan

    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    outcomes: list[dict[str, Any]] = []
    returncode = 0
    selected_set = set(selected)
    upstream_identity: str | None = None
    for name in phases:
        phase = phases[name]
        phase_dir = root / "phases" / name
        terminal_path = phase_dir / "terminal.json"
        if name not in selected_set:
            if not _valid_terminal(terminal_path, phase, upstream_identity):
                raise ScienceToolError(
                    f"cannot start from {from_phase}: upstream phase {name} "
                    "has no valid compatible terminal"
                )
            terminal = _require_mapping(
                f"{name} terminal", load_json(terminal_path)
            )
            upstream_identity = _terminal_identity(terminal)
            continue
        if _valid_terminal(terminal_path, phase, upstream_identity):
            outcomes.append({"phase": name, "status": "resumed"})
            terminal = _require_mapping(
                f"{name} terminal", load_json(terminal_path)
            )
            upstream_identity = _terminal_identity(terminal)
            continue
        phase_dir.mkdir(parents=True, exist_ok=True)
        terminal = _run_phase(phase, phase_dir, upstream_identity)
        write_json_atomic(terminal_path, terminal)
        outcomes.append({"phase": name, "status": terminal["status"]})
        if terminal["status"] != "succeeded":
            returncode = 1
            break
        upstream_identity = _terminal_identity(terminal)
    summary = {
        **plan,
        "dry_run": False,
        "completed_at": utc_now(),
        "status": "succeeded" if returncode == 0 else "failed",
        "outcomes": outcomes,
    }
    write_json_atomic(root / "run.json", summary)
    return returncode, summary


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="lab-surgery",
        description="Run optional, resumable model-surgery command phases."
    )
    root.add_argument("--config", required=True)
    root.add_argument("--output-dir", required=True)
    root.add_argument("--from-phase", choices=PHASES)
    root.add_argument("--dry-run", action="store_true")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        returncode, result = execute(
            args.config,
            args.output_dir,
            from_phase=args.from_phase,
            dry_run=args.dry_run,
        )
    except ScienceToolError as error:
        print(json.dumps({"error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
