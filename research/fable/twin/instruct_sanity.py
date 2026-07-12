"""Qualitative instruct sanity suite: baseline vs healed head-pruned model.

12 chat prompts through the SmolLM2 chat template, greedy decoding,
side-by-side outputs saved for qualitative pass/fail review. Complements
perplexity: wikitext healing may erode chat behaviour (catastrophic
forgetting), which ppl alone won't show.
"""

import json

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import MODELS, RESULTS, save_json

DEVICE = "mps"
PROMPTS = [
    "What is the capital of France?",
    "Explain photosynthesis in two sentences.",
    "Write a haiku about the ocean.",
    "List three uses for a paperclip.",
    "What is 17 + 25?",
    "Give me a one-line Python function that squares a number.",
    "Who wrote Romeo and Juliet?",
    "Translate 'good morning' into French.",
    "Name two planets closer to the Sun than Earth.",
    "What gas do plants absorb from the atmosphere?",
    "Suggest a name for a coffee shop run by cats.",
    "Summarize in one sentence why exercise is healthy.",
]


@torch.no_grad()
def generate_all(model_dir):
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.float32).to(DEVICE)
    model.eval()
    outs = []
    for p in PROMPTS:
        msgs = [{"role": "user", "content": p}]
        enc = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt")
        ids = (enc["input_ids"] if not torch.is_tensor(enc) else enc).to(DEVICE)
        gen = model.generate(ids, max_new_tokens=120, do_sample=False,
                             pad_token_id=tok.eos_token_id)
        outs.append(tok.decode(gen[0, ids.shape[1]:], skip_special_tokens=True).strip())
    del model
    torch.mps.empty_cache()
    return outs


def main():
    base = generate_all(MODELS / "smollm2-135m-instruct")
    healed = generate_all(MODELS / "smollm2-135m-pruned-h6-healed")
    rows = [{"prompt": p, "baseline": b, "healed_pruned": h}
            for p, b, h in zip(PROMPTS, base, healed)]
    save_json({"decoding": "greedy, max_new_tokens=120, chat template",
               "rows": rows}, RESULTS / "instruct_sanity.json")
    for r in rows:
        print("=" * 70)
        print("PROMPT:", r["prompt"])
        print("- base :", r["baseline"][:200].replace("\n", " | "))
        print("- heal :", r["healed_pruned"][:200].replace("\n", " | "))


if __name__ == "__main__":
    main()
