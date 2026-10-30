"""Query facts for twin v2: parse every production SQL in facts_v2 with PostHog's HogQL parser.

For each SQL call (execute_sql, HogQL insights, executed saved insights) this resolves table aliases and attributes
qualified and unqualified columns to tables, collects literal filters, type hints from function use and comparisons,
join key pairs, and maps result columns back to source columns. Simple query shapes are inverted into seed rows:

- shape A (projection): no GROUP BY and no aggregates over one table -> the result rows are rows of that table;
- shape B (group count): GROUP BY bare columns of one table with count()/sum(col)/avg(col) -> per-group counts.

Output per conversation: qfacts_v2/<conversation_id>.json with
`calls` (per SQL call analysis), `dw` (table -> column -> {types, literals, values, refs}), `joins` (column pairs),
`dw_seeds` (table -> rows), `event_seeds` (rows over events), `entity_literals` (person/group identifiers in filters),
`series` (time series per event) and `volume` (event counts over windows).

Run with the PostHog venv (the parser is PostHog's):
    cd /opt/posthog-env/posthog && .venv/bin/python /opt/posthog-sft/env-research/twingen/v2/qfacts.py [--split test_v2]
Prints aggregates only.
"""

from __future__ import annotations

import argparse
import collections as C
import dataclasses
import datetime as dt
import glob
import json
import os
import re
import sys

sys.path.insert(0, "/opt/posthog-sft/env-research/twins")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import twinlib as T  # noqa: E402
import paths as PATHS  # noqa: E402

FACTS = PATHS.FACTS
OUT = PATHS.QFACTS
SPECS = PATHS.SPECS

try:
    import anoncheck  # anonymizer-corruption detector (same directory)

    _vocab = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anoncheck_vocab.json")
    if os.path.exists(_vocab):
        anoncheck.load_vocab(_vocab)
except Exception:  # noqa: BLE001
    anoncheck = None

CORE_TABLES = {"events", "persons", "sessions", "groups", "person_distinct_ids", "person_distinct_id_overrides",
               "session_replay_events", "cohort_people", "raw_sessions", "static_cohort_people", "log_entries",
               "numbers", "system", "error_tracking_issues", "app_metrics", "query_log", "logs", "document_embeddings",
               "heatmaps", "exchange_rate", "web_stats_daily", "web_bounces_daily", "preaggregation_results",
               "survey_responses", "experiment_exposures"}
DATE_FUNCS = {"todate", "tostartofmonth", "tostartofweek", "tostartofday", "tostartofhour", "tostartofquarter",
              "tostartofyear", "datediff", "date_diff", "date_trunc", "datetrunc", "todatetime", "toyyyymm", "toyyyymmdd",
              "formatdatetime", "parsedatetimebesteffort", "parsedatetime64besteffort", "todatetime64", "tounixtimestamp",
              "toyear", "tomonth", "todayofweek", "tostartofinterval", "dateadd", "datesub", "toiso8601", "totimezone",
              "tostartofisoweek", "toweek", "toisoweek", "todayofmonth", "tohour", "date_add", "date_sub", "age"}
NUM_FUNCS = {"sum", "avg", "round", "tofloat", "tofloat64", "toint", "toint64", "toint32", "touint64", "quantile",
             "median", "sumif", "avgif", "floor", "ceil", "abs", "todecimal", "tofloatornull", "tointornull",
             "tofloat64ornull", "toint64ornull", "stddevpop", "varpop", "quantiles", "exp", "log", "sqrt"}
STR_FUNCS = {"lower", "upper", "like", "ilike", "splitbychar", "substring", "concat", "trim", "replaceall", "position",
             "startswith", "endswith", "match", "extract", "domain", "lowerutf8", "length", "leftpad", "tostring"}
JSON_FUNCS = {"jsonextractstring", "jsonextractint", "jsonextractfloat", "jsonextractbool", "jsonextractraw",
              "jsonextract", "jsonhas", "jsonextractarrayraw", "jsonextractkeys", "jsonlength", "visitparamextractstring"}
AGG = {"count", "countif", "uniq", "uniqexact", "uniqif", "sum", "sumif", "avg", "avgif", "min", "max", "any",
       "argmax", "argmin", "groupuniqarray", "grouparray", "median", "quantile", "countdistinct", "uniqcombined",
       "anylast", "uniqexactif", "minif", "maxif", "quantileif", "sumdistinct"}
ISO = re.compile(r"^\d{4}-\d\d-\d\d(?:[ T]\d\d:\d\d(?::\d\d(?:\.\d+)?)?)?(?:Z|[+-]\d\d:?\d\d)?$")
INTERVAL = re.compile(r"INTERVAL\s+'?(\d+)'?\s*(DAY|WEEK|MONTH|HOUR|YEAR|QUARTER)S?\b", re.I)
INTERVAL_FN = re.compile(r"toInterval(Day|Week|Month|Hour|Year)\s*\(\s*(\d+)\s*\)", re.I)
UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "hour": 1 / 24, "year": 365, "quarter": 91}

_ast = None


def ast():
    global _ast
    if _ast is None:
        from posthog.hogql import ast as a

        _ast = a
    return _ast


def children(node):
    """Direct AST children (lists and dicts flattened), skipping resolved types."""
    if not dataclasses.is_dataclass(node):
        return
    for f in dataclasses.fields(node):
        if f.name in ("type", "start", "end"):
            continue
        v = getattr(node, f.name, None)
        if v is None:
            continue
        if isinstance(v, list):
            for x in v:
                if dataclasses.is_dataclass(x):
                    yield x
        elif isinstance(v, dict):
            for x in v.values():
                if dataclasses.is_dataclass(x):
                    yield x
        elif dataclasses.is_dataclass(v):
            yield v


def is_query(n) -> bool:
    a = ast()
    return isinstance(n, (a.SelectQuery, a.SelectSetQuery))


def walk_scope(node):
    """Yield nodes of one query scope; nested queries are yielded but not descended into."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        if is_query(n):
            continue
        stack.extend(children(n))


def const_values(n) -> list | None:
    a = ast()
    if isinstance(n, a.Constant):
        return [n.value]
    if isinstance(n, (a.Tuple, a.Array)):
        out = []
        for x in n.exprs:
            if isinstance(x, a.Constant):
                out.append(x.value)
        return out
    if isinstance(n, a.Call) and n.name.lower() in ("todate", "todatetime", "tuple", "array") and n.args:
        vals = []
        for x in n.args:
            if isinstance(x, a.Constant):
                vals.append(x.value)
        return vals or None
    return None


class Scope:
    def __init__(self, q, ctes: dict, known: dict[str, set]):
        a = ast()
        self.q = q
        self.tables: dict[str, tuple[str, str | None]] = {}  # alias -> (kind, name)
        self.order: list[str] = []  # real table names in FROM order
        self.join_pairs: list = []
        self.subqueries: list = []
        self.known = known
        je = q.select_from
        while je is not None:
            t = je.table
            if isinstance(t, a.Field):
                name = ".".join(str(c) for c in t.chain)
                if name in ctes:
                    self.tables[je.alias or name] = ("cte", name)
                else:
                    self.tables[je.alias or name] = ("table", name)
                    if je.alias:
                        self.tables.setdefault(name, ("table", name))
                    self.order.append(name)
            elif t is not None and is_query(t):
                self.subqueries.append(t)
                if je.alias:
                    self.tables[je.alias] = ("sub", None)
            je = je.next_join
        self.select_aliases = {x.alias for x in q.select if isinstance(x, a.Alias)}

    def real_tables(self) -> list[str]:
        return [t for t in self.order]

    def resolve(self, chain: list) -> tuple[str, str, list] | None:
        """Field chain -> (table, column, rest) for real tables; None for CTE/subquery/select-alias refs."""
        chain = [str(c) for c in chain]
        if not chain:
            return None
        if chain[0] in self.tables and len(chain) > 1:
            kind, name = self.tables[chain[0]]
            if kind == "table":
                return name, chain[1], chain[2:]
            return None
        # dotted table names: stripe.charges.amount
        for name in self.order:
            parts = name.split(".")
            if len(chain) > len(parts) and chain[: len(parts)] == parts:
                return name, chain[len(parts)], chain[len(parts) + 1:]
        if chain[0] in self.select_aliases:
            return None
        reals = self.real_tables()
        has_derived = any(k != "table" for k, _ in self.tables.values())
        if len(reals) == 1 and not has_derived:
            return reals[0], chain[0], chain[1:]
        if reals:
            cands = [t for t in reals if chain[0] in self.known.get(t, set())]
            if len(cands) == 1:
                return cands[0], chain[0], chain[1:]
            if not has_derived and len(cands) == 0:
                # unqualified, unknown everywhere: events columns go to events, otherwise the first warehouse table
                if "events" in reals and chain[0] in ("event", "timestamp", "distinct_id", "person_id", "properties",
                                                        "person", "uuid", "$session_id", "elements_chain"):
                    return "events", chain[0], chain[1:]
                dw = [t for t in reals if T.classify_table(t) == "dw"]
                if dw:
                    return dw[0], chain[0], chain[1:] + ["?ambiguous"]
        return None


def type_hint_of_context(parent, field_node) -> str | None:
    a = ast()
    if isinstance(parent, a.Call):
        nm = parent.name.lower()
        if nm in DATE_FUNCS:
            return "datetime"
        if nm in NUM_FUNCS:
            return "numeric"
        if nm in JSON_FUNCS and parent.args and parent.args[0] is field_node:
            return "json"
        if nm in STR_FUNCS:
            return "string"
    if isinstance(parent, a.ArithmeticOperation):
        return "numeric"
    return None


def value_type(v) -> str | None:
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "numeric"
    if isinstance(v, str):
        if ISO.match(v.strip()):
            return "datetime"
        return "string"
    return None


def analyze_sql(sql: str, known: dict[str, set]) -> dict:
    from posthog.hogql.parser import parse_select

    a = ast()
    out = {"ok": False}
    try:
        root = parse_select(sql)
    except Exception as e:  # noqa: BLE001
        out["parse_error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return out
    out["ok"] = True
    refs = C.Counter()
    hints: dict = C.defaultdict(C.Counter)
    literals: dict = C.defaultdict(list)
    join_pairs = []
    tables_used = set()
    events_used = set()
    top = {"root": None}

    def visit_query(q, ctes, is_top):
        if isinstance(q, a.SelectSetQuery):
            visit_query(q.initial_select_query, ctes, is_top)
            for sn in q.subsequent_select_queries:
                visit_query(sn.select_query, ctes, False)
            return
        if not isinstance(q, a.SelectQuery):
            return
        ctes = dict(ctes)
        if q.ctes:
            for name, cte in q.ctes.items():
                ctes[name] = cte
                if is_query(cte.expr):
                    visit_query(cte.expr, ctes, False)
        sc = Scope(q, ctes, known)
        tables_used.update(sc.order)
        for sub in sc.subqueries:
            visit_query(sub, ctes, False)
        parents = {}
        roots = list(q.select) + [x for x in (q.where, q.prewhere, q.having) if x is not None]
        roots += list(q.group_by or []) + [o.expr for o in (q.order_by or [])]
        je = q.select_from
        while je is not None:
            if je.constraint is not None:
                roots.append(je.constraint.expr)
            je = je.next_join
        nested = []
        for r in roots:
            for n in walk_scope(r):
                if is_query(n) and n is not r:
                    nested.append(n)
                    continue
                for ch in children(n):
                    parents[id(ch)] = n
                if isinstance(n, a.Field):
                    res = sc.resolve(n.chain)
                    if res is None:
                        continue
                    t, col, rest = res
                    key = (t, col)
                    refs[key] += 1
                    p = parents.get(id(n))
                    h = type_hint_of_context(p, n)
                    if h:
                        hints[key][h] += 1
                if isinstance(n, a.CompareOperation):
                    for lhs, rhs in ((n.left, n.right), (n.right, n.left)):
                        f = lhs
                        while isinstance(f, a.Call) and f.args and f.name.lower() in (
                                "lower", "upper", "tostring", "todate", "todatetime", "trim", "lowerutf8", "toint", "tofloat"):
                            f = f.args[0]
                        if isinstance(f, a.Field):
                            res = sc.resolve(f.chain)
                            vals = const_values(rhs)
                            if res is not None and vals:
                                t, col, rest = res
                                path = ".".join([col] + [str(x) for x in rest if x != "?ambiguous"])
                                literals[(t, path)].append({"op": str(n.op), "values": [v if not isinstance(v, (dt.date, dt.datetime)) else str(v) for v in vals][:50]})
                                for v in vals:
                                    vt = value_type(v)
                                    if vt and not rest:
                                        hints[(t, col)][vt] += 1
                                if t == "events" and col == "event":
                                    events_used.update(str(v) for v in vals if isinstance(v, str))
                            elif res is not None and isinstance(rhs, a.Field):
                                r2 = sc.resolve(rhs.chain)
                                if r2 is not None and r2[0] != res[0]:
                                    join_pairs.append(sorted([[res[0], res[1]], [r2[0], r2[1]]]))
        for nq in nested:
            visit_query(nq, ctes, False)
        if is_top:
            top["root"] = (q, sc)

    visit_query(root, {}, True)
    out["tables"] = sorted(tables_used)
    out["refs"] = [[t, c, n] for (t, c), n in refs.items()]
    out["hints"] = [[t, c, dict(h)] for (t, c), h in hints.items()]
    out["literals"] = [[t, p, v] for (t, p), v in literals.items()]
    out["join_pairs"] = [list(map(list, jp)) for jp in {json.dumps(j): j for j in join_pairs}.values()]
    out["events"] = sorted(events_used)
    # result column mapping + shape on the top-level query
    if top["root"] is not None:
        q, sc = top["root"]
        cols = []
        n_agg = 0
        for x in q.select:
            name = x.alias if isinstance(x, a.Alias) else None
            e = x.expr if isinstance(x, a.Alias) else x
            if isinstance(e, a.Field):
                res = sc.resolve(e.chain)
                if res:
                    t, col, rest = res
                    cols.append({"name": name or str(e.chain[-1]), "kind": "field", "table": t,
                                 "path": ".".join([col] + [str(r) for r in rest if r != "?ambiguous"])})
                else:
                    cols.append({"name": name or str(e.chain[-1]), "kind": "other"})
            elif isinstance(e, a.Call) and e.name.lower() in AGG:
                n_agg += 1
                arg = None
                if e.args and isinstance(e.args[0], a.Field):
                    r = sc.resolve(e.args[0].chain)
                    if r:
                        arg = ".".join([r[1]] + [str(x) for x in r[2] if x != "?ambiguous"])
                fn = e.name.lower()
                if fn == "count" and getattr(e, "distinct", False):
                    fn = "uniq"
                cols.append({"name": name, "kind": "agg", "fn": fn, "arg": arg})
            else:
                cols.append({"name": name, "kind": "other"})
        reals = sc.real_tables()
        single = len(reals) == 1 and all(k == "table" for k, _ in sc.tables.values())
        shape = None
        gb_ok = q.group_by and all(isinstance(g, a.Field) or (isinstance(g, a.Field)) for g in q.group_by)
        if single and not q.group_by and n_agg == 0 and any(c["kind"] == "field" for c in cols):
            shape = "A"
        elif single and q.group_by and n_agg >= 1 and gb_ok:
            shape = "B"
        elif single and not q.group_by and n_agg >= 1 and all(c["kind"] == "agg" for c in cols):
            shape = "total"
        out["result_cols"] = cols
        out["shape"] = shape
        out["from_table"] = reals[0] if len(reals) == 1 else None
    out["window"] = window_of(sql)
    return out


def window_of(sql: str) -> dict:
    w = {}
    m = INTERVAL.findall(sql) or [(n, u) for u, n in INTERVAL_FN.findall(sql)]
    if m:
        w["interval_days"] = max(int(n) * UNIT_DAYS[u.lower()] for n, u in m)
    ds = sorted(set(re.findall(r"'(\d{4}-\d\d-\d\d)", sql)))
    if ds:
        w["min_date"], w["max_date"] = ds[0], ds[-1]
    return w


def known_tables(spec: dict) -> dict[str, set]:
    out = {}
    for tn, tb in ((spec.get("warehouse") or {}).get("tables") or {}).items():
        out[tn] = {f.get("name") for f in tb.get("fields") or [] if f.get("name")}
    return out


def num(x):
    try:
        s = str(x).replace(",", "").strip()
        if s in ("", "(null)", "null", "None", "nan"):
            return None
        return float(s)
    except Exception:  # noqa: BLE001
        return None


def conv_qfacts(f: dict, spec: dict) -> dict:
    known = known_tables(spec)
    calls = []
    dw: dict = C.defaultdict(lambda: C.defaultdict(lambda: {"types": C.Counter(), "literals": [], "values": [], "refs": 0}))
    joins = []
    dw_seeds: dict = C.defaultdict(list)
    event_seeds = []
    entity_literals = []
    volume = []
    series = []
    stats = C.Counter()
    for call in f["calls"]:
        sql = call.get("sql")
        if not sql or not isinstance(sql, str):
            continue
        corrupted = None
        if anoncheck is not None:
            try:
                corrupted = anoncheck.analyze_sql(sql, anoncheck.known_from_spec(spec) if spec else None).get("corrupted")
            except Exception:  # noqa: BLE001
                corrupted = None
        an = analyze_sql(sql, known)
        an["k"], an["turn"], an["tool"], an["is_error"], an["corrupted"] = call["k"], call["turn"], call["tool"], call["is_error"], corrupted
        calls.append(an)
        stats["sql"] += 1
        if not an["ok"]:
            stats["parse_error"] += 1
            continue
        if call["is_error"] or corrupted:
            stats["skipped_error_or_corrupted"] += 1
            continue
        for t, c, n in an["refs"]:
            if T.classify_table(t) == "dw":
                dw[t][c]["refs"] += n
        for t, c, h in an["hints"]:
            if T.classify_table(t) == "dw":
                dw[t][c]["types"].update(h)
        for t, p, v in an["literals"]:
            if T.classify_table(t) == "dw":
                dw[t][p.split(".")[0]]["literals"].extend(v)
            else:
                if re.search(r"email|distinct_id|person_id|user_id|\$group_\d|organization|org_id|company|account|name|^id$", p, re.I):
                    entity_literals.append({"table": t, "path": p, "lit": v, "k": call["k"]})
        joins.extend(an["join_pairs"])
        rows = call.get("rows") or []
        cols = an.get("result_cols") or []
        if not rows or not cols:
            continue
        rows = [r for r in rows if len(r) == len(cols)]
        ft = an.get("from_table")
        if an.get("shape") == "A" and ft:
            mapped = [(i, c["path"]) for i, c in enumerate(cols) if c["kind"] == "field"]
            seed = [{p: r[i] for i, p in mapped} for r in rows]
            if T.classify_table(ft) == "dw":
                for i, p in mapped:
                    dw[ft][p.split(".")[0]]["values"].extend(r[i] for r in rows[:200])
                dw_seeds[ft].append({"k": call["k"], "rows": seed, "where": an["literals"]})
            elif ft == "events":
                event_seeds.append({"k": call["k"], "rows": seed, "where": an["literals"], "window": an["window"]})
            stats["shape_A"] += 1
        elif an.get("shape") == "B" and ft:
            dims = [(i, c["path"]) for i, c in enumerate(cols) if c["kind"] == "field"]
            aggs = [(i, c) for i, c in enumerate(cols) if c["kind"] == "agg"]
            groups = []
            for r in rows:
                g = {"dims": {p: r[i] for i, p in dims}, "aggs": {}}
                for i, c in aggs:
                    g["aggs"][f"{c['fn']}({c.get('arg') or ''})"] = num(r[i])
                groups.append(g)
            if T.classify_table(ft) == "dw":
                for i, p in dims:
                    dw[ft][p.split(".")[0]]["values"].extend(r[i] for r in rows[:200])
                dw_seeds[ft].append({"k": call["k"], "groups": groups, "where": an["literals"]})
            elif ft == "events":
                dim_paths = [p for _, p in dims]
                time_dim = next((p for p in dim_paths if p == "timestamp"), None)
                ev_filter = an["events"]
                filtered = any(t == "events" and p not in ("event", "timestamp") for t, p, _ in an["literals"])
                if dim_paths == ["event"]:
                    volume.append({"k": call["k"], "kind": "by_event", "groups": groups, "window": an["window"], "filtered": filtered})
                event_seeds.append({"k": call["k"], "groups": groups, "where": an["literals"], "window": an["window"],
                                    "events": ev_filter, "time_dim": time_dim})
            stats["shape_B"] += 1
        elif an.get("shape") == "total" and ft == "events":
            volume.append({"k": call["k"], "kind": "total", "events": an["events"], "aggs": {
                f"{c['fn']}({c.get('arg') or ''})": num(rows[0][i]) for i, c in enumerate(cols) if c["kind"] == "agg"} if rows else {},
                "window": an["window"], "filtered": any(t == "events" and p not in ("event", "timestamp") for t, p, _ in an["literals"])})
            stats["shape_total"] += 1
    # Trends insight results -> per-event series (create_insight and executed saved insights)
    for call in f["calls"]:
        sch = call.get("schema")
        if call.get("is_error") or not isinstance(sch, dict) or not call.get("rows"):
            continue
        src = sch.get("source") if sch.get("kind") in ("InsightVizNode", "DataVisualizationNode") else sch
        if not isinstance(src, dict) or src.get("kind") != "TrendsQuery" or src.get("breakdownFilter"):
            continue
        secs = trend_sections(call.get("cols") or [], call["rows"])
        if len(secs) < 2:
            continue  # not a compare-mode result: handled by the loop below
        stats["series_compare_results"] += 1
        interval = src.get("interval") or "day"
        ser = src.get("series") or []
        for period, cols, rows in secs:
            if len(cols) != len(ser) + 1:
                continue
            for j, s in enumerate(ser):
                if s.get("kind") != "EventsNode" or not s.get("event"):
                    continue
                pts = []
                for r in rows:
                    if len(r) != len(cols):
                        continue
                    dd = str(r[0]).split(" ")[0]
                    v = num(r[j + 1])
                    if re.match(r"^\d{4}-\d\d-\d\d", dd) and v is not None:
                        pts.append([dd[:10], v, "partial" in str(r[0])])
                if len(pts) >= 3:
                    series.append({"k": call["k"], "event": s["event"], "math": s.get("math") or "total",
                                   "interval": interval, "filtered": bool(s.get("properties") or src.get("properties")),
                                   "points": pts, **({"period": "previous"} if period == "previous" else {})})
    for call in f["calls"]:
        if len(trend_sections(call.get("cols") or [], call.get("rows") or [])) >= 2:
            continue
        sch = call.get("schema")
        if call.get("is_error") or not isinstance(sch, dict) or not call.get("rows"):
            continue
        src = sch.get("source") if sch.get("kind") in ("InsightVizNode", "DataVisualizationNode") else sch
        if not isinstance(src, dict) or src.get("kind") != "TrendsQuery" or src.get("breakdownFilter"):
            continue
        ser = src.get("series") or []
        cols = call.get("cols") or []
        if len(cols) != len(ser) + 1:
            continue
        interval = src.get("interval") or "day"
        for j, s in enumerate(ser):
            if s.get("kind") != "EventsNode" or not s.get("event"):
                continue
            pts = []
            for r in call["rows"]:
                if len(r) != len(cols):
                    continue
                d = str(r[0]).split(" ")[0]
                v = num(r[j + 1])
                if re.match(r"^\d{4}-\d\d-\d\d", d) and v is not None:
                    pts.append([d[:10], v, "partial" in str(r[0])])
            if len(pts) >= 3:
                series.append({"k": call["k"], "event": s["event"], "math": s.get("math") or "total", "interval": interval,
                               "filtered": bool(s.get("properties") or src.get("properties")), "points": pts})
    return {"conversation_id": f["conversation_id"], "calls": calls,
            "dw": {t: {c: {**v, "types": dict(v["types"]), "values": v["values"][:300]} for c, v in cs.items()} for t, cs in dw.items()},
            "joins": joins, "dw_seeds": dw_seeds, "event_seeds": event_seeds, "entity_literals": entity_literals,
            "volume": volume, "series": series, "stats": dict(stats)}


def trend_sections(cols: list, rows: list) -> list[tuple[str, list, list]]:
    """Split a compare-mode Trends table into ("previous"|"current", header, data rows) sections. A section starts at
    a one-cell row (or the column header) ending in "period:"; its next row is the header. Returns [] when the table
    has no such sections."""
    lines = [list(cols)] + [list(r) for r in rows]
    out, cur = [], None
    i = 0
    while i < len(lines):
        r = lines[i]
        lab = str(r[0]).strip().lower() if len(r) == 1 and r else ""
        if lab.endswith("period:"):
            cur = ["previous" if lab.startswith("previous") else "current", None, []]
            out.append(cur)
            if i + 1 < len(lines):
                cur[1] = lines[i + 1]
                i += 2
                continue
        elif cur is not None and cur[1] is not None and len(r) == len(cur[1]):
            cur[2].append(r)
        i += 1
    return [(p, h, rs) for p, h, rs in out if h]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test_v2")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--ids", default=None, help="comma-separated conversation ids")
    a = ap.parse_args()
    sys.path.insert(0, "/opt/posthog-env")
    import boot

    boot.init()
    os.makedirs(a.out, exist_ok=True)
    tot = C.Counter()
    ids = set(a.ids.split(",")) if a.ids else None
    for p in sorted(glob.glob(os.path.join(FACTS, "*.json"))):
        if os.path.basename(p).startswith("_"):
            continue
        f = json.load(open(p))
        if f.get("split") not in a.split.split(",") or (ids and f["conversation_id"] not in ids):
            continue
        sp = os.path.join(SPECS, f"{f['conversation_id']}.json")
        spec = json.load(open(sp)) if os.path.exists(sp) else {}
        q = conv_qfacts(f, spec)
        with open(os.path.join(a.out, f"{f['conversation_id']}.json"), "w") as fh:
            json.dump(q, fh, default=str)
        tot.update(q["stats"])
        tot["convs"] += 1
        tot["dw_tables"] += len(q["dw"])
        tot["dw_cols"] += sum(len(v) for v in q["dw"].values())
        tot["event_seed_sets"] += len(q["event_seeds"])
        tot["dw_seed_sets"] += sum(len(v) for v in q["dw_seeds"].values())
        tot["series"] += len(q["series"])
        tot["volume"] += len(q["volume"])
        tot["entity_literals"] += len(q["entity_literals"])
        tot["join_pairs"] += len(q["joins"])
    print(json.dumps(dict(tot)), flush=True)
    os._exit(0)


if __name__ == "__main__":
    main()
