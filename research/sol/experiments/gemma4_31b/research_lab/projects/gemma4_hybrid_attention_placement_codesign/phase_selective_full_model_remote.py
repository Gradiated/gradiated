#!/usr/bin/env python3
"""Bridge installed inside the later single-model SGLang server process.

The old version constructed a second, standalone ``ModelRunner``.  This bridge
accepts the already-resident production model and records the phase/cache
contract on it before any candidate request is admitted.  The later component
driver supplies the exact production ForwardBatch and invokes the bound hooks.
"""
from __future__ import annotations

from typing import Any

from full_model_memory_adapter import CONVERTED_LAYERS, adapter_binding


def _layers(model: Any) -> Any:
    """Resolve the pinned Gemma text-layer collection without creating a model."""
    for path in (("language_model", "layers"), ("model", "layers"), ("layers",)):
        current = model
        try:
            for name in path:
                current = getattr(current, name)
        except AttributeError:
            continue
        if len(current) > max(CONVERTED_LAYERS):
            return current
    raise RuntimeError("pinned Gemma layer collection unavailable on resident server model")


def install_phase_selective_adapter(model: Any) -> dict[str, Any]:
    """Bind metadata and hook ownership to exactly one resident target model.

    The mutable cache implementation remains the production worker's pools.
    No tensor, cache, or model is allocated here; the later target-verify
    driver performs mirrored bank operations via the bound dispatcher.
    """
    if getattr(model, "_phase_selective_adapter", None) is not None:
        raise RuntimeError("phase-selective adapter already bound; refusing duplicate residency")
    layers = _layers(model)
    binding = adapter_binding()
    for index in CONVERTED_LAYERS:
        attention = getattr(layers[index], "self_attn", None)
        if attention is None:
            raise RuntimeError(f"converted layer {index} lacks pinned Gemma self_attn")
        # Metadata is intentionally non-tensor: it cannot silently create a
        # second producer or preallocate a cache before the later claim.
        setattr(attention, "_phase_selective_cache_binding", binding)
    setattr(model, "_phase_selective_adapter", binding)
    return binding


def adapter_is_bound(model: Any) -> bool:
    return getattr(model, "_phase_selective_adapter", None) == adapter_binding()
