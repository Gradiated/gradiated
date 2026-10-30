"""Load all v2 twins of a group, a few at a time (PostHog venv). Resumable: skips twins already in teams_v2.jsonl.

    cd /opt/posthog-env/posthog
    nohup .venv/bin/python ../loader/load_all_v2.py --group test_v2 --workers 3 > ../loader/logs/load_all_v2.out 2>&1 &

Pauses launching while free disk < --min-free-gb. Logs per twin under loader/logs/twins_v2/. Prints aggregates only.
"""
import argparse, concurrent.futures as cf, json, os, shutil, subprocess, sys, time

sys.path.insert(0, "/opt/posthog-env/loader")
sys.path.insert(0, "/opt/posthog-sft/env-research/twingen/v2")
import paths as PATHS  # noqa: E402
LOADER = "/opt/posthog-env/loader"
PROJ = PATHS.PROJECTS


def done_ids():
    out = set()
    p = PATHS.TEAMS
    if os.path.exists(p):
        for l in open(p):
            r = json.loads(l)
            (out.discard if r.get("removed") else out.add)(r.get("twin_id"))
    return out


def one(tid, force):
    os.makedirs(f"{LOADER}/logs/twins_v2", exist_ok=True)
    cmd = [sys.executable, f"{LOADER}/load_twin_v2.py", tid] + (["--replace"] if force else [])
    t = time.time()
    for attempt in range(4):  # ClickHouse is shared: back off and retry when the server is at its memory cap
        logp = f"{LOADER}/logs/twins_v2/{tid}.log"
        with open(logp, "w") as log:
            r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd="/opt/posthog-env/posthog")
        if r.returncode == 0 or "MEMORY_LIMIT_EXCEEDED" not in open(logp, errors="replace").read():
            break
        time.sleep(120 * (attempt + 1))
    return tid, r.returncode, round(time.time() - t, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="test_v2")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--min-free-gb", type=float, default=120)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--ids")
    a = ap.parse_args()
    tg = [json.loads(l) for l in open(PATHS.TARGETS)]
    ids = a.ids.split(",") if a.ids else [t["id"] for t in tg if t.get("reason") == a.group]
    ids = [i for i in ids if os.path.exists(f"{PROJ}/{i}/manifest.json")]
    if not a.force:
        d = done_ids()
        ids = [i for i in ids if i not in d]
    ids.sort(key=lambda i: json.load(open(f"{PROJ}/{i}/manifest.json"))["counts"]["events"])
    ok = fail = 0
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = []
        for i in ids:
            while shutil.disk_usage("/").free / 1e9 < a.min_free_gb:
                print("low disk, waiting", flush=True); time.sleep(60)
            futs.append(ex.submit(one, i, a.force))
            while sum(not f.done() for f in futs) >= a.workers:
                time.sleep(1)
        for f in cf.as_completed(futs):
            tid, rc, t = f.result()
            ok += rc == 0; fail += rc != 0
            if rc:
                print("FAIL", tid, flush=True)
    print(json.dumps({"loaded": ok, "failed": fail}), flush=True)


if __name__ == "__main__":
    main()
