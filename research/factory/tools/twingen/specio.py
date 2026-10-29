"""Load conversation specs and cluster specs into one normalized in-memory form."""
import json, re, datetime as dt
from collections import Counter

ROOT = "/opt/posthog-sft/env-research"
TWINS = f"{ROOT}/twins"

TZ_MAP = {
    "UTC": "UTC", "IST+330": "Asia/Kolkata", "+0530(+330)": "Asia/Kolkata", "-03(-180)": "America/Sao_Paulo",
    "Europe/Central": "Europe/Berlin", "Europe/Eastern": "Europe/Athens", "+08(+480)": "Asia/Singapore",
    "Australia/Eastern": "Australia/Sydney", "Australia/Central": "Australia/Adelaide", "CST+480": "Asia/Shanghai",
    "-05(-300)": "America/Bogota", "+07(+420)": "Asia/Bangkok", "+04(+240)": "Asia/Dubai", "+05(+300)": "Asia/Tashkent",
    "-02(-120)": "America/Noronha", "EAT(+180)": "Africa/Nairobi", "AWST(+480)": "Australia/Perth",
    "PKT(+300)": "Asia/Karachi", "AKDT(-480)": "America/Anchorage", "SAST(+120)": "Africa/Johannesburg",
    "NDT(-150)": "America/St_Johns",
}


def resolve_tz(family, offset_min):
    from zoneinfo import ZoneInfo
    cands = [TZ_MAP.get(family or ""), family]
    for c in cands:
        if not c:
            continue
        try:
            ZoneInfo(c)
            return c
        except Exception:
            pass
    if offset_min is not None and offset_min % 60 == 0:
        h = -offset_min // 60  # Etc/GMT signs are inverted
        return "UTC" if h == 0 else f"Etc/GMT{h:+d}"
    return "UTC"


def parse_ts(s):
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d)(?::(\d\d))?", s)
    if not m:
        return None
    y = int(m.group(1))
    if not 2023 <= y <= 2027:
        return None
    try:
        return dt.datetime(*[int(g or 0) for g in m.groups()], tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def _prop(p):
    t = p.get("type")
    if p.get("types"):  # cluster: majority type histogram
        t = max(p["types"].items(), key=lambda kv: kv[1])[0]
        t = None if t in ("None", "null") else t
    return {"type": t, "description": p.get("description"), "values": [str(v) for v in (p.get("values") or [])],
            "more_values": p.get("more_values"), "values_status": p.get("values_status"),
            "standard": bool(p.get("standard")), "sources": p.get("sources") or {}}


def _props(d):
    return {k: _prop(v) for k, v in (d or {}).items()}


def load(path):
    s = json.load(open(path))
    is_cluster = "members" in s
    out = {"id": s.get("cluster_id") or s.get("conversation_id"), "kind": "cluster" if is_cluster else "conversation",
           "members": s.get("members") or [s.get("conversation_id")], "split": s.get("split"),
           "modes": sorted(set(s.get("modes") or []) | set(m for c in s.get("conversations") or [] for m in c.get("modes") or []))}
    # timezone and now
    tz = s["project"].get("timezone") or None
    fam = off = None
    times = []
    if tz:
        if is_cluster:
            obs = sorted(tz.get("observed") or [], key=lambda o: -(o.get("n") or 0))
            if obs:
                fam, off = obs[0].get("family"), obs[0].get("utc_offset_min")
            times = tz.get("current_time_utc_range") or []
        else:
            fam, off = tz.get("family"), tz.get("utc_offset_min")
            times = tz.get("current_time_utc") or []
    ts = [t for t in (parse_ts(x) for x in times) if t]
    out["now_utc"] = max(ts) if ts else None
    out["tz"] = resolve_tz(fam, off) if fam else "UTC"
    out["tz_known"] = bool(fam)
    # events
    ev = {}
    for name, e in (s.get("events") or {}).items():
        evid = e.get("evidence")
        if isinstance(evid, dict):
            if not (evid.get("observed") or evid.get("referenced")):
                continue
            evid = "observed" if evid.get("observed") else "referenced"
        if evid == "failed_only":
            continue
        ev[name] = {"standard": bool(e.get("standard")), "description": e.get("description"),
                    "not_seen_days": e.get("not_seen_days"), "evidence": evid,
                    "sources": e.get("sources") or {}, "properties": _props(e.get("properties")),
                    "volume": e.get("volume") or {}}
    out["events"] = ev
    out["unscoped"] = _props(s.get("event_properties_unscoped"))
    ent = s.get("entities") or {}
    out["person_props"] = _props((ent.get("person") or {}).get("properties"))
    out["session_props"] = _props((ent.get("session") or {}).get("properties"))
    g = s.get("groups") or {}
    out["group_types"] = {k: _props(v.get("properties")) for k, v in (g.get("types") or {}).items()}
    out["group_indices"] = sorted(set(str(x) for x in g.get("indices_used") or []))
    out["warehouse"] = (s.get("warehouse") or {}).get("tables") or {}
    out["objects"] = s.get("objects") or {}
    out["anchors"] = s.get("anchors") or []
    sc = {}
    for k, v in (s.get("scale") or {}).items():
        sc[k] = v.get("max") if isinstance(v, dict) else v
    out["scale"] = sc
    out["n_tasks"] = len(s.get("tasks") or []) + sum(len(c.get("tasks") or []) for c in s.get("conversations") or [])
    return out


def num(x):
    try:
        v = float(str(x).replace(",", "").strip())
        if v != v or v in (float("inf"), float("-inf")):
            return None
        return v
    except Exception:
        return None


def target_daily(vol):
    """Best estimate of (daily total, daily DAU, lower_bound_only) from an event's volume dict."""
    def est(o):
        mx, md = o.get("max") or 0.0, o.get("median") or 0.0
        return max(md, 0.35 * mx)
    tot = dau = None
    filt = False
    for key, mult in (("day_total", 1.0), ("week_total", 1 / 7), ("month_total", 1 / 30), ("hour_total", 24.0),
                      ("minute_total", 1440.0)):
        if key in vol:
            tot, filt = est(vol[key]) * mult, bool(vol[key].get("filtered"))
            break
    for key, mult in (("day_dau", 1.0), ("week_dau", 0.35), ("month_dau", 0.15), ("hour_dau", 3.0)):
        if key in vol:
            dau = est(vol[key]) * mult
            break
    return tot, dau, filt


def shape_of(name):
    n = name.lower().lstrip("$")
    for pat, lab in [(r"(^|_)(email|e_mail)$|email", "email"), (r"_id$|^id$|uuid|_key$", "id"),
                     (r"_at$|_date$|_time$|timestamp|^date$", "datetime"), (r"(_count|^num_|^n_|_total|_number)$|^count", "count"),
                     (r"(_ms|_seconds|_secs|_duration|duration|latency)", "duration"),
                     (r"(amount|price|revenue|cost|mrr|arr|value|usd|total)", "money"),
                     (r"^(is|has|can|should|was|did)_|_enabled$|_flag$", "bool"), (r"url|href|link", "url"),
                     (r"(^|_)(name|title|label)$", "name"), (r"(_type|_kind|_category|_status|_source|^type|^status|plan|tier|role)", "category"),
                     (r"path|route|page|screen", "path")]:
        if re.search(pat, n):
            return lab
    return "other"
