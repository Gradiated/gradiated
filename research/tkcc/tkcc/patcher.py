"""Undoable attribute patches applied by a hot-reloaded candidate."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

_MISSING = object()


@dataclass(frozen=True)
class _Record:
    target: Any
    name: str
    previous: Any


class Patcher:
    """Records every setattr so teardown can restore the baseline exactly.

    Candidates call ``patch(obj, "name", value)``. A dotted module path is
    accepted as ``obj`` so candidates can replace module-level kernels too.
    """

    def __init__(self) -> None:
        self._records: list[_Record] = []

    def __call__(self, target: Any, name: str, value: Any) -> Any:
        if isinstance(target, str):
            target = importlib.import_module(target)
        previous = target.__dict__.get(name, _MISSING) if hasattr(target, "__dict__") else _MISSING
        if previous is _MISSING and not hasattr(target, "__dict__"):
            previous = getattr(target, name, _MISSING)
        self._records.append(_Record(target, name, previous))
        setattr(target, name, value)
        return value

    def __len__(self) -> int:
        return len(self._records)

    def undo(self) -> int:
        restored = 0
        while self._records:
            record = self._records.pop()
            if record.previous is _MISSING:
                try:
                    delattr(record.target, record.name)
                except AttributeError:
                    pass
            else:
                setattr(record.target, record.name, record.previous)
            restored += 1
        return restored
