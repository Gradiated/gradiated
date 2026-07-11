"""Per-head importance for SmolLM2-135M: mean L2 norm of each head's
contribution at the o_proj input, measured over ~50k tokens of wikitext-2
validation. Saves (num_layers, num_heads) matrix + JSON."""

import json

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import MODELS, RESULTS, tokenize_wikitext

MODEL_DIR = MODELS / "smollm2-135m-instruct"
DEVICE = "mps"
SEQ_LEN = 1024
MAX_TOKENS = 50_000


def main():
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, dtype=torch.float32).to(DEVICE)
    model.eval()
    cfg = model.config
    H = cfg.num_attention_heads
    hd = cfg.hidden_size // H
    L = cfg.num_hidden_layers

    sums = torch.zeros(L, H, dtype=torch.float64)
    counts = torch.zeros(L, dtype=torch.float64)

    def make_hook(li):
        def hook(module, inp, out):
            x = inp[0]  # (b, s, H*hd) — concatenated head outputs entering o_proj
            b, s, _ = x.shape
            norms = x.reshape(b * s, H, hd).norm(dim=-1)  # (tokens, H)
            sums[li] += norms.sum(0).cpu().double()
            counts[li] += b * s
        return hook

    handles = [
        model.model.layers[li].self_attn.o_proj.register_forward_hook(make_hook(li))
        for li in range(L)
    ]

    ids = tokenize_wikitext(tok, "validation", MAX_TOKENS)
    with torch.no_grad():
        for s in range(0, ids.numel() - SEQ_LEN + 1, SEQ_LEN):
            model(ids[s : s + SEQ_LEN].unsqueeze(0).to(DEVICE))
    for h in handles:
        h.remove()

    imp = (sums / counts.unsqueeze(1)).numpy()
    out = RESULTS / "head_importance"
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "head_norm_importance.npy", imp)

    kv_groups = H // cfg.num_key_value_heads  # q-heads per kv head
    pruned = {}
    for li in range(L):
        drop = []
        for g in range(cfg.num_key_value_heads):
            grp = list(range(g * kv_groups, (g + 1) * kv_groups))
            drop.append(int(min(grp, key=lambda h_: imp[li, h_])))
        pruned[li] = drop

    meta = {
        "model": str(MODEL_DIR),
        "metric": "mean L2 norm of per-head o_proj input over tokens",
        "tokens": int(counts[0].item()),
        "seq_len": SEQ_LEN,
        "importance": {str(li): [round(float(v), 4) for v in imp[li]] for li in range(L)},
        "heads_to_drop_per_layer": pruned,
    }
    (out / "head_importance.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({"heads_to_drop_per_layer": pruned}, indent=2))


if __name__ == "__main__":
    main()
