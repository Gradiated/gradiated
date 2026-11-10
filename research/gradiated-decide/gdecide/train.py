"""LoRA post-training of a Decider-protocol checkpoint (non-causal full attention, per-question marker readout).

    torchrun --nproc-per-node 8 -m gdecide.train --checkpoint CKPT --data train.jsonl --out RUN_DIR [options]

Training rows are Decisions-API requests with targets:
    {"state": ..., "questions": {key: question}, "expected": {key: option_key | {option_key: probability}},
     "source": "<dataset name>"}
``expected`` may omit questions that are not scored. Option keys follow ``pplx_decider.protocol.options``: the
criteria keys for ``choice``, ``"0".."n-1"`` for ``score`` and ``"false"/"true"`` for ``noul`` (a float is read as
P(true)). The loss is the cross entropy of each scored readout over its valid options, optionally plus a KL anchor
to the frozen starting model (the adapter disabled), which limits drift on skills the new data does not cover.

Resumable: the newest ``step-*`` directory under ``--out`` (adapter, readout, optimizer and data position) is
loaded on start. Only rank 0 writes checkpoints.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from pathlib import Path

LORA_TARGETS = r".*language_model.*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj|in_proj_qkvz|in_proj_ba|in_proj_qkv|in_proj_z|in_proj_a|in_proj_b|out_proj)$"


def target_distribution(question: dict, expected) -> list[float] | None:
    from pplx_decider.protocol import options

    keys, _ = options(question)
    if expected is None:
        return None
    if question["type"] == "noul" and isinstance(expected, (int, float)) and not isinstance(expected, bool):
        p = float(expected)
        return [1 - p, p]
    if isinstance(expected, bool):
        expected = "true" if expected else "false"
    if isinstance(expected, dict):
        total = sum(float(expected.get(k, 0)) for k in keys)
        return [float(expected.get(k, 0)) / total for k in keys] if total > 0 else None
    expected = str(expected)
    if expected not in keys:
        return None
    return [1.0 if k == expected else 0.0 for k in keys]


def encode_rows(path: str, encoder, max_length: int, rank: int, world: int, seed: int):
    """Tokenize this rank's share of the rows. Rows longer than ``max_length`` or without a target are dropped."""
    import torch

    examples, dropped = [], 0
    with open(path) as f:
        for i, line in enumerate(f):
            if i % world != rank:
                continue
            row = json.loads(line)
            request = {"state": row["state"], "questions": row["questions"]}
            try:
                encoder.validate(request)
                encoded = encoder.encode(request)
            except Exception:
                dropped += 1
                continue
            if encoded.length > max_length:
                dropped += 1
                continue
            targets = []
            for key, question in row["questions"].items():
                targets.append(target_distribution(question, row.get("expected", {}).get(key)))
            if all(t is None for t in targets):
                dropped += 1
                continue
            examples.append({"ids": encoded.input_ids, "markers": encoded.markers, "counts": encoded.counts, "targets": targets, "source": row.get("source", "?"), "weight": float(row.get("weight", 1.0))})
    random.Random(seed + rank).shuffle(examples)
    return examples, dropped


def batches(examples: list[dict], budget: int, seed: int, epoch: int):
    """Token-budget batches: shuffle, sort within windows of 256 by length, pack while padded width * n <= budget."""
    rng = random.Random(seed * 1000 + epoch)
    order = list(range(len(examples)))
    rng.shuffle(order)
    out = []
    for w in range(0, len(order), 256):
        window = sorted(order[w : w + 256], key=lambda i: examples[i]["ids"].numel())
        group, width = [], 0
        for i in window:
            n = examples[i]["ids"].numel()
            if group and max(width, n) * (len(group) + 1) > budget:
                out.append(group)
                group, width = [], 0
            group.append(i)
            width = max(width, n)
        if group:
            out.append(group)
    rng.shuffle(out)
    return out


def collate(examples: list[dict], pad_id: int):
    import torch

    width = max(e["ids"].numel() for e in examples)
    ids = torch.full((len(examples), width), pad_id, dtype=torch.long)
    mask = torch.zeros((len(examples), width), dtype=torch.long)
    rows, cols, counts, targets, weights = [], [], [], [], []
    for b, e in enumerate(examples):
        n = e["ids"].numel()
        ids[b, width - n :] = e["ids"]
        mask[b, width - n :] = 1
        for j, (count, target) in enumerate(zip(e["counts"], e["targets"], strict=True)):
            if target is None:
                continue
            rows.append(b)
            cols.append(int(e["markers"][j]) + width - n)
            counts.append(count)
            targets.append(target)
            weights.append(e["weight"])
    return ids, mask, rows, cols, counts, targets, weights


def readout_loss(logits, counts, targets, weights, anchor=None, anchor_weight=0.0):
    """Mean weighted cross entropy over valid options (soft targets), plus an optional KL(anchor || model)."""
    import torch

    losses, kls = [], []
    for i, (count, target) in enumerate(zip(counts, targets, strict=True)):
        logp = torch.log_softmax(logits[i, :count].float(), -1)
        t = torch.tensor(target, device=logp.device, dtype=torch.float32)
        losses.append(-(t * logp).sum() * weights[i])
        if anchor is not None and anchor_weight > 0:
            q = torch.log_softmax(anchor[i, :count].float(), -1)
            kls.append((q.exp() * (q - logp)).sum())
    loss = torch.stack(losses).sum() / max(1e-6, sum(weights))
    kl = torch.stack(kls).mean() if kls else torch.zeros((), device=loss.device)
    return loss + anchor_weight * kl, loss.detach(), kl.detach()


def latest_step(out: Path) -> Path | None:
    steps = sorted(out.glob("step-*"), key=lambda p: int(p.name.split("-")[1]))
    steps = [p for p in steps if (p / "done").exists()]
    return steps[-1] if steps else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--dev", help="held-out rows in the same format; loss reported per source")
    parser.add_argument("--out", required=True)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--readout-lr", type=float, default=1e-5)
    parser.add_argument("--rank", type=int, default=32)
    parser.add_argument("--alpha", type=int, default=64)
    parser.add_argument("--dropout", type=float, default=0.0)
    parser.add_argument("--tokens-per-batch", type=int, default=16384)
    parser.add_argument("--accumulate", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=8192)
    parser.add_argument("--warmup", type=int, default=50)
    parser.add_argument("--anchor", type=float, default=0.0, help="weight of KL to the starting model")
    parser.add_argument("--save-every", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261110)
    args = parser.parse_args()

    import torch
    import torch.distributed as dist
    from peft import LoraConfig, get_peft_model, set_peft_model_state_dict
    from safetensors.torch import load_file, save_file

    from pplx_decider import Decider

    dist.init_process_group("nccl")
    rank, world = dist.get_rank(), dist.get_world_size()
    local = int(os.environ.get("LOCAL_RANK", 0))
    torch.cuda.set_device(local)
    device = torch.device("cuda", local)
    torch.manual_seed(args.seed)
    out = Path(args.out)
    if rank == 0:
        out.mkdir(parents=True, exist_ok=True)
        (out / "args.json").write_text(json.dumps(vars(args), indent=2))

    decider = Decider.from_pretrained(args.checkpoint, device=str(device), max_length=args.max_length)
    encoder = decider.encoder
    backbone = decider.backbone
    readout = decider.readout
    config = LoraConfig(r=args.rank, lora_alpha=args.alpha, lora_dropout=args.dropout, target_modules=LORA_TARGETS, bias="none")
    backbone = get_peft_model(backbone, config)
    backbone.base_model.model.language_model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    backbone.train()
    readout.requires_grad_(True).train()
    lora_params = [p for p in backbone.parameters() if p.requires_grad]
    if rank == 0:
        print(json.dumps({"lora_parameters": sum(p.numel() for p in lora_params), "modules": len({n.rsplit('.lora_', 1)[0] for n, _ in backbone.named_parameters() if 'lora_' in n})}), flush=True)

    examples, dropped = encode_rows(args.data, encoder, args.max_length, rank, world, args.seed)
    dev, _ = encode_rows(args.dev, encoder, args.max_length, rank, world, args.seed) if args.dev else ([], 0)
    counts = torch.tensor([len(examples), dropped], device=device)
    dist.all_reduce(counts)
    epoch_batches = batches(examples, args.tokens_per_batch, args.seed, 0)
    n = torch.tensor([len(epoch_batches)], device=device)
    dist.all_reduce(n, op=dist.ReduceOp.MIN)
    per_epoch = int(n.item()) // args.accumulate
    total_steps = max(1, int(per_epoch * args.epochs))
    if rank == 0:
        print(json.dumps({"examples": int(counts[0]), "dropped": int(counts[1]), "steps_per_epoch": per_epoch, "total_steps": total_steps}), flush=True)

    optimizer = torch.optim.AdamW([{"params": lora_params, "lr": args.lr}, {"params": list(readout.parameters()), "lr": args.readout_lr}], weight_decay=0.0, betas=(0.9, 0.99))

    def schedule(step):
        if step < args.warmup:
            return (step + 1) / args.warmup
        progress = (step - args.warmup) / max(1, total_steps - args.warmup)
        return 0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1.0, progress)))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, schedule)
    step = 0
    resume = latest_step(out)
    if resume:
        set_peft_model_state_dict(backbone, load_file(str(resume / "adapter_model.safetensors")))
        readout.load_state_dict(load_file(str(resume / "readout.safetensors")))
        state = torch.load(resume / f"optimizer-{rank}.pt", map_location=device, weights_only=False)
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        step = state["step"]
        if rank == 0:
            print(json.dumps({"resumed": str(resume), "step": step}), flush=True)

    trainable = lora_params + list(readout.parameters())

    def forward(batch, with_anchor):
        ids, mask, rows, cols, cnts, targets, weights = batch
        ids, mask = ids.to(device), mask.to(device)
        hidden = backbone(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state
        r = torch.tensor(rows, device=device)
        c = torch.tensor(cols, device=device)
        logits = readout(hidden[r, c])
        anchor = None
        if with_anchor:
            with torch.no_grad(), backbone.disable_adapter():
                base_hidden = backbone(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state
                anchor = decider_readout0(base_hidden[r, c])
        return readout_loss(logits, cnts, targets, weights, anchor, args.anchor)

    readout0 = torch.nn.Linear(readout.in_features, readout.out_features, bias=False, dtype=readout.weight.dtype, device=device)
    readout0.load_state_dict(load_file(str(Path(decider.checkpoint) / "readout.safetensors")))
    readout0.requires_grad_(False)
    decider_readout0 = readout0

    def evaluate_dev():
        if not args.dev:
            return {}
        backbone.eval()
        sums: dict[str, list[float]] = {}
        with torch.no_grad():
            for group in batches(dev, args.tokens_per_batch, args.seed, 999):
                for e in (dev[i] for i in group):
                    one = collate([e], encoder.pad_id)
                    if not one[2]:
                        continue
                    _, ce, _ = forward(one, False)
                    s = sums.setdefault(e["source"], [0.0, 0.0])
                    s[0] += float(ce)
                    s[1] += 1
        backbone.train()
        gathered = [None] * world
        dist.all_gather_object(gathered, sums)
        merged: dict[str, list[float]] = {}
        for g in gathered:
            for k, (a, b) in g.items():
                m = merged.setdefault(k, [0.0, 0.0])
                m[0] += a
                m[1] += b
        return {k: round(a / b, 4) for k, (a, b) in sorted(merged.items()) if b}

    def save(step):
        target = out / f"step-{step}"
        if rank == 0:
            target.mkdir(parents=True, exist_ok=True)
            backbone.save_pretrained(str(target))
            save_file({k: v.contiguous() for k, v in readout.state_dict().items()}, str(target / "readout.safetensors"))
        dist.barrier()
        torch.save({"optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(), "step": step}, target / f"optimizer-{rank}.pt")
        dist.barrier()
        if rank == 0:
            (target / "done").write_text(json.dumps({"step": step, "time": time.time()}))

    epoch = step // max(1, per_epoch)
    position = (step % max(1, per_epoch)) * args.accumulate
    started = time.perf_counter()
    tokens = 0
    while step < total_steps:
        epoch_batches = batches(examples, args.tokens_per_batch, args.seed, epoch)[: per_epoch * args.accumulate]
        while position < len(epoch_batches) and step < total_steps:
            optimizer.zero_grad(set_to_none=True)
            ce_sum = kl_sum = 0.0
            for micro in range(args.accumulate):
                items = [examples[i] for i in epoch_batches[position + micro]]
                batch = collate(items, encoder.pad_id)
                tokens += int(batch[1].sum())
                if not batch[2]:
                    continue
                loss, ce, kl = forward(batch, args.anchor > 0)
                (loss / args.accumulate).backward()
                ce_sum += float(ce) / args.accumulate
                kl_sum += float(kl) / args.accumulate
            position += args.accumulate
            for p in trainable:
                if p.grad is not None:
                    dist.all_reduce(p.grad, op=dist.ReduceOp.AVG)
            norm = torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()
            scheduler.step()
            step += 1
            if step % 10 == 0:
                stats = torch.tensor([ce_sum, kl_sum, tokens], device=device, dtype=torch.float64)
                dist.all_reduce(stats)
                if rank == 0:
                    elapsed = time.perf_counter() - started
                    print(json.dumps({"step": step, "of": total_steps, "ce": round(stats[0].item() / world, 4), "kl": round(stats[1].item() / world, 4), "grad_norm": round(float(norm), 3), "lr": scheduler.get_last_lr()[0], "tokens_per_s": round(stats[2].item() / elapsed), "elapsed_s": round(elapsed)}), flush=True)
            if step % args.save_every == 0 or step == total_steps:
                save(step)
                report = evaluate_dev()
                if rank == 0 and report:
                    print(json.dumps({"step": step, "dev_ce": report}), flush=True)
                    (out / f"step-{step}" / "dev.json").write_text(json.dumps(report, indent=2))
        epoch += 1
        position = 0
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
