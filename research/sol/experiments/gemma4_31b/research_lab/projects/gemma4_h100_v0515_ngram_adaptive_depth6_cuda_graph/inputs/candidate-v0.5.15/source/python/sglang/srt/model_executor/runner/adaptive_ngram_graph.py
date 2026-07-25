from __future__ import annotations

from dataclasses import dataclass
from typing import Collection, Optional


CAPACITY_DEPTH = 12
HIGH_LOAD_DEPTH = 6
HIGH_LOAD_THRESHOLD = 8


class AdaptiveNgramGraphError(ValueError):
    pass


def depth_for_batch(batch_size: int) -> int:
    if batch_size < 1:
        raise AdaptiveNgramGraphError(f"invalid_batch_size:{batch_size}")
    return CAPACITY_DEPTH if batch_size < HIGH_LOAD_THRESHOLD else HIGH_LOAD_DEPTH


@dataclass(frozen=True)
class AdaptiveNgramGraphIdentity:
    batch_size: int
    speculative_depth: int
    num_tokens: int

    @classmethod
    def exact(
        cls,
        *,
        batch_size: int,
        speculative_depth: int,
        num_tokens: int,
    ) -> AdaptiveNgramGraphIdentity:
        expected_depth = depth_for_batch(batch_size)
        if speculative_depth != expected_depth:
            raise AdaptiveNgramGraphError(
                f"depth_rule_mismatch:{batch_size}:{speculative_depth}:{expected_depth}"
            )
        expected_tokens = batch_size * speculative_depth
        if num_tokens != expected_tokens:
            raise AdaptiveNgramGraphError(
                f"token_shape_mismatch:{num_tokens}:{expected_tokens}"
            )
        return cls(batch_size, speculative_depth, num_tokens)


def runtime_identity(
    forward_batch,
    *,
    captured_batch_sizes: Collection[int],
) -> Optional[AdaptiveNgramGraphIdentity]:
    spec_info = getattr(forward_batch, "spec_info", None)
    depth = getattr(spec_info, "draft_token_num", None)
    if depth is None:
        return None
    try:
        identity = AdaptiveNgramGraphIdentity.exact(
            batch_size=forward_batch.batch_size,
            speculative_depth=int(depth),
            num_tokens=int(forward_batch.input_ids.numel()),
        )
    except (AdaptiveNgramGraphError, TypeError, ValueError):
        return None
    if identity.batch_size not in captured_batch_sizes:
        return None
    for name in ("positions", "out_cache_loc"):
        value = getattr(forward_batch, name, None)
        if value is None or int(value.numel()) != identity.num_tokens:
            return None
    custom_mask = getattr(spec_info, "custom_mask", None)
    seq_lens = getattr(forward_batch, "seq_lens_cpu", None)
    if seq_lens is None:
        seq_lens = getattr(forward_batch, "seq_lens", None)
    if custom_mask is None or seq_lens is None:
        return None
    expected_mask = sum(
        identity.speculative_depth
        * (int(seq_len) + identity.speculative_depth)
        for seq_len in seq_lens[: identity.batch_size]
    )
    if int(custom_mask.numel()) != expected_mask:
        return None
    return identity
