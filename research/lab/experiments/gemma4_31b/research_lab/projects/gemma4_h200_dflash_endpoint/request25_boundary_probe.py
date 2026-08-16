#!/usr/bin/env python3
"""Pure contracts for the request-25 DFlash boundary probe."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any, TypeVar

SCHEMA_VERSION = 1
T = TypeVar("T")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def semantic_request_sha256(body: dict[str, Any]) -> str:
    semantic_body = {key: value for key, value in body.items() if key != "rid"}
    return sha256_bytes(canonical_bytes(semantic_body))


def input_ids_sha256(input_ids: Sequence[int]) -> str:
    return sha256_bytes(canonical_bytes([int(value) for value in input_ids]))


def request_rows(
    request_ids: Sequence[str] | None,
    request_slots: Sequence[int],
) -> list[tuple[int, int, str]]:
    """Return logical request rows while excluding graph-padding rows."""

    if request_ids is None:
        raise ValueError("logical request ids are unavailable")
    if len(request_ids) > len(request_slots):
        raise ValueError("more logical request ids than physical request rows")
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


def select_request_row(
    request_ids: Sequence[str] | None,
    request_slots: Sequence[int],
    target_rid: str,
) -> tuple[int, int] | None:
    matches = [
        (row, slot)
        for row, slot, rid in request_rows(request_ids, request_slots)
        if rid == target_rid
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("target RID appears more than once")
    return matches[0]


def row_major_slice(
    values: Sequence[T],
    *,
    row: int,
    rows: int,
    width: int,
    field: str,
) -> list[T]:
    if rows <= 0 or width <= 0:
        raise ValueError(f"{field} has invalid geometry")
    if len(values) != rows * width:
        raise ValueError(
            f"{field} length {len(values)} != rows*width {rows * width}"
        )
    if row < 0 or row >= rows:
        raise ValueError(f"{field} row is out of range")
    start = row * width
    return list(values[start : start + width])


def hash_plane_segments(
    raw: bytes,
    *,
    layer_planes: int,
    flat_count: int,
    sample_itemsize: int,
    offsets: Sequence[tuple[int, int]],
) -> list[str]:
    expected = layer_planes * flat_count * sample_itemsize
    if len(raw) != expected:
        raise ValueError(f"sample byte count {len(raw)} != expected {expected}")
    row_width_bytes = flat_count * sample_itemsize
    plane = memoryview(raw)
    digests: list[str] = []
    for start, end in offsets:
        if start < 0 or end < start or end > flat_count:
            raise ValueError("invalid segment offset")
        digest = hashlib.sha256()
        for layer_plane in range(layer_planes):
            base = layer_plane * row_width_bytes
            digest.update(
                plane[
                    base + start * sample_itemsize :
                    base + end * sample_itemsize
                ]
            )
        digests.append(digest.hexdigest())
    return digests


def make_boundary_record(
    *,
    request_id: str,
    request_index: int,
    request_semantic_sha256: str,
    request_input_ids_sha256: str,
    request_row: int,
    request_slot: int,
    input_ids: Sequence[int],
    positions: Sequence[int],
    seq_len: int,
    seq_len_cpu: int,
    out_cache_loc: Sequence[int],
    req_to_token_prefix: Sequence[int],
    pre_forward_kv_sha256: str,
    kv_digest_stats: dict[str, Any],
    raw_first_position_top1: int,
    post_adjustment_first_position_top1: int,
    source_binding_sha256: str,
) -> dict[str, Any]:
    if not request_id:
        raise ValueError("request id is empty")
    for name, digest in {
        "request_semantic_sha256": request_semantic_sha256,
        "request_input_ids_sha256": request_input_ids_sha256,
        "pre_forward_kv_sha256": pre_forward_kv_sha256,
        "source_binding_sha256": source_binding_sha256,
    }.items():
        if len(digest) != 64:
            raise ValueError(f"{name} is not SHA-256")
    if seq_len != seq_len_cpu:
        raise ValueError("device and host sequence lengths differ")
    if len(input_ids) != len(positions) or len(input_ids) != len(out_cache_loc):
        raise ValueError("verify row token, position, and output-location widths differ")
    if len(req_to_token_prefix) != seq_len:
        raise ValueError("request-to-token prefix length differs from sequence length")
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "phase": "request25_pre_forward_kv_pre_post_logit",
        "request_id": request_id,
        "request_index": int(request_index),
        "request_semantic_sha256": request_semantic_sha256,
        "request_row": int(request_row),
        "request_slot": int(request_slot),
        "pre_forward": {
            "input_ids": [int(value) for value in input_ids],
            "positions": [int(value) for value in positions],
            "seq_len": int(seq_len),
            "seq_len_cpu": int(seq_len_cpu),
            "out_cache_loc": [int(value) for value in out_cache_loc],
            "req_to_token_prefix": [int(value) for value in req_to_token_prefix],
            "req_to_token_prefix_sha256": sha256_bytes(
                canonical_bytes([int(value) for value in req_to_token_prefix])
            ),
            "kv_content_sha256": pre_forward_kv_sha256,
            "kv_digest_stats": kv_digest_stats,
        },
        "logits_boundary": {
            "raw_first_position_top1": int(raw_first_position_top1),
            "post_adjustment_first_position_top1": int(
                post_adjustment_first_position_top1
            ),
            "labels": [
                "raw_before_apply_dflash_verify_logits_adjustments",
                "after_apply_dflash_verify_logits_adjustments",
            ],
        },
        "source_binding_sha256": source_binding_sha256,
    }
    record["record_sha256"] = sha256_bytes(canonical_bytes(record))
    return record
