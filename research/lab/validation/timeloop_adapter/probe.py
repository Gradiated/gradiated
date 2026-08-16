from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import io
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

from validation.timeloop_adapter.normalize import build_report


PROBE_SCHEMA_VERSION = "inference-foundry.timeloop-external-probe.v1"
NATIVE_DEPENDENCIES = (
    "libconfig++",
    "yaml-cpp",
    "isl",
    "barvinok",
    "ntl",
    "polylibgmp",
    "gmp",
)


def run_probe(
    request_path: Path,
    repo_root: Path,
    output_directory: Path,
) -> dict[str, object]:
    request = _load_object(request_path)
    raw_directory = output_directory / "raw"
    raw_directory.mkdir(parents=True, exist_ok=True)
    paths = {
        key: repo_root / str(request[key])
        for key in (
            "problem_export_path",
            "problem_yaml_path",
            "architecture_path",
            "mapper_path",
        )
    }
    installation = _installation_identity(request)
    (raw_directory / "installation.stdout").write_text(
        json.dumps(installation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (raw_directory / "installation.stderr").write_text("", encoding="utf-8")
    dependency_probe = _probe_dependencies()
    (raw_directory / "dependencies.stdout").write_text(
        "\n".join(
            f"{name}\t{'found' if result['found'] else 'missing'}\t{result['version']}"
            for name, result in dependency_probe.items()
        )
        + "\n",
        encoding="utf-8",
    )
    (raw_directory / "dependencies.stderr").write_text("", encoding="utf-8")
    frontend = _run_frontend(paths, raw_directory)
    native = _run_native(request, paths, repo_root, raw_directory)
    probe: dict[str, object] = {
        "schema_version": PROBE_SCHEMA_VERSION,
        "frontend": frontend,
        "native_backend": native,
        "environment": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "python_executable": sys.executable,
            "installation": installation,
            "native_dependency_probe": dependency_probe,
        },
        "inputs": {
            "architecture": _file_identity(paths["architecture_path"]),
            "mapper": _file_identity(paths["mapper_path"]),
            "problem_yaml": _file_identity(paths["problem_yaml_path"]),
        },
    }
    probe_path = output_directory / "probe.json"
    probe_path.write_text(
        json.dumps(probe, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = build_report(
        request_path,
        paths["problem_export_path"],
        probe_path,
        raw_directory,
    )
    report_path = output_directory / "report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe a pinned Timeloop v4 backend.")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(arguments)
    try:
        report = run_probe(
            args.request,
            args.repo_root.resolve(),
            args.output_directory,
        )
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "output": str(args.output_directory / "report.json"),
                "content_id": report["content_identity_sha256"],
                "status": report["status"],
            },
            sort_keys=True,
        )
    )
    return 0


def _run_frontend(paths: dict[str, Path], raw_directory: Path) -> dict[str, object]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    started = time.perf_counter_ns()
    result: dict[str, object]
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            from timeloopfe.v4 import Specification

            specification = Specification.from_yaml_files(
                str(paths["architecture_path"]),
                str(paths["mapper_path"]),
                str(paths["problem_yaml_path"]),
            )
            processed = specification._process()
            instance = {
                key: int(processed.problem.instance[key])
                for key in ("B", "M", "N", "K")
            }
            result = {
                "status": "succeeded",
                "shape_name": str(processed.problem.shape.name),
                "dimensions": [
                    str(value) for value in processed.problem.shape.dimensions
                ],
                "instance": instance,
            }
            print("FRONTEND_PROCESS_OK")
            print(json.dumps(result, sort_keys=True))
        except Exception as error:
            result = {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "shape_name": None,
                "dimensions": [],
                "instance": {},
            }
            print("FRONTEND_PROCESS_FAILED")
            print(f"{type(error).__name__}: {error}", file=sys.stderr)
    result["runtime_nanoseconds"] = time.perf_counter_ns() - started
    (raw_directory / "frontend.stdout").write_text(stdout.getvalue(), encoding="utf-8")
    (raw_directory / "frontend.stderr").write_text(stderr.getvalue(), encoding="utf-8")
    return result


def _run_native(
    request: dict[str, object],
    paths: dict[str, Path],
    repo_root: Path,
    raw_directory: Path,
) -> dict[str, object]:
    native_request = _require_object(request, "native_backend")
    executable_name = str(native_request["executable"])
    executable_path = shutil.which(executable_name)
    frontend_cli = Path(sys.executable).with_name("timeloop")
    output_directory = raw_directory / "native-output"
    output_directory.mkdir(parents=True, exist_ok=True)
    command = [
        str(frontend_cli),
        "mapper",
        str(paths["architecture_path"]),
        str(paths["mapper_path"]),
        str(paths["problem_yaml_path"]),
        "-o",
        str(output_directory),
    ]
    timeout_seconds = int(native_request["timeout_seconds"])
    started = time.perf_counter_ns()
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        wrapper_exit_code: int | None = completed.returncode
        if executable_path is None:
            status = "executable_not_found"
        elif completed.returncode == 0:
            status = "succeeded"
        else:
            status = "nonzero_exit"
    except subprocess.TimeoutExpired as error:
        stdout = _timeout_text(error.stdout)
        stderr = _timeout_text(error.stderr)
        wrapper_exit_code = None
        status = "timed_out"
    runtime_nanoseconds = time.perf_counter_ns() - started
    (raw_directory / "native.stdout").write_text(stdout, encoding="utf-8")
    (raw_directory / "native.stderr").write_text(stderr, encoding="utf-8")
    return {
        "status": status,
        "runtime_nanoseconds": runtime_nanoseconds,
        "executable_name": executable_name,
        "executable_path": executable_path,
        "frontend_cli_path": str(frontend_cli),
        "frontend_cli_exit_code": wrapper_exit_code,
        "native_exit_code_observed_in_frontend_output": (
            127 if "return code 127" in stderr else None
        ),
        "command": command,
        "timeout_seconds": timeout_seconds,
    }


def _installation_identity(request: dict[str, object]) -> dict[str, object]:
    return {
        "frontend": _package_identity(
            "timeloopfe", _require_object(request, "frontend")
        ),
        "accelergy": _package_identity(
            "accelergy", _require_object(request, "accelergy")
        ),
    }


def _package_identity(
    distribution_name: str, expected: dict[str, object]
) -> dict[str, object]:
    distribution = importlib.metadata.distribution(distribution_name)
    direct_url_path = (
        Path(distribution.locate_file(""))
        / f"{distribution_name}-0.4.dist-info/direct_url.json"
    )
    direct_url = _load_object(direct_url_path)
    vcs_info = _require_object(direct_url, "vcs_info")
    observed_revision = str(vcs_info.get("commit_id", ""))
    expected_revision = str(expected["revision"])
    observed_version = distribution.version
    expected_version = str(expected["version"])
    if observed_revision != expected_revision:
        raise RuntimeError(
            f"{distribution_name} revision mismatch: {observed_revision} != {expected_revision}"
        )
    if observed_version != expected_version:
        raise RuntimeError(
            f"{distribution_name} version mismatch: {observed_version} != {expected_version}"
        )
    return {
        "name": distribution_name,
        "version": observed_version,
        "revision": observed_revision,
        "repository": direct_url.get("url"),
        "direct_url_path": str(direct_url_path),
    }


def _probe_dependencies() -> dict[str, dict[str, object]]:
    return {name: _pkg_config(name) for name in NATIVE_DEPENDENCIES}


def _pkg_config(name: str) -> dict[str, object]:
    executable = shutil.which("pkg-config")
    if executable is None:
        return {"found": False, "version": None, "probe": "pkg-config unavailable"}
    completed = subprocess.run(
        [executable, "--modversion", name],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return {
        "found": completed.returncode == 0,
        "version": completed.stdout.strip() or None,
        "probe": f"pkg-config --modversion {name}",
    }


def _load_object(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return document


def _require_object(document: dict[str, object], key: str) -> dict[str, object]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _timeout_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    return (
        value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
    )


def _file_identity(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


if __name__ == "__main__":
    raise SystemExit(main())
