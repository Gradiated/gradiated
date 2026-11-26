"""Completion-only supervised fine-tuning with portable LoRA checkpoints."""

import argparse
import gzip
import hashlib
import json
import math
import random
import subprocess
import time
from pathlib import Path

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoModelForImageTextToText,
    AutoTokenizer,
)

TARGETS = {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}


def load(model, revision):
    kwargs = dict(revision=revision, dtype=torch.bfloat16, attn_implementation="sdpa")
    try:
        return AutoModelForCausalLM.from_pretrained(model, **kwargs)
    except (KeyError, ValueError):
        return AutoModelForImageTextToText.from_pretrained(model, **kwargs)


def read_examples(a, tokenizer):
    source = gzip.open(a.train, "rt") if a.train.suffix == ".gz" else a.train.open()
    with source:
        rows = [json.loads(line) for line in source]
    random.Random(a.seed).shuffle(rows)
    examples = []
    skipped = 0
    tokens = 0
    for row in rows:
        prefix, target = tokenizer(
            [row["prompt"], row["completion"]], add_special_tokens=False
        )["input_ids"]
        target.append(tokenizer.eos_token_id)
        if not prefix or len(prefix) + len(target) > a.max_len:
            skipped += 1
            continue
        tokens += len(prefix) + len(target)
        if a.token_limit and tokens > a.token_limit:
            break
        examples.append((prefix, target))
        if len(examples) >= a.examples:
            break
    if not examples:
        raise RuntimeError("no valid examples")
    return examples, skipped


def batches(data, budget, seed):
    order = list(range(len(data)))
    rng = random.Random(seed)
    rng.shuffle(order)
    result = []
    for lo in range(0, len(order), 512):
        group = sorted(order[lo : lo + 512], key=lambda i: sum(map(len, data[i])))
        pending = []
        longest = 0
        for i in group:
            length = sum(map(len, data[i]))
            if pending and max(longest, length) * (len(pending) + 1) > budget:
                result.append(pending)
                pending = []
                longest = 0
            pending.append(i)
            longest = max(longest, length)
        if pending:
            result.append(pending)
    rng.shuffle(result)
    return result


def fit_batch(data, indices, pad, model, head):
    width = max(sum(map(len, data[i])) for i in indices)
    shape = (len(indices), width)
    tokens = torch.full(shape, pad, dtype=torch.long)
    labels = torch.full(shape, -100, dtype=torch.long)
    keep = torch.zeros(shape, dtype=torch.long)
    count = 0
    supervised = 0
    for row, i in enumerate(indices):
        prefix, target = data[i]
        sequence = prefix + target
        tokens[row, : len(sequence)] = torch.tensor(sequence)
        labels[row, len(prefix) : len(sequence)] = torch.tensor(target)
        keep[row, : len(sequence)] = 1
        count += len(sequence)
        supervised += len(target)
    tokens, labels, keep = tokens.cuda(), labels.cuda(), keep.cuda()
    out = model(
        input_ids=tokens,
        attention_mask=keep,
        output_hidden_states=True,
        logits_to_keep=1,
    )
    targets = labels[:, 1:]
    mask = targets != -100
    hidden = out.hidden_states[-1][:, :-1][mask]
    loss = torch.nn.functional.cross_entropy(head(hidden).float(), targets[mask])
    loss.backward()
    return loss.item(), count, supervised


def checkpoint(a, model, opt, sched, progress):
    step = progress["step"]
    path = a.out / f"checkpoint-{step:06d}"
    path.mkdir(exist_ok=True)
    model.save_pretrained(path, safe_serialization=True)
    torch.save(
        dict(optimizer=opt.state_dict(), scheduler=sched.state_dict()),
        path / "optimizer.pt",
    )
    (path / "progress.json").write_text(json.dumps(progress, indent=2) + "\n")
    if a.persist:
        left = max(10, min(180, a.deadline - int(time.time()) - 10))
        subprocess.run(
            [
                "aws",
                "s3",
                "sync",
                "--quiet",
                str(path),
                f"{a.persist}/checkpoints/{path.name}/",
            ],
            timeout=left,
            check=True,
        )
        subprocess.run(
            [
                "aws",
                "s3",
                "cp",
                "--quiet",
                str(path / "progress.json"),
                f"{a.persist}/latest.json",
            ],
            timeout=25,
            check=True,
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--revision", required=True)
    p.add_argument("--train", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--deadline", type=int, required=True)
    p.add_argument("--persist", default="")
    p.add_argument("--resume", type=Path)
    p.add_argument("--examples", type=int, default=25_000)
    p.add_argument(
        "--token-limit",
        type=int,
        default=0,
        help="limit distinct prompt and target tokens before batching",
    )
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--lr", type=float, default=6e-5)
    p.add_argument("--max-len", type=int, default=4096)
    p.add_argument("--batch-tokens", type=int, default=8192)
    p.add_argument("--max-steps", type=int, default=0)
    a = p.parse_args()
    if a.batch_tokens < a.max_len or a.examples < 1 or a.token_limit < 0:
        p.error("provide a valid example count and token budgets")
    a.out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(a.seed)
    tokenizer = AutoTokenizer.from_pretrained(a.model, revision=a.revision)
    data, skipped = read_examples(a, tokenizer)
    plan = batches(data, a.batch_tokens, a.seed)
    if a.max_steps:
        plan = plan[: a.max_steps]
    identity = hashlib.sha256(a.train.read_bytes()).hexdigest()
    config = dict(
        model=a.model,
        revision=a.revision,
        train_sha256=identity,
        examples=len(data),
        seed=a.seed,
        max_len=a.max_len,
        batch_tokens=a.batch_tokens,
        token_limit=a.token_limit,
        lr=a.lr,
        steps=len(plan),
        available_prompt_tokens=sum(len(prefix) for prefix, _ in data),
        available_target_tokens=sum(len(target) for _, target in data),
    )
    (a.out / "spec.json").write_text(json.dumps(config, indent=2) + "\n")
    print(json.dumps(dict(event="tokenized", skipped=skipped, **config)), flush=True)
    model = load(a.model, a.revision)
    if a.resume:
        prior = json.loads((a.resume / "progress.json").read_text())
        if prior["config"] != config:
            raise ValueError("checkpoint does not match the frozen training plan")
        model = PeftModel.from_pretrained(model, a.resume, is_trainable=True)
    else:
        targets = [
            name
            for name, module in model.named_modules()
            if name.rsplit(".", 1)[-1] in TARGETS
            and isinstance(module, torch.nn.Linear)
            and "visual" not in name
            and "vision" not in name
        ]
        if not targets:
            raise ValueError("model has no eligible text projection modules")
        model = get_peft_model(
            model,
            LoraConfig(
                r=16,
                lora_alpha=32,
                target_modules=targets,
                bias="none",
                task_type="CAUSAL_LM",
            ),
        )
    model = model.cuda()
    model.gradient_checkpointing_enable(
        gradient_checkpointing_kwargs={"use_reentrant": False}
    )
    model.config.use_cache = False
    model.train()
    head = model.get_output_embeddings()
    params = [x for x in model.parameters() if x.requires_grad]
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0)
    warm = max(1, len(plan) // 30)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt,
        lambda step: (
            min(1, (step + 1) / warm)
            * 0.5
            * (1 + math.cos(math.pi * min(1, step / len(plan))))
        ),
    )
    step = 0
    tok = 0
    supervised = 0
    if a.resume:
        content = torch.load(
            a.resume / "optimizer.pt", map_location="cpu", weights_only=True
        )
        opt.load_state_dict(content["optimizer"])
        sched.load_state_dict(content["scheduler"])
        step = prior["step"]
        tok = prior["tokens"]
        supervised = prior["supervised_tokens"]
    started = time.time()
    last_checkpoint = started
    pad = (
        tokenizer.pad_token_id
        if tokenizer.pad_token_id is not None
        else tokenizer.eos_token_id
    )
    last_saved = -1
    while step < len(plan) and time.time() < a.deadline - 330:
        opt.zero_grad(set_to_none=True)
        loss, used, targets = fit_batch(data, plan[step], pad, model, head)
        torch.nn.utils.clip_grad_norm_(params, 1.0, error_if_nonfinite=True)
        opt.step()
        sched.step()
        step += 1
        tok += used
        supervised += targets
        progress = dict(
            config=config, step=step, tokens=tok, supervised_tokens=supervised
        )
        if step % 20 == 0 or step == 1:
            print(
                json.dumps(
                    dict(
                        event="step",
                        step=step,
                        loss=round(loss, 4),
                        tokens=tok,
                        supervised_tokens=supervised,
                        seconds=round(time.time() - started, 2),
                    )
                ),
                flush=True,
            )
        if time.time() - last_checkpoint > 600:
            checkpoint(a, model, opt, sched, progress)
            last_checkpoint = time.time()
            last_saved = step
    if not step:
        raise RuntimeError("deadline before any optimizer steps")
    progress = dict(config=config, step=step, tokens=tok, supervised_tokens=supervised)
    if last_saved != step:
        checkpoint(a, model, opt, sched, progress)
    merged = model.merge_and_unload()
    merged.config.use_cache = True
    merged.save_pretrained(a.out / "merged", safe_serialization=True)
    tokenizer.save_pretrained(a.out / "merged")
    (a.out / "train_meta.json").write_text(
        json.dumps(
            dict(
                **progress,
                complete=step == len(plan),
                useful_gpu_seconds=round(time.time() - started, 2),
            ),
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(dict(event="train_finished", step=step, complete=step == len(plan))),
        flush=True,
    )


if __name__ == "__main__":
    main()
