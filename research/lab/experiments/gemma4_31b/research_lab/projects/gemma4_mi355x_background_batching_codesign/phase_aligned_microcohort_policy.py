"""Fixed phase-aligned microcohort admission policy.

This module is the model-specific policy core intended for vLLM's
``SchedulerConfig.scheduler_cls`` hook.  It deliberately has no vLLM import:
the scheduler adapter owns request conversion, while this core emits the
exact per-request token map consumed by ``GPUModelRunner``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


COHORT_SIZE = 16
MAX_LIVE_SEQUENCES = 96
PREFILL_TOKEN_BUDGET = 8192


class PolicyRequest(Protocol):
    request_id: int
    fresh_prompt_tokens: int
    fresh_computed: int
    output_tokens: int

    @property
    def is_prefill(self) -> bool: ...


@dataclass
class Microcohort:
    cohort_id: int
    requests: list[PolicyRequest]
    terminal_partial_fallback: bool = False

    def __post_init__(self) -> None:
        size = len(self.requests)
        if size != COHORT_SIZE and not self.terminal_partial_fallback:
            raise ValueError("ordinary microcohorts must contain exactly 16 requests")
        if not 0 < size <= COHORT_SIZE:
            raise ValueError("microcohort size must be in [1, 16]")
        if len({request.request_id for request in self.requests}) != size:
            raise ValueError("microcohort request IDs must be unique")

    @property
    def size(self) -> int:
        return len(self.requests)

    @property
    def is_prefill(self) -> bool:
        states = {request.is_prefill for request in self.requests}
        if len(states) != 1:
            raise RuntimeError("microcohort phase alignment was lost in prefill")
        return states.pop()

    @property
    def output_tokens(self) -> int:
        counts = {request.output_tokens for request in self.requests}
        if len(counts) != 1:
            raise RuntimeError("microcohort output phase alignment was lost")
        return counts.pop()


@dataclass(frozen=True)
class ScheduledRow:
    request: PolicyRequest
    kind: str
    tokens: int
    cohort_id: int
    terminal_partial_fallback: bool


class PhaseAlignedMicrocohortPolicy:
    """One fixed FCFS 16-request policy; there are no tuning parameters."""

    cohort_size = COHORT_SIZE
    max_live_sequences = MAX_LIVE_SEQUENCES
    prefill_token_budget = PREFILL_TOKEN_BUDGET

    def __init__(self) -> None:
        self._next_cohort_id = 0

    def form_ready_cohort(
        self,
        waiting: list[PolicyRequest],
        live_sequences: int,
        *,
        arrival_stream_closed: bool,
    ) -> Microcohort | None:
        available_slots = self.max_live_sequences - live_sequences
        if len(waiting) >= self.cohort_size and available_slots >= self.cohort_size:
            size = self.cohort_size
            fallback = False
        elif (
            arrival_stream_closed
            and waiting
            and len(waiting) < self.cohort_size
            and available_slots >= len(waiting)
        ):
            size = len(waiting)
            fallback = True
        else:
            return None

        requests = waiting[:size]
        del waiting[:size]
        cohort = Microcohort(
            cohort_id=self._next_cohort_id,
            requests=requests,
            terminal_partial_fallback=fallback,
        )
        self._next_cohort_id += 1
        return cohort

    @staticmethod
    def _prefill_counts(
        cohort: Microcohort, token_budget: int
    ) -> list[int] | None:
        remaining = [
            request.fresh_prompt_tokens - request.fresh_computed
            for request in cohort.requests
        ]
        if any(value <= 0 for value in remaining):
            raise RuntimeError("invalid aligned prefill remainder")
        if sum(remaining) <= token_budget:
            return remaining

        # Every member advances by the same amount on non-final chunks.  At
        # least one token remains for every member so the final, possibly
        # 535/536-cache-mixed chunk completes the entire cohort together.
        common = min(min(remaining) - 1, token_budget // cohort.size)
        if common <= 0:
            return None
        return [common] * cohort.size

    def schedule_existing(
        self, cohorts: list[Microcohort], token_budget: int
    ) -> tuple[list[ScheduledRow], int]:
        scheduled: list[ScheduledRow] = []
        for cohort in cohorts:
            if cohort.is_prefill:
                counts = self._prefill_counts(cohort, token_budget)
                if counts is None:
                    continue
                kind = "prefill"
            else:
                if token_budget < cohort.size:
                    continue
                counts = [1] * cohort.size
                kind = "decode"
            for request, count in zip(cohort.requests, counts, strict=True):
                scheduled.append(
                    ScheduledRow(
                        request=request,
                        kind=kind,
                        tokens=count,
                        cohort_id=cohort.cohort_id,
                        terminal_partial_fallback=(
                            cohort.terminal_partial_fallback
                        ),
                    )
                )
            token_budget -= sum(counts)
        return scheduled, token_budget

    def admit_and_schedule(
        self,
        waiting: list[PolicyRequest],
        cohorts: list[Microcohort],
        token_budget: int,
        *,
        arrival_stream_closed: bool,
    ) -> tuple[list[ScheduledRow], int, list[Microcohort]]:
        scheduled: list[ScheduledRow] = []
        admitted: list[Microcohort] = []
        live = sum(cohort.size for cohort in cohorts)
        while token_budget > 0:
            cohort = self.form_ready_cohort(
                waiting,
                live,
                arrival_stream_closed=arrival_stream_closed,
            )
            if cohort is None:
                break
            counts = self._prefill_counts(cohort, token_budget)
            if counts is None:
                # Admission is atomic with the first token-map emission.
                waiting[:0] = cohort.requests
                self._next_cohort_id -= 1
                break
            admitted.append(cohort)
            cohorts.append(cohort)
            live += cohort.size
            for request, count in zip(cohort.requests, counts, strict=True):
                scheduled.append(
                    ScheduledRow(
                        request=request,
                        kind="prefill",
                        tokens=count,
                        cohort_id=cohort.cohort_id,
                        terminal_partial_fallback=(
                            cohort.terminal_partial_fallback
                        ),
                    )
                )
            token_budget -= sum(counts)
        return scheduled, token_budget, admitted

    def schedule(
        self,
        waiting: list[PolicyRequest],
        cohorts: list[Microcohort],
        *,
        arrival_stream_closed: bool,
    ) -> tuple[list[ScheduledRow], list[Microcohort]]:
        scheduled, remaining = self.schedule_existing(
            cohorts, self.prefill_token_budget
        )
        new_rows, _, admitted = self.admit_and_schedule(
            waiting,
            cohorts,
            remaining,
            arrival_stream_closed=arrival_stream_closed,
        )
        scheduled.extend(new_rows)
        return scheduled, admitted
