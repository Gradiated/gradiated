"""Judge v3: graded, severity-aware scoring of one PostHog AI rollout in the synthetic environment.

Runs on fbf8 (PostHog venv path for runner imports). Reuses the runner's trajectory renderer with larger evidence
budgets. The judge returns five 0-10 dimension scores with short reasons and a list of errors with severity; the
overall score is a fixed weighted mean, so no single flag can zero a rollout.

    env_judge_v3.py --models qwen opus --tasks <id> ... [--judge gpt-6.1-sol] [--tag v3c]

Checked on 18 rollouts: gpt-6.1-sol twice Spearman 0.95, gpt-6.1-sol vs gpt-6-sol 0.91; same Opus-vs-Qwen
direction on 9 of 9 tasks in both comparisons (the v2 item rubric zeroed most of these rollouts).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

R = "/opt/posthog-env/runner"
sys.path.insert(0, R)
from abs_common import project_block, render_trajectory, turns_block, user_turns  # noqa: E402

WEIGHTS = {"outcome": 0.40, "evidence": 0.20, "analysis": 0.20, "process": 0.10, "communication": 0.10}

PROMPT = """You are a senior product analyst reviewing how well PostHog AI (an agent that answers questions about a
PostHog project by calling tools: taxonomy lookups, HogQL queries, insights, recordings, etc.) helped a user.
Judge the rollout the way an expert reviewer would judge a colleague's work: what matters is whether the user ends up
with a correct, useful answer, reached by sound analysis, honestly stated.

## Project
{project}

## User messages (a multi-turn conversation; later messages may react to earlier answers)
{turns}

## Rollout (tool calls, tool results, and the final answer after each user message)
{trajectory}

## How to read the evidence
- Tool results may be shortened ("...[N characters omitted]"). A number or fact that could be in an omitted part is
  UNVERIFIABLE, not unsupported: do not penalise it unless something visible contradicts it.
- The environment is a simulated copy of the user's project. If an object, table or historical event the user mentions
  is genuinely missing, the best response says so plainly, offers the closest real alternative, and does not pretend.
- Proving absence: a proportionate, clearly scoped search (e.g. checked the full data range, searched names and
  properties) is enough. Do not demand exhaustive proof over every conceivable name or time.

## First, in one or two sentences, state what a correct, complete answer to the user's requests required (the
## "target"), given what the data and tools could actually provide. Score against that target.

## Score five dimensions, 0-10 each (10 = what a strong expert would deliver; 5 = usable but with clear gaps;
## 0 = useless or misleading)
1. outcome: does the final state of the conversation give the user what they asked for, correct and complete? Weight
   the user's main request and the latest turns most; an early-turn slip that was later fixed matters little.
2. evidence: are the answer's key numbers and claims backed by the tool results, with speculation labelled as such?
   Numbers that contradict the agent's own results, or invented findings, are severe.
3. analysis: did the agent pick the right events/properties/tables, date ranges, timezones, aggregations and filters;
   check premises (e.g. how far back data goes, whether the named object exists); interpret results correctly?
4. process: efficient, purposeful tool use; recovered from errors; no pointless repetition or loops.
5. communication: clear, direct, appropriately concise, in the user's language, with the key answer up front.

## Errors
List every concrete error, each with severity:
- "material": changes what the user would conclude or do (wrong key number, wrong entity, misrepresented failure,
  invented cause stated as fact, answered a different question).
- "moderate": real flaw that weakens the answer but not its main conclusion (missing part of the question, unclear
  scope, avoidable inefficiency with impact).
- "minor": wording, small imprecision, harmless over-generalisation.
Misrepresenting what was found (presenting a substitute as the requested object, hiding a failed lookup, claiming a
check that was not run) is material. A hypothesis clearly labelled as a hypothesis, or an analysis choice the agent
states openly (e.g. "I counted users active in the last year"), is at most moderate. For each error say whether a
later turn corrected it and whether it affects the final answer the user is left with.

Calibrate: reserve 9-10 for genuinely excellent work and 0-2 for useless or misleading work. Do not reward length.
Two rollouts of different quality should get clearly different scores.

Respond with ONLY a JSON object:
{{"target": "<what a correct, complete answer required>",
 "outcome": {{"score": <0-10>, "reason": "<one sentence>"}},
 "evidence": {{"score": <0-10>, "reason": "<one sentence>"}},
 "analysis": {{"score": <0-10>, "reason": "<one sentence>"}},
 "process": {{"score": <0-10>, "reason": "<one sentence>"}},
 "communication": {{"score": <0-10>, "reason": "<one sentence>"}},
 "errors": [{{"severity": "material|moderate|minor", "turn": <n>, "corrected_later": <true|false>, "affects_final_answer": <true|false>, "what": "<short>"}}],
 "summary": "<two sentences: what the agent did well and what most limits the score>"}}"""


def relay(prompt: str, model: str, effort: str | None = None) -> str:
    body = json.dumps({"prompt": prompt, "model": model, "reasoning_effort": effort}).encode()
    for attempt in range(8):
        try:
            req = urllib.request.Request("http://127.0.0.1:18777/complete", body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=900) as r:
                d = json.load(r)
            if d.get("text"):
                return d["text"]
        except Exception:  # noqa: BLE001
            pass
        time.sleep(min(60, 3 * 2 ** attempt))
    raise RuntimeError("relay failed")


def parse(text: str) -> dict:
    s, e = text.find("{"), text.rfind("}")
    return json.loads(text[s:e + 1])


def judge(model: str, task_id: str, judge_model: str, tag: str) -> dict:
    out = f"{R}/judge_v3/out/{tag}/{judge_model}/{model}/{task_id}.json"
    if os.path.exists(out):
        return json.load(open(out))
    tr = json.load(open(f"{R}/runs/{model}/{task_id}.json"))
    prompt = PROMPT.format(project=project_block(tr), turns=turns_block(user_turns(tr)),
                           trajectory=render_trajectory(tr, max_result=14000, max_args=3000, max_answer=16000, max_total=260000))
    d = parse(relay(prompt, judge_model))
    dims = {k: float(d[k]["score"]) for k in WEIGHTS}
    live = [e for e in d.get("errors", []) if e.get("severity") == "material" and not e.get("corrected_later")]
    final = sum(1 for e in live if e.get("affects_final_answer", True))
    earlier = len(live) - final
    cap = 10.0 if final == 0 else 5.0 if final == 1 else 3.0  # material errors in the final answer cap outcome/evidence
    for k in ("outcome", "evidence"):
        dims[k] = min(dims[k], cap)
    dims["evidence"] = max(0.0, dims["evidence"] - 1.0 * earlier)  # material slips confined to earlier turns
    d["capped_dims"] = dims
    d["material_final"], d["material_earlier"] = final, earlier
    d["overall"] = round(sum(WEIGHTS[k] * d["capped_dims"][k] for k in WEIGHTS), 2)
    d["prompt_chars"] = len(prompt)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(d, open(out, "w"), indent=1)
    return d


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+", default=["qwen", "opus"])
    p.add_argument("--tasks", nargs="+", required=True)
    p.add_argument("--judge", default="gpt-6.1-sol")
    p.add_argument("--tag", default="v3a")
    p.add_argument("--workers", type=int, default=8)
    a = p.parse_args()
    jobs = [(m, t) for t in a.tasks for m in a.models]
    with ThreadPoolExecutor(a.workers) as pool:
        res = list(pool.map(lambda j: (j, judge(j[0], j[1], a.judge, a.tag)), jobs))
    for (m, t), d in res:
        dims = " ".join(f"{k[:4]}={d['capped_dims'][k]:g}" for k in WEIGHTS)
        errs = [f"{e['severity'][:3]}:{e['what'][:70]}" for e in d.get("errors", [])]
        print(f"{t[:8]} {m:6s} overall={d['overall']:.1f}  {dims}")
        print(f"   errors: {errs[:5]}")
        print(f"   material final/earlier: {d.get("material_final")}/{d.get("material_earlier")}  target: {d.get("target", "")[:200]}")
        print(f"   summary: {d.get('summary', '')[:260]}")


if __name__ == "__main__":
    main()
