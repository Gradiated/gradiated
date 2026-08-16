from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pathlib

import torch


LOGITS_PROCESSOR_SHA256 = (
    "e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14"
)
DRAFT_TOKENS = 12


def source_hash(module: object) -> str:
    return hashlib.sha256(pathlib.Path(module.__file__).read_bytes()).hexdigest()


def append_audit(row: dict) -> None:
    path_value = os.environ.get("COMPACTION_AUDIT")
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


def install() -> None:
    from sglang.srt.layers import logits_processor

    observed = source_hash(logits_processor)
    if observed != LOGITS_PROCESSOR_SHA256:
        raise RuntimeError(f"compaction_logits_source_mismatch:{observed}")
    cls = logits_processor.LogitsProcessor
    if getattr(cls, "_variable_decode_lm_head_installed", False):
        return
    original = cls._get_logits

    def variable_decode_get_logits(
        self,
        hidden_states,
        lm_head,
        logits_metadata,
        embedding_bias=None,
    ):
        if not logits_metadata.forward_mode.is_target_verify():
            return original(
                self,
                hidden_states,
                lm_head,
                logits_metadata,
                embedding_bias,
            )
        from sglang.srt.speculative import ngram_info

        lengths = ngram_info.CURRENT_NGRAM_VALID_LENGTHS
        # CUDA graph capture constructs a fixed-shape synthetic TARGET_VERIFY
        # batch before any NGRAM producer has run.  Preserve the qualified
        # fixed LM-head path for that dummy; real compact requests always
        # publish lengths and take the variable remap below.
        if lengths is None:
            append_audit(
                {
                    "candidate_symbol": (
                        "LogitsProcessor._get_logits.graph_capture_dummy"
                    ),
                    "compact_rows": hidden_states.shape[0],
                }
            )
            return original(
                self,
                hidden_states,
                lm_head,
                logits_metadata,
                embedding_bias,
            )
        if not lengths or sum(lengths) != hidden_states.shape[0]:
            raise RuntimeError(
                f"compaction_lm_head_length_mismatch:{lengths}:"
                f"{hidden_states.shape[0]}"
            )
        batch_size = len(lengths)
        offsets = [0]
        for length in lengths:
            offsets.append(offsets[-1] + length)
        chunk_metadata = dataclasses.replace(
            logits_metadata, next_token_logits_buffer=None
        )
        compact_logits = None
        for depth in range(DRAFT_TOKENS):
            padded_hidden = torch.zeros(
                (batch_size, hidden_states.shape[-1]),
                dtype=hidden_states.dtype,
                device=hidden_states.device,
            )
            active_requests = [
                request_index
                for request_index, length in enumerate(lengths)
                if depth < length
            ]
            if active_requests:
                compact_rows = torch.tensor(
                    [offsets[index] + depth for index in active_requests],
                    dtype=torch.int64,
                    device=hidden_states.device,
                )
                request_rows = torch.tensor(
                    active_requests,
                    dtype=torch.int64,
                    device=hidden_states.device,
                )
                padded_hidden[request_rows] = hidden_states[compact_rows]
            depth_logits = original(
                self,
                padded_hidden.contiguous(),
                lm_head,
                chunk_metadata,
                embedding_bias,
            )
            if compact_logits is None:
                compact_logits = torch.empty(
                    (hidden_states.shape[0], depth_logits.shape[-1]),
                    dtype=depth_logits.dtype,
                    device=depth_logits.device,
                )
            if active_requests:
                compact_logits[compact_rows] = depth_logits[request_rows]
        append_audit(
            {
                "batch_size": batch_size,
                "candidate_symbol": (
                    "LogitsProcessor._get_logits.variable_request_major_depth_slices"
                ),
                "compact_rows": hidden_states.shape[0],
                "fixed_rows": batch_size * DRAFT_TOKENS,
                "valid_lengths": lengths,
            }
        )
        return compact_logits

    cls._get_logits = variable_decode_get_logits
    cls._variable_decode_lm_head_installed = True
    append_audit(
        {
            "candidate_symbol": (
                "LogitsProcessor._get_logits.variable_request_major_depth_slices"
            ),
            "source_sha256": observed,
        }
    )
