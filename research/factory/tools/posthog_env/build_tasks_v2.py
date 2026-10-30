#!/usr/bin/env python3
"""Build v2 task files (runner/tasks/v2/<split>.jsonl) for the v2 twin teams (loader/teams_v2.jsonl). Stdlib only.

Differences from build_tasks.py (v1 files are not touched):
- every human turn of the conversation is kept and `max_turns` equals the number of turns (run with --max-turns 0);
- /project/<production id>/ in the user text points at the v2 twin's project id;
- absolute dates in the user text (2026-10-11, Oct 11, October 11, 2026, 11 Oct) move by the twin's shift_days, the
  same shift the loader applied to the data;
- follow-ups whose premise depends on the production answer are marked: a later turn that quotes concrete facts
  (numbers, quoted strings, identifiers, names) that first appeared in the production assistant's answers, not in
  earlier user turns. Option A: `turns` stops before the first such follow-up (`turns_full` keeps all, `followups`
  holds the per-turn flags and the evidence kinds);
- turns whose production SQL was anonymizer-corrupted are listed in `corrupted_sql_turns` (qfacts_v2).

    python3 build_tasks_v2.py [--splits test_v2,dev]
Prints counts only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from collections import Counter

TEAMS_V2 = "/opt/posthog-env/loader/teams_v2.jsonl"
SPECS = "/opt/posthog-sft/env-research/twins/specs"
QFACTS = "/opt/posthog-sft/env-research/twins/qfacts_v2"
OUT = "/opt/posthog-env/runner/tasks/v2"
TRACES = {"test_v2": "/opt/posthog-sft/eval/data/test_v2.jsonl", "dev": "/opt/posthog-sft/root_agent/data_all/dev.jsonl"}
SPLIT_MAP = {"dev": "dev", "test_v2": "test", "train": "train"}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December"]
MON = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
ISO = re.compile(r"\b(20\d\d)-([01]\d)-([0-3]\d)\b")
MD = re.compile(rf"\b{MON}\.? ([0-3]?\d)(?:st|nd|rd|th)?\b(,? (20\d\d))?")
DM = re.compile(rf"\b([0-3]?\d)(?:st|nd|rd|th)? {MON}\b(,? (20\d\d))?")
PROJ = re.compile(r"/project/(\d+)/")


def rows(path):
    with open(path) as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def shift_text(s: str, days: int, now: dt.date) -> tuple[str, int]:
    if not days:
        return s, 0
    n = 0

    def iso(m):
        nonlocal n
        try:
            d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) + dt.timedelta(days=days)
        except ValueError:
            return m.group(0)
        n += 1
        return d.isoformat()

    def month_day(mon: str, day: str, year: str | None, fmt) -> str | None:
        mi = MONTHS.index(mon[:3].lower())
        y = int(year) if year else now.year
        try:
            d = dt.date(y, mi + 1, int(day))
        except ValueError:
            return None
        if not year and d > now + dt.timedelta(days=31):
            d = d.replace(year=y - 1)
        d2 = d + dt.timedelta(days=days)
        full = len(mon) > 4 or mon in ("June", "July")
        name = MONTH_FULL[d2.month - 1] if full else MONTH_FULL[d2.month - 1][:3]
        return fmt(name, d2.day, d2.year if year else None)

    def md(m):
        nonlocal n
        r = month_day(m.group(1), m.group(2), m.group(4),
                      lambda nm, d, y: f"{nm} {d}" + (f"{m.group(3)[:-4]}{y}" if y else ""))
        if r is None:
            return m.group(0)
        n += 1
        return r

    def dm(m):
        nonlocal n
        r = month_day(m.group(2), m.group(1), m.group(4),
                      lambda nm, d, y: f"{d} {nm}" + (f"{m.group(3)[:-4]}{y}" if y else ""))
        if r is None:
            return m.group(0)
        n += 1
        return r

    s = ISO.sub(iso, s)
    s = MD.sub(md, s)
    s = DM.sub(dm, s)
    return s, n


# ---------------------------------------------------------------- follow-up premise detection
NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(%|k|K|M)?(?![\w])")
QUOTED = re.compile(r"[`\"“]([^`\"”\n]{3,60})[`\"”]")
IDENT = re.compile(r"\b(\$?[a-z][a-z0-9]*(?:[_.$][a-z0-9]+)+)\b")
CAPS = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)+)\b")
DEIXIS = re.compile(r"\b(you (?:said|mentioned|found|showed|listed|noted|flagged|identified)|as you (?:said|mentioned)|"
                    r"the (?:first|second|third|fourth|top|last|other) (?:one|row|item|result|two|three|option)s?|"
                    r"(?:that|this|the) (?:spike|drop|dip|jump|increase|decrease|decline|surge|anomaly|outlier|number|figure|"
                    r"discrepancy|gap|difference|result|table|chart|list|breakdown|query|insight|finding|pattern|trend)|"
                    r"(?:those|these) (?:users|people|accounts|orgs|organizations|customers|companies|events|numbers|results|"
                    r"sessions|pages|errors|ones|\d+)|why (?:is|did|was|are|were) (?:it|that|this|they|there)|"
                    r"(?:option|number|item|point) (?:\d|one|two|three|a|b|c)\b)", re.I)
STOP_NUM = {str(i) for i in range(0, 32)} | {"7", "14", "30", "60", "90", "100", "2024", "2025", "2026"}


def salient(text: str) -> dict[str, set]:
    out = {"number": set(), "quoted": set(), "identifier": set(), "name": set()}
    for m in NUM.finditer(text):
        v = m.group(1).replace(",", "")
        if v in STOP_NUM or (len(v) < 3 and not m.group(2)):
            continue
        out["number"].add(v + (m.group(2) or "").lower())
    for m in QUOTED.finditer(text):
        out["quoted"].add(m.group(1).strip().lower())
    for m in IDENT.finditer(text):
        out["identifier"].add(m.group(1).lower())
    for m in CAPS.finditer(text):
        out["name"].add(m.group(1).lower())
    return out


def premise_flags(turns: list[str], answers: list[str]) -> list[dict]:
    """Per turn i>0: facts quoted from production answers 0..i-1 that no earlier user turn mentioned."""
    flags = [{"turn": 0, "depends_on_answer": False}]
    for i in range(1, len(turns)):
        prior_user = " ".join(turns[:i]).lower()
        prior_ans = " ".join(answers[:i]).lower()
        ev = Counter()
        for kind, vals in salient(turns[i]).items():
            for v in vals:
                if v in prior_user:
                    continue
                if v in prior_ans:
                    ev[kind] += 1
        if DEIXIS.search(turns[i]):
            ev["deixis"] += 1
        dep = bool(ev["number"] or ev["quoted"] or ev["identifier"] or ev["name"] or ev["deixis"])
        flags.append({"turn": i, "depends_on_answer": dep, "evidence": dict(ev)})
    return flags


def answers_by_turn(rec: dict) -> list[str]:
    out: list[str] = []
    cur: list[str] = []
    started = False
    for m in rec["messages"]:
        c = m["content"]
        human = m["role"] == "user" and (isinstance(c, str) or not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c))
        if human:
            if started:
                out.append("\n".join(cur))
            cur, started = [], True
            continue
        if m["role"] == "assistant":
            if isinstance(c, str):
                cur.append(c)
            else:
                cur.extend(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    if started:
        out.append("\n".join(cur))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", default="test_v2,dev")
    a = ap.parse_args()
    latest = {}
    for r in rows(TEAMS_V2) if os.path.exists(TEAMS_V2) else []:
        if r.get("removed"):
            latest.pop(r.get("twin_id"), None)
        else:
            latest[r["twin_id"]] = r
    by_cid = {}
    for r in latest.values():
        for cid in r.get("members") or []:
            by_cid[cid] = r
    stats = Counter()
    by_split: dict[str, list] = {}
    for split in a.splits.split(","):
        for rec in rows(TRACES[split]):
            cid = rec["id"]
            team = by_cid.get(cid)
            if team is None:
                stats[f"{split}_no_v2_team"] += 1
                continue
            spec = json.load(open(os.path.join(SPECS, f"{cid}.json")))
            tturns = [t for t in sorted(spec.get("tasks") or [], key=lambda t: t.get("turn", 0)) if (t.get("text") or "").strip()]
            if not tturns:
                stats[f"{split}_no_turns"] += 1
                continue
            shift = int(team.get("shift_days") or 0)
            twin_now = dt.datetime.fromisoformat(str(team["twin_now_utc"]).replace("Z", "+00:00")).date()
            texts, n_dates, n_urls = [], 0, 0
            for t in tturns:
                s, k = shift_text(t["text"], shift, twin_now)
                n_dates += k
                s2 = PROJ.sub(f"/project/{team['project_id']}/", s)
                n_urls += s2 != s
                texts.append(s2)
            answers = answers_by_turn(rec)
            answers += [""] * (len(tturns) - len(answers))
            flags = premise_flags([t["text"] for t in tturns], answers)
            first_dep = next((f["turn"] for f in flags if f["depends_on_answer"]), None)
            qf = os.path.join(QFACTS, f"{cid}.json")
            corrupted = sorted({c["turn"] for c in json.load(open(qf))["calls"] if c.get("corrupted")}) if os.path.exists(qf) else []
            tz = (spec.get("project") or {}).get("timezone") or {}
            out_split = SPLIT_MAP.get(split, split)
            task = {
                "task_id": cid, "source": "twin_v2", "split": out_split, "team_id": int(team["team_id"]),
                "project_id": int(team["project_id"]), "twin_id": team["twin_id"], "conversation_id": cid,
                "turns": texts[:first_dep] if first_dep else texts,
                "turns_full": texts, "max_turns": len(texts),
                "followups": flags, "first_answer_dependent_turn": first_dep,
                "agent_mode": None, "spec_agent_mode": spec.get("agent_mode"),
                "reference_tools": [t.get("tools") for t in tturns],
                "corrupted_sql_turns": corrupted,
                "shifted_dates_in_text": n_dates, "rewritten_project_urls": n_urls,
                "twin_current_time_utc": tz.get("current_time_utc"), "twin_now_utc": team.get("twin_now_utc"),
                "shift_days": shift, "loaded_now_utc": team.get("loaded_now_utc"), "twin_timezone": tz.get("abbr"),
            }
            by_split.setdefault(out_split, []).append(task)
            stats[f"{out_split}_tasks"] += 1
            stats[f"{out_split}_turns_full"] += len(texts)
            stats[f"{out_split}_turns_optionA"] += len(task["turns"])
            stats[f"{out_split}_multi_turn"] += len(texts) > 1
            stats[f"{out_split}_over_4_turns"] += len(texts) > 4
            stats[f"{out_split}_answer_dependent_followups"] += sum(f["depends_on_answer"] for f in flags)
            stats[f"{out_split}_tasks_truncated_optionA"] += first_dep is not None
            stats[f"{out_split}_tasks_with_shifted_dates"] += n_dates > 0
            stats[f"{out_split}_tasks_with_url_rewrite"] += n_urls > 0
            stats[f"{out_split}_tasks_with_corrupted_sql_turns"] += bool(corrupted)
    os.makedirs(OUT, exist_ok=True)
    for split, tasks in by_split.items():
        tasks.sort(key=lambda t: hashlib.sha256(f"phai-runner-v1:{t['task_id']}".encode()).hexdigest())
        p = os.path.join(OUT, f"{split}.jsonl")
        with open(p + ".tmp", "w") as f:
            for t in tasks:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        os.replace(p + ".tmp", p)
    print(json.dumps(dict(sorted(stats.items()))))


if __name__ == "__main__":
    main()
