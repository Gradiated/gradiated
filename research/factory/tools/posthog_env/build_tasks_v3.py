#!/usr/bin/env python3
"""Build v3 task files: build_tasks_v2 plus the fixes from spot-check round 1 (stdlib; runs on fbf8).

Changes against v2 (v2 is imported, not modified):
- dates: ISO dates on the first of a month inside a quoted SQL literal (`month = '2025-09-01'`) are not shifted, so
  they still match month-start warehouse rows; other dates (prose, daily result tables) shift by shift_days;
- capture placeholders: a turn containing "[truncated: N bytes too large for capture]" ends the task before it; a
  task whose first turn is such a placeholder is excluded;
- answer-dependent follow-ups: also bare acknowledgements ("yes", "ok", "go ahead", "sí", "sim", ...) and follow-ups
  that reuse a content phrase (3 consecutive non-stopwords) first introduced by the production assistant;
- greeting-only first turns ("hi", "hello", "hey there") are dropped when more turns follow;
- detection runs on the user's own words only: <system_reminder>, <attached_context> and <voice_mode> blocks (page
  context, attached results, current query) are stripped first, so phrases inside attached context no longer mark a
  turn as answer-dependent; quoted evidence needs 2+ words or 6+ characters (UI labels like "All" are not quotes);
  numbers with a unit ("80 days") and «»/‘’ quotes count; identical re-sent turns are collapsed;
- agent_mode = the conversation's production mode (sql, product_analytics, ...), so SQL-mode tasks start in SQL mode;
- tasks whose reference made no tool calls (docs/advice-only) are excluded from the default set (kept and marked);
  a reference turn with no final text is flagged (reference_no_final_answer);
- quality flags per task (`quality`): continuation summary, reference made no tool calls, clock mismatch (relative-day
  words while the conversation spans more than 6 h), off-topic code dump, capture placeholder; `exclude` holds the
  reason a task is excluded from the default set (None = include).

    TWIN_V2_ROOT=... TWIN_V2_TAG=... TWIN_V2_TRACES=... python3 build_tasks_v3.py --splits train [--ids a,b] [--out DIR]
Writes <out>/<split>.jsonl (default runner/tasks/v3<sfx>/). Prints counts only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter

sys.path.insert(0, "/opt/posthog-env/runner")
sys.path.insert(0, "/opt/posthog-sft/env-research/twingen/v2")
import build_tasks_v2 as V2  # noqa: E402
import paths as PATHS  # noqa: E402

CAPTURE = re.compile(r"\[truncated: \d+ bytes too large for capture\]")
ACK = re.compile(r"^\s*(yes|yeah|yep|yup|ok|okay|sure|go ahead|go for it|do it|please do|yes please|proceed|continue|"
                 r"sounds good|perfect|great|y|sí|si|dale|claro|sim|pode|ja|oui|d'accord|vas-y|let'?s do it|"
                 r"do that|both|all of them|the first one|the second one|option [a-c1-3])[\s.!,]*(please|pls|thanks)?[\s.!]*$",
                 re.I)
GREETING = re.compile(r"^\s*(hi|hello|hey|hey there|hi there|hola|olá|ola|bonjour|hallo|good (morning|afternoon|evening))"
                      r"[\s,.!]*(max|posthog|team)?[\s.!]*$", re.I)
RELDAY = re.compile(r"\b(yesterday|today|tonight|this morning|last night|right now|ayer|hoy|ontem|hoje|gestern|heute|"
                    r"hier|aujourd'hui)\b", re.I)
CONTINUATION = re.compile(r"(continued from a previous conversation|conversation (?:that )?ran out of context|"
                          r"summary of (?:the|our) (?:previous|earlier) (?:conversation|session)|previous session summary|"
                          r"<summary>|this session is being continued)", re.I)
POSTHOG_WORDS = re.compile(r"\b(posthog|event|insight|dashboard|funnel|retention|trend|user|session|query|sql|hogql|"
                           r"flag|experiment|survey|cohort|pageview|metric|data|chart)s?\b", re.I)
STOP = set("""a an the of to in on for and or but if then so with without by from at as is are was were be been being
this that these those it its it's we our you your i me my they them their he she his her not no do does did done can could
should would will just also more most less very how what why when where which who whom whose all any each every some
than too up down out over under again further once here there about into through during before after above below
between both few other such only own same yes ok please show give tell get make let like want need one two three""".split())
WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9_'-]+")
CTX = re.compile(r"<(system_reminder|attached_context|voice_mode)>.*?</\1>", re.S)
QUOTE2 = re.compile(r"[«‘'\"“`]([^«»‘’'\"“”`\n]{2,80})[»’'\"”`]")
NUM_UNIT = re.compile(r"\b(\d+(?:[.,]\d+)?)\s?(%|days?|d[ií]as|dias|weeks?|semanas?|hours?|horas?|users?|usuarios|usu[aá]rios|"
                      r"events?|eventos|rows?|filas|linhas)\b", re.I)
WRITE_TOOLS = {"create_insight", "upsert_dashboard", "create_notebook", "execute_sql", "upsert_alert", "create_feature_flag",
               "create_experiment", "create_survey", "edit_current_insight", "edit_current_query"}
AGENT_MODES = {"product_analytics", "sql", "session_replay", "error_tracking", "plan", "execution", "survey", "research",
               "flags", "llm_analytics", "sandbox", "user_interview", "customer_analytics"}


def own_text(s: str) -> str:
    """The user's own words: the turn without attached page context, reminders and voice-mode blocks."""
    return CTX.sub(" ", s).strip()


def shift_text(s: str, days: int, now: dt.date) -> tuple[str, int, int]:
    """V2.shift_text with month-start ISO dates kept (masked before shifting, restored after)."""
    kept: list[str] = []

    def mask(m):
        quoted = m.start() > 0 and s[m.start() - 1] == "'" and s[m.end():m.end() + 1] == "'"
        if m.group(3) == "01" and quoted:
            kept.append(m.group(0))
            return f"\x00MS{len(kept) - 1}\x00"
        return m.group(0)

    masked = V2.ISO.sub(mask, s)
    out, n = V2.shift_text(masked, days, now)
    for i, v in enumerate(kept):
        out = out.replace(f"\x00MS{i}\x00", v)
    return out, n, len(kept)


def phrases(text: str) -> set[str]:
    w = [x.lower() for x in WORD.findall(text)]
    return {" ".join(w[i:i + 3]) for i in range(len(w) - 2) if not any(t in STOP or len(t) < 3 for t in w[i:i + 3])}


CORRECTION = re.compile(r"^\s*(no[,.!]|nope\b|not that\b|that'?s not\b|i meant\b|i mean\b|what i meant\b|wrong\b|"
                        r"me refiero\b|quise decir\b|não[,.!]|nao[,.!]|eu quis dizer\b|quis dizer\b|nein[,.!]|non[,.!])", re.I)


def fold(x: str) -> str:
    """Lowercase without accents ("Último" == "ultimo")."""
    return "".join(c for c in unicodedata.normalize("NFKD", x.lower()) if not unicodedata.combining(c))


def premise_flags(turns: list[str], answers: list[str]) -> list[dict]:
    """Per turn i>0: does it rely on what the production assistant said in turns < i?
    Evidence from the full turn (attached context included: a context built from the production answer is a real
    dependency): numbers, identifiers and names first seen in production answers. From the user's own words only:
    deixis ("that spike", "the third one"), acknowledgements, corrections ("No, I meant ..."), quotes (2+ words or
    6+ chars, accent/case-folded), numbers with units, and 3-word content phrases introduced by the assistant."""
    own = [own_text(t) for t in turns]
    full = V2.premise_flags(turns, answers)
    flags = [{"turn": 0, "depends_on_answer": False}]
    for i in range(1, len(turns)):
        fe = full[i].get("evidence") or {}
        ev = {k: fe[k] for k in ("number", "identifier", "name") if fe.get(k)}
        pu, pa = fold(" ".join(own[:i])), fold(" ".join(answers[:i]))
        if V2.DEIXIS.search(own[i]):
            ev["deixis"] = 1
        if ACK.match(own[i]) and len(own[i]) <= 40:
            ev["ack"] = 1
        if CORRECTION.match(own[i]):
            ev["correction"] = 1
        qs = {fold(m.group(1).strip()) for rx in (V2.QUOTED, QUOTE2) for m in rx.finditer(own[i])}
        qs = [q for q in qs if (len(q) >= 6 or " " in q) and q in pa and q not in pu]
        if qs:
            ev["quoted"] = len(qs)
        nu = [fold(m.group(0)) for m in NUM_UNIT.finditer(own[i])]
        nu = [x for x in nu if x in pa and x not in pu]
        if nu:
            ev["number_unit"] = len(nu)
        ph = [x for x in phrases(own[i]) if fold(x) in pa and fold(x) not in pu]
        if ph:
            ev["phrase"] = len(ph)
        flags.append({"turn": i, "depends_on_answer": bool(ev), "evidence": ev})
    return flags


def ref_tool_calls(rec: dict, upto_turn: int) -> int:
    """Production tool calls made while answering human turns 0..upto_turn-1."""
    return len(ref_calls(rec, upto_turn))


def is_docs_call(name: str, inp: dict) -> bool:
    q = inp.get("query") if isinstance(inp.get("query"), dict) else {}
    return name == "search" and (inp.get("kind") == "docs" or q.get("kind") == "docs")


def ref_calls(rec: dict, upto_turn: int) -> list[tuple[str, dict]]:
    turn, out = -1, []
    for m in rec["messages"]:
        c = m["content"]
        blocks = [{"type": "text", "text": c}] if isinstance(c, str) else (c or [])
        if m["role"] == "user" and not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks):
            if any(isinstance(b, dict) and b.get("type") == "text" and (b.get("text") or "").strip() for b in blocks):
                turn += 1
            continue
        if m["role"] == "assistant" and 0 <= turn < upto_turn:
            out += [(b.get("name"), b.get("input") or {}) for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
    return out


def _unused_ref_tool_calls(rec: dict, upto_turn: int) -> int:
    turn, n = -1, 0
    for m in rec["messages"]:
        c = m["content"]
        blocks = [{"type": "text", "text": c}] if isinstance(c, str) else (c or [])
        if m["role"] == "user" and not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks):
            if any(isinstance(b, dict) and b.get("type") == "text" and (b.get("text") or "").strip() for b in blocks):
                turn += 1
            continue
        if m["role"] == "assistant" and 0 <= turn < upto_turn:
            n += sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use")
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", default="test_v2,dev")
    ap.add_argument("--ids", default="", help="comma-separated conversation ids (default: every loaded twin member)")
    ap.add_argument("--out", default=f"/opt/posthog-env/runner/tasks/v3{PATHS.SFX}")
    a = ap.parse_args()
    only = set(a.ids.split(",")) if a.ids else None
    latest = {}
    for r in V2.rows(V2.TEAMS_V2) if os.path.exists(V2.TEAMS_V2) else []:
        if r.get("removed"):
            latest.pop(r.get("twin_id"), None)
        else:
            latest[r["twin_id"]] = r
    by_cid = {cid: r for r in latest.values() for cid in r.get("members") or []}
    stats: Counter = Counter()
    by_split: dict[str, list] = {}
    for split in a.splits.split(","):
        for rec in V2.rows(V2.TRACES[split]):
            cid = rec["id"]
            if only is not None and cid not in only:
                continue
            team = by_cid.get(cid)
            if team is None:
                stats[f"{split}_no_team"] += 1
                continue
            spec = json.load(open(os.path.join(V2.SPECS, f"{cid}.json")))
            tturns = [t for t in sorted(spec.get("tasks") or [], key=lambda t: t.get("turn", 0)) if (t.get("text") or "").strip()]
            if not tturns:
                stats[f"{split}_no_turns"] += 1
                continue
            shift = int(team.get("shift_days") or 0)
            twin_now = dt.datetime.fromisoformat(str(team["twin_now_utc"]).replace("Z", "+00:00")).date()
            raw = [t["text"] for t in tturns]
            dups = {i for i in range(1, len(raw)) if own_text(raw[i]) and own_text(raw[i]) == own_text(raw[i - 1])}
            texts, n_dates, n_kept, n_urls = [], 0, 0, 0
            for s0 in raw:
                s, k, kept = shift_text(s0, shift, twin_now)
                n_dates += k
                n_kept += kept
                s2 = V2.PROJ.sub(f"/project/{team['project_id']}/", s)
                n_urls += s2 != s
                texts.append(s2)
            answers = V2.answers_by_turn(rec)
            answers += [""] * (len(tturns) - len(answers))
            flags = premise_flags(raw, answers)
            # a follow-up whose attached context changed after the production agent created/edited something carries
            # production's output (saved insight, edited query, result table): it depends on that answer
            prev_ctx = None
            for i, s0 in enumerate(raw):
                ctx = "".join(m.group(0) for m in CTX.finditer(s0) if m.group(1) == "attached_context")
                if i > 0 and ctx and ctx != prev_ctx:
                    made = [n for n, _ in ref_calls(rec, i)[len(ref_calls(rec, i - 1)):] if n in WRITE_TOOLS]
                    if made and not flags[i]["depends_on_answer"]:
                        flags[i]["depends_on_answer"] = True
                        flags[i].setdefault("evidence", {})["context_from_answer"] = len(made)
                prev_ctx = ctx
            first_dep = next((f["turn"] for f in flags if f["depends_on_answer"]), None)
            end = first_dep if first_dep else len(texts)
            cap = next((i for i, s in enumerate(texts) if CAPTURE.search(s)), None)
            quality: dict = {}
            exclude = None
            if cap is not None:
                quality["capture_placeholder_turn"] = cap
                end = min(end, cap)
                if cap == 0:
                    exclude = "capture placeholder in first turn"
            start = 0
            if end > 1 and GREETING.match(own_text(texts[0])):
                start = 1
                quality["greeting_dropped"] = True
            turns = [t for i, t in enumerate(texts[start:end], start) if i not in dups]
            if any(start <= i < end for i in dups):
                quality["duplicate_turns_collapsed"] = sum(1 for i in dups if start <= i < end)
            if not turns and exclude is None:
                exclude = "no turns left"
            joined = "\n".join(own_text(t) for t in turns)
            if CONTINUATION.search(joined):
                quality["continuation_summary"] = True
            rc = ref_calls(rec, end)
            ntc = len(rc)
            quality["reference_tool_calls"] = ntc
            if rc and all(is_docs_call(n, x) or n == "switch_mode" for n, x in rc) and any(is_docs_call(n, x) for n, x in rc):
                quality["docs_only"] = True
                if exclude is None:
                    exclude = "docs-only reference (no project data used)"
            if ntc == 0:
                quality["reference_no_tools"] = True
                if exclude is None:
                    exclude = "reference made no tool calls (docs/advice-only)"
            if end >= 1 and not (answers[end - 1] or "").strip():
                quality["reference_no_final_answer"] = True
            span = ((spec.get("project") or {}).get("timezone") or {}).get("current_time_utc") or []
            if RELDAY.search(joined) and len(span) == 2:
                try:
                    t0, t1 = (dt.datetime.fromisoformat(str(x).replace("Z", "+00:00")) for x in span)
                    if (t1 - t0).total_seconds() > 6 * 3600:
                        quality["clock_mismatch"] = round((t1 - t0).total_seconds() / 3600, 1)
                except ValueError:
                    pass
            if len(joined) > 6000 and len(POSTHOG_WORDS.findall(joined)) < 5:
                quality["off_topic_code_dump"] = True
            qf = os.path.join(V2.QFACTS, f"{cid}.json")
            corrupted = sorted({c["turn"] for c in json.load(open(qf))["calls"] if c.get("corrupted")}) if os.path.exists(qf) else []
            tz = (spec.get("project") or {}).get("timezone") or {}
            out_split = V2.SPLIT_MAP.get(split, split)
            task = {
                "task_id": cid, "source": "twin_v3", "split": out_split, "team_id": int(team["team_id"]),
                "project_id": int(team["project_id"]), "twin_id": team["twin_id"], "conversation_id": cid,
                "turns": turns, "turns_full": texts, "turn_offset": start, "max_turns": len(turns),
                "followups": flags, "first_answer_dependent_turn": first_dep,
                "agent_mode": spec.get("agent_mode") if spec.get("agent_mode") in AGENT_MODES else None,
                "spec_agent_mode": spec.get("agent_mode"),
                "env_defaults": {"POSTHOG_LOCAL_DOCS": "1"},
                "reference_tools": [t.get("tools") for t in tturns],
                "corrupted_sql_turns": corrupted,
                "shifted_dates_in_text": n_dates, "kept_month_start_dates": n_kept, "rewritten_project_urls": n_urls,
                "twin_current_time_utc": tz.get("current_time_utc"), "twin_now_utc": team.get("twin_now_utc"),
                "shift_days": shift, "loaded_now_utc": team.get("loaded_now_utc"), "twin_timezone": tz.get("abbr"),
                "quality": quality, "exclude": exclude, "builder": "build_tasks_v3",
            }
            by_split.setdefault(out_split, []).append(task)
            stats[f"{out_split}_tasks"] += 1
            stats[f"{out_split}_excluded"] += exclude is not None
            for k in quality:
                if k != "reference_tool_calls":
                    stats[f"{out_split}_q_{k}"] += 1
    os.makedirs(a.out, exist_ok=True)
    for split, tasks in by_split.items():
        tasks.sort(key=lambda t: hashlib.sha256(f"phai-runner-v1:{t['task_id']}".encode()).hexdigest())
        p = os.path.join(a.out, f"{split}.jsonl")
        with open(p + ".tmp", "w") as f:
            for t in tasks:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        os.replace(p + ".tmp", p)
    print(json.dumps(dict(sorted(stats.items()))))


if __name__ == "__main__":
    main()
