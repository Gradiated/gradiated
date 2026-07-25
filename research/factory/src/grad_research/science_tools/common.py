from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..util import canonical_json_bytes, file_hash, utc_now


class ScienceToolError(RuntimeError):
    """A researcher-facing scientific tool could not produce valid evidence."""


def load_json(path: str | Path) -> Any:
    source = Path(path)
    try:
        return json.loads(source.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ScienceToolError(f"cannot read JSON from {source}: {error}") from error


def write_json_atomic(path: str | Path, value: Any) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical_json_bytes(value) + b"\n"
    handle = tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def write_jsonl_atomic(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            for row in rows:
                handle.write(canonical_json_bytes(dict(row)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    rows: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(source.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ScienceToolError(f"{source}:{line_number} must contain a JSON object")
            rows.append(value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ScienceToolError(f"cannot read JSONL from {source}: {error}") from error
    return rows


def artifact_identity(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise ScienceToolError(f"artifact is absent: {source}")
    return {
        "path": str(source),
        "sha256": file_hash(source),
        "size_bytes": source.stat().st_size,
    }


def _redact_command(command: Sequence[str]) -> list[str]:
    sensitive_words = (
        "authorization",
        "bearer",
        "cookie",
        "password",
        "secret",
        "token",
        "api-key",
        "api_key",
    )
    redacted: list[str] = []
    redact_next = False
    inspect_header_next = False
    credential_flags = {"-u", "-U", "--user", "--proxy-user"}
    for raw in command:
        part = str(raw)
        lowered = part.lower()
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue
        if inspect_header_next:
            inspect_header_next = False
            if any(word in lowered for word in sensitive_words):
                redacted.append("<redacted-header>")
                continue
        if part.startswith(("http://", "https://")):
            parsed = urllib.parse.urlsplit(part)
            host = parsed.hostname or ""
            if parsed.port is not None:
                host = f"{host}:{parsed.port}"
            part = urllib.parse.urlunsplit(
                (parsed.scheme, host, parsed.path, "", "")
            )
            lowered = part.lower()
        if part.startswith("-H") and part != "-H":
            header = part[2:]
            if any(word in header.lower() for word in sensitive_words):
                part = "-H<redacted-header>"
        elif part.startswith("--header="):
            header = part.split("=", 1)[1]
            if any(word in header.lower() for word in sensitive_words):
                part = "--header=<redacted-header>"
        elif part in {"-H", "--header"}:
            inspect_header_next = True
        elif part in credential_flags:
            redact_next = True
        elif any(part.startswith(f"{flag}=") for flag in credential_flags):
            part = f"{part.split('=', 1)[0]}=<redacted>"
        elif (
            len(part) > 2
            and not part.startswith("--")
            and part[:2] in {"-u", "-U"}
        ):
            part = f"{part[:2]}<redacted>"
        elif part.startswith("-") and any(word in lowered for word in sensitive_words):
            if "=" in part:
                part = f"{part.split('=', 1)[0]}=<redacted>"
            else:
                redact_next = True
        elif lowered.startswith(("bearer ", "basic ")) or any(
            lowered.startswith(f"{word}:") for word in sensitive_words
        ):
            part = "<redacted>"
        elif "=" in part and any(
            word in part.split("=", 1)[0].lower() for word in sensitive_words
        ):
            part = f"{part.split('=', 1)[0]}=<redacted>"
        redacted.append(part)
    return redacted


def run_command(
    command: Sequence[str],
    *,
    output_dir: str | Path,
    name: str,
    cwd: str | Path | None = None,
    timeout_seconds: float = 900,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not command:
        raise ScienceToolError(f"{name} command is empty")
    if timeout_seconds <= 0:
        raise ScienceToolError(f"{name} timeout must be positive")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    stdout_path = root / f"{name}.stdout.log"
    stderr_path = root / f"{name}.stderr.log"
    started_at = utc_now()
    started_clock = time.monotonic()
    merged_environment = os.environ.copy()
    if environment:
        merged_environment.update({str(key): str(value) for key, value in environment.items()})
    timed_out = False
    returncode: int | None = None
    spawn_error: str | None = None
    with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
        try:
            process = subprocess.Popen(
                [str(part) for part in command],
                cwd=None if cwd is None else str(cwd),
                env=merged_environment,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
        except OSError as error:
            spawn_error = str(error)
        else:
            try:
                returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    returncode = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    returncode = process.wait()
        stdout_handle.flush()
        stderr_handle.flush()
    result = {
        "schema_version": 1,
        "name": name,
        "command": _redact_command(command),
        "cwd": None if cwd is None else str(cwd),
        "started_at": started_at,
        "completed_at": utc_now(),
        "duration_seconds": time.monotonic() - started_clock,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "returncode": returncode,
        "stdout": artifact_identity(stdout_path),
        "stderr": artifact_identity(stderr_path),
    }
    if spawn_error is not None:
        result["spawn_error"] = spawn_error
    return result
