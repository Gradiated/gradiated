"""Generate v2 twin projects in parallel (twingen .venv).

    run_all2.py --reason test_v2 [--out projects_v2] [--workers 8] [--calib-dir DIR] [--ids a,b]

Targets come from ../targets.jsonl (same ids and specs as v1). Writes OUT/<id>/ and OUT/_run_log.jsonl.
With --calib-dir, DIR/<id>.json calibration multipliers are applied. Prints aggregates only.

Memory gate: ClickHouse on the host caps its memory at 128 GiB but counts all anonymous memory of its cgroup, which
includes generator workers; over the cap every agent tool call fails ("under heavy load"). Before generating, each
twin estimates its peak (MEM_PER_EVENT x planned events) and waits until cgroup anon + other workers' unfilled
reservations + its own estimate fit under TWINGEN_MEM_LIMIT_GB (default 105). Reservations are files in
/dev/shm/twingen_mem, shared by every run_all2 process (loop producer, regress, rebuilds).
"""

from __future__ import annotations

import argparse
import fcntl
import glob
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


MEM_DIR = "/dev/shm/twingen_mem"
MEM_PER_EVENT = 9_000  # bytes of peak worker RSS per generated event (measured: 43 GB at 5.4M events)
CH_PID_FILE = "/opt/posthog-env/run/clickhouse.pid"


def ch_cgroup() -> str | None:
    """memory.stat of ClickHouse's cgroup (what its memory limit counts), or None when not found."""
    p = os.environ.get("TWINGEN_CH_CGROUP")
    if not p:
        try:
            pid = open(CH_PID_FILE).read().strip()
            rel = open(f"/proc/{pid}/cgroup").read().strip().split("::", 1)[1]
            p = f"/sys/fs/cgroup{rel}"
        except (OSError, IndexError):
            return None
    return f"{p}/memory.stat" if os.path.exists(f"{p}/memory.stat") else None


def cgroup_anon(stat: str) -> int:
    for line in open(stat):
        if line.startswith("anon "):
            return int(line.split()[1])
    return 0


def rss(pid: int) -> int:
    try:
        for line in open(f"/proc/{pid}/status"):
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except OSError:
        return -1
    return 0


def reserve(est: int, log=print) -> str | None:
    """Block until est bytes fit under the limit; returns the reservation file (remove it when done)."""
    stat = ch_cgroup()
    if stat is None:
        return None
    limit = float(os.environ.get("TWINGEN_MEM_LIMIT_GB", "105")) * 2**30
    os.makedirs(MEM_DIR, exist_ok=True)
    me = f"{MEM_DIR}/{os.getpid()}.json"
    t0, waited = time.time(), False
    while True:
        with open(f"{MEM_DIR}/.lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            pending, others = 0, 0
            for f in glob.glob(f"{MEM_DIR}/*.json"):
                try:
                    r = json.load(open(f))
                except (OSError, ValueError):
                    continue
                cur = rss(r["pid"])
                if cur < 0:  # dead worker
                    os.remove(f)
                    continue
                others += 1
                pending += max(0, r["est"] - cur)
            anon = cgroup_anon(stat)
            if anon + pending + est <= limit or others == 0:
                json.dump({"pid": os.getpid(), "est": est, "t": time.time()}, open(me, "w"))
                if waited:
                    log(f"memgate: waited {time.time() - t0:.0f}s for {est / 2**30:.1f} GiB")
                return me
        waited = True
        time.sleep(15)


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
        planned = min(max_events, sum(x for x, _ in p.targets.values()) * p.H) if getattr(p, "targets", None) else max_events
        slot = reserve(int(planned * MEM_PER_EVENT) + 2 * 2**30)
        try:
            man = p.run(os.path.join(out_root, t["id"]))
        finally:
            if slot and os.path.exists(slot):
                os.remove(slot)
        return {"id": t["id"], "ok": True, "events": man["counts"]["events"], "planned": int(planned),
                "t": round(time.time() - t0, 1),
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
