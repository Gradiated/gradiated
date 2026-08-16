"""Content-addressed retention for generated host-bootstrap launchers."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any


def launcher_record(payload: bytes) -> dict[str, Any]:
    return {
        "encoding": "base64",
        "byte_length": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": base64.b64encode(payload).decode("ascii"),
    }


def launcher_bytes(record: dict[str, Any]) -> bytes:
    if not isinstance(record, dict) or record.get("encoding") != "base64":
        raise ValueError("launcher record encoding is invalid")
    encoded = record.get("bytes")
    if not isinstance(encoded, str):
        raise ValueError("launcher bytes are missing")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("launcher bytes are not valid base64") from error
    expected = launcher_record(payload)
    if {key: record.get(key) for key in ("byte_length", "sha256")} != {
        key: expected[key] for key in ("byte_length", "sha256")
    }:
        raise ValueError("launcher length or SHA-256 does not match retained bytes")
    return payload


def write_launcher(path: Path, payload: bytes, record_path: Path | None = None) -> dict[str, Any]:
    record = launcher_record(payload)
    path.write_bytes(payload)
    if record_path is not None:
        record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return record


def validate_file(path: Path, record: dict[str, Any]) -> bytes:
    if not path.is_file():
        raise ValueError(f"retained launcher is missing: {path}")
    payload = path.read_bytes()
    expected = launcher_bytes(record)
    if payload != expected:
        raise ValueError("retained launcher bytes differ from immutable record")
    return payload
