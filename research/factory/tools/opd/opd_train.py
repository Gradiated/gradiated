"""One on-policy distillation update of the Qwen LoRA from a scored round (opd_sample_score.py output).

Per student token with a teacher signal, the advantage is the teacher-minus-student span logprob share from the
cross-tokenizer aligner; tokens without one are masked. The loss is the clipped policy-gradient surrogate
-min(r A, clip(r, 1-eps, 1+eps) A) with r = pi_theta / pi_sampler, summed over tokens and divided by the global
number of scored tokens, so one minibatch step is the reverse-KL gradient on the student's own samples.
The LoRA matches the root-agent SFT trainer (rank 16, alpha 32, all linear layers). AdamW state carries across rounds.

    CUDA_VISIBLE_DEVICES=5,6,7 accelerate launch --num_processes 3 opd_train.py --batch round-000.jsonl \\
        --adapter-out runs/opd/adapters/001 [--adapter-in runs/opd/adapters/000]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch
from accelerate import Accelerator
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import AutoModelForCausalLM

MODEL = "/opt/posthog-sft/models/Qwen3.8-27B"


def load_rows(paths: list[str], max_length: int) -> list[dict]:
    rows = []
    for path in paths:
        for line in open(path):
            r = json.loads(line)
            if r.get("status") != "ok" or not r.get("covered"):
                continue
            ids = r["prompt_token_ids"] + r["token_ids"]
            if len(ids) > max_length:
                continue
            rows.append({
                "input_ids": ids, "start": len(r["prompt_token_ids"]),
                "advantages": [0.0 if a is None else a for a in r["advantages"]],
                "mask": [a is not None for a in r["advantages"]],
                "old": r["sampler_logprobs"],
            })
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--batch", nargs="+", required=True)
    p.add_argument("--adapter-in")
    p.add_argument("--adapter-out", required=True)
    p.add_argument("--lr", type=float, default=5e-5)
    p.add_argument("--minibatches", type=int, default=2, help="optimizer steps per round")
    p.add_argument("--clip", type=float, default=0.2)
    p.add_argument("--max-length", type=int, default=34500)
    p.add_argument("--max-grad-norm", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    accelerator = Accelerator()
    rank, world = accelerator.process_index, accelerator.num_processes
    rows = load_rows(args.batch, args.max_length)
    random.Random(args.seed).shuffle(rows)

    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, attn_implementation="sdpa")
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    if args.adapter_in:
        model = PeftModel.from_pretrained(model, args.adapter_in, is_trainable=True)
    else:
        lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.0, target_modules="all-linear",
                          exclude_modules=r".*(visual|vision|mtp).*", task_type="CAUSAL_LM")
        model = get_peft_model(model, lora)
    model.train()  # gradient checkpointing only applies in training mode; from_pretrained returns eval mode
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=args.lr, betas=(0.9, 0.999), weight_decay=0.0)
    state_in = Path(args.adapter_in) / "optimizer.pt" if args.adapter_in else None
    if state_in and state_in.exists():
        optimizer.load_state_dict(torch.load(state_in, map_location="cpu", weights_only=False))
    model, optimizer = accelerator.prepare(model, optimizer)
    device = accelerator.device

    started = time.time()
    chunks = [rows[i::args.minibatches] for i in range(args.minibatches)]
    log = []
    for step, chunk in enumerate(chunks):
        total = sum(sum(r["mask"]) for r in chunk)  # global count of scored tokens in this minibatch
        mine = chunk[rank::world]
        per_rank = math.ceil(len(chunk) / world)  # equal backward counts on every rank keep DDP in step
        sums = torch.zeros(5, device=device)  # loss, ratio sum, clipped count, token count, rows
        for i in range(per_rank):
            dummy = i >= len(mine)
            r = mine[i % len(mine)] if mine else chunk[0]
            ids = torch.tensor([r["input_ids"]], device=device)
            start, n = r["start"], len(r["advantages"])
            keep = torch.zeros_like(ids, dtype=torch.bool)
            keep[0, start - 1 : start - 1 + n] = True  # hidden states that predict the completion tokens
            sync = i == per_rank - 1
            context = accelerator.no_sync(model) if not sync else torch.enable_grad()
            with context:
                out = model(input_ids=ids, logits_to_keep=keep, use_cache=False)
                logp = torch.log_softmax(out.logits.reshape(-1, out.logits.shape[-1]).float(), dim=-1)
                targets = ids[0, start : start + n]
                new = logp.gather(1, targets[:, None])[:, 0]
                adv = torch.tensor(r["advantages"], device=device)
                mask = torch.tensor(r["mask"], device=device, dtype=torch.float32)
                ratio = torch.exp(new - torch.tensor(r["old"], device=device))
                surrogate = torch.minimum(ratio * adv, ratio.clamp(1 - args.clip, 1 + args.clip) * adv)
                loss = -(surrogate * mask).sum() / max(1, total) * world  # DDP averages gradients over ranks
                if dummy:
                    loss = loss * 0.0
                accelerator.backward(loss)
            if not dummy:
                with torch.no_grad():
                    clipped = ((ratio - 1).abs() > args.clip).float()
                    sums += torch.stack([loss.detach() / world, (ratio * mask).sum(), (clipped * mask).sum(), mask.sum(),
                                         torch.tensor(1.0, device=device)])
        norm = accelerator.clip_grad_norm_(params, args.max_grad_norm)
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        sums = accelerator.reduce(sums, reduction="sum")
        record = {"step": step, "rows": int(sums[4]), "tokens": int(sums[3]), "loss": float(sums[0]),
                  "mean_ratio": float(sums[1] / sums[3].clamp(min=1)), "clip_frac": float(sums[2] / sums[3].clamp(min=1)),
                  "grad_norm": float(norm), "seconds": round(time.time() - started)}
        log.append(record)
        if accelerator.is_main_process:
            print(json.dumps(record), flush=True)

    accelerator.wait_for_everyone()
    if accelerator.is_main_process:
        out = Path(args.adapter_out)
        accelerator.unwrap_model(model).save_pretrained(str(out))
        torch.save(optimizer.state_dict(), out / "optimizer.pt")
        (out / "train_log.json").write_text(json.dumps({"args": vars(args), "rows": len(rows), "log": log}, indent=1))
    accelerator.wait_for_everyone()


if __name__ == "__main__":
    main()
