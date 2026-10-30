#!/usr/bin/env python3
"""Spot-check cards for twin-environment tasks (runs on fbf8, system python; data never leaves the host).

One plain-text card per task with everything a reviewer needs to judge whether the task is sound:
  1. task: turns as the agent sees them, scripted follow-ups, answer-dependent turn, agent mode, team, twin clock
  2. build verdict: per-task status, reasons and checks from the build's status.json; calibration flag
  3. production reference: the original conversation (user turns, tool calls with args, tool results, answers),
     clipped, with the turns the task uses marked
  4. twin state: event span and counts (top events with 90-day counts), persons, warehouse tables, saved objects
  5. replay: how each production tool call fared when re-run in the twin (rows, comparison class)
  6. reviewer checklist (defect classes)

    python3 spot_card.py --tasks runner/tasks/v2_reanon/test.jsonl --traces DIR/test_v2.jsonl \
        --replay /tmp/fid2_reanon --out /opt/posthog-sft/env-research/twins_reanon/spot/r1 --sample 20 --seed 1
    python3 spot_card.py ... --ids <task_id_prefix>,<task_id_prefix>

Prints the card paths and aggregate counts only.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import urllib.parse
import urllib.request

CH_DB, PG_DB = "posthog_ai_eval", "test_posthog_ai_eval"

CHECKLIST = """## Reviewer checklist (mark each: ok / DEFECT <class> <one line> / n.a.)
- T1 request clear and self-contained (no missing earlier context, no reference to something the agent cannot see)
- T2 request is checkable (a definite answer, object or finding exists; not open-ended advice only)
- T3 scripted follow-ups still make sense whatever the agent answered (or task truncates before them)
- D1 twin has the events / properties / persons the request needs, with non-trivial volume in the asked window
- D2 twin has the warehouse tables / columns the request needs
- D3 objects the request names (insight, dashboard, notebook, flag, experiment, survey, error) exist in the twin
- D4 numbers in the twin are plausible against production (same order of magnitude, same trend direction)
- D5 dates line up (relative windows land on data; absolute dates in the text were shifted)
- A1 anonymization artefact visible in the task or twin (mangled identifier, wrong-business fake, inconsistent fake)
- R1 production reference answer is supported by its own tool results (no wrong numbers, no invented facts)
- R2 production reference relies on core memory / external context not in the transcript
- G1 judge can grade it (enough is observable; docs-only questions have the docs index)
- verdict: KEEP / FIX (<what>) / DROP (<why>)
"""


def ch(q: str):
    params = {"database": CH_DB, "default_format": "JSONCompact", "max_execution_time": "60", "max_threads": "2"}
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8123/?" + urllib.parse.urlencode(params), data=q.encode(), timeout=90)
        return json.loads(r.read())["data"]
    except Exception as e:  # noqa: BLE001
        return [[f"ERR {type(e).__name__}: {str(e)[:200]}"]]


def pg(q: str):
    out = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "posthog", "-d", PG_DB, "-At", "-F", "\t", "-c", q],
                         capture_output=True, text=True, env={**os.environ, "PGPASSWORD": "posthog"})
    if out.returncode:
        return [[f"ERR {out.stderr[:200]}"]]
    return [line.split("\t") for line in out.stdout.splitlines() if line]


def clip(s, n: int) -> str:
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    s = s.strip()
    return s if len(s) <= n else s[: n // 2] + f"\n   …[{len(s) - n} chars omitted]…\n" + s[-n // 2:]


def blocks(m: dict) -> list[dict]:
    c = m.get("content")
    return [{"type": "text", "text": c}] if isinstance(c, str) else (c or [])


def render_trace(rec: dict, n_task_turns: int, max_result: int, max_text: int) -> list[str]:
    out, turn = [], -1
    for m in rec.get("messages") or []:
        bs = blocks(m)
        if m.get("role") == "user" and not any(b.get("type") == "tool_result" for b in bs):
            text = "\n".join(b.get("text") or "" for b in bs if b.get("type") == "text").strip()
            if text:
                turn += 1
                mark = "IN TASK" if turn < n_task_turns else "not in task"
                out.append(f"\n>>> USER turn {turn} ({mark}):\n{clip(text, max_text)}")
            continue
        for b in bs:
            t = b.get("type")
            if t == "text" and (b.get("text") or "").strip():
                out.append(f"  ASSISTANT: {clip(b['text'], max_text)}")
            elif t == "tool_use":
                out.append(f"  CALL {b.get('name')}: {clip(b.get('input'), 900)}")
            elif t == "tool_result":
                s = b.get("content")
                if isinstance(s, list):
                    s = "\n".join(x.get("text", "") for x in s if isinstance(x, dict))
                out.append("    -> " + clip(s or "", max_result).replace("\n", "\n       "))
    return out


def twin_state(t: dict) -> list[str]:
    tid = int(t["team_id"])
    now = (t.get("loaded_now_utc") or "")[:19].replace("T", " ")
    out = []
    out += [f"team: {pg(f'select name, timezone from posthog_team where id={tid}')}"]
    span = ch(f"select min(timestamp), max(timestamp), count(), uniqExact(person_id) from events where team_id={tid}")
    out += [f"events span/count/persons-with-events: {span}"]
    out += [f"persons: {ch(f'select count() from person where team_id={tid}')}"]
    ev = ch(f"select event, count(), countIf(timestamp >= toDateTime('{now}') - interval 90 day), "
            f"toDate(min(timestamp)), toDate(max(timestamp)) from events where team_id={tid} "
            f"group by event order by 2 desc limit 40")
    out.append("top events (event | total | last 90d | first | last):")
    out += [f"   {r}" for r in ev]
    paths = ch(f"select domain(JSONExtractString(properties, '$current_url')) AS host, "
               f"path(JSONExtractString(properties, '$current_url')) AS p, count() from events "
               f"where team_id={tid} and event in ('$pageview', '$screen') group by host, p order by 3 desc limit 25")
    out.append("top pages (host | path | pageviews):")
    out += [f"   {r}" for r in paths]
    dw = pg(f"select name, row_count, left(columns::text, 400) from posthog_datawarehousetable "
            f"where team_id={tid} and deleted is not true")
    out.append(f"warehouse tables ({len(dw)}):")
    out += [f"   {r}" for r in dw[:20]]
    for label, q in (("insights", f"select short_id, name from posthog_dashboarditem where team_id={tid} and deleted is not true limit 30"),
                     ("dashboards", f"select id, name from posthog_dashboard where team_id={tid} and deleted is not true limit 30"),
                     ("notebooks", f"select short_id, title from posthog_notebook where team_id={tid} limit 30"),
                     ("flags", f"select key, active from posthog_featureflag where team_id={tid} and deleted is not true limit 40"),
                     ("experiments", f"select id, name from posthog_experiment where team_id={tid} limit 20"),
                     ("surveys", f"select id, name from posthog_survey where team_id={tid} limit 20")):
        rows = pg(q)
        out.append(f"{label} ({len(rows)}): {rows[:30]}")
    return out


def event_props(t: dict, max_events: int = 6) -> list[str]:
    """Top property values (by count) for the twin events that the task text names, so a reviewer or editor can
    check premises about values (channels, plans, page types) without querying."""
    tid = int(t["team_id"])
    names = [r[0] for r in ch(f"select event from events where team_id={tid} group by event order by count() desc limit 300")]
    text = " ".join(x if isinstance(x, str) else json.dumps(x) for x in t.get("turns") or []).lower()
    named = [e for e in names if isinstance(e, str) and len(e) > 3 and e.lower() in text][:max_events]
    out = []
    for e in named:
        esc = e.replace("'", "\\'")
        keys = ch(f"select arrayJoin(JSONExtractKeys(properties)) AS k, count() from events where team_id={tid} "
                  f"and event='{esc}' group by k order by 2 desc limit 60")
        out.append(f"   all property keys (with counts): {[(k, n) for k, n in keys]}")
        total = ch(f"select count() from events where team_id={tid} and event='{esc}'")
        out.append(f"event {e!r}: total {total}")
        for k, _n in keys[:25]:
            if str(k) in ("$session_id", "$window_id", "$insert_id", "$time", "$sent_at", "token", "$device_id"):
                continue
            ke = str(k).replace("'", "\\'")
            vals = ch(f"select JSONExtractString(properties, '{ke}') AS v, count() from events where team_id={tid} "
                      f"and event='{esc}' group by v order by 2 desc limit 6")
            out.append(f"   {k}: {vals}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--traces", required=True, help="trace jsonl holding the tasks' conversations")
    ap.add_argument("--status", default="", help="build status.json (default: next to --tasks)")
    ap.add_argument("--replay", default="", help="build replay dir (replay.jsonl, sql_cls.json)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--ids", default="", help="comma-separated task id prefixes (overrides --sample)")
    ap.add_argument("--exclude", default="", help="file with task ids already reviewed (one per line)")
    ap.add_argument("--max-result", type=int, default=1500)
    ap.add_argument("--max-text", type=int, default=4000)
    a = ap.parse_args()

    tasks = [json.loads(x) for x in open(a.tasks) if x.strip()]
    if a.ids:
        pre = a.ids.split(",")
        tasks = [t for t in tasks if any(t["task_id"].startswith(p) for p in pre)]
    else:
        seen = set(open(a.exclude).read().split()) if a.exclude and os.path.exists(a.exclude) else set()
        pool = [t for t in tasks if t["task_id"] not in seen]
        random.Random(a.seed).shuffle(pool)
        tasks = pool[: a.sample]
    status_path = a.status or os.path.join(os.path.dirname(a.tasks), "status.json")
    status = (json.load(open(status_path)).get("tasks") or {}) if os.path.exists(status_path) else {}
    replay, sqlc = {}, {}
    if a.replay and os.path.exists(f"{a.replay}/replay.jsonl"):
        for line in open(f"{a.replay}/replay.jsonl"):
            r = json.loads(line)
            replay.setdefault(r.get("cid"), []).append(r)
        if os.path.exists(f"{a.replay}/sql_cls.json"):
            sqlc = json.load(open(f"{a.replay}/sql_cls.json"))
    want = {t["conversation_id"] for t in tasks}
    traces = {}
    for line in open(a.traces):
        r = json.loads(line)
        if str(r.get("id")) in want:
            traces[str(r["id"])] = r
    os.makedirs(a.out, exist_ok=True)
    for i, t in enumerate(tasks, 1):
        cid = t["conversation_id"]
        st = status.get(t["task_id"]) or status.get(cid) or {}
        L = [f"# CARD {i:02d}  task {t['task_id']}  conversation {cid[:8]}  source {t.get('source')}  split {t.get('split')}",
             f"agent_mode {t.get('agent_mode')} (spec {t.get('spec_agent_mode')})  team {t['team_id']}  tz {t.get('twin_timezone')}  "
             f"twin now {t.get('loaded_now_utc')}  shift_days {t.get('shift_days')}  shifted dates in text {t.get('shifted_dates_in_text')}  "
             f"max_turns {t.get('max_turns')}  first answer-dependent turn {t.get('first_answer_dependent_turn')}",
             f"reference tools {t.get('reference_tools')}  corrupted sql turns {t.get('corrupted_sql_turns')}  env {t.get('env_defaults')}",
             "", "## 1. Task turns (sent to the agent)"]
        for k, turn in enumerate(t["turns"]):
            L.append(f"[turn {k}] {clip(turn if isinstance(turn, str) else json.dumps(turn), a.max_text)}")
        if t.get("followups"):
            L.append(f"followups meta: {clip(t.get('followups'), 800)}")
        if t.get("curation"):
            cu = t["curation"]
            L += ["", "## 1b. Curation (LLM editor)",
                  f"decision {cu.get('decision')} ({cu.get('drop_kind') or ''}) difficulty {cu.get('difficulty')} skills {cu.get('skills')}",
                  f"reason: {cu.get('reason')}", f"edits: {clip(cu.get('edits'), 1500)}"]
            if cu.get("twin_gap"):
                L.append(f"twin gap: {cu.get('twin_gap')}")
            for k, turn in enumerate(t.get("turns_built") or []):
                L.append(f"[built turn {k}] {clip(turn, 2500)}")
            if t.get("grading_notes"):
                L.append(f"grading notes: {clip(t['grading_notes'], 3000)}")
            if t.get("twin_overrides"):
                L.append(f"twin overrides (applied): {clip(t['twin_overrides'], 1500)}")
        L += ["", "## 2. Build verdict",
              f"status {st.get('status')}  reasons {st.get('reasons')}  calib {st.get('calib_flag')} {st.get('calib_reason') or ''}",
              f"checks {st.get('checks')}", f"needs {st.get('needs')}", f"fixes {st.get('fixes')}  artefact {st.get('artefact_check')}"]
        L += ["", "## 3. Production reference conversation"]
        rec = traces.get(cid)
        L += render_trace(rec, len(t["turns"]), a.max_result, a.max_text) if rec else ["(trace not found)"]
        L += ["", "## 4. Twin state"] + twin_state(t) + event_props(t)
        L += ["", "## 5. Replay of production calls in the twin"]
        for r in replay.get(cid, []):
            row = {k: r.get(k) for k in ("tool", "kind", "k", "exists", "n_rows", "dw_cmp") if k in r}
            if r.get("tool") == "execute_sql":
                row["cls"] = sqlc.get(f"{cid}:{r.get('k')}", "prod_failed")
            if isinstance(r.get("shifted"), dict) and r["shifted"].get("err"):
                row["err"] = str(r["shifted"]["err"])[:160]
            L.append(f"   {row}")
        if not replay.get(cid):
            L.append("   (no replay rows)")
        L += ["", CHECKLIST]
        path = f"{a.out}/card_{i:02d}_{t['task_id'][:8]}.txt"
        open(path, "w").write("\n".join(str(x) for x in L))
        print(path)
    open(f"{a.out}/ids.txt", "w").write("\n".join(t["task_id"] for t in tasks) + "\n")
    print(json.dumps({"cards": len(tasks), "traces_found": len(traces)}))


if __name__ == "__main__":
    main()
