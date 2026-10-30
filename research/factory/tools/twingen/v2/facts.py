"""Extract production facts per conversation from the anonymized traces (twin v2).

The v1 specs keep taxonomy, a query summary per object and up to 120 anchor rows. v2 needs more of the trace:
every data-read call with its full query and result table, the saved objects the conversation read (insight query
JSON and short id, notebook markdown and short id, dashboards), object URLs in the user text, absolute dates, and
named entities in filters and result rows.

    python3 -I facts.py [--splits test_v2,dev] [--out DIR]

Writes DIR/<conversation_id>.json (default /opt/posthog-sft/env-research/twins/facts_v2) and DIR/_index.jsonl.
Stdlib only. Prints aggregate counts only. Everything stays on fbf8.
"""

from __future__ import annotations

import argparse
import collections as C
import json
import os
import re
import sys

sys.path.insert(0, "/opt/posthog-sft/env-research/twins")
import twinlib as T  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as PATHS  # noqa: E402

OUT = PATHS.FACTS
MAX_ROWS = 400

READ_TOOLS = {"execute_sql", "create_insight", "read_data", "list_data", "read_taxonomy", "search",
              "filter_session_recordings", "list_feature_flags", "search_error_tracking_issues"}
URL_RE = re.compile(r"(?:https?://[^\s/)\]]+)?/project/(\d+)/((?:insights|notebooks|dashboard|dashboards|feature_flags|"
                    r"experiments|surveys|cohorts|persons|person|replay|error_tracking|data-warehouse|sql)[^\s)\]\"'>]*)")
OBJ_IN_PATH = re.compile(r"^(insights|notebooks|dashboard|dashboards|feature_flags|experiments|surveys|cohorts)/([A-Za-z0-9_-]+)")
ISO_DATE = re.compile(r"\b(20\d\d-[01]\d-[0-3]\d)\b")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def text_of(c) -> str:
    if isinstance(c, list):
        return "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    return c if isinstance(c, str) else json.dumps(c)


def is_human(m) -> bool:
    if m["role"] != "user":
        return False
    c = m["content"]
    if isinstance(c, str):
        return True
    return not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c)


def first_table(s):
    blocks = T.parse_envelope(s)
    kind = blocks[0]["kind"] if blocks else None
    schema = None
    for b in blocks:
        if schema is None and b.get("schema") is not None:
            schema = b["schema"]
        if b.get("table"):
            return b["kind"], b["table"], schema if schema is not None else b.get("schema")
    return kind, None, schema


def header_fields(s: str, keys: tuple[str, ...]) -> dict:
    out = {}
    for line in s.split("\n")[:12]:
        for k in keys:
            if line.startswith(k + ":"):
                out.setdefault(k, line[len(k) + 1:].strip())
    return out


def parse_notebook(s: str) -> dict | None:
    lines = s.split("\n")
    if not lines or not lines[0].startswith("Notebook:"):
        return None
    h = header_fields(s, ("Notebook", "short_id", "created_at", "last_modified_at", "URL"))
    body_start = 0
    for i, line in enumerate(lines[:8]):
        if line.startswith("URL:"):
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:]).strip("\n")
    return {"title": h.get("Notebook"), "short_id": h.get("short_id"), "created_at": h.get("created_at"),
            "last_modified_at": h.get("last_modified_at"), "content_markdown": body}


def parse_insight(s: str) -> dict | None:
    h = header_fields(s, ("Name", "Insight ID", "Artifact ID", "Description", "Insight URL"))
    if "Name" not in h:
        return None
    kind, table, schema = first_table(s)
    out = {"name": h.get("Name"), "short_id": h.get("Insight ID"), "description": h.get("Description"),
           "saved": "Insight URL" in h, "query": schema, "result_kind": kind}
    if table:
        out["cols"], out["rows"] = table[0], table[1:MAX_ROWS + 1]
    return out


DASH_INS = re.compile(r"Insight ID: ([A-Za-z0-9_-]+)")


def parse_dashboard(s: str) -> dict | None:
    h = header_fields(s, ("Dashboard name", "Dashboard ID", "Dashboard URL", "Description"))
    if "Dashboard name" not in h:
        return None
    tiles = []
    # insight blocks inside the dashboard result start with "Name:"; keep name + short id + query schema
    chunks = re.split(r"\n(?=Name: )", s)
    for ch in chunks[1:]:
        ins = parse_insight(ch)
        if ins:
            tiles.append(ins)
    return {"name": h.get("Dashboard name"), "id": h.get("Dashboard ID"), "description": h.get("Description"),
            "tiles": tiles}


def extract(rec: dict) -> dict:
    cid = rec["id"]
    uses: dict = {}
    turn = -1
    k = 0
    calls: list[dict] = []
    objects: dict[str, dict] = {"insights": {}, "notebooks": {}, "dashboards": {}}
    created: dict[str, list] = C.defaultdict(list)
    user_texts: list[str] = []
    url_refs: list[dict] = []
    for m in rec["messages"]:
        c = m["content"]
        if is_human(m):
            turn += 1
            t = text_of(c)
            user_texts.append(t)
            for mm in URL_RE.finditer(t):
                path = mm.group(2)
                om = OBJ_IN_PATH.match(path)
                url_refs.append({"turn": turn, "project": mm.group(1), "path": path[:200],
                                 "kind": om.group(1) if om else path.split("/")[0], "id": om.group(2) if om else None})
        if not isinstance(c, list):
            continue
        for b in c:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                uses[b["id"]] = (b, turn)
                continue
            if b.get("type") != "tool_result":
                continue
            u, uturn = uses.get(b.get("tool_use_id"), (None, turn))
            if not u:
                continue
            name, inp = u["name"], u.get("input") or {}
            s = text_of(b.get("content"))
            err = bool(b.get("is_error")) or T.err_kind(s) is not None
            if name in ("upsert_dashboard", "create_notebook", "create_feature_flag", "create_experiment", "upsert_alert"):
                created[name].append({"turn": uturn, "is_error": err})
                continue
            if name not in READ_TOOLS:
                continue
            call = {"k": k, "turn": uturn, "tool": name, "input": inp, "is_error": err, "res_len": len(s)}
            k += 1
            if name in ("execute_sql", "create_insight"):
                kind, table, schema = first_table(s)
                call["result_kind"] = kind
                call["schema"] = schema
                if table:
                    call["cols"], call["rows"], call["n_rows"] = table[0], table[1:MAX_ROWS + 1], len(table) - 1
                if name == "execute_sql":
                    call["sql"] = inp.get("query")
                elif isinstance(schema, dict):
                    src = schema.get("source") if schema.get("kind") in ("InsightVizNode", "DataVisualizationNode", "DataTableNode") else schema
                    if isinstance(src, dict) and src.get("kind") == "HogQLQuery":
                        call["sql"] = src.get("query")
                if err:
                    call["error_head"] = s[:240]
            elif name == "read_data":
                q = inp.get("query") or {}
                kd = q.get("kind")
                call["kind"] = kd
                if not err and kd == "insight":
                    ins = parse_insight(s)
                    if ins:
                        sid = ins.get("short_id") or q.get("insight_id")
                        ins["requested_id"] = q.get("insight_id")
                        prev = objects["insights"].get(sid) or {}
                        objects["insights"][sid] = {**prev, **{kk: v for kk, v in ins.items() if v is not None}}
                        call["object"] = sid
                        if ins.get("rows") is not None:
                            call["cols"], call["rows"], call["result_kind"] = ins.get("cols"), ins.get("rows"), ins.get("result_kind")
                            src = ins.get("query")
                            if isinstance(src, dict):
                                call["schema"] = src
                                if src.get("kind") == "HogQLQuery":
                                    call["sql"] = src.get("query")
                elif not err and kd == "notebook":
                    nb = parse_notebook(s)
                    if nb and nb.get("short_id"):
                        prev = objects["notebooks"].get(nb["short_id"])
                        # keep the earliest read (later reads may include the agent's own edits)
                        if prev is None:
                            nb["first_read_turn"] = uturn
                            objects["notebooks"][nb["short_id"]] = nb
                        call["object"] = nb["short_id"]
                elif not err and kd == "dashboard":
                    d = parse_dashboard(s)
                    if d:
                        did = d.get("id") or str(q.get("dashboard_id"))
                        objects["dashboards"][did] = d
                        for ins in d["tiles"]:
                            sid = ins.get("short_id")
                            if sid and sid not in objects["insights"]:
                                objects["insights"][sid] = {kk: v for kk, v in ins.items() if kk not in ("rows", "cols")}
                        call["object"] = did
                elif kd in ("data_warehouse_table", "data_warehouse_schema") and not err:
                    try:
                        tb = T.parse_dw_table(s) if kd == "data_warehouse_table" else T.parse_dw_schema(s)
                        call["dw"] = {tn: v.get("fields") for tn, v in tb.items()}
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    call["head"] = s[:200]
            elif name == "read_taxonomy":
                call["head"] = s[:200]
            else:
                call["head"] = s[:300]
            calls.append(call)
    # entities: emails anywhere in user text and result rows; literal filters in SQL
    emails = C.Counter()
    for t in user_texts:
        emails.update(EMAIL.findall(t))
    for call in calls:
        for row in call.get("rows") or []:
            for x in row:
                for e in EMAIL.findall(str(x)):
                    emails[e] += 1
        if call.get("sql"):
            for e in EMAIL.findall(call["sql"]):
                emails[e] += 1
    dates = sorted({d for call in calls for d in ISO_DATE.findall(call.get("sql") or json.dumps(call.get("schema") or ""))})
    return {"conversation_id": cid, "agent_mode": rec.get("agent_mode"), "n_turns": turn + 1, "calls": calls,
            "objects": objects, "created_by_agent": dict(created), "url_refs": url_refs,
            "emails": dict(emails.most_common(200)), "query_dates": dates,
            "user_dates": sorted({d for t in user_texts for d in ISO_DATE.findall(t)})}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", default="test_v2,dev")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    stats = C.Counter()
    with open(os.path.join(a.out, "_index.jsonl"), "w") as idx:
        for split in a.splits.split(","):
            files = PATHS.trace_files()
            if split not in files:
                continue
            with open(files[split], encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    f = extract(rec)
                    f["split"] = split
                    with open(os.path.join(a.out, f"{rec['id']}.json"), "w") as out:
                        json.dump(f, out)
                    row = {"conversation_id": rec["id"], "split": split, "calls": len(f["calls"]),
                           "sql": sum(1 for c in f["calls"] if c.get("sql")),
                           "insights": len(f["objects"]["insights"]), "notebooks": len(f["objects"]["notebooks"]),
                           "dashboards": len(f["objects"]["dashboards"]), "url_refs": len(f["url_refs"]),
                           "emails": len(f["emails"])}
                    idx.write(json.dumps(row) + "\n")
                    stats[f"{split}_convs"] += 1
                    for kk in ("calls", "sql", "insights", "notebooks", "dashboards", "url_refs", "emails"):
                        stats[f"{split}_{kk}"] += row[kk]
    print(json.dumps(dict(stats)))


if __name__ == "__main__":
    main()
