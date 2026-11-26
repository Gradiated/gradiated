"""Instrumentation candidate: count distinct routed experts per prefill chunk.

Wraps every MoE gate's forward (undone at teardown) and reproduces noaux_tc
selection (sqrt-softplus score plus correction bias, top-k) to record which
experts the tokens of each eager prefill chunk route to.
"""

import torch

_STATE = {"hits": [], "tokens": [], "layer": []}
TOPK = 6


def _record(layer_index, gate, logits):
    if not isinstance(logits, torch.Tensor) or logits.dim() != 2 or logits.shape[0] < 65:
        return
    if torch.cuda.is_current_stream_capturing():
        return
    scores = torch.sqrt(torch.nn.functional.softplus(logits.float()))
    bias = getattr(gate, "e_score_correction_bias", None)
    if bias is not None:
        scores = scores + bias.float()
    picks = scores.topk(TOPK, dim=-1).indices
    _STATE["hits"].append(int(torch.unique(picks).numel()))
    _STATE["tokens"].append(int(logits.shape[0]))
    _STATE["layer"].append(layer_index)


def install(model, patch, ctx):
    for index, layer in enumerate(ctx["text_model"].layers):
        gate = getattr(getattr(layer, "ffn", None), "gate", None)
        if gate is None:
            continue
        original = gate.forward

        def wrapped(*args, _original=original, _gate=gate, _index=index, **kwargs):
            out = _original(*args, **kwargs)
            _record(_index, _gate, out[0] if isinstance(out, tuple) else out)
            return out

        patch(gate, "forward", wrapped)


def reset():
    for values in _STATE.values():
        values.clear()
    return True


def collect():
    return {key: list(values) for key, values in _STATE.items()}
