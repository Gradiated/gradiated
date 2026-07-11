"""Real head surgery on SmolLM2-135M: prune Q-heads 9 -> 6 (drop the weakest
q-head in each GQA group of 3, per layer, per head_importance.json), slicing
q_proj rows and o_proj columns. K/V untouched (kv_heads stays 3).

Writes models/smollm2-135m-pruned-h6/ with fixed config
(num_attention_heads=6, head_dim=64) + tokenizer files."""

import json
import shutil

import torch
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

from common import MODELS, RESULTS

SRC = MODELS / "smollm2-135m-instruct"
DST = MODELS / "smollm2-135m-pruned-h6"


def main():
    plan = json.loads((RESULTS / "head_importance" / "head_importance.json").read_text())
    drop = {int(k): v for k, v in plan["heads_to_drop_per_layer"].items()}

    model = AutoModelForCausalLM.from_pretrained(SRC, dtype=torch.float32)
    cfg = model.config
    H, KV = cfg.num_attention_heads, cfg.num_key_value_heads
    hd = cfg.hidden_size // H
    assert H == 9 and KV == 3 and hd == 64

    for li, layer in enumerate(model.model.layers):
        keep = sorted(set(range(H)) - set(drop[li]))
        assert len(keep) == 6
        # GQA validity: exactly 2 kept q-heads per kv group of 3
        for g in range(KV):
            assert sum(1 for h in keep if h // (H // KV) == g) == 2, (li, keep)
        attn = layer.self_attn
        q_rows = torch.cat([torch.arange(h * hd, (h + 1) * hd) for h in keep])
        attn.q_proj.weight.data = attn.q_proj.weight.data[q_rows].clone()
        attn.q_proj.out_features = len(q_rows)
        attn.o_proj.weight.data = attn.o_proj.weight.data[:, q_rows].clone()
        attn.o_proj.in_features = len(q_rows)

    cfg.num_attention_heads = 6
    cfg.head_dim = hd

    DST.mkdir(exist_ok=True)
    model.save_pretrained(DST, safe_serialization=True)
    # save_pretrained rewrites config from cfg; ensure head_dim persisted
    saved = json.loads((DST / "config.json").read_text())
    assert saved["num_attention_heads"] == 6
    saved["head_dim"] = hd
    saved["num_key_value_heads"] = KV
    (DST / "config.json").write_text(json.dumps(saved, indent=2))

    for f in ["tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
              "generation_config.json"]:
        if (SRC / f).exists():
            shutil.copy(SRC / f, DST / f)

    n_params = sum(p.numel() for p in model.parameters())
    print(f"pruned model params: {n_params/1e6:.2f}M -> {DST}")

    # reload sanity check
    m2 = AutoModelForCausalLM.from_pretrained(DST, dtype=torch.float32)
    tok = AutoTokenizer.from_pretrained(DST)
    ids = tok("The capital of France is", return_tensors="pt").input_ids
    with torch.no_grad():
        out = m2(ids)
    print("reload ok, logits shape", tuple(out.logits.shape))


if __name__ == "__main__":
    main()
