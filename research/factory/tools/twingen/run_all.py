"""Generate many projects in parallel.

Usage:
  run_all.py targets [--train-sample 500] [--seed 0]        -> writes targets.jsonl (spec paths + reasons)
  run_all.py run TARGETS_JSONL OUT_ROOT [--workers 24] [--max-events N] [--limit N]
Errors are reported as exception type + code location only (never messages, which may contain names).
"""
import argparse, json, os, random, sys, time, traceback, glob
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TWINS = "/opt/posthog-sft/env-research/twins"


def build_targets(train_sample, seed):
    idx = [json.loads(l) for l in open(f"{TWINS}/index.jsonl")]
    clusters = [json.loads(l) for l in open(f"{TWINS}/clusters/clusters.jsonl")]
    in_multi = set()
    out = []
    for c in clusters:
        if len(c["members"]) >= 2:
            out.append({"id": c["cluster_id"], "spec": f"{TWINS}/clusters/{c['cluster_id']}.json", "reason": "cluster"})
            in_multi.update(c["members"])
    for r in idx:
        if r["split"] in ("test_v2", "dev"):
            out.append({"id": r["conversation_id"], "spec": f"{TWINS}/{r['spec_file']}", "reason": r["split"]})
    singles = sorted(r["conversation_id"] for r in idx if r["split"] == "train" and r["conversation_id"] not in in_multi)
    rnd = random.Random(seed)
    by = {r["conversation_id"]: r for r in idx}
    for cid in rnd.sample(singles, min(train_sample, len(singles))):
        out.append({"id": cid, "spec": f"{TWINS}/{by[cid]['spec_file']}", "reason": "train_singleton"})
    return out


def job(args):
    t, out_root, max_events, seed = args
    import gen, specio
    t0 = time.time()
    try:
        spec = specio.load(t["spec"])
        man = gen.Project(spec, seed, None, max_events).run(os.path.join(out_root, t["id"]))
        return {"id": t["id"], "reason": t["reason"], "ok": True, "events": man["counts"]["events"],
                "persons": man["counts"]["persons"], "seconds": round(time.time() - t0, 2),
                "volume_scale": man["volume_scale"]}
    except Exception as ex:
        tb = traceback.extract_tb(ex.__traceback__)
        loc = [f"{os.path.basename(f.filename)}:{f.lineno}" for f in tb[-3:]]
        return {"id": t["id"], "reason": t["reason"], "ok": False, "error": type(ex).__name__, "where": loc,
                "seconds": round(time.time() - t0, 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--train-sample", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--max-events", type=int, default=5_000_000)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    if a.cmd == "targets":
        ts = build_targets(a.train_sample, a.seed)
        with open(a.args[0], "w") as fh:
            for t in ts:
                fh.write(json.dumps(t) + "\n")
        from collections import Counter
        print(json.dumps(Counter(t["reason"] for t in ts)))
        return
    targets = [json.loads(l) for l in open(a.args[0])]
    if a.limit:
        targets = targets[: a.limit]
    out_root = a.args[1]
    os.makedirs(out_root, exist_ok=True)
    log = open(os.path.join(out_root, "_run_log.jsonl"), "a")
    t0 = time.time()
    n_ok = n_err = ev = 0
    # big clusters first so the pool tail is short
    targets.sort(key=lambda t: -os.path.getsize(t["spec"]))
    with Pool(a.workers, maxtasksperchild=20) as pool:
        for r in pool.imap_unordered(job, [(t, out_root, a.max_events, a.seed) for t in targets]):
            log.write(json.dumps(r) + "\n"); log.flush()
            if r["ok"]:
                n_ok += 1; ev += r["events"]
            else:
                n_err += 1
    print(json.dumps({"ok": n_ok, "errors": n_err, "events": ev, "wall_s": round(time.time() - t0, 1)}))


if __name__ == "__main__":
    main()
