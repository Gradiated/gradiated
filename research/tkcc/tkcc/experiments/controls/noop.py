"""A candidate that changes nothing: use it to check the tooling and noise."""


def install(model, patch, ctx):
    layer = ctx["text_model"].layers[0]
    patch(layer, "_tkcc_marker", ctx["rank"])
