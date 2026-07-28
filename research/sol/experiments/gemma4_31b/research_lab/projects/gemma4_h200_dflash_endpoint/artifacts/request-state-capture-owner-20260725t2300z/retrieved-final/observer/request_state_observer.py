#!/usr/bin/env python3
"""Pure contracts for the exact request-state observer."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Sequence
from typing import Any, TypeVar

SCHEMA_VERSION = 1
REQUEST_MARKER_BASE = 200000
REQUEST_COUNT = 32
T = TypeVar("T")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def request_index_from_tokens(tokens: Iterable[int]) -> int | None:
    indices = {
        int(token) - REQUEST_MARKER_BASE
        for token in tokens
        if REQUEST_MARKER_BASE <= int(token) < REQUEST_MARKER_BASE + REQUEST_COUNT
    }
    if len(indices) > 1:
        raise ValueError(f"multiple request markers in one request segment: {indices}")
    return next(iter(indices)) if indices else None


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


def bind_slots(
    slots: Sequence[int],
    token_segments: Sequence[Sequence[int]],
    prior: dict[int, int] | None = None,
) -> dict[int, int]:
    if len(slots) != len(token_segments):
        raise ValueError("slot and token-segment counts differ")
    result = dict(prior or {})
    for slot, segment in zip(slots, token_segments, strict=True):
        request_index = request_index_from_tokens(segment)
        if request_index is None:
            continue
        existing = result.get(int(slot))
        if existing is not None and existing != request_index:
            raise ValueError(
                f"slot {slot} rebound from request {existing} to {request_index}"
            )
        result[int(slot)] = request_index
    return result


def pass_through(call: Callable[..., T], observe: Callable[[T], None], *args, **kwargs) -> T:
    result = call(*args, **kwargs)
    observe(result)
    return result


def make_event(
    *,
    arm: str,
    phase: str,
    request_index: int,
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
        "request_index": int(request_index),
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
        "request_index",
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
    if not 0 <= int(event["request_index"]) < REQUEST_COUNT:
        raise ValueError("request index outside exact-c32")
    if int(event["sequence_length_after"]) < int(event["sequence_length_before"]):
        raise ValueError("sequence length regressed")
    if len(str(event["kv_content_sha256"])) != 64:
        raise ValueError("invalid KV content digest")

