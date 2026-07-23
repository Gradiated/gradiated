from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RingOwnership:
    request_pool_size: int
    tokens_per_row: int

    def __post_init__(self) -> None:
        if self.request_pool_size < 1:
            raise ValueError("request pool must contain at least one real slot")
        if self.tokens_per_row < 1 or self.tokens_per_row & (self.tokens_per_row - 1):
            raise ValueError("ring length must be a positive power of two")

    @property
    def row_count(self) -> int:
        return self.request_pool_size

    @property
    def reserved_slots(self) -> int:
        return self.row_count * self.tokens_per_row

    @property
    def slot_to_row(self) -> tuple[int, ...]:
        return (-1, *range(self.row_count))

    def rows_for_slots(self, request_slots: list[int]) -> list[int]:
        table = self.slot_to_row
        if any(slot < 0 or slot >= len(table) for slot in request_slots):
            raise ValueError("request slot lies outside the bound request pool")
        return [table[slot] for slot in request_slots]
