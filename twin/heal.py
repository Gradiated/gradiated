"""Heal the pruned SmolLM2-135M with a brief finetune on wikitext-2 train.

Protocol: AdamW (no weight decay on norms/bias), lr 1e-4 cosine to 1e-5 with
100-step linear warmup, seq 1024, batch 8 (packed, non-overlapping windows,
reshuffled each epoch over ~2.4M train tokens), fp32 on MPS, 2000 steps
(= 16.4M tokens seen). Validation ppl (wikitext-2 validation, first 100k
tokens, window 1024 stride 1024) every 250 steps. Only model weights are
saved; optimizer state is discarded.
"""

import argparse
import json
import math
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import MODELS, RESULTS, save_json, strided_perplexity, tokenize_wikitext

_ap = argparse.ArgumentParser()
_ap.add_argument("--src", default=str(MODELS / "smollm2-135m-pruned-h6"))
_ap.add_argument("--dst", default=str(MODELS / "smollm2-135m-pruned-h6-healed"))
_ap.add_argument("--curve", default="healing_curve.json")
_ap.add_argument("--steps", type=int, default=1500)
_ap.add_argument("--force-head-dim", type=int, default=64,
                 help="head_dim written into saved config.json (0 = leave config alone)")
_args = _ap.parse_args()

SRC = MODELS.parent / _args.src if not _args.src.startswith("/") else type(MODELS)(_args.src)
DST = MODELS.parent / _args.dst if not _args.dst.startswith("/") else type(MODELS)(_args.dst)
DEVICE = "mps"
SEQ = 1024
BATCH = 8
STEPS = _args.steps
WARMUP = 100
LR = 1e-4
LR_MIN = 1e-5
EVAL_EVERY = 250
VAL_TOKENS = 100_000


def lr_at(step):
    if step < WARMUP:
        return LR * (step + 1) / WARMUP
    p = (step - WARMUP) / max(STEPS - WARMUP, 1)
    return LR_MIN + 0.5 * (LR - LR_MIN) * (1 + math.cos(math.pi * p))


def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(SRC)
    model = AutoModelForCausalLM.from_pretrained(SRC, dtype=torch.float32).to(DEVICE)

    train_ids = tokenize_wikitext(tok, "train")
    val_ids = tokenize_wikitext(tok, "validation", VAL_TOKENS)
    n_windows = train_ids.numel() // SEQ
    print(f"train tokens={train_ids.numel()} windows={n_windows}")
    windows = train_ids[: n_windows * SEQ].reshape(n_windows, SEQ)

    decay, no_decay = [], []
    for n, p in model.named_parameters():
        (no_decay if p.ndim < 2 else decay).append(p)
    opt = torch.optim.AdamW(
        [{"params": decay, "weight_decay": 0.01}, {"params": no_decay, "weight_decay": 0.0}],
        lr=LR, betas=(0.9, 0.95),
    )

    perm = torch.randperm(n_windows)
    cursor = 0
    log = []
    t0 = time.time()

    def save_weights():
        DST.mkdir(exist_ok=True)
        model.save_pretrained(DST, safe_serialization=True)
        if _args.force_head_dim:
            saved_cfg = json.loads((DST / "config.json").read_text())
            saved_cfg["head_dim"] = _args.force_head_dim
            (DST / "config.json").write_text(json.dumps(saved_cfg, indent=2))

    def evaluate(step, checkpoint=True):
        model.eval()
        r = strided_perplexity(model, val_ids, window=SEQ, stride=SEQ,
                               batch_windows=4, device=DEVICE)
        model.train()
        entry = {"step": step, "val_ppl": round(r["ppl"], 4),
                 "wall_s": round(time.time() - t0, 1)}
        log.append(entry)
        print(json.dumps(entry), flush=True)
        if checkpoint and step > 0:
            save_weights()
        torch.mps.empty_cache()

    evaluate(0)
    model.train()
    running = 0.0
    for step in range(STEPS):
        if cursor + BATCH > n_windows:
            perm = torch.randperm(n_windows)
            cursor = 0
        idx = perm[cursor : cursor + BATCH]
        cursor += BATCH
        batch = windows[idx].to(DEVICE)
        for g in opt.param_groups:
            g["lr"] = lr_at(step)
        out = model(batch, labels=batch)
        out.loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        opt.zero_grad(set_to_none=True)
        running += out.loss.item()
        del out
        if (step + 1) % 100 == 0:
            torch.mps.empty_cache()
        if (step + 1) % 50 == 0:
            print(f"step {step+1} loss {running/50:.4f} lr {lr_at(step):.2e} "
                  f"{(step+1)*BATCH*SEQ/(time.time()-t0):.0f} tok/s", flush=True)
            running = 0.0
        if (step + 1) % EVAL_EVERY == 0:
            evaluate(step + 1)

    del opt
    wall = time.time() - t0
    save_weights()
    import shutil
    for f in ["tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
              "generation_config.json"]:
        if (SRC / f).exists():
            shutil.copy(SRC / f, DST / f)

    save_json(
        {"steps": STEPS, "batch": BATCH, "seq": SEQ, "lr": LR, "lr_min": LR_MIN,
         "warmup": WARMUP, "tokens_seen": STEPS * BATCH * SEQ,
         "wall_seconds": round(wall, 1), "device": DEVICE, "dtype": "float32",
         "src": str(SRC), "dst": str(DST), "curve": log},
        RESULTS / _args.curve,
    )
    print(f"healing wall time: {wall/60:.1f} min; saved to {DST}")


if __name__ == "__main__":
    main()
