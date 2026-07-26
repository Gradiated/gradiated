from __future__ import annotations

import os
from collections.abc import Iterable


LAYER_COUNT = 60
FULL_DEPTH_ROUTE = "full_depth"
PHYSICAL_PROXY_ROUTE = "proxy_30p20v"

PREFILL_GROUPS = ((0, 10), (25, 35), (50, 60))
VERIFICATION_GROUPS = ((0, 10), (50, 60))


def expand_groups(groups: Iterable[tuple[int, int]]) -> frozenset[int]:
    active = frozenset(
        layer_index
        for start, stop in groups
        for layer_index in range(start, stop)
    )
    if any(layer_index < 0 or layer_index >= LAYER_COUNT for layer_index in active):
        raise ValueError("conditional-depth group lies outside the 60-layer stack")
    return active


PREFILL_ACTIVE_LAYERS = expand_groups(PREFILL_GROUPS)
VERIFICATION_ACTIVE_LAYERS = expand_groups(VERIFICATION_GROUPS)
FULL_ACTIVE_LAYERS = frozenset(range(LAYER_COUNT))
DEFAULT_ROUTE = os.environ.get(
    "SGLANG_CONDITIONAL_DEPTH_ROUTE", PHYSICAL_PROXY_ROUTE
)

if not VERIFICATION_ACTIVE_LAYERS.issubset(PREFILL_ACTIVE_LAYERS):
    raise RuntimeError("verification layers must own KV written during prefill")


def _mode_name(forward_mode: object) -> str:
    name = getattr(forward_mode, "name", forward_mode)
    return str(name).upper()


def phase_for_mode(forward_mode: object) -> str:
    mode = _mode_name(forward_mode)
    if mode in {"TARGET_VERIFY", "DECODE", "IDLE"}:
        return "verification"
    if mode in {
        "EXTEND",
        "MIXED",
        "SPLIT_PREFILL",
        "DRAFT_EXTEND",
        "DRAFT_EXTEND_V2",
        "DLLM_EXTEND",
        "PREBUILT",
    }:
        return "prefill"
    raise ValueError(f"unsupported conditional-depth forward mode: {mode}")


def route_for_batch(forward_batch: object) -> str:
    route_ids = getattr(forward_batch, "conditional_depth_route_ids", None)
    if route_ids is not None:
        unique = frozenset(str(route_id) for route_id in route_ids)
        if len(unique) != 1:
            raise ValueError(
                "conditional-depth batches must be route-homogeneous before model execution"
            )
        route = next(iter(unique))
    else:
        route = str(
            getattr(
                forward_batch,
                "conditional_depth_route_id",
                DEFAULT_ROUTE,
            )
        )
    if route not in {FULL_DEPTH_ROUTE, PHYSICAL_PROXY_ROUTE}:
        raise ValueError(f"unknown conditional-depth route: {route}")
    return route


def active_layer_indices(forward_batch: object) -> frozenset[int]:
    if route_for_batch(forward_batch) == FULL_DEPTH_ROUTE:
        return FULL_ACTIVE_LAYERS
    phase = phase_for_mode(getattr(forward_batch, "forward_mode"))
    if phase == "prefill":
        return PREFILL_ACTIVE_LAYERS
    return VERIFICATION_ACTIVE_LAYERS
