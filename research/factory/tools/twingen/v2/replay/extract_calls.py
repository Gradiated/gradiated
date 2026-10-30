"""Extract production data-read tool calls (test_v2) with result summaries. Output stays on fbf8."""
import sys as _sys
_sys.path.insert(0, "/opt/posthog-sft/env-research/twingen/v2")
import paths as PATHS  # noqa: E402
FID = PATHS.REPLAY_DIR

import json, re, sys, collections as C
sys.path.insert(0, "/opt/posthog-sft/env-research/twins")
import twinlib as T

tasks = {}
for l in open(PATHS.TASKS_DIR + "/test.jsonl"):
    t = json.loads(l); tasks[t["conversation_id"]] = t

def text_of(cc):
    if isinstance(cc, list):
        return "\n".join(x.get("text", "") for x in cc if isinstance(x, dict))
    return cc if isinstance(cc, str) else json.dumps(cc)

def table_of(s):
    blocks = T.parse_envelope(s)
    for b in blocks:
        if b.get("table"):
            return b["kind"], b["table"], b.get("schema")
    sch = blocks[0].get("schema") if blocks else None
    return (blocks[0]["kind"] if blocks else None), None, sch

out = open(FID + "/calls.jsonl", "w")
n = C.Counter()
for l in open(PATHS.trace_files()["test_v2"]):
    r = json.loads(l)
    cid = r["id"]; t = tasks.get(cid)
    uses = {}; turn = -1; k = 0
    for m in r["messages"]:
        c = m["content"]
        if m["role"] == "user" and (isinstance(c, str) or any(isinstance(b, dict) and b.get("type") == "text" for b in c)):
            if not (isinstance(c, list) and any(b.get("type") == "tool_result" for b in c if isinstance(b, dict))):
                turn += 1
        if not isinstance(c, list):
            continue
        for b in c:
            if not isinstance(b, dict): continue
            if b.get("type") == "tool_use":
                uses[b["id"]] = b
            elif b.get("type") == "tool_result":
                u = uses.get(b.get("tool_use_id"))
                if not u: continue
                name = u["name"]
                if name not in ("execute_sql", "create_insight", "read_taxonomy", "read_data", "list_data", "search", "filter_session_recordings", "list_feature_flags", "search_error_tracking_issues"):
                    continue
                s = text_of(b.get("content"))
                rec = {"cid": cid, "team_id": t and t["team_id"], "shift_days": t and t.get("shift_days"), "turn": turn, "k": k,
                       "tool": name, "input": u.get("input"), "is_error": bool(b.get("is_error")), "err_kind": T.err_kind(s),
                       "res_len": len(s)}
                k += 1
                if name in ("execute_sql", "create_insight"):
                    kind, tab, sch = table_of(s)
                    rec["res_kind"] = kind
                    rec["schema"] = sch
                    if tab:
                        rec["cols"] = tab[0]; rec["n_rows"] = len(tab) - 1; rec["rows"] = tab[1:21]
                    else:
                        rec["n_rows"] = None
                    rec["head"] = s[:300]
                elif name == "read_taxonomy":
                    q = (u.get("input") or {}).get("query") or {}
                    kd = q.get("kind")
                    if kd == "events":
                        rec["names"] = [x[0] for x in T.parse_events_list(s)]
                    elif kd in ("event_properties", "entity_properties"):
                        rec["names"] = [x[0] for x in T.parse_properties(s)]
                    else:
                        v, more, st = T.parse_values(s)
                        rec["names"] = v[:50]; rec["values_status"] = st
                    rec["head"] = s[:300]
                else:
                    rec["head"] = s[:400]
                    if name == "read_data" and ((u.get("input") or {}).get("query") or {}).get("kind") in ("data_warehouse_table", "data_warehouse_schema"):
                        tb = T.parse_dw_table(s) if ((u.get("input") or {}).get("query") or {}).get("kind") == "data_warehouse_table" else T.parse_dw_schema(s)
                        rec["dw"] = {k: [f["name"] for f in v["fields"]] for k, v in tb.items()}
                out.write(json.dumps(rec) + "\n"); n[name] += 1
print(n)
