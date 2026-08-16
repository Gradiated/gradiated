"""Pure scope contract for selective GLM-4.7 head/shared W4 packets."""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable
from typing import Any


VALID_SCOPES = ("combined", "head_only", "shared_only")
EXPECTED_WEIGHT_COUNTS = {
    "combined": 139,
    "head_only": 1,
    "shared_only": 138,
}


def normalize_scope(scope: str) -> str:
    if scope not in VALID_SCOPES:
        raise ValueError(f"unsupported selective-W4 scope: {scope!r}")
    return scope


def is_head_weight(name: str) -> bool:
    return name == "lm_head.weight"


def is_shared_weight(name: str) -> bool:
    return bool(
        re.fullmatch(
            r"model\.layers\.(?:[1-9]|[1-3][0-9]|4[0-6])\.mlp\.shared_experts\.(?:gate_proj|up_proj|down_proj)\.weight",
            name,
        )
    )


def is_selective_candidate(name: str) -> bool:
    return is_head_weight(name) or is_shared_weight(name)


def selected_weight(name: str, scope: str) -> bool:
    scope = normalize_scope(scope)
    return (
        scope in {"combined", "head_only"} and is_head_weight(name)
    ) or (
        scope in {"combined", "shared_only"} and is_shared_weight(name)
    )


def expected_weight_count(scope: str) -> int:
    return EXPECTED_WEIGHT_COUNTS[normalize_scope(scope)]


def apply_scope_to_config(
    config: dict[str, Any],
    candidate_weights: Iterable[str],
    scope: str,
) -> dict[str, Any]:
    """Return a copied config whose dispatch and ignore lists match one scope.

    All candidate names must describe the complete head-plus-shared universe. This
    fail-closed requirement prevents a partial index from silently producing a
    packet with an apparently valid precision label.
    """

    scope = normalize_scope(scope)
    candidates = list(candidate_weights)
    if len(candidates) != EXPECTED_WEIGHT_COUNTS["combined"]:
        raise ValueError(
            "selective-W4 candidate closure mismatch: "
            f"{len(candidates)} != {EXPECTED_WEIGHT_COUNTS['combined']}"
        )
    if len(set(candidates)) != len(candidates) or not all(
        is_selective_candidate(name) for name in candidates
    ):
        raise ValueError("selective-W4 candidate universe is invalid")

    selected = {name for name in candidates if selected_weight(name, scope)}
    if len(selected) != expected_weight_count(scope):
        raise ValueError(
            f"selective-W4 {scope} closure mismatch: "
            f"{len(selected)} != {expected_weight_count(scope)}"
        )

    result = copy.deepcopy(config)
    quantization = result["quantization_config"]
    groups = quantization["config_groups"]
    base_group = groups.get("group_0")
    weights = base_group.get("weights") if isinstance(base_group, dict) else None
    if (
        not isinstance(base_group, dict)
        or base_group.get("targets") != ["Linear"]
        or not isinstance(weights, dict)
        or (weights.get("num_bits"), weights.get("type"), weights.get("symmetric"), weights.get("strategy"), weights.get("group_size"))
        != (4, "int", True, "group", 32)
    ):
        raise ValueError("selective-W4 native Linear group-32 symmetric uint4 contract mismatch")
    if scope in {"combined", "head_only"}:
        groups["parallel_lm_head_w4"] = {
            **copy.deepcopy(groups["group_0"]),
            "targets": ["ParallelLMHead"],
        }
    else:
        groups.pop("parallel_lm_head_w4", None)

    selected_modules = {name.removesuffix(".weight") for name in selected}
    candidate_modules = [name.removesuffix(".weight") for name in candidates]
    ignored = [
        name for name in quantization["ignore"] if name not in selected_modules
    ]
    ignored_set = set(ignored)
    for module in candidate_modules:
        if module not in selected_modules and module not in ignored_set:
            ignored.append(module)
            ignored_set.add(module)
    quantization["ignore"] = ignored
    return result


def validate_scope_config(
    config: dict[str, Any],
    candidate_weights: Iterable[str],
    scope: str,
) -> None:
    """Raise when a materialized config does not express its claimed scope."""

    scope = normalize_scope(scope)
    candidates = list(candidate_weights)
    selected_modules = {
        name.removesuffix(".weight")
        for name in candidates
        if selected_weight(name, scope)
    }
    unselected_modules = {
        name.removesuffix(".weight")
        for name in candidates
        if not selected_weight(name, scope)
    }
    quantization = config["quantization_config"]
    ignored = set(quantization["ignore"])
    groups = quantization["config_groups"]
    head_group = groups.get("parallel_lm_head_w4")
    head_group_pass = (
        head_group is not None and head_group.get("targets") == ["ParallelLMHead"]
    ) if scope in {"combined", "head_only"} else head_group is None
    if not head_group_pass:
        raise ValueError(f"selective-W4 {scope} ParallelLMHead dispatch mismatch")
    if selected_modules & ignored:
        raise ValueError(f"selective-W4 {scope} selected modules remain ignored")
    if not unselected_modules <= ignored:
        raise ValueError(f"selective-W4 {scope} BF16 modules are not all ignored")
