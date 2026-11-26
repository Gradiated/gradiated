"""Negative control: scales every routed-expert output by 0.97 (must fail the gate)."""


def install(model, patch, ctx):
    for layer in ctx["text_model"].layers:
        experts = getattr(getattr(layer, "ffn", None), "experts", None)
        if experts is None:
            continue
        original = experts.forward

        def scaled(*args, _original=original, **kwargs):
            out = _original(*args, **kwargs)
            if isinstance(out, tuple):
                return tuple(o * 0.97 if hasattr(o, "mul") else o for o in out)
            return out * 0.97

        patch(experts, "forward", scaled)
