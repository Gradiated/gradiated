from __future__ import annotations

from dataclasses import dataclass

import torch
import triton
import triton.language as tl


@triton.jit
def _commit_decode_metadata(
    req_to_token,
    req_pool_indices,
    seq_lens_in,
    orig_seq_lens_in,
    out_cache_loc,
    seq_lens_out,
    orig_seq_lens_out,
    req_to_token_stride,
    batch_size: tl.constexpr,
    block_size: tl.constexpr,
):
    row = tl.program_id(0) * block_size + tl.arange(0, block_size)
    mask = row < batch_size
    req = tl.load(req_pool_indices + row, mask=mask)
    seq = tl.load(seq_lens_in + row, mask=mask)
    orig = tl.load(orig_seq_lens_in + row, mask=mask)
    slot = tl.load(out_cache_loc + row, mask=mask).to(tl.int32)
    tl.store(req_to_token + req * req_to_token_stride + seq, slot, mask=mask)
    tl.store(seq_lens_out + row, seq + 1, mask=mask)
    tl.store(orig_seq_lens_out + row, orig + 1, mask=mask)


@dataclass
class DecodeMetadataOutputs:
    seq_lens: torch.Tensor
    orig_seq_lens: torch.Tensor


class DecodeSchedulerTaskGraph:
    """One device task for the decode allocator-to-forward metadata boundary.

    KV slot selection and eviction stay host-owned. This object replaces only
    the three ordered device tasks that publish selected slots and advance the
    two model-consumed length vectors. Two output-buffer sets preserve the
    pinned runtime's overlap lifetime: the previous forward may retain one set
    while the schedule stream writes the other.
    """

    def __init__(self, seq_lens: torch.Tensor, orig_seq_lens: torch.Tensor):
        if seq_lens.device.type != "cuda" or orig_seq_lens.device.type != "cuda":
            raise ValueError("decode_scheduler_task_graph_requires_cuda")
        if seq_lens.dtype != torch.int64 or orig_seq_lens.dtype != torch.int32:
            raise ValueError("decode_scheduler_task_graph_dtype_mismatch")
        if seq_lens.ndim != 1 or orig_seq_lens.shape != seq_lens.shape:
            raise ValueError("decode_scheduler_task_graph_shape_mismatch")
        self._seq_buffers = [torch.empty_like(seq_lens), torch.empty_like(seq_lens)]
        self._orig_buffers = [
            torch.empty_like(orig_seq_lens),
            torch.empty_like(orig_seq_lens),
        ]
        self._next_buffer = 0

    def compatible(
        self, seq_lens: torch.Tensor, orig_seq_lens: torch.Tensor
    ) -> bool:
        return (
            seq_lens.device.type == "cuda"
            and orig_seq_lens.device == seq_lens.device
            and seq_lens.dtype == torch.int64
            and orig_seq_lens.dtype == torch.int32
            and seq_lens.ndim == 1
            and orig_seq_lens.shape == seq_lens.shape
            and self._seq_buffers[0].shape == seq_lens.shape
        )

    def commit(
        self,
        *,
        req_to_token: torch.Tensor,
        req_pool_indices: torch.Tensor,
        seq_lens: torch.Tensor,
        orig_seq_lens: torch.Tensor,
        out_cache_loc: torch.Tensor,
    ) -> DecodeMetadataOutputs:
        batch_size = seq_lens.numel()
        if batch_size == 0:
            raise ValueError("decode_scheduler_task_graph_empty_batch")
        if not self.compatible(seq_lens, orig_seq_lens):
            raise ValueError("decode_scheduler_task_graph_incompatible_state")
        if (
            req_to_token.device != seq_lens.device
            or req_pool_indices.device != seq_lens.device
            or out_cache_loc.device != seq_lens.device
        ):
            raise ValueError("decode_scheduler_task_graph_device_mismatch")
        if req_to_token.dtype != torch.int32:
            raise ValueError("decode_scheduler_task_graph_pool_dtype_mismatch")
        if req_pool_indices.dtype != torch.int64 or out_cache_loc.dtype != torch.int64:
            raise ValueError("decode_scheduler_task_graph_index_dtype_mismatch")
        if (
            req_pool_indices.shape != seq_lens.shape
            or out_cache_loc.shape != seq_lens.shape
        ):
            raise ValueError("decode_scheduler_task_graph_index_shape_mismatch")
        if req_to_token.ndim != 2 or req_to_token.stride(1) != 1:
            raise ValueError("decode_scheduler_task_graph_pool_layout_mismatch")

        target = self._next_buffer
        self._next_buffer ^= 1
        seq_lens_out = self._seq_buffers[target]
        orig_seq_lens_out = self._orig_buffers[target]
        block_size = triton.next_power_of_2(batch_size)
        _commit_decode_metadata[(1,)](
            req_to_token,
            req_pool_indices,
            seq_lens,
            orig_seq_lens,
            out_cache_loc,
            seq_lens_out,
            orig_seq_lens_out,
            req_to_token.stride(0),
            batch_size=batch_size,
            block_size=block_size,
            num_warps=1 if block_size <= 32 else 4,
        )
        return DecodeMetadataOutputs(seq_lens_out, orig_seq_lens_out)


def commit_schedule_batch_decode_metadata(
    batch, out_cache_loc: torch.Tensor
) -> None:
    committer = getattr(batch, "_decode_scheduler_task_graph", None)
    if committer is None or not committer.compatible(
        batch.seq_lens, batch.orig_seq_lens
    ):
        committer = DecodeSchedulerTaskGraph(batch.seq_lens, batch.orig_seq_lens)
        batch._decode_scheduler_task_graph = committer
    outputs = committer.commit(
        req_to_token=batch.req_to_token_pool.req_to_token,
        req_pool_indices=batch.req_pool_indices,
        seq_lens=batch.seq_lens,
        orig_seq_lens=batch.orig_seq_lens,
        out_cache_loc=out_cache_loc,
    )
    batch.seq_lens = outputs.seq_lens
    batch.orig_seq_lens = outputs.orig_seq_lens
