from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any, Iterable

from .state import project_events
from .util import ValidationError, canonical_json_bytes, content_hash, require_id, utc_now


class EventIntegrityError(RuntimeError):
    """The append-only event stream is malformed or its hash chain changed."""


class EventStore:
    def __init__(self, root: str | Path, program_id: str):
        self.root = Path(root)
        self.program_id = require_id("program_id", program_id)
        self.program_dir = self.root / "programs" / self.program_id
        self.program_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.program_dir / "events.jsonl"
        self.lock_path = self.program_dir / ".events.lock"
        self.state_path = self.program_dir / "STATE.json"

    def _load_unlocked(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        events = []
        previous_hash = None
        for line_number, line in enumerate(self.events_path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise EventIntegrityError(f"invalid JSON on event line {line_number}: {error}") from error
            expected_sequence = len(events) + 1
            if event.get("sequence") != expected_sequence:
                raise EventIntegrityError(f"event line {line_number} has a noncontiguous sequence")
            if event.get("program_id") != self.program_id:
                raise EventIntegrityError(f"event line {line_number} belongs to another program")
            if event.get("previous_hash") != previous_hash:
                raise EventIntegrityError(f"event line {line_number} breaks the previous-hash chain")
            claimed = event.get("event_hash")
            material = {key: value for key, value in event.items() if key != "event_hash"}
            if claimed != content_hash(material):
                raise EventIntegrityError(f"event line {line_number} hash mismatch")
            previous_hash = claimed
            events.append(event)
        return events

    def load(self) -> list[dict[str, Any]]:
        with self.lock_path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            try:
                return self._load_unlocked()
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def append(self, event_type: str, payload: dict[str, Any], *, timestamp: str | None = None) -> dict[str, Any]:
        return self.append_many([(event_type, payload, timestamp)])[0]

    def append_once(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        return self.append_many([(event_type, payload, timestamp, idempotency_key)])[0]

    def append_many(
        self,
        rows: Iterable[
            tuple[str, dict[str, Any], str | None, str]
            | tuple[str, dict[str, Any], str | None]
            | tuple[str, dict[str, Any]]
        ],
    ) -> list[dict[str, Any]]:
        materialized = list(rows)
        if not materialized:
            return []
        with self.lock_path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                events = self._load_unlocked()
                previous_hash = events[-1]["event_hash"] if events else None
                appended = []
                results = []
                keyed = {
                    event["idempotency_key"]: event
                    for event in events
                    if event.get("idempotency_key") is not None
                }
                for row in materialized:
                    if len(row) == 2:
                        event_type, payload = row
                        timestamp = None
                        idempotency_key = None
                    elif len(row) == 3:
                        event_type, payload, timestamp = row
                        idempotency_key = None
                    else:
                        event_type, payload, timestamp, idempotency_key = row
                    if not isinstance(payload, dict):
                        raise ValidationError("event payload must be an object")
                    if idempotency_key is not None:
                        idempotency_key = require_id("idempotency_key", idempotency_key)
                        existing = keyed.get(idempotency_key)
                        if existing is not None:
                            if existing["event_type"] != event_type or existing["payload"] != payload:
                                raise ValidationError(
                                    f"idempotency key {idempotency_key} was reused with different content"
                                )
                            results.append(existing)
                            continue
                    event = {
                        "schema_version": 1,
                        "sequence": len(events) + len(appended) + 1,
                        "timestamp": timestamp or utc_now(),
                        "program_id": self.program_id,
                        "event_type": require_id("event_type", event_type),
                        "payload": payload,
                        "previous_hash": previous_hash,
                    }
                    if idempotency_key is not None:
                        event["idempotency_key"] = idempotency_key
                    event["event_hash"] = content_hash(event)
                    previous_hash = event["event_hash"]
                    canonical_json_bytes(event)
                    appended.append(event)
                    results.append(event)
                    if idempotency_key is not None:
                        keyed[idempotency_key] = event
                with self.events_path.open("ab") as handle:
                    for event in appended:
                        handle.write(canonical_json_bytes(event) + b"\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                return results
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def project(self) -> dict[str, Any]:
        return project_events(self.load(), self.program_id)

    def write_state(self) -> Path:
        state = self.project()
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_bytes(json.dumps(state, indent=2, sort_keys=True).encode() + b"\n")
        os.replace(temporary, self.state_path)
        return self.state_path
