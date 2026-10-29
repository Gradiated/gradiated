"""Validate generated projects against their specs. Aggregates only.

Usage: validate.py OUT_JSON PROJECT_DIR... (each project dir has manifest.json naming its spec)
"""
import glob, json, math, os, sys, time
from collections import Counter, defaultdict
import datetime as dt

import numpy as np
import orjson
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anchors, specio

SAMPLE_PER_EVENT = 4000


def spec_path(man):
    sid = man["spec_id"]
    p = f"{specio.TWINS}/clusters/{sid}.json"
    return p if man["spec_kind"] == "cluster" else f"{specio.TWINS}/specs/{sid}.json"


def validate(pdir):
    man = json.load(open(os.path.join(pdir, "manifest.json")))
    S = specio.load(spec_path(man))
    defs = orjson.loads(open(os.path.join(pdir, "definitions.json"), "rb").read())
    t = pq.read_table(os.path.join(pdir, "events.parquet"),
                      columns=["event", "timestamp", "person_id", "properties", "$session_id"])
    ev = t.column("event").to_numpy(zero_copy_only=False)
    ts = t.column("timestamp").cast("int64").to_numpy() / 1e6
    pid = t.column("person_id").to_numpy(zero_copy_only=False)
    sid = t.column("$session_id").to_numpy(zero_copy_only=False)
    import pyarrow as pa
    props_col = t.column("properties").cast(pa.large_string())
    names = Counter(ev.tolist())
    defined = {d["name"] for d in defs["event_definitions"]}
    r = {"spec_id": man["spec_id"], "kind": man["spec_kind"], "events": int(len(ev)), "persons": man["counts"]["persons"],
         "gen_seconds": man["timing_s"]["total"], "volume_scale": man["volume_scale"], "history_days": man["history_days"]}
    # ---- event coverage
    act = [e for e, i in S["events"].items() if i["not_seen_days"] is None]
    ina = [e for e, i in S["events"].items() if i["not_seen_days"] is not None]
    r["spec_active_events"] = len(act)
    r["spec_active_events_present"] = sum(1 for e in act if names.get(e))
    r["spec_inactive_events"] = len(ina)
    r["spec_inactive_events_in_data"] = sum(1 for e in ina if names.get(e))
    r["spec_inactive_events_defined"] = sum(1 for e in ina if e in defined)
    # ---- property coverage (sampled rows per event)
    rng = np.random.default_rng(0)
    idx_by_ev = defaultdict(list)
    for i, e in enumerate(ev):
        idx_by_ev[e].append(i)
    seen_props = defaultdict(set)
    seen_vals = defaultdict(set)
    for e, idx in idx_by_ev.items():
        if len(idx) > SAMPLE_PER_EVENT:
            idx = rng.choice(idx, SAMPLE_PER_EVENT, replace=False)
        sub = props_col.take(np.asarray(idx)).to_pylist()
        for s in sub:
            d = orjson.loads(s)
            for k, v in d.items():
                seen_props[e].add(k)
                seen_props["*"].add(k)
                if isinstance(v, (str, int, float, bool)):
                    seen_vals[k].add(str(v).lower() if isinstance(v, bool) else str(v))
                    if isinstance(v, float) and v == int(v):
                        seen_vals[k].add(str(int(v)))
    pdef_names = {d["name"] for d in defs["property_definitions"] if d["type"] == 1}
    tot = pres = virt = 0
    vtot = vpres = 0
    for e, info in S["events"].items():
        for p, d in info["properties"].items():
            tot += 1
            if p in seen_props.get(e, ()) or (names.get(e, 0) == 0 and p in pdef_names):
                pres += 1
            elif p in pdef_names:
                virt += 1
            if d["values"] and d["type"] != "DateTime" and d["values_status"] != "result_values":
                sv = seen_vals.get(p, ())
                for v in d["values"][:100]:
                    vtot += 1
                    hit = v in sv or v.lower() in sv
                    if not hit and d["values_status"] == "filter_values":  # filter literals are often icontains
                        hit = any(v.lower() in str(x).lower() for x in list(sv)[:5000])
                    vpres += hit
    r["spec_event_props"] = tot
    r["spec_event_props_present_on_event"] = pres
    r["spec_event_props_definition_only"] = virt
    utot = upres = 0
    for p, d in S["unscoped"].items():
        utot += 1
        upres += p in seen_props["*"]
    r["spec_unscoped_props"] = utot
    r["spec_unscoped_props_present"] = upres
    r["spec_prop_values"] = vtot
    r["spec_prop_values_present"] = vpres
    # person props
    persons = pq.read_table(os.path.join(pdir, "persons.parquet"), columns=["properties"]).column("properties").to_pylist()
    pseen = set()
    for s in persons[:20000]:
        pseen.update(orjson.loads(s).keys())
    pp = [p for p in S["person_props"] if not p.startswith("$virt_")]
    r["spec_person_props"] = len(pp)
    r["spec_person_props_present"] = sum(1 for p in pp if p in pseen)
    # ---- volumes against hints
    now = dt.datetime.fromisoformat(man["now_utc"].replace("Z", "+00:00")).timestamp()
    win = min(30, man["history_days"])
    lo = now - win * 86400
    m = ts >= lo
    day = ((ts - lo) // 86400).astype(np.int64)
    cmp = []
    for e, metric, val, src, lower in anchors.volume_hints(S):
        if lower or val <= 0 or e not in names:
            continue
        sel = m & (ev == e)
        if metric == "total":
            g = sel.sum() / win
        else:
            dd = day[sel]
            pp_ = pid[sel]
            g = len(set(zip(dd.tolist(), pp_.tolist()))) / win
        tgt = val * man["volume_scale"]
        cmp.append({"event_std": e.startswith("$"), "metric": metric, "source": src, "target": tgt, "raw_target": val,
                    "gen": float(g)})
    def within(c, f=3.0):
        tg, g = c["target"], c["gen"]
        if tg < 1 and g < 3:  # sub-1/day targets: accept anything in [0, 3]/day
            return True
        return tg / f <= g <= tg * f
    r["volume_checks"] = len(cmp)
    r["volume_within_3x"] = sum(within(c) for c in cmp)
    r["volume_within_3x_ge1"] = sum(within(c) for c in cmp if c["target"] >= 1)
    r["volume_checks_ge1"] = sum(1 for c in cmp if c["target"] >= 1)
    r["volume_log_ratio"] = [math.log10(max(c["gen"], 1e-3) / max(c["target"], 1e-3)) for c in cmp if c["target"] >= 1]
    # project DAU (all events) vs manifest target
    dd = day[m]
    r["dau_last30"] = len(set(zip(dd.tolist(), pid[m].tolist()))) / win
    r["target_dau"] = man["target_dau"]
    # sessions
    order = np.lexsort((ts, sid))
    s_sorted, t_sorted = sid[order], ts[order]
    brk = np.r_[True, s_sorted[1:] != s_sorted[:-1]]
    starts = np.nonzero(brk)[0]
    ends = np.r_[starts[1:], len(s_sorted)] - 1
    durs = t_sorted[ends] - t_sorted[starts]
    sizes = ends - starts + 1
    r["sessions"] = int(len(starts))
    r["session_duration_median_s"] = float(np.median(durs)) if len(durs) else 0
    r["events_per_session_median"] = float(np.median(sizes)) if len(sizes) else 0
    return r


def safe_validate(p):
    try:
        return validate(p.rstrip("/"))
    except Exception as ex:  # report failures as type only (messages may contain names)
        return {"project": os.path.basename(p.rstrip("/")), "error": type(ex).__name__}


def main():
    out = sys.argv[1]
    from multiprocessing import Pool
    with Pool(int(os.environ.get("VALIDATE_WORKERS", "16"))) as pool:
        res = pool.map(safe_validate, sys.argv[2:], chunksize=1)
    json.dump(res, open(out, "w"), indent=1)
    ok = [r for r in res if "error" not in r]
    def s(k):
        return sum(r[k] for r in ok)
    print(json.dumps({
        "projects": len(res), "errors": len(res) - len(ok),
        "active_event_coverage": f"{s('spec_active_events_present')}/{s('spec_active_events')}",
        "inactive_events_in_data": f"{s('spec_inactive_events_in_data')}/{s('spec_inactive_events')}",
        "inactive_events_defined": f"{s('spec_inactive_events_defined')}/{s('spec_inactive_events')}",
        "event_prop_coverage_on_event": f"{s('spec_event_props_present_on_event')}/{s('spec_event_props')}",
        "event_prop_definition_only": s("spec_event_props_definition_only"),
        "unscoped_prop_coverage": f"{s('spec_unscoped_props_present')}/{s('spec_unscoped_props')}",
        "person_prop_coverage": f"{s('spec_person_props_present')}/{s('spec_person_props')}",
        "prop_value_coverage": f"{s('spec_prop_values_present')}/{s('spec_prop_values')}",
        "volume_within_3x": f"{s('volume_within_3x')}/{s('volume_checks')}",
        "volume_within_3x_target_ge1": f"{s('volume_within_3x_ge1')}/{s('volume_checks_ge1')}",
        "projects_with_volume_checks": sum(1 for r in ok if r["volume_checks"]),
    }, indent=1))


if __name__ == "__main__":
    main()
