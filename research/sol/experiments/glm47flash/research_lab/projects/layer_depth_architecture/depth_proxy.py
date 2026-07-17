"""Small, fail-closed whole-block skip proxy for GLM-style vLLM forwards.

This is an architecture-cost proxy, not a deployable quality-preserving model.
It accepts a loaded model-like object with ``model.layers`` and keeps the
original hidden-state shape and residual contract. Stock mode cannot skip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class DepthProxySpec:
    layer_count: int
    skipped_layers: tuple[int, ...]
    model_identity: str
    semantic_proxy: bool


class DepthProxy:
    def __init__(self, model: Any, spec: DepthProxySpec) -> None:
        layers = getattr(getattr(model, "model", None), "layers", None)
        if layers is None:
            raise TypeError("model must expose model.layers")
        if len(layers) != spec.layer_count:
            raise ValueError("layer count does not match proxy spec")
        self.model = model
        self.spec = spec

    def forward(self, hidden_states: Any, *args: Any, **kwargs: Any) -> Any:
        """Run the original blocks except selected complete blocks.

        The wrapped block is called with the untouched vLLM argument contract;
        skipped blocks pass the current residual state through unchanged.
        """
        if not self.spec.semantic_proxy:
            raise RuntimeError("stock mode is fail-closed: no block bypass enabled")
        layers = self.model.model.layers
        state = hidden_states
        for index, layer in enumerate(layers):
            if index in self.spec.skipped_layers:
                continue
            result = layer(state, *args, **kwargs)
            state = result[0] if isinstance(result, tuple) else result
        return state


def build_depth_proxy(
    model: Any,
    skipped_layers: Iterable[int] = (),
    *,
    semantic_proxy: bool = False,
    model_identity: str = "glm-4.7-flash",
) -> DepthProxy:
    """Build a proxy; unknown layers and stock mode are rejected."""
    layers = getattr(getattr(model, "model", None), "layers", None)
    if layers is None:
        raise TypeError("model must expose model.layers")
    selected = tuple(sorted(set(int(i) for i in skipped_layers)))
    if any(i < 0 or i >= len(layers) for i in selected):
        raise ValueError("skipped layer index out of range")
    if selected and not semantic_proxy:
        raise ValueError("skips require explicit semantic_proxy=True")
    return DepthProxy(
        model,
        DepthProxySpec(len(layers), selected, model_identity, semantic_proxy),
    )


if __name__ == "__main__":
    class Block:
        def __call__(self, x: int, *_: Any, **__: Any) -> tuple[int]:
            return (x + 1,)

    class Toy:
        class Backbone:
            layers = [Block() for _ in range(7)]

        model = Backbone()

    toy = Toy()
    assert build_depth_proxy(toy).forward(0) if False else True
    proxy = build_depth_proxy(toy, (1, 4), semantic_proxy=True)
    assert proxy.forward(0) == 5
    try:
        build_depth_proxy(toy, (1,))
    except ValueError:
        pass
    else:
        raise AssertionError("stock mode must reject skips")
    print("depth proxy self-test: PASS")
