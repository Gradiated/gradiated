"""Side-by-side fidelity metrics of two replays of production reads (v1 /tmp/fid vs v2 /tmp/fid2). Stdlib.

    python3 fidelity_compare.py /tmp/fid /tmp/fid2 [--anoncheck DIR]
Prints aggregates only.
"""

from __future__ import annotations

import json
import os
import re
import statistics as S
import sys

JOIN = re.compile(r"\bJOIN\b", re.I)


def num(x):
    try:
        return float(str(x).replace(",", ""))
    except Exception:  # noqa: BLE001
        return None


def load(d):
    rs = [json.loads(l) for l in open(os.path.join(d, "replay.jsonl"))]
    ri = [json.loads(l) for l in open(os.path.join(d, "replay_ins.jsonl"))] if os.path.exists(os.path.join(d, "replay_ins.jsonl")) else []
    calls = {}
    for l in open(os.path.join(d, "calls.jsonl")):
        c = json.loads(l)
        calls[(c["cid"], c["k"])] = c
    return rs, ri, calls


def metrics(d, corrupted_fn):
    rs, ri, calls = load(d)
    m = {}
    sql = [r for r in rs if r["tool"] == "execute_sql" and "shifted" in r and r["err_kind"] is None and r["n_rows"] is not None]
    q = {id(r): (calls.get((r["cid"], r["k"])) or {}).get("input", {}).get("query") or "" for r in sql}
    cor = {id(r): corrupted_fn(q[id(r)]) for r in sql}
    ne = lambda r: r["shifted"]["ok"] and r["shifted"]["n"] > 0 and not (  # noqa: E731
        r["shifted"]["n"] == 1 and all(str(x) in ("0", "None", "nan", "[]", "", "0.0") for x in r["shifted"]["rows"][0]))
    m["sql_prod_ok"] = len(sql)
    m["sql_runs"] = sum(r["shifted"]["ok"] for r in sql)
    m["sql_nonempty"] = sum(ne(r) for r in sql)
    clean = [r for r in sql if not cor[id(r)]]
    m["sql_uncorrupted"] = len(clean)
    m["sql_uncorrupted_runs"] = sum(r["shifted"]["ok"] for r in clean)
    m["sql_uncorrupted_nonempty"] = sum(ne(r) for r in clean)
    joins = [r for r in clean if JOIN.search(q[id(r)])]
    m["join_queries"] = len(joins)
    m["join_nonempty"] = sum(ne(r) for r in joins)
    dw = [r for r in clean if (r.get("ents") or {}).get("dw")]
    m["dw_queries"] = len(dw)
    m["dw_runs"] = sum(r["shifted"]["ok"] for r in dw)
    m["dw_nonempty"] = sum(ne(r) for r in dw)
    absd = [r for r in clean if r.get("has_abs_date")]
    m["abs_date_queries"] = len(absd)
    m["abs_date_nonempty"] = sum(ne(r) for r in absd)
    # numbers: single-row numeric results, all numeric cells
    ratios = []
    for r in clean:
        sh = r["shifted"]
        pr = r.get("prod_rows") or []
        if not (sh["ok"] and len(pr) == 1 and sh["n"] == 1 and len(pr[0]) == len(sh["rows"][0])):
            continue
        for a, b in zip(pr[0], sh["rows"][0]):
            a, b = num(a), num(b)
            if a is not None and b is not None and a > 0:
                ratios.append(b / a)
    m["single_row_numbers"] = len(ratios)
    m["single_row_within_3x"] = sum(1 for x in ratios if 1 / 3 <= x <= 3)
    m["single_row_ratio_median"] = round(S.median(ratios), 3) if ratios else None
    # insights: totals
    ir = []
    for r in ri:
        sh = r.get("shifted") or {}
        if not sh.get("ok") or r.get("err_kind"):
            continue
        pt = sum(v for row in r.get("prod_rows") or [] for v in (num(x) for x in row[1:]) if v is not None)
        if pt > 0:
            ir.append((sh.get("total") or 0) / pt)
    m["insights_with_prod_total"] = len(ir)
    m["insights_nonzero"] = sum(1 for x in ir if x > 0)
    m["insights_within_3x"] = sum(1 for x in ir if 1 / 3 <= x <= 3)
    m["insight_ratio_median"] = round(S.median(ir), 3) if ir else None
    # objects
    rd = [r for r in rs if r["tool"] == "read_data" and "exists" in r and not r.get("err_kind")]
    for k in ("insight", "notebook", "dashboard", "feature_flag", "error_tracking_issue"):
        v = [r for r in rd if r.get("kind") == k]
        m[f"obj_{k}"] = f"{sum(r['exists'] for r in v)}/{len(v)}"
    m["objects_found"] = f"{sum(r['exists'] for r in rd)}/{len(rd)}"
    return m


def main():
    a, b = sys.argv[1], sys.argv[2]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import anoncheck

        voc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anoncheck_vocab.json")
        if os.path.exists(voc):
            anoncheck.load_vocab(voc)
        cf = lambda s: bool(anoncheck.analyze_sql(s).get("corrupted"))  # noqa: E731
    except Exception:  # noqa: BLE001
        cf = lambda s: False  # noqa: E731
    ma, mb = metrics(a, cf), metrics(b, cf)
    w = max(len(k) for k in ma)
    print(f"{'metric':<{w}}  {'v1':>14}  {'v2':>14}")
    for k in ma:
        print(f"{k:<{w}}  {str(ma[k]):>14}  {str(mb.get(k)):>14}")


if __name__ == "__main__":
    main()
