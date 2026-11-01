#!/usr/bin/env python3
"""Teacher-generated SFT data for the student: K3 answers training prefixes, rendered in the student's format.

For each anonymized training prefix, K3 (Fireworks, non-thinking) writes the next assistant turn. The turn is
rendered in Qwen's chat format (text, then <tool_call> blocks, then <|im_end|>) and tokenized with Qwen's tokenizer;
the prompt token ids come from the student's vLLM server, so training sees exactly what serving sees. Rows use the
opd_train.py format with every completion token scored (train with --sft).

    opd_teacher_sft_data.py --prefixes 1000 --samples 1 --out runs/sft-k3/data.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, "/opt/posthog-sft/eval")
sys.path.insert(0, str(HERE))

from formats import anthropic_to_openai, openai_tools  # noqa: E402
from opd_sample_score import QWEN_DIR, post  # noqa: E402
from providers import restore_required_properties  # noqa: E402
from sampling import _clean, enumerate_points  # noqa: E402
from tokenizers import Tokenizer  # noqa: E402

IM_END = 248046


def qwen_completion(content: str, calls: list[dict]) -> str:
    """The assistant turn as Qwen 3.8's chat template renders it after `<think>\\n\\n</think>\\n\\n`."""
    text = content.strip()
    for i, call in enumerate(calls):
        if i == 0:
            text += "\n\n<tool_call>\n" if text else "<tool_call>\n"
        else:
            text += "\n<tool_call>\n"
        text += f"<function={call['name']}>\n"
        for key, value in call["arguments"].items():
            rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            text += f"<parameter={key}>\n{rendered}\n</parameter>\n"
        text += "</function>\n</tool_call>"
    return text


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="/opt/posthog-sft/root_agent/data_all/train.jsonl")
    p.add_argument("--prefixes", type=int, default=1000)
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--max-prompt-tokens", type=int, default=32000)
    p.add_argument("--teacher", default="accounts/fireworks/models/kimi-k3")
    p.add_argument("--student", default="qwen27b-base")
    p.add_argument("--seed", type=int, default=2000)
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    with open(args.data) as f:
        conversations = [_clean(json.loads(line), default_id=f"train:{i}") for i, line in enumerate(f) if line.strip()]
    points = enumerate_points(conversations)
    random.Random(args.seed).shuffle(points)
    tok = Tokenizer.from_file(str(QWEN_DIR / "tokenizer.json"))
    fireworks = {"Authorization": f"Bearer {os.environ['FIREWORKS_API_KEY']}"}
    stats: Counter = Counter()

    def run(pt) -> list[dict]:
        tools = openai_tools(pt.tools)
        messages = anthropic_to_openai(pt.system, pt.history)
        try:
            prompt = post("http://127.0.0.1:18000/v1/chat/completions",
                          {"model": args.student, "messages": messages, "tools": tools, "tool_choice": "none", "max_tokens": 1,
                           "return_token_ids": True, "chat_template_kwargs": {"enable_thinking": False}}, {}, attempts=2)
        except RuntimeError:
            stats["student_template_error"] += 1
            return []
        prompt_ids = prompt["prompt_token_ids"]
        if len(prompt_ids) > args.max_prompt_tokens:
            stats["prompt_too_long"] += 1
            return []
        try:
            response = post("https://api.fireworks.ai/inference/v1/chat/completions",
                            {"model": args.teacher, "messages": messages, "tools": [restore_required_properties(t) for t in tools],
                             "n": args.samples, "temperature": args.temperature, "max_tokens": 2048,
                             "chat_template_kwargs": {"thinking": False}}, fireworks)
        except RuntimeError:
            stats["teacher_error"] += 1
            return []
        for k, v in (response.get("usage") or {}).items():
            if isinstance(v, int):
                stats[f"teacher_{k}"] += v
        rows = []
        for choice in response["choices"]:
            if choice.get("finish_reason") not in ("stop", "tool_calls"):
                stats["teacher_truncated"] += 1
                continue
            m = choice["message"]
            calls = []
            try:
                for c in m.get("tool_calls") or []:
                    args_ = c["function"].get("arguments") or "{}"
                    calls.append({"name": c["function"]["name"], "arguments": json.loads(args_) if isinstance(args_, str) else args_})
            except (ValueError, KeyError):
                stats["teacher_bad_arguments"] += 1
                continue
            text = qwen_completion(m.get("content") or "", calls)
            ids = tok.encode(text, add_special_tokens=False).ids + [IM_END]
            rows.append({"status": "ok", "point_id": pt.point_id, "prompt_token_ids": prompt_ids, "token_ids": ids,
                         "advantages": [1.0] * len(ids), "sampler_logprobs": [0.0] * len(ids), "covered": len(ids),
                         "calls": len(calls)})
            stats["rows"] += 1
        return rows

    with ThreadPoolExecutor(args.workers) as pool, open(args.out, "w") as f:
        for rows in pool.map(run, points[: args.prefixes]):
            for row in rows:
                f.write(json.dumps(row) + "\n")
    print(json.dumps(dict(stats), indent=1))


if __name__ == "__main__":
    main()
