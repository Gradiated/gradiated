#!/usr/bin/env python3
"""Does the teacher's likelihood agree with the judge? Scores judged eval turns with K3 through Fireworks echo.

For each eval point, K3 scores the candidate's turn and Sonnet's reference turn in its own template (non-thinking).
Reports how well K3's mean logprob per token separates candidates the judge rated at least as good as the reference,
and how often K3 prefers the judge's winner (whole turn, and the first tool name when both call different tools).
Scoring only: nothing here trains on test points. Prints aggregates only.

    opd_teacher_agreement.py --results eval/results/vllm_qwen27b-base_n300_s0.jsonl --points 150
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

from formats import anthropic_to_openai, openai_tools  # noqa: E402
from opd_sample_score import load_k3, post  # noqa: E402
from providers import restore_required_properties  # noqa: E402
from sampling import enumerate_points, load_conversations  # noqa: E402


def message(output: dict) -> dict:
    m: dict = {"role": "assistant", "content": output.get("text") or ""}
    if output.get("tool_calls"):
        m["tool_calls"] = [{"id": f"c{i}", "type": "function",
                            "function": {"name": c["name"], "arguments": json.dumps(c.get("arguments") or {}, ensure_ascii=False)}}
                           for i, c in enumerate(output["tool_calls"])]
    return m


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--results", required=True)
    p.add_argument("--data", default="/opt/posthog-sft/eval/data/test_v2.jsonl")
    p.add_argument("--points", type=int, default=150)
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    kimi, special = load_k3(HERE)
    inverse = {v: k for k, v in special.items()}
    header = [special["<|open|>"], *kimi.encode_ordinary("message"), *kimi.encode_ordinary(" role"), *kimi.encode_ordinary('="'),
              *kimi.encode_ordinary("assistant"), *kimi.encode_ordinary('"'), special["<|sep|>"]]
    points = {pt.point_id: pt for pt in enumerate_points(load_conversations([args.data]))}
    records = [r for r in map(json.loads, open(args.results)) if "error" not in r and "judge" in r and r["point_id"] in points]
    records = sorted(records, key=lambda r: r["point_id"])[: args.points]
    headers = {"Authorization": f"Bearer {os.environ['FIREWORKS_API_KEY']}"}

    def text_of(i: int) -> str:
        return inverse.get(i) or kimi.decode_single_token_bytes(i).decode(errors="replace")

    def score(pt, output: dict) -> dict | None:
        tools = openai_tools(pt.tools)
        body = {"model": "accounts/fireworks/models/kimi-k3", "messages": anthropic_to_openai(pt.system, pt.history) + [message(output)],
                "tools": [restore_required_properties(t) for t in tools], "max_tokens": 1, "echo": True, "logprobs": True,
                "raw_output": True, "chat_template_kwargs": {"thinking": False}}
        try:
            d = post("https://api.fireworks.ai/inference/v1/chat/completions", body, headers, attempts=2)
        except RuntimeError:
            return None
        ids = d["choices"][0]["raw_output"]["prompt_token_ids"]
        lps = [c.get("logprob") or 0.0 for c in d["choices"][0]["logprobs"]["content"]]
        starts = [i for i in range(len(ids) - len(header) + 1) if ids[i : i + len(header)] == header]
        if len(starts) < 2:
            return None
        lo, hi = starts[-2] + len(header), starts[-1]
        texts = [text_of(i) for i in ids[lo:hi]]
        joined, pos = "", []
        for t in texts:
            pos.append(len(joined))
            joined += t
        name_lp = None
        k = joined.find('call tool="')
        if k >= 0:
            a = k + len('call tool="')
            b = joined.find('"', a)
            name_lp = sum(lps[lo + j] for j, s in enumerate(pos) if a <= s < b)
        return {"sum": sum(lps[lo:hi]), "tokens": hi - lo, "mean": sum(lps[lo:hi]) / max(1, hi - lo), "name": name_lp}

    def run(r):
        pt = points[r["point_id"]]
        return r, score(pt, r["candidate"]), score(pt, r["reference"])

    with ThreadPoolExecutor(args.workers) as pool:
        rows = [x for x in pool.map(run, records) if x[1] and x[2]]
    out = []
    for r, c, ref in rows:
        out.append({"point_id": r["point_id"], "verdict": r["judge"]["verdict"], "candidate": c, "reference": ref,
                    "cand_tools": [t["name"] for t in r["candidate"].get("tool_calls") or []],
                    "ref_tools": [t["name"] for t in r["reference"].get("tool_calls") or []]})
    Path(args.out).write_text("\n".join(json.dumps(o) for o in out))

    def auroc(pos: list[float], neg: list[float]) -> float:
        wins = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
        return wins / max(1, len(pos) * len(neg))

    good = [o["candidate"]["mean"] for o in out if o["verdict"] in ("better", "equivalent")]
    bad = [o["candidate"]["mean"] for o in out if o["verdict"] == "worse"]
    decided = [o for o in out if o["verdict"] in ("better", "worse")]
    agree_mean = sum((o["candidate"]["mean"] > o["reference"]["mean"]) == (o["verdict"] == "better") for o in decided)
    agree_sum = sum((o["candidate"]["sum"] > o["reference"]["sum"]) == (o["verdict"] == "better") for o in decided)
    diff_tool = [o for o in decided if o["cand_tools"] and o["ref_tools"] and o["cand_tools"][0] != o["ref_tools"][0]
                 and o["candidate"]["name"] is not None and o["reference"]["name"] is not None]
    agree_name = sum((o["candidate"]["name"] > o["reference"]["name"]) == (o["verdict"] == "better") for o in diff_tool)
    print(json.dumps({
        "scored_points": len(out),
        "auroc_candidate_mean_logprob_vs_judged_good": round(auroc(good, bad), 3), "good": len(good), "bad": len(bad),
        "pairs_decided": len(decided),
        "k3_prefers_judge_winner_by_mean_logprob": round(agree_mean / max(1, len(decided)), 3),
        "k3_prefers_judge_winner_by_total_logprob": round(agree_sum / max(1, len(decided)), 3),
        "pairs_with_different_first_tool": len(diff_tool),
        "k3_prefers_judge_winner_by_first_tool_name": round(agree_name / max(1, len(diff_tool)), 3),
    }, indent=1))


if __name__ == "__main__":
    main()
