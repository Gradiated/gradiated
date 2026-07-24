from __future__ import annotations

import json
import os
from pathlib import Path

import torch

from ring_ownership import RingOwnership
from ring_kv import (
    restore_ring_prefix_if_needed,
    ring_decode_attention,
    store_ring_kv,
    store_ring_kv_bytes,
)


RING_TOKENS = 1024
_INSTALLED = False
_RESERVED_RING_SLOTS = 0


def _audit(row):
    path = os.environ.get("RING_CACHE_AUDIT")
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _capturing() -> bool:
    try:
        return torch.cuda.is_current_stream_capturing()
    except RuntimeError:
        return False


def _tensor_values(value):
    return value.detach().cpu().tolist()


def _comparison(candidate, control):
    candidate_float = candidate.float()
    control_float = control.float()
    delta = candidate_float - control_float
    denominator = torch.linalg.vector_norm(control_float).clamp_min(1e-12)
    return {
        "all_finite": bool(torch.isfinite(candidate_float).all().item()),
        "max_abs": float(delta.abs().max().item()),
        "relative_l2": float(
            (torch.linalg.vector_norm(delta) / denominator).item()
        ),
        "exact_bytes": bool(
            torch.equal(
                candidate.contiguous().view(torch.uint8),
                control.contiguous().view(torch.uint8),
            )
        ),
    }


def _token_comparison(candidate, control):
    if candidate.shape != control.shape or candidate.ndim == 0:
        return {
            "all_tokens_exact": False,
            "candidate_shape": list(candidate.shape),
            "control_shape": list(control.shape),
        }
    candidate_bytes = candidate.contiguous().view(candidate.shape[0], -1).view(
        torch.uint8
    )
    control_bytes = control.contiguous().view(control.shape[0], -1).view(torch.uint8)
    exact = torch.all(candidate_bytes == control_bytes, dim=1)
    mismatches = torch.nonzero(~exact, as_tuple=False).flatten()
    return {
        "token_count": candidate.shape[0],
        "exact_token_count": int(exact.sum().item()),
        "first_mismatch_token": (
            int(mismatches[0].item()) if mismatches.numel() else None
        ),
        "all_tokens_exact": bool(exact.all().item()),
    }


def install():
    global _INSTALLED, _RESERVED_RING_SLOTS
    if _INSTALLED:
        return
    from sglang.srt.layers.attention.triton_backend import TritonAttnBackend
    from sglang.srt.managers.scheduler_components.invariant_checker import (
        SchedulerInvariantChecker,
    )
    from sglang.srt.mem_cache.allocator.token import TokenToKVPoolAllocator
    from sglang.srt.mem_cache.swa_memory_pool import SWAKVPool

    original_init = TritonAttnBackend.__init__
    original_extend = TritonAttnBackend.forward_extend
    original_decode = TritonAttnBackend.forward_decode
    original_check_swa_pool = SchedulerInvariantChecker._check_swa_pool
    original_token_clear = TokenToKVPoolAllocator.clear

    def patched_init(self, model_runner, *args, **kwargs):
        original_init(self, model_runner, *args, **kwargs)
        pool = self.token_to_kv_pool
        if not isinstance(pool, SWAKVPool):
            raise RuntimeError("ring candidate requires the production hybrid SWA pool")
        ownership = RingOwnership(
            request_pool_size=model_runner.req_to_token_pool.size,
            tokens_per_row=RING_TOKENS,
        )
        allocator = self.token_to_kv_pool_allocator.swa_attn_allocator
        allocator._ring_reserved_slots = ownership.reserved_slots
        if pool.size_swa < ownership.reserved_slots + 1:
            raise RuntimeError(
                "ring capacity unavailable:"
                f"{pool.size_swa}<{ownership.reserved_slots + 1}"
            )
        allocator.free_pages = allocator.free_pages[
            allocator.free_pages > ownership.reserved_slots
        ]
        self._ring_ownership = ownership
        self._ring_slot_to_row = torch.tensor(
            ownership.slot_to_row,
            dtype=torch.int32,
            device=model_runner.device,
        )
        self._ring_first_sliding_layer = min(
            layer_id
            for layer_id, (_pool_layer, is_swa) in pool.layers_mapping.items()
            if is_swa
        )
        self._ring_extend_trace_slots = set()
        self._ring_decode_trace_counts = {}
        self._ring_audited_layers = set()
        _RESERVED_RING_SLOTS = ownership.reserved_slots
        _audit(
            {
                "event": "ring_region_reserved",
                "slots": ownership.reserved_slots,
                "slot_begin": 1,
                "slot_end": ownership.reserved_slots,
                "requests": ownership.row_count,
                "tokens_per_request": RING_TOKENS,
                "request_slot_zero_row": -1,
                "ownership": "persistent_bijection_request_pool_slot_to_ring_row",
                "dtype": str(pool.dtype),
                "global_pool_unchanged": True,
            }
        )

    def ring_views(backend, pool, layer_id):
        k_paged = pool.get_key_buffer(layer_id)
        v_paged = pool.get_value_buffer(layer_id)
        slots = backend._ring_ownership.reserved_slots
        rows = backend._ring_ownership.row_count
        return (
            k_paged,
            v_paged,
            k_paged[1 : slots + 1].view(
                rows, RING_TOKENS, k_paged.shape[1], k_paged.shape[2]
            ),
            v_paged[1 : slots + 1].view(
                rows, RING_TOKENS, v_paged.shape[1], v_paged.shape[2]
            ),
        )

    def request_rows(backend, forward_batch):
        return backend._ring_slot_to_row[forward_batch.req_pool_indices.long()]

    def layer_scale(layer, name):
        parameter = getattr(layer, f"{name}_scale", None)
        if parameter is None:
            return None
        scalar = getattr(layer, f"{name}_scale_float", None)
        if scalar is None:
            if parameter.numel() != 1:
                raise RuntimeError(f"ring candidate requires scalar {name}_scale")
            scalar = parameter.detach().cpu().item()
        scalar = float(scalar)
        if scalar <= 0:
            raise RuntimeError(f"ring candidate requires positive {name}_scale")
        return scalar

    def store_scales(layer, k, v, k_ring, v_ring):
        actual_k_scale = layer_scale(layer, "k")
        actual_v_scale = layer_scale(layer, "v")
        return (
            actual_k_scale
            if actual_k_scale is not None and k.dtype != k_ring.dtype
            else 1.0,
            actual_v_scale
            if actual_v_scale is not None and v.dtype != v_ring.dtype
            else 1.0,
        )

    def scale_audit(layer):
        return {
            "k_scale": layer_scale(layer, "k"),
            "v_scale": layer_scale(layer, "v"),
            "producer_semantics": "divide_by_scale_before_fp8_cast",
        }

    def trace_extend(
        backend,
        layer,
        forward_batch,
        k_paged,
        v_paged,
        k_ring,
        v_ring,
        request_ids,
        prefix_lens,
        positions,
        repeated_ids,
    ):
        if (
            os.environ.get("RING_CACHE_TRACE_TRANSITIONS") != "1"
            or layer.layer_id != backend._ring_first_sliding_layer
            or _capturing()
        ):
            return
        request_slots = tuple(_tensor_values(forward_batch.req_pool_indices))
        if request_slots in backend._ring_extend_trace_slots:
            return
        backend._ring_extend_trace_slots.add(request_slots)
        valid = repeated_ids >= 0
        ring_positions = positions & (RING_TOKENS - 1)
        swa_locs = backend.forward_metadata.swa_out_cache_loc[: positions.numel()]
        current_k = k_ring[repeated_ids[valid].long(), ring_positions[valid].long()]
        current_v = v_ring[repeated_ids[valid].long(), ring_positions[valid].long()]
        row = {
            "event": "ring_transition_extend",
            "layer_id": layer.layer_id,
            "producer_binding": "canonical_paged_e5m2_swa_out_cache_loc",
            "request_pool_indices": request_slots,
            "ring_rows": _tensor_values(request_ids),
            "prefix_lens": _tensor_values(prefix_lens),
            "extend_lens": _tensor_values(forward_batch.extend_seq_lens),
            "scales": scale_audit(layer),
            "absolute_positions": _tensor_values(positions),
            "current_k": _comparison(current_k, k_paged[swa_locs[valid]]),
            "current_v": _comparison(current_v, v_paged[swa_locs[valid]]),
            "current_k_tokens": _token_comparison(
                current_k, k_paged[swa_locs[valid]]
            ),
            "current_v_tokens": _token_comparison(
                current_v, v_paged[swa_locs[valid]]
            ),
        }
        indptr = backend.forward_metadata.window_kv_indptr
        prefix_counts = indptr[1:] - indptr[:-1]
        total_prefix = int(indptr[-1].item())
        if total_prefix:
            prefix_rows = torch.repeat_interleave(
                request_ids,
                prefix_counts,
                output_size=total_prefix,
            )
            starts = prefix_lens - prefix_counts
            prefix_positions = torch.cat(
                [
                    torch.arange(
                        int(start.item()),
                        int(prefix_len.item()),
                        dtype=torch.int64,
                        device=k_ring.device,
                    )
                    for start, prefix_len in zip(starts, prefix_lens)
                ]
            )
            prefix_valid = prefix_rows >= 0
            prefix_ring_positions = prefix_positions & (RING_TOKENS - 1)
            prefix_slots = backend.forward_metadata.window_kv_indices[:total_prefix]
            row["restored_prefix_tokens"] = total_prefix
            row["prefix_k"] = _comparison(
                k_ring[
                    prefix_rows[prefix_valid].long(),
                    prefix_ring_positions[prefix_valid].long(),
                ],
                k_paged[prefix_slots[prefix_valid]],
            )
            row["prefix_v"] = _comparison(
                v_ring[
                    prefix_rows[prefix_valid].long(),
                    prefix_ring_positions[prefix_valid].long(),
                ],
                v_paged[prefix_slots[prefix_valid]],
            )
        else:
            row["restored_prefix_tokens"] = 0
        _audit(row)

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
        if forward_batch.extend_seq_lens is None:
            return original_extend(
                self, q, k, v, layer, forward_batch, save_kv_cache, sinks
            )
        if not pool.layers_mapping[layer.layer_id][1] or not save_kv_cache:
            return original_extend(
                self, q, k, v, layer, forward_batch, save_kv_cache, sinks
            )
        result = original_extend(
            self, q, k, v, layer, forward_batch, save_kv_cache, sinks
        )
        k_paged, v_paged, k_ring, v_ring = ring_views(self, pool, layer.layer_id)
        request_ids = request_rows(self, forward_batch)
        prefix_lens = forward_batch.extend_prefix_lens
        lengths = forward_batch.extend_seq_lens
        if prefix_lens is None:
            prefix_lens = torch.zeros_like(lengths)
        else:
            scratch_last = torch.full(
                (self._ring_ownership.row_count,),
                -2**30,
                dtype=torch.int64,
                device=q.device,
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
        # The deferred production path has already committed the fused
        # RMSNorm+RoPE output to the canonical E5M2 SWA locations. Source the
        # ring from those exact bytes so its slice, layout, rotary convention,
        # and scale are identical to stock. Both sides are E5M2, hence scale 1.
        swa_locs = self.forward_metadata.swa_out_cache_loc[: k.shape[0]]
        produced_k = k_paged[swa_locs]
        produced_v = v_paged[swa_locs]
        store_ring_kv_bytes(
            produced_k,
            produced_v,
            k_ring,
            v_ring,
            repeated_ids,
            positions,
        )
        trace_extend(
            self,
            layer,
            forward_batch,
            k_paged,
            v_paged,
            k_ring,
            v_ring,
            request_ids,
            prefix_lens,
            positions,
            repeated_ids,
        )
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
        if q.shape[0] > self._ring_ownership.row_count:
            raise RuntimeError(
                "ring padded batch exceeds request-pool rows:"
                f"{q.shape[0]}>{self._ring_ownership.row_count}"
            )
        k_paged, v_paged, k_ring, v_ring = ring_views(self, pool, layer.layer_id)
        request_ids = request_rows(self, forward_batch)
        seq_lens = forward_batch.seq_lens
        absolute_positions = seq_lens - 1
        k_scale, v_scale = store_scales(layer, k, v, k_ring, v_ring)
        store_ring_kv(
            k,
            v,
            k_ring,
            v_ring,
            request_ids,
            absolute_positions,
            k_scale,
            v_scale,
        )

        trace_key = None
        trace_this_transition = False
        if (
            os.environ.get("RING_CACHE_TRACE_TRANSITIONS") == "1"
            and layer.layer_id == self._ring_first_sliding_layer
            and not _capturing()
        ):
            trace_key = tuple(_tensor_values(forward_batch.req_pool_indices))
            trace_this_transition = (
                self._ring_decode_trace_counts.get(trace_key, 0) < 2
            )
        stock_result = None
        if trace_this_transition:
            stock_result = original_decode(
                self, q, k.clone(), v.clone(), layer, forward_batch, True, sinks
            )

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
            context_lens = torch.where(request_ids >= 0, context_lens, 0)
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
        if trace_this_transition:
            self._ring_decode_trace_counts[trace_key] = (
                self._ring_decode_trace_counts.get(trace_key, 0) + 1
            )
            valid = request_ids >= 0
            ring_positions = absolute_positions & (RING_TOKENS - 1)
            swa_locs = self.forward_metadata.swa_out_cache_loc[: request_ids.numel()]
            context_lens = (
                self.forward_metadata.window_kv_indptr[1:]
                - self.forward_metadata.window_kv_indptr[:-1]
            )
            _audit(
                {
                    "event": "ring_transition_decode",
                    "transition_for_request": self._ring_decode_trace_counts[
                        trace_key
                    ],
                    "layer_id": layer.layer_id,
                    "request_pool_indices": _tensor_values(
                        forward_batch.req_pool_indices
                    ),
                    "ring_rows": _tensor_values(request_ids),
                    "valid_rows": _tensor_values(valid),
                    "seq_lens": _tensor_values(seq_lens),
                    "context_lens": _tensor_values(context_lens),
                    "absolute_positions": _tensor_values(absolute_positions),
                    "scales": scale_audit(layer),
                    "current_k": _comparison(
                        k_ring[
                            request_ids[valid].long(),
                            ring_positions[valid].long(),
                        ],
                        k_paged[swa_locs[valid]],
                    ),
                    "current_v": _comparison(
                        v_ring[
                            request_ids[valid].long(),
                            ring_positions[valid].long(),
                        ],
                        v_paged[swa_locs[valid]],
                    ),
                    "ring_vs_stock_output": _comparison(result, stock_result),
                }
            )
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
                    "scales": scale_audit(layer),
                }
            )
        return result

    TritonAttnBackend.__init__ = patched_init
    TritonAttnBackend.forward_extend = patched_extend
    TritonAttnBackend.forward_decode = patched_decode

    def patched_token_clear(self):
        original_token_clear(self)
        reserved = getattr(self, "_ring_reserved_slots", 0)
        if reserved:
            self.free_pages = self.free_pages[self.free_pages > reserved]

    TokenToKVPoolAllocator.clear = patched_token_clear

    def patched_check_swa_pool(self, ps, uncached=0):
        # The ring reservation is intentional capacity, not a leak. Preserve
        # every other term and the production checker itself.
        original_total = self.swa_tokens_per_layer
        scheduler_ring_slots = self.req_to_token_pool.size * RING_TOKENS
        self.swa_tokens_per_layer = original_total - scheduler_ring_slots
        try:
            return original_check_swa_pool(self, ps, uncached)
        finally:
            self.swa_tokens_per_layer = original_total

    SchedulerInvariantChecker._check_swa_pool = patched_check_swa_pool
    _INSTALLED = True
