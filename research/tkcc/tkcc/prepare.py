"""Prepare tier model directories and the prompt workload on the GPU host."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from tkcc import workload

LAYER_KEY = re.compile(r"(?:^|\.)layers\.(\d+)\.")


def truncate_text_config(config: dict, layers: int) -> dict:
    """Return a copy of a DeepSeek V4.1 config that keeps the first ``layers`` layers.

    Cross-layer references (shared KV, indexer sources, candidate filter,
    Engram tables) are filtered to layers that still exist.
    """
    config = json.loads(json.dumps(config))
    text = config["text_config"]
    total = text["num_hidden_layers"]
    if not 0 < layers <= total:
        raise ValueError(f"layers must be in 1..{total}")
    if layers == total:
        return config
    extra = len(text["compress_ratios"]) - total
    text["compress_ratios"] = text["compress_ratios"][:layers] + text["compress_ratios"][total : total + extra]
    text["num_hidden_layers"] = layers
    for key in ("kv_source_layer_ids", "index_source_layer_ids"):
        if key in text:
            text[key] = [layer for layer in text[key] if layer < layers]
    if text.get("candidate_source_layer_id", -1) >= layers:
        text["candidate_source_layer_id"] = -1
        text["candidate_topk_blocks"] = 0
    if "engram_layer_ids" in text:
        keep = [i for i, layer in enumerate(text["engram_layer_ids"]) if layer < layers]
        text["engram_layer_ids"] = [text["engram_layer_ids"][i] for i in keep]
        text["engram_num_embeddings"] = [text["engram_num_embeddings"][i] for i in keep]
    if "dspark_target_layer_ids" in text:
        count = len(text["dspark_target_layer_ids"])
        text["dspark_target_layer_ids"] = list(range(max(0, layers - count), layers))
    return config


def keep_weight(name: str, layers: int) -> bool:
    match = LAYER_KEY.search(name)
    return match is None or int(match.group(1)) < layers


def build_tier_dir(source: Path, target: Path, layers: int) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    config = json.loads((source / "config.json").read_text())
    (target / "config.json").write_text(json.dumps(truncate_text_config(config, layers), indent=2))
    index = json.loads((source / "model.safetensors.index.json").read_text())
    weight_map = {k: v for k, v in index["weight_map"].items() if keep_weight(k, layers)}
    (target / "model.safetensors.index.json").write_text(json.dumps({**index, "weight_map": weight_map}))
    shards = sorted(set(weight_map.values()))
    for entry in source.iterdir():
        if entry.name in ("config.json", "model.safetensors.index.json"):
            continue
        if entry.name.endswith(".safetensors") and entry.name not in shards:
            continue
        link = target / entry.name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(os.path.realpath(entry))
    return {"layers": layers, "shards": len(shards), "tensors": len(weight_map)}


def build_workload(model: Path, code_root: Path, prose_files: list[Path], out: Path, count: int, input_len: int, seed: int) -> dict:
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(model / "tokenizer.json"))

    def encode(text: str) -> list[int]:
        return tokenizer.encode(text, add_special_tokens=False).ids

    corpus = workload.Corpus.from_paths(sorted(code_root.rglob("*.py")), prose_files, seed)
    prompts = workload.build_prompt_token_ids(corpus, encode, count, input_len, seed)
    meta = {"count": count, "input_len": input_len, "seed": seed, "documents": len(corpus.documents), "source": "code+prose"}
    workload.save(out, prompts, meta)
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    tier = sub.add_parser("tier")
    tier.add_argument("--source", type=Path, required=True)
    tier.add_argument("--target", type=Path, required=True)
    tier.add_argument("--layers", type=int, required=True)
    load = sub.add_parser("workload")
    load.add_argument("--model", type=Path, required=True)
    load.add_argument("--code-root", type=Path, required=True)
    load.add_argument("--prose", type=Path, nargs="*", default=[])
    load.add_argument("--out", type=Path, required=True)
    load.add_argument("--count", type=int, default=32)
    load.add_argument("--input-len", type=int, default=32768)
    load.add_argument("--seed", type=int, default=20261107)
    args = parser.parse_args()
    if args.command == "tier":
        print(json.dumps(build_tier_dir(args.source, args.target, args.layers)))
    else:
        print(json.dumps(build_workload(args.model, args.code_root, args.prose, args.out, args.count, args.input_len, args.seed)))


if __name__ == "__main__":
    main()
