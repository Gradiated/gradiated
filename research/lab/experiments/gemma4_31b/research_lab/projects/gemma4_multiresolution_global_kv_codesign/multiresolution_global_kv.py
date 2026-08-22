"""Source-complete two-tier global KV path for the pinned Gemma 4 geometry.

The production entry points are ``forward_extend`` (ordinary prefill and
TARGET_VERIFY) and ``forward_decode``.  Sliding-attention layers are rejected
by construction so the stock 1,024-token local consumer remains untouched.

Keys enter this module after Gemma 4's Q/K RMSNorm and RoPE.  Summaries
therefore average already-positioned keys; they are never rotated a second
time.  Values enter after V RMSNorm.  A summary contributes ``log(count)`` to
its attention logit so its represented-token count reaches the real softmax
consumer rather than surviving only as metadata.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable, Sequence

try:
    import torch
except ImportError:
    torch = None

try:
    import triton
    import triton.language as tl
except ImportError:
    triton = None
    tl = None


SUMMARY_BLOCK_TOKENS = 512
RECENT_EXACT_TOKENS = 8
MAX_PROTECTED_TOKENS = 8
QUERY_BLOCK_TOKENS = 32
COMPACT_TILE_TOKENS = 64
GLOBAL_KV_HEADS = 4
GLOBAL_HEAD_DIM = 512
CLAIMED_PHASES = frozenset({"prefill", "target_verify", "decode"})


class EntryKind(IntEnum):
    SUMMARY = 0
    EXACT = 1


@dataclass(frozen=True)
class CompactEntry:
    kind: EntryKind
    positions: tuple[int, ...]
    causal_end: int

    @property
    def count(self) -> int:
        return len(self.positions)


@dataclass(frozen=True)
class CompactBlockPlan:
    query_start: int
    query_count: int
    entries: tuple[CompactEntry, ...]
    protected_positions: tuple[int, ...]

    @property
    def query_end(self) -> int:
        return self.query_start + self.query_count

    @property
    def compact_tokens(self) -> int:
        return len(self.entries)

    @property
    def represented_positions(self) -> tuple[int, ...]:
        represented: list[int] = []
        for entry in self.entries:
            represented.extend(entry.positions)
        return tuple(represented)


class IncrementalGlobalSummaryState:
    """Request-and-layer-owned FP32 summaries updated once per committed token."""

    def __init__(self, protected_positions: Sequence[int] = ()) -> None:
        self.protected_positions = _deduplicated_protected(
            protected_positions, 2**31 - 1
        )
        self._protected = set(self.protected_positions)
        self.committed_tokens = 0
        self.full_k: list[torch.Tensor] = []
        self.full_v: list[torch.Tensor] = []
        self.full_counts: list[int] = []
        self.partial_k: torch.Tensor | None = None
        self.partial_v: torch.Tensor | None = None
        self.partial_count = 0

    def _zero_accumulators(self, exemplar: torch.Tensor) -> None:
        shape = (GLOBAL_KV_HEADS, GLOBAL_HEAD_DIM)
        self.partial_k = torch.zeros(shape, dtype=torch.float32, device=exemplar.device)
        self.partial_v = torch.zeros_like(self.partial_k)
        self.partial_count = 0

    def append_committed(
        self, post_rope_k: torch.Tensor, v: torch.Tensor
    ) -> None:
        """Fuseable KV-write epilogue; each accepted token is appended once."""

        if post_rope_k.shape != v.shape or post_rope_k.shape[1:] != (
            GLOBAL_KV_HEADS,
            GLOBAL_HEAD_DIM,
        ):
            raise ValueError("global_kv_geometry_mismatch")
        if self.partial_k is None:
            self._zero_accumulators(post_rope_k)
        for offset in range(post_rope_k.shape[0]):
            position = self.committed_tokens
            if position not in self._protected:
                self.partial_k.add_(post_rope_k[offset].float())
                self.partial_v.add_(v[offset].float())
                self.partial_count += 1
            self.committed_tokens += 1
            if self.committed_tokens % SUMMARY_BLOCK_TOKENS == 0:
                if self.partial_count:
                    self.full_k.append(self.partial_k / self.partial_count)
                    self.full_v.append(self.partial_v / self.partial_count)
                    self.full_counts.append(self.partial_count)
                self._zero_accumulators(post_rope_k)

    def materialize(
        self,
        exact_k: torch.Tensor,
        exact_v: torch.Tensor,
        query_start: int,
        query_count: int,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Read cached summaries plus exact protected/recent/current positions."""

        if query_start != self.committed_tokens:
            raise RuntimeError("summary_request_ownership_or_position_mismatch")
        query_end = query_start + query_count
        if exact_k.shape[0] < query_end or exact_k.shape != exact_v.shape:
            raise ValueError("exact_global_kv_sequence_mismatch")
        old_end = max(0, query_start - RECENT_EXACT_TOKENS)
        complete_blocks = old_end // SUMMARY_BLOCK_TOKENS
        compact_k = list(self.full_k[:complete_blocks])
        compact_v = list(self.full_v[:complete_blocks])
        counts = list(self.full_counts[:complete_blocks])
        causal_ends = [
            min((index + 1) * SUMMARY_BLOCK_TOKENS, old_end) - 1
            for index in range(complete_blocks)
        ]

        partial_start = complete_blocks * SUMMARY_BLOCK_TOKENS
        if partial_start < old_end:
            block_index = complete_blocks
            if block_index < len(self.full_k):
                block_end = (block_index + 1) * SUMMARY_BLOCK_TOKENS
                partial_k_sum = self.full_k[block_index] * self.full_counts[block_index]
                partial_v_sum = self.full_v[block_index] * self.full_counts[block_index]
                partial_count = self.full_counts[block_index]
                subtract_end = block_end
            else:
                partial_k_sum = self.partial_k.clone()
                partial_v_sum = self.partial_v.clone()
                partial_count = self.partial_count
                subtract_end = query_start
            subtract_positions = [
                position
                for position in range(old_end, subtract_end)
                if position not in self._protected
            ]
            if subtract_positions:
                subtract_index = torch.tensor(
                    subtract_positions, device=exact_k.device, dtype=torch.long
                )
                partial_k_sum.sub_(
                    exact_k.index_select(0, subtract_index).float().sum(dim=0)
                )
                partial_v_sum.sub_(
                    exact_v.index_select(0, subtract_index).float().sum(dim=0)
                )
                partial_count -= len(subtract_positions)
            if partial_count:
                compact_k.append(partial_k_sum / partial_count)
                compact_v.append(partial_v_sum / partial_count)
                counts.append(partial_count)
                causal_ends.append(old_end - 1)

        exact_positions = sorted(
            {
                position
                for position in self.protected_positions
                if position < query_end
            }.union(range(old_end, query_end))
        )
        exact_index = torch.tensor(
            exact_positions, device=exact_k.device, dtype=torch.long
        )
        compact_k.extend(exact_k.index_select(0, exact_index).float().unbind(0))
        compact_v.extend(exact_v.index_select(0, exact_index).float().unbind(0))
        counts.extend([1] * len(exact_positions))
        causal_ends.extend(exact_positions)
        if len(counts) > COMPACT_TILE_TOKENS:
            raise RuntimeError("compact_tile_overflow")
        return (
            torch.stack(compact_k).to(exact_k.dtype),
            torch.stack(compact_v).to(exact_v.dtype),
            torch.tensor(counts, device=exact_k.device, dtype=torch.int32),
            torch.tensor(causal_ends, device=exact_k.device, dtype=torch.int32),
        )


def _deduplicated_protected(
    protected_positions: Iterable[int], query_end: int
) -> tuple[int, ...]:
    protected = tuple(
        sorted({int(position) for position in protected_positions if 0 <= position < query_end})
    )
    if len(protected) > MAX_PROTECTED_TOKENS:
        raise RuntimeError("protected_position_overflow")
    return protected


def build_compact_block_plan(
    query_start: int,
    query_count: int,
    *,
    protected_positions: Sequence[int] = (),
) -> CompactBlockPlan:
    """Build one causal shared-K plan for at most 32 consecutive query rows.

    Old non-protected positions are partitioned into nonempty summaries.
    Protected positions, the recent tier, and the current query block remain
    exact.  Sharing the plan across a query block preserves matrix-multiply
    reuse; per-row causality is enforced from each entry's ``causal_end``.
    """

    if query_start < 0 or not 1 <= query_count <= QUERY_BLOCK_TOKENS:
        raise ValueError("invalid_query_block")
    query_end = query_start + query_count
    protected = _deduplicated_protected(protected_positions, query_end)
    protected_set = set(protected)
    old_end = max(0, query_start - RECENT_EXACT_TOKENS)

    entries: list[CompactEntry] = []
    for summary_start in range(0, old_end, SUMMARY_BLOCK_TOKENS):
        summary_end = min(old_end, summary_start + SUMMARY_BLOCK_TOKENS)
        contributors = tuple(
            position
            for position in range(summary_start, summary_end)
            if position not in protected_set
        )
        if contributors:
            entries.append(
                CompactEntry(
                    kind=EntryKind.SUMMARY,
                    positions=contributors,
                    causal_end=contributors[-1],
                )
            )

    exact_positions = set(protected)
    exact_positions.update(range(old_end, query_end))
    entries.extend(
        CompactEntry(kind=EntryKind.EXACT, positions=(position,), causal_end=position)
        for position in sorted(exact_positions)
    )
    if len(entries) > COMPACT_TILE_TOKENS:
        raise RuntimeError("compact_tile_overflow")

    plan = CompactBlockPlan(
        query_start=query_start,
        query_count=query_count,
        entries=tuple(entries),
        protected_positions=protected,
    )
    represented = plan.represented_positions
    if len(represented) != len(set(represented)):
        raise RuntimeError("duplicate_token_contribution")
    if set(represented) != set(range(query_end)):
        raise RuntimeError("missing_token_contribution")
    return plan


def materialize_compact_post_rope_kv(
    exact_k: torch.Tensor,
    exact_v: torch.Tensor,
    plan: CompactBlockPlan,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Materialize the tile consumed by global attention.

    ``exact_k`` and ``exact_v`` are ``[sequence, 4, 512]`` tensors.  Summary
    accumulation is FP32 and the compact tile is returned in the producer
    dtype.  The fourth result is the causal end position used by every claimed
    phase, including speculative target verification.
    """

    expected_tail = (GLOBAL_KV_HEADS, GLOBAL_HEAD_DIM)
    if exact_k.shape != exact_v.shape or tuple(exact_k.shape[1:]) != expected_tail:
        raise ValueError("global_kv_geometry_mismatch")
    if exact_k.shape[0] < plan.query_end:
        raise ValueError("global_kv_sequence_too_short")

    compact_k: list[torch.Tensor] = []
    compact_v: list[torch.Tensor] = []
    counts: list[int] = []
    causal_ends: list[int] = []
    for entry in plan.entries:
        positions = torch.tensor(entry.positions, device=exact_k.device, dtype=torch.long)
        selected_k = exact_k.index_select(0, positions)
        selected_v = exact_v.index_select(0, positions)
        if entry.kind == EntryKind.SUMMARY:
            compact_k.append(selected_k.float().mean(dim=0).to(exact_k.dtype))
            compact_v.append(selected_v.float().mean(dim=0).to(exact_v.dtype))
        else:
            compact_k.append(selected_k[0])
            compact_v.append(selected_v[0])
        counts.append(entry.count)
        causal_ends.append(entry.causal_end)
    return (
        torch.stack(compact_k),
        torch.stack(compact_v),
        torch.tensor(counts, device=exact_k.device, dtype=torch.int32),
        torch.tensor(causal_ends, device=exact_k.device, dtype=torch.int32),
    )


def consume_compact_global_attention(
    q: torch.Tensor,
    query_positions: torch.Tensor,
    compact_k: torch.Tensor,
    compact_v: torch.Tensor,
    counts: torch.Tensor,
    causal_ends: torch.Tensor,
    *,
    scale: float | None = None,
) -> torch.Tensor:
    """First decision-bearing consumer used by prefill, verify, and decode.

    This executable Torch form is the numerical oracle for the fused
    production kernel.  It performs grouped-query attention without repeating
    K/V, applies summary multiplicity inside the real logits, masks summaries
    and exact entries causally, and consumes the complete compact V tile.
    """

    if q.ndim != 3 or q.shape[1:] != (32, GLOBAL_HEAD_DIM):
        raise ValueError("global_query_geometry_mismatch")
    if compact_k.shape != compact_v.shape or compact_k.shape[1:] != (
        GLOBAL_KV_HEADS,
        GLOBAL_HEAD_DIM,
    ):
        raise ValueError("compact_global_kv_geometry_mismatch")
    if compact_k.shape[0] > COMPACT_TILE_TOKENS:
        raise ValueError("compact_tile_overflow")
    if query_positions.shape != (q.shape[0],):
        raise ValueError("query_position_shape_mismatch")

    if q.is_cuda and triton is not None:
        return _consume_compact_global_attention_triton(
            q, query_positions, compact_k, compact_v, counts, causal_ends
        )

    q_grouped = q.view(q.shape[0], GLOBAL_KV_HEADS, 8, GLOBAL_HEAD_DIM)
    logits = torch.einsum("qhgd,khd->qhgk", q_grouped.float(), compact_k.float())
    logits.mul_(scale if scale is not None else GLOBAL_HEAD_DIM**-0.5)
    logits.add_(counts.float().log().view(1, 1, 1, -1))
    causal = causal_ends.view(1, 1, 1, -1) <= query_positions.view(-1, 1, 1, 1)
    logits.masked_fill_(~causal, float("-inf"))
    probabilities = torch.softmax(logits, dim=-1)
    output = torch.einsum("qhgk,khd->qhgd", probabilities, compact_v.float())
    return output.to(q.dtype).reshape(q.shape[0], 32, GLOBAL_HEAD_DIM)


if triton is not None:

    @triton.jit
    def _compact_global_attention_kernel(
        q_ptr,
        k_ptr,
        v_ptr,
        counts_ptr,
        causal_ends_ptr,
        query_positions_ptr,
        output_ptr,
        query_count,
        compact_count,
        scale: tl.constexpr,
        BLOCK_M: tl.constexpr,
        BLOCK_N: tl.constexpr,
        BLOCK_D: tl.constexpr,
    ):
        query_head = tl.program_id(0)
        kv_head = query_head // 8
        rows = tl.arange(0, BLOCK_M)
        dimensions = tl.arange(0, BLOCK_D)
        keys = tl.arange(0, BLOCK_N)
        row_mask = rows < query_count
        key_mask = keys < compact_count

        q_offsets = (
            rows[:, None] * 32 * BLOCK_D
            + query_head * BLOCK_D
            + dimensions[None, :]
        )
        q_block = tl.load(
            q_ptr + q_offsets,
            mask=row_mask[:, None],
            other=0.0,
        )
        k_offsets = (
            keys[None, :] * 4 * BLOCK_D
            + kv_head * BLOCK_D
            + dimensions[:, None]
        )
        k_block = tl.load(
            k_ptr + k_offsets,
            mask=key_mask[None, :],
            other=0.0,
        )
        logits = tl.dot(q_block, k_block) * scale
        counts = tl.load(counts_ptr + keys, mask=key_mask, other=1).to(tl.float32)
        logits += tl.log(counts)[None, :]
        query_positions = tl.load(
            query_positions_ptr + rows, mask=row_mask, other=-1
        )
        causal_ends = tl.load(
            causal_ends_ptr + keys, mask=key_mask, other=2**31 - 1
        )
        valid = (
            row_mask[:, None]
            & key_mask[None, :]
            & (causal_ends[None, :] <= query_positions[:, None])
        )
        logits = tl.where(valid, logits, float("-inf"))
        maximum = tl.max(logits, axis=1)
        probabilities = tl.exp(logits - maximum[:, None])
        probabilities /= tl.sum(probabilities, axis=1)[:, None]

        v_offsets = (
            keys[:, None] * 4 * BLOCK_D
            + kv_head * BLOCK_D
            + dimensions[None, :]
        )
        v_block = tl.load(
            v_ptr + v_offsets,
            mask=key_mask[:, None],
            other=0.0,
        )
        output = tl.dot(probabilities.to(v_block.dtype), v_block)
        output_offsets = (
            rows[:, None] * 32 * BLOCK_D
            + query_head * BLOCK_D
            + dimensions[None, :]
        )
        tl.store(
            output_ptr + output_offsets,
            output,
            mask=row_mask[:, None],
        )


def _consume_compact_global_attention_triton(
    q: torch.Tensor,
    query_positions: torch.Tensor,
    compact_k: torch.Tensor,
    compact_v: torch.Tensor,
    counts: torch.Tensor,
    causal_ends: torch.Tensor,
) -> torch.Tensor:
    """One-CTA-per-query-head production consumer for the locked tile."""

    if triton is None:
        raise RuntimeError("triton_unavailable")
    if not all(
        tensor.is_cuda
        for tensor in (q, query_positions, compact_k, compact_v, counts, causal_ends)
    ):
        raise RuntimeError("mixed_device_compact_attention")
    output = torch.empty_like(q)
    _compact_global_attention_kernel[(32,)](
        q,
        compact_k,
        compact_v,
        counts,
        causal_ends,
        query_positions,
        output,
        q.shape[0],
        compact_k.shape[0],
        GLOBAL_HEAD_DIM**-0.5,
        BLOCK_M=QUERY_BLOCK_TOKENS,
        BLOCK_N=COMPACT_TILE_TOKENS,
        BLOCK_D=GLOBAL_HEAD_DIM,
        num_warps=8,
        num_stages=1,
    )
    return output


def multiresolution_global_attention(
    phase: str,
    q: torch.Tensor,
    exact_post_rope_k: torch.Tensor,
    exact_v: torch.Tensor,
    query_start: int,
    *,
    summary_state: IncrementalGlobalSummaryState,
    protected_positions: Sequence[int] = (),
    commit_after_consume: bool,
) -> torch.Tensor:
    """Production-shape route from post-RoPE KV writes to attention output."""

    if phase not in CLAIMED_PHASES:
        raise RuntimeError("unsupported_global_attention_phase")
    plan = build_compact_block_plan(
        query_start,
        q.shape[0],
        protected_positions=protected_positions,
    )
    if tuple(protected_positions) != summary_state.protected_positions:
        raise RuntimeError("protected_position_identity_mismatch")
    compact_k, compact_v, counts, causal_ends = summary_state.materialize(
        exact_post_rope_k, exact_v, query_start, q.shape[0]
    )
    query_positions = torch.arange(
        query_start,
        query_start + q.shape[0],
        device=q.device,
        dtype=torch.int32,
    )
    output = consume_compact_global_attention(
        q, query_positions, compact_k, compact_v, counts, causal_ends
    )
    if commit_after_consume:
        summary_state.append_committed(
            exact_post_rope_k[query_start : query_start + q.shape[0]],
            exact_v[query_start : query_start + q.shape[0]],
        )
    return output


def forward_extend(
    *,
    layer_sliding_window: int | None,
    forward_mode: str,
    q: torch.Tensor,
    post_rope_k: torch.Tensor,
    v: torch.Tensor,
    query_start: int,
    summary_state: IncrementalGlobalSummaryState,
    protected_positions: Sequence[int] = (),
) -> torch.Tensor:
    """SGLang backend insertion for ordinary prefill and TARGET_VERIFY."""

    if layer_sliding_window is not None:
        raise RuntimeError("local_attention_must_use_stock_consumer")
    phase = "target_verify" if forward_mode == "TARGET_VERIFY" else "prefill"
    return multiresolution_global_attention(
        phase,
        q,
        post_rope_k,
        v,
        query_start,
        summary_state=summary_state,
        protected_positions=protected_positions,
        commit_after_consume=phase == "prefill",
    )


def forward_decode(
    *,
    layer_sliding_window: int | None,
    q: torch.Tensor,
    post_rope_k: torch.Tensor,
    v: torch.Tensor,
    query_start: int,
    summary_state: IncrementalGlobalSummaryState,
    protected_positions: Sequence[int] = (),
) -> torch.Tensor:
    """SGLang backend insertion for ordinary one-token decode."""

    if layer_sliding_window is not None:
        raise RuntimeError("local_attention_must_use_stock_consumer")
    return multiresolution_global_attention(
        "decode",
        q,
        post_rope_k,
        v,
        query_start,
        summary_state=summary_state,
        protected_positions=protected_positions,
        commit_after_consume=True,
    )


def fixture() -> dict[str, object]:
    """Small deterministic end-to-end oracle with every token consumed."""

    if torch is None:
        plan = build_compact_block_plan(
            1_056, 1, protected_positions=(0, 17, 511, 700)
        )
        return {
            "finite": None,
            "output_shape": None,
            "compact_tokens": plan.compact_tokens,
            "all_positions_once": (
                len(plan.represented_positions) == 1_057
                and set(plan.represented_positions) == set(range(1_057))
            ),
            "summary_entries": sum(
                entry.kind == EntryKind.SUMMARY for entry in plan.entries
            ),
            "exact_entries": sum(
                entry.kind == EntryKind.EXACT for entry in plan.entries
            ),
            "multiplicity_sum": sum(entry.count for entry in plan.entries),
            "consumer_execution": "unavailable_without_torch_on_coordinator",
        }
    torch.manual_seed(7)
    sequence = 1_057
    query_start = 1_056
    k = torch.randn(sequence + 1, GLOBAL_KV_HEADS, GLOBAL_HEAD_DIM)
    v = torch.randn_like(k)
    q = torch.randn(1, 32, GLOBAL_HEAD_DIM)
    plan = build_compact_block_plan(
        query_start, 1, protected_positions=(0, 17, 511, 700)
    )
    compact = materialize_compact_post_rope_kv(k, v, plan)
    output = consume_compact_global_attention(
        q,
        torch.tensor([query_start], dtype=torch.int32),
        *compact,
    )
    return {
        "finite": bool(torch.isfinite(output).all()),
        "output_shape": list(output.shape),
        "compact_tokens": plan.compact_tokens,
        "all_positions_once": (
            len(plan.represented_positions) == query_start + 1
            and set(plan.represented_positions) == set(range(query_start + 1))
        ),
        "summary_entries": sum(entry.kind == EntryKind.SUMMARY for entry in plan.entries),
        "exact_entries": sum(entry.kind == EntryKind.EXACT for entry in plan.entries),
        "multiplicity_sum": sum(entry.count for entry in plan.entries),
    }
