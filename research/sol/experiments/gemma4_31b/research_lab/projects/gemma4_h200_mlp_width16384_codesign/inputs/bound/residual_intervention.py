from __future__ import annotations

import hashlib
import json
import os
import pathlib

import triton
import triton.language as tl


TARGET = pathlib.Path(
    "/sgl-workspace/sglang/python/sglang/srt/layers/attention/triton_backend.py"
)
EXPECTED_SHA256 = "429dbb4c3617331ac495b67cfdb6f1f38c6eceec2755a3df84f8f89b1b8fa80d"

OLD = '''    create_flashinfer_kv_indices_triton[(bs,)](
        req_to_token,
        req_pool_indices,
        window_kv_lens,
        window_kv_indptr,
        window_kv_start_idx,
        window_kv_indices,
        req_to_token.stride(0),
    )
    if hasattr(token_to_kv_pool, "translate_loc_from_full_to_swa"):
        kv_last_index = window_kv_indptr[-1]
        window_kv_indices[:kv_last_index] = (
            token_to_kv_pool.translate_loc_from_full_to_swa(
                window_kv_indices[:kv_last_index]
            )
        )
'''

NEW = '''    if hasattr(token_to_kv_pool, "translate_loc_from_full_to_swa"):
        from residual_intervention import launch_producer_fused_swa_indices

        launch_producer_fused_swa_indices(
            req_to_token,
            req_pool_indices,
            window_kv_lens,
            window_kv_indptr,
            window_kv_start_idx,
            window_kv_indices,
            token_to_kv_pool.full_to_swa_index_mapping,
            bs,
        )
    else:
        create_flashinfer_kv_indices_triton[(bs,)](
            req_to_token,
            req_pool_indices,
            window_kv_lens,
            window_kv_indptr,
            window_kv_start_idx,
            window_kv_indices,
            req_to_token.stride(0),
        )
'''


@triton.jit
def create_flashinfer_swa_kv_indices_triton(
    req_to_token_ptr,
    req_pool_indices_ptr,
    page_kernel_lens_ptr,
    kv_indptr,
    kv_start_idx,
    kv_indices_ptr,
    full_to_swa_mapping,
    req_to_token_ptr_stride: tl.constexpr,
):
    block_size: tl.constexpr = 512
    pid = tl.program_id(axis=0)
    req_pool_index = tl.load(req_pool_indices_ptr + pid)
    kv_indices_offset = tl.load(kv_indptr + pid)
    kv_start = tl.load(kv_start_idx + pid).to(tl.int32)
    kv_end = kv_start + tl.load(page_kernel_lens_ptr + pid).to(tl.int32)
    num_loop = tl.cdiv(kv_end - kv_start, block_size)
    for i in range(num_loop):
        offset = tl.arange(0, block_size).to(tl.int64) + i * block_size
        mask = offset < kv_end - kv_start
        full_index = tl.load(
            req_to_token_ptr
            + req_pool_index * req_to_token_ptr_stride
            + kv_start
            + offset,
            mask=mask,
            other=0,
        )
        swa_index = tl.load(full_to_swa_mapping + full_index, mask=mask, other=0)
        tl.store(kv_indices_ptr + kv_indices_offset + offset, swa_index, mask=mask)


_audited = False


def launch_producer_fused_swa_indices(
    req_to_token,
    req_pool_indices,
    window_kv_lens,
    window_kv_indptr,
    window_kv_start_idx,
    window_kv_indices,
    full_to_swa_mapping,
    batch_size: int,
) -> None:
    create_flashinfer_swa_kv_indices_triton[(batch_size,)](
        req_to_token,
        req_pool_indices,
        window_kv_lens,
        window_kv_indptr,
        window_kv_start_idx,
        window_kv_indices,
        full_to_swa_mapping,
        req_to_token.stride(0),
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
                        "block_size": 512,
                        "candidate_path": "create_flashinfer_kv_indices_triton.producer_fused_swa_mapping",
                        "device_count_proportional": True,
                        "graph_safe": True,
                        "no_capacity_wide_second_pass": True,
                        "no_device_scalar_read": True,
                        "phase": "runtime_invocation",
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        _audited = True


def install() -> None:
    raw = TARGET.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    text = raw.decode()
    if NEW in text:
        return
    if actual != EXPECTED_SHA256:
        raise RuntimeError(f"bound post-attention Triton backend mismatch:{actual}")
    if text.count(OLD) != 1:
        raise RuntimeError("producer-fused SWA patch target is not unique")
    TARGET.write_text(text.replace(OLD, NEW))
