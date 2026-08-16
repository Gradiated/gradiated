"""Project-local dual-depth adapter used by the exact H100 component.

The native producers are intentionally separate objects: a depth-6 result is
never a view or slice of the depth-12 producer.  The carrier keeps accepted
rows by request, which is the invariant the earlier partial H200 patch broke.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ResultCarrier:
    request_ids: tuple[str, ...]
    offsets: tuple[int, ...]
    tokens: tuple[int, ...]

    def rows(self) -> list[list[int]]:
        return [list(self.tokens[self.offsets[i] : self.offsets[i + 1]])
                for i in range(len(self.request_ids))]


class DualDepthNgram:
    """Exact-depth native producer pair plus fail-closed state transitions."""

    CAPACITY = 12
    LOW = 6

    def __init__(self, corpus_cls, **kwargs):
        self.corpora = {
            self.CAPACITY: corpus_cls(draft_token_num=self.CAPACITY, **kwargs),
            self.LOW: corpus_cls(draft_token_num=self.LOW, **kwargs),
        }
        self.active_depth: dict[str, int] = {}
        self.accepted = ResultCarrier((), (0,), ())

    @staticmethod
    def depth_for_batch(batch_size: int) -> int:
        if batch_size < 1:
            raise ValueError("batch size must be positive")
        return 12 if batch_size <= 7 else 6

    def insert(self, rows: Iterable[Sequence[int]]) -> None:
        rows = [list(row) for row in rows]
        for corpus in self.corpora.values():
            corpus.batch_put(rows)
            corpus.synchronize()

    def produce(self, request_ids: list[str], queries: list[list[int]], lengths: list[int]):
        depth = self.depth_for_batch(len(request_ids))
        for rid in request_ids:
            if self.active_depth.get(rid) != depth:
                self.active_depth[rid] = depth
        tokens, masks = self.corpora[depth].batch_get(request_ids, queries, lengths)
        if tokens.shape != (len(request_ids) * depth,):
            raise ValueError("native producer token shape mismatch")
        if masks.shape != (len(request_ids) * depth * depth,):
            raise ValueError("native producer mask shape mismatch")
        return depth, tokens, masks

    def settle(self, request_ids: list[str], accepted_rows: list[list[int]]) -> ResultCarrier:
        if len(request_ids) != len(accepted_rows) or len(set(request_ids)) != len(request_ids):
            raise ValueError("ambiguous request ownership")
        offsets = [0]
        flat: list[int] = []
        for row in accepted_rows:
            flat.extend(row)
            offsets.append(len(flat))
        self.accepted = ResultCarrier(tuple(request_ids), tuple(offsets), tuple(flat))
        return self.accepted

    @staticmethod
    def graph_mode(depth: int) -> str:
        if depth == 12:
            return "cuda_graph"
        if depth == 6:
            return "eager"
        raise ValueError("unsupported depth")
