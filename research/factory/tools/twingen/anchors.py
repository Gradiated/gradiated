"""Turn spec anchors (query/result pairs) into volume hints, funnel shapes and retention curves."""
import re
from specio import num, target_daily

UNIQ_COL = re.compile(r"user|person|visitor|unique|uniq|dau|active|people|customers|accounts|distinct", re.I)
BUCKET_DAYS = {"toDate": 1, "toStartOfDay": 1, "toStartOfWeek": 7, "toMonday": 7, "toStartOfMonth": 30,
               "toStartOfHour": 1 / 24}


def interval_days(sql):
    if not isinstance(sql, str):
        return None
    pats = [(r"INTERVAL\s+'?(\d+)\s*(DAY|WEEK|MONTH|HOUR|YEAR)", 1), (r"toInterval(Day|Week|Month|Hour|Year)\s*\(\s*(\d+)", 2)]
    unit_days = {"day": 1, "week": 7, "month": 30, "hour": 1 / 24, "year": 365}
    for p, order in pats:
        m = re.search(p, sql, re.I)
        if m:
            n, u = (m.group(1), m.group(2)) if order == 1 else (m.group(2), m.group(1))
            d = int(n) * unit_days[u.lower()]
            if 0 < d <= 3650:
                return d
    return None


def date_from_days(df):
    """'-30d' style relative dateRange.date_from to days."""
    if not isinstance(df, str):
        return None
    m = re.fullmatch(r"-(\d+)([hdwmy])", df.strip())
    if not m:
        return {"all": 365, "dStart": 1, "mStart": 30, "yStart": 300}.get(df.strip())
    n, u = int(m.group(1)), m.group(2)
    return n * {"h": 1 / 24, "d": 1, "w": 7, "m": 30, "y": 365}[u]


def required_history_days(spec):
    best = 0
    for a in spec["anchors"]:
        q = a.get("query")
        d = None
        if isinstance(q, dict):
            d = date_from_days((q.get("dateRange") or {}).get("date_from"))
        elif isinstance(q, str):
            d = interval_days(q)
        if d:
            best = max(best, d)
    for o in (spec["objects"].get("insights") or {}).values():
        q = o.get("query") or {}
        d = date_from_days((q.get("dateRange") or {}).get("date_from")) if isinstance(q, dict) else None
        if d:
            best = max(best, d)
    return best


def volume_hints(spec):
    """[(event, metric, daily_value, source, lower_bound)] for calibration and validation."""
    hints = []
    for name, e in spec["events"].items():
        tot, dau, filt = target_daily(e["volume"])
        if tot is not None:
            hints.append((name, "total", tot, "volume", filt))
        if dau is not None:
            hints.append((name, "dau", dau, "volume", filt))
    for a in spec["anchors"]:
        kind = a.get("result_kind")
        ef = a.get("events_filter") or []
        if a.get("has_property_filter") or len(ef) != 1 or ef[0] not in spec["events"]:
            ef = None
        cols = a.get("columns") or []
        rows = a.get("rows") or []
        if kind == "sql_events_timeseries" and ef and a.get("bucket") in BUCKET_DAYS and len(rows) >= 3:
            bd = BUCKET_DAYS[a["bucket"]]
            used_tot = used_dau = False
            for ci in range(1, len(cols)):
                vals = [num(r[ci]) for r in rows if ci < len(r)]
                vals = [v for v in vals if v is not None]
                if len(vals) < 3:
                    continue
                vals.sort()
                med = vals[len(vals) // 2]
                if re.search(r"pct|rate|percent|ratio|avg|mean|median", cols[ci], re.I):
                    continue
                if UNIQ_COL.search(cols[ci]):
                    if not used_dau and bd <= 1:
                        hints.append((ef[0], "dau", med / bd, "sql_timeseries", False)); used_dau = True
                elif not used_tot:
                    hints.append((ef[0], "total", med / bd, "sql_timeseries", False)); used_tot = True
        elif kind == "sql_events_breakdown" and cols and cols[0].lower() in ("event", "event_name", "name") \
                and not a.get("has_property_filter"):
            days = interval_days(a.get("query"))
            if not days:
                continue
            for r in rows:
                if not r or r[0] not in spec["events"]:
                    continue
                for ci in range(1, min(len(cols), len(r))):
                    v = num(r[ci])
                    if v is None or re.search(r"pct|rate|percent|avg|first|last|min|max", cols[ci], re.I):
                        continue
                    if UNIQ_COL.search(cols[ci]):
                        if days <= 1:
                            hints.append((r[0], "dau", v / days, "sql_breakdown", False))
                    else:
                        hints.append((r[0], "total", v / days, "sql_breakdown", False))
                        break
    return hints


def funnel_from_anchor(a):
    """(step_events, counts, median_conv_seconds) or None."""
    q = a.get("query")
    if not isinstance(q, dict):
        return None
    steps = [s.get("event") for s in q.get("series") or []]
    counts = None
    times = None
    for r in a.get("rows") or []:
        if r and r[0] == "Total person count":
            counts = [num(x) for x in r[1:]]
        if r and r[0] == "Median conversion time":
            times = [dur_seconds(x) for x in r[1:]]
    if not counts or any(c is None for c in counts) or len(counts) < 2:
        return None
    return steps, counts, times


def dur_seconds(s):
    if not isinstance(s, str) or s.strip() in ("-", ""):
        return None
    tot = 0
    found = False
    for n, u in re.findall(r"(\d+(?:\.\d+)?)\s*([a-z]+)", s):
        mult = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hr": 3600, "d": 86400, "w": 604800}.get(u)
        if mult:
            tot += float(n) * mult
            found = True
    return tot if found else None


def retention_from_anchor(a):
    """(unit, [(cohort_size, [pct0, pct1, ...])]) or None."""
    rows = a.get("rows") or []
    unit = None
    out = []
    for r in rows:
        if r and isinstance(r[0], str) and r[0].startswith("Time ") and ":" in r[0]:
            unit = r[0].split(":", 1)[1].strip().lower()
        if len(r) >= 3 and re.match(r"\d{4}-\d\d-\d\d", str(r[0])):
            size = num(r[1])
            pcts = [num(str(x).rstrip("%")) for x in r[2:]]
            pcts = [p for p in pcts if p is not None]
            if size and pcts:
                out.append((size, pcts))
    if not out:
        return None
    return unit or "day", out
