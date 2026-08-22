#!/usr/bin/env python3
"""Render immutable agent traces into token IDs for native-engine quality evaluation."""

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

from transformers import AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--prompts", type=int, default=16)
    parser.add_argument("--maximum-tokens", type=int, default=8159)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    prompts: list[dict[str, object]] = []
    with Path(args.input).open(encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            messages = record["messages"]
            assistant_indices = [
                index for index, message in enumerate(messages) if message["role"] == "assistant"
            ]
            if not assistant_indices:
                continue
            context = messages[: assistant_indices[-1]]
            rendered = tokenizer.apply_chat_template(
                context, tokenize=True, add_generation_prompt=True
            )
            input_ids = rendered["input_ids"] if isinstance(rendered, Mapping) else rendered
            if input_ids and isinstance(input_ids[0], list):
                input_ids = input_ids[0]
            if not input_ids or len(input_ids) > args.maximum_tokens:
                continue
            prompts.append({"id": record["session_id"], "input_ids": input_ids})
            if len(prompts) == args.prompts:
                break
    if len(prompts) != args.prompts:
        raise RuntimeError(f"only {len(prompts)} qualifying prompts found")
    Path(args.output).write_text(
        json.dumps({"model": args.model, "prompts": prompts}, separators=(",", ":")),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
