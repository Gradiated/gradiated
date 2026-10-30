#!/usr/bin/env python3
"""Curation stage: an LLM editor turns built tasks (seeded from production conversations) into representative,
self-contained, gradable environment tasks. Runs on fbf8 (system python); calls go through the subscription proxy.

For each task the editor sees the task as built, the production conversation (the seed), and the twin's actual
state, and returns:
  decision      keep | edit | drop (with a reason)
  turns         the edited user turns (keep intent, language, tone, agent mode and the kind of work; change only
                what is needed to make the task self-contained, unambiguous and answerable in this twin)
  edits         one entry per change: kind (rewrite_followup, fold_context, pin_definition, remove_turn, fix_premise,
                anon_fix, other) and why
  grading_notes what a correct final answer must contain, checkable against the TWIN (not production numbers),
                acceptable variations, and what is not required
  twin_overrides changes the twin needs so the task's premise is true (event volume multipliers, spikes, history)
  difficulty, skills  for task-mix tracking

The editor never makes a task easier: no hints about which events, properties or tables to use beyond what the
user already said. Edits are recorded so the task mix can be compared before and after curation.

    python3 curate_tasks.py --tasks B/tasks/train.jsonl --traces T/train.jsonl --out B/curated [--model claude-opus-5-5]
Writes <out>/<task_id>.json (editor output) and <out>/curated.jsonl (tasks with edited turns, grading_notes,
curation metadata; dropped tasks keep exclude="curation: <reason>"). Twin overrides are written to
<out>/overrides/<twin_id>.json (not applied; the loop applies them by regenerating the twin). Prints counts only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/opt/posthog-env/runner")
sys.path.insert(0, "/opt/posthog-env")
import llm_proxy  # noqa: E402
import spot_card as SC  # noqa: E402

PROMPT = """You curate tasks for a reinforcement-learning environment that trains and evaluates PostHog AI, an agent that
answers product-analytics questions about a PostHog project by calling tools (taxonomy reads, HogQL/SQL, insights,
dashboards, docs search, recordings...). Each task replays the user side of a real (anonymized) production
conversation against a synthetic "twin" project whose data was generated to resemble the original project. The
production conversation is only a SEED: you may edit the task so it becomes a good, representative training task.

Goal: the task set must reflect what real users ask (production distribution), and every task must be
self-contained, unambiguous enough to grade, answerable from THIS twin, and not artificially easy.

## Task as built (turns are sent to the agent in order; later turns are scripted, they are sent whatever the agent
## answered)
agent mode at start: {mode}
{turns}

builder notes: {notes}

## Production conversation (the seed; turns marked IN TASK are the ones above)
{reference}

## The twin project's actual state (dates are the twin's dates, i.e. already shifted to "now")
{twin}

## Rules
1. Preserve the user's intent, language, tone and phrasing style, the agent mode, and the kind of work (SQL editing,
   insight building, dashboard building, investigation, docs question...). Edit as little as possible.
2. Make the task self-contained: a scripted follow-up must make sense whatever a competent agent answered. Rewrite or
   remove follow-ups that quote or react to the production agent's specific answer (its numbers, its suggestions,
   its mistakes). If the user's message only makes sense with attached context the agent can't see, fold the needed
   facts into the text. Read the WHOLE production conversation, including turns not in the task: when a later user
   turn corrects or clarifies what they meant ("No, I mean the events it returns"), fold that clarification into
   the task's wording so the task asks what the user actually wanted.
3. Make it gradable: if the request is ambiguous in a way that changes the answer (which event means "signup",
   which ARR definition), pin it the way a real user plausibly would, or note acceptable readings in grading_notes.
4. The premise must be true in the twin. Check every concrete thing the task relies on against the twin state shown
   (events, page paths and hosts, property values, objects, warehouse tables, date span). If the user asserts or
   needs something (a drop, a spike, pages under a path, an event, a property value, a dashboard) that the twin's
   state contradicts or lacks, either propose twin_overrides that make it true or rewrite the premise to match the
   twin; if neither is possible, drop the task and say what the twin lacks. Don't keep tasks whose correct answer is "the data isn't there" unless
   that is also what production found.
5. Never make the task easier: don't add which events/properties/tables to use, don't add the answer, don't remove
   genuine difficulty. Do remove anonymization artefacts that make the task unanswerable.
6. Drop the task only if it cannot be made into a good task: off-topic or abusive, pure chit-chat, no checkable
   outcome even after pinning, or needs data/systems the twin can't hold. Docs-only questions are kept only if they
   need real product knowledge.
6b. Generator artefacts are bugs, not traps. If the twin shows something implausible for this business (a value
   leaked onto unrelated events, a country code that disagrees with the country name, a one-day burst, a population
   with no baseline, sessions that make no sense), do NOT write it into the grading notes as a trap or a bonus:
   fix it with twin_overrides if they can, otherwise list it in "twin_defects" (and drop with drop_kind twin_gap if
   it breaks the task). Facts the agent cannot obtain with its tools (e.g. product prices missing from the docs it
   can search) must not be required in grading_notes.
7. grading_notes must be checkable against the twin (the agent will see twin data, not production): describe what the
   right answer contains and how to check it (query sketch, object to inspect), acceptable variations, and things
   not required. Don't copy production numbers unless the twin reproduces them.
8. twin_overrides may only use: {{"kind": "event_multiplier", "event": E, "factor": x}}, {{"kind": "spike",
   "event": E, "from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "factor": x}} (twin dates), {{"kind": "history_days",
   "days": n}}. Leave empty if the twin already supports the task.

Respond with ONLY a JSON object:
## Verifying the twin before you decide
The twin state above is a summary (top-N lists). Before claiming the twin lacks something (an event, page, property,
value, person) or that a premise is false, CHECK it: instead of the final JSON you may reply with
{{"queries": [{{"why": "<what you check>", "sql": "<ClickHouse SELECT>"}}, ...]}} (at most 6). Tables:
events(team_id, event, timestamp, distinct_id, person_id, properties) and person(team_id, id, properties), where
properties is a JSON string (use JSONExtractString(properties, 'key'), JSONHas(properties, 'key')). Every query must
contain `team_id = {{team}}` (it is filled in for you) and should aggregate or LIMIT. You get the results back and can
ask once more. Every drop with drop_kind twin_gap and every fix_premise edit must cite what you checked in "evidence".

Turns you do not change: write null in "turns" at that position (it is copied from the built task verbatim, with
its attached context). Never write a summary or placeholder of a turn.

{{"decision": "keep|edit|drop", "reason": "<one sentence>",
 "drop_kind": "<only for drop: twin_gap (the twin lacks data/objects the task needs and overrides can't add them) | unfixable | off_topic | chitchat>",
 "twin_gap": "<only for twin_gap: what the generator would need to produce, concretely>",
 "evidence": ["<query you ran -> what it showed>", ...],
 "twin_defects": ["<implausible generator artefact you noticed, concretely>", ...],
 "turns": ["<turn 0>", ...],
 "edits": [{{"kind": "rewrite_followup|fold_context|pin_definition|remove_turn|fix_premise|anon_fix|other", "turn": <i>, "why": "<short>"}}],
 "grading_notes": {{"must_include": ["..."], "how_to_check": ["..."], "acceptable_variations": ["..."], "not_required": ["..."]}},
 "twin_overrides": [ ... ],
 "difficulty": "trivial|moderate|hard", "skills": ["sql|trends|funnels|retention|dashboards|insight_edit|taxonomy|docs|recordings|flags|experiments|surveys|warehouse|investigation|other"]}}"""


PLACEHOLDER = re.compile(r"^\s*\[(turn \d+ )?(unchanged|same as|original|verbatim)", re.I)


def resolve_turns(turns, built: list[str], edits: list[dict]) -> list[str]:
    """Editor turns -> final turns. null (or a placeholder like "[turn 0 unchanged: ...]") copies the built turn; an
    edited turn that lost more than half of a built turn's attached context must have an edit entry for that turn."""
    assert isinstance(turns, list) and turns, "no turns"
    if all(t is None for t in turns) and len(turns) != len(built):
        turns = [None] * len(built)
    out = []
    edited = {e.get("turn") for e in edits}
    for i, t in enumerate(turns):
        if t is None or (isinstance(t, str) and PLACEHOLDER.match(t)):
            assert i < len(built), f"turn {i} copied but the built task has {len(built)} turns"
            out.append(built[i])
            continue
        assert isinstance(t, str) and t.strip(), f"turn {i} empty"
        if i < len(built) and len(t) < 0.5 * len(built[i]) and i not in edited and len(built[i]) > 2000:
            raise AssertionError(f"turn {i} shrank {len(built[i])}->{len(t)} without an edit entry")
        out.append(t)
    return out


FORBIDDEN = re.compile(r"\b(insert|alter|drop|truncate|create|optimize|system|kill|attach|detach|rename|grant)\b", re.I)


def run_queries(qs: list, team: int) -> list[dict]:
    """Run the editor's verification queries read-only on the twin team (readonly=1, 30 s, 50 rows)."""
    import urllib.parse
    import urllib.request

    out = []
    for q in qs:
        sql = str((q or {}).get("sql") or "")
        why = str((q or {}).get("why") or "")[:200]
        if "{team}" not in sql or FORBIDDEN.search(sql.replace("{team}", "")) or not sql.lstrip().lower().startswith(("select", "with")):
            out.append({"why": why, "sql": sql[:400], "result": "REJECTED: must be a SELECT containing team_id = {team}"})
            continue
        sql = sql.replace("{team}", str(team)).rstrip().rstrip(";")
        params = {"database": SC.CH_DB, "default_format": "JSONCompact", "readonly": "1", "max_execution_time": "30",
                  "max_result_rows": "50", "result_overflow_mode": "break", "max_threads": "2"}
        try:
            r = urllib.request.urlopen("http://127.0.0.1:8123/?" + urllib.parse.urlencode(params), data=sql.encode(), timeout=60)
            data = json.loads(r.read()).get("data")
            res = json.dumps(data, ensure_ascii=False)[:1500]
        except Exception as ex:  # noqa: BLE001
            res = f"ERROR {str(ex)[:300]}"
        out.append({"why": why, "sql": sql[:600], "result": res})
    return out


def clip_turn(t: str, n: int = 6000) -> str:
    return SC.clip(t, n)


def curate_one(task: dict, rec: dict | None, model: str, out_dir: str) -> dict:
    path = f"{out_dir}/{task['task_id']}.json"
    if os.path.exists(path):
        return json.load(open(path))
    turns = "\n".join(f"[turn {i}] {clip_turn(t)}" for i, t in enumerate(task["turns"]))
    notes = json.dumps({k: v for k, v in (task.get("quality") or {}).items()}, ensure_ascii=False)
    ref = "\n".join(SC.render_trace(rec, len(task["turns"]) + task.get("turn_offset", 0), 1200, 3000)) if rec else "(none)"
    ref = SC.clip(ref, 60000)
    twin = "\n".join(str(x) for x in SC.twin_state(task) + SC.event_props(task))
    prompt = PROMPT.format(mode=task.get("agent_mode") or "product_analytics (default)", turns=turns, notes=notes,
                           reference=ref, twin=SC.clip(twin, 20000))
    rec_out = {"task_id": task["task_id"], "model": model, "queries_run": []}
    convo = prompt
    rounds = 0
    for _ in range(5):
        try:
            text, usage = llm_proxy.judge_complete(convo, model, None, attempts=6, preamble=False)
            s, e = text.find("{"), text.rfind("}")
            d = json.loads(text[s:e + 1])
            if d.get("queries") and "decision" not in d and rounds < 2:
                rounds += 1
                res = run_queries(d["queries"][:6], int(task["team_id"]))
                rec_out["queries_run"] += res
                convo = (convo + "\n\n## Your queries and their results (round " + str(rounds) + ")\n" +
                         "\n".join(f"- {r['why']}\n  SQL: {r['sql']}\n  -> {r['result']}" for r in res) +
                         ("\n\nNow give the final JSON." if rounds >= 2 else "\n\nAsk once more or give the final JSON."))
                continue
            assert d.get("decision") in ("keep", "edit", "drop")
            if d["decision"] != "drop":
                d["turns"] = resolve_turns(d.get("turns"), task["turns"], d.get("edits") or [])
            rec_out.update(d)
            rec_out.pop("error", None)
            break
        except Exception as ex:  # noqa: BLE001
            rec_out["error"] = f"{type(ex).__name__}: {str(ex)[:200]}"
    json.dump(rec_out, open(path, "w"), ensure_ascii=False, indent=1)
    return rec_out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--traces", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--include-excluded", action="store_true", help="also curate tasks the builder excluded")
    a = ap.parse_args()
    os.makedirs(f"{a.out}/overrides", exist_ok=True)
    tasks = [json.loads(x) for x in open(a.tasks) if x.strip()]
    todo = [t for t in tasks if a.include_excluded or not t.get("exclude")]
    want = {t["conversation_id"] for t in todo}
    recs = {}
    for line in open(a.traces):
        r = json.loads(line)
        if str(r.get("id")) in want:
            recs[str(r["id"])] = r
    with ThreadPoolExecutor(a.workers) as pool:
        res = dict(zip([t["task_id"] for t in todo],
                       pool.map(lambda t: curate_one(t, recs.get(t["conversation_id"]), a.model, a.out), todo)))
    stats: Counter = Counter()
    out = []
    for t in tasks:
        r = res.get(t["task_id"])
        t = dict(t)
        if r is None:
            out.append(t)
            continue
        stats[f"decision_{r.get('decision', 'error')}"] += 1
        if r.get("decision") == "drop":
            stats[f"drop_{r.get('drop_kind') or 'unspecified'}"] += 1
        stats["twin_defects_reported"] += len(r.get("twin_defects") or [])
        for e in r.get("edits") or []:
            stats[f"edit_{e.get('kind')}"] += 1
        t["curation"] = {k: r.get(k) for k in ("decision", "reason", "drop_kind", "twin_gap", "twin_defects", "evidence", "edits", "difficulty",
                                                "skills", "model")}
        t["curation"]["n_queries"] = len(r.get("queries_run") or [])
        if r.get("decision") == "drop":
            t["exclude"] = f"curation: {r.get('reason')}"
        elif r.get("decision") in ("keep", "edit"):
            t["turns_built"] = t["turns"]
            t["turns"] = r["turns"]
            t["max_turns"] = len(r["turns"])
            t["grading_notes"] = r.get("grading_notes")
            if r.get("twin_overrides"):
                t["twin_overrides"] = r["twin_overrides"]
                json.dump({"twin_id": t["twin_id"], "shift_days": t.get("shift_days"), "overrides": r["twin_overrides"]},
                          open(f"{a.out}/overrides/{t['twin_id']}.json", "w"), indent=1)
                stats["with_overrides"] += 1
        else:
            stats["errors"] += 1
        out.append(t)
    with open(f"{a.out}/curated.jsonl", "w") as f:
        for t in out:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(json.dumps(dict(sorted(stats.items()))))


if __name__ == "__main__":
    main()
