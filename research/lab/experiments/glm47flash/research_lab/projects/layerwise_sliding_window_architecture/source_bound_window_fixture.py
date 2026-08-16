#!/usr/bin/env python3
"""Executable source-bound mask and KV-state fixture for hybrid MLA layers."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass


LAYERS = 47
PROMPT = 8192
OUTPUT = 1024


def allowed_positions(layer: int, position: int, window: int | None,
                      global_layers: frozenset[int]) -> list[int]:
    if not 0 <= layer < LAYERS or position < 0:
        raise ValueError("invalid layer or position")
    first = 0 if window is None or layer in global_layers else max(0, position + 1 - window)
    return list(range(first, position + 1))


@dataclass
class KVState:
    window: int | None
    global_layers: frozenset[int]
    values: dict[int, list[int]]

    @classmethod
    def create(cls, window: int | None, global_layers: frozenset[int]) -> "KVState":
        return cls(window, global_layers, {layer: [] for layer in range(LAYERS)})

    def append(self, position: int) -> None:
        for layer in self.values:
            self.values[layer].append(position)
            if self.window is not None and layer not in self.global_layers:
                self.values[layer] = self.values[layer][-self.window:]


def check_fixture() -> dict[str, object]:
    globals_ = frozenset({0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44})
    probe = PROMPT + OUTPUT - 1
    global_mask = allowed_positions(0, probe, 1024, globals_)
    local_mask = allowed_positions(1, probe, 1024, globals_)
    assert global_mask[0] == 0 and global_mask[-1] == probe and len(global_mask) == probe + 1
    assert local_mask == list(range(probe + 1 - 1024, probe + 1))
    assert local_mask[0] == 8192 and local_mask[-1] == 9215

    state = KVState.create(1024, globals_)
    for position in range(PROMPT + OUTPUT):
        state.append(position)
    assert len(state.values[0]) == PROMPT + OUTPUT
    assert len(state.values[1]) == 1024
    assert state.values[1][0] == 8192 and state.values[1][-1] == 9215

    stock = KVState.create(None, frozenset())
    for position in range(33):
        stock.append(position)
    assert stock.values == {layer: list(range(33)) for layer in range(LAYERS)}
    return {
        "status": "pass",
        "layers": LAYERS,
        "probe_position": probe,
        "global_layer_count": len(globals_),
        "global_mask_tokens": len(global_mask),
        "local_mask_first_position": local_mask[0],
        "local_mask_tokens": len(local_mask),
        "global_kv_tokens": len(state.values[0]),
        "local_kv_tokens": len(state.values[1]),
        "stock_mode_unchanged": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = check_fixture()
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else "source-bound fixture: PASS")
