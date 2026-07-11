"""Wikitext-2 sliding-window perplexity for a local HF checkpoint.

Usage: python eval_ppl.py --model <dir> [--split test] [--window 1024] [--stride 512]
                          [--max-tokens N] [--device mps] [--dtype float32] [--tag name]
"""

import argparse
import json
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import RESULTS, save_json, strided_perplexity, tokenize_wikitext


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--window", type=int, default=1024)
    ap.add_argument("--stride", type=int, default=512)
    ap.add_argument("--max-tokens", type=int, default=None)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--dtype", default="float32")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=getattr(torch, args.dtype)
    ).to(args.device)
    ids = tokenize_wikitext(tok, args.split, args.max_tokens)
    print(f"{args.model}: {ids.numel()} tokens ({args.split})")

    t0 = time.time()
    res = strided_perplexity(model, ids, window=args.window, stride=args.stride, device=args.device)
    res.update(
        model=args.model,
        split=args.split,
        dtype=args.dtype,
        device=args.device,
        total_tokens=ids.numel(),
        wall_seconds=round(time.time() - t0, 1),
    )
    print(json.dumps(res, indent=2))
    if args.tag:
        save_json(res, RESULTS / f"ppl_{args.tag}.json")


if __name__ == "__main__":
    main()
