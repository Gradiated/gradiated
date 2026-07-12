"""Verify the mixed-precision KV plan derived from kv_sensitivity.json:
int8 on the 10 most int4-sensitive layers, int4 on the remaining 20.
Same protocol as kv_sensitivity.py."""

import json

import torch
from transformers import AttentionInterface, AutoModelForCausalLM, AutoTokenizer

from common import MODELS, RESULTS, save_json, strided_perplexity, tokenize_wikitext
from kv_sensitivity import EVAL_TOKENS, MODEL_DIR, WINDOW, kvq_attention, set_bits

DEVICE = "mps"
N_INT8 = 10


def main():
    prior = json.loads((RESULTS / "kv_sensitivity.json").read_text())
    ranking = prior["layers_most_tolerant_to_int4_first"]
    int8_layers = set(int(x) for x in ranking[-N_INT8:])
    plan = {li: (8 if li in int8_layers else 4) for li in range(len(ranking))}

    AttentionInterface.register("kvq", kvq_attention)
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, dtype=torch.float32).to(DEVICE)
    model.set_attn_implementation("kvq")
    model.eval()
    ids = tokenize_wikitext(tok, "test", EVAL_TOKENS)

    set_bits(model, plan)
    r = strided_perplexity(model, ids, window=WINDOW, stride=WINDOW, device=DEVICE)
    out = {
        "plan": {str(k): v for k, v in sorted(plan.items())},
        "int8_layers": sorted(int8_layers),
        "ppl": r["ppl"],
        "delta_vs_fp32_baseline": round(r["ppl"] - prior["baseline_ppl"], 4),
        "all_int8_ppl": prior["all_layers_int8_ppl"],
        "all_int4_ppl": prior["all_layers_int4_ppl"],
        "kv_bytes_vs_all_int8": round((20 * 4 + 10 * 8) / (30 * 8), 4),
    }
    print(json.dumps(out, indent=2))
    save_json(out, RESULTS / "kv_mixed.json")


if __name__ == "__main__":
    main()
