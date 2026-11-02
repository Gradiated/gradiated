#!/usr/bin/env python3
"""Asynchronous environment-iteration loop, producer side (runs on fbf8, system python).

Keeps building small random batches of tasks with the current builder/generator code while earlier batches are being
reviewed. Per batch: sample conversations from the pool (default: train; test_v2 stays held out), qfacts, generate,
load, build tasks (build_tasks_v3, excluded tasks kept and marked), write spot-check cards for every task (included,
truncated and excluded, so reviewers also judge what the builder threw away), run the frontier pilot (bench_env.py,
k=1) on the included tasks, then mark the batch READY. Batches carry the code version (sha of the scripts).

    python3 loop_producer.py --setup                 # once: specs/targets/facts/xindex for the loop root
    python3 loop_producer.py --batches 20 --n 10     # producer loop (stops at --batches or when STOP exists)
    python3 loop_producer.py --batches 1 --n 40 --name b14   # one acceptance round; may overlap a running round
    python3 loop_producer.py --rebuild-ids a,b --name fixcheck1   # rebuild given conversations with current code

Pacing: at most --max-ahead batches that are READY but not yet REVIEWED (reviewers touch <batch>/REVIEWED).
Layout: /opt/posthog-sft/env-research/twins_loop/batches/b<NN>/{ids.json, version.json, cards/, log.txt, READY}.
Prints counts only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import random
import subprocess
import sys
import time

ROOT = "/opt/posthog-sft/env-research/twins_loop"
TRACES = "/opt/posthog-sft/env-research/twins_reanon/traces"
TAG = "loop"
V2 = "/opt/posthog-sft/env-research/twingen/v2"
TG = "/opt/posthog-sft/env-research/twingen"
PH = "/opt/posthog-env/posthog"
RUNNER = "/opt/posthog-env/runner"
BATCHES = f"{ROOT}/batches"
CODE = [f"{V2}/gen2.py", f"{V2}/lint.py", f"{V2}/valuepools.py", f"{TG}/gen.py", f"{V2}/facts.py", f"{V2}/qfacts.py",
        f"{RUNNER}/build_tasks_v3.py",
        f"{RUNNER}/curate_tasks.py", f"{RUNNER}/apply_overrides.py", f"{RUNNER}/validate_tasks.py",
        "/opt/posthog-env/loader/load_twin_v2.py", f"{RUNNER}/spot_card.py"]
# 3M events per twin: peak worker memory ~27 GB instead of ~55 GB at 6M, so more twins fit under ClickHouse's cap
MAX_EVENTS = "3000000"
# generators run in their own cgroup (twingen, 400 GiB), outside ClickHouse's: 12 workers x ~27 GB peak fits
GEN_WORKERS = "12"
# second acceptance gate: the independent auditor (Opus) re-checks every task the validator passed (rounds 6-10:
# the validator passed all audited tasks, auditors found 23-47% with defects)
GATE_MODEL = "claude-opus-5-5"
ENV = {**os.environ, "TWIN_V2_TRACES": TRACES, "TWIN_V2_ROOT": ROOT, "TWIN_V2_TAG": TAG}


def sh(cmd: list[str], log, cwd: str | None = None, timeout: float = 7200) -> int:
    log.write(f"\n$ {' '.join(cmd)[:300]}\n")
    log.flush()
    p = subprocess.run(cmd, cwd=cwd, env=ENV, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    log.write(f"[rc={p.returncode}]\n")
    log.flush()
    p.check_returncode()
    return p.returncode


def version() -> dict:
    v = {}
    for f in CODE:
        try:
            v[os.path.basename(f)] = hashlib.sha256(open(f, "rb").read()).hexdigest()[:10]
        except OSError:
            v[os.path.basename(f)] = None
    v["combined"] = hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()[:10]
    return v


def setup() -> None:
    os.makedirs(BATCHES, exist_ok=True)
    with open(f"{ROOT}/setup.log", "a") as log:
        sh(["python3", "-I", f"{V2}/build_specs.py", "--splits", "train,dev"], log)
        sh(["python3", "-I", f"{V2}/facts.py", "--splits", "train,dev"], log)
        sh(["python3", "-I", f"{V2}/xindex.py", "--splits", "train,dev"], log)
    with open(f"{ROOT}/twingen/targets.jsonl") as targets:
        print(json.dumps({"setup": "ok", "targets": sum(1 for _ in targets)}))


HOLDOUT = f"{ROOT}/eval_holdout.json"  # train-split conversations reserved for eval (whole project clusters)


def seen_ids() -> set[str]:
    s = set()
    for f in glob.glob(f"{BATCHES}/*/ids.json"):
        s |= set(json.load(open(f)))
    if os.path.exists(HOLDOUT):  # never train on the eval holdout
        s |= set(json.load(open(HOLDOUT))["ids"])
    return s


def tool_calls() -> dict:
    return {json.loads(x)["conversation_id"]: json.loads(x).get("n_tool_calls") or 0 for x in open(f"{ROOT}/twins/index.jsonl")}


def hard_first(pool: list[str], rng) -> list[str]:
    """Order conversations so complex ones (more production tool calls) come first: easy conversations give mostly
    trivial tasks (0-2 tool calls: 80% of sound tasks trivial; 11+: 97% moderate/hard). Weighted shuffle by band."""
    tc = tool_calls()
    w = lambda n: 0.3 if n <= 2 else 1.0 if n <= 5 else 1.5 if n <= 10 else 2.0
    keyed = [(rng.random() ** (1.0 / w(tc.get(c, 0))), c) for c in pool]
    return [c for _, c in sorted(keyed, reverse=True)]


def make_holdout(n: int, seed: int) -> None:
    """Reserve ~n unseen train conversations for eval, by whole cluster (same customer project), stratified toward
    moderate/hard: band shares 0-2 15%, 3-5 35%, 6-10 25%, 11+ 25%."""
    if os.path.exists(HOLDOUT):
        print(json.dumps({"holdout": "exists"}))
        return
    rng = random.Random(seed)
    tc = tool_calls()
    seen = seen_ids()
    pool = [json.loads(x)["id"] for x in open(f"{TRACES}/train.jsonl")]
    group: dict = {c: c for c in pool}
    cf = f"{ROOT}/twins/clusters/clusters.jsonl"
    if os.path.exists(cf):
        for line in open(cf):
            m = json.loads(line).get("members") or []
            for c in m:
                group[c] = m[0]
    members: dict = {}
    for c in pool:
        members.setdefault(group.get(c, c), []).append(c)
    groups = [g for g, ms in members.items() if not any(m in seen for m in ms)]
    band = lambda c: "0-2" if tc.get(c, 0) <= 2 else "3-5" if tc.get(c, 0) <= 5 else "6-10" if tc.get(c, 0) <= 10 else "11+"
    quota = {"0-2": 0.15 * n, "3-5": 0.35 * n, "6-10": 0.25 * n, "11+": 0.25 * n}
    rng.shuffle(groups)
    got: list[str] = []
    have = {k: 0 for k in quota}
    for g in groups:
        ms = members[g]
        b = band(ms[0])
        if have[b] + len(ms) > quota[b] + 2:
            continue
        got += ms
        have[b] += len(ms)
        if len(got) >= n:
            break
    json.dump({"ids": got, "bands": have, "seed": seed}, open(HOLDOUT, "w"), indent=1)
    print(json.dumps({"holdout": len(got), "bands": have}))


def pending() -> int:
    return sum(1 for d in glob.glob(f"{BATCHES}/*/") if os.path.exists(f"{d}READY") and not os.path.exists(f"{d}REVIEWED"))


REGISTRY = f"/opt/posthog-env/loader/teams_v2_{TAG}.jsonl"


def shift_dates_deep(x, days: int):
    """Shift ISO dates in every string of a JSON value by `days` (build_tasks_v3.shift_text: month starts in monthly
    contexts are kept)."""
    sys.path.insert(0, RUNNER)
    import build_tasks_v3 as BT  # noqa: E402

    if isinstance(x, str):
        return BT.shift_text(x, days, dt.date.today())[0]
    if isinstance(x, list):
        return [shift_dates_deep(v, days) for v in x]
    if isinstance(x, dict):
        return {k: shift_dates_deep(v, days) for k, v in x.items()}
    return x


def reanchor(path: str, log) -> None:
    """Reload a task set's twins so their data ends 'now' again (twins are not re-anchored at run time: relative windows
    drift as days pass), then refresh team ids and shift the tasks' text dates with the data."""
    tasks = [json.loads(x) for x in open(path) if x.strip()]
    ids = sorted({t["twin_id"] for t in tasks})
    sh([f"{PH}/.venv/bin/python", "../loader/load_all_v2.py", "--ids", ",".join(ids), "--workers", "2", "--force",
        "--min-free-gb", "60"], log, cwd=PH)
    refresh_teams(path, log)


def refresh_teams(path: str, log=None) -> int:
    """A forced reload creates a NEW team and marks the old one replaced, but task files kept the old team_id, so the
    validator, audits and benches read the pre-override data (round 6: all 20 override-regenerated twins). Rewrites
    team_id/project_id/loaded_now_utc/shift_days (and /project/<id>/ in text) from the loader registry."""
    latest: dict = {}
    for line in open(REGISTRY):
        r = json.loads(line)
        if r.get("removed") or not r.get("twin_id") or not r.get("team_id"):
            continue
        latest[r["twin_id"]] = r
    tasks = [json.loads(x) for x in open(path) if x.strip()]
    n = 0
    for t in tasks:
        r = latest.get(t.get("twin_id"))
        if not r or int(r["team_id"]) == int(t.get("team_id") or 0):
            continue
        old_p, new_p = t.get("project_id"), r.get("project_id") or r["team_id"]
        delta = int(r.get("shift_days") or 0) - int(t.get("shift_days") or 0)
        for k in ("turns", "turns_built", "grading_notes"):
            if k in t and t[k] is not None:
                t[k] = json.loads(json.dumps(t[k], ensure_ascii=False).replace(f"/project/{old_p}/", f"/project/{new_p}/"))
                if delta:  # re-anchored twin: the text's dates move with the data (clock pinning)
                    t[k] = shift_dates_deep(t[k], delta)
        t.update({"team_id": int(r["team_id"]), "project_id": int(new_p), "loaded_now_utc": r.get("loaded_now_utc"),
                  "shift_days": r.get("shift_days", t.get("shift_days"))})
        n += 1
    with open(path + ".tmp", "w") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    os.replace(path + ".tmp", path)
    if log:
        log.write(f"teams refreshed: {n} tasks in {os.path.basename(path)}\n")
    return n


def regen_pending(d: str, ids: list[str], split: str, log) -> None:
    """Validator repairs may add twin_overrides (round 6: 28 of 29 repair drops were twin gaps the curator was not
    allowed to fix). Apply them, regenerate + reload the twins, refresh team ids, then validate the pending tasks
    again (one repair round, no further regeneration) and merge the verdicts into validated.jsonl."""
    vf = f"{d}/validated/validated.jsonl"
    tasks = [json.loads(x) for x in open(vf) if x.strip()]
    pend = [t for t in tasks if (t.get("validation") or {}).get("verdict") == "PENDING_REGEN" or t.get("pending_regen")]
    if not pend:
        return
    changed = set()
    for od in sorted(glob.glob(f"{d}/validated/rev*/overrides") + glob.glob(f"{d}/validated/regen*/rev*/overrides")
                     + glob.glob(f"{d}/validated/gate_rev/overrides") + glob.glob(f"{d}/validated/regen*/gate_rev/overrides")):
        ch = subprocess.run(["python3", f"{RUNNER}/apply_overrides.py", "--overrides-dir", od, "--root", ROOT], env=ENV,
                            capture_output=True, text=True, check=True, timeout=7200).stdout.strip()
        changed |= {x for x in ch.split(",") if x}
    log.write(f"regen_pending: {len(pend)} tasks, twins changed: {len(changed)}\n")
    if changed:
        csv = ",".join(sorted(changed))
        sh([f"{TG}/.venv/bin/python", f"{V2}/run_all2.py", "--ids", csv, "--workers", GEN_WORKERS, "--max-events", MAX_EVENTS], log)
        sh([f"{PH}/.venv/bin/python", "../loader/load_all_v2.py", "--ids", csv, "--workers", "2", "--force",
            "--min-free-gb", "60"], log, cwd=PH)
        lint(ids, d, log)
    pf = f"{d}/validated/pending.jsonl"
    with open(pf, "w") as f:
        for t in pend:
            t = {k: v for k, v in t.items() if k not in ("exclude", "validation", "pending_regen")}
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    refresh_teams(pf, log)
    refresh_teams(vf, log)
    out = f"{d}/validated/regen{len(glob.glob(f'{d}/validated/regen*/')) + 1}"  # fresh dir: no cached verdicts
    sh(["python3", f"{RUNNER}/validate_tasks.py", "--tasks", pf, "--traces", f"{TRACES}/{split}.jsonl",
        "--out", out, "--repair", "--repair-rounds", "1", "--lint", f"{d}/lint.jsonl",
        "--workers", "8", "--gate-model", GATE_MODEL], log, timeout=7200)
    got = {json.loads(x)["task_id"]: json.loads(x) for x in open(f"{out}/validated.jsonl") if x.strip()}
    for t in got.values():  # a second PENDING_REGEN is not regenerated again
        if (t.get("validation") or {}).get("verdict") == "PENDING_REGEN":
            t["exclude"] = "validator: pending regeneration after second repair"
    tasks = [got.get(t["task_id"], t) for t in [json.loads(x) for x in open(vf) if x.strip()]]
    with open(vf, "w") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    log.write(f"regen_pending: merged {len(got)} re-validated tasks\n")


def lint(ids: list[str], d: str, log) -> None:
    """twingen/v2/lint.py on every generated twin of the batch -> <batch>/lint.jsonl (read by the validator)."""
    dirs = [p for i in ids for p in glob.glob(f"{ROOT}/twingen/projects_v2/{i}*") if os.path.exists(f"{p}/events.parquet")]
    if not dirs:
        return
    r = subprocess.run([f"{TG}/.venv/bin/python", f"{V2}/lint.py", *dirs], env=ENV, capture_output=True, text=True,
                       check=True, timeout=7200)
    open(f"{d}/lint.jsonl", "w").write(r.stdout)
    rows = [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
    log.write(f"lint: {sum(1 for x in rows if any(f['severity'] == 'material' for f in x.get('findings') or []))}"
              f"/{len(rows)} twins with material findings\n")


def build_batch(name: str, ids: list[str], split: str, pilot: bool) -> None:
    d = f"{BATCHES}/{name}"
    os.makedirs(d, exist_ok=True)
    # A rebuild is not ready merely because an older attempt published this marker.
    try:
        os.unlink(f"{d}/READY")
    except FileNotFoundError:
        pass
    with open(f"{d}/ids.json", "w") as ids_file:
        json.dump(ids, ids_file)
    ver = version()
    with open(f"{d}/version.json", "w") as version_file:
        json.dump(ver, version_file)
    t0 = time.time()
    csv = ",".join(ids)
    with open(f"{d}/log.txt", "a") as log:
        sh([f"{PH}/.venv/bin/python", f"{V2}/qfacts.py", "--split", split, "--ids", csv], log, cwd=PH)
        # run_all2 moves into the twingen cgroup (ClickHouse does not count it); else its memory gate applies
        sh([f"{TG}/.venv/bin/python", f"{V2}/run_all2.py", "--ids", csv, "--workers", GEN_WORKERS, "--max-events", MAX_EVENTS], log)
        sh([f"{PH}/.venv/bin/python", "../loader/load_all_v2.py", "--ids", csv, "--workers", "2", "--force",
            "--min-free-gb", "60"], log, cwd=PH)
        lint(ids, d, log)
        sh(["python3", f"{RUNNER}/build_tasks_v3.py", "--splits", split, "--ids", csv, "--out", f"{d}/tasks"], log)
        tf = f"{d}/tasks/{'test' if split == 'test_v2' else split}.jsonl"
        if not os.path.exists(tf):
            raise FileNotFoundError(f"Task construction produced no task file: {tf}")
        # curation: LLM editor (edit/drop, grading notes, twin overrides), then regenerate + reload changed twins
        sh(["python3", f"{RUNNER}/curate_tasks.py", "--tasks", tf, "--traces", f"{TRACES}/{split}.jsonl",
            "--out", f"{d}/curated", "--include-excluded", "--workers", "8"], log, timeout=7200)
        if not os.path.exists(f"{d}/curated/curated.jsonl"):
            raise FileNotFoundError("Curation produced no curated task file")
        if os.path.exists(f"{d}/curated/curated.jsonl"):
            ch = subprocess.run(["python3", f"{RUNNER}/apply_overrides.py", "--overrides-dir", f"{d}/curated/overrides",
                                 "--root", ROOT], env=ENV, capture_output=True, text=True, check=True, timeout=7200).stdout.strip()
            log.write(f"overrides changed: {ch}\n")
            if ch:
                sh([f"{TG}/.venv/bin/python", f"{V2}/run_all2.py", "--ids", ch, "--workers", GEN_WORKERS, "--max-events", MAX_EVENTS], log)
                sh([f"{PH}/.venv/bin/python", "../loader/load_all_v2.py", "--ids", ch, "--workers", "2", "--force",
                    "--min-free-gb", "60"], log, cwd=PH)
                lint(ids, d, log)
            tf = f"{d}/curated/curated.jsonl"
            refresh_teams(tf, log)  # reloads create new teams
            # independent validator (GPT-6.1 Sol, read-only twin queries) with one curator repair round; only SOUND kept
            sh(["python3", f"{RUNNER}/validate_tasks.py", "--tasks", tf, "--traces", f"{TRACES}/{split}.jsonl",
                "--out", f"{d}/validated", "--repair", "--lint", f"{d}/lint.jsonl", "--workers", "8", "--gate-model", GATE_MODEL], log,
               timeout=10800)
            if not os.path.exists(f"{d}/validated/validated.jsonl"):
                raise FileNotFoundError("Validation produced no validated task file")
            if os.path.exists(f"{d}/validated/validated.jsonl"):
                tf = f"{d}/validated/validated.jsonl"
                for _ in range(2):  # repairs that add data need regeneration; one pass rarely converges (round 8/9)
                    regen_pending(d, ids, split, log)
        with open(tf) as task_file:
            tasks = [json.loads(x) for x in task_file]
        inc = [t for t in tasks if not t.get("exclude")]
        with open(f"{d}/included.json", "w") as included_file:
            json.dump([t["task_id"] for t in inc], included_file)
        sh(["python3", f"{RUNNER}/spot_card.py", "--tasks", tf, "--traces", f"{TRACES}/{split}.jsonl",
            "--status", "/nonexistent", "--out", f"{d}/cards", "--sample", "1000", "--seed", "0"], log)
        if pilot and inc:
            sh(["python3", f"{RUNNER}/bench_env.py", "--tag", f"loop_{name}_{ver['combined']}", "--tasks", tf,
                "--task-ids-file", f"{d}/included.json", "--arms", "gpt-luna,gpt-terra,haiku55", "--samples", "1",
                "--max-turns", "12", "--wall-s", "1500",
                "--workers", "15", "--api-concurrency", "5", "--judge-workers", "6"], log, timeout=10800)
    with open(f"{d}/READY.tmp", "w") as ready:
        ready.write(json.dumps({"tasks": len(tasks), "included": len(inc), "s": round(time.time() - t0)}))
    os.replace(f"{d}/READY.tmp", f"{d}/READY")
    print(json.dumps({"batch": name, "tasks": len(tasks), "included": len(inc), "s": round(time.time() - t0)}), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--batches", type=int, default=20)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--split", default="train")
    ap.add_argument("--seed", type=int, default=1030)
    ap.add_argument("--max-ahead", type=int, default=2)
    ap.add_argument("--pilot", action="store_true", help="frontier pilot bench after validation (off: acceptance "
                    "rounds only need the audit; benches also compete for ClickHouse)")
    ap.add_argument("--rebuild-ids", default="")
    ap.add_argument("--refresh-teams", default="", help="rewrite team ids in a task file from the loader registry")
    ap.add_argument("--regen-pending", default="", help="batch name: regenerate + re-validate PENDING_REGEN tasks")
    ap.add_argument("--hard-first", action="store_true", help="sample complex conversations first (see hard_first)")
    ap.add_argument("--make-holdout", type=int, default=0, help="reserve N train conversations for eval (by cluster)")
    ap.add_argument("--reanchor", default="", help="task file: reload its twins to now and refresh ids/dates")
    ap.add_argument("--name", default="")
    a = ap.parse_args()
    if a.setup:
        setup()
        return
    if a.make_holdout:
        make_holdout(a.make_holdout, a.seed)
        return
    if a.reanchor:
        with open(a.reanchor + ".reanchor.log", "a") as log:
            reanchor(a.reanchor, log)
        return
    if a.regen_pending:
        d = f"{BATCHES}/{a.regen_pending}"
        with open(f"{d}/log.txt", "a") as log:
            regen_pending(d, json.load(open(f"{d}/ids.json")), a.split, log)
        return
    if a.refresh_teams:
        print(json.dumps({"refreshed": refresh_teams(a.refresh_teams)}))
        return
    if a.rebuild_ids:
        build_batch(a.name or f"fix_{int(time.time())}", a.rebuild_ids.split(","), a.split, a.pilot)
        return
    pool = sorted(json.loads(x)["id"] for x in open(f"{TRACES}/{a.split}.jsonl"))
    rng = random.Random(a.seed)
    rng.shuffle(pool)
    if a.hard_first:
        pool = hard_first(pool, rng)
    for _ in range(a.batches):
        if os.path.exists(f"{ROOT}/STOP"):
            break
        while pending() >= a.max_ahead and not os.path.exists(f"{ROOT}/STOP"):
            time.sleep(60)
        seen = seen_ids()
        ids = [i for i in pool if i not in seen][: a.n]
        if not ids:
            break
        k = 1 + len(glob.glob(f"{BATCHES}/b*/"))
        # --name lets rounds overlap (the next round generates while the previous one curates and validates)
        build_batch(a.name or f"b{k:02d}", ids, a.split, a.pilot)


if __name__ == "__main__":
    sys.exit(main())
