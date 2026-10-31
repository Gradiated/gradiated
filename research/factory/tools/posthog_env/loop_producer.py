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
ENV = {**os.environ, "TWIN_V2_TRACES": TRACES, "TWIN_V2_ROOT": ROOT, "TWIN_V2_TAG": TAG}


def sh(cmd: list[str], log, cwd: str | None = None, timeout: float = 7200) -> int:
    log.write(f"\n$ {' '.join(cmd)[:300]}\n")
    log.flush()
    p = subprocess.run(cmd, cwd=cwd, env=ENV, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    log.write(f"[rc={p.returncode}]\n")
    log.flush()
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
        assert sh(["python3", "-I", f"{V2}/build_specs.py", "--splits", "train,dev"], log) == 0
        assert sh(["python3", "-I", f"{V2}/facts.py", "--splits", "train,dev"], log) == 0
        assert sh(["python3", "-I", f"{V2}/xindex.py"], log) == 0
    print(json.dumps({"setup": "ok", "targets": sum(1 for _ in open(f"{ROOT}/twingen/targets.jsonl"))}))


def seen_ids() -> set[str]:
    s = set()
    for f in glob.glob(f"{BATCHES}/*/ids.json"):
        s |= set(json.load(open(f)))
    return s


def pending() -> int:
    return sum(1 for d in glob.glob(f"{BATCHES}/*/") if os.path.exists(f"{d}READY") and not os.path.exists(f"{d}REVIEWED"))


def lint(ids: list[str], d: str, log) -> None:
    """twingen/v2/lint.py on every generated twin of the batch -> <batch>/lint.jsonl (read by the validator)."""
    dirs = [p for i in ids for p in glob.glob(f"{ROOT}/twingen/projects_v2/{i}*") if os.path.exists(f"{p}/events.parquet")]
    if not dirs:
        return
    r = subprocess.run([f"{TG}/.venv/bin/python", f"{V2}/lint.py", *dirs], env=ENV, capture_output=True, text=True)
    open(f"{d}/lint.jsonl", "w").write(r.stdout)
    rows = [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
    log.write(f"lint: {sum(1 for x in rows if any(f['severity'] == 'material' for f in x.get('findings') or []))}"
              f"/{len(rows)} twins with material findings\n")


def build_batch(name: str, ids: list[str], split: str, pilot: bool) -> None:
    d = f"{BATCHES}/{name}"
    os.makedirs(d, exist_ok=True)
    json.dump(ids, open(f"{d}/ids.json", "w"))
    ver = version()
    json.dump(ver, open(f"{d}/version.json", "w"))
    t0 = time.time()
    csv = ",".join(ids)
    with open(f"{d}/log.txt", "a") as log:
        sh([f"{PH}/.venv/bin/python", f"{V2}/qfacts.py", "--split", split, "--ids", csv], log, cwd=PH)
        # 4 generator workers; run_all2's memory gate keeps ClickHouse's cgroup under its cap
        sh([f"{TG}/.venv/bin/python", f"{V2}/run_all2.py", "--ids", csv, "--workers", "4"], log)
        sh([f"{PH}/.venv/bin/python", "../loader/load_all_v2.py", "--ids", csv, "--workers", "2", "--force",
            "--min-free-gb", "60"], log, cwd=PH)
        lint(ids, d, log)
        sh(["python3", f"{RUNNER}/build_tasks_v3.py", "--splits", split, "--ids", csv, "--out", f"{d}/tasks"], log)
        tf = f"{d}/tasks/{'test' if split == 'test_v2' else split}.jsonl"
        if not os.path.exists(tf):
            log.write("no task file\n")
            open(f"{d}/READY", "w").write(json.dumps({"tasks": 0, "s": round(time.time() - t0)}))
            return
        # curation: LLM editor (edit/drop, grading notes, twin overrides), then regenerate + reload changed twins
        sh(["python3", f"{RUNNER}/curate_tasks.py", "--tasks", tf, "--traces", f"{TRACES}/{split}.jsonl",
            "--out", f"{d}/curated", "--include-excluded", "--workers", "8"], log, timeout=7200)
        if os.path.exists(f"{d}/curated/curated.jsonl"):
            ch = subprocess.run(["python3", f"{RUNNER}/apply_overrides.py", "--overrides-dir", f"{d}/curated/overrides",
                                 "--root", ROOT], env=ENV, capture_output=True, text=True).stdout.strip()
            log.write(f"overrides changed: {ch}\n")
            if ch:
                sh([f"{TG}/.venv/bin/python", f"{V2}/run_all2.py", "--ids", ch, "--workers", "4"], log)
                sh([f"{PH}/.venv/bin/python", "../loader/load_all_v2.py", "--ids", ch, "--workers", "2", "--force",
                    "--min-free-gb", "60"], log, cwd=PH)
                lint(ids, d, log)
            tf = f"{d}/curated/curated.jsonl"
            # independent validator (GPT-6.1 Sol, read-only twin queries) with one curator repair round; only SOUND kept
            sh(["python3", f"{RUNNER}/validate_tasks.py", "--tasks", tf, "--traces", f"{TRACES}/{split}.jsonl",
                "--out", f"{d}/validated", "--repair", "--lint", f"{d}/lint.jsonl", "--workers", "8"], log,
               timeout=10800)
            if os.path.exists(f"{d}/validated/validated.jsonl"):
                tf = f"{d}/validated/validated.jsonl"
        tasks = [json.loads(x) for x in open(tf)]
        inc = [t for t in tasks if not t.get("exclude")]
        json.dump([t["task_id"] for t in inc], open(f"{d}/included.json", "w"))
        sh(["python3", f"{RUNNER}/spot_card.py", "--tasks", tf, "--traces", f"{TRACES}/{split}.jsonl",
            "--status", "/nonexistent", "--out", f"{d}/cards", "--sample", "1000", "--seed", "0"], log)
        if pilot and inc:
            sh(["python3", f"{RUNNER}/bench_env.py", "--tag", f"loop_{name}_{ver['combined']}", "--tasks", tf,
                "--task-ids-file", f"{d}/included.json", "--arms", "gpt-luna,gpt-terra,haiku55", "--samples", "1",
                "--max-turns", "12", "--wall-s", "1500",
                "--workers", "15", "--api-concurrency", "5", "--judge-workers", "6"], log, timeout=10800)
    open(f"{d}/READY", "w").write(json.dumps({"tasks": len(tasks), "included": len(inc), "s": round(time.time() - t0)}))
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
    ap.add_argument("--name", default="")
    a = ap.parse_args()
    if a.setup:
        setup()
        return
    if a.rebuild_ids:
        build_batch(a.name or f"fix_{int(time.time())}", a.rebuild_ids.split(","), a.split, a.pilot)
        return
    pool = sorted(json.loads(x)["id"] for x in open(f"{TRACES}/{a.split}.jsonl"))
    rng = random.Random(a.seed)
    rng.shuffle(pool)
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
