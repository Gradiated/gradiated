"""Shared utilities for the functional-twin surgery experiments."""

import json
import math
import time
from pathlib import Path

import pandas as pd
import torch

SARTOR = Path("/Users/js/dev/sartor")
DATA = SARTOR / "data"
MODELS = SARTOR / "models"
RESULTS = SARTOR / "experiments" / "results" / "twin"


def load_wikitext_text(split: str) -> str:
    df = pd.read_parquet(DATA / f"wikitext2-{split}.parquet")
    return "\n\n".join(df["text"].tolist())


def tokenize_wikitext(tokenizer, split: str, max_tokens: int | None = None) -> torch.Tensor:
    ids = tokenizer(load_wikitext_text(split), return_tensors="pt").input_ids[0]
    if max_tokens is not None:
        ids = ids[:max_tokens]
    return ids


@torch.no_grad()
def strided_perplexity(
    model,
    input_ids: torch.Tensor,
    window: int = 1024,
    stride: int = 512,
    batch_windows: int = 8,
    device: str = "mps",
) -> dict:
    """Standard sliding-window perplexity (HF protocol).

    Windows of `window` tokens advance by `stride`; loss is scored only on the
    final `stride` tokens of each window (full window for the first), so every
    token is scored exactly once with >= (window - stride) tokens of context.
    """
    model.eval()
    seq_len = input_ids.numel()
    spans = []  # (begin, end, trg_len)
    prev_end = 0
    for begin in range(0, seq_len - 1, stride):
        end = min(begin + window, seq_len)
        spans.append((begin, end, end - prev_end))
        prev_end = end
        if end == seq_len:
            break

    nll_sum, n_tokens = 0.0, 0
    t0 = time.time()
    for i in range(0, len(spans), batch_windows):
        chunk = spans[i : i + batch_windows]
        w = max(end - begin for begin, end, _ in chunk)
        batch = torch.full((len(chunk), w), 0, dtype=torch.long)
        tgt = torch.full((len(chunk), w), -100, dtype=torch.long)
        for j, (begin, end, trg_len) in enumerate(chunk):
            ids = input_ids[begin:end]
            batch[j, : end - begin] = ids
            tgt[j, end - begin - trg_len : end - begin] = ids[-trg_len:]
        batch, tgt = batch.to(device), tgt.to(device)
        logits = model(batch).logits.float()
        shift_logits = logits[:, :-1].reshape(-1, logits.size(-1))
        shift_tgt = tgt[:, 1:].reshape(-1)
        losses = torch.nn.functional.cross_entropy(
            shift_logits, shift_tgt, ignore_index=-100, reduction="sum"
        )
        nll_sum += losses.item()
        n_tokens += (shift_tgt != -100).sum().item()

    return {
        "ppl": math.exp(nll_sum / n_tokens),
        "nll_per_token": nll_sum / n_tokens,
        "n_scored_tokens": n_tokens,
        "window": window,
        "stride": stride,
        "eval_seconds": round(time.time() - t0, 1),
    }


def save_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))
    print(f"wrote {path}")
