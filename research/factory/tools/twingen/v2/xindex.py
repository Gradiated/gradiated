"""Cross-trace index of saved objects and warehouse schemas (stdlib), for same-customer completion in gen2.

A conversation often references a dashboard, notebook or warehouse table that only a sibling conversation of the
same customer actually read. This scans every trace split (train, dev, test_v2) and every spec, and keeps:
- dashboards by id (name, description, tiles with insight short id/name/query), insights and notebooks by short id
  (content from read_data results);
- warehouse tables by name: the richest field list seen (read_data data_warehouse_table/schema results, spec
  warehouse fields), with the number of conversations that showed it.
Names that are not distinctive (seen under several customers) are still indexed; gen2 only uses a table entry
when the conversation itself references that table, and an object only by its exact id.

    python3 -I xindex.py [--traces-dir DIR] [--out PATH]
Default out: /opt/posthog-sft/env-research/twins/xindex_v2.json. Prints aggregates only.
"""

from __future__ import annotations

import argparse
import collections as C
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/opt/posthog-sft/env-research/twins")
import facts as FX  # noqa: E402
import twinlib as T  # noqa: E402
import paths as PATHS  # noqa: E402

OUT = PATHS.XINDEX
SPECS = PATHS.SPECS


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--splits", default="train,dev,test_v2")
    a = ap.parse_args()
    dash, ins, nb = {}, {}, {}
    tables: dict = {}
    seen = C.defaultdict(set)
    st = C.Counter()
    for split in a.splits.split(","):
        files = PATHS.trace_files()
        if split not in files:
            continue
        with open(files[split], encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                rec = json.loads(line)
                f = FX.extract(rec)
                st[f"{split}_convs"] += 1
                o = f["objects"]
                for did, d in o["dashboards"].items():
                    if did and (did not in dash or len(d.get("tiles") or []) > len(dash[did].get("tiles") or [])):
                        dash[did] = {**d, "tiles": [{k: v for k, v in t.items() if k not in ("rows", "cols")} for t in d.get("tiles") or []]}
                for sid, i in o["insights"].items():
                    if sid and (sid not in ins or (i.get("query") and not ins[sid].get("query"))):
                        ins[sid] = {k: v for k, v in i.items() if k not in ("rows", "cols")}
                for sid, n in o["notebooks"].items():
                    if sid and (sid not in nb or len(n.get("content_markdown") or "") > len(nb[sid].get("content_markdown") or "")):
                        nb[sid] = n
                for c in f["calls"]:
                    for tn, fields in (c.get("dw") or {}).items():
                        fl = [x for x in fields or [] if isinstance(x, dict) and x.get("name")]
                        seen[tn].add(rec["id"])
                        if fl and len(fl) > len(tables.get(tn, {}).get("fields") or []):
                            tables[tn] = {"fields": [{"name": x["name"], "type": x.get("type")} for x in fl], "source": "read_data"}
    for p in glob.glob(os.path.join(SPECS, "*.json")):
        s = json.load(open(p))
        for tn, tb in ((s.get("warehouse") or {}).get("tables") or {}).items():
            fl = [x for x in tb.get("fields") or [] if x.get("name")]
            seen[tn].add(s.get("conversation_id"))
            if fl and len(fl) > len(tables.get(tn, {}).get("fields") or []):
                tables[tn] = {"fields": [{"name": x["name"], "type": x.get("type")} for x in fl], "source": "spec"}
    for tn in tables:
        tables[tn]["n_conversations"] = len(seen[tn])
    with open(a.out, "w") as fh:
        json.dump({"dashboards": dash, "insights": ins, "notebooks": nb, "tables": tables}, fh)
    st.update({"dashboards": len(dash), "insights": len(ins), "notebooks": len(nb), "tables": len(tables)})
    print(json.dumps(dict(st)))


if __name__ == "__main__":
    main()
