from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


LOW_LOAD_DEPTH = 12
HIGH_LOAD_DEPTH = 6
HIGH_LOAD_MIN_REQUESTS = 8
SUPPORTED_DEPTHS = (HIGH_LOAD_DEPTH, LOW_LOAD_DEPTH)


class ContractError(ValueError):
    pass


def selected_depth(running_requests: int) -> int:
    if running_requests < 1:
        raise ContractError(f"running_requests_must_be_positive:{running_requests}")
    return (
        HIGH_LOAD_DEPTH
        if running_requests >= HIGH_LOAD_MIN_REQUESTS
        else LOW_LOAD_DEPTH
    )


@dataclass(frozen=True)
class ProducerRequest:
    rid: str
    seq_len: int
    tail_tokens: tuple[int, ...]
    prefix_kv: tuple[int, ...]
    out_cache_base: int

    def __post_init__(self) -> None:
        if not self.rid:
            raise ContractError("empty_request_id")
        if self.seq_len < 1:
            raise ContractError(f"invalid_seq_len:{self.rid}:{self.seq_len}")
        if len(self.prefix_kv) != self.seq_len:
            raise ContractError(
                f"prefix_kv_shape:{self.rid}:{len(self.prefix_kv)}:{self.seq_len}"
            )


@dataclass(frozen=True)
class ProducerLane:
    request: ProducerRequest
    depth: int
    draft_tokens: tuple[int, ...]
    tree_mask: tuple[tuple[bool, ...], ...]

    def validate(self) -> None:
        if self.depth not in SUPPORTED_DEPTHS:
            raise ContractError(f"unsupported_depth:{self.depth}")
        if len(self.draft_tokens) != self.depth:
            raise ContractError(
                f"draft_shape:{self.request.rid}:{len(self.draft_tokens)}:{self.depth}"
            )
        if len(self.tree_mask) != self.depth:
            raise ContractError(
                f"tree_rows:{self.request.rid}:{len(self.tree_mask)}:{self.depth}"
            )
        for row_index, row in enumerate(self.tree_mask):
            if len(row) != self.depth:
                raise ContractError(
                    f"tree_columns:{self.request.rid}:{row_index}:{len(row)}:{self.depth}"
                )
            if not row[row_index]:
                raise ContractError(
                    f"tree_missing_self:{self.request.rid}:{row_index}"
                )
            if any(row[row_index + 1 :]):
                raise ContractError(
                    f"tree_forward_edge:{self.request.rid}:{row_index}"
                )


class SyntheticDepthCorpus:
    """A deterministic CPU stand-in for one exact-depth native corpus object."""

    def __init__(self, depth: int):
        if depth not in SUPPORTED_DEPTHS:
            raise ContractError(f"unsupported_corpus_depth:{depth}")
        self.depth = depth
        self.match_calls = 0
        self.erased: list[str] = []
        self._last_total_len: dict[str, int] = {}

    def erase_match_state(self, request_ids: Iterable[str]) -> None:
        for rid in request_ids:
            self._last_total_len.pop(rid, None)
            self.erased.append(rid)

    def match_stateful(
        self, requests: Sequence[ProducerRequest]
    ) -> tuple[ProducerLane, ...]:
        self.match_calls += 1
        lanes = []
        for request in requests:
            prior = self._last_total_len.get(request.rid)
            if prior is not None and request.seq_len < prior:
                raise ContractError(
                    f"producer_total_len_regressed:{request.rid}:{prior}:{request.seq_len}"
                )
            self._last_total_len[request.rid] = request.seq_len
            seed = sum(request.tail_tokens) % 100_000
            draft_tokens = tuple(seed * 100 + index for index in range(self.depth))
            tree_mask = tuple(
                tuple(column <= row for column in range(self.depth))
                for row in range(self.depth)
            )
            lanes.append(
                ProducerLane(
                    request=request,
                    depth=self.depth,
                    draft_tokens=draft_tokens,
                    tree_mask=tree_mask,
                )
            )
        return tuple(lanes)


class DepthAwareCorpusRouter:
    """Routes to a real depth-specific producer and resets stale match ownership."""

    def __init__(self) -> None:
        self.corpora = {
            depth: SyntheticDepthCorpus(depth) for depth in SUPPORTED_DEPTHS
        }
        self._last_depth_by_request: dict[str, int] = {}

    def produce(
        self, requests: Sequence[ProducerRequest]
    ) -> tuple[ProducerLane, ...]:
        depth = selected_depth(len(requests))
        corpus = self.corpora[depth]
        switched = [
            request.rid
            for request in requests
            if self._last_depth_by_request.get(request.rid, depth) != depth
        ]
        corpus.erase_match_state(switched)
        lanes = corpus.match_stateful(requests)
        for request in requests:
            self._last_depth_by_request[request.rid] = depth
        return lanes


@dataclass(frozen=True)
class PackedBatch:
    depth: int
    request_ids: tuple[str, ...]
    seq_lens: tuple[int, ...]
    row_splits: tuple[int, ...]
    draft_tokens: tuple[int, ...]
    positions: tuple[int, ...]
    tree_mask: tuple[bool, ...]
    full_custom_mask: tuple[bool, ...]
    mask_indptr: tuple[int, ...]
    qo_indptr: tuple[int, ...]
    kv_indptr: tuple[int, ...]
    kv_indices: tuple[int, ...]
    out_cache_loc: tuple[int, ...]
    row_owner: tuple[str, ...]

    @property
    def batch_size(self) -> int:
        return len(self.request_ids)

    @property
    def target_rows(self) -> int:
        return len(self.draft_tokens)

    def request_row_slice(self, index: int) -> slice:
        return slice(self.row_splits[index], self.row_splits[index + 1])

    def validate(self) -> None:
        expected_rows = self.batch_size * self.depth
        if self.row_splits != tuple(
            index * self.depth for index in range(self.batch_size + 1)
        ):
            raise ContractError("nonuniform_target_row_splits")
        for name, values in (
            ("draft_tokens", self.draft_tokens),
            ("positions", self.positions),
            ("out_cache_loc", self.out_cache_loc),
            ("row_owner", self.row_owner),
        ):
            if len(values) != expected_rows:
                raise ContractError(
                    f"packed_shape:{name}:{len(values)}:{expected_rows}"
                )
        if len(self.tree_mask) != self.batch_size * self.depth * self.depth:
            raise ContractError("packed_tree_mask_shape")
        expected_qo = tuple(
            index * self.depth for index in range(self.batch_size + 1)
        )
        if self.qo_indptr != expected_qo:
            raise ContractError(f"qo_indptr_mismatch:{self.qo_indptr}:{expected_qo}")
        if len(self.mask_indptr) != self.batch_size + 1:
            raise ContractError("mask_indptr_shape")
        if self.mask_indptr[-1] != len(self.full_custom_mask):
            raise ContractError("custom_mask_terminal_offset")
        if len(self.kv_indptr) != self.batch_size + 1:
            raise ContractError("kv_indptr_shape")
        if self.kv_indptr[-1] != len(self.kv_indices):
            raise ContractError("kv_terminal_offset")
        for index, rid in enumerate(self.request_ids):
            lane = self.row_owner[self.request_row_slice(index)]
            if lane != (rid,) * self.depth:
                raise ContractError(f"row_owner_mismatch:{rid}")


def pack_target_rows(
    lanes: Sequence[ProducerLane], running_requests: int
) -> PackedBatch:
    if len(lanes) != running_requests:
        raise ContractError(
            f"running_request_count_mismatch:{len(lanes)}:{running_requests}"
        )
    depth = selected_depth(running_requests)
    if len({lane.request.rid for lane in lanes}) != len(lanes):
        raise ContractError("duplicate_request_id")

    request_ids: list[str] = []
    seq_lens: list[int] = []
    draft_tokens: list[int] = []
    positions: list[int] = []
    tree_mask: list[bool] = []
    full_custom_mask: list[bool] = []
    mask_indptr = [0]
    qo_indptr = [0]
    kv_indptr = [0]
    kv_indices: list[int] = []
    out_cache_loc: list[int] = []
    row_owner: list[str] = []

    for lane in lanes:
        lane.validate()
        if lane.depth != depth:
            raise ContractError(
                f"producer_consumer_depth:{lane.request.rid}:{lane.depth}:{depth}"
            )
        request = lane.request
        request_ids.append(request.rid)
        seq_lens.append(request.seq_len)
        draft_tokens.extend(lane.draft_tokens)
        flat_tree = [value for row in lane.tree_mask for value in row]
        tree_mask.extend(flat_tree)
        positions.extend(
            request.seq_len + sum(row) - 1 for row in lane.tree_mask
        )
        for row in lane.tree_mask:
            full_custom_mask.extend((True,) * request.seq_len)
            full_custom_mask.extend(row)
        mask_indptr.append(len(full_custom_mask))
        qo_indptr.append(len(draft_tokens))
        request_out_cache = tuple(
            request.out_cache_base + offset for offset in range(depth)
        )
        out_cache_loc.extend(request_out_cache)
        kv_indices.extend(request.prefix_kv)
        kv_indices.extend(request_out_cache)
        kv_indptr.append(len(kv_indices))
        row_owner.extend((request.rid,) * depth)

    packed = PackedBatch(
        depth=depth,
        request_ids=tuple(request_ids),
        seq_lens=tuple(seq_lens),
        row_splits=tuple(index * depth for index in range(len(lanes) + 1)),
        draft_tokens=tuple(draft_tokens),
        positions=tuple(positions),
        tree_mask=tuple(tree_mask),
        full_custom_mask=tuple(full_custom_mask),
        mask_indptr=tuple(mask_indptr),
        qo_indptr=tuple(qo_indptr),
        kv_indptr=tuple(kv_indptr),
        kv_indices=tuple(kv_indices),
        out_cache_loc=tuple(out_cache_loc),
        row_owner=tuple(row_owner),
    )
    packed.validate()
    return packed


@dataclass(frozen=True)
class AcceptanceState:
    depth: int
    request_ids: tuple[str, ...]
    accept_indices: tuple[tuple[int, ...], ...]
    accept_lens: tuple[int, ...]
    num_correct_drafts: tuple[int, ...]
    accepted_token_rows: tuple[tuple[int, ...], ...]
    kv_moves: tuple[tuple[str, int, int], ...]

    def validate(self, packed: PackedBatch) -> None:
        if self.depth != packed.depth or self.request_ids != packed.request_ids:
            raise ContractError("acceptance_batch_identity")
        if len(self.accept_indices) != packed.batch_size:
            raise ContractError("acceptance_batch_shape")
        for request_index, row in enumerate(self.accept_indices):
            if len(row) != self.depth:
                raise ContractError("acceptance_row_width")
            valid = [value for value in row if value != -1]
            if len(valid) != self.accept_lens[request_index]:
                raise ContractError("acceptance_length")
            lane_slice = packed.request_row_slice(request_index)
            if any(value < lane_slice.start or value >= lane_slice.stop for value in valid):
                raise ContractError(
                    f"cross_request_accept_index:{packed.request_ids[request_index]}"
                )
            if any(value != -1 for value in row[len(valid) :]):
                raise ContractError("acceptance_sentinel_order")
            if self.num_correct_drafts[request_index] != len(valid) - 1:
                raise ContractError("accepted_draft_count")
            if len(self.accepted_token_rows[request_index]) != self.depth:
                raise ContractError("accepted_token_row_width")
        for rid, _source, _destination in self.kv_moves:
            if rid not in packed.request_ids:
                raise ContractError(f"kv_move_unknown_owner:{rid}")


def settle_acceptance(
    packed: PackedBatch, accepted_local_rows: Mapping[str, Sequence[int]]
) -> AcceptanceState:
    rows: list[tuple[int, ...]] = []
    accept_lens: list[int] = []
    num_correct: list[int] = []
    accepted_token_rows: list[tuple[int, ...]] = []
    kv_moves: list[tuple[str, int, int]] = []

    for request_index, rid in enumerate(packed.request_ids):
        local_rows = tuple(accepted_local_rows[rid])
        if not local_rows:
            raise ContractError(f"missing_bonus_row:{rid}")
        if len(local_rows) > packed.depth:
            raise ContractError(f"too_many_accept_rows:{rid}")
        if len(set(local_rows)) != len(local_rows):
            raise ContractError(f"duplicate_accept_row:{rid}")
        if any(index < 0 or index >= packed.depth for index in local_rows):
            raise ContractError(f"accept_row_oob:{rid}")

        lane_start = packed.row_splits[request_index]
        global_rows = tuple(lane_start + index for index in local_rows)
        padded_indices = global_rows + (-1,) * (packed.depth - len(global_rows))
        predicted = tuple(900_000 + index for index in global_rows)
        padded_tokens = predicted + (-1,) * (packed.depth - len(predicted))
        rows.append(padded_indices)
        accept_lens.append(len(global_rows))
        num_correct.append(len(global_rows) - 1)
        accepted_token_rows.append(padded_tokens)
        destination_base = packed.seq_lens[request_index]
        for accepted_offset, global_row in enumerate(global_rows):
            source = packed.out_cache_loc[global_row]
            destination = destination_base + accepted_offset
            kv_moves.append((rid, source, destination))

    state = AcceptanceState(
        depth=packed.depth,
        request_ids=packed.request_ids,
        accept_indices=tuple(rows),
        accept_lens=tuple(accept_lens),
        num_correct_drafts=tuple(num_correct),
        accepted_token_rows=tuple(accepted_token_rows),
        kv_moves=tuple(kv_moves),
    )
    state.validate(packed)
    return state


@dataclass(frozen=True)
class AcceptedCarrier:
    request_ids: tuple[str, ...]
    row_offsets: tuple[int, ...]
    token_rows: tuple[int, ...]
    accept_lens: tuple[int, ...]

    def validate(self) -> None:
        if len(self.row_offsets) != len(self.request_ids) + 1:
            raise ContractError("carrier_offset_shape")
        if not self.row_offsets or self.row_offsets[0] != 0:
            raise ContractError("carrier_offset_origin")
        if any(
            left > right
            for left, right in zip(self.row_offsets, self.row_offsets[1:])
        ):
            raise ContractError("carrier_offsets_not_monotonic")
        if self.row_offsets[-1] != len(self.token_rows):
            raise ContractError("carrier_terminal_offset")
        if len(self.accept_lens) != len(self.request_ids):
            raise ContractError("carrier_accept_shape")
        for index, accepted in enumerate(self.accept_lens):
            width = self.row_offsets[index + 1] - self.row_offsets[index]
            if accepted < 1 or accepted > width:
                raise ContractError(
                    f"carrier_accept_width:{self.request_ids[index]}:{accepted}:{width}"
                )

    @classmethod
    def from_acceptance(cls, state: AcceptanceState) -> AcceptedCarrier:
        token_rows = tuple(
            token for request_row in state.accepted_token_rows for token in request_row
        )
        offsets = tuple(
            index * state.depth for index in range(len(state.request_ids) + 1)
        )
        carrier = cls(
            request_ids=state.request_ids,
            row_offsets=offsets,
            token_rows=token_rows,
            accept_lens=state.accept_lens,
        )
        carrier.validate()
        return carrier

    def accepted_tokens(self, index: int) -> tuple[int, ...]:
        start = self.row_offsets[index]
        return self.token_rows[start : start + self.accept_lens[index]]

    def filter(self, indices: Sequence[int]) -> AcceptedCarrier:
        rows: list[int] = []
        offsets = [0]
        request_ids = []
        accept_lens = []
        for index in indices:
            if index < 0 or index >= len(self.request_ids):
                raise ContractError(f"carrier_filter_oob:{index}")
            start, end = self.row_offsets[index : index + 2]
            rows.extend(self.token_rows[start:end])
            offsets.append(len(rows))
            request_ids.append(self.request_ids[index])
            accept_lens.append(self.accept_lens[index])
        result = AcceptedCarrier(
            request_ids=tuple(request_ids),
            row_offsets=tuple(offsets),
            token_rows=tuple(rows),
            accept_lens=tuple(accept_lens),
        )
        result.validate()
        return result

    def merge(self, other: AcceptedCarrier) -> AcceptedCarrier:
        self.validate()
        other.validate()
        if set(self.request_ids) & set(other.request_ids):
            raise ContractError("carrier_merge_duplicate_request")
        shift = len(self.token_rows)
        result = AcceptedCarrier(
            request_ids=self.request_ids + other.request_ids,
            row_offsets=self.row_offsets + tuple(
                shift + offset for offset in other.row_offsets[1:]
            ),
            token_rows=self.token_rows + other.token_rows,
            accept_lens=self.accept_lens + other.accept_lens,
        )
        result.validate()
        return result


def settle_scheduler(
    carrier: AcceptedCarrier, completed_requests: Iterable[str]
) -> dict[str, tuple[int, ...]]:
    carrier.validate()
    completed = set(completed_requests)
    unknown = completed - set(carrier.request_ids)
    if unknown:
        raise ContractError(f"completed_request_unknown:{sorted(unknown)}")
    return {
        rid: (() if rid in completed else carrier.accepted_tokens(index))
        for index, rid in enumerate(carrier.request_ids)
    }


def graph_admissible(
    packed: PackedBatch, captured_depth: int = LOW_LOAD_DEPTH
) -> tuple[bool, str]:
    packed.validate()
    if packed.depth != captured_depth:
        return False, f"depth_mismatch:{packed.depth}:{captured_depth}"
    if packed.target_rows != packed.batch_size * captured_depth:
        return False, "target_row_shape"
    return True, "exact_depth_shape"


def analytical_work(running_requests: int, sequence_length: int) -> dict[str, float | int]:
    if sequence_length < 1:
        raise ContractError(f"invalid_sequence_length:{sequence_length}")
    depth = selected_depth(running_requests)
    baseline_depth = LOW_LOAD_DEPTH
    baseline_rows = running_requests * baseline_depth
    candidate_rows = running_requests * depth
    baseline_mask_elements = running_requests * baseline_depth * (
        sequence_length + baseline_depth
    )
    candidate_mask_elements = running_requests * depth * (
        sequence_length + depth
    )
    return {
        "running_requests": running_requests,
        "sequence_length": sequence_length,
        "selected_depth": depth,
        "baseline_target_rows": baseline_rows,
        "candidate_target_rows": candidate_rows,
        "eliminated_target_rows": baseline_rows - candidate_rows,
        "target_row_reduction_fraction": (
            (baseline_rows - candidate_rows) / baseline_rows
        ),
        "baseline_attention_mask_elements": baseline_mask_elements,
        "candidate_attention_mask_elements": candidate_mask_elements,
        "eliminated_attention_mask_elements": (
            baseline_mask_elements - candidate_mask_elements
        ),
        "attention_mask_reduction_fraction": (
            (baseline_mask_elements - candidate_mask_elements)
            / baseline_mask_elements
        ),
    }
