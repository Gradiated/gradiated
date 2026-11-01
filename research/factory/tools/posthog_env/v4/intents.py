#!/usr/bin/env python3
"""Production task map: classify every trace's request into a task family (runs on fbf8; labels only, no text out).

For each conversation (train, dev, test_v2): the first user request (clipped) and the tool names production used go to
an LLM classifier; the output is labels only: family, needs_data, multi_step, difficulty 1-5, skills. This is the
distribution the v4 synthesized task set follows (reweighted toward analysis-heavy families).

    python3 intents.py --out /opt/posthog-sft/env-research/intent/intents.jsonl [--workers 16] [--limit N]
"""

from __future__ import annotations

import argparse
import collections as C
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "/opt/posthog-env")
import llm_proxy  # noqa: E402

TRACES = "/opt/posthog-sft/env-research/twins_reanon/traces"
FAMILIES = {
    "metric_lookup": "a single number, count or simple trend",
    "trend_breakdown": "compare/break down a metric over time or by segment",
    "funnel_conversion": "conversion through steps, drop-off",
    "retention_engagement": "retention, stickiness, cohorts, active users",
    "anomaly_investigation": "why did a metric change / diagnose a spike or drop",
    "attribution_marketing": "traffic sources, UTMs, campaigns, referrers",
    "entity_lookup": "what did a specific user/account/org do",
    "sql_help": "write, fix or explain a HogQL/SQL query",
    "build_insight_dashboard": "create or edit insights/dashboards/notebooks",
    "session_replay": "find or analyse session recordings",
    "flags_experiments": "create/analyse feature flags or experiments",
    "surveys": "create/analyse surveys",
    "errors_logs": "error tracking, exceptions, logs",
    "llm_analytics": "LLM/AI generation analytics",
    "warehouse": "data warehouse tables, joins, sources",
    "product_howto": "how PostHog works / setup / configuration, no project data needed",
    "tracking_quality": "instrumentation problems, missing or wrong events",
    "other": "anything else",
}
PROMPT = """Classify this request to PostHog AI (an analytics agent). Families:
{families}

User request (clipped): {text}
Tools production used (names, in order): {tools}

Reply with ONLY JSON: {{"family": "<one family key>", "secondary": "<family key or null>", "needs_data": true|false,
"multi_step": true|false, "difficulty": <1-5, 1 = single lookup or docs answer, 5 = multi-step investigation with
judgment>, "skills": ["sql"|"taxonomy"|"insight"|"funnel"|"retention"|"breakdown"|"objects"|"replay"|"docs"|"warehouse"|"flags"|"experiments"|"surveys"|"errors"]}}"""


CTX = re.compile(r"<(system_reminder|attached_context|voice_mode)>.*?</\1>", re.S)  # as build_tasks_v3.own_text


def first_request(rec: dict) -> tuple[str, list[str]]:
    """The user's own words of the first user message with any (attached context, reminders stripped), and the tool
    names production used."""
    text, tools = "", []
    for m in rec.get("messages") or []:
        blocks = [b for b in m.get("content") or [] if isinstance(b, dict)]
        if m.get("role") == "user" and not text:
            own = CTX.sub(" ", " ".join(b.get("text") or "" for b in blocks if b.get("type") == "text")).strip()
            if own:
                text = own
        tools += [str(b.get("name")) for b in blocks if b.get("type") == "tool_use"]
    return text[:1500], tools[:40]


def classify(rec: dict) -> dict:
    text, tools = first_request(rec)
    fam = "\n".join(f"- {k}: {v}" for k, v in FAMILIES.items())
    out = {"id": rec["id"], "n_tools": len(tools)}
    for _ in range(3):
        try:
            t, _u = llm_proxy.judge_complete(PROMPT.format(families=fam, text=text, tools=", ".join(tools) or "(none)"),
                                             "gpt-6.1-terra", None, attempts=4, preamble=False)
            d = json.loads(t[t.find("{"):t.rfind("}") + 1])
            if d.get("family") in FAMILIES:
                out.update({k: d.get(k) for k in ("family", "secondary", "needs_data", "multi_step", "difficulty", "skills")})
                return out
        except Exception as e:  # noqa: BLE001
            out["error"] = f"{type(e).__name__}: {str(e)[:100]}"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    done = {json.loads(x)["id"] for x in open(a.out)} if os.path.exists(a.out) else set()
    recs = []
    for split in ("train", "dev", "test_v2"):
        for line in open(f"{TRACES}/{split}.jsonl"):
            r = json.loads(line)
            if r["id"] not in done:
                r["_split"] = split
                recs.append(r)
            if a.limit and len(recs) >= a.limit:
                break
    with open(a.out, "a") as f, ThreadPoolExecutor(a.workers) as pool:
        futs = {pool.submit(classify, r): r for r in recs}
        for fut in as_completed(futs):  # completion order: one stuck call does not block the rest
            res = fut.result()
            res["split"] = futs[fut]["_split"]
            f.write(json.dumps(res) + "\n")
            f.flush()
    rows = [json.loads(x) for x in open(a.out)]
    print(json.dumps({"n": len(rows), "families": C.Counter(r.get("family") for r in rows).most_common()}))


if __name__ == "__main__":
    main()
