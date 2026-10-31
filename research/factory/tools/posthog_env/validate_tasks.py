#!/usr/bin/env python3
"""Validator stage: an independent model audits each curated task against its twin; only SOUND tasks are kept.

The curator (Opus) edits tasks; this validator (a different model, GPT-6.1 Sol by default) checks the result the way
a careful human reviewer does, with read-only queries against the twin (events, persons, session recordings, data
warehouse tables via warehouse('name')), and returns
  verdict   SOUND (measures models correctly as-is) | MINOR (usable but flawed) | BROKEN (would mis-measure)
  checks    premise / data / warehouse / objects / grading notes / self-containedness, each ok or a defect
  defects   [{class, what, evidence}]  (class from a fixed list, so drop rates can be tracked per class)
Only SOUND tasks stay included; others get exclude = "validator: <verdict>: <first defect>". Verdicts are cached per
task (<out>/<task_id>.json). Prints counts per verdict and per defect class.

    python3 validate_tasks.py --tasks B/curated/curated.jsonl --traces T/train.jsonl --out B/validated
Writes <out>/validated.jsonl.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/opt/posthog-env/runner")
sys.path.insert(0, "/opt/posthog-env")
import curate_tasks as CT  # noqa: E402  (run_queries incl. warehouse macro)
import llm_proxy  # noqa: E402
import spot_card as SC  # noqa: E402

CLASSES = ["premise_false", "data_missing", "data_implausible", "warehouse_broken", "object_missing", "object_leak",
           "notes_wrong", "notes_overspecified", "not_self_contained", "unanswerable_with_tools", "trivial", "other"]

PROMPT = """You audit tasks of a reinforcement-learning environment for PostHog AI (an analytics agent with tools: taxonomy
reads, HogQL/SQL over events/persons/sessions/recordings/data warehouse, insights, dashboards, notebooks, docs search).
Each task replays a (curated) user request against a synthetic "twin" PostHog project. Scores of models on this task
will be reported, so it must measure the model, not the environment. Be strict and concrete; verify, don't assume.

## Task (turns sent to the agent in order; later turns are scripted)
agent mode at start: {mode}
{turns}

## Grading notes the judge will use
{notes}

## Production conversation this task was seeded from (for intent only; the twin is NOT production)
{reference}

## Twin state summary (top-N lists; verify anything you rely on with queries)
The twin's data ends at {now} (the agent's "now"; relative windows like "last month" are evaluated at this time).
{twin}

## The twin team's PostHog objects (Postgres; what the agent's tools return)
{objects}

## Twin defects the curator noticed (it may have kept the task anyway; you decide)
{curator_defects}

## Mechanical lint findings on this twin (deterministic coherence checks; may or may not touch this task)
{lint}

## Your checks
1. Self-contained: a competent agent seeing only the turns can understand what is asked (no reference to unseen
   context; names resolve in the twin; scripted follow-ups make sense whatever the agent answered).
2. Premise: everything the user asserts or assumes is true in the twin (spikes, drops, events, pages, objects,
   property values, recordings, warehouse rows, date ranges relative to now = the latest data).
3. Data: the data a correct answer needs exists, is plausible for this business, and is coherent (funnel steps by the
   same people in order, consistent property combinations, realistic value domains and numeric scales, no placeholders
   like "<name>_a", "Name 3", "month_0").
4. Warehouse: if the task touches warehouse tables, read them (warehouse('<name>')): needed columns exist, join keys
   actually join, values are sensible.
5. Grading notes: every must_include item is correct on the twin (re-check numbers you can), achievable with the agent's
   tools, not over-specified (open-ended asks use k-of-n), acceptable variations non-empty; no grading on things the
   user did not ask. A required point stating a product fact (permissions, limits, defaults, pricing, regions) that
   you cannot confirm, or that depends on org/project settings, or that answers something the user did not ask, is a
   notes_wrong/notes_overspecified defect: BROKEN (round 5: "only admins can invite" was required; PostHog's default
   lets any member invite).
6. Curator defects and lint: start from the two lists above. For every curator-listed defect and every material lint
   finding, decide with a query whether it touches what the user asks about OR data a competent agent would
   naturally look at while answering. If it does, the task is BROKEN (class data_implausible) — even when the
   grading notes tolerate or explain it away; notes that steer around an artefact are themselves a defect.
   SOUND requires showing, with a query, that each such item is irrelevant to this task.
6b. Plausibility checks an expert reviewer applies (each one touching the task makes it at least MINOR):
   - a custom event reaching > 80% of active persons; a later step (verified, converted, completed, purchased)
     with more persons than its earlier step (registered, started, visited); a once-per-person event (signup,
     conversion, verification) repeated many times per person;
   - funnel-like steps done in random order;
   - pageviews on posthog.com/app.posthog.com /project/ paths for a business that is not PostHog; mobile lifecycle
     (Application *) or mcp* events in a web-only product; session-level $entry_* props on custom events;
   - placeholder values (userN@example.com, "<prop>_a", "Name 3"), the same email shared by many persons, event
     email disagreeing with the person's email;
   - an attached insight/dashboard/query whose events or properties don't exist on the twin, or return nothing.
   MINOR is not kept: only SOUND tasks are used.
6c. Objects and clock: every object the turns or grading notes name (flag/insight/dashboard/experiment ids, keys,
   names, filters, conditions) must match the object list above, not the production reference; any grading claim
   about an object or setting you cannot confirm there or with a query means the task is not SOUND. A date the
   turn states as "today"/"current date" must agree with the data end above (no day/week/month boundary between).
6e. Attached results and ids: result tables/numbers pasted into a turn must agree with the twin at the data end
   (query them); every session id, insight/dashboard/flag id the turns name must exist (objects list,
   session_replay_events). A contradiction a competent agent would notice is at least MINOR; if grading depends on
   it, BROKEN. Curation edits listed (e.g. remove_turn) must be reflected in the turns.
6f. Numbers: recompute every number the grading notes state, on the twin at the data end, under both a rolling window
   and PostHog's start-of-day window; if a correct live number falls outside what the notes accept, that is
   notes_wrong (round 8: notes said ~500/515, live 518/533, and a strict grader could fail the correct answer).
6d. Minimal-answer test: imagine the shortest correct answer to exactly what the user asked; if a must_include point
   would fail it (a supporting fact or caveat the user did not ask for), that is notes_overspecified.
7. Difficulty: is it trivial (single lookup, answer in the prompt)? Trivial is allowed if it is a real request; mark it.

To check, reply with {{"queries": [{{"why": "...", "sql": "..."}}]}} (at most 8 per round, up to 4 rounds). Tables:
events(team_id, event, timestamp, distinct_id, person_id, properties), person(team_id, id, properties),
session_replay_events(team_id, session_id, distinct_id, min_first_timestamp, ...); warehouse tables via
warehouse('<name>'). Every query must contain `team_id = {{team}}`. properties are JSON strings (JSONExtractString).

Final answer, ONLY JSON:
{{"verdict": "SOUND|MINOR|BROKEN", "trivial": true|false,
 "checks": {{"self_contained": "ok|<defect>", "premise": "ok|<defect>", "data": "ok|<defect>", "warehouse": "ok|n/a|<defect>",
            "grading_notes": "ok|<defect>"}},
 "defects": [{{"class": "{classes}", "what": "<concrete>", "evidence": "<query -> result>"}}],
 "summary": "<one sentence>"}}
SOUND means: you would report model scores on this task without caveats, and an expert auditing the twin data
behind it would find nothing implausible that the task touches. Any defect that could change whether a
competent answer passes makes it BROKEN; a real but harmless flaw is MINOR."""


def last_json(text: str) -> dict:
    """The last JSON object with a verdict or queries (round 3: a reply holding two objects failed json.loads)."""
    dec, found, i = json.JSONDecoder(), None, text.find("{")
    while i >= 0:
        try:
            obj, end = dec.raw_decode(text, i)
            if isinstance(obj, dict) and ("verdict" in obj or "queries" in obj):
                found = obj
            i = text.find("{", end)
        except ValueError:
            i = text.find("{", i + 1)
    if found is None:
        raise ValueError("no JSON object with verdict/queries")
    return found


LINT: dict = {}  # conversation_id -> [finding] (from loop_producer's lint.jsonl)


def load_lint(path: str) -> None:
    for line in open(path):
        r = json.loads(line)
        LINT[r["project"][:36]] = r.get("findings") or []


def lint_text(conv: str) -> str:
    f = LINT.get(str(conv)[:36])
    if f is None:
        return "(not run)"
    return "\n".join(f"- [{x['severity']}] {x['check']}: {x['detail']}" for x in f) or "(none)"


def validate_one(task: dict, rec: dict | None, model: str, out_dir: str) -> dict:
    path = f"{out_dir}/{task['task_id']}.json"
    if os.path.exists(path):
        return json.load(open(path))
    turns = "\n".join(f"[turn {i}] {SC.clip(t, 6000)}" for i, t in enumerate(task["turns"]))
    ref = "\n".join(SC.render_trace(rec, len(task["turns"]) + task.get("turn_offset", 0), 800, 2000)) if rec else "(none)"
    twin = "\n".join(str(x) for x in SC.twin_state(task) + SC.event_props(task))
    prompt = PROMPT.format(mode=task.get("agent_mode") or "product_analytics", turns=turns,
                           notes=json.dumps(task.get("grading_notes"), ensure_ascii=False, indent=1)[:6000],
                           reference=SC.clip(ref, 30000), twin=SC.clip(twin, 20000), classes="|".join(CLASSES),
                           lint=SC.clip(lint_text(task["conversation_id"]), 4000),
                           now=task.get("loaded_now_utc") or "?", objects=SC.clip(SC.team_objects(task["team_id"]), 5000),
                           curator_defects=SC.clip(json.dumps((task.get("curation") or {}).get("twin_defects") or [],
                                                              ensure_ascii=False, indent=1), 4000) or "(none)")
    out = {"task_id": task["task_id"], "model": model, "queries_run": []}
    convo, rounds = prompt, 0
    for _ in range(8):
        try:
            text, _u = llm_proxy.judge_complete(convo, model, None, attempts=6, preamble=False)
            d = last_json(text)
            if d.get("queries") and "verdict" not in d and rounds < 4:
                rounds += 1
                res = CT.run_queries(d["queries"][:8], int(task["team_id"]))
                out["queries_run"] += res
                convo += (f"\n\n## Your queries and results (round {rounds})\n" +
                          "\n".join(f"- {r['why']}\n  SQL: {r['sql']}\n  -> {r['result']}" for r in res) +
                          ("\n\nNow give the final JSON." if rounds >= 4 else "\n\nAsk again or give the final JSON."))
                continue
            assert d.get("verdict") in ("SOUND", "MINOR", "BROKEN")
            out.update(d)
            out.pop("error", None)
            break
        except Exception as ex:  # noqa: BLE001
            out["error"] = f"{type(ex).__name__}: {str(ex)[:200]}"
    json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--traces", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="gpt-6.1-sol")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--repair", action="store_true",
                    help="send non-SOUND tasks back to the curator with the findings, then validate the revision once")
    ap.add_argument("--curator-model", default="claude-opus-5-5")
    ap.add_argument("--repair-rounds", type=int, default=2)
    ap.add_argument("--lint", default="", help="lint.jsonl from twingen/v2/lint.py (one line per project)")
    a = ap.parse_args()
    if a.lint and os.path.exists(a.lint):
        load_lint(a.lint)
    os.makedirs(a.out, exist_ok=True)
    tasks = [json.loads(x) for x in open(a.tasks) if x.strip()]
    todo = [t for t in tasks if not t.get("exclude")]
    want = {t["conversation_id"] for t in todo}
    recs = {}
    for line in open(a.traces):
        r = json.loads(line)
        if str(r.get("id")) in want:
            recs[str(r["id"])] = r
    with ThreadPoolExecutor(a.workers) as pool:
        res = dict(zip([t["task_id"] for t in todo],
                       pool.map(lambda t: validate_one(t, recs.get(t["conversation_id"]), a.model, a.out), todo)))
    stats: Counter = Counter()
    if a.repair:
        for rnd in range(1, a.repair_rounds + 1):
            cur = {t["task_id"]: t for t in tasks}
            bad = [cur[t["task_id"]] for t in todo
                   if (res.get(t["task_id"]) or {}).get("verdict") in ("MINOR", "BROKEN") and t["task_id"] in cur
                   and not cur[t["task_id"]].get("repair_gave_up")]
            if not bad:
                break
            rdir = f"{a.out}/rev{rnd}"
            os.makedirs(f"{rdir}/curated", exist_ok=True)

            def repair(t, rdir=rdir):
                r = res[t["task_id"]]
                fb = {"prev": {"turns": t["turns"], "grading_notes": t.get("grading_notes")},
                      "findings": {k: r.get(k) for k in ("verdict", "checks", "defects", "summary")}}
                base = {**t, "turns": t.get("turns_built") or t["turns"]}
                c = CT.curate_one(base, recs.get(t["conversation_id"]), a.curator_model, f"{rdir}/curated", feedback=fb)
                if c.get("decision") not in ("keep", "edit") or not c.get("turns"):
                    return t["task_id"], {**t, "repair_gave_up": True}, None
                if c.get("twin_overrides"):  # data fix: regenerate before validating (loop_producer.regen_pending)
                    os.makedirs(f"{rdir}/overrides", exist_ok=True)
                    path = f"{rdir}/overrides/{t['twin_id']}.json"
                    cur = json.load(open(path)) if os.path.exists(path) else {"twin_id": t["twin_id"],
                                                                              "shift_days": t.get("shift_days"), "overrides": []}
                    cur["overrides"] += c["twin_overrides"]
                    json.dump(cur, open(path, "w"), indent=1)
                t2 = {**t, "turns": c["turns"], "max_turns": len(c["turns"]), "grading_notes": c.get("grading_notes"),
                      "revised_by_validator": rnd,
                      "curation": {**(t.get("curation") or {}), **{k: c.get(k) for k in (
                          "decision", "reason", "twin_defects", "evidence", "edits", "difficulty") if k in c},
                                   "revision": rnd}}
                if c.get("twin_overrides"):
                    t2["pending_regen"] = rnd
                    return t["task_id"], t2, {"task_id": t["task_id"], "verdict": "PENDING_REGEN",
                                              "summary": "curator added twin_overrides; validate after regeneration"}
                return t["task_id"], t2, validate_one(t2, recs.get(t["conversation_id"]), a.model, rdir)

            with ThreadPoolExecutor(a.workers) as pool:
                for tid, t2, r2 in pool.map(repair, bad):
                    stats[f"repair{rnd}_attempted"] += 1
                    if r2 is None:
                        stats[f"repair{rnd}_dropped_by_curator"] += 1
                    else:
                        res[tid] = r2
                        stats[f"repair{rnd}_fixed"] += r2.get("verdict") == "SOUND"
                        stats[f"repair{rnd}_pending_regen"] += r2.get("verdict") == "PENDING_REGEN"
                    for i, t in enumerate(tasks):
                        if t["task_id"] == tid:
                            tasks[i] = t2
    with open(f"{a.out}/validated.jsonl", "w") as f:
        for t in tasks:
            t = dict(t)
            r = res.get(t["task_id"])
            if r is not None:
                v = r.get("verdict") or "ERROR"
                stats[f"verdict_{v}"] += 1
                for d in r.get("defects") or []:
                    stats[f"class_{d.get('class')}"] += 1
                t["validation"] = {k: r.get(k) for k in ("verdict", "trivial", "checks", "defects", "summary", "model")}
                if v != "SOUND":
                    first = ((r.get("defects") or [{}])[0].get("what") or r.get("summary") or r.get("error") or "")[:160]
                    t["exclude"] = f"validator: {v}: {first}"
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(json.dumps(dict(sorted(stats.items()))))


if __name__ == "__main__":
    main()
