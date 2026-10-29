#!/usr/bin/env python3
"""Can the teacher pick the better of the student's own samples? Best-of-n on dev prefixes, judged and teacher-scored.

For each dev prefix, the student samples n next turns. Every sample is judged against Sonnet's recorded turn (both
orders, as in run_eval.py) and scored by K3 (mean logprob per token of its own rendering, non-thinking, Fireworks
echo). Reports single-sample, judge best-of-n (headroom) and K3 best-of-n rates of "at least as good as Sonnet",
and within-group agreement between K3's ranking and the judge. Dev split only; prints aggregates.

    opd_group_ranking.py --prefixes 60 --samples 8 --out diag/group-base.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, "/opt/posthog-sft/eval")
sys.path.insert(0, str(HERE))

from formats import anthropic_to_openai, openai_tools, output_from_anthropic_blocks, tool_schemas  # noqa: E402
from opd_sample_score import param_types, post  # noqa: E402
from opd_teacher_agreement import message  # noqa: E402
from providers import OpenAIResponses, restore_required_properties  # noqa: E402
from run_eval import JudgeOptions, judge_record  # noqa: E402
from sampling import _clean, enumerate_points  # noqa: E402
from scoring import action_match, args_similarity, validity  # noqa: E402
from xtok_distill import ParseError, parse_qwen_output  # noqa: E402

from opd_sample_score import load_k3  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="/opt/posthog-sft/root_agent/data_all/dev.jsonl")
    p.add_argument("--student", default="qwen27b-base")
    p.add_argument("--prefixes", type=int, default=60)
    p.add_argument("--samples", type=int, default=8)
    p.add_argument("--max-prompt-tokens", type=int, default=32000)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--same-tokenizer-teacher", default="", help="also score with this same-tokenizer teacher (completions echo)")
    p.add_argument("--skip-k3-extras", action="store_true", help="skip K3 reasoning and hint scorers")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    with open(args.data) as f:
        conversations = [_clean(json.loads(line), default_id=f"dev:{i}") for i, line in enumerate(f) if line.strip()]
    points = enumerate_points(conversations)
    random.Random(7).shuffle(points)
    judge = OpenAIResponses("gpt-6.1-sol", 120, None)
    options = JudgeOptions("gpt-6.1-sol", reference_faithfulness=False)
    kimi, special = load_k3(HERE)
    header = [special["<|open|>"], *kimi.encode_ordinary("message"), *kimi.encode_ordinary(" role"), *kimi.encode_ordinary('="'),
              *kimi.encode_ordinary("assistant"), *kimi.encode_ordinary('"'), special["<|sep|>"]]
    fireworks = {"Authorization": f"Bearer {os.environ['FIREWORKS_API_KEY']}"}

    think_close = [special["<|close|>"], *kimi.encode_ordinary("think"), special["<|sep|>"]]

    def k3_reasoning(pt) -> str | None:
        """K3's own thinking for this prefix (thinking mode), used as privileged context when scoring."""
        body = {"model": "accounts/fireworks/models/kimi-k3", "messages": anthropic_to_openai(pt.system, pt.history),
                "tools": [restore_required_properties(t) for t in openai_tools(pt.tools)], "max_tokens": 3000,
                "temperature": 0.6, "reasoning_effort": "high"}
        try:
            d = post("https://api.fireworks.ai/inference/v1/chat/completions", body, fireworks, attempts=2)
        except RuntimeError:
            return None
        m = d["choices"][0]["message"]
        return m.get("reasoning_content") or m.get("reasoning") or None

    def k3_mean(pt, output: dict, mode: str = "plain", reasoning: str | None = None, hint: str | None = None) -> float | None:
        messages = anthropic_to_openai(pt.system, pt.history)
        if hint:
            messages = messages + [{"role": "system", "content": "For reference, a strong next step at this point was:\n\n" + hint}]
        final = message(output)
        if mode == "reasoning":
            final = {**final, "reasoning_content": reasoning}
        body = {"model": "accounts/fireworks/models/kimi-k3",
                "messages": messages + [final],
                "tools": [restore_required_properties(t) for t in openai_tools(pt.tools)], "max_tokens": 1, "echo": True,
                "logprobs": True, "raw_output": True, "chat_template_kwargs": {"thinking": mode == "reasoning"}}
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
        if mode == "reasoning":  # score only the turn after K3's own reasoning
            after = [i for i in range(lo, hi - len(think_close) + 1) if ids[i : i + len(think_close)] == think_close]
            if not after:
                return None
            lo = after[0] + len(think_close)
        return sum(lps[lo:hi]) / max(1, hi - lo)

    def same_tok_mean(prompt_ids: list[int], ids: list[int]) -> float | None:
        body = {"model": args.same_tokenizer_teacher, "prompt": prompt_ids + ids, "max_tokens": 1, "echo": True, "logprobs": 1}
        try:
            d = post("https://api.fireworks.ai/inference/v1/completions", body, fireworks, attempts=2)
        except RuntimeError:
            return None
        lp = d["choices"][0]["logprobs"]["token_logprobs"][len(prompt_ids) : len(prompt_ids) + len(ids)]
        return sum(x or 0.0 for x in lp) / max(1, len(ids))

    def run(pt) -> dict | None:
        tools = openai_tools(pt.tools)
        body = {"model": args.student, "messages": anthropic_to_openai(pt.system, pt.history), "tools": tools,
                "tool_choice": "none", "n": args.samples, "temperature": 1.0, "max_tokens": 2048, "logprobs": True,
                "return_token_ids": True, "chat_template_kwargs": {"enable_thinking": False}}
        try:
            response = post("http://127.0.0.1:18000/v1/chat/completions", body, {}, attempts=2)
        except RuntimeError:
            return None
        if len(response["prompt_token_ids"]) > args.max_prompt_tokens:
            return None
        reference = output_from_anthropic_blocks(pt.reference.get("content"))
        schemas = tool_schemas(pt.tools)
        reasoning = None if args.skip_k3_extras else k3_reasoning(pt)
        hint = reference["text"] + "".join(f"\n[tool call] {c['name']}({json.dumps(c.get('arguments'), ensure_ascii=False)})"
                                           for c in reference["tool_calls"])
        samples = []
        for choice in response["choices"]:
            text = choice["message"]["content"] or ""
            try:
                turn, _ = parse_qwen_output(text, param_types=param_types(tools))
            except (ParseError, ValueError):
                samples.append({"parse_error": True})
                continue
            output = {"text": turn.content.strip(), "tool_calls": [
                {"name": c.name, "arguments": {a.key: (a.text if a.is_string else json.loads(a.text)) for a in c.arguments},
                 "raw": ""} for c in turn.calls]}
            record = {"point_id": pt.point_id, "stratum": pt.stratum, "candidate": output, "reference": reference,
                      "finish": choice["finish_reason"], "validity": validity(output, schemas, choice["finish_reason"]),
                      "action_match": action_match(output, reference), "args_similarity": args_similarity(output, reference)}
            try:
                judged = judge_record(record, pt, judge, options)
                verdict = judged["judge"]["verdict"]
            except Exception:  # noqa: BLE001
                verdict = None
            student = [c["logprob"] for c in choice["logprobs"]["content"]]
            k3 = k3_mean(pt, output)
            samples.append({"verdict": verdict, "k3_mean": k3, "valid": record["validity"]["valid"],
                            "k3_reasoning": k3_mean(pt, output, "reasoning", reasoning=reasoning) if reasoning else None,
                            "k3_hint": None if args.skip_k3_extras else k3_mean(pt, output, hint=hint),
                            "teacher_same": same_tok_mean(response["prompt_token_ids"], choice["token_ids"]) if args.same_tokenizer_teacher else None,
                            "student_mean": sum(student) / max(1, len(student)),
                            "log_ratio": None if k3 is None else k3 - sum(student) / max(1, len(student)),
                            "tools": [c["name"] for c in output["tool_calls"]], "output": output})
        for smp in samples:
            if smp.get("teacher_same") is not None:
                smp["teacher_same_ratio"] = smp["teacher_same"] - smp["student_mean"]
        return {"point_id": pt.point_id, "stratum": pt.stratum, "samples": samples}

    with ThreadPoolExecutor(args.workers) as pool:
        groups = [g for g in pool.map(run, points[: args.prefixes]) if g]
    Path(args.out).write_text("\n".join(json.dumps(g) for g in groups))

    def ok(s):
        return s.get("verdict") in ("better", "equivalent") and s.get("valid")

    single = judge_best = 0.0
    report = {"groups": 0}
    for key in ("k3_mean", "k3_reasoning", "k3_hint", "log_ratio", "student_mean", "teacher_same", "teacher_same_ratio"):
        usable = [[s for s in g["samples"] if s.get("verdict") and s.get(key) is not None] for g in groups]
        usable = [u for u in usable if len(u) >= 2]
        if not usable:
            continue
        pairs = agree = 0
        for u in usable:
            for i, a in enumerate(u):
                for b in u[i + 1:]:
                    if ok(a) != ok(b) and a[key] != b[key]:
                        pairs += 1
                        agree += (a[key] > b[key]) == ok(a)
        report[key] = {"groups": len(usable), "best_of_n": round(sum(ok(max(u, key=lambda s: s[key])) for u in usable) / len(usable), 3),
                       "worst_of_n": round(sum(ok(min(u, key=lambda s: s[key])) for u in usable) / len(usable), 3),
                       "pairwise_agreement": round(agree / max(1, pairs), 3), "mixed_pairs": pairs}
        if key == "k3_mean":
            report["groups"] = len(usable)
            report["single_sample_ge_rate"] = round(sum(sum(map(ok, u)) / len(u) for u in usable) / len(usable), 3)
            report["judge_best_of_n"] = round(sum(any(map(ok, u)) for u in usable) / len(usable), 3)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
