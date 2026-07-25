#!/usr/bin/env python3
"""Pure contracts for the exact request-state observer.

Logical ownership is the opaque SGLang request id carried in ``ForwardBatch.rids``.
``req_pool_indices`` are retained only as physical-location telemetry.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

SCHEMA_VERSION = 2
REQUEST_COUNT = 32
T = TypeVar("T")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def split_by_lengths(values: Sequence[T], lengths: Sequence[int]) -> list[list[T]]:
    if any(int(length) < 0 for length in lengths):
        raise ValueError("segment lengths must be nonnegative")
    if sum(int(length) for length in lengths) != len(values):
        raise ValueError("segment lengths do not cover values")
    result: list[list[T]] = []
    offset = 0
    for length in lengths:
        end = offset + int(length)
        result.append(list(values[offset:end]))
        offset = end
    return result


def request_rows(
    request_ids: Sequence[str] | None,
    request_slots: Sequence[int],
) -> list[tuple[int, int, str]]:
    """Return actual request rows, excluding CUDA-graph padding rows.

    ``ForwardBatch.rids`` is constructed from ``ScheduleBatch.reqs`` before
    padding. ``req_pool_indices`` may subsequently be padded with the reserved
    physical row 0, so its length may be greater but never smaller here.
    """

    if request_ids is None:
        raise ValueError("ForwardBatch.rids is unavailable")
    if len(request_ids) > len(request_slots):
        raise ValueError("more request ids than request-pool rows")
    rows: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for row, request_id in enumerate(request_ids):
        rid = str(request_id)
        if not rid:
            raise ValueError(f"empty request id at row {row}")
        if rid in seen:
            raise ValueError(f"duplicate request id in one batch: {rid}")
        seen.add(rid)
        rows.append((row, int(request_slots[row]), rid))
    return rows


def pass_through(call: Callable[..., T], observe: Callable[[T], None], *args, **kwargs) -> T:
    result = call(*args, **kwargs)
    observe(result)
    return result


def make_event(
    *,
    arm: str,
    phase: str,
    request_id: str,
    request_slot: int,
    sequence_length_before: int,
    sequence_length_after: int,
    kv_locations: Sequence[int],
    kv_content_sha256: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    event = {
        "schema_version": SCHEMA_VERSION,
        "arm": arm,
        "phase": phase,
        "request_id": str(request_id),
        "request_slot": int(request_slot),
        "sequence_length_before": int(sequence_length_before),
        "sequence_length_after": int(sequence_length_after),
        "kv_locations": [int(value) for value in kv_locations],
        "kv_locations_sha256": sha256_bytes(
            canonical_bytes([int(value) for value in kv_locations])
        ),
        "kv_content_sha256": kv_content_sha256,
        **payload,
    }
    validate_event(event)
    event["event_sha256"] = sha256_bytes(canonical_bytes(event))
    return event


def validate_event(event: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "arm",
        "phase",
        "request_id",
        "request_slot",
        "sequence_length_before",
        "sequence_length_after",
        "kv_locations",
        "kv_locations_sha256",
        "kv_content_sha256",
    }
    missing = sorted(required - event.keys())
    if missing:
        raise ValueError(f"event missing fields: {missing}")
    if event["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported event schema")
    if event["phase"] not in {"target_prefill", "first_target_step"}:
        raise ValueError(f"unsupported phase: {event['phase']}")
    if not str(event["request_id"]):
        raise ValueError("empty request id")
    if int(event["sequence_length_after"]) < int(event["sequence_length_before"]):
        raise ValueError("sequence length regressed")
    if len(str(event["kv_content_sha256"])) != 64:
        raise ValueError("invalid KV content digest")
