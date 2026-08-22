#!/usr/bin/env python3
"""Build a deterministic model-neutral replay workload from public agent traces."""

from __future__ import annotations

import argparse
import json
import random
import urllib.parse
import urllib.request
from pathlib import Path


DATASET = "thoughtworks/agentic-coding-trajectories"
ROWS_ENDPOINT = "https://datasets-server.huggingface.co/rows"


def fetch_rows(dataset: str, offset: int, length: int) -> list[dict[str, object]]:
    query = urllib.parse.urlencode(
        {
            "dataset": dataset,
            "config": "default",
            "split": "train",
            "offset": offset,
            "length": length,
        }
    )
    with urllib.request.urlopen(f"{ROWS_ENDPOINT}?{query}", timeout=60) as response:
        payload = json.load(response)
    return [item["row"] for item in payload["rows"]]


def as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def normalize_messages(raw_messages: list[dict[str, object]]) -> list[dict[str, str]]:
    """Normalize traces to alternating system/user/assistant OpenAI messages.

    Tool results become user observations and structured calls become assistant
    text. This keeps the performance workload portable across model templates;
    tool-schema correctness is measured by a separate quality benchmark.
    """
    normalized: list[dict[str, str]] = []
    for raw in raw_messages:
        raw_role = str(raw.get("role") or "user").lower()
        role = {
            "ai": "assistant",
            "human": "user",
            "observation": "user",
            "tool": "user",
        }.get(raw_role, raw_role)
        if role not in {"system", "user", "assistant"}:
            role = "user"

        content = as_text(raw.get("content"))
        tool_calls = raw.get("tool_calls") or raw.get("tool_calls_json")
        if tool_calls and tool_calls != "null":
            content += "\n<tool_calls>\n" + as_text(tool_calls) + "\n</tool_calls>"
        tool_call_id = raw.get("tool_call_id")
        if tool_call_id:
            content = f"<tool_result id={tool_call_id}>\n{content}\n</tool_result>"
        if not content.strip():
            continue

        if role == "system" and normalized:
            role = "user"
        if normalized and normalized[-1]["role"] == role:
            normalized[-1]["content"] += "\n\n" + content
        else:
            normalized.append({"role": role, "content": content})

    # A replay request is the history immediately before an assistant message.
    # Drop malformed leading assistant turns and trailing non-request material.
    while normalized and normalized[0]["role"] == "assistant":
        normalized.pop(0)
    return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=DATASET)
    parser.add_argument("--offset", type=int, default=50)
    parser.add_argument("--candidate-count", type=int, default=650)
    parser.add_argument("--sessions", type=int, default=64)
    parser.add_argument("--min-isl", type=int, default=4500)
    parser.add_argument("--max-isl", type=int, default=6800)
    parser.add_argument("--min-turns", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260822)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidates: list[dict[str, object]] = []
    remaining = args.candidate_count
    offset = args.offset
    while remaining:
        batch_size = min(100, remaining)
        rows = fetch_rows(args.dataset, offset, batch_size)
        if not rows:
            break
        candidates.extend(rows)
        offset += len(rows)
        remaining -= len(rows)

    eligible = [
        row
        for row in candidates
        if args.min_isl <= int(row["max_isl"]) <= args.max_isl
        and int(row["n_turns"]) >= args.min_turns
    ]
    random.Random(args.seed).shuffle(eligible)
    selected = eligible[: args.sessions]
    if len(selected) < args.sessions:
        raise RuntimeError(
            f"only {len(selected)} eligible sessions; requested {args.sessions}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as workload:
        for row in selected:
            raw_messages = json.loads(str(row["messages_json"]))
            record = {
                "session_id": row["session_id"],
                "source_dataset": row["source_dataset"],
                "source_id": row["source_id"],
                "agent_framework": row["agent_framework"],
                "recorded_model": row["recorded_model"],
                "source_max_isl_cl100k": row["max_isl"],
                "messages": normalize_messages(raw_messages),
            }
            workload.write(json.dumps(record, ensure_ascii=False) + "\n")

    manifest_path = args.output.with_suffix(args.output.suffix + ".manifest.json")
    manifest = {
        "dataset": args.dataset,
        "dataset_url": f"https://huggingface.co/datasets/{args.dataset}",
        "dataset_revision": "main",
        "selection": {
            "offset": args.offset,
            "candidate_count": args.candidate_count,
            "sessions": args.sessions,
            "min_isl_cl100k": args.min_isl,
            "max_isl_cl100k": args.max_isl,
            "min_turns": args.min_turns,
            "seed": args.seed,
        },
        "session_ids": [row["session_id"] for row in selected],
        "format": "OpenAI system/user/assistant messages; tool events flattened to text",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "manifest": str(manifest_path),
                "sessions": len(selected),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
