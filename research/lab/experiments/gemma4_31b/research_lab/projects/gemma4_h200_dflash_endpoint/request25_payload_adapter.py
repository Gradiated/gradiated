#!/usr/bin/env python3
"""Recognize exact request 25 without changing its request body."""

from __future__ import annotations

from request25_boundary_probe import input_ids_sha256, semantic_request_sha256

REQUEST_INDEX = 25
REQUEST_SEMANTIC_SHA256 = (
    "ee2edfa7a9ff571b0268966f506c4cb868868ab880ac87c2684b055d48a0e150"
)
REQUEST_INPUT_IDS_SHA256 = (
    "51a23cdfb44941cb799a80c7ca3fd7f859e8558405f70976d1f8508703f6b360"
)


def is_request25(body: dict) -> bool:
    return (
        semantic_request_sha256(body) == REQUEST_SEMANTIC_SHA256
        and input_ids_sha256(body["input_ids"]) == REQUEST_INPUT_IDS_SHA256
    )
