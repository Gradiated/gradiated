"""Offline endpoint-facing integration of the frozen adaptive-depth contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from adaptive_depth_contract import (
    AcceptedCarrier,
    ContractError,
    DepthAwareCorpusRouter,
    ProducerRequest,
    PackedBatch,
    pack_target_rows,
    settle_acceptance,
    settle_scheduler,
)


@dataclass(frozen=True)
class LifecycleResult:
    batch: PackedBatch
    carrier: AcceptedCarrier
    scheduler_rows: dict[str, tuple[int, ...]]
    graph_mode: str


class AdaptiveDepthEndpointLifecycle:
    """One coherent scheduler→producer→verify→settlement state machine.

    The router owns active producer depth; the packed batch owns the same depth
    for metadata, KV locations, acceptance, and scheduler stride. Completion
    retires request ownership before a slot can be reused.
    """

    def __init__(self) -> None:
        self.router = DepthAwareCorpusRouter()
        self.active: dict[str, int] = {}
        self.generation: dict[str, int] = {}

    def _check_requests(self, requests: Sequence[ProducerRequest]) -> None:
        ids = [request.rid for request in requests]
        if not ids:
            raise ContractError("empty_running_batch")
        if len(set(ids)) != len(ids):
            raise ContractError("duplicate_request_id")
        if set(ids) & (set(self.active) - set(ids)):
            raise ContractError("active_request_missing_from_batch")

    def _retire(self, request_ids: Iterable[str]) -> None:
        """Retire ownership through the adapter; bound contract stays immutable."""
        ids = tuple(request_ids)
        for corpus in self.router.corpora.values():
            corpus.erase_match_state(ids)
        for rid in ids:
            self.router._last_depth_by_request.pop(rid, None)

    def run_cycle(
        self,
        requests: Sequence[ProducerRequest],
        accepted_local_rows: Mapping[str, Sequence[int]],
        *,
        completed: Iterable[str] = (),
        cancelled: Iterable[str] = (),
    ) -> LifecycleResult:
        self._check_requests(requests)
        request_ids = {request.rid for request in requests}
        completed = set(completed)
        cancelled = set(cancelled)
        if not (completed | cancelled) <= request_ids:
            raise ContractError("settlement_owner_unknown")
        lanes = self.router.produce(requests)
        batch = pack_target_rows(lanes, len(requests))
        acceptance = settle_acceptance(batch, accepted_local_rows)
        carrier = AcceptedCarrier.from_acceptance(acceptance)
        scheduler_rows = settle_scheduler(carrier, completed | cancelled)
        graph_mode = "cuda_graph" if batch.depth == 12 else "eager"
        if graph_mode == "cuda_graph" and batch.target_rows != batch.batch_size * 12:
            raise ContractError("graph_shape_disguise")
        if graph_mode == "eager" and batch.depth != 6:
            raise ContractError("eager_depth_mismatch")
        for rid in completed | cancelled:
            self.active.pop(rid, None)
            self._retire((rid,))
        for request in requests:
            if request.rid not in completed and request.rid not in cancelled:
                self.active[request.rid] = batch.depth
                self.generation.setdefault(request.rid, 0)
        return LifecycleResult(batch, carrier, scheduler_rows, graph_mode)

    def reuse_slot(self, request: ProducerRequest) -> int:
        if request.rid in self.active:
            raise ContractError("reused_live_request_slot")
        generation = self.generation.get(request.rid, -1) + 1
        self.generation[request.rid] = generation
        return generation
