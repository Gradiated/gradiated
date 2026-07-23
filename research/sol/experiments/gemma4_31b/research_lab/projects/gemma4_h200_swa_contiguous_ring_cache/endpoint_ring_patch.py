from __future__ import annotations

import json
import os
from pathlib import Path

import torch

from ring_kv import (
    mark_ring_positions,
    restore_ring_prefix_if_needed,
    ring_decode_attention,
    store_ring_kv,
)


RING_TOKENS = 1024
RING_REQUESTS = 32
RING_SLOTS = RING_TOKENS * RING_REQUESTS
_INSTALLED = False


def _audit(row):
    path = os.environ.get("RING_CACHE_AUDIT")
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    from sglang.srt.layers.attention.triton_backend import TritonAttnBackend
    from sglang.srt.managers.scheduler_components.invariant_checker import (
        SchedulerInvariantChecker,
    )
    from sglang.srt.mem_cache.swa_memory_pool import SWAKVPool

    original_init = TritonAttnBackend.__init__
    original_extend = TritonAttnBackend.forward_extend
    original_decode = TritonAttnBackend.forward_decode
    original_check_swa_pool = SchedulerInvariantChecker._check_swa_pool

    def patched_init(self, model_runner, *args, **kwargs):
        original_init(self, model_runner, *args, **kwargs)
        pool = self.token_to_kv_pool
        if not isinstance(pool, SWAKVPool):
            raise RuntimeError("ring candidate requires the production hybrid SWA pool")
        allocator = self.token_to_kv_pool_allocator.swa_attn_allocator
        if pool.size_swa < RING_SLOTS + 1:
            raise RuntimeError(
                f"ring capacity unavailable:{pool.size_swa}<{RING_SLOTS + 1}"
            )
        # Slot zero remains the production padding sentinel. Slots 1..32768 are
        # permanently request-owned and removed from the ordinary SWA allocator.
        allocator.free_pages = allocator.free_pages[allocator.free_pages > RING_SLOTS]
        self._ring_last_positions = {}
        self._ring_audited_layers = set()
        _audit(
            {
                "event": "ring_region_reserved",
                "slots": RING_SLOTS,
                "slot_begin": 1,
                "slot_end": RING_SLOTS,
                "requests": RING_REQUESTS,
                "tokens_per_request": RING_TOKENS,
                "dtype": str(pool.dtype),
                "global_pool_unchanged": True,
            }
        )

    def ring_views(pool, layer_id):
        k_paged = pool.get_key_buffer(layer_id)
        v_paged = pool.get_value_buffer(layer_id)
        return (
            k_paged,
            v_paged,
            k_paged[1 : RING_SLOTS + 1].view(
                RING_REQUESTS, RING_TOKENS, k_paged.shape[1], k_paged.shape[2]
            ),
            v_paged[1 : RING_SLOTS + 1].view(
                RING_REQUESTS, RING_TOKENS, v_paged.shape[1], v_paged.shape[2]
            ),
        )

    def patched_extend(
        self,
        q,
        k,
        v,
        layer,
        forward_batch,
        save_kv_cache=True,
        sinks=None,
    ):
        pool = self.token_to_kv_pool
        if not pool.layers_mapping[layer.layer_id][1] or not save_kv_cache:
            return original_extend(
                self, q, k, v, layer, forward_batch, save_kv_cache, sinks
            )
        result = original_extend(
            self, q, k, v, layer, forward_batch, save_kv_cache, sinks
        )
        k_paged, v_paged, k_ring, v_ring = ring_views(pool, layer.layer_id)
        # ReqToTokenPool reserves request slot zero; compact active request
        # slots 1..32 onto ring rows 0..31.
        request_ids = torch.clamp(forward_batch.req_pool_indices - 1, min=0)
        if request_ids.numel() > RING_REQUESTS:
            raise RuntimeError("extend request count exceeds exact c32")
        prefix_lens = forward_batch.extend_prefix_lens
        if prefix_lens is not None:
            scratch_last = torch.full(
                (RING_REQUESTS,), -2**30, dtype=torch.int64, device=q.device
            )
            restore_ring_prefix_if_needed(
                k_paged,
                v_paged,
                k_ring,
                v_ring,
                request_ids,
                prefix_lens,
                self.forward_metadata.window_kv_indptr,
                self.forward_metadata.window_kv_indices,
                scratch_last,
                exclude_last=False,
                force=True,
            )
        lengths = forward_batch.extend_seq_lens
        repeated_ids = torch.repeat_interleave(
            request_ids, lengths, output_size=k.shape[0]
        )
        starts = torch.cumsum(lengths, dim=0) - lengths
        repeated_starts = torch.repeat_interleave(
            starts, lengths, output_size=k.shape[0]
        )
        repeated_prefix = torch.repeat_interleave(
            prefix_lens, lengths, output_size=k.shape[0]
        )
        positions = (
            torch.arange(k.shape[0], device=k.device)
            - repeated_starts
            + repeated_prefix
        )
        store_ring_kv(k, v, k_ring, v_ring, repeated_ids, positions)
        return result

    def patched_decode(
        self,
        q,
        k,
        v,
        layer,
        forward_batch,
        save_kv_cache=True,
        sinks=None,
    ):
        pool = self.token_to_kv_pool
        mapping = pool.layers_mapping[layer.layer_id]
        if not mapping[1]:
            return original_decode(
                self, q, k, v, layer, forward_batch, save_kv_cache, sinks
            )
        if q.shape[0] > RING_REQUESTS:
            raise RuntimeError(f"ring padded batch exceeds exact c32:{q.shape[0]}")
        _k_paged, _v_paged, k_ring, v_ring = ring_views(pool, layer.layer_id)
        request_ids = torch.clamp(forward_batch.req_pool_indices - 1, min=0)
        seq_lens = forward_batch.seq_lens
        absolute_positions = seq_lens - 1
        store_ring_kv(k, v, k_ring, v_ring, request_ids, absolute_positions)

        previous_decode = self.decode_attention_fwd

        def ring_consumer(
            q_view,
            _k_paged,
            _v_paged,
            output,
            kv_indptr,
            _kv_indices,
            attn_logits,
            attn_lse,
            num_kv_splits,
            max_kv_splits,
            sm_scale,
            k_scale,
            v_scale,
            **_kwargs,
        ):
            context_lens = (
                self.forward_metadata.window_kv_indptr[1:]
                - self.forward_metadata.window_kv_indptr[:-1]
            )
            ring_starts = (seq_lens - context_lens) & (RING_TOKENS - 1)
            return ring_decode_attention(
                q_view,
                k_ring,
                v_ring,
                output,
                context_lens,
                ring_starts,
                kv_indptr,
                attn_logits,
                attn_lse,
                num_kv_splits,
                max_kv_splits,
                sm_scale,
                k_scale,
                v_scale,
                request_ids=request_ids,
            )

        self.decode_attention_fwd = ring_consumer
        try:
            # The local stock store is replaced, not duplicated. Global paged
            # writes and every extend/prefix-cache operation remain production.
            result = original_decode(
                self, q, k, v, layer, forward_batch, False, sinks
            )
        finally:
            self.decode_attention_fwd = previous_decode
        if layer.layer_id not in self._ring_audited_layers:
            self._ring_audited_layers.add(layer.layer_id)
            _audit(
                {
                    "event": "ring_decode_captured",
                    "layer_id": layer.layer_id,
                    "layer_type": "sliding_attention",
                    "q_heads": layer.tp_q_head_num,
                    "kv_heads": k_ring.shape[2],
                    "head_dim": k_ring.shape[3],
                    "window": RING_TOKENS,
                    "consumer": "ring_decode_attention",
                    "producer": "store_ring_kv",
                }
            )
        return result

    TritonAttnBackend.__init__ = patched_init
    TritonAttnBackend.forward_extend = patched_extend
    TritonAttnBackend.forward_decode = patched_decode

    def patched_check_swa_pool(self, ps, uncached=0):
        # The ring reservation is intentional capacity, not a leak. Preserve
        # every other term and the production checker itself.
        original_total = self.swa_tokens_per_layer
        self.swa_tokens_per_layer = original_total - RING_SLOTS
        try:
            return original_check_swa_pool(self, ps, uncached)
        finally:
            self.swa_tokens_per_layer = original_total

    SchedulerInvariantChecker._check_swa_pool = patched_check_swa_pool
    _INSTALLED = True
