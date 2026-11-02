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
import hashlib
import json
import os
from pathlib import Path
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
   it breaks the task). A twin defect that touches what the user asks about, or that a competent agent would
   naturally query while answering, BREAKS the task: fix it or drop it; never keep the task with grading notes that
   explain the artefact away or steer around it. If the user attaches an insight/dashboard/query, its events and
   properties must exist on the twin with sensible data (run it); if they don't and overrides can't add them, drop. Facts the agent cannot obtain with its tools (e.g. product prices missing from the docs it
   can search) must not be required in grading_notes.
6h. Attached production results (tables, insight results, numbers pasted as context) must not contradict the twin:
   keep the definition and either remove the result rows or replace them with values computed on the twin as of
   its data end. Every id the turns name (insight short id, dashboard/flag/experiment id, session id, person) must
   exist in the twin (objects list above, session_replay_events): otherwise rewrite it to an existing one, add it
   with overrides, or drop. A remove_turn edit must actually remove the turn from "turns".
6g. Required points answer what the user asked. Caveats the user did not ask about (permissions, plan limits,
   regions, pricing) go in acceptable_variations or not_required, never in must_include. A required point that
   states a product fact must be one you verified (the docs the production answer retrieved, or the twin's own
   org/project settings); if unverified or setting-dependent (e.g. who may invite members depends on the org's
   members_can_invite), do not require it (round 5: "only admins can invite" was required and is false by default).
6c. must_include items are FINDINGS a correct answer reaches ("finds that subscription_updated carries mrr and uses
   it", "creates the flag rather than describing it"), not exact reference numbers, unless the number follows
   unambiguously from the twin with the obvious query. Every acceptable variation you list must give a non-empty,
   sensible answer on THIS twin (check it with a query); never accept a variation that returns nothing.
6d. Renaming (anon_fix): a replacement name must keep the same role. If the user names THEIR OWN product or company,
   do not substitute a name that reads like a customer or another company; write "our product"/"our app" or use the
   twin's own site/product name as the twin shows it (host, app name). Never introduce a name the twin cannot resolve.
6f. A turn that begins by answering questions from an earlier conversation the agent never saw gets a one-line
   preface in the user's voice ("Answers to the questions you asked earlier:"), so it reads as self-contained.
6e. Open-ended requests ("analyse the project and suggest improvements"): must_include lists the core findings a good
   answer would reach and says how many of them are required (e.g. "at least 3 of these 5"); do not require every
   finding of the production answer.
7. grading_notes must be checkable against the twin (the agent will see twin data, not production): describe what the
   right answer contains and how to check it (query sketch, object to inspect), acceptable variations, and things
   not required. Don't copy production numbers unless the twin reproduces them.
8. twin_overrides (twin dates YYYY-MM-DD; the twin is regenerated with them, then checked again). Kinds:
   {{"kind": "event_multiplier", "event": E, "factor": x}}
   {{"kind": "spike", "event": E, "from": D, "to": D, "factor": x}}   (factor 0 stops the event in that window)
   {{"kind": "history_days", "days": n}}
   {{"kind": "new_event", "event": E, "per_day": n, "from": D, "to": D, "persons": N, "props": {{prop: SPEC}},
     "lib": "posthog-ios"|"posthog-android"|"web"(optional)}}   an event the request needs that the twin lacks
   {{"kind": "sequence", "steps": [E1, E2, ...], "persons": N, "from": D, "to": D, "rates": [1, 0.6, 0.35, ...],
     "gap_minutes": [lo, hi], "props": {{E: {{prop: SPEC}}}}, "lib": ..., "shared_id": "order_id"(optional)}}
     ordered journeys with realistic drop-off; "shared_id": one generated id on every step of a journey
   {{"kind": "person", "email": ..., "name": ..., "props": {{...}}}}   a named, active person the request refers to
   {{"kind": "event_props", "event": E, "props": {{prop: SPEC}}, "share": 0..1, "per": "<id prop>"(optional)}}
     properties on an existing event; "per": one value per entity (all events with the same submission_id agree)
   {{"kind": "person_props", "props": {{prop: SPEC}}, "share": 0..1}}   person properties (plan, company, role, ...)
   {{"kind": "warehouse_table", "table": T, "columns": {{col: {{"type": "string|integer|float|datetime|boolean",
     "values": [...]}}}}}}   a synced table; key columns named distinct_id/user_id/email/person_id join to persons
   SPEC = {{"values": [v, ...] or [[v, weight], ...]}} | {{"range": [lo, hi], "int": true, "log": true}} | literal;
   add "per_person": true for a value that stays fixed per person (a reader's book, a customer's plan).
   Use them to make the request's premise and the data a correct answer needs real and PLAUSIBLE for this business
   (realistic volumes, shares and drop-off, values in the business's domain, consistent across related events).
   An override changes only what it names: list EVERY event type a fix must reach (e.g. both $pageview and
   $pageleave), use share 1.0 for corrections, and fix the cause, not one view of it. Grading notes must not state
   exact numbers that depend on data an override adds (they are written before regeneration): describe the finding
   and how to check it with a query instead.
   Prefer this over dropping with twin_gap. Never add data that hands the agent the answer or makes the task easier
   than production (no labels that name the conclusion). Leave empty if the twin already supports the task.

Respond with ONLY a JSON object:
## Verifying the twin before you decide
The twin state above is a summary (top-N lists). Before claiming the twin lacks something (an event, page, property,
value, person) or that a premise is false, CHECK it: instead of the final JSON you may reply with
{{"queries": [{{"why": "<what you check>", "sql": "<ClickHouse SELECT>"}}, ...]}} (at most 6). Tables:
events(team_id, event, timestamp, distinct_id, person_id, properties), person(team_id, id, properties) and
session_replay_events(team_id, session_id, distinct_id, min_first_timestamp, max_last_timestamp, first_url, ...)
(session recordings live ONLY there, not in events), where properties is a JSON string. Data warehouse tables
are read with warehouse('<table name>') in place of a table (e.g. SELECT count() FROM warehouse('stripe_customers')
WHERE team_id = {{team}} ... -- keep the team_id condition text, it is checked but not applied to warehouse reads);
always check warehouse-backed premises (join keys actually join, value domains make sense, columns exist) (use JSONExtractString(properties, 'key'), JSONHas(properties, 'key')). Every query must
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


WH_MACRO = re.compile(r"warehouse\(\s*'([^']+)'\s*\)")


def warehouse_urls(team: int) -> dict:
    rows = SC.pg(f"select name, url_pattern from posthog_datawarehousetable where team_id={int(team)} and deleted is not true")
    return {r[0]: r[1] for r in rows if len(r) == 2 and r[1].startswith("http")}


def expand_warehouse(sql: str, team: int) -> tuple[str, list]:
    """warehouse('name') -> url('<parquet url>', 'Parquet') for the twin team's warehouse table."""
    names = WH_MACRO.findall(sql)
    if not names:
        return sql, []
    urls = warehouse_urls(team)
    missing = [n for n in names if n not in urls]
    return WH_MACRO.sub(lambda m: f"url('{urls.get(m.group(1), '')}', 'Parquet')", sql), missing


URL_READ = re.compile(r"url\(\s*'([^']*/twins/(\d+)/[^']*)'\s*,\s*'Parquet'\s*\)", re.I)


def team_scoped_urls(sql: str, team: int) -> str:
    """Warehouse parquet has no team_id column, but every query must filter team_id (round 3: validator and curator
    wrote `url(...) WHERE team_id = N`, ClickHouse rejected it, and three tasks were judged 'warehouse unreadable').
    Each twin warehouse read becomes a subquery that carries the team id."""
    return URL_READ.sub(lambda m: f"(SELECT *, {int(m.group(2))} AS team_id FROM url('{m.group(1)}', 'Parquet'))", sql)


FORBIDDEN = re.compile(r"\b(insert|alter|drop|truncate|create|optimize|system|kill|attach|detach|rename|grant)\b", re.I)


def run_queries(qs: list, team: int) -> list[dict]:
    """Run the editor's verification queries read-only on the twin team (readonly=2: no writes, but table functions such
    as url() for warehouse parquet are allowed; readonly=1 blocked every warehouse read), 30 s, 50 rows."""
    import urllib.error
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
        sql, missing = expand_warehouse(sql, team)
        if missing:
            out.append({"why": why, "sql": sql[:400], "result": f"ERROR unknown warehouse table(s): {missing}"})
            continue
        sql = team_scoped_urls(sql, team)
        params = {"database": SC.CH_DB, "default_format": "JSONCompact", "readonly": "2", "max_execution_time": "30",
                  "max_result_rows": "50", "result_overflow_mode": "break", "max_threads": "2"}
        try:
            r = urllib.request.urlopen("http://127.0.0.1:8123/?" + urllib.parse.urlencode(params), data=sql.encode(), timeout=60)
            data = json.loads(r.read()).get("data")
            res = json.dumps(data, ensure_ascii=False)[:1500]
        except urllib.error.HTTPError as ex:  # ClickHouse's message, so the model can fix its query
            body = ex.read().decode("utf-8", "replace")
            res = f"ERROR {ex.code}: {re.sub(r'Stack trace:.*', '', body, flags=re.S).strip()[:400]}"
        except Exception as ex:  # noqa: BLE001
            res = f"ERROR {str(ex)[:300]}"
        out.append({"why": why, "sql": sql[:600], "result": res})
    return out


def clip_turn(t: str, n: int = 6000) -> str:
    return SC.clip(t, n)


FEEDBACK = """

## Revision request
An independent validator audited the version of this task you produced (turns and grading notes below) against the
twin and found these problems. Fix them by editing the turns and/or grading notes (verify with queries), and fix
twin data defects with twin_overrides (the twin is then regenerated and the task validated again) rather than
dropping; drop only if neither can make the task sound. Keep everything else that was fine.
Your previous version: {prev}
Validator findings: {findings}"""


def curation_complete(record: dict) -> bool:
    if record.get("error") or record.get("decision") not in ("keep", "edit", "drop"):
        return False
    if record["decision"] == "drop":
        return True
    turns = record.get("turns")
    notes = record.get("grading_notes")
    required = notes.get("must_include") if isinstance(notes, dict) else None
    return (isinstance(turns, list) and bool(turns) and all(isinstance(t, str) and t.strip() for t in turns)
            and isinstance(required, list) and bool(required)
            and all(isinstance(point, str) and point.strip() for point in required))


def curate_one(task: dict, rec: dict | None, model: str, out_dir: str, feedback: dict | None = None) -> dict:
    path = f"{out_dir}/{task['task_id']}.json"
    turns = "\n".join(f"[turn {i}] {clip_turn(t)}" for i, t in enumerate(task["turns"]))
    notes = json.dumps({k: v for k, v in (task.get("quality") or {}).items()}, ensure_ascii=False)
    ref = "\n".join(SC.render_trace(rec, len(task["turns"]) + task.get("turn_offset", 0), 1200, 3000)) if rec else "(none)"
    ref = SC.clip(ref, 60000)
    twin = "\n".join(str(x) for x in SC.twin_state(task) + SC.event_props(task))
    twin += (f"\n\nData ends at {task.get('loaded_now_utc')} (the agent's now).\nTwin PostHog objects (Postgres; use these, "
             f"not production's, for any object claim):\n" + SC.team_objects(task["team_id"]))
    prompt = PROMPT.format(mode=task.get("agent_mode") or "product_analytics (default)", turns=turns, notes=notes,
                           reference=ref, twin=SC.clip(twin, 20000))
    if feedback:
        prompt += FEEDBACK.format(prev=json.dumps(feedback.get("prev"), ensure_ascii=False)[:8000],
                                  findings=json.dumps(feedback.get("findings"), ensure_ascii=False)[:6000])
    # Include both complete inputs and the rendered live context. Same-ID rebuilds or model/feedback changes
    # must not reuse edits, grading notes or overrides from a different task/world.
    identity = {"version": 1, "task": task, "reference": rec, "model": model, "feedback": feedback, "prompt": prompt}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    if os.path.exists(path):
        try:
            cached = json.loads(Path(path).read_text())
            if cached.get("input_key") == key and curation_complete(cached):
                return cached
        except (OSError, ValueError, AttributeError):
            pass
    rec_out = {"task_id": task["task_id"], "model": model, "queries_run": [], "revision": bool(feedback), "input_key": key}
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
                removes = sum(1 for e in d.get("edits") or [] if e.get("kind") == "remove_turn")
                if removes and d.get("decision") == "edit" and len(d["turns"] or []) > len(task["turns"]) - removes:
                    # round 7: a remove_turn edit was listed but the turn stayed (false premise kept in the task)
                    convo += ("\n\nYour edits list remove_turn but the turns you returned still contain that turn. "
                              "Return the final JSON again with the turns exactly as the task should be.")
                    d = None
                    continue
            rec_out.update({k: v for k, v in d.items()
                            if k not in ("task_id", "model", "queries_run", "revision", "input_key")})
            rec_out.pop("error", None)
            break
        except Exception as ex:  # noqa: BLE001
            rec_out["error"] = f"{type(ex).__name__}: {str(ex)[:200]}"
    Path(path + ".tmp").write_text(json.dumps(rec_out, ensure_ascii=False, indent=1))
    os.replace(path + ".tmp", path)
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
            if str(t.get("exclude") or "").startswith(("docs-only", "reference made no tool")):
                t["builder_exclude_overridden"] = t.pop("exclude")  # the curator decides soft exclusions
                t["exclude"] = None
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
