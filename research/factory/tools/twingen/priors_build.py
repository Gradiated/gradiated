"""Aggregate priors across all conversation specs. Writes JSON files to twingen/priors/.

Privacy rule: a string value enters a cross-project prior only if it appears in at least MIN_SPECS_VALUE distinct
specs, so a project-specific value never leaks into another synthetic project. Prints aggregate counts only.
"""
import glob, json, math, os, re, sys, collections
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import specio, anchors
from specio import num, shape_of

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "priors")
MIN_SPECS_VALUE = 3
MIN_SPECS_NAME = 15


def qs(xs, ps=(0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)):
    xs = sorted(xs)
    if not xs:
        return None
    return {f"p{int(p * 100)}": xs[min(len(xs) - 1, int(len(xs) * p))] for p in ps} | {"n": len(xs)}


class PropAgg:
    def __init__(self):
        self.n = 0
        self.types = Counter()
        self.vals = Counter()       # value -> n specs
        self.nums = []
        self.descs = Counter()
        self.more = 0

    def add(self, p, seen_vals):
        self.n += 1
        if p["type"]:
            self.types[p["type"]] += 1
        if p.get("description"):
            self.descs[p["description"]] += 1
        if p.get("more_values"):
            self.more += 1
        for v in set(p["values"]):
            x = num(v)
            if x is not None and p["type"] in ("Numeric", None):
                self.nums.append(x)
            if v not in seen_vals:
                self.vals[v] += 1

    def out(self, nspecs_base):
        t = self.types.most_common(1)[0][0] if self.types else None
        vals = [(v, c) for v, c in self.vals.most_common(300) if c >= MIN_SPECS_VALUE]
        d = {"frac": round(self.n / max(1, nspecs_base), 4), "n_specs": self.n, "type": t,
             "types": dict(self.types), "values": vals, "more_values_frac": round(self.more / max(1, self.n), 3)}
        if self.nums:
            d["numeric"] = qs(self.nums)
        if self.descs:
            desc, c = self.descs.most_common(1)[0]
            if c >= MIN_SPECS_VALUE:
                d["description"] = desc
        return d


def value_class(v):
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", v, re.I):
        return "uuid"
    if re.fullmatch(r"-?\d+", v):
        return "int"
    if re.fullmatch(r"-?\d+\.\d+", v):
        return "float"
    if re.fullmatch(r"[0-9a-f]{16,}", v, re.I):
        return "hex"
    if "@" in v and "." in v.split("@")[-1]:
        return "email"
    if re.match(r"https?://", v):
        return "url"
    if re.fullmatch(r"\d{4}-\d\d-\d\d([T ][\d:.]+Z?)?", v):
        return "datetime"
    if v.lower() in ("true", "false"):
        return "bool"
    if re.fullmatch(r"[a-z]+_[A-Za-z0-9]{6,}", v):
        return "prefixed_id"
    if re.fullmatch(r"[a-z0-9]+([_-][a-z0-9]+)*", v):
        return "slug"
    return "text"


def main():
    files = sorted(glob.glob(f"{specio.TWINS}/specs/*.json"))
    std = defaultdict(lambda: defaultdict(PropAgg))      # $event -> prop -> agg
    std_n = Counter()                                     # $event -> specs with prop list
    cust_dollar = defaultdict(PropAgg); cust_n = 0        # $ props on custom events
    cust_props = defaultdict(PropAgg)                      # custom prop names on custom events
    cust_props_specs = defaultdict(set)
    nprops_custom = []
    shape_types = defaultdict(Counter); shape_nums = defaultdict(list); shape_vclass = defaultdict(Counter)
    person = defaultdict(PropAgg); person_n = 0
    person_custom_specs = defaultdict(set)
    group_props = defaultdict(PropAgg)
    dollar_any = defaultdict(PropAgg)                      # any $ prop on any event / unscoped
    session = defaultdict(PropAgg); session_n = 0
    ev_daily = defaultdict(list); ev_dau = defaultdict(list); ev_per_dau = defaultdict(list)
    rel_to_pv = defaultdict(list); custom_rel_to_pv = []
    proj_dau = []; proj_total = []; proj_nevents_active = []; proj_custom_active = []
    persons_ratio = []
    funnel_conv = defaultdict(list); funnel_time = []
    retention = defaultdict(lambda: defaultdict(list))
    custom_event_names = defaultdict(set)                  # name -> tz families
    custom_event_specs = Counter()
    now_list = []
    hist_req = []
    wh_field_types = Counter(); wh_fields_by_name = defaultdict(Counter); wh_n = 0
    obj_counts = defaultdict(list)
    ev_nsd = defaultdict(Counter)

    for f in files:
        s = specio.load(f)
        if s["now_utc"]:
            now_list.append(s["now_utc"].timestamp())
        fam = s["tz"] if s["tz_known"] else None
        active = [n for n, e in s["events"].items() if e["not_seen_days"] is None]
        proj_nevents_active.append(len(active))
        proj_custom_active.append(sum(1 for n in active if not s["events"][n]["standard"]))
        for n, e in s["events"].items():
            ev_nsd[n if e["standard"] else "<custom>"]["inactive" if e["not_seen_days"] is not None else "active"] += 1
            if not e["standard"]:
                custom_event_specs[n] += 1
                if fam:
                    custom_event_names[n].add(fam)
            if e["properties"]:
                if e["standard"]:
                    std_n[n] += 1
                    for pn, p in e["properties"].items():
                        std[n][pn].add(p, ())
                else:
                    cust_n += 1
                    nprops_custom.append(sum(1 for pn in e["properties"] if not pn.startswith("$")))
                    for pn, p in e["properties"].items():
                        if pn.startswith("$"):
                            cust_dollar[pn].add(p, ())
                        else:
                            cust_props[pn].add(p, ())
                            cust_props_specs[pn].add(s["id"])
            for pn, p in e["properties"].items():
                if pn.startswith("$"):
                    dollar_any[pn].add(p, ())
                else:
                    sh = shape_of(pn)
                    if p["type"]:
                        shape_types[sh][p["type"]] += 1
                    for v in p["values"]:
                        x = num(v)
                        if x is not None and p["type"] == "Numeric":
                            shape_nums[sh].append(x)
                        shape_vclass[sh][value_class(v)] += 1
        for pn, p in s["unscoped"].items():
            if pn.startswith("$"):
                dollar_any[pn].add(p, ())
        if s["person_props"]:
            person_n += 1
            for pn, p in s["person_props"].items():
                person[pn].add(p, ())
                if not pn.startswith("$"):
                    person_custom_specs[pn].add(s["id"])
                    sh = shape_of(pn)
                    if p["type"]:
                        shape_types["person:" + sh][p["type"]] += 1
        if s["session_props"]:
            session_n += 1
            for pn, p in s["session_props"].items():
                session[pn].add(p, ())
        for gt, props in s["group_types"].items():
            for pn, p in props.items():
                group_props[pn].add(p, ())
        # volumes
        hints = anchors.volume_hints(s)
        tot = defaultdict(float); dau = defaultdict(float)
        for ev, metric, val, src, lb in hints:
            if lb:
                continue
            if metric == "total":
                tot[ev] = max(tot[ev], val)
            else:
                dau[ev] = max(dau[ev], val)
        for ev, v in tot.items():
            key = ev if s["events"][ev]["standard"] else "<custom>"
            ev_daily[key].append(v)
            if dau.get(ev):
                ev_per_dau[key].append(v / dau[ev])
        for ev, v in dau.items():
            ev_dau[ev if s["events"][ev]["standard"] else "<custom>"].append(v)
        pv = tot.get("$pageview")
        if pv and pv > 0:
            for ev, v in tot.items():
                if ev != "$pageview":
                    (rel_to_pv[ev] if s["events"][ev]["standard"] else custom_rel_to_pv).append(v / pv)
        d = max(list(dau.values()) + [s["scale"].get("all_events_day_dau") or 0])
        if d > 0:
            proj_dau.append(d)
        t = max(sum(tot.values()), s["scale"].get("all_events_day_total") or 0)
        if t > 0:
            proj_total.append(t)
        if s["scale"].get("persons_count") and d > 0:
            persons_ratio.append(s["scale"]["persons_count"] / d)
        hist_req.append(anchors.required_history_days(s))
        for a in s["anchors"]:
            if a.get("result_kind") == "FunnelsQuery":
                fr = anchors.funnel_from_anchor(a)
                if fr:
                    steps, counts, times = fr
                    for k in range(1, len(counts)):
                        if counts[k - 1] and counts[k - 1] >= 5:
                            funnel_conv[min(k, 5)].append(min(1.0, counts[k] / counts[k - 1]))
                    for tm in times or []:
                        if tm:
                            funnel_time.append(tm)
            elif a.get("result_kind") == "RetentionQuery":
                rr = anchors.retention_from_anchor(a)
                if rr:
                    unit, cohorts = rr
                    unit = unit.rstrip("s")
                    for size, pcts in cohorts:
                        if size >= 10:
                            for i, p in enumerate(pcts[:13]):
                                retention[unit][i].append(p / 100)
        if s["warehouse"]:
            wh_n += 1
            for tn, tb in s["warehouse"].items():
                for fl in tb.get("fields") or []:
                    wh_field_types[fl.get("type")] += 1
                    wh_fields_by_name[fl.get("name")][fl.get("type")] += 1
        for k, objs in s["objects"].items():
            obj_counts[k].append(len(objs))

    os.makedirs(OUT, exist_ok=True)

    def dump(name, obj):
        with open(os.path.join(OUT, name), "w") as fh:
            json.dump(obj, fh, indent=1, sort_keys=True, default=str)

    std_out = {}
    for ev, props in std.items():
        if std_n[ev] < 2:
            continue
        std_out[ev] = {"n_specs": std_n[ev],
                       "properties": {pn: a.out(std_n[ev]) for pn, a in props.items() if a.n >= 2 and pn.startswith("$")}}
    dump("std_event_props.json", std_out)
    dump("custom_event_dollar_props.json", {"n_specs": cust_n, "properties": {
        pn: a.out(cust_n) for pn, a in cust_dollar.items() if a.n >= 5}})
    common_custom = {pn: a.out(cust_n) | {"n_projects": len(cust_props_specs[pn])} for pn, a in cust_props.items()
                     if len(cust_props_specs[pn]) >= MIN_SPECS_NAME}
    dump("custom_props_common.json", {"n_custom_event_prop_lists": cust_n, "n_custom_props_per_event": qs(nprops_custom),
                                      "properties": common_custom})
    dump("dollar_props_any.json", {pn: a.out(1) for pn, a in dollar_any.items() if a.n >= 2})
    shape_out = {}
    for sh in set(shape_types) | set(shape_vclass):
        shape_out[sh] = {"types": dict(shape_types[sh]), "numeric": qs(shape_nums.get(sh, [])),
                         "value_classes": dict(shape_vclass[sh])}
    dump("name_shape_priors.json", shape_out)
    common_person = {pn: a.out(person_n) for pn, a in person.items()
                     if pn.startswith("$") or len(person_custom_specs[pn]) >= MIN_SPECS_NAME}
    dump("person_props.json", {"n_specs": person_n, "properties": common_person})
    dump("session_props.json", {"n_specs": session_n, "properties": {pn: a.out(session_n) for pn, a in session.items()
                                                                       if pn.startswith("$")}})
    dump("group_props.json", {pn: a.out(1) for pn, a in group_props.items() if a.n >= MIN_SPECS_VALUE})
    generic = {n: {"n_specs": custom_event_specs[n], "n_tz_families": len(fams)}
               for n, fams in custom_event_names.items() if len(fams) >= 3 and custom_event_specs[n] >= 20}
    log = lambda xs: [math.log10(x) for x in xs if x > 0]
    vol = {
        "event_daily_total": {k: qs(v) for k, v in ev_daily.items() if len(v) >= 3},
        "event_daily_dau": {k: qs(v) for k, v in ev_dau.items() if len(v) >= 3},
        "event_total_per_dau": {k: qs(v) for k, v in ev_per_dau.items() if len(v) >= 3},
        "std_rel_to_pageview": {k: qs(v) for k, v in rel_to_pv.items() if len(v) >= 3},
        "custom_rel_to_pageview": qs(custom_rel_to_pv),
        "project_dau": qs(proj_dau), "project_dau_log10": qs(log(proj_dau)),
        "project_daily_total": qs(proj_total), "project_daily_total_log10": qs(log(proj_total)),
        "persons_per_dau": qs(persons_ratio),
        "active_events_per_project": qs(proj_nevents_active), "active_custom_events_per_project": qs(proj_custom_active),
        "required_history_days": qs([h for h in hist_req if h]),
        "event_activity": {k: dict(v) for k, v in ev_nsd.items() if sum(v.values()) >= 20},
    }
    dump("volume.json", vol)
    ret_out = {}
    for unit, by in retention.items():
        ret_out[unit] = {str(i): {"mean": sum(v) / len(v), "median": sorted(v)[len(v) // 2], "n": len(v)}
                         for i, v in sorted(by.items()) if len(v) >= 3}
    dump("funnel_retention.json", {"funnel_step_conversion": {str(k): qs(v) for k, v in funnel_conv.items()},
                                   "funnel_median_conversion_seconds": qs(funnel_time), "retention": ret_out})
    now_sorted = sorted(now_list)
    dump("project.json", {"default_now_utc_epoch": now_sorted[len(now_sorted) // 2] if now_sorted else None,
                          "n_specs": len(files), "generic_custom_events": generic,
                          "objects_per_spec": {k: qs(v) for k, v in obj_counts.items()}})
    dump("warehouse.json", {"n_specs": wh_n, "field_types": dict(wh_field_types),
                            "field_type_by_name": {n: dict(c) for n, c in wh_fields_by_name.items()
                                                   if sum(c.values()) >= MIN_SPECS_NAME}})
    print("specs", len(files), "std events with priors", len(std_out), "common custom props", len(common_custom),
          "person props", len(common_person), "generic custom events", len(generic))
    print("volume points: project_dau", len(proj_dau), "project_total", len(proj_total), "funnel steps",
          sum(len(v) for v in funnel_conv.values()), "retention units", {u: len(b) for u, b in retention.items()})


if __name__ == "__main__":
    main()
