from __future__ import annotations

from dataclasses import dataclass, field


class CommitBufferCapacityError(RuntimeError):
    pass


@dataclass
class _RequestState:
    owner: str
    max_rows: int
    rows: list[tuple[int, ...]] = field(default_factory=list)


class CompletedRequestCommitBuffer:
    def __init__(self, max_active_requests: int):
        if max_active_requests <= 0:
            raise ValueError("max_active_requests must be positive")
        self.max_active_requests = max_active_requests
        self._states: dict[str, _RequestState] = {}
        self.committed_requests = 0
        self.committed_rows = 0
        self.discarded_requests = 0
        self.discarded_rows = 0
        self.id_reuses = 0

    @property
    def active_requests(self) -> int:
        return len(self._states)

    @property
    def buffered_rows(self) -> int:
        return sum(len(state.rows) for state in self._states.values())

    def stage(
        self,
        request_id: str,
        owner: str,
        tokens: list[int],
        max_rows: int,
    ) -> None:
        request_id = str(request_id)
        owner = str(owner)
        if max_rows <= 0:
            raise CommitBufferCapacityError("request row bound must be positive")

        state = self._states.get(request_id)
        if state is not None and state.owner != owner:
            self._discard_state(request_id)
            self.id_reuses += 1
            state = None

        if state is None:
            if len(self._states) >= self.max_active_requests:
                raise CommitBufferCapacityError("active request bound exceeded")
            state = _RequestState(owner=owner, max_rows=max_rows)
            self._states[request_id] = state
        elif state.max_rows != max_rows:
            raise CommitBufferCapacityError("request row bound changed in flight")

        if len(state.rows) >= state.max_rows:
            raise CommitBufferCapacityError("per-request row bound exceeded")
        state.rows.append(tuple(int(token) for token in tokens))

    def finish(
        self, request_id: str, owner: str, *, aborted: bool
    ) -> list[list[int]]:
        request_id = str(request_id)
        state = self._states.get(request_id)
        if state is None or state.owner != str(owner):
            return []
        rows = self._states.pop(request_id).rows
        if aborted:
            self.discarded_requests += 1
            self.discarded_rows += len(rows)
            return []
        self.committed_requests += 1
        self.committed_rows += len(rows)
        return [list(row) for row in rows]

    def discard(self, request_id: str, owner: str | None = None) -> bool:
        request_id = str(request_id)
        state = self._states.get(request_id)
        if state is None or (owner is not None and state.owner != str(owner)):
            return False
        self._discard_state(request_id)
        return True

    def discard_matching(self, request_id_prefix: str, *, all_requests: bool) -> int:
        request_id_prefix = str(request_id_prefix)
        matches = [
            request_id
            for request_id in self._states
            if all_requests or request_id.startswith(request_id_prefix)
        ]
        for request_id in matches:
            self._discard_state(request_id)
        return len(matches)

    def clear(self) -> None:
        for request_id in list(self._states):
            self._discard_state(request_id)

    def _discard_state(self, request_id: str) -> None:
        state = self._states.pop(request_id)
        self.discarded_requests += 1
        self.discarded_rows += len(state.rows)
