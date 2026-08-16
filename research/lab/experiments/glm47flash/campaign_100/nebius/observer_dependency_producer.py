"""Deterministic producer/materializer for observer dependency evidence.

This module is deliberately offline: the SQLite export is supplied by the caller and
the schema probe never invokes Nsight or a provider.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

NSYS_VERSION = "2026.3.1.157"
CONTRACT_VERSION = "observer-dependency-attribution-v1"
REQUIRED_SCHEMA = {
    "StringIds": {"id", "value"},
    "NVTX_EVENTS": {"start", "end", "text"},
    "CUDA_API_TRACE": {"start", "end", "correlationId", "streamId"},
}


class ProducerError(ValueError):
    pass


def content_hash(value: bytes | str | dict[str, Any] | list[Any]) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode()
    else:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def probe_target_schema(path: Path, *, version: str = NSYS_VERSION) -> dict[str, Any]:
    if version != NSYS_VERSION:
        raise ProducerError(f"unsupported Nsight Systems version: {version}")
    if not path.is_file():
        raise ProducerError("target SQLite export is unavailable")
    header = path.read_bytes()[:100]
    if len(header) < 20 or header[:16] != b"SQLite format 3\x00":
        raise ProducerError("target SQLite export header is invalid")
    page_size = int.from_bytes(header[16:18], "big") or 65536
    if path.stat().st_size % page_size:
        raise ProducerError("target SQLite export has trailing or truncated bytes")
    con = sqlite3.connect(path)
    try:
        tables = {
            row[0]: {item[1] for item in con.execute(f'PRAGMA table_info("{row[0]}")')}
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        con.close()
    missing = {table: sorted(columns - tables.get(table, set())) for table, columns in REQUIRED_SCHEMA.items() if not columns <= tables.get(table, set())}
    missing = {table: columns for table, columns in missing.items() if columns or table not in tables}
    if missing:
        raise ProducerError("target schema is missing required tables/columns: " + json.dumps(missing, sort_keys=True))
    return {"schema_version": 1, "nsys_version": version, "tables": {k: sorted(v) for k, v in sorted(tables.items()) if k in REQUIRED_SCHEMA}}


def _rows(con: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    try:
        con.row_factory = sqlite3.Row
        return [dict(row) for row in con.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
    except sqlite3.Error as error:
        raise ProducerError(f"required export table unavailable: {table}") from error


def materialize_export(path: Path, output: Path, *, request_rows: list[dict[str, Any]]) -> dict[str, Any]:
    schema = probe_target_schema(path)
    con = sqlite3.connect(path)
    try:
        nvtx = _rows(con, "NVTX_EVENTS")
        api = _rows(con, "CUDA_API_TRACE")
    finally:
        con.close()
    if not request_rows:
        raise ProducerError("raw request rows are required")
    raw_events = [{"kind": "nvtx", **row} for row in nvtx] + [{"kind": "cuda_api", **row} for row in api]
    if not raw_events:
        raise ProducerError("export contains no raw observer events")
    dependencies = []
    for index, row in enumerate(api):
        correlation = row.get("correlationId")
        if correlation is None:
            raise ProducerError(f"CUDA_API_TRACE[{index}] lacks correlationId")
        dependencies.append({"event_id": f"dependency-{index}", "source_correlation_id": correlation, "target_event_id": f"cuda-api-{index}", "edge_kind": "explicit-cuda-correlation"})
    output.mkdir(parents=True, exist_ok=True)
    request_bytes = b"".join(json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n" for row in request_rows)
    raw_bytes = b"".join(json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n" for row in raw_events)
    dep_bytes = b"".join(json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n" for row in dependencies)
    (output / "raw-events.jsonl").write_bytes(raw_bytes)
    (output / "dependency-events.jsonl").write_bytes(dep_bytes)
    manifest = {"schema_version": 1, "contract_id": CONTRACT_VERSION, "nsys_version": NSYS_VERSION, "raw_requests_sha256": content_hash(request_bytes), "raw_events_sha256": content_hash(raw_bytes), "dependency_events_sha256": content_hash(dep_bytes), "raw_request_rows": len(request_rows), "raw_event_rows": len(raw_events), "dependency_edge_rows": len(dependencies)}
    (output / "dependency-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"schema": schema, "manifest": manifest}


def package_raw_rows(output: Path, request_rows: list[dict[str, Any]], event_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not request_rows or not event_rows:
        raise ProducerError("full and partial packages must retain exact raw rows")
    request_bytes = b"".join(json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n" for row in request_rows)
    event_bytes = b"".join(json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n" for row in event_rows)
    result = {"raw_request_rows": request_rows, "raw_event_rows": event_rows, "raw_requests_sha256": content_hash(request_bytes), "raw_events_sha256": content_hash(event_bytes)}
    (output / "partial-packaging-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result
