"""Read-only replay of production data reads (test_v2) against each conversation's twin team. Output stays on fbf8."""
import sys as _sys
_sys.path.insert(0, "/opt/posthog-sft/env-research/twingen/v2")
import paths as PATHS  # noqa: E402
FID = PATHS.REPLAY_DIR

import sys, os, json, re, datetime as dt, traceback, time, collections as C
sys.path.insert(0, "/opt/posthog-env"); sys.path.insert(0, "/opt/posthog-sft/env-research/twins")
import boot; boot.init()
fake = boot.activate_personhog()
import twinlib as T
from posthog.models import Team
from posthog.hogql.query import execute_hogql_query
from posthog.hogql.constants import HogQLGlobalSettings
from posthog.api.services.query import process_query_dict
from ee.hogai.chat_agent.query_planner.toolkit import TaxonomyAgentToolkit
from ee.hogai.tools.read_taxonomy.core import (ReadEvents, ReadEventProperties, ReadEntityProperties,
    ReadEventSamplePropertyValues, ReadEntitySamplePropertyValues, execute_taxonomy_query)
from posthog.models import EventDefinition, PropertyDefinition
from products.dashboards.backend.models.dashboard import Dashboard
from products.product_analytics.backend.models.insight import Insight
from products.feature_flags.backend.models.feature_flag import FeatureFlag
from products.notebooks.backend.models import Notebook
from products.warehouse_sources.backend.models.table import DataWarehouseTable
sys.path.insert(0, "/opt/posthog-env/loader"); import personhog_seed

DATE = re.compile(r"(?<=['\"])(\d{4}-\d\d-\d\d)(?=[ T'\"])")
def shift(s, days):
    if not days: return s
    return DATE.sub(lambda m: (dt.date.fromisoformat(m.group(1)) + dt.timedelta(days=days)).isoformat(), s)

def errclass(msg):
    m = msg or ""
    for k, p in [("unresolved_field", r"Unable to resolve field|Unable to resolve|Field .* not found|Unknown field|has no field"),
                 ("unknown_table", r"Unknown table|Table .* (does not exist|not found)|Unknown database|table .* not found"),
                 ("unknown_function", r"Unsupported function|Unknown function|not supported"),
                 ("syntax", r"Syntax error|mismatched input|no viable alternative|extraneous input|missing"),
                 ("type", r"Illegal type|Cannot convert|NO_COMMON_TYPE|type mismatch|Cannot parse|CANNOT_PARSE"),
                 ("timeout", r"timeout|Timeout|TOO_SLOW|exceeded")]:
        if re.search(p, m): return k
    return "other"

def run_sql(q, team):
    t0 = time.time()
    try:
        r = execute_hogql_query(query=q, team=team, settings=HogQLGlobalSettings(max_execution_time=25))
        return {"ok": True, "n": len(r.results or []), "cols": r.columns, "rows": [[str(x)[:80] for x in row] for row in (r.results or [])[:30]], "t": round(time.time()-t0,2)}
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        return {"ok": False, "err": msg[:300], "cls": errclass(msg), "t": round(time.time()-t0,2)}

def run_insight(src, team):
    try:
        r = process_query_dict(team, src)
        res = r.get("results") if isinstance(r, dict) else getattr(r, "results", None)
        if res is None and hasattr(r, "model_dump"): res = r.model_dump().get("results")
        n = len(res or []); total = None
        if isinstance(res, list) and res and isinstance(res[0], dict):
            def f(v):
                try: return float(v or 0)
                except Exception: return 0.0
            a = sum(f(x.get("count")) for x in res); b = sum(f(x.get("aggregated_value")) for x in res)
            c = sum(sum(f(v) for v in (x.get("data") or [])) for x in res)
            total = max(a, b, c)
        elif isinstance(res, list) and res and isinstance(res[0], list):
            try: total = sum(float(s.get("count") or 0) for s in res[0] if isinstance(s, dict))
            except Exception: total = None
        series = None
        if isinstance(res, list) and res and isinstance(res[0], dict) and isinstance(res[0].get("data"), list):
            series = [[float(v or 0) for v in (x.get("data") or [])] for x in res[:5]]
        return {"ok": True, "n": n, "total": total, "series": series}
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        return {"ok": False, "err": msg[:300], "cls": errclass(msg)}

teams = {}
def get_team(tid):
    if tid not in teams:
        team = Team.objects.get(id=tid)
        try: personhog_seed.seed_team(fake, tid)
        except Exception: pass
        user = team.organization.members.order_by("id").first()
        evs = set(EventDefinition.objects.filter(team_id=tid).values_list("name", flat=True))
        props = C.defaultdict(set)
        for n, ty in PropertyDefinition.objects.filter(team_id=tid).values_list("name", "type"): props[ty].add(n)
        dw = {}
        for t in DataWarehouseTable.objects.filter(team_id=tid, deleted=False):
            dw[t.name] = list((t.columns or {}).keys())
        teams[tid] = (team, user, evs, props, dw)
    return teams[tid]

out = open(FID + "/replay_ins.jsonl", "w")
for line in open(FID + "/calls.jsonl"):
    r = json.loads(line)
    if r["team_id"] is None or r["tool"] != "create_insight": continue
    team, user, evs, props, dw = get_team(r["team_id"])
    o = {k: r.get(k) for k in ("cid", "team_id", "turn", "k", "tool", "err_kind", "n_rows", "shift_days")}
    inp = r.get("input") or {}
    try:
        if r["tool"] == "execute_sql":
            q = inp.get("query") or ""
            o["raw"] = run_sql(q, team)
            sq = shift(q, r["shift_days"])
            o["has_abs_date"] = sq != q
            o["shifted"] = run_sql(sq, team) if sq != q else o["raw"]
            p = T.parse_sql(q)
            o["ents"] = {"events": sorted(p["events"]), "events_missing": sorted(e for e in p["events"] if e not in evs),
                         "props": sorted({(s, n) for s, n, _ in p["props"]}),
                         "props_missing": sorted({(s, n) for s, n, _ in p["props"] if n not in (props[1] if s == "event" else props[2] if s == "person" else props[1] | props[2] | props[3] | props[4])}),
                         "dw": sorted(p["tables"]["dw"]),
                         "dw_missing": sorted(t for t in p["tables"]["dw"] if t not in dw and t.replace(".", "_") not in dw and not any(k.endswith(t.split(".")[-1]) for k in dw))}
            o["prod_rows"] = r.get("rows"); o["prod_cols"] = r.get("cols")
        elif r["tool"] == "create_insight":
            sch = r.get("schema")
            if isinstance(sch, dict) and sch.get("kind"):
                src = sch.get("source") if sch.get("kind") in ("InsightVizNode", "DataVisualizationNode", "DataTableNode") else sch
                if isinstance(src, dict):
                    o["qkind"] = src.get("kind")
                    o["raw"] = run_insight(src, team)
                    s2 = json.loads(shift(json.dumps(src), r["shift_days"]))
                    o["has_abs_date"] = s2 != src
                    o["shifted"] = run_insight(s2, team) if s2 != src else o["raw"]
                    acc = T.new_acc(); T.walk_query(src, acc)
                    o["acc"] = {k: sorted(map(str, v))[:50] if isinstance(v, (set, list)) else str(v)[:200] for k, v in acc.items()}
            o["prod_rows"] = r.get("rows"); o["prod_cols"] = r.get("cols")
        elif r["tool"] == "read_taxonomy":
            q = inp.get("query") or {}
            kd = q.get("kind")
            M = {"events": ReadEvents, "event_properties": ReadEventProperties, "entity_properties": ReadEntityProperties,
                 "event_property_values": ReadEventSamplePropertyValues, "entity_property_values": ReadEntitySamplePropertyValues}.get(kd)
            o["kind"] = kd; o["q"] = q
            if M:
                tk = TaxonomyAgentToolkit(team, user)
                txt = execute_taxonomy_query(M(**q), tk, team, user)
                if kd == "events": names = [x[0] for x in T.parse_events_list(txt)]
                elif kd in ("event_properties", "entity_properties"): names = [x[0] for x in T.parse_properties(txt)]
                else: names = T.parse_values(txt)[0]
                o["prod"] = r.get("names") or []; o["twin"] = names[:500]; o["twin_head"] = txt[:200]
        elif r["tool"] == "read_data":
            q = inp.get("query") or {}
            kd = q.get("kind"); o["kind"] = kd; o["q"] = q
            if kd == "insight": o["exists"] = Insight.objects.filter(team=team, short_id=q.get("insight_id")).exists()
            elif kd == "notebook": o["exists"] = Notebook.objects.filter(team=team, short_id=q.get("notebook_id")).exists()
            elif kd == "dashboard": o["exists"] = Dashboard.objects.filter(team=team, id=int(q.get("dashboard_id"))).exists()
            elif kd == "feature_flag": o["exists"] = FeatureFlag.objects.filter(team=team, key=q.get("key")).exists() if q.get("key") else FeatureFlag.objects.filter(team=team, id=q.get("id")).exists()
            elif kd == "error_tracking_issue":
                from products.error_tracking.backend.models import ErrorTrackingIssue
                o["exists"] = ErrorTrackingIssue.objects.filter(team=team, id=q.get("issue_id")).exists()
            elif kd in ("data_warehouse_table", "data_warehouse_schema"):
                pdw = r.get("dw") or {}
                o["dw_cmp"] = []
                for tn, fields in pdw.items():
                    flat = tn.replace(".", "_")
                    tw = dw.get(tn) or dw.get(flat) or next((v for k, v in dw.items() if k.endswith(tn.split(".")[-1])), None)
                    o["dw_cmp"].append({"t": tn, "in_twin": tw is not None, "prod_f": len(fields),
                                        "f_present": sum(1 for f in fields if tw and f in tw), "twin_f": len(tw or [])})
    except Exception as e:
        o["exc"] = f"{type(e).__name__}: {str(e)[:200]}"
    out.write(json.dumps(o, default=str) + "\n"); out.flush()
print("done", len(teams))
os._exit(0)
