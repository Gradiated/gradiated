"""Negative control: scales the final RMSNorm output by 0.9 (sharpens nothing, flattens logits; must fail)."""


def install(model, patch, ctx):
    norm = ctx["text_model"].norm
    original = norm.forward

    def scaled(*args, **kwargs):
        out = original(*args, **kwargs)
        return out * 0.9 if not isinstance(out, tuple) else (out[0] * 0.9,) + tuple(out[1:])

    patch(norm, "forward", scaled)
