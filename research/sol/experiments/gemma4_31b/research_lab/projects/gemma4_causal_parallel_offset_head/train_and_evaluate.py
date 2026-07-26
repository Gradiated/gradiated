#!/usr/bin/env python3
"""Deterministic head-only training and disjoint-holdout evaluator."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import pathlib
import random

from causal_parallel_offset_head import (
    HeadConfig,
    acceptance_curve,
    batched_tied_logits,
    batched_tied_top1,
    build_torch_module,
    prefix_weighted_loss,
)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def read_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def load_capture(capture_root: pathlib.Path):
    import torch

    mapping = {}
    manifest_rows = []
    for path in sorted(capture_root.glob("tap-chunk-*.pt")):
        payload = torch.load(path, map_location="cpu", weights_only=True)
        if tuple(payload["tap_layers"]) != (45, 54, 60):
            raise RuntimeError(f"tap_layer_mismatch:{path}")
        if payload["hidden_size"] != 5376:
            raise RuntimeError(f"hidden_size_mismatch:{path}")
        for row_index, row in enumerate(payload["rows"]):
            key = (row["request_index"], row["target_offset"])
            if key in mapping:
                raise RuntimeError(f"duplicate_capture_row:{key}")
            mapping[key] = tuple(
                tap[row_index] for tap in payload["taps"]
            )
        manifest_rows.append(
            {"path": path.name, "sha256": sha256(path), "rows": len(payload["rows"])}
        )
    return mapping, manifest_rows


def batches(rows: list[dict], size: int, seed: int):
    order = list(range(len(rows)))
    random.Random(seed).shuffle(order)
    for start in range(0, len(order), size):
        yield [rows[index] for index in order[start : start + size]]


def stack_batch(rows: list[dict], capture, device):
    import torch

    taps = [
        torch.stack(
            [
                capture[(row["request_index"], row["target_start_offset"])][tap]
                for row in rows
            ]
        )
        .to(device=device, dtype=torch.bfloat16)
        .contiguous()
        for tap in range(3)
    ]
    targets = torch.tensor(
        [row["target_token_ids"] for row in rows],
        device=device,
        dtype=torch.int64,
    )
    return taps, targets


def load_tied_weight(path: pathlib.Path, key: str, device):
    from safetensors import safe_open

    with safe_open(path, framework="pt", device="cpu") as handle:
        weight = handle.get_tensor(key)
    if tuple(weight.shape) != (262144, 5376):
        raise RuntimeError(f"tied_weight_shape:{tuple(weight.shape)}")
    return weight.to(device=device, dtype=__import__("torch").bfloat16).contiguous()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-root", required=True, type=pathlib.Path)
    parser.add_argument("--split", required=True, type=pathlib.Path)
    parser.add_argument("--cost-model", required=True, type=pathlib.Path)
    parser.add_argument("--tied-weight", required=True, type=pathlib.Path)
    parser.add_argument(
        "--weight-key",
        default="model.language_model.embed_tokens.weight",
    )
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--seed", type=int, default=20260726)
    args = parser.parse_args()
    import torch

    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    torch.use_deterministic_algorithms(True)
    split = json.loads(args.split.read_text())
    project = args.split.parent
    train_rows = read_jsonl(project / split["train"]["path"])
    holdout_rows = read_jsonl(project / split["holdout"]["path"])
    capture, capture_manifest = load_capture(args.capture_root)
    required = {
        (row["request_index"], row["target_start_offset"])
        for row in train_rows + holdout_rows
    }
    missing = sorted(required - set(capture))
    if missing:
        raise RuntimeError(f"capture_rows_missing:{len(missing)}:{missing[:8]}")
    device = torch.device("cuda")
    config = HeadConfig()
    model = build_torch_module(config).to(device=device, dtype=torch.bfloat16)
    tied_weight = load_tied_weight(args.tied_weight, args.weight_key, device)
    tied_weight.requires_grad_(False)
    cost = json.loads(args.cost_model.read_text())
    offset_weights = torch.tensor(
        cost["training_offset_weights"]["normalized_offsets_1_through_16"],
        device=device,
        dtype=torch.float32,
    )
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.learning_rate, weight_decay=0.01
    )
    model.train()
    losses = []
    for epoch in range(args.epochs):
        for rows in batches(train_rows, args.batch_size, args.seed + epoch):
            taps, targets = stack_batch(rows, capture, device)
            optimizer.zero_grad(set_to_none=True)
            hidden = model(taps)
            logits = batched_tied_logits(hidden, tied_weight, config.softcap)
            loss = prefix_weighted_loss(logits, targets, offset_weights)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    checkpoint = args.artifact_root / "head_checkpoint.pt"
    checkpoint_temporary = checkpoint.with_suffix(".pt.part")
    torch.save(
        {
            "schema_version": 1,
            "config": dataclasses.asdict(config),
            "seed": args.seed,
            "epochs": args.epochs,
            "state_dict": {
                key: value.detach().cpu()
                for key, value in model.state_dict().items()
            },
        },
        checkpoint_temporary,
    )
    checkpoint_temporary.replace(checkpoint)
    model.eval()
    predicted, targets_all = [], []
    with torch.no_grad():
        for start in range(0, len(holdout_rows), args.batch_size):
            rows = holdout_rows[start : start + args.batch_size]
            taps, targets = stack_batch(rows, capture, device)
            hidden = model(taps)
            _, token_ids = batched_tied_top1(hidden, tied_weight, config.softcap)
            predicted.extend(token_ids.cpu().tolist())
            targets_all.extend(targets.cpu().tolist())
    curve = acceptance_curve(predicted, targets_all)
    accepted = curve[16]["mean_accepted_target_tokens"]
    threshold = cost["service_model"]["threshold"]
    result = {
        "schema_version": 1,
        "classification": "disjoint_holdout_head_result",
        "pass": accepted >= threshold["mean_accepted_target_tokens"],
        "seed": args.seed,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "train_examples": len(train_rows),
        "holdout_examples": len(holdout_rows),
        "split_sha256": sha256(args.split),
        "cost_model_sha256": sha256(args.cost_model),
        "capture_manifest": capture_manifest,
        "tied_weight": {
            "path": str(args.tied_weight),
            "sha256": sha256(args.tied_weight),
            "key": args.weight_key,
        },
        "checkpoint": {
            "path": str(checkpoint),
            "sha256": sha256(checkpoint),
        },
        "training_loss_first": losses[0],
        "training_loss_last": losses[-1],
        "acceptance_curve": curve,
        "required_mean_accepted_target_tokens": threshold[
            "mean_accepted_target_tokens"
        ],
        "semantic_scope": (
            "draft proposals only; target verifier, accepted tokens, bonus token, "
            "KV compaction/commit, and subsequent target execution are unchanged"
        ),
    }
    atomic_json(args.artifact_root / "HOLDOUT_RESULT.json", result)
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
