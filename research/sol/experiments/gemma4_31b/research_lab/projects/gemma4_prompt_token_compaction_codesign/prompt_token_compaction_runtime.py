from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Sequence

try:
    import torch
except ModuleNotFoundError:
    torch = None


COMPACTION_AFTER_LAYER = 5
PROMPT_TOKENS = 4214
OUTPUT_STATES = 1152
PROTECTED_SHARED_PREFIX_TOKENS = 535
PROTECTED_RECENT_TOKENS = 384
MAX_SUMMARY_STATES = (
    OUTPUT_STATES - PROTECTED_SHARED_PREFIX_TOKENS - PROTECTED_RECENT_TOKENS
)
MIN_SUMMARY_STATES = 64
MAX_ADDITIONAL_PROTECTED_TOKENS = MAX_SUMMARY_STATES - MIN_SUMMARY_STATES


class CompactionFallback(RuntimeError):
    pass


@dataclass(frozen=True)
class MergeGroup:
    source_indices: tuple[int, ...]
    output_position: int
    protected_singleton: bool


@dataclass(frozen=True)
class RequestMergePlan:
    groups: tuple[MergeGroup, ...]
    input_length: int

    @property
    def output_length(self) -> int:
        return len(self.groups)

    def assert_contribution_invariant(self) -> None:
        contributors = [
            source_index
            for group in self.groups
            for source_index in group.source_indices
        ]
        if sorted(contributors) != list(range(self.input_length)):
            raise RuntimeError("every_input_token_must_contribute_exactly_once")
        if any(not group.source_indices for group in self.groups):
            raise RuntimeError("empty_summary_group")
        if any(
            left.output_position >= right.output_position
            for left, right in zip(self.groups, self.groups[1:])
        ):
            raise RuntimeError("merged_state_order_is_not_strictly_causal")


@dataclass(frozen=True)
class BatchMergePlan:
    requests: tuple[RequestMergePlan, ...]

    @property
    def output_lengths(self) -> tuple[int, ...]:
        return tuple(request.output_length for request in self.requests)

    @property
    def input_lengths(self) -> tuple[int, ...]:
        return tuple(request.input_length for request in self.requests)

    @property
    def total_output_states(self) -> int:
        return sum(self.output_lengths)

    def representative_flat_indices(self) -> list[int]:
        representatives: list[int] = []
        offset = 0
        for request in self.requests:
            representatives.extend(
                offset + group.output_position for group in request.groups
            )
            offset += request.input_length
        return representatives


def _partition_contiguous(indices: list[int], count: int) -> list[list[int]]:
    if count <= 0 or count > len(indices):
        raise CompactionFallback("invalid_summary_partition_geometry")
    return [
        indices[(group * len(indices)) // count : ((group + 1) * len(indices)) // count]
        for group in range(count)
    ]


def build_request_merge_plan(
    input_ids: Sequence[int],
    *,
    special_token_ids: Sequence[int] = (),
    tool_mask: Sequence[bool] | None = None,
) -> RequestMergePlan:
    length = len(input_ids)
    if length != PROMPT_TOKENS:
        raise CompactionFallback("route_requires_full_4214_token_prompt")
    if tool_mask is not None and len(tool_mask) != length:
        raise ValueError("tool_mask_geometry_mismatch")
    special = frozenset(int(value) for value in special_token_ids)
    protected = set(range(PROTECTED_SHARED_PREFIX_TOKENS))
    protected.update(range(length - PROTECTED_RECENT_TOKENS, length))
    protected.update(
        index
        for index, token_id in enumerate(input_ids)
        if int(token_id) in special
    )
    if tool_mask is not None:
        protected.update(
            index for index, value in enumerate(tool_mask) if bool(value)
        )
    additional = (
        len(protected)
        - PROTECTED_SHARED_PREFIX_TOKENS
        - PROTECTED_RECENT_TOKENS
    )
    if additional > MAX_ADDITIONAL_PROTECTED_TOKENS:
        raise CompactionFallback("protected_state_budget_leaves_fewer_than_64_summaries")
    summary_count = OUTPUT_STATES - len(protected)
    mergeable = [index for index in range(length) if index not in protected]
    summary_groups = _partition_contiguous(mergeable, summary_count)
    groups = [
        MergeGroup((index,), index, True) for index in sorted(protected)
    ]
    groups.extend(
        MergeGroup(tuple(indices), indices[-1], False)
        for indices in summary_groups
    )
    groups.sort(key=lambda group: group.output_position)
    plan = RequestMergePlan(tuple(groups), length)
    plan.assert_contribution_invariant()
    if plan.output_length != OUTPUT_STATES:
        raise RuntimeError("merge_plan_does_not_emit_fixed_1152_states")
    return plan


def build_batch_merge_plan(
    input_ids: Sequence[int],
    request_lengths: Sequence[int],
    *,
    special_token_ids: Sequence[int] = (),
    tool_mask: Sequence[bool] | None = None,
) -> BatchMergePlan:
    if len(input_ids) != sum(request_lengths):
        raise ValueError("ragged_prompt_geometry_mismatch")
    requests: list[RequestMergePlan] = []
    offset = 0
    for length in request_lengths:
        request_tool_mask = (
            tool_mask[offset : offset + length] if tool_mask is not None else None
        )
        requests.append(
            build_request_merge_plan(
                input_ids[offset : offset + length],
                special_token_ids=special_token_ids,
                tool_mask=request_tool_mask,
            )
        )
        offset += length
    return BatchMergePlan(tuple(requests))


def _merge_tensor(
    values: Any,
    scores: Any,
    plan: BatchMergePlan,
) -> Any:
    outputs = []
    offset = 0
    for request in plan.requests:
        for group in request.groups:
            indices = torch.tensor(
                [offset + index for index in group.source_indices],
                dtype=torch.long,
                device=values.device,
            )
            members = values.index_select(0, indices)
            if group.protected_singleton:
                outputs.append(members[0])
            else:
                group_scores = scores.index_select(0, indices).float()
                weights = torch.softmax(group_scores, dim=0).to(members.dtype)
                view_shape = (weights.shape[0],) + (1,) * (members.dim() - 1)
                outputs.append((members * weights.reshape(view_shape)).sum(dim=0))
        offset += request.input_length
    return torch.stack(outputs)


def merge_tensor_states(
    hidden_states: Any,
    per_layer_inputs: Any | None,
    plan: BatchMergePlan,
) -> tuple[Any, Any | None]:
    scores = hidden_states.float().square().mean(dim=-1)
    merged_hidden = _merge_tensor(hidden_states, scores, plan)
    merged_per_layer = (
        _merge_tensor(per_layer_inputs, scores, plan)
        if per_layer_inputs is not None
        else None
    )
    return merged_hidden, merged_per_layer


class CompactKVView:
    def __init__(self, model_runner: Any):
        self.req_to_token = torch.zeros_like(
            model_runner.req_to_token_pool.req_to_token
        )
        self.dropped_by_request: dict[int, int] = {}

    def _request_rows(self, forward_batch: Any) -> list[int]:
        return [
            int(row)
            for row in forward_batch.req_pool_indices.detach().cpu().tolist()
        ]

    def select_prefill_slots(
        self, full_batch: Any, plan: BatchMergePlan
    ) -> tuple[Any, Any]:
        representatives = torch.tensor(
            plan.representative_flat_indices(),
            dtype=torch.long,
            device=full_batch.out_cache_loc.device,
        )
        selected_slots = full_batch.out_cache_loc.index_select(0, representatives)
        rows = self._request_rows(full_batch)
        offset = 0
        for row, output_length, input_length in zip(
            rows, plan.output_lengths, plan.input_lengths, strict=True
        ):
            self.req_to_token[
                row, :output_length
            ] = selected_slots[offset : offset + output_length]
            self.dropped_by_request[row] = input_length - output_length
            offset += output_length
        return selected_slots, self.req_to_token

    def attach_continuation(self, full_batch: Any) -> Any:
        rows = self._request_rows(full_batch)
        if any(row not in self.dropped_by_request for row in rows):
            raise CompactionFallback("continuation_missing_compact_request_state")
        late = copy.copy(full_batch)
        dropped = torch.tensor(
            [self.dropped_by_request[row] for row in rows],
            dtype=full_batch.seq_lens.dtype,
            device=full_batch.seq_lens.device,
        )
        late.seq_lens = full_batch.seq_lens - dropped
        if bool(torch.any(late.seq_lens <= 0)):
            raise RuntimeError("compacted_continuation_length_is_nonpositive")
        late.seq_lens_sum = int(late.seq_lens.sum().item())
        late.req_to_token = self.req_to_token
        extend_lengths = getattr(full_batch, "extend_seq_lens", None)
        extend_starts = getattr(full_batch, "extend_start_loc", None)
        if extend_lengths is None:
            batch_size = len(rows)
            token_count = full_batch.out_cache_loc.numel()
            if token_count % batch_size != 0:
                raise CompactionFallback("continuation_rows_are_not_request_regular")
            per_request = token_count // batch_size
            extend_lengths = torch.full(
                (batch_size,),
                per_request,
                dtype=torch.int32,
                device=full_batch.out_cache_loc.device,
            )
            extend_starts = torch.arange(
                batch_size,
                dtype=torch.int32,
                device=full_batch.out_cache_loc.device,
            ) * per_request
        if extend_starts is None:
            extend_starts = torch.zeros_like(extend_lengths)
            if extend_lengths.numel() > 1:
                extend_starts[1:] = torch.cumsum(extend_lengths[:-1], dim=0)
        for request_offset, row in enumerate(rows):
            count = int(extend_lengths[request_offset].item())
            start = int(extend_starts[request_offset].item())
            logical_end = int(late.seq_lens[request_offset].item())
            self.req_to_token[
                row, logical_end - count : logical_end
            ] = full_batch.out_cache_loc[start : start + count]
        if getattr(full_batch, "extend_prefix_lens", None) is not None:
            late.extend_prefix_lens = full_batch.extend_prefix_lens - dropped
            late.extend_prefix_lens_cpu = (
                late.extend_prefix_lens.detach().cpu().tolist()
            )
        return late


class LateAttentionMetadata:
    def __init__(self, attention_backend: Any, compact_kv: CompactKVView):
        self.attention_backend = attention_backend
        self.compact_kv = compact_kv

    def init_forward_metadata(self, late_batch: Any) -> None:
        backend = self.attention_backend
        original_req_to_token = getattr(backend, "req_to_token", None)
        pool = getattr(backend, "req_to_token_pool", None)
        original_pool_map = pool.req_to_token if pool is not None else None
        if original_req_to_token is not None:
            backend.req_to_token = self.compact_kv.req_to_token
        if pool is not None:
            pool.req_to_token = self.compact_kv.req_to_token
        try:
            backend.init_forward_metadata(late_batch)
        finally:
            if original_req_to_token is not None:
                backend.req_to_token = original_req_to_token
            if pool is not None:
                pool.req_to_token = original_pool_map


def _mode_name(forward_batch: Any) -> str:
    mode = getattr(forward_batch, "forward_mode", "")
    return str(getattr(mode, "name", mode)).upper()


def _is_extend(forward_batch: Any) -> bool:
    return _mode_name(forward_batch) in {"EXTEND", "MIXED", "SPLIT_PREFILL"}


def _request_lengths(forward_batch: Any) -> tuple[int, ...]:
    values = getattr(forward_batch, "extend_seq_lens_cpu", None)
    if values is None:
        values = getattr(forward_batch, "extend_seq_lens", None)
        if values is not None:
            values = values.detach().cpu().tolist()
    if values is None:
        raise CompactionFallback("extend_request_lengths_unavailable")
    lengths = tuple(int(value) for value in values)
    if any(value != PROMPT_TOKENS for value in lengths):
        raise CompactionFallback("route_requires_full_4214_token_prefill")
    return lengths


def build_late_forward_batch(
    full_batch: Any,
    plan: BatchMergePlan,
    merged_input_ids: Any,
    merged_positions: Any,
) -> Any:
    compact_kv = getattr(full_batch, "prompt_compaction_kv_view", None)
    if compact_kv is None:
        raise CompactionFallback("compact_kv_view_unavailable")
    late_slots, late_req_to_token = compact_kv.select_prefill_slots(
        full_batch, plan
    )
    late = copy.copy(full_batch)
    lengths = torch.tensor(
        plan.output_lengths,
        dtype=torch.int32,
        device=merged_positions.device,
    )
    starts = torch.zeros_like(lengths)
    if lengths.numel() > 1:
        starts[1:] = torch.cumsum(lengths[:-1], dim=0)
    late.input_ids = merged_input_ids
    late.positions = merged_positions
    late.out_cache_loc = late_slots
    late.req_to_token = late_req_to_token
    late.extend_seq_lens = lengths
    late.extend_seq_lens_cpu = list(plan.output_lengths)
    late.extend_prefix_lens = torch.zeros_like(lengths)
    late.extend_prefix_lens_cpu = [0] * len(plan.requests)
    late.extend_start_loc = starts
    late.seq_lens = lengths
    late.seq_lens_sum = plan.total_output_states
    late.prompt_compaction_merge_plan = plan
    reinitialize = getattr(
        full_batch, "prompt_compaction_reinitialize_attention", None
    )
    if reinitialize is None:
        raise CompactionFallback("late_attention_metadata_callback_unavailable")
    reinitialize(late)
    full_batch.prompt_compaction_late_view = late
    return late


@dataclass
class LayerLoopState:
    input_ids: Any
    positions: Any
    forward_batch: Any
    merge_plan: BatchMergePlan | None = None

    def merge_after(
        self,
        layer_index: int,
        hidden_states: Any,
        per_layer_inputs: Any | None,
    ) -> tuple[Any, Any, Any | None, Any]:
        if layer_index != COMPACTION_AFTER_LAYER:
            return hidden_states, self.positions, per_layer_inputs, self.forward_batch
        if not _is_extend(self.forward_batch):
            late_view = getattr(
                self.forward_batch, "prompt_compaction_late_view", None
            )
            if late_view is None:
                raise CompactionFallback("decode_missing_persisted_late_kv_view")
            reinitialize = getattr(
                self.forward_batch,
                "prompt_compaction_reinitialize_attention",
                None,
            )
            if reinitialize is None:
                raise CompactionFallback(
                    "late_attention_metadata_callback_unavailable"
                )
            reinitialize(late_view)
            self.forward_batch = late_view
            return hidden_states, self.positions, per_layer_inputs, late_view

        lengths = _request_lengths(self.forward_batch)
        special_ids = tuple(
            int(value)
            for value in getattr(
                self.forward_batch, "prompt_compaction_special_token_ids", ()
            )
        )
        tool_mask = getattr(self.forward_batch, "prompt_compaction_tool_mask", None)
        self.merge_plan = build_batch_merge_plan(
            self.input_ids.detach().cpu().tolist(),
            lengths,
            special_token_ids=special_ids,
            tool_mask=(
                tool_mask.detach().cpu().tolist()
                if tool_mask is not None
                else None
            ),
        )
        hidden_states, per_layer_inputs = merge_tensor_states(
            hidden_states, per_layer_inputs, self.merge_plan
        )
        representatives = torch.tensor(
            self.merge_plan.representative_flat_indices(),
            dtype=torch.long,
            device=self.positions.device,
        )
        self.positions = self.positions.index_select(0, representatives)
        merged_input_ids = self.input_ids.index_select(0, representatives)
        self.forward_batch = build_late_forward_batch(
            self.forward_batch,
            self.merge_plan,
            merged_input_ids,
            self.positions,
        )
        return hidden_states, self.positions, per_layer_inputs, self.forward_batch


def begin_layer_loop(
    input_ids: Any,
    positions: Any,
    forward_batch: Any,
) -> LayerLoopState:
    return LayerLoopState(input_ids, positions, forward_batch)


def bind_runtime_resources(model_runner: Any, forward_batch: Any) -> None:
    compact_kv = getattr(model_runner, "prompt_compaction_kv_view", None)
    if compact_kv is None:
        compact_kv = CompactKVView(model_runner)
        model_runner.prompt_compaction_kv_view = compact_kv
        model_runner.prompt_compaction_late_attn_backend = LateAttentionMetadata(
            model_runner.attn_backend, compact_kv
        )
    forward_batch.prompt_compaction_kv_view = compact_kv
    forward_batch.prompt_compaction_reinitialize_attention = (
        model_runner.prompt_compaction_late_attn_backend.init_forward_metadata
    )
    if not _is_extend(forward_batch):
        forward_batch.prompt_compaction_late_view = compact_kv.attach_continuation(
            forward_batch
        )
