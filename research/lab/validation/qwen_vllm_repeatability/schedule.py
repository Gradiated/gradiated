from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduledRun:
    ordinal: int
    pair_id: str
    concurrency: int
    repeat_index: int
    state: str


def build_schedule(
    concurrency_levels: tuple[int, ...], repeat_pairs: int, seed: int
) -> tuple[ScheduledRun, ...]:
    pairs = [
        (concurrency, repeat_index)
        for concurrency in concurrency_levels
        for repeat_index in range(1, repeat_pairs + 1)
    ]
    random.Random(seed).shuffle(pairs)
    runs: list[ScheduledRun] = []
    for concurrency, repeat_index in pairs:
        pair_id = f"c{concurrency}-r{repeat_index}"
        for state in ("cold_engine", "warm_engine"):
            runs.append(
                ScheduledRun(
                    ordinal=len(runs) + 1,
                    pair_id=pair_id,
                    concurrency=concurrency,
                    repeat_index=repeat_index,
                    state=state,
                )
            )
    return tuple(runs)
