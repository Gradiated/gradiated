from __future__ import annotations

import struct
from collections import OrderedDict
from collections.abc import Hashable, Sequence


class DistinctRequestPromotionGate:
    def __init__(self, max_probation_entries: int):
        if max_probation_entries < 1:
            raise ValueError("max_probation_entries must be positive")
        self.max_probation_entries = max_probation_entries
        self._first_request_by_suffix: OrderedDict[bytes, Hashable] = OrderedDict()
        self.admitted = 0
        self.evicted = 0
        self.same_request_repeats = 0

    @staticmethod
    def suffix_key(tokens: Sequence[int]) -> bytes:
        values = tuple(int(token) for token in tokens)
        return struct.pack(f"<{len(values)}I", *values)

    def admit(self, request_id: Hashable, tokens: Sequence[int]) -> bool:
        key = self.suffix_key(tokens)
        first_request = self._first_request_by_suffix.get(key)
        if first_request is None:
            self._first_request_by_suffix[key] = request_id
            if len(self._first_request_by_suffix) > self.max_probation_entries:
                self._first_request_by_suffix.popitem(last=False)
                self.evicted += 1
            return False
        if first_request == request_id:
            self.same_request_repeats += 1
            return False
        del self._first_request_by_suffix[key]
        self.admitted += 1
        return True

    def clear(self) -> None:
        self._first_request_by_suffix.clear()

    @property
    def probation_entries(self) -> int:
        return len(self._first_request_by_suffix)

