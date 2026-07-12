"""Capture per-token MoE routing decisions from granite-1b-a400m.

Hooks every layer's GraniteMoeTopKRouter and records the top-k expert indices
for each token. Corpus: ~150k tokens of wikitext-2 (train) + ~50k tokens of
code-ish text mined from local sharegpt_v3.json (assistant turns containing
fenced code blocks). Output: routing_topk.npz with per-layer (T, k) int8 index
arrays plus domain boundaries.
"""

import json
import time
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import DATA, MODELS, RESULTS, load_wikitext_text

MODEL_DIR = MODELS / "granite-1b-a400m"
DEVICE = "mps"
SEQ_LEN = 2048
WIKI_TOKENS = 150_000
CODE_TOKENS = 50_000


def code_text_from_sharegpt(min_chars=200_000) -> str:
    """Concatenate fenced code blocks from sharegpt assistant turns."""
    data = json.loads((DATA / "sharegpt_v3.json").read_text())
    chunks, total = [], 0
    for conv in data:
        for turn in conv.get("conversations", []):
            v = turn.get("value", "")
            if turn.get("from") == "gpt" and "```" in v:
                parts = v.split("```")
                for i in range(1, len(parts), 2):  # inside fences
                    body = parts[i]
                    if "\n" in body:
                        body = body.split("\n", 1)[1]  # drop language tag line
                    if len(body.strip()) > 80:
                        chunks.append(body)
                        total += len(body)
        if total > min_chars:
            break
    return "\n\n".join(chunks)


def main():
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, dtype=torch.float32).to(DEVICE)
    model.eval()
    cfg = model.config
    L, E, K = cfg.num_hidden_layers, cfg.num_local_experts, cfg.num_experts_per_tok
    print(f"layers={L} experts={E} top_k={K}")

    routers = []
    for i, layer in enumerate(model.model.layers):
        r = layer.block_sparse_moe.router
        routers.append(r)
    assert len(routers) == L

    captured = [[] for _ in range(L)]

    def make_hook(idx):
        def hook(module, inp, out):
            top_k_index = out[0]  # (num_tokens, K)
            captured[idx].append(top_k_index.detach().to("cpu", torch.int8))
        return hook

    handles = [r.register_forward_hook(make_hook(i)) for i, r in enumerate(routers)]

    wiki_ids = tok(load_wikitext_text("train"), return_tensors="pt").input_ids[0][:WIKI_TOKENS]
    code_ids = tok(code_text_from_sharegpt(), return_tensors="pt").input_ids[0][:CODE_TOKENS]
    print(f"wiki tokens={wiki_ids.numel()} code tokens={code_ids.numel()}")

    t0 = time.time()
    n_done = 0
    domain_boundary = None
    with torch.no_grad():
        for name, ids in [("wiki", wiki_ids), ("code", code_ids)]:
            if name == "code":
                domain_boundary = n_done
            for s in range(0, ids.numel() - SEQ_LEN + 1, SEQ_LEN):
                batch = ids[s : s + SEQ_LEN].unsqueeze(0).to(DEVICE)
                model(batch)
                n_done += SEQ_LEN
                if n_done % 20480 == 0:
                    print(f"{n_done} tokens, {time.time()-t0:.0f}s", flush=True)

    for h in handles:
        h.remove()

    arrays = {f"layer_{i:02d}": torch.cat(captured[i]).numpy() for i in range(L)}
    meta = dict(
        model=str(MODEL_DIR), layers=L, experts=E, top_k=K, seq_len=SEQ_LEN,
        n_tokens=n_done, domain_boundary=domain_boundary,
        domains={"wiki": [0, domain_boundary], "code": [domain_boundary, n_done]},
        capture_seconds=round(time.time() - t0, 1),
    )
    out = RESULTS / "granite_routing"
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "routing_topk.npz", **arrays)
    (out / "capture_meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
