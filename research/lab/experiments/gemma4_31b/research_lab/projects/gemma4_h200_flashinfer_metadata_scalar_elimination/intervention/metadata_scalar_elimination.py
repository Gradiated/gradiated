from __future__ import annotations

import hashlib
import json
import os
import pathlib

import torch
import triton
import triton.language as tl


TARGET = pathlib.Path(
    "/sgl-workspace/sglang/python/sglang/srt/layers/attention/triton_backend.py"
)
EXPECTED_SHA256 = "429dbb4c3617331ac495b67cfdb6f1f38c6eceec2755a3df84f8f89b1b8fa80d"

OLD = '''    if hasattr(token_to_kv_pool, "translate_loc_from_full_to_swa"):
        kv_last_index = window_kv_indptr[-1]
        window_kv_indices[:kv_last_index] = (
            token_to_kv_pool.translate_loc_from_full_to_swa(
                window_kv_indices[:kv_last_index]
            )
        )
'''

NEW = '''    if hasattr(token_to_kv_pool, "translate_loc_from_full_to_swa"):
        from residual_intervention import translate_valid_swa_indices_inplace

        translate_valid_swa_indices_inplace(
            window_kv_indices,
            window_kv_indptr,
            bs,
            token_to_kv_pool.full_to_swa_index_mapping,
        )
'''


@triton.jit
def _translate_valid_swa_indices_inplace(
    kv_indices,
    kv_indptr,
    batch_size,
    full_to_swa_mapping,
    capacity: tl.constexpr,
    BLOCK_SIZE: tl.constexpr,
):
    offsets = tl.program_id(0) * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE)
    valid_count = tl.load(kv_indptr + batch_size)
    mask = offsets < valid_count
    full_indices = tl.load(kv_indices + offsets, mask=mask, other=0)
    swa_indices = tl.load(full_to_swa_mapping + full_indices, mask=mask, other=0)
    tl.store(kv_indices + offsets, swa_indices, mask=mask)


_audited = False


def translate_valid_swa_indices_inplace(
    kv_indices: torch.Tensor,
    kv_indptr: torch.Tensor,
    batch_size: int,
    full_to_swa_mapping: torch.Tensor,
) -> None:
    capacity = kv_indices.numel()
    if capacity:
        _translate_valid_swa_indices_inplace[(triton.cdiv(capacity, 256),)](
            kv_indices,
            kv_indptr,
            batch_size,
            full_to_swa_mapping,
            capacity,
            BLOCK_SIZE=256,
        )
    global _audited
    if not _audited and (audit := os.environ.get("RESIDUAL_CANDIDATE_AUDIT")):
        destination = pathlib.Path(audit)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a") as handle:
            handle.write(
                json.dumps(
                    {
                        "batch_size": batch_size,
                        "candidate_path": "update_sliding_window_buffer.device_count_masked_swa_gather",
                        "capacity": capacity,
                        "graph_safe": True,
                        "no_device_scalar_read": True,
                        "phase": "runtime_invocation",
                        "valid_count_source": "window_kv_indptr[batch_size] read inside Triton kernel",
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        _audited = True


def install() -> None:
    raw = TARGET.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if NEW in raw.decode():
        return
    if actual != EXPECTED_SHA256:
        raise RuntimeError(f"bound post-attention Triton backend mismatch:{actual}")
    text = raw.decode()
    if text.count(OLD) != 1:
        raise RuntimeError("metadata scalar patch target is not unique")
    TARGET.write_text(text.replace(OLD, NEW))
