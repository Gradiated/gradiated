"""Per-layer KV-cache precision sensitivity for SmolLM2-135M via fake-quant.

Mechanism: a custom attention function registered with AttentionInterface
wraps SDPA and fake-quantizes the key/value tensors it receives. In
transformers' Llama forward these are the post-RoPE K and post-projection V
exactly as they would sit in the KV cache, shape (b, kv_heads, s, head_dim).

Quantizer: symmetric round-to-nearest, absmax scale per head per token
(amax over head_dim), int8 -> qmax 127, int4 -> qmax 7.

Conditions: fp32 baseline, all-layers int8, all-layers int4, and int4 on one
layer at a time (30 runs). Eval: first 100k tokens of wikitext-2 test,
window 1024, stride 1024 (non-overlapping), fp32 on MPS.
"""

import json

import torch
from transformers import AttentionInterface, AutoModelForCausalLM, AutoTokenizer
from transformers.integrations.sdpa_attention import sdpa_attention_forward

from common import MODELS, RESULTS, save_json, strided_perplexity, tokenize_wikitext

MODEL_DIR = MODELS / "smollm2-135m-instruct"
DEVICE = "mps"
EVAL_TOKENS = 100_000
WINDOW = 1024


def fake_quant(x: torch.Tensor, bits: int) -> torch.Tensor:
    qmax = 2 ** (bits - 1) - 1
    s = x.abs().amax(dim=-1, keepdim=True).clamp(min=1e-8) / qmax
    return torch.round(x / s).clamp(-qmax, qmax) * s


def kvq_attention(module, query, key, value, attention_mask, **kwargs):
    bits = getattr(module, "_kv_bits", None)
    if bits is not None:
        key = fake_quant(key, bits)
        value = fake_quant(value, bits)
    return sdpa_attention_forward(module, query, key, value, attention_mask, **kwargs)


def set_bits(model, per_layer: dict[int, int | None]):
    for li, layer in enumerate(model.model.layers):
        layer.self_attn._kv_bits = per_layer.get(li)


def main():
    AttentionInterface.register("kvq", kvq_attention)
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, dtype=torch.float32).to(DEVICE)
    model.set_attn_implementation("kvq")
    model.eval()
    L = model.config.num_hidden_layers
    ids = tokenize_wikitext(tok, "test", EVAL_TOKENS)

    def run(tag, per_layer):
        set_bits(model, per_layer)
        r = strided_perplexity(model, ids, window=WINDOW, stride=WINDOW, device=DEVICE)
        print(f"{tag}: ppl {r['ppl']:.4f} ({r['eval_seconds']}s)", flush=True)
        return r["ppl"]

    results = {
        "protocol": {
            "model": str(MODEL_DIR), "eval_tokens": EVAL_TOKENS, "window": WINDOW,
            "stride": WINDOW, "dtype": "float32", "device": DEVICE,
            "quant": "symmetric RTN, absmax scale per head per token over head_dim",
        }
    }
    base = run("baseline fp32 KV", {})
    results["baseline_ppl"] = base
    results["all_layers_int8_ppl"] = run("all-layers int8", {li: 8 for li in range(L)})
    results["all_layers_int4_ppl"] = run("all-layers int4", {li: 4 for li in range(L)})

    per_layer = {}
    for li in range(L):
        per_layer[li] = run(f"only layer {li} int4", {li: 4})
    results["single_layer_int4_ppl"] = per_layer
    results["single_layer_int4_delta"] = {
        li: round(p - base, 4) for li, p in per_layer.items()
    }
    ranking = sorted(per_layer, key=lambda li: per_layer[li])
    results["layers_most_tolerant_to_int4_first"] = ranking
    save_json(results, RESULTS / "kv_sensitivity.json")


if __name__ == "__main__":
    main()
