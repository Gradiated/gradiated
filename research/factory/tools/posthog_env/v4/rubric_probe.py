"""Synthetic final-answer interventions on an observed rollout; never a model benchmark.

Keep executed tool work fixed. Test whether the current judge accepts a shortest user-complete answer and
rejects wrong numbers and non-answers. A failed minimal variant needs semantic review, not automatic approval
or rejection of the rubric. Run on fbf8; output contains traces and must remain on the host.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import sys


def final_indices(messages: list[dict]) -> list[int]:
    segments = []
    for i, message in enumerate(messages):
        if message.get("type") == "HumanMessage":
            segments.append([])
        if segments:
            segments[-1].append(i)
    indices = []
    for segment in segments:
        found = next((i for i in reversed(segment) if messages[i].get("type") == "AssistantMessage"
                      and isinstance(messages[i].get("content"), str) and messages[i]["content"].strip()
                      and not messages[i].get("tool_calls")), None)
        if found is None:
            raise ValueError("Every user segment must have a final answer")
        indices.append(found)
    if not indices:
        raise ValueError("No user/final-answer segments")
    return indices


def replace_answers(trace: dict, answers: list[str]) -> dict:
    out = copy.deepcopy(trace)
    indices = final_indices(out["messages"])
    if len(indices) != len(answers):
        raise ValueError("Final-answer count mismatch")
    for i, answer in zip(indices, answers):
        out["messages"][i]["content"] = answer
    if "final_answers" in out:
        out["final_answers"] = answers
    if "final_answer" in out:
        out["final_answer"] = answers[-1]
    return out


NUMBER = re.compile(r"(?<![\w/])\d+(?:,\d{3})*(?:\.\d+)?(?![\w/])")
URL = re.compile(r"https?://[^\s)]+")


def wrong_numbers(answer: str) -> str:
    links = [m.span() for m in URL.finditer(answer)]
    changed = 0

    def rewrite(match):
        nonlocal changed
        value = float(match.group().replace(",", ""))
        if any(a <= match.start() < b for a, b in links) or value == 0 or 1900 <= value <= 2100:
            return match.group()
        if value.is_integer() and value <= 31:
            return match.group()
        changed += 1
        return str(round(value * 1.37, 5)) if "." in match.group() else str(round(value * 1.37))

    result = NUMBER.sub(rewrite, answer)
    if not changed or result == answer:
        raise ValueError("No suitable numeric findings to corrupt")
    return result


def parse_answers(text: str, count: int) -> list[str]:
    decoder, offset = json.JSONDecoder(), 0
    while (start := text.find("[", offset)) >= 0:
        try:
            value, offset = decoder.raw_decode(text, start)
            if isinstance(value, list) and len(value) == count and all(isinstance(v, str) and v.strip() for v in value):
                return value
        except ValueError:
            offset = start + 1
    raise ValueError("No valid rewritten answer list")


def passes(result: dict) -> bool:
    return (result.get("overall") is not None and result["overall"] >= 7.5
            and result.get("material_wrong_final") == 0 and result.get("material_unsupported_final") == 0)


def complete_judgement(result: dict) -> bool:
    score = result.get("overall")
    return (not result.get("error") and isinstance(score, (int, float)) and not isinstance(score, bool)
            and math.isfinite(score) and 0 <= score <= 10
            and all(isinstance(result.get(k), int) and result[k] >= 0
                    for k in ("material_wrong_final", "material_unsupported_final")))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--tasks", type=Path, required=True)
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--judge", default="judge_v3i")
    a = ap.parse_args()
    sys.path[:0] = ["/opt/posthog-env/runner", "/opt/posthog-env/runner/judge_v3", "/opt/posthog-env"]
    import llm_proxy

    judge = importlib.import_module(a.judge)
    task = next(t for t in map(json.loads, a.tasks.read_text().splitlines()) if t["task_id"] == a.task_id)
    trace = json.loads(a.trace.read_text())
    indices = final_indices(trace["messages"])
    originals = [trace["messages"][i]["content"] for i in indices]
    a.out.mkdir(parents=True, exist_ok=True)
    identity = hashlib.sha256(a.trace.read_bytes() + json.dumps(task, sort_keys=True).encode()
                              + a.judge.encode() + Path(__file__).read_bytes()).hexdigest()
    minimal_path = a.out / "minimal_user_only.answers.json"
    cached = json.loads(minimal_path.read_text()) if minimal_path.exists() else {}
    minimal = cached.get("answers") if isinstance(cached, dict) and cached.get("input_key") == identity else None
    if minimal is None:
        prompt = ("Rewrite each final answer as the SHORTEST faithful answer that fully answers what the user "
                  "explicitly requested. Preserve every necessary finding, number, qualification and conclusion; "
                  "omit unasked supporting details. Do not invent or alter facts. No grading rubric is provided. "
                  "Return ONLY a JSON list of rewritten answer strings in turn order.\n\n" +
                  json.dumps({"user_turns": task["turns"], "answers": originals}))
        text, _ = llm_proxy.judge_complete(prompt, "gpt-6.1-terra", attempts=2, timeout=120, preamble=False)
        minimal = parse_answers(text, len(indices))
        minimal_path.write_text(json.dumps({"input_key": identity, "answers": minimal}))
    variants = {"original": originals, "minimal_user_only": minimal,
                "wrong_numbers": [wrong_numbers(x) for x in originals],
                "clarify_only": ["Which scope and definition should I use?" for _ in originals],
                "process_only": ["I would query the relevant data, compare the periods and explain the findings." for _ in originals]}
    results = {}
    for name, answers in variants.items():
        path = a.out / f"{name}.judge.json"
        result = json.loads(path.read_text()) if path.exists() else None
        if not result or result.get("input_key") != identity or not complete_judgement(result):
            variant = replace_answers(trace, answers)
            variant["grading_notes"] = task.get("grading_notes")
            (a.out / f"{name}.trace.json").write_text(json.dumps(variant))
            result = judge.score_transcript(variant, "gpt-6.1-sol")
            result.update({"input_key": identity, "evidence": "synthetic final-answer intervention", "variant": name})
            path.write_text(json.dumps(result, indent=2))
        if not complete_judgement(result):
            raise RuntimeError(f"Incomplete judgement for {name}; not a measured acceptance/rejection")
        results[name] = {"score": result.get("overall"), "pass": passes(result)}
        print(json.dumps({"variant": name, **results[name]}), flush=True)
    summary = {"evidence": "synthetic interventions on one observed trace; not model performance",
               "task_id": a.task_id, "results": results,
               "unexpected_wrong_passes": [n for n in ("wrong_numbers", "clarify_only", "process_only") if results[n]["pass"]],
               "minimal_needs_review": not results["minimal_user_only"]["pass"]}
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
