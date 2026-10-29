#!/usr/bin/env python3
"""Does a hindsight teacher rank the student's own samples better? Re-scores saved, judged group samples.

K3 sees the recorded continuation of the conversation after the cut (Sonnet's next turns and their tool results,
up to a character budget) as a system note before scoring each student sample. Compares within-group agreement
with the judge against plain K3 on the same samples. Reads opd_group_ranking.py output; prints aggregates only.

    opd_hindsight_ranking.py diag/group2-base.jsonl --out diag/hindsight.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, "/opt/posthog-sft/eval")
sys.path.insert(0, str(HERE))

from formats import anthropic_to_openai, blocks, openai_tools  # noqa: E402
from opd_sample_score import load_k3, post  # noqa: E402
from opd_teacher_agreement import message  # noqa: E402
from providers import restore_required_properties  # noqa: E402
from sampling import _clean, enumerate_points  # noqa: E402


def render_future(messages: list[dict], budget: int) -> str:
    parts = []
    for m in messages:
        for b in blocks(m.get("content")):
            if b.get("type") == "text" and b.get("text"):
                parts.append(f"[{m['role']}] {b['text']}")
            elif b.get("type") == "tool_use":
                parts.append(f"[assistant tool call] {b.get('name')}({json.dumps(b.get('input'), ensure_ascii=False)[:1500]})")
            elif b.get("type") == "tool_result":
                content = b.get("content")
                text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                parts.append(f"[tool result] {text[:1500]}")
    out, used = [], 0
    for part in parts:
        if used + len(part) > budget:
            break
        out.append(part)
        used += len(part)
    return "\n".join(out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("groups", nargs="+")
    p.add_argument("--data", default="/opt/posthog-sft/root_agent/data_all/dev.jsonl")
    p.add_argument("--budget", type=int, default=12000, help="characters of recorded continuation shown to the teacher")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    with open(args.data) as f:
        conversations = [_clean(json.loads(line), default_id=f"dev:{i}") for i, line in enumerate(f) if line.strip()]
    by_id = {c["id"]: c for c in conversations}
    points = {pt.point_id: pt for pt in enumerate_points(conversations)}
    kimi, special = load_k3(HERE)
    header = [special["<|open|>"], *kimi.encode_ordinary("message"), *kimi.encode_ordinary(" role"), *kimi.encode_ordinary('="'),
              *kimi.encode_ordinary("assistant"), *kimi.encode_ordinary('"'), special["<|sep|>"]]
    fireworks = {"Authorization": f"Bearer {os.environ['FIREWORKS_API_KEY']}"}

    def k3_future(pt, output, future: str) -> float | None:
        note = ("Hindsight for scoring: this is what actually happened next in the recorded conversation "
                "(the assistant's following steps and the tool results). Use it to judge the next step.\n\n" + future)
        body = {"model": "accounts/fireworks/models/kimi-k3",
                "messages": anthropic_to_openai(pt.system, pt.history) + [{"role": "system", "content": note}, message(output)],
                "tools": [restore_required_properties(t) for t in openai_tools(pt.tools)], "max_tokens": 1, "echo": True,
                "logprobs": True, "raw_output": True, "chat_template_kwargs": {"thinking": False}}
        try:
            d = post("https://api.fireworks.ai/inference/v1/chat/completions", body, fireworks, attempts=2)
        except RuntimeError:
            return None
        ids = d["choices"][0]["raw_output"]["prompt_token_ids"]
        lps = [c.get("logprob") or 0.0 for c in d["choices"][0]["logprobs"]["content"]]
        starts = [i for i in range(len(ids) - len(header) + 1) if ids[i : i + len(header)] == header]
        if len(starts) < 2:
            return None
        lo, hi = starts[-2] + len(header), starts[-1]
        return sum(lps[lo:hi]) / max(1, hi - lo)

    groups = [json.loads(line) for path in args.groups for line in open(path) if line.strip()]

    def run(g):
        pt = points.get(g["point_id"])
        if pt is None:
            return g
        conv = by_id[pt.conversation_id]
        future = render_future(conv["messages"][pt.cut + 1 :], args.budget)
        for s in g["samples"]:
            if "output" in s and s.get("verdict"):
                s["k3_future"] = k3_future(pt, s["output"], future) if future else None
        return g

    with ThreadPoolExecutor(12) as pool:
        groups = list(pool.map(run, groups))
    Path(args.out).write_text("\n".join(json.dumps(g) for g in groups))

    def ok(s):
        return s.get("verdict") in ("better", "equivalent") and s.get("valid")

    report = {}
    for key in ("k3_mean", "k3_future"):
        pairs = agree = 0
        for g in groups:
            u = [s for s in g["samples"] if s.get("verdict") and s.get(key) is not None and s.get("k3_future") is not None]
            for i, a in enumerate(u):
                for b in u[i + 1:]:
                    if ok(a) != ok(b) and a[key] != b[key]:
                        pairs += 1
                        agree += (a[key] > b[key]) == ok(a)
        report[key] = {"mixed_pairs": pairs, "pairwise_agreement": round(agree / max(1, pairs), 3)}
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
