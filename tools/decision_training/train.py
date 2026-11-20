import argparse
import hashlib
import json
import math
import pathlib
import random
import signal
import sys
import time

from data import read_jsonl
from distributed import DistributedRun, rank_batches
from snapshot import verify_snapshot


def bounded_checkpoint_write(write, deadline, previous_seconds=0, reserve=900):
    # Skip near the fence, and interrupt unexpectedly slow serialization/hashing.
    # The supported training entry point runs on the Linux main thread.
    check_deadline(
        deadline, reserve=reserve, estimated_seconds=max(60, 2 * previous_seconds)
    )
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError("checkpoint writer cannot replace an active alarm")

    def timeout(_signum, _frame):
        raise TimeoutError("checkpoint write reached the evaluation reserve")

    old_handler = signal.signal(signal.SIGALRM, timeout)
    started = time.monotonic()
    try:
        signal.setitimer(signal.ITIMER_REAL, deadline - reserve - started)
        write()
        check_deadline(deadline, reserve=reserve)
        return time.monotonic() - started
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def check_deadline(deadline, reserve=0, now=None, estimated_seconds=0):
    if (
        time.monotonic() if now is None else now
    ) + estimated_seconds >= deadline - reserve:
        raise TimeoutError("experiment deadline or reserved evaluation window reached")


def parse_s3_uri(uri):
    bucket, separator, prefix = uri.removeprefix("s3://").partition("/")
    prefix = prefix.strip("/")
    if (
        not uri.startswith("s3://")
        or not separator
        or not bucket
        or not prefix
        or any(c.isspace() for c in uri)
        or "?" in uri
        or "#" in uri
    ):
        raise ValueError("--s3-uri must contain a nonempty bucket and project prefix")
    return bucket, prefix


def validate_experiment_bounds(args):
    if (
        args["steps"] < 1
        or args["seconds"] < 120
        or min(
            args[key] for key in ["batch_size", "accumulation", "max_length", "rank"]
        )
        < 1
        or not math.isfinite(args["learning_rate"])
        or args["learning_rate"] <= 0
        or not math.isfinite(args["brier_weight"])
        or args["brier_weight"] < 0
    ):
        raise ValueError("invalid experiment bounds")
    if not args["evaluate_only"] and args["seconds"] <= 900:
        raise ValueError(
            "training deadline must exceed the 900-second evaluation reserve"
        )


def learning_rate_for_step(step, total_steps, peak):
    return (
        peak
        * min(1.0, step / 20)
        * 0.5
        * (1 + math.cos(math.pi * (step - 1) / total_steps))
    )


def validate_resume_arguments(saved, current):
    critical = (
        "batch_size",
        "accumulation",
        "max_length",
        "learning_rate",
        "brier_weight",
        "rank",
        "steps",
    )
    changed = [
        key for key in critical if key not in saved or saved[key] != current[key]
    ]
    if saved.get("training_world_size", 1) != current.get("training_world_size", 1):
        changed.append("training_world_size")
    if changed:
        raise ValueError("checkpoint training arguments differ: " + ", ".join(changed))


def validate_checkpoint_identity(manifest, identity):
    if "identity" not in manifest or manifest["identity"] != identity:
        raise ValueError("checkpoint identity is missing or belongs to another run")


def validate_output_reuse(output, resume):
    output = pathlib.Path(output)
    if not resume and (
        any(output.glob("checkpoint-*")) or (output / "adapter-final").exists()
    ):
        raise ValueError(
            "output directory already contains training artifacts; use --resume "
            "or a new output directory"
        )


def build_run_identity(root, data, max_length, world_size=1):
    source_dir = pathlib.Path(__file__).resolve().parent
    benchmark_dir = root / "jevbench" / "jevbench"
    sources = {
        "runner/" + name: source_dir / name
        for name in ("train.py", "data.py", "snapshot.py", "distributed.py")
    }
    for name in ("__init__.py", "scoring.py", "metrics.py", "tasks.py"):
        if not (benchmark_dir / name).is_file():
            raise ValueError(f"missing benchmark executable source: {name}")
    sources.update(
        {
            "jevbench/" + str(path.relative_to(benchmark_dir)): path
            for path in benchmark_dir.rglob("*.py")
        }
    )
    return {
        "model": "thinkingmachines/Inkling-2-Mini",
        "revision": "6e7c8248f75265bdd4fbab5273304243b5d8c2cb",
        "prompt": "native-chat-none-letter-v1",
        "evaluation_batch_size": 1,
        "verified_model_manifest_sha256": verify_snapshot(root),
        "max_length": max_length,
        "training_world_size": world_size,
        "executable_sources_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in sorted(sources.items())
        },
        "data": {
            name: hashlib.sha256((data / name).read_bytes()).hexdigest()
            for name in ["train.jsonl", "dev.jsonl", "jevbench-231.jsonl"]
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Train and evaluate a direct Inkling decision adapter."
    )
    parser.add_argument("--run-dir", type=pathlib.Path, required=True)
    parser.add_argument("--s3-uri", required=True)
    parser.add_argument("--brier-weight", type=float, default=1.0)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--rank", type=int, default=32)
    parser.add_argument("--stop-file", type=pathlib.Path)
    parser.add_argument("--data-dir", type=pathlib.Path)
    parser.add_argument("--output-dir", type=pathlib.Path)
    parser.add_argument("--resume", type=str)
    parser.add_argument("--evaluate-only", action="store_true")
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--seconds", type=int, default=9000)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--accumulation", type=int, default=4)
    parser.add_argument("--max-length", type=int, default=1024)
    args = parser.parse_args()
    if args.evaluate_only and not args.resume:
        parser.error("--evaluate-only requires --resume")
    try:
        s3_bucket, s3_prefix = parse_s3_uri(args.s3_uri)
        validate_experiment_bounds(vars(args))
        validate_output_reuse(args.output_dir or args.run_dir / "outputs", args.resume)
    except ValueError as error:
        parser.error(str(error))
    start = time.monotonic()
    deadline = start + args.seconds
    import torch
    from peft import LoraConfig, get_peft_model, set_peft_model_state_dict
    from safetensors.torch import load_file
    from transformers import AutoTokenizer, Inkling2LoopForConditionalGeneration

    distributed = DistributedRun(torch)
    args.training_world_size = distributed.world_size

    ROOT = args.run_dir.resolve()
    DATA = args.data_dir or ROOT / "data"
    OUT = args.output_dir or ROOT / "outputs"
    sys.path.insert(0, str(ROOT / "jevbench"))
    from jevbench.metrics import brier_score, ece_top_label
    from jevbench.scoring import score_task
    from jevbench.tasks import Task

    random.seed(20261120)
    torch.manual_seed(20261120)
    torch.set_num_threads(12)
    if distributed.primary:
        OUT.mkdir(parents=True, exist_ok=True)
    distributed.barrier()

    def event(kind, **fields):
        if not distributed.primary:
            return
        row = {
            "event": kind,
            "time": time.time(),
            "elapsed": time.monotonic() - start,
            **fields,
        }
        print(json.dumps(row), flush=True)
        with (OUT / "events.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")

    def sync(reserve=0):
        if not distributed.primary:
            return
        import boto3
        from botocore.config import Config

        check_deadline(deadline, reserve=reserve)
        s = boto3.client(
            "s3",
            config=Config(
                connect_timeout=5, read_timeout=30, retries={"total_max_attempts": 3}
            ),
        )
        bucket, prefix = s3_bucket, s3_prefix

        def upload(path, key):
            check_deadline(deadline, reserve=reserve)
            s.upload_file(
                str(path),
                bucket,
                key,
                Callback=lambda _bytes: check_deadline(deadline, reserve=reserve),
            )

        for base in [OUT, DATA]:
            for p in sorted(
                base.rglob("*"), key=lambda p: p.name == "checkpoint-complete.json"
            ):
                if p.is_file() and not any(
                    part.endswith(".tmp") for part in p.relative_to(base).parts
                ):
                    upload(p, prefix + "/" + base.name + "/" + str(p.relative_to(base)))
        for name in [
            "train.py",
            "prepare_data.py",
            "pilot.json",
            "model-manifest.json",
            "model-sha256.txt",
            "model-integrity.json",
        ]:
            p = ROOT / name
            if p.exists():
                upload(p, prefix + "/" + name)
        for name in (
            "train.py",
            "data.py",
            "snapshot.py",
            "distributed.py",
            "compare.py",
            "requirements.txt",
        ):
            source = pathlib.Path(__file__).parent / name
            if source.exists():
                upload(source, prefix + "/source/" + name)
        for source in sorted((ROOT / "jevbench" / "jevbench").rglob("*.py")):
            upload(
                source,
                prefix
                + "/source/jevbench/"
                + str(source.relative_to(ROOT / "jevbench")),
            )
        event("s3_sync")

    identity = distributed.broadcast(
        build_run_identity(ROOT, DATA, args.max_length, distributed.world_size)
        if distributed.primary
        else None
    )
    identity_path = OUT / "identity.json"
    if distributed.primary and identity_path.exists():
        if json.loads(identity_path.read_text()) != identity:
            raise ValueError(
                "output directory belongs to different model, prompt or data"
            )
    elif distributed.primary:
        identity_path.write_text(json.dumps(identity, indent=2) + "\n")
    distributed.barrier()

    def read(name):
        return read_jsonl(DATA / name)

    tokenizer = AutoTokenizer.from_pretrained(ROOT / "model")
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    letter_ids = [tokenizer.encode(c, add_special_tokens=False) for c in letters]
    assert all(len(x) == 1 for x in letter_ids), letter_ids
    letter_ids = torch.tensor([x[0] for x in letter_ids], device="cuda")

    def bench_row(r):
        q = r["question"]
        criteria = q.get("criteria")
        labels = r["labels"]
        if q["type"] == "noul":
            descs = [
                str((criteria or {}).get("false" if l == "no" else "true", l))
                for l in labels
            ]
        elif q["type"] == "score":
            descs = [str(criteria[int(l)]) for l in labels]
        else:
            descs = [str(criteria[l]) for l in labels]
        return {**r, "descriptions": descs}

    def encode(r):
        state = (
            r["state"]
            if isinstance(r["state"], str)
            else json.dumps(r["state"], ensure_ascii=False, sort_keys=True)
        )
        q = r["question"]
        instruction = (
            q["instructions"]
            if isinstance(q["instructions"], str)
            else json.dumps(q["instructions"], ensure_ascii=False)
        )
        opts = "\n".join(f"{letters[i]}: {d}" for i, d in enumerate(r["descriptions"]))
        content = f"State:\n{state}\n\nQuestion:\n{instruction}\n\nOptions:\n{opts}\n\nChoose the correct option. Reply with its letter only."
        prompt = (
            tokenizer.apply_chat_template(
                [{"role": "user", "content": content}],
                tokenize=False,
                reasoning_effort="none",
            )
            + "<|message_model|><|content_text|>"
        )
        ids = tokenizer.encode(prompt, add_special_tokens=False)
        return {**r, "ids": ids}

    train = []
    for r in read("train.jsonl"):
        r = encode(r)
        if len(r["ids"]) <= args.max_length:
            train.append(r)
    dev = [encode(r) for r in read("dev.jsonl")]
    dev = [r for r in dev if len(r["ids"]) <= args.max_length][:256]
    bench = [encode(bench_row(r)) for r in read("jevbench-231.jsonl")]
    event(
        "data_ready",
        train=len(train),
        dev=len(dev),
        benchmark=len(bench),
        max_benchmark_tokens=max(len(r["ids"]) for r in bench),
    )
    assert train and dev and len(bench) == 231

    event("model_load_start")
    model, loading = Inkling2LoopForConditionalGeneration.from_pretrained(
        ROOT / "model",
        dtype=torch.bfloat16,
        device_map="cuda",
        output_loading_info=True,
    )
    for key in ["missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs"]:
        assert not loading.get(key), (key, loading[key])
    model.config.use_cache = False
    model.model.language_model.config.use_cache = False
    model.eval()
    event("model_loaded", gpu_allocated_gb=torch.cuda.memory_allocated() / 1e9)

    training_model = model

    def logits(rows, training=False):
        inputs = tokenizer.pad(
            {"input_ids": [r["ids"] for r in rows]}, return_tensors="pt"
        ).to("cuda")
        return (
            (training_model if training else model)(
                **inputs, use_cache=False, logits_to_keep=1
            )
            .logits[:, -1, letter_ids]
            .float()
        )

    def evaluate(rows, name, temperature=1.0, sync_outputs=True):
        model.eval()
        predictions = []
        ordered = sorted(rows, key=lambda r: len(r["ids"]))
        prediction_path = OUT / (name + ".jsonl")
        if (
            prediction_path.exists()
            and prediction_path.stat().st_size
            and not (OUT / (name + ".json")).exists()
        ):
            raise RuntimeError(
                "partial evaluation exists; retain and repair it rather than replaying requests"
            )
        with torch.no_grad(), prediction_path.open("w") as prediction_stream:
            for offset, row in enumerate(ordered):
                check_deadline(deadline)
                batch = [row]
                ts = time.monotonic()
                raw = logits(batch)
                torch.cuda.synchronize()
                dt = time.monotonic() - ts
                for r, z in zip(batch, raw):
                    n = len(r["labels"])
                    p = (z[:n] / temperature).softmax(-1).tolist()
                    probs = dict(zip(r["labels"], p))
                    entry = {
                        "id": r["id"],
                        "type": r["question"]["type"],
                        "probs": probs,
                        "logits": z[:n].tolist(),
                        "elapsed_batch_seconds": dt,
                        "batch_size": len(batch),
                    }
                    if "expected" in r:
                        task = Task.from_dict(
                            {
                                k: r[k]
                                for k in [
                                    "id",
                                    "family",
                                    "state",
                                    "question",
                                    "labels",
                                    "expected",
                                    "split",
                                    "group",
                                    "provenance",
                                ]
                                if k in r
                            }
                        )
                        result = score_task(probs, task)
                        entry.update(result)
                        entry["expected"] = r["expected"]
                        entry["family"] = r["family"]
                        entry["brier"] = brier_score(
                            probs, str(r["expected"]), r["labels"]
                        )
                    else:
                        target = r["target"]
                        entry["target"] = target
                        entry["correct"] = max(range(n), key=lambda i: p[i]) == max(
                            range(n), key=lambda i: target[i]
                        )
                        entry["brier"] = sum((a - b) ** 2 for a, b in zip(p, target))
                    predictions.append(entry)
                    prediction_stream.write(json.dumps(entry) + "\n")
                    prediction_stream.flush()
                if offset % 40 == 0:
                    event(
                        "evaluation_progress",
                        name=name,
                        done=min(offset + len(batch), len(ordered)),
                        total=len(ordered),
                    )
        pairs = [(max(r["probs"].values()), r["correct"]) for r in predictions]
        metrics = {
            "n": len(predictions),
            "accuracy": sum(r["correct"] for r in predictions) / len(predictions),
            "brier": sum(r["brier"] for r in predictions) / len(predictions),
            "ece": ece_top_label(pairs),
            "temperature": temperature,
        }
        metrics["by_type"] = {
            kind: {"n": len(rs), "accuracy": sum(r["correct"] for r in rs) / len(rs)}
            for kind in ["noul", "choice", "score"]
            if (rs := [r for r in predictions if r["type"] == kind])
        }
        (OUT / (name + ".json")).write_text(json.dumps(metrics, indent=2) + "\n")
        event("evaluation_complete", name=name, **metrics)
        if sync_outputs:
            sync()
        return predictions, metrics

    with torch.no_grad():
        lengths = sorted(bench, key=lambda row: len(row["ids"]))
        probability_delta = (
            max(
                (
                    logits([row])[0, : len(row["labels"])].softmax(-1)
                    - logits([row])[0, : len(row["labels"])].softmax(-1)
                )
                .abs()
                .max()
                .item()
                for row in [lengths[0], lengths[len(lengths) // 2], lengths[-1]]
            )
            if distributed.primary
            else 0
        )
        if probability_delta > 1e-5:
            raise ValueError(f"single-request replay is unstable: {probability_delta}")
        event("single_request_replay", maximum_probability_delta=probability_delta)

    if distributed.primary and not (OUT / "baseline-jevbench.json").exists():
        evaluate(bench, "baseline-jevbench")
    if distributed.primary and not (OUT / "baseline-dev.json").exists():
        evaluate(dev, "baseline-dev")
    distributed.barrier()
    # Fixed low-rank intervention on attention projections and answer readout.
    targets = [
        name
        for name, module in model.named_modules()
        if isinstance(module, torch.nn.Linear)
        and (".self_attn." in name or name == "lm_head")
    ]
    assert len(targets) > 50, targets
    model = get_peft_model(
        model,
        LoraConfig(
            r=args.rank,
            lora_alpha=2 * args.rank,
            lora_dropout=0,
            target_modules=targets,
            bias="none",
        ),
    )
    model.gradient_checkpointing_enable(
        gradient_checkpointing_kwargs={"use_reentrant": False}
    )
    model.enable_input_require_grads()
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=args.learning_rate,
        betas=(0.9, 0.95),
        weight_decay=0.0,
    )
    event(
        "training_start",
        trainable=sum(p.numel() for p in model.parameters() if p.requires_grad),
        targets=targets,
        arguments={
            k: str(v) if isinstance(v, pathlib.Path) else v
            for k, v in vars(args).items()
        },
    )

    # Length buckets reduce padding without changing examples or targets.
    batches, dropped = rank_batches(
        train, args.batch_size, distributed.world_size, distributed.rank
    )
    event(
        "distributed_geometry",
        world_size=distributed.world_size,
        global_batch_size=args.batch_size * args.accumulation * distributed.world_size,
        local_batches=len(batches),
        dropped_incomplete_epoch_examples=dropped,
    )
    step = 0
    cursor = 0
    lastsave = time.monotonic()
    optimizer.zero_grad(set_to_none=True)
    if args.resume:
        ckpt = pathlib.Path(args.resume)
        checkpoint_manifest = json.loads(
            (ckpt / "checkpoint-complete.json").read_text()
        )
        validate_checkpoint_identity(checkpoint_manifest, identity)
        for name, digest in checkpoint_manifest["files"].items():
            if hashlib.sha256((ckpt / name).read_bytes()).hexdigest() != digest:
                raise ValueError("incomplete or corrupt checkpoint")
        state = torch.load(ckpt / "trainer.pt", map_location="cpu", weights_only=False)
        validate_resume_arguments(state["args"], vars(args))
        set_peft_model_state_dict(
            model, load_file(str(ckpt / "adapter_model.safetensors"))
        )
        optimizer.load_state_dict(state["optimizer"])
        step = state["step"]
        cursor = state["cursor"]
        rng = state.get("rank_rng", [state])[distributed.rank]
        random.setstate(rng["random"])
        torch.set_rng_state(rng["torch_rng"])
        torch.cuda.set_rng_state(
            rng["cuda_rng"][0]
            if "rank_rng" in state
            else rng["cuda_rng"][distributed.local_rank]
        )
        event("resumed", checkpoint=str(ckpt), step=step)
    training_model = distributed.wrap(model)
    first_step = step + 1
    completed_steps = step
    final_step = step if args.evaluate_only else args.steps
    longest_microbatch_seconds = 0
    longest_optimizer_seconds = 0
    longest_checkpoint_seconds = 0
    cumulative_tokens = 0
    training_wall_start = time.monotonic()
    for step in range(first_step, final_step + 1):
        if not distributed.all(
            time.monotonic() < deadline - 900
            and not (args.stop_file and args.stop_file.exists())
        ):
            event("training_deadline_or_stop")
            break
        model.train()
        loss_sum = 0
        step_start = time.monotonic()
        step_cursor = cursor
        interrupted = False
        useful_tokens = 0
        padded_tokens = 0
        for micro in range(args.accumulation):
            if not distributed.all(
                time.monotonic() + longest_microbatch_seconds < deadline - 900
                and not (args.stop_file and args.stop_file.exists())
            ):
                interrupted = True
                break
            micro_start = time.monotonic()
            batch = batches[cursor % len(batches)]
            cursor += 1
            with distributed.accumulation(
                training_model, micro == args.accumulation - 1
            ):
                raw = logits(batch, training=True)
                losses = []
                for r, z in zip(batch, raw):
                    target = torch.tensor(
                        r["target"], device="cuda", dtype=torch.float32
                    )
                    lp = z[: len(target)].log_softmax(-1)
                    p = lp.exp()
                    losses.append(
                        -(target * lp).sum()
                        + args.brier_weight * ((p - target) ** 2).sum()
                    )
                loss = torch.stack(losses).mean() / args.accumulation
                if not distributed.all(bool(torch.isfinite(loss))):
                    raise ValueError("nonfinite loss on a training rank")
                loss.backward()
            loss_sum += loss.item()
            useful_tokens += sum(len(row["ids"]) for row in batch)
            padded_tokens += len(batch) * max(len(row["ids"]) for row in batch)
            torch.cuda.synchronize()
            longest_microbatch_seconds = max(
                longest_microbatch_seconds, time.monotonic() - micro_start
            )
        if not distributed.all(
            time.monotonic() + longest_optimizer_seconds < deadline - 900
        ):
            interrupted = True
        if interrupted:
            cursor = step_cursor
            optimizer.zero_grad(set_to_none=True)
            event("partial_update_discarded", pending_step=step)
            break
        optimizer_start = time.monotonic()
        norm = torch.nn.utils.clip_grad_norm_(
            [p for p in model.parameters() if p.requires_grad], 1.0
        )
        if not distributed.all(bool(torch.isfinite(norm) and norm > 0)):
            raise ValueError("invalid gradient norm on a training rank")
        for group in optimizer.param_groups:
            group["lr"] = learning_rate_for_step(step, args.steps, args.learning_rate)
        optimizer.step()
        torch.cuda.synchronize()
        longest_optimizer_seconds = max(
            longest_optimizer_seconds, time.monotonic() - optimizer_start
        )
        completed_steps = step
        cumulative_tokens += useful_tokens
        optimizer.zero_grad(set_to_none=True)
        if step == 1 or step % 10 == 0:
            global_useful = distributed.sum(useful_tokens)
            global_padded = distributed.sum(padded_tokens)
            cumulative_global_tokens = distributed.sum(cumulative_tokens)
            global_loss = distributed.sum(loss_sum) / distributed.world_size
            event(
                "training_step",
                step=step,
                loss=global_loss,
                gradient_norm=norm.item(),
                seconds=time.monotonic() - step_start,
                gpu_peak_gb=torch.cuda.max_memory_allocated() / 1e9,
                useful_tokens=global_useful,
                padded_tokens=global_padded,
                useful_tokens_per_second=global_useful
                / (time.monotonic() - step_start),
                cumulative_useful_tokens=cumulative_global_tokens,
                training_wall_seconds=time.monotonic() - training_wall_start,
                end_to_end_useful_tokens_per_second=cumulative_global_tokens
                / (time.monotonic() - training_wall_start),
            )
        if distributed.primary_flag(
            step == 1 or step % 100 == 0 or time.monotonic() - lastsave > 600
        ):
            rank_rng = distributed.gather(
                {
                    "random": random.getstate(),
                    "torch_rng": torch.get_rng_state(),
                    "cuda_rng": [torch.cuda.get_rng_state()],
                }
            )
            ckpt = OUT / f"checkpoint-{step:05d}"
            staging = ckpt.with_name(ckpt.name + ".tmp")

            def write_checkpoint(
                staging=staging, step=step, cursor=cursor, ckpt=ckpt, rank_rng=rank_rng
            ):
                model.save_pretrained(staging, save_embedding_layers=False)
                check_deadline(deadline, reserve=900)
                torch.save(
                    {
                        "step": step,
                        "cursor": cursor,
                        "optimizer": optimizer.state_dict(),
                        "random": random.getstate(),
                        "torch_rng": torch.get_rng_state(),
                        "cuda_rng": rank_rng[0]["cuda_rng"],
                        "rank_rng": rank_rng,
                        "args": {
                            k: str(v) if isinstance(v, pathlib.Path) else v
                            for k, v in vars(args).items()
                        },
                    },
                    staging / "trainer.pt",
                )
                files = {}
                for path in staging.iterdir():
                    if not path.is_file() or path.name == "checkpoint-complete.json":
                        continue
                    digest = hashlib.sha256()
                    with path.open("rb") as stream:
                        while chunk := stream.read(4 * 1024 * 1024):
                            check_deadline(deadline, reserve=900)
                            digest.update(chunk)
                    files[path.name] = digest.hexdigest()
                check_deadline(deadline, reserve=900)
                (staging / "checkpoint-complete.json").write_text(
                    json.dumps(
                        {
                            "step": step,
                            "identity": identity,
                            "files": files,
                        },
                        indent=2,
                    )
                )
                check_deadline(deadline, reserve=900)
                staging.rename(ckpt)

            checkpoint_ok = True
            if distributed.primary:
                try:
                    elapsed = bounded_checkpoint_write(
                        write_checkpoint, deadline, longest_checkpoint_seconds
                    )
                    longest_checkpoint_seconds = max(
                        longest_checkpoint_seconds, elapsed
                    )
                    sync(reserve=900)
                except TimeoutError:
                    event("checkpoint_deferred", step=step)
                    checkpoint_ok = False
            if not distributed.primary_flag(checkpoint_ok):
                break
            lastsave = time.monotonic()

    if not args.evaluate_only and completed_steps < first_step:
        raise RuntimeError(
            "no optimizer updates completed; no trained comparison will be written"
        )
    if not distributed.primary:
        distributed.barrier()
        distributed.close()
        return
    model.save_pretrained(OUT / "adapter-final", save_embedding_layers=False)
    tokenizer.save_pretrained(OUT / "adapter-final")
    trained_dev, _ = evaluate(dev, "trained-dev", sync_outputs=False)

    # Temperature is selected using only the source-held-out dev set, never JevBench labels.
    def dev_loss(t):
        total = 0
        for r in trained_dev:
            z = torch.tensor(r["logits"]) / t
            y = torch.tensor(r["target"])
            total += -(y * z.log_softmax(-1)).sum().item()
        return total / len(trained_dev)

    temp = min([0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0], key=dev_loss)
    (OUT / "calibration.json").write_text(
        json.dumps(
            {
                "temperature": temp,
                "source": "trained-dev",
                "held_out_from_training": True,
                "grid_nll": {
                    str(t): dev_loss(t)
                    for t in [0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]
                },
            }
        )
    )
    evaluate(bench, "trained-jevbench", temperature=temp, sync_outputs=False)
    event("complete", steps=completed_steps)
    sync()
    distributed.barrier()
    distributed.close()


if __name__ == "__main__":
    main()
