"""Full fine-tuning of a Decider-protocol checkpoint with FSDP2 (fp32 master weights, bf16 compute).

    torchrun --nproc-per-node 8 -m gdecide.train_full --checkpoint CKPT --data DATA_DIR --out RUN_DIR [options]

``DATA_DIR`` comes from ``gdecide.prepare``. Trainable: every language-model layer, the final norm and the
readout head; the token embeddings and the vision tower stay frozen. Loss: soft cross entropy over each scored
question's valid options plus ``--brier`` times the multiclass Brier score, plus ``--anchor`` times
KL(base || model) to a frozen bf16 copy of the starting checkpoint on the same inputs. Non-causal full attention is the
upstream forward hook, so training sees exactly the inference computation.

Spot-safe: ``state-<step>/`` (sharded model and optimizer, torch.distributed.checkpoint) is written every
``--state-minutes`` and the newest complete one is resumed. ``export-<step>/`` is a loadable bf16 checkpoint
(the base checkpoint's files with new weights and readout) written every ``--export-every`` steps and at the end.
The launcher syncs ``RUN_DIR`` to S3; this process only writes locally and marks each directory complete with
a ``done`` file once every rank has finished writing it.

``--family gemma`` trains a KnowLine (Gemma 4) checkpoint on data from ``gdecide.prepare --family gemma`` (one causal
prompt per question). The readout is KnowLine's: the rows of the tied output embedding for the option labels (frozen
with the embeddings, as a buffer), then the checkpoint's final-logit soft-cap, at the last prompt token. Attention is
Gemma's own causal / sliding-window masking; batches are right-padded, so no mask or position hook is needed.
Trainable: every language-model layer and the final norm (which carries part of the folded readout temperature);
the embeddings, vision tower and vision projection stay frozen. Exports keep the checkpoint's key names and its
non-weight files (KnowLine's front end and temperatures), so they load in ``gdecide.evaluate --backend knowline``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import time
from pathlib import Path


def batches(lengths: list[int], budget: int, seed: int, epoch: int) -> list[list[int]]:
    rng = random.Random(seed * 1000 + epoch)
    order = list(range(len(lengths)))
    rng.shuffle(order)
    out = []
    for w in range(0, len(order), 512):
        window = sorted(order[w : w + 512], key=lengths.__getitem__)
        group, width = [], 0
        for i in window:
            if group and max(width, lengths[i]) * (len(group) + 1) > budget:
                out.append(group)
                group, width = [], 0
            group.append(i)
            width = max(width, lengths[i])
        if group:
            out.append(group)
    rng.shuffle(out)
    return out


def collate(examples, pad_id, right=False):
    """Left-padded (Decider) or, with ``right``, right-padded (causal Gemma) batch."""
    import torch

    width = max(int(e["ids"].numel()) for e in examples)
    ids = torch.full((len(examples), width), pad_id, dtype=torch.long)
    mask = torch.zeros((len(examples), width), dtype=torch.long)
    rows, cols, counts, targets, weights = [], [], [], [], []
    for b, e in enumerate(examples):
        n = int(e["ids"].numel())
        start = 0 if right else width - n
        ids[b, start : start + n] = e["ids"].long()
        mask[b, start : start + n] = 1
        for j, (count, target) in enumerate(zip(e["counts"], e["targets"], strict=True)):
            if target is None:
                continue
            rows.append(b)
            cols.append(int(e["markers"][j]) + start)
            counts.append(int(count))
            targets.append(target)
            weights.append(float(e["weight"]))
    return ids, mask, rows, cols, counts, targets, weights


def losses(logits, counts, targets, weights, brier, anchor=None, anchor_weight=0.0):
    """Per-question soft CE, Brier and optional KL(anchor || model) over valid options, as a dense block."""
    import torch

    n, width = len(counts), max(counts)
    valid = torch.arange(width, device=logits.device)[None, :] < torch.tensor(counts, device=logits.device)[:, None]
    t = torch.zeros((n, width), device=logits.device)
    for i, target in enumerate(targets):
        t[i, : len(target)] = torch.tensor(target, device=logits.device)
    z = logits[:, :width].float().masked_fill(~valid, float("-inf"))
    logp = torch.log_softmax(z, -1)
    w = torch.tensor(weights, device=logits.device)
    ce = -(t * logp.masked_fill(~valid, 0)).sum(-1)
    br = ((logp.exp() - t) ** 2).masked_fill(~valid, 0).sum(-1)
    kl = torch.zeros_like(ce)
    if anchor is not None:
        q = torch.log_softmax(anchor[:, :width].float().masked_fill(~valid, float("-inf")), -1)
        kl = (q.exp() * (q - logp)).masked_fill(~valid, 0).sum(-1)
    total = ((ce + brier * br + anchor_weight * kl) * w).sum() / w.sum().clamp_min(1e-6)
    return total, (ce * w).sum().detach(), (br * w).sum().detach(), w.sum().detach(), (kl * w).sum().detach()


def complete(path: Path) -> bool:
    return (path / "done").exists()


def gemma_label_logits(hidden, label_weight, softcap):
    """KnowLine's readout at the selected positions: label rows of the tied output embedding in fp32, then the cap."""
    import torch

    z = hidden.float() @ label_weight.T
    return z if softcap is None else torch.tanh(z / softcap) * softcap


def build_gemma(checkpoint: Path, dtype, device_index: int, label_ids: list[int], attn: str = "sdpa"):
    """Gemma 4 backbone (no LM head) plus KnowLine's frozen label readout, as a module with the Decider signature."""
    import torch
    from transformers.models.gemma4.modeling_gemma4 import Gemma4Model

    class GemmaDecider(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = Gemma4Model.from_pretrained(str(checkpoint), dtype=dtype, attn_implementation=attn, device_map={"": device_index})
            weight = self.backbone.language_model.embed_tokens.weight
            index = torch.tensor(label_ids, device=weight.device)
            self.register_buffer("label_weight", weight.detach()[index].float().clone(), persistent=False)
            self.softcap = self.backbone.config.get_text_config().final_logit_softcapping

        def forward(self, ids, mask, rows, cols):
            hidden = self.backbone.language_model(input_ids=ids, use_cache=False).last_hidden_state
            return gemma_label_logits(hidden[rows, cols], self.label_weight, self.softcap)

    return GemmaDecider()


def freeze_gemma(backbone) -> None:
    backbone.requires_grad_(False)
    backbone.language_model.layers.requires_grad_(True)
    backbone.language_model.norm.requires_grad_(True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--lr", type=float, default=3e-6)
    parser.add_argument("--readout-lr", type=float, default=1e-5)
    parser.add_argument("--min-lr-ratio", type=float, default=0.1)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--brier", type=float, default=0.5)
    parser.add_argument("--anchor", type=float, default=0.0, help="weight of KL(base || model) on the training inputs")
    parser.add_argument("--tokens-per-batch", type=int, default=32768, help="padded tokens per micro-batch per GPU")
    parser.add_argument("--accumulate", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=30)
    parser.add_argument("--state-minutes", type=float, default=40)
    parser.add_argument("--export-every", type=int, default=0, help="steps between bf16 exports (0: only at the end)")
    parser.add_argument("--dev-every", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261110)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--family", choices=("qwen", "gemma"), default="qwen", help="qwen: Decider checkpoints; gemma: KnowLine")
    # Speed options. None changes the optimisation maths; --compile and --attn change only kernel rounding.
    parser.add_argument("--keep-activations", type=int, default=0, help="layers (spread evenly) that store activations instead of recomputing them")
    parser.add_argument("--no-reshard", action="store_true", help="keep each layer's gathered bf16 weights from forward to backward")
    parser.add_argument("--compile", action="store_true", help="torch.compile each decoder layer")
    parser.add_argument("--attn", default="sdpa", help="gemma only: transformers attn_implementation (sdpa, flex_attention, ...)")
    parser.add_argument("--profile", action="store_true", help="write a torch.profiler table for steps 4-6 (rank 0) to OUT/profile.txt")
    parser.add_argument("--bench", action="store_true", help="throughput run: no dev evaluation, state or export")
    args = parser.parse_args()
    gemma = args.family == "gemma"

    import torch
    import torch.distributed as dist
    import torch.distributed.checkpoint as dcp
    from safetensors.torch import load_file, save_file
    from torch.distributed.checkpoint.state_dict import StateDictOptions, get_model_state_dict, get_optimizer_state_dict, set_optimizer_state_dict, set_model_state_dict
    from torch.distributed.fsdp import MixedPrecisionPolicy, fully_shard
    if gemma:
        from gdecide.backends.knowline import Renderer

        label_ids = Renderer(str(args.checkpoint)).label_ids
        MAX_OPTIONS = len(label_ids)
    else:
        from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5Model

        from pplx_decider.model import enable_noncausal_full_attention
        from pplx_decider.protocol import MAX_OPTIONS

    dist.init_process_group("nccl")
    rank, world = dist.get_rank(), dist.get_world_size()
    local = int(os.environ.get("LOCAL_RANK", 0))
    torch.cuda.set_device(local)
    device = torch.device("cuda", local)
    torch.manual_seed(args.seed)
    torch.backends.cuda.enable_cudnn_sdp(False)
    out = Path(args.out)
    checkpoint = Path(args.checkpoint)
    if rank == 0:
        out.mkdir(parents=True, exist_ok=True)
        (out / "args.json").write_text(json.dumps(vars(args), indent=2))

    def log(**kw):
        if rank == 0:
            line = json.dumps({"time": round(time.time()), **kw})
            print(line, flush=True)
            with (out / "train.log.jsonl").open("a") as f:
                f.write(line + "\n")

    class Model(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = Qwen3_5Model.from_pretrained(str(checkpoint), dtype=torch.float32, attn_implementation="sdpa", device_map={"": local})
            hidden = self.backbone.config.text_config.hidden_size
            self.readout = torch.nn.Linear(hidden, MAX_OPTIONS, bias=False, dtype=torch.float32, device=device)
            self.readout.load_state_dict({k: v.float() for k, v in load_file(str(checkpoint / "readout.safetensors")).items()})

        def forward(self, ids, mask, rows, cols):
            hidden = self.backbone(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state
            return self.readout(hidden[rows, cols])

    model = build_gemma(checkpoint, torch.float32, local, label_ids, args.attn) if gemma else Model()
    text = model.backbone.language_model
    if gemma:
        freeze_gemma(model.backbone)
    else:
        enable_noncausal_full_attention(text)
        text.embed_tokens.requires_grad_(False)
        model.backbone.visual.requires_grad_(False)
    model.backbone.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.backbone.config.use_cache = False
    layers = list(text.layers)
    if args.keep_activations:
        keep = {round(i * len(layers) / args.keep_activations) for i in range(min(args.keep_activations, len(layers)))}
        for i in keep:
            layers[i].gradient_checkpointing = False
    if args.compile:
        for layer in layers:
            layer.compile()
    policy = MixedPrecisionPolicy(param_dtype=torch.bfloat16, reduce_dtype=torch.float32)
    for layer in layers:
        fully_shard(layer, mp_policy=policy, reshard_after_forward=not args.no_reshard)
    for frozen_part in ([model.backbone.vision_tower, model.backbone.embed_vision] if gemma else [model.backbone.visual]):
        if frozen_part is not None:
            fully_shard(frozen_part, mp_policy=policy)
    fully_shard(text.embed_tokens, mp_policy=policy)
    fully_shard(model, mp_policy=policy)
    torch.cuda.empty_cache()
    model.train()

    teacher = None
    if args.anchor > 0 and gemma:
        teacher = build_gemma(checkpoint, torch.bfloat16, local, label_ids)
        teacher.requires_grad_(False)
        teacher.backbone.config.use_cache = False
        frozen = MixedPrecisionPolicy(param_dtype=torch.bfloat16, reduce_dtype=torch.bfloat16)
        for layer in teacher.backbone.language_model.layers:
            fully_shard(layer, mp_policy=frozen, reshard_after_forward=True)
        fully_shard(teacher, mp_policy=frozen)
        teacher.eval()
        teacher_readout = torch.nn.Identity()
        torch.cuda.empty_cache()
    elif args.anchor > 0:

        class Teacher(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.backbone = Qwen3_5Model.from_pretrained(str(checkpoint), dtype=torch.bfloat16, attn_implementation="sdpa", device_map={"": local})

            def forward(self, ids, mask, rows, cols):
                return self.backbone(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state[rows, cols]

        teacher = Teacher()
        enable_noncausal_full_attention(teacher.backbone.language_model)
        teacher.requires_grad_(False)
        teacher.backbone.config.use_cache = False
        frozen = MixedPrecisionPolicy(param_dtype=torch.bfloat16, reduce_dtype=torch.bfloat16)
        for layer in teacher.backbone.language_model.layers:
            fully_shard(layer, mp_policy=frozen, reshard_after_forward=True)
        fully_shard(teacher, mp_policy=frozen)
        teacher.eval()
        teacher_readout = torch.nn.Linear(model.readout.in_features, MAX_OPTIONS, bias=False, dtype=torch.float32, device=device)
        teacher_readout.load_state_dict({k: v.float() for k, v in load_file(str(checkpoint / "readout.safetensors")).items()})
        teacher_readout.requires_grad_(False)
        torch.cuda.empty_cache()

    body = [p for n, p in model.named_parameters() if p.requires_grad and not n.startswith("readout.")]
    head = [] if gemma else list(model.readout.parameters())
    groups = [{"params": body, "lr": args.lr}] + ([{"params": head, "lr": args.readout_lr}] if head else [])
    optimizer = torch.optim.AdamW(groups, betas=(0.9, 0.95), eps=1e-8, weight_decay=args.weight_decay, foreach=True)
    log(event="model", trainable=sum(p.numel() for p in body + head), memory_gib=round(torch.cuda.memory_allocated() / 2**30, 1))

    shards = sorted(Path(args.data).glob("train-*.pt"))
    examples = []
    for i, shard in enumerate(shards):
        rows = torch.load(shard, weights_only=False)
        examples += rows[rank::world]
    dev = torch.load(Path(args.data) / "dev.pt", weights_only=False)[rank::world] if (Path(args.data) / "dev.pt").exists() else []
    pad_id = json.loads((checkpoint / "tokenizer_config.json").read_text()).get("pad_token_id")
    if pad_id is None:
        from transformers import AutoTokenizer

        pad_id = AutoTokenizer.from_pretrained(str(checkpoint)).pad_token_id
    lengths = [int(e["ids"].numel()) for e in examples]
    n = torch.tensor([len(batches(lengths, args.tokens_per_batch, args.seed, 0))], device=device)
    dist.all_reduce(n, op=dist.ReduceOp.MIN)
    per_epoch = int(n.item()) // args.accumulate
    total_steps = max(1, int(per_epoch * args.epochs))
    if args.max_steps:
        total_steps = min(total_steps, args.max_steps)
    log(event="data", examples_rank0=len(examples), dev_rank0=len(dev), steps_per_epoch=per_epoch, total_steps=total_steps, tokens_rank0=sum(lengths))

    def schedule(step):
        if step < args.warmup:
            return (step + 1) / args.warmup
        progress = min(1.0, (step - args.warmup) / max(1, total_steps - args.warmup))
        return args.min_lr_ratio + (1 - args.min_lr_ratio) * 0.5 * (1 + math.cos(math.pi * progress))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, schedule)
    step = 0
    states = sorted((p for p in out.glob("state-*") if complete(p)), key=lambda p: int(p.name.split("-")[1]))
    if states:
        state = {"model": get_model_state_dict(model), "optim": get_optimizer_state_dict(model, optimizer)}
        dcp.load(state, checkpoint_id=str(states[-1]))
        set_model_state_dict(model, state["model"])
        set_optimizer_state_dict(model, optimizer, state["optim"])
        meta = json.loads((states[-1] / "done").read_text())
        step = meta["step"]
        scheduler.load_state_dict(meta["scheduler"])
        log(event="resumed", state=str(states[-1]), step=step)

    def barrier_done(path: Path, meta: dict):
        dist.barrier()
        if rank == 0:
            (path / "done").write_text(json.dumps(meta))
        dist.barrier()

    def save_state(step):
        path = out / f"state-{step}"
        state = {"model": get_model_state_dict(model), "optim": get_optimizer_state_dict(model, optimizer)}
        dcp.save(state, checkpoint_id=str(path))
        barrier_done(path, {"step": step, "scheduler": scheduler.state_dict(), "time": time.time()})
        if rank == 0:
            for old in out.glob("state-*"):
                if old != path and complete(path):
                    shutil.rmtree(old, ignore_errors=True)
        log(event="state_saved", step=step)

    def export(step):
        path = out / f"export-{step}"
        full = get_model_state_dict(model, options=StateDictOptions(full_state_dict=True, cpu_offload=True))
        if rank == 0:
            path.mkdir(parents=True, exist_ok=True)
            for f in checkpoint.iterdir():
                if f.is_file() and not f.name.startswith("model-") and f.name not in ("model.safetensors.index.json", "readout.safetensors"):
                    shutil.copy2(f, path / f.name)
            if gemma:
                expected = set(json.loads((checkpoint / "model.safetensors.index.json").read_text())["weight_map"])
                weights = {"model." + k.removeprefix("backbone."): v.to(torch.bfloat16).contiguous() for k, v in full.items() if k.startswith("backbone.")}
                if set(weights) != expected:
                    raise RuntimeError(f"export keys differ from the checkpoint: missing {sorted(expected - set(weights))[:5]}, extra {sorted(set(weights) - expected)[:5]}")
            else:
                weights = {k.removeprefix("backbone."): v.to(torch.bfloat16).contiguous() for k, v in full.items() if k.startswith("backbone.")}
                save_file({"weight": full["readout.weight"].to(torch.bfloat16).contiguous()}, str(path / "readout.safetensors"))
            index, shard, size, files = {}, {}, 0, []

            def flush():
                nonlocal shard, size
                if shard:
                    name = f"model-{len(files) + 1:05d}.safetensors"
                    save_file(shard, str(path / name), metadata={"format": "pt"})
                    files.append(name)
                    for k in shard:
                        index[k] = name
                    shard, size = {}, 0

            for k in sorted(weights):
                shard[k] = weights[k]
                size += weights[k].numel() * 2
                if size >= 5 * 2**30:
                    flush()
            flush()
            (path / "model.safetensors.index.json").write_text(json.dumps({"metadata": {"total_size": sum(v.numel() * 2 for v in weights.values())}, "weight_map": index}, indent=1))
            (path / "MODIFICATIONS").write_text(f"Gradiated Decide: full fine-tune of {checkpoint.name} (step {step}); see gdecide README.\n")
        del full
        barrier_done(path, {"step": step, "time": time.time()})
        log(event="exported", step=step, path=str(path))

    def evaluate_dev():
        if not dev:
            return {}
        model.eval()
        sums: dict[str, list[float]] = {}
        with torch.no_grad():
            dl = [int(e["ids"].numel()) for e in dev]
            groups = [g for g in batches(dl, args.tokens_per_batch, args.seed, 999) if any(t is not None for i in g for t in dev[i]["targets"])]
            count = torch.tensor([len(groups)], device=device)
            dist.all_reduce(count, op=dist.ReduceOp.MAX)
            for k in range(int(count.item())):
                real = k < len(groups)
                items = [dev[i] for i in groups[k]] if real else [dev[0]]
                ids, mask, rows, cols, counts, targets, weights = collate(items, pad_id, right=gemma)
                logits = model(ids.to(device), mask.to(device), torch.tensor(rows, device=device), torch.tensor(cols, device=device))
                if not real:
                    continue
                cursor = 0
                for b, e in enumerate(items):
                    m = sum(1 for t in e["targets"] if t is not None)
                    if not m:
                        continue
                    _, ce, br, w, _ = losses(logits[cursor : cursor + m], counts[cursor : cursor + m], targets[cursor : cursor + m], [1.0] * m, 0.0)
                    acc = sum(int(int(logits[cursor + j, : counts[cursor + j]].argmax()) == max(range(counts[cursor + j]), key=targets[cursor + j].__getitem__)) for j in range(m))
                    s = sums.setdefault(e["source"], [0.0, 0.0, 0.0])
                    s[0] += float(ce)
                    s[1] += acc
                    s[2] += m
                    cursor += m
        model.train()
        gathered = [None] * world
        dist.all_gather_object(gathered, sums)
        merged: dict[str, list[float]] = {}
        for g in gathered:
            for k, v in g.items():
                m = merged.setdefault(k, [0.0, 0.0, 0.0])
                for i in range(3):
                    m[i] += v[i]
        return {k: {"ce": round(a / c, 4), "acc": round(b / c, 4), "n": int(c)} for k, (a, b, c) in sorted(merged.items()) if c}

    if args.bench:
        args.dev_every, args.export_every, args.state_minutes = 0, 0, float("inf")
    profiler = None
    if args.profile and rank == 0:
        profiler = torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA], schedule=torch.profiler.schedule(wait=3, warmup=1, active=3, repeat=1))
        profiler.start()
    if step == 0 and not args.bench:
        log(event="dev", step=0, dev=evaluate_dev())
    last_state = time.time()
    started = time.perf_counter()
    tokens = 0
    window = (time.perf_counter(), 0)
    epoch = step // max(1, per_epoch)
    position = (step % max(1, per_epoch)) * args.accumulate
    while step < total_steps:
        plan = batches(lengths, args.tokens_per_batch, args.seed, epoch)[: per_epoch * args.accumulate]
        while position < len(plan) and step < total_steps:
            optimizer.zero_grad(set_to_none=True)
            sums = torch.zeros(5, device=device, dtype=torch.float64)
            for micro in range(args.accumulate):
                ids, mask, rows, cols, counts, targets, weights = collate([examples[i] for i in plan[position + micro]], pad_id, right=gemma)
                tokens += int(mask.sum())
                ids, mask, rows, cols = ids.to(device, non_blocking=True), mask.to(device, non_blocking=True), torch.tensor(rows, device=device), torch.tensor(cols, device=device)
                anchor = None
                if teacher is not None:
                    with torch.no_grad():
                        anchor = teacher_readout(teacher(ids, mask, rows, cols).float())
                logits = model(ids, mask, rows, cols)
                loss, ce, br, w, kl = losses(logits, counts, targets, weights, args.brier, anchor, args.anchor)
                (loss / args.accumulate).backward()
                sums += torch.stack([ce, br, w, mask.sum().to(w), kl]).double()
            position += args.accumulate
            norm = torch.nn.utils.clip_grad_norm_(body + head, 1.0)
            optimizer.step()
            scheduler.step()
            step += 1
            if profiler is not None:
                profiler.step()
                if step == 7:
                    profiler.stop()
                    averages = profiler.key_averages()
                    try:
                        table = averages.table(sort_by="self_device_time_total", row_limit=60)
                    except Exception:
                        table = averages.table(sort_by="self_cuda_time_total", row_limit=60)
                    (out / "profile.txt").write_text(table)
                    profiler = None
            if step % 10 == 0 or step == 1:
                dist.all_reduce(sums)
                elapsed = time.perf_counter() - started
                tok = torch.tensor([tokens], device=device, dtype=torch.float64)
                dist.all_reduce(tok)
                torch.cuda.synchronize()
                now = time.perf_counter()
                recent = round((float(tok) - window[1]) / max(1e-6, now - window[0]))
                window = (now, float(tok))
                log(event="train", recent_tokens_per_s=recent, step=step, of=total_steps, ce=round(float(sums[0] / sums[2]), 4), brier=round(float(sums[1] / sums[2]), 4), kl=round(float(sums[4] / sums[2]), 5), grad_norm=round(float(norm.full_tensor() if hasattr(norm, "full_tensor") else norm), 3), lr=scheduler.get_last_lr()[0], tokens_per_s=round(float(tok) / elapsed), mem_gib=round(torch.cuda.max_memory_allocated() / 2**30, 1))
            if args.dev_every and step % args.dev_every == 0:
                log(event="dev", step=step, dev=evaluate_dev())
            flag = torch.tensor([1.0 if time.time() - last_state > args.state_minutes * 60 else 0.0], device=device)
            dist.all_reduce(flag, op=dist.ReduceOp.MAX)
            if flag.item() > 0 and step < total_steps:
                save_state(step)
                last_state = time.time()
            if args.export_every and step % args.export_every == 0 and step < total_steps:
                export(step)
        epoch += 1
        position = 0
    if not args.bench:
        log(event="dev", step=step, dev=evaluate_dev())
        export(step)
    log(event="finished", step=step)
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
