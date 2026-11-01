#!/usr/bin/env python3
"""v4 task synthesis: tasks written against a clean twin's real data, guided by the production task map (fbf8).

Replaying production conversations ties every task to a situation the generic twin rarely reproduces (complex
conversations: 4-7% yield, mostly premise/data mismatches). v4 inverts it: the twin is the ground truth and the
production traces are a map of what users ask (families, phrasing, difficulty). Per (twin, family):
  1. an author model explores the twin with read-only queries (CT.run_queries) and finds something worth asking,
  2. writes the request (1-3 turns, in the style of real production requests of that family), reference queries whose
     results determine the answer, and grading notes built only from results it has seen,
  3. the reference queries are re-run here; a task whose answer queries fail or return nothing is rejected,
  4. the task then goes through validate_tasks (validator, Opus gate, repairs) like every other task.

    python3 synth_tasks.py --base B1/validated/validated.jsonl[,B2...] --twins 10 --per-twin 5 --out DIR [--seed 7]
Writes DIR/tasks.jsonl (bench/validator compatible; field "synth" holds family, reference queries and results).
"""

from __future__ import annotations

import argparse
import collections as C
import hashlib
import json
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/opt/posthog-env/runner")
sys.path.insert(0, "/opt/posthog-env")
import curate_tasks as CT  # noqa: E402  (run_queries: team-scoped, read-only, warehouse macro)
import llm_proxy  # noqa: E402
import spot_card as SC  # noqa: E402

INTENTS = "/opt/posthog-sft/env-research/intent/intents.jsonl"
TRACES = "/opt/posthog-sft/env-research/twins_reanon/traces/train.jsonl"
CTX = re.compile(r"<(system_reminder|attached_context|voice_mode)>.*?</\1>", re.S)
# production family shares are reweighted toward analysis: docs-only and trivial lookups are capped
REWEIGHT = {"product_howto": 0.25, "metric_lookup": 0.5, "other": 0.0, "tracking_quality": 0.7}
FAMILY_DESC = {
    "metric_lookup": "a specific number or simple trend the user needs for a decision",
    "trend_breakdown": "compare or break down a metric over time or by segment and explain what differs",
    "funnel_conversion": "conversion through steps, where users drop off and for whom",
    "retention_engagement": "retention, stickiness, cohorts or active users and what drives them",
    "anomaly_investigation": "why a metric changed: find the change, isolate the segment/cause, quantify it",
    "attribution_marketing": "which sources/campaigns/referrers bring users who convert or stay",
    "entity_lookup": "what a specific user/account/org did and what stands out",
    "sql_help": "write or fix a HogQL query for a precise question and report its result",
    "build_insight_dashboard": "create insights/dashboards that answer a stated need (objects must be created)",
    "session_replay": "find recordings matching a behaviour and summarise what happens in them",
    "flags_experiments": "create or analyse feature flags/experiments",
    "surveys": "create or analyse surveys",
    "errors_logs": "find, quantify and prioritise errors/exceptions",
    "llm_analytics": "analyse LLM generations: cost, latency, errors by model/feature",
    "warehouse": "join warehouse tables with events/persons to answer a business question",
    "product_howto": "how to do something in PostHog, grounded in this project's setup",
    "tracking_quality": "find instrumentation problems in this project's events/properties",
}

AUTHOR = """You design ONE evaluation task for PostHog AI (an analytics agent with tools: taxonomy reads, HogQL/SQL over
events/persons/sessions/recordings/warehouse, insights, dashboards, notebooks, flags, experiments, surveys, docs
search). The task runs against the synthetic PostHog project described below; scores of models on it are used to train
them, so it must be realistic, hard enough to separate strong from weak agents, and exactly gradeable.

## Task family: {family} — {family_desc}
Target difficulty {difficulty}/5 (3 = several dependent steps; 4-5 = investigation with segmentation/comparison and a
judgment call). Real users of this family asked things like (style only; do not copy their entities):
{exemplars}

## The project (ground truth; data ends at {now}, the agent's "now")
{twin}

## PostHog objects in the project
{objects}

## How to work
1. Explore with read-only queries until you find something genuinely worth asking about in THIS data (a real
   difference between segments, a drop/spike, a funnel step that leaks for a cohort, a source whose users retain
   differently, an object that answers or fails a need). Reply with {{"queries": [{{"why": "...", "sql": "..."}}]}}
   (at most 8 per round, up to 4 rounds). Every query must contain `team_id = {{team}}`; tables:
   events(team_id, event, timestamp, distinct_id, person_id, properties), person(team_id, id, properties),
   session_replay_events(team_id, session_id, distinct_id, min_first_timestamp, ...), warehouse('<name>').
   properties are JSON strings (JSONExtractString(properties, 'k')).
2. Then write the task. Rules:
   - The request reads like a real user of this product (their vocabulary, their business), 1-3 turns; later turns
     are follow-ups that make sense whatever the agent answered first. No hints about which events/properties/tables
     to use beyond what a real user would say. Never state the answer.
   - Everything the request presupposes is true in this data (verified by your queries); relative windows refer to
     the data end above.
   - It needs several dependent steps (except product_howto); it must not be answerable by one obvious lookup.
   - Prefer questions this data answers substantively (a real finding with numbers). A task built around data that
     does not exist (the agent must notice an event is missing and pick a proxy) is allowed only when it is the most
     realistic request for this family here; most tasks should have a substantive answer.
   - reference_queries: the minimal set of queries whose results determine a correct answer (they will be re-run).
   - grading_notes are built ONLY from results you have seen: must_include = the findings a correct final answer
     states (phrase each as "the final answer states ..."), with numbers only where they follow unambiguously from the
     obvious query (give tolerances); acceptable_variations = other reasonable readings and their (non-empty) results;
     not_required = things a good answer may skip. Required points answer what the user asked; no unverified product
     facts.
   - If this data has nothing worth asking for this family, reply {{"skip": "<why>"}}.

Final answer, ONLY JSON:
{{"turns": ["<user turn 1>", ...], "agent_mode": "product_analytics|sql|...", "difficulty": <1-5>,
 "why_hard": "<what makes it multi-step>", "reference_queries": [{{"id": "q1", "purpose": "...", "sql": "..."}}],
 "findings": ["<fact from your results that the answer depends on>", ...],
 "grading_notes": {{"must_include": ["..."], "acceptable_variations": ["..."], "not_required": ["..."],
                    "how_to_check": "<queries/objects a grader should inspect>"}}}}"""


def jlines(path: str) -> list[dict]:
    return [json.loads(x) for x in open(path) if x.strip()]


def family_weights() -> dict:
    rows = jlines(INTENTS) if os.path.exists(INTENTS) else []
    cnt = C.Counter(r.get("family") for r in rows if r.get("family"))
    return {f: cnt.get(f, 0) * REWEIGHT.get(f, 1.0) for f in FAMILY_DESC if cnt.get(f, 0)}


def exemplars(family: str, rng, n: int = 3) -> list[str]:
    """User requests of this family from train conversations (style examples for the author)."""
    ids = [r["id"] for r in jlines(INTENTS) if r.get("family") == family and r.get("split") == "train"]
    want = set(rng.sample(ids, min(len(ids), 40)))
    out = []
    for line in open(TRACES):
        r = json.loads(line)
        if r["id"] not in want:
            continue
        for m in r.get("messages") or []:
            if m.get("role") == "user":
                t = CTX.sub(" ", " ".join(b.get("text") or "" for b in m.get("content") or []
                                          if isinstance(b, dict) and b.get("type") == "text")).strip()
                if 20 < len(t) < 800:
                    out.append(t)
                break
        if len(out) >= n:
            break
    return out


PLANTED_HINT = """

## A planted change you must build the task around (ground truth; verify it with queries first)
Event `{event}` for the segment {where} was multiplied by {factor} from {fr} to {to} ({state}); every other segment is
unchanged. Write an investigation task whose correct answer discovers this: the user describes only the visible
symptom (e.g. that `{event}` volume or a conversion that depends on it changed, roughly since when), never the
segment or the cause. must_include: the change and its timing, the segment responsible (and that other segments are
stable), its size relative to the baseline; acceptable_variations: equivalent segment descriptions."""


def author(base: dict, family: str, difficulty: int, rng, model: str, out_dir: str, planted: dict | None = None) -> dict:
    key = hashlib.sha256(f"{base['twin_id']}:{family}:{difficulty}:{bool(planted)}".encode()).hexdigest()[:12]
    path = f"{out_dir}/raw/{key}.json"
    if os.path.exists(path):
        return json.load(open(path))
    twin = "\n".join(str(x) for x in SC.twin_state(base) + SC.event_props(base))
    ex = exemplars(family, rng) or ["(none)"]
    prompt = AUTHOR.format(family=family, family_desc=FAMILY_DESC[family], difficulty=difficulty,
                           exemplars="\n".join(f"- {SC.clip(e, 500)}" for e in ex), now=base.get("loaded_now_utc"),
                           twin=SC.clip(twin, 24000), objects=SC.clip(SC.team_objects(base["team_id"]), 4000))
    if base.get("_avoid"):
        prompt += ("\n\n## Known minor data defects in this project (do not build the task on these areas)\n" +
                   "\n".join(f"- {x}" for x in base["_avoid"][:12]))
    if planted:
        prompt += PLANTED_HINT.format(event=planted["event"], where=json.dumps(planted["where"]), factor=planted["factor"],
                                      fr=planted["from"], to=planted["to"],
                                      state="still ongoing at the data end" if planted.get("ongoing") else "then back to normal")
    rec = {"key": key, "twin_id": base["twin_id"], "family": family, "difficulty_target": difficulty,
           "queries_run": [], "model": model}
    convo, rounds = prompt, 0
    for _ in range(9):
        try:
            text, _u = llm_proxy.judge_complete(convo, model, None, attempts=6, preamble=False)
            d = json.loads(text[text.find("{"):text.rfind("}") + 1])
            if d.get("queries") and "turns" not in d and rounds < 4:
                rounds += 1
                res = CT.run_queries(d["queries"][:8], int(base["team_id"]))
                rec["queries_run"] += res
                convo += (f"\n\n## Your queries and results (round {rounds})\n" +
                          "\n".join(f"- {r['why']}\n  SQL: {r['sql']}\n  -> {r['result']}" for r in res) +
                          ("\n\nNow write the final JSON." if rounds >= 4 else "\n\nQuery more or write the final JSON."))
                continue
            rec.update(d)
            break
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(rec, open(path, "w"), ensure_ascii=False, indent=1)
    return rec


def verify(rec: dict, team: int) -> tuple[bool, list]:
    """Re-run the reference queries: every one must succeed and at least one must return rows."""
    # the author often writes the literal team id; run_queries requires the {team} placeholder (pilot 1: 20 rejected)
    qs = [{"why": q.get("purpose", ""), "sql": re.sub(rf"\b{team}\b", "{team}", q.get("sql", ""))
           if "{team}" not in q.get("sql", "") else q.get("sql", "")} for q in rec.get("reference_queries") or []]
    if not qs:
        return False, []
    res = CT.run_queries(qs, team)
    ok = all(not str(r["result"]).startswith(("ERROR", "REJECTED")) for r in res) and \
        any(str(r["result"]) not in ("[]", "") for r in res)
    return ok, res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="validated.jsonl files of built batches (twins + team ids)")
    ap.add_argument("--twins", type=int, default=10)
    ap.add_argument("--per-twin", type=int, default=5)
    ap.add_argument("--min-events", type=int, default=20000)
    ap.add_argument("--exclude-lint", default="", help="lint.jsonl files: skip twins with material findings")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--planted", default="", help="planted.jsonl: planted twins get one investigation task built on it")
    ap.add_argument("--only-planted", action="store_true", help="use only the planted twins")
    ap.add_argument("--audit", default="", help="audit.jsonl from audit_twins.py: skip MATERIAL twins, avoid minor defects")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    os.makedirs(a.out, exist_ok=True)
    bad = set()
    for f in filter(None, a.exclude_lint.split(",")):
        for r in jlines(f):
            if any(x.get("severity") == "material" for x in r.get("findings") or []):
                bad.add(r["project"][:36])
    reg = {}
    for line in open("/opt/posthog-env/loader/teams_v2_loop.jsonl"):
        r = json.loads(line)
        if not r.get("removed") and r.get("twin_id"):
            reg[r["twin_id"]] = r
    bases = {}
    for f in a.base.split(","):
        for t in jlines(f):
            r = reg.get(t["twin_id"])
            if not r or t["twin_id"] in bad or (r.get("events") or 0) < a.min_events:
                continue
            bases.setdefault(t["twin_id"], {**t, "team_id": r["team_id"], "project_id": r.get("project_id") or r["team_id"],
                                            "loaded_now_utc": r.get("loaded_now_utc"), "shift_days": r.get("shift_days")})
    if a.audit:
        aud = {json.loads(x)["twin_id"]: json.loads(x) for x in open(a.audit)}
        for tw in list(bases):
            r = aud.get(tw)
            if r is None or r.get("verdict") not in ("CLEAN", "MINOR"):
                bases.pop(tw)  # not audited, failed, or MATERIAL
            else:
                bases[tw]["_avoid"] = [d.get("what") for d in r.get("defects") or [] if d.get("severity") == "minor"]
    planted = {json.loads(x)["twin_id"]: json.loads(x) for x in open(a.planted)} if a.planted else {}
    pool = sorted(t for t in bases if t in planted) if a.only_planted else sorted(bases)
    twins = rng.sample(pool, min(a.twins, len(pool)))
    fw = family_weights()
    fams, ws = list(fw), [fw[f] for f in fw]
    jobs = []
    for tw in twins:
        picked = []
        while len(picked) < a.per_twin:
            f = rng.choices(fams, ws)[0]
            if f not in picked or len(set(fams)) < a.per_twin:
                picked.append(f)
        if tw in planted:
            picked = ["anomaly_investigation"] + [f for f in picked if f != "anomaly_investigation"][:a.per_twin - 1]
        for f in picked:
            jobs.append((bases[tw], f, rng.choice([3, 3, 4, 4, 5]) if f != "product_howto" else 2,
                         planted.get(tw) if f == "anomaly_investigation" else None))
    print(json.dumps({"twins": len(twins), "jobs": len(jobs), "families": C.Counter(j[1] for j in jobs)}), flush=True)

    def run(job):
        base, fam, diff, pl = job
        rec = author(base, fam, diff, random.Random(f"{a.seed}:{base['twin_id']}:{fam}"), a.model, a.out, planted=pl)
        rec["planted"] = pl
        if rec.get("skip") or not rec.get("turns"):
            return None, rec
        if not ((rec.get("grading_notes") or {}).get("must_include")):
            rec["rejected"] = "no must_include"
            return None, rec
        ok, res = verify(rec, int(base["team_id"]))
        if not ok:
            rec["rejected"] = "reference queries failed or empty"
            return None, rec
        tid = f"v4-{rec['key']}"
        task = {**{k: base[k] for k in ("team_id", "project_id", "twin_id", "conversation_id", "loaded_now_utc",
                                        "shift_days", "env_defaults", "twin_timezone") if k in base},
                "task_id": tid, "source": "synth_v4", "split": base.get("split", "train"), "turns": rec["turns"],
                "turns_built": rec["turns"], "max_turns": len(rec["turns"]), "agent_mode": rec.get("agent_mode") or "product_analytics",
                "grading_notes": rec.get("grading_notes"),
                "curation": {"decision": "keep", "difficulty": {1: "trivial", 2: "trivial", 3: "moderate"}.get(rec.get("difficulty"), "hard"),
                             "reason": "synthesized v4", "twin_defects": []},
                "synth": {"family": fam, "difficulty": rec.get("difficulty"), "why_hard": rec.get("why_hard"),
                          "findings": rec.get("findings"), "reference_queries": rec.get("reference_queries"),
                          "reference_results": [r["result"] for r in res], "planted": rec.get("planted")}}
        return task, rec

    stats = C.Counter()
    with ThreadPoolExecutor(a.workers) as pool, open(f"{a.out}/tasks.jsonl", "w") as f:
        for task, rec in pool.map(run, jobs):
            stats["skip" if rec.get("skip") else "rejected" if rec.get("rejected") else "error" if not rec.get("turns")
                  else "ok"] += 1
            if task:
                stats[f"family_{task['synth']['family']}"] += 1
                f.write(json.dumps(task, ensure_ascii=False) + "\n")
    print(json.dumps(dict(stats)))


if __name__ == "__main__":
    main()
