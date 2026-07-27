from __future__ import annotations

import mmap
import os
import pathlib
import struct
from dataclasses import dataclass
from typing import Protocol, Sequence, TypeVar


POLICY_NAME = "attained-service"
TRACE_ENV = "SGLANG_ATTAINED_SERVICE_GRAPH_TRACE"
TRACE_MAGIC = b"ASGBV001"
TRACE = struct.Struct("<8sQQQQQQQ")


class RuntimeRequest(Protocol):
    rid: str
    output_ids: Sequence[int]
    time_stats: object


T = TypeVar("T", bound=RuntimeRequest)


@dataclass(frozen=True)
class RequestState:
    request_id: str
    arrival_ordinal: int
    arrival_ns: int
    prompt_tokens: int
    attained_output_tokens: int


def attained_service_sort_key(request: RuntimeRequest) -> tuple[int, float, str]:
    return (
        len(request.output_ids),
        float(request.time_stats.scheduler_recv_time),
        request.rid,
    )


def fifo_sort_key(request: RequestState) -> tuple[int, int, str]:
    return (request.arrival_ns, request.arrival_ordinal, request.request_id)


def offline_attained_service_sort_key(
    request: RequestState,
) -> tuple[int, int, int, str]:
    return (
        request.attained_output_tokens,
        request.arrival_ns,
        request.arrival_ordinal,
        request.request_id,
    )


def order_offline(
    requests: Sequence[RequestState], *, attained_service: bool
) -> list[RequestState]:
    key = offline_attained_service_sort_key if attained_service else fifo_sort_key
    return sorted(requests, key=key)


class GraphShapeObserver:
    __slots__ = (
        "_map",
        "_path",
        "active_row_steps",
        "decode_steps",
        "graph_transitions",
        "last_padded_bs",
        "padded_row_steps",
    )

    def __init__(self, path: pathlib.Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            os.ftruncate(fd, mmap.PAGESIZE)
            self._map = mmap.mmap(fd, mmap.PAGESIZE, access=mmap.ACCESS_WRITE)
        finally:
            os.close(fd)
        self._path = path
        self.active_row_steps = 0
        self.decode_steps = 0
        self.graph_transitions = 0
        self.last_padded_bs = 0
        self.padded_row_steps = 0
        self._persist(raw_bs=0, padded_bs=0)

    def observe(self, *, raw_bs: int, padded_bs: int) -> None:
        if raw_bs <= 0 or padded_bs < raw_bs:
            raise ValueError(f"invalid graph shape: {raw_bs=}, {padded_bs=}")
        if self.last_padded_bs and self.last_padded_bs != padded_bs:
            self.graph_transitions += 1
        self.decode_steps += 1
        self.active_row_steps += raw_bs
        self.padded_row_steps += padded_bs - raw_bs
        self.last_padded_bs = padded_bs
        self._persist(raw_bs=raw_bs, padded_bs=padded_bs)

    def _persist(self, *, raw_bs: int, padded_bs: int) -> None:
        self._map[: TRACE.size] = TRACE.pack(
            TRACE_MAGIC,
            self.decode_steps,
            self.active_row_steps,
            self.padded_row_steps,
            self.graph_transitions,
            raw_bs,
            padded_bs,
            self.last_padded_bs,
        )


_OBSERVER: GraphShapeObserver | None = None


def observe_graph_shape(*, raw_bs: int, padded_bs: int) -> None:
    global _OBSERVER
    path = os.environ.get(TRACE_ENV)
    if not path:
        return
    if _OBSERVER is None:
        _OBSERVER = GraphShapeObserver(pathlib.Path(path))
    _OBSERVER.observe(raw_bs=raw_bs, padded_bs=padded_bs)


def read_graph_trace(path: pathlib.Path) -> dict[str, int]:
    raw = path.read_bytes()[: TRACE.size]
    (
        magic,
        decode_steps,
        active_row_steps,
        padded_row_steps,
        graph_transitions,
        raw_bs,
        padded_bs,
        last_padded_bs,
    ) = TRACE.unpack(raw)
    if magic != TRACE_MAGIC:
        raise ValueError("attained-service graph trace magic mismatch")
    return {
        "decode_steps": decode_steps,
        "active_row_steps": active_row_steps,
        "padded_row_steps": padded_row_steps,
        "graph_transitions": graph_transitions,
        "raw_bs": raw_bs,
        "padded_bs": padded_bs,
        "last_padded_bs": last_padded_bs,
    }
