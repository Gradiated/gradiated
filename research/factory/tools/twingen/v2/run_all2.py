"""Generate v2 twin projects in parallel (twingen .venv).

    run_all2.py --reason test_v2 [--out projects_v2] [--workers 8] [--calib-dir DIR] [--ids a,b]

Targets come from ../targets.jsonl (same ids and specs as v1). Writes OUT/<id>/ and OUT/_run_log.jsonl.
With --calib-dir, DIR/<id>.json calibration multipliers are applied. Prints aggregates only.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import paths as PATHS  # noqa: E402


def job(args):
    t, out_root, max_events, calib_dir = args
    import gen2
    import specio

    t0 = time.time()
    try:
        spec = specio.load(t["spec"])
        cid = spec["id"]
        facts = gen2.load_json(os.path.join(gen2.FACTS, f"{cid}.json"))
        qf = gen2.load_json(os.path.join(gen2.QFACTS, f"{cid}.json"))
        calib = gen2.load_json(os.path.join(calib_dir, f"{t['id']}.json")) if calib_dir else None
        members = [s for s in (gen2.load_json(os.path.join(gen2.SPECS, f"{m}.json")) for m in gen2.cluster_members(cid)) if s] \
            if spec["kind"] == "conversation" else []
        ovr = gen2.load_json(os.path.join(gen2.OVERRIDES, f"{t['id']}.json"))
        p = gen2.Project2(spec, facts=facts, qfacts=qf, calib=calib, member_specs=members, overrides=ovr, seed=0,
                          max_events=max_events)
        man = p.run(os.path.join(out_root, t["id"]))
        return {"id": t["id"], "ok": True, "events": man["counts"]["events"], "t": round(time.time() - t0, 1),
                "v2": {k: v for k, v in man["v2"].items() if isinstance(v, (int, float))}}
    except Exception as e:  # noqa: BLE001
        return {"id": t["id"], "ok": False, "err": f"{type(e).__name__}: {str(e)[:200]}",
                "tb": traceback.format_exc(limit=4)[-600:], "t": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reason", default="test_v2")
    ap.add_argument("--out", default=PATHS.PROJECTS)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-events", type=int, default=6_000_000)
    ap.add_argument("--calib-dir", default=None, help="calibration multipliers (e.g. PATHS.CALIB)")
    ap.add_argument("--ids")
    a = ap.parse_args()
    targets = [json.loads(l) for l in open(PATHS.TARGETS)]
    if a.ids:
        ids = set(a.ids.split(","))
        targets = [t for t in targets if t["id"] in ids]
    else:
        targets = [t for t in targets if t.get("reason") in a.reason.split(",")]
    os.makedirs(a.out, exist_ok=True)
    ok = fail = ev = 0
    with mp.get_context("spawn").Pool(a.workers) as pool, open(os.path.join(a.out, "_run_log.jsonl"), "a") as log:
        for r in pool.imap_unordered(job, [(t, a.out, a.max_events, a.calib_dir) for t in targets]):
            log.write(json.dumps(r) + "\n")
            log.flush()
            if r["ok"]:
                ok += 1
                ev += r["events"]
            else:
                fail += 1
                print("FAIL", r["id"], r["err"], flush=True)
    print(json.dumps({"targets": len(targets), "ok": ok, "failed": fail, "events": ev}), flush=True)


if __name__ == "__main__":
    main()
