"""Decode-shape LM-head projection for pinned SGLang NGRAM verification."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pathlib
from typing import Callable

import torch


LOGITS_PROCESSOR_SHA256 = (
    "e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14"
)
DRAFT_TOKENS = 12
_baseline_values: torch.Tensor | None = None
_baseline_ids: torch.Tensor | None = None


def _source_hash(module: object) -> str:
    return hashlib.sha256(pathlib.Path(module.__file__).read_bytes()).hexdigest()


def _append_audit(row: dict) -> None:
    path_value = os.environ.get("DECODE_EQ_AUDIT")
    if not path_value:
        return
    path = pathlib.Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        payload = json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
        os.write(descriptor, payload.encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def project_decode_shapes(
    original: Callable,
    processor: object,
    hidden_states: torch.Tensor,
    lm_head: object,
    logits_metadata: object,
    embedding_bias: torch.Tensor | None,
    draft_tokens: int,
) -> torch.Tensor:
    rows = hidden_states.shape[0]
    if rows % draft_tokens:
        raise RuntimeError(
            f"decode_equivalent_rows_not_divisible:{rows}:{draft_tokens}"
        )
    batch_size = rows // draft_tokens
    chunk_metadata = dataclasses.replace(
        logits_metadata, next_token_logits_buffer=None
    )
    request_major = hidden_states.reshape(
        batch_size, draft_tokens, hidden_states.shape[-1]
    )
    depth_logits = [
        original(
            processor,
            request_major[:, depth, :].contiguous(),
            lm_head,
            chunk_metadata,
            embedding_bias,
        )
        for depth in range(draft_tokens)
    ]
    logits = torch.stack(depth_logits, dim=1).reshape(
        rows, depth_logits[0].shape[-1]
    )
    if logits_metadata.next_token_logits_buffer is not None:
        buffer = logits_metadata.next_token_logits_buffer
        buffer.copy_(logits)
        logits = buffer
    return logits


def get_shadow_baseline(rows: int) -> tuple[torch.Tensor, torch.Tensor] | None:
    if _baseline_values is None or _baseline_ids is None:
        return None
    return _baseline_values[:rows], _baseline_ids[:rows]


def install() -> None:
    from sglang.srt.layers import logits_processor

    observed = _source_hash(logits_processor)
    if observed != LOGITS_PROCESSOR_SHA256:
        raise RuntimeError(
            f"decode_equivalent_logits_source_mismatch:{observed}"
        )
    cls = logits_processor.LogitsProcessor
    if getattr(cls, "_decode_equivalent_lm_head_installed", False):
        return

    original = cls._get_logits
    max_rows = int(os.environ.get("DECODE_EQ_MAX_ROWS", str(32 * DRAFT_TOKENS)))
    shadow = os.environ.get("DECODE_EQ_SHADOW_BASELINE") == "1"

    def decode_equivalent_get_logits(
        self,
        hidden_states,
        lm_head,
        logits_metadata,
        embedding_bias=None,
    ):
        global _baseline_values, _baseline_ids
        if not logits_metadata.forward_mode.is_target_verify():
            return original(
                self,
                hidden_states,
                lm_head,
                logits_metadata,
                embedding_bias,
            )

        if shadow:
            shadow_metadata = dataclasses.replace(
                logits_metadata, next_token_logits_buffer=None
            )
            baseline = original(
                self,
                hidden_states,
                lm_head,
                shadow_metadata,
                embedding_bias,
            )
            if _baseline_values is None:
                _baseline_values = torch.empty(
                    (max_rows, 2),
                    dtype=baseline.dtype,
                    device=baseline.device,
                )
                _baseline_ids = torch.empty(
                    (max_rows, 2),
                    dtype=torch.int64,
                    device=baseline.device,
                )
            values, ids = torch.topk(baseline, k=2, dim=-1)
            _baseline_values[: hidden_states.shape[0]].copy_(values)
            _baseline_ids[: hidden_states.shape[0]].copy_(ids)

        return project_decode_shapes(
            original,
            self,
            hidden_states,
            lm_head,
            logits_metadata,
            embedding_bias,
            DRAFT_TOKENS,
        )

    cls._get_logits = decode_equivalent_get_logits
    cls._decode_equivalent_lm_head_installed = True
    _append_audit(
        {
            "candidate_symbol": "LogitsProcessor._get_logits.decode_equivalent_request_major_depth_slices",
            "draft_tokens": DRAFT_TOKENS,
            "shadow_baseline": shadow,
            "source_sha256": observed,
        }
    )
