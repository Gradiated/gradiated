#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Callable


HOLDOUT_REQUESTS = (18, 28, 29, 30)
PAD_TOKEN = -1


def repository_relative(path: Path) -> str:
    resolved = path.resolve()
    for parent in (resolved, *resolved.parents):
        if (parent / ".git").exists():
            return str(resolved.relative_to(parent))
    return str(path)


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_sequences(root: Path) -> tuple[dict[int, list[int]], list[dict[str, object]]]:
    sequences: dict[int, list[int]] = {}
    manifest: list[dict[str, object]] = []
    for request_index in range(32):
        path = root / f"request-{request_index:02d}.json"
        row = json.loads(path.read_text())
        token_ids = row.get("token_ids")
        if (
            not isinstance(token_ids, list)
            or len(token_ids) != 358
            or not all(isinstance(token, int) and token >= 0 for token in token_ids)
        ):
            raise ValueError(f"invalid target token sequence: {path}")
        sequences[request_index] = token_ids
        manifest.append(
            {
                "request_index": request_index,
                "path": repository_relative(path),
                "sha256": sha256(path),
                "tokens": len(token_ids),
            }
        )
    return sequences, manifest


def equality_features(tokens: list[int], width: int):
    import torch

    context = [PAD_TOKEN] * max(0, width - len(tokens)) + tokens[-width:]
    valid = [float(token != PAD_TOKEN) for token in context]
    equality = [
        float(left != PAD_TOKEN and left == right)
        for left in context
        for right in context
    ]
    return torch.tensor(valid + equality, dtype=torch.float32)


def label_for_next(
    context: list[int],
    target: int,
    width: int,
    vocabulary_index: dict[int, int],
) -> int:
    for distance in range(1, min(width, len(context)) + 1):
        if context[-distance] == target:
            return distance
    return width + 1 + vocabulary_index[target]


def build_examples(
    sequences: list[list[int]],
    width: int,
    vocabulary_index: dict[int, int],
):
    import torch

    features = []
    labels = []
    for sequence in sequences:
        for position in range(1, len(sequence)):
            features.append(equality_features(sequence[:position], width))
            labels.append(
                label_for_next(
                    sequence[:position],
                    sequence[position],
                    width,
                    vocabulary_index,
                )
            )
    return torch.stack(features), torch.tensor(labels, dtype=torch.int64)


def build_model(input_size: int, output_size: int):
    import torch

    return torch.nn.Sequential(
        torch.nn.Linear(input_size, 128),
        torch.nn.GELU(),
        torch.nn.Linear(128, 64),
        torch.nn.GELU(),
        torch.nn.Linear(64, output_size),
    )


def train_model(
    features,
    labels,
    *,
    output_size: int,
    epochs: int,
    seed: int,
):
    import torch

    torch.manual_seed(seed)
    random.seed(seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(min(8, os.cpu_count() or 1))
    model = build_model(features.shape[1], output_size)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    generator = torch.Generator().manual_seed(seed)
    losses = []
    started = time.monotonic()
    model.train()
    for _ in range(epochs):
        order = torch.randperm(len(labels), generator=generator)
        epoch_loss = 0.0
        for start in range(0, len(labels), 256):
            indices = order[start : start + 256]
            optimizer.zero_grad(set_to_none=True)
            logits = model(features[indices])
            loss = torch.nn.functional.cross_entropy(logits, labels[indices])
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.detach()) * len(indices)
        losses.append(epoch_loss / len(labels))
    return model.eval(), losses, time.monotonic() - started


def trained_draft(
    model,
    prefix: list[int],
    depth: int,
    width: int,
    vocabulary: list[int],
) -> list[int]:
    import torch

    generated = list(prefix)
    draft = []
    with torch.inference_mode():
        for _ in range(depth):
            logits = model(equality_features(generated, width))
            label = int(torch.argmax(logits))
            if 1 <= label <= width and label <= len(generated):
                token = generated[-label]
            elif label > width:
                vocabulary_position = label - width - 1
                if vocabulary_position >= len(vocabulary):
                    break
                token = vocabulary[vocabulary_position]
            else:
                break
            draft.append(token)
            generated.append(token)
    return draft


def latest_copy_draft(prefix: list[int], depth: int) -> list[int]:
    return [prefix[-1]] * depth if prefix else []


def corpus_ngram_table(
    sequences: list[list[int]],
    max_order: int,
) -> dict[tuple[int, ...], int]:
    counts: dict[tuple[int, ...], Counter[int]] = {}
    for sequence in sequences:
        for position in range(1, len(sequence)):
            for order in range(1, min(max_order, position) + 1):
                key = tuple(sequence[position - order : position])
                counts.setdefault(key, Counter())[sequence[position]] += 1
    table = {}
    for key, counter in counts.items():
        ranked = counter.most_common(2)
        if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
            table[key] = ranked[0][0]
    return table


def corpus_ngram_draft(
    table: dict[tuple[int, ...], int],
    prefix: list[int],
    depth: int,
    max_order: int,
) -> list[int]:
    generated = list(prefix)
    draft = []
    for _ in range(depth):
        token = None
        for order in range(min(max_order, len(generated)), 0, -1):
            token = table.get(tuple(generated[-order:]))
            if token is not None:
                break
        if token is None:
            break
        draft.append(token)
        generated.append(token)
    return draft


def in_request_ngram_draft(
    prefix: list[int],
    depth: int,
    max_order: int,
) -> list[int]:
    generated = list(prefix)
    draft = []
    for _ in range(depth):
        token = None
        for order in range(min(max_order, len(generated)), 0, -1):
            suffix = generated[-order:]
            for end in range(len(generated) - 1, order - 1, -1):
                if generated[end - order : end] == suffix:
                    token = generated[end]
                    break
            if token is not None:
                break
        if token is None:
            break
        draft.append(token)
        generated.append(token)
    return draft


def accepted_prefix(draft: list[int], target: list[int]) -> int:
    accepted = 0
    for proposed, expected in zip(draft, target):
        if proposed != expected:
            break
        accepted += 1
    return accepted


def evaluate(
    sequences: dict[int, list[int]],
    draft: Callable[[list[int], int], list[int]],
    *,
    depth: int,
    warmup: int,
) -> dict[str, object]:
    accepted = []
    per_request = {}
    first_correct = 0
    proposed = 0
    for request_index, sequence in sorted(sequences.items()):
        request_accepted = []
        for position in range(warmup, len(sequence) - depth + 1):
            prediction = draft(sequence[:position], depth)
            prefix = accepted_prefix(prediction, sequence[position : position + depth])
            request_accepted.append(prefix)
            accepted.append(prefix)
            if prediction:
                proposed += 1
                first_correct += int(prediction[0] == sequence[position])
        per_request[str(request_index)] = {
            "mean_accepted_draft_tokens": statistics.fmean(request_accepted),
            "full_depth_fraction": sum(value == depth for value in request_accepted)
            / len(request_accepted),
            "positions": len(request_accepted),
        }
    return {
        "mean_accepted_draft_tokens": statistics.fmean(accepted),
        "mean_accepted_target_tokens": 1.0 + statistics.fmean(accepted),
        "full_depth_fraction": sum(value == depth for value in accepted) / len(accepted),
        "first_draft_token_accuracy": first_correct / proposed if proposed else 0.0,
        "proposal_coverage": proposed / len(accepted),
        "positions": len(accepted),
        "per_request": per_request,
    }


def timed_draft_us(
    draft: Callable[[list[int], int], list[int]],
    prefixes: list[list[int]],
    depth: int,
) -> dict[str, float]:
    samples = []
    for prefix in prefixes:
        started = time.perf_counter_ns()
        draft(prefix, depth)
        samples.append((time.perf_counter_ns() - started) / 1000)
    return {
        "median": statistics.median(samples),
        "p95": sorted(samples)[math.ceil(0.95 * len(samples)) - 1],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    project = Path(__file__).resolve().parent
    parser.add_argument(
        "--data-root",
        type=Path,
        default=project.parent
        / "gemma4_h200_dflash_endpoint"
        / "artifacts"
        / "request-state-capture-owner-20260725T232227Z"
        / "retrieved"
        / "results"
        / "ar-c32",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project / "CPU_SPECULATIVE_DECODER_RESULT.json",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=project / "cpu_speculative_decoder" / "model.pt",
    )
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--width", type=int, default=16)
    parser.add_argument("--depth", type=int, default=4)
    args = parser.parse_args()

    import torch

    if torch.cuda.is_available():
        raise RuntimeError("CPU experiment refuses to run while CUDA is visible")
    sequences, source_manifest = load_sequences(args.data_root)
    train = {
        key: value
        for key, value in sequences.items()
        if key not in HOLDOUT_REQUESTS
    }
    holdout = {
        key: value
        for key, value in sequences.items()
        if key in HOLDOUT_REQUESTS
    }
    vocabulary = sorted({token for sequence in train.values() for token in sequence})
    vocabulary_index = {token: index for index, token in enumerate(vocabulary)}
    features, labels = build_examples(
        list(train.values()),
        args.width,
        vocabulary_index,
    )
    model, losses, training_seconds = train_model(
        features,
        labels,
        output_size=args.width + 1 + len(vocabulary),
        epochs=args.epochs,
        seed=args.seed,
    )
    corpus_table = corpus_ngram_table(list(train.values()), args.width)
    methods: dict[str, Callable[[list[int], int], list[int]]] = {
        "trained_copy_vocabulary_mlp": lambda prefix, depth: trained_draft(
            model,
            prefix,
            depth,
            args.width,
            vocabulary,
        ),
        "latest_token_copy": latest_copy_draft,
        "training_corpus_ngram": lambda prefix, depth: corpus_ngram_draft(
            corpus_table,
            prefix,
            depth,
            args.width,
        ),
        "in_request_ngram": lambda prefix, depth: in_request_ngram_draft(
            prefix,
            depth,
            args.width,
        ),
    }
    metrics = {
        name: evaluate(
            holdout,
            method,
            depth=args.depth,
            warmup=args.width,
        )
        for name, method in methods.items()
    }
    timing_prefixes = [
        sequence[:position]
        for sequence in holdout.values()
        for position in range(args.width, len(sequence) - args.depth + 1, 16)
    ]
    timing = {
        name: timed_draft_us(method, timing_prefixes, args.depth)
        for name, method in methods.items()
    }
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_temporary = args.checkpoint.with_suffix(".pt.tmp")
    torch.save(
        {
            "schema_version": 1,
            "model": model.state_dict(),
            "input_size": int(features.shape[1]),
            "output_size": args.width + 1 + len(vocabulary),
            "vocabulary": vocabulary,
            "width": args.width,
            "depth": args.depth,
            "seed": args.seed,
        },
        checkpoint_temporary,
    )
    checkpoint_temporary.replace(args.checkpoint)
    trained = metrics["trained_copy_vocabulary_mlp"]
    control = metrics["in_request_ngram"]
    result = {
        "schema_version": 1,
        "classification": "measured_cpu_speculative_decoder_pilot",
        "evidence": "measured",
        "scope": "offline exact-token prefixes on synthetic gemma4-background-exact-mix-c32-20260718 only",
        "decision": (
            "promote_to_endpoint"
            if trained["mean_accepted_draft_tokens"]
            > control["mean_accepted_draft_tokens"]
            else "do_not_promote_learned_decoder_over_in_request_ngram"
        ),
        "reason": (
            "The learned decoder beats the deterministic in-request n-gram control."
            if trained["mean_accepted_draft_tokens"]
            > control["mean_accepted_draft_tokens"]
            else "The learned decoder does not beat the simpler deterministic in-request n-gram control on request-disjoint traces."
        ),
        "cpu_only": {
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "torch_cuda_available": torch.cuda.is_available(),
            "torch_version": torch.__version__,
            "training_seconds": training_seconds,
            "threads": torch.get_num_threads(),
        },
        "data": {
            "source_manifest": source_manifest,
            "train_request_indices": sorted(train),
            "holdout_request_indices": sorted(holdout),
            "train_examples": len(labels),
            "train_unique_tokens": len(vocabulary),
            "holdout_unique_tokens": len(
                {token for sequence in holdout.values() for token in sequence}
            ),
            "holdout_tokens_seen_in_training": len(
                {token for sequence in holdout.values() for token in sequence}
                & set(vocabulary)
            ),
        },
        "model": {
            "architecture": "token-identity-invariant equality features -> 128 GELU -> 64 GELU -> copy-distance-or-training-vocabulary",
            "parameters": sum(parameter.numel() for parameter in model.parameters()),
            "epochs": args.epochs,
            "loss_first": losses[0],
            "loss_last": losses[-1],
            "checkpoint": {
                "path": repository_relative(args.checkpoint),
                "sha256": sha256(args.checkpoint),
                "bytes": args.checkpoint.stat().st_size,
            },
        },
        "measurement": {
            "depth": args.depth,
            "context_width": args.width,
            "metrics": metrics,
            "controller_cpu_draft_time_us": timing,
        },
        "limitations": [
            "The workload uses synthetic token-ID prompts and highly repetitive completions.",
            "This is not a matched target-GPU endpoint measurement.",
            "The decoder sees output-token context but no target hidden state or prompt representation.",
            "Target verification would preserve output exactly in a later runtime integration.",
        ],
    }
    atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
