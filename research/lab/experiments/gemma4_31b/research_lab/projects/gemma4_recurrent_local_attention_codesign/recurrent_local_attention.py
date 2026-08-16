"""Rolling positive-feature local attention for the pinned Gemma 4 geometry.

The insertion point is the pinned ``Gemma4Attention`` path after Q/K RMSNorm
and RoPE and after V RMSNorm.  Each request and local layer owns one state.
The state represents exactly the last 1,024 positions; an expiring token's
stored positive-key feature and full-width value are subtracted before the
current token is added.

This intentionally changes softmax attention semantics.  It preserves the
mechanical information path, model depth, heads, head width, parameters,
query rows, and causal horizon, but it makes no quality-equivalence claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

try:
    import torch
    import torch.nn.functional as torch_functional
except ImportError:
    torch = None
    torch_functional = None

try:
    import triton
    import triton.language as tl
except ImportError:
    triton = None
    tl = None


LOCAL_LAYERS = 50
TOTAL_LAYERS = 60
QUERY_HEADS = 32
KV_HEADS = 16
GQA_GROUP_SIZE = QUERY_HEADS // KV_HEADS
HEAD_DIM = 256
FEATURE_RANK = 64
WINDOW_TOKENS = 1024
MAX_QUERY_BLOCK = 32
TARGET_VERIFY_ROWS = 12
NORMALIZATION_EPSILON = 1.0e-6


@dataclass(frozen=True)
class WindowTransition:
    query_position: int
    added_positions: tuple[int, ...]
    evicted_positions: tuple[int, ...]
    represented_positions: tuple[int, ...]


def window_transitions(query_start: int, query_count: int) -> tuple[WindowTransition, ...]:
    if query_start < 0 or not 1 <= query_count <= MAX_QUERY_BLOCK:
        raise ValueError("invalid_local_query_block")
    rows = []
    for row in range(query_count):
        position = query_start + row
        window_start = max(0, position - WINDOW_TOKENS + 1)
        rows.append(
            WindowTransition(
                query_position=position,
                added_positions=tuple(range(query_start, position + 1)),
                evicted_positions=tuple(
                    range(max(0, query_start - WINDOW_TOKENS), window_start)
                ),
                represented_positions=tuple(range(window_start, position + 1)),
            )
        )
    return tuple(rows)


def _require_torch() -> None:
    if torch is None:
        raise RuntimeError("torch_unavailable")


def positive_q_features(q_post_rope: torch.Tensor, projection: torch.Tensor) -> torch.Tensor:
    """Map [T,32,256] queries to positive [T,16,2,64] GQA features."""

    _require_torch()
    if tuple(q_post_rope.shape[1:]) != (QUERY_HEADS, HEAD_DIM):
        raise ValueError("local_query_geometry_mismatch")
    if tuple(projection.shape) != (KV_HEADS, HEAD_DIM, FEATURE_RANK):
        raise ValueError("local_feature_projection_geometry_mismatch")
    grouped = q_post_rope.reshape(
        q_post_rope.shape[0], KV_HEADS, GQA_GROUP_SIZE, HEAD_DIM
    )
    projected = torch.einsum("thgd,hdr->thgr", grouped.float(), projection.float())
    return torch_functional.elu(projected) + 1.0


def positive_k_features(
    post_rope_k: torch.Tensor, projection: torch.Tensor
) -> torch.Tensor:
    """Map [T,16,256] post-RoPE keys to positive [T,16,64] features."""

    _require_torch()
    if tuple(post_rope_k.shape[1:]) != (KV_HEADS, HEAD_DIM):
        raise ValueError("local_key_geometry_mismatch")
    if tuple(projection.shape) != (KV_HEADS, HEAD_DIM, FEATURE_RANK):
        raise ValueError("local_feature_projection_geometry_mismatch")
    projected = torch.einsum("thd,hdr->thr", post_rope_k.float(), projection.float())
    return torch_functional.elu(projected) + 1.0


class RollingRecurrentLocalState:
    """Request-and-layer-owned numerator/denominator plus an exact eviction ring."""

    def __init__(
        self,
        *,
        request_id: str,
        layer_id: int,
        projection: torch.Tensor,
    ) -> None:
        _require_torch()
        if not 0 <= layer_id < TOTAL_LAYERS or layer_id % 6 == 5:
            raise ValueError("candidate_requires_sliding_attention_layer")
        if tuple(projection.shape) != (KV_HEADS, HEAD_DIM, FEATURE_RANK):
            raise ValueError("local_feature_projection_geometry_mismatch")
        self.request_id = request_id
        self.layer_id = layer_id
        self.projection = projection
        self.next_position = 0
        device = projection.device
        self.numerator = torch.zeros(
            (KV_HEADS, FEATURE_RANK, HEAD_DIM), dtype=torch.float32, device=device
        )
        self.denominator = torch.zeros(
            (KV_HEADS, FEATURE_RANK), dtype=torch.float32, device=device
        )
        self.ring_phi_k = torch.zeros(
            (WINDOW_TOKENS, KV_HEADS, FEATURE_RANK),
            dtype=projection.dtype,
            device=device,
        )
        self.ring_v = torch.zeros(
            (WINDOW_TOKENS, KV_HEADS, HEAD_DIM),
            dtype=projection.dtype,
            device=device,
        )

    def _validate_block(
        self, post_rope_k: torch.Tensor, v: torch.Tensor, position_start: int
    ) -> None:
        if position_start != self.next_position:
            raise RuntimeError("local_state_request_owner_or_position_mismatch")
        if post_rope_k.shape != v.shape or tuple(post_rope_k.shape[1:]) != (
            KV_HEADS,
            HEAD_DIM,
        ):
            raise ValueError("local_kv_geometry_mismatch")
        if not 1 <= post_rope_k.shape[0] <= MAX_QUERY_BLOCK:
            raise ValueError("invalid_local_state_block")

    def eviction_rows(self, position_start: int, count: int) -> tuple[torch.Tensor, torch.Tensor]:
        slots = torch.arange(
            position_start,
            position_start + count,
            dtype=torch.long,
            device=self.projection.device,
        )
        valid = slots >= WINDOW_TOKENS
        slots = slots.remainder(WINDOW_TOKENS)
        evicted_phi = self.ring_phi_k.index_select(0, slots).float()
        evicted_v = self.ring_v.index_select(0, slots).float()
        valid_shape = (count, 1, 1)
        return (
            evicted_phi * valid.reshape(valid_shape),
            evicted_v * valid.reshape(valid_shape),
        )

    def append_committed(
        self, post_rope_k: torch.Tensor, v: torch.Tensor, position_start: int
    ) -> None:
        """Vectorized producer/update/eviction for committed positions."""

        self._validate_block(post_rope_k, v, position_start)
        count = post_rope_k.shape[0]
        phi_k = positive_k_features(post_rope_k, self.projection)
        evicted_phi, evicted_v = self.eviction_rows(position_start, count)
        added_outer = torch.einsum("thr,thd->hrd", phi_k, v.float())
        evicted_outer = torch.einsum("thr,thd->hrd", evicted_phi, evicted_v)
        self.numerator.add_(added_outer - evicted_outer)
        self.denominator.add_(phi_k.sum(dim=0) - evicted_phi.sum(dim=0))
        slots = torch.arange(
            position_start,
            position_start + count,
            dtype=torch.long,
            device=self.projection.device,
        ).remainder(WINDOW_TOKENS)
        self.ring_phi_k.index_copy_(0, slots, phi_k.to(self.ring_phi_k.dtype))
        self.ring_v.index_copy_(0, slots, v.to(self.ring_v.dtype))
        self.next_position += count

    def consume_block(
        self,
        q_post_rope: torch.Tensor,
        post_rope_k: torch.Tensor,
        v: torch.Tensor,
        *,
        query_start: int,
    ) -> torch.Tensor:
        """Consume all causal rows in one recurrent pass without mutating state."""

        self._validate_block(post_rope_k, v, query_start)
        if q_post_rope.shape[0] != post_rope_k.shape[0]:
            raise ValueError("local_qkv_row_mismatch")
        phi_q = positive_q_features(q_post_rope, self.projection)
        phi_k = positive_k_features(post_rope_k, self.projection)
        evicted_phi, evicted_v = self.eviction_rows(
            query_start, post_rope_k.shape[0]
        )
        if q_post_rope.is_cuda and triton is not None:
            return _consume_recurrent_local_attention_triton(
                phi_q,
                phi_k,
                v,
                evicted_phi,
                evicted_v,
                self.numerator,
                self.denominator,
                q_post_rope.dtype,
            )
        added_outer = torch.einsum("thr,thd->thrd", phi_k, v.float())
        removed_outer = torch.einsum("thr,thd->thrd", evicted_phi, evicted_v)
        numerator_rows = self.numerator.unsqueeze(0) + torch.cumsum(
            added_outer - removed_outer, dim=0
        )
        denominator_rows = self.denominator.unsqueeze(0) + torch.cumsum(
            phi_k - evicted_phi, dim=0
        )
        numerator = torch.einsum("thgr,thrd->thgd", phi_q, numerator_rows)
        denominator = torch.einsum("thgr,thr->thg", phi_q, denominator_rows)
        output = numerator / denominator.clamp_min(NORMALIZATION_EPSILON).unsqueeze(-1)
        return output.to(q_post_rope.dtype).reshape(
            q_post_rope.shape[0], QUERY_HEADS, HEAD_DIM
        )


if triton is not None:

    @triton.jit
    def _recurrent_local_consumer_kernel(
        q_features,
        current_k_features,
        current_v,
        evicted_k_features,
        evicted_v,
        base_numerator,
        base_denominator,
        output,
        query_rows: tl.constexpr,
        BLOCK_R: tl.constexpr,
        BLOCK_D: tl.constexpr,
        normalization_epsilon: tl.constexpr,
    ):
        request = tl.program_id(0)
        kv_head = tl.program_id(1)
        dimension_tile = tl.program_id(2)
        ranks = tl.arange(0, BLOCK_R)
        dimensions = dimension_tile * BLOCK_D + tl.arange(0, BLOCK_D)
        state_offsets = (
            request * KV_HEADS * FEATURE_RANK * HEAD_DIM
            + kv_head * FEATURE_RANK * HEAD_DIM
            + ranks[:, None] * HEAD_DIM
            + dimensions[None, :]
        )
        denominator_offsets = (
            request * KV_HEADS * FEATURE_RANK
            + kv_head * FEATURE_RANK
            + ranks
        )
        state = tl.load(base_numerator + state_offsets)
        denominator_state = tl.load(base_denominator + denominator_offsets)
        for row in range(query_rows):
            feature_offset = (
                row * KV_HEADS * FEATURE_RANK
                + kv_head * FEATURE_RANK
                + ranks
            )
            value_offset = (
                row * KV_HEADS * HEAD_DIM
                + kv_head * HEAD_DIM
                + dimensions
            )
            added_feature = tl.load(current_k_features + feature_offset)
            removed_feature = tl.load(evicted_k_features + feature_offset)
            added_value = tl.load(current_v + value_offset)
            removed_value = tl.load(evicted_v + value_offset)
            state += (
                added_feature[:, None] * added_value[None, :]
                - removed_feature[:, None] * removed_value[None, :]
            )
            denominator_state += added_feature - removed_feature
            for group in range(GQA_GROUP_SIZE):
                query_offset = (
                    row * KV_HEADS * GQA_GROUP_SIZE * FEATURE_RANK
                    + kv_head * GQA_GROUP_SIZE * FEATURE_RANK
                    + group * FEATURE_RANK
                    + ranks
                )
                query = tl.load(q_features + query_offset)
                numerator = tl.sum(query[:, None] * state, axis=0)
                denominator = tl.sum(query * denominator_state, axis=0)
                output_offset = (
                    row * QUERY_HEADS * HEAD_DIM
                    + (kv_head * GQA_GROUP_SIZE + group) * HEAD_DIM
                    + dimensions
                )
                tl.store(
                    output + output_offset,
                    numerator / tl.maximum(denominator, normalization_epsilon),
                )


def _consume_recurrent_local_attention_triton(
    q_features: torch.Tensor,
    current_k_features: torch.Tensor,
    current_v: torch.Tensor,
    evicted_k_features: torch.Tensor,
    evicted_v: torch.Tensor,
    base_numerator: torch.Tensor,
    base_denominator: torch.Tensor,
    output_dtype: torch.dtype,
) -> torch.Tensor:
    if triton is None or not q_features.is_cuda:
        raise RuntimeError("triton_local_consumer_unavailable")
    query_rows = q_features.shape[0]
    output = torch.empty(
        (query_rows, QUERY_HEADS, HEAD_DIM),
        dtype=output_dtype,
        device=q_features.device,
    )
    _recurrent_local_consumer_kernel[(1, KV_HEADS, HEAD_DIM // 64)](
        q_features,
        current_k_features,
        current_v,
        evicted_k_features,
        evicted_v,
        base_numerator,
        base_denominator,
        output,
        query_rows=query_rows,
        BLOCK_R=FEATURE_RANK,
        BLOCK_D=64,
        normalization_epsilon=NORMALIZATION_EPSILON,
        num_warps=8,
        num_stages=1,
    )
    return output


def consume_recurrent_local_attention(
    *,
    layer_sliding_window: int | None,
    forward_mode: str,
    q_post_rope: torch.Tensor,
    post_rope_k: torch.Tensor,
    v: torch.Tensor,
    query_start: int,
    state: RollingRecurrentLocalState,
    commit: bool,
    active_query_rows: int | None = None,
) -> torch.Tensor:
    """Pinned backend replacement for prefill, TARGET_VERIFY, and decode."""

    if layer_sliding_window != WINDOW_TOKENS:
        raise RuntimeError("candidate_requires_exact_1024_local_window")
    if forward_mode not in {"EXTEND", "TARGET_VERIFY", "DECODE"}:
        raise RuntimeError("unsupported_local_attention_phase")
    active = q_post_rope.shape[0] if active_query_rows is None else active_query_rows
    if not 1 <= active <= q_post_rope.shape[0] <= MAX_QUERY_BLOCK:
        raise RuntimeError("invalid_graph_active_query_rows")
    active_output = state.consume_block(
        q_post_rope[:active],
        post_rope_k[:active],
        v[:active],
        query_start=query_start,
    )
    if commit:
        state.append_committed(post_rope_k[:active], v[:active], query_start)
    if active == q_post_rope.shape[0]:
        return active_output
    output = torch.zeros_like(q_post_rope)
    output[:active] = active_output
    return output


def forward_with_stock_fallback(
    *,
    stock_consumer,
    layer_sliding_window: int | None,
    forward_mode: str,
    q_post_rope: torch.Tensor,
    post_rope_k: torch.Tensor,
    v: torch.Tensor,
    query_start: int,
    state: RollingRecurrentLocalState,
    commit: bool,
    active_query_rows: int | None = None,
) -> torch.Tensor:
    """Fail to the unchanged pinned consumer before any candidate mutation."""

    try:
        if query_start != state.next_position:
            raise RuntimeError("local_state_request_owner_or_position_mismatch")
        if layer_sliding_window != WINDOW_TOKENS:
            raise RuntimeError("candidate_requires_exact_1024_local_window")
        if q_post_rope.shape[0] > MAX_QUERY_BLOCK:
            raise RuntimeError("candidate_graph_variant_unavailable")
        return consume_recurrent_local_attention(
            layer_sliding_window=layer_sliding_window,
            forward_mode=forward_mode,
            q_post_rope=q_post_rope,
            post_rope_k=post_rope_k,
            v=v,
            query_start=query_start,
            state=state,
            commit=commit,
            active_query_rows=active_query_rows,
        )
    except (RuntimeError, ValueError) as candidate_error:
        return stock_consumer(
            q_post_rope,
            post_rope_k,
            v,
            query_start=query_start,
            candidate_error=str(candidate_error),
        )


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def deterministic_information_fixture() -> dict[str, object]:
    """Pure-Python recurrence/direct-window comparison across eviction."""

    window = 8
    rank = 4
    width = 3
    numerator = [[0.0] * width for _ in range(rank)]
    denominator = [0.0] * rank
    ring: dict[int, tuple[list[float], list[float]]] = {}

    def token(position: int) -> tuple[list[float], list[float]]:
        feature = [1.0 + ((position + axis) % 5) / 5.0 for axis in range(rank)]
        value = [
            (position + 1) * (axis + 1) / 17.0 + (position % 3) / 11.0
            for axis in range(width)
        ]
        return feature, value

    def update(feature: list[float], value: list[float], sign: float) -> None:
        for feature_axis in range(rank):
            denominator[feature_axis] += sign * feature[feature_axis]
            for value_axis in range(width):
                numerator[feature_axis][value_axis] += (
                    sign * feature[feature_axis] * value[value_axis]
                )

    for position in range(8):
        feature, value = token(position)
        update(feature, value, 1.0)
        ring[position] = (feature, value)

    rows = []
    maximum_error = 0.0
    for position in range(8, 12):
        expired = position - window
        expired_feature, expired_value = ring.pop(expired)
        update(expired_feature, expired_value, -1.0)
        feature, value = token(position)
        update(feature, value, 1.0)
        ring[position] = (feature, value)
        query = [1.0 + (position + axis) / 23.0 for axis in range(rank)]
        recurrent_numerator = [
            _dot(query, [numerator[r][d] for r in range(rank)])
            for d in range(width)
        ]
        recurrent_denominator = _dot(query, denominator)
        recurrent = [value / recurrent_denominator for value in recurrent_numerator]
        direct_positions = tuple(range(position - window + 1, position + 1))
        direct_weights = {
            source: _dot(query, token(source)[0]) for source in direct_positions
        }
        direct_denominator = sum(direct_weights.values())
        direct = [
            sum(direct_weights[source] * token(source)[1][axis] for source in direct_positions)
            / direct_denominator
            for axis in range(width)
        ]
        error = max(abs(a - b) for a, b in zip(recurrent, direct))
        maximum_error = max(maximum_error, error)
        rows.append(
            {
                "query_position": position,
                "represented_positions": list(sorted(ring)),
                "direct_positions": list(direct_positions),
                "every_in_window_token_once": tuple(sorted(ring)) == direct_positions,
                "expired_positions_absent": not any(p < direct_positions[0] for p in ring),
                "maximum_absolute_error": error,
            }
        )
    finite = all(
        value == value and abs(value) != float("inf")
        for row in numerator
        for value in row
    )
    return {
        "consumer_executed": True,
        "fixture_backend": "pure_python_fp64",
        "window_tokens": window,
        "feature_rank": rank,
        "head_width": width,
        "rows": rows,
        "every_in_window_token_once": all(
            row["every_in_window_token_once"] for row in rows
        ),
        "expired_tokens_contribute_zero": all(
            row["expired_positions_absent"] for row in rows
        ),
        "protected_or_current_double_count": False,
        "output_shape": [4, width],
        "finite": finite,
        "maximum_absolute_error": maximum_error,
        "direct_recurrent_match": maximum_error < 1.0e-12,
    }
