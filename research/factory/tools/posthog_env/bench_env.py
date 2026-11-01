#!/usr/bin/env python3
"""Cross-model benchmark of the PostHog twin environment (runs on fbf8, system python).

Every arm is a runner model key (runner_common.MODELS: qwen, opus, sonnet55, gpt-sol, gpt-terra, gpt-luna, LoRA arms).
Each arm runs --samples rollouts per task through runner/run_task.py with --reset-team-state track; jobs are
interleaved sample -> task -> arm so drift hits every arm equally. vLLM arms share the replica port pool; API arms
(proxy) have their own concurrency cap. Each rollout is judged once with judge v3g (runner/judge_v3/judge_v3g.py,
docs-grounded; gpt-6.1-sol through the subscription proxy) in a separate pool; --judge v3h (default) also shows the
task's curation grading notes when it has them (identical to v3g otherwise). Resumable.

    python3 bench_env.py --tag reanon_b1 --tasks runner/tasks/v2_reanon/test.jsonl \
        --arms qwen,opus,sonnet55,gpt-sol,gpt-terra,gpt-luna --samples 3
    python3 bench_env.py ... --report-only

Layout: runner/bench/<tag>/<arm>/runs/<task>/r<k>.json, .../judge/<task>.s<k>.json, runner/bench/<tag>/report.json.
Prints counts and aggregates only (no task text).

Report: per arm mean of per-task means (95% t-interval), pass rate (overall >= 7.5 and no material wrong/unsupported
error in the final answer) with a Wilson interval, rollout status, cost and wall time; every pair of arms: paired
per-task difference with Wilcoxon and sign tests; ranking agreement with the expected capability order; per-task
difficulty bands (all arms pass / none pass / separating) and the share of tasks that separate the strongest from
the weakest arm.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import queue
import statistics
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

RUNNER = "/opt/posthog-env/runner"
PH = "/opt/posthog-env/posthog"
sys.path.insert(0, RUNNER)
import eval_ms as E  # noqa: E402  (statistics helpers; imports llm_proxy and turns the proxy default on)

sys.path.insert(0, f"{RUNNER}/judge_v3")
import importlib  # noqa: E402

J = None  # judge module (judge_v3g / judge_v3h), set in main() from --judge

THRESH = 7.5
VLLM_ARMS_ROOT = "vllm"
FAIL = ("infra_error", "crash", "exception")


def jload(p):
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return None


def jwrite(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    json.dump(d, open(tmp, "w"), indent=1)
    os.replace(tmp, p)


def wilson(k: int, n: int) -> list[float]:
    if n == 0:
        return [float("nan"), float("nan")]
    z = 1.959964
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(c - h, 3), round(c + h, 3)]


def is_vllm(model_key: str) -> bool:
    import runner_common as RC

    return RC.MODELS[model_key]["root"] == VLLM_ARMS_ROOT


class Ports:
    def __init__(self, spec: str):
        self.q: queue.Queue = queue.Queue()
        for part in spec.split(","):
            port, _, n = part.partition(":")
            for _ in range(int(n or 1)):
                self.q.put(int(port))

    def acquire(self) -> int:
        return self.q.get()

    def release(self, p: int) -> None:
        self.q.put(p)


TEAM_LOCKS: dict = {}
TEAM_LOCKS_GUARD = threading.Lock()


def team_lock(team_id) -> threading.Lock:
    """One rollout per twin team at a time: concurrent rollouts on one team saw each other's objects (b11: an arm
    reused another arm's insights) and their state resets could race."""
    with TEAM_LOCKS_GUARD:
        return TEAM_LOCKS.setdefault(team_id, threading.Lock())


def rollout(args, arm: str, tid: str, k: int, ports: Ports, api_slots: dict) -> dict | None:
    base = f"{args.root}/{arm}"
    out = f"{base}/runs/{tid}/r{k}.json"
    tr = jload(out)
    if tr and tr.get("status") not in FAIL:
        return tr
    vllm = is_vllm(arm)
    for attempt in range(1, 4):
        if os.path.exists(out):
            os.remove(out)
        runner_py = "/opt/posthog-env/opd_env/run_task_capture.py" if (args.capture and not vllm) else f"{RUNNER}/run_task.py"
        cmd = [f"{PH}/.venv/bin/python", runner_py, "--tasks", args.tasks, "--task-id", tid,
               "--model", arm, "--out", out, "--wall-s", str(args.wall_s), "--step-cap", "30",
               "--max-turns", str(args.max_turns), "--reset-team-state", "track"]
        env = dict(os.environ)
        env.update({"POSTHOG_ENV_ROOT": "/opt/posthog-env", "UV_PYTHON_INSTALL_DIR": "/opt/posthog-env/uv-python",
                    "PATH": "/opt/posthog-env/bin:" + env.get("PATH", ""), "POSTHOG_ENV_LLM_VIA_PROXY": "1"})
        port = None
        if vllm:
            port = ports.acquire()
            env["VLLM_BASE_URL"] = f"http://127.0.0.1:{port}/v1"
        else:
            api_slots[arm].acquire()
        log = f"{base}/logs/{tid}.r{k}.log"
        os.makedirs(os.path.dirname(log), exist_ok=True)
        lock = team_lock(TASK_TEAM.get(tid))
        lock.acquire()
        try:
            with open(log, "a") as lf:
                lf.write(f"\n=== attempt {attempt} {time.strftime('%H:%M:%S')} ===\n")
                lf.flush()
                proc = subprocess.Popen(cmd, cwd=PH, env=env, stdout=lf, stderr=lf, stdin=subprocess.DEVNULL)
                try:
                    proc.wait(timeout=args.wall_s + 600)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        finally:
            lock.release()
            if vllm:
                ports.release(port)
            else:
                api_slots[arm].release()
        tr = jload(out)
        if tr and tr.get("status") not in FAIL:
            return tr
        time.sleep(30 * attempt)
    return tr


def judge(path: str, tr: dict, notes=None) -> dict:
    ver = J.__name__.replace("judge_", "")
    rec = jload(path)
    if rec and rec.get("started_at") == tr.get("started_at") and rec.get("overall") is not None \
            and rec.get("judge_version", "v3g") == ver:
        return rec
    if notes:
        tr = {**tr, "grading_notes": notes}
    rec = {"judge": "gpt-6.1-sol", "judge_version": ver, "started_at": tr.get("started_at")}
    for _ in range(3):
        try:
            rec.update(J.score_transcript(tr, "gpt-6.1-sol"))
            rec.pop("error", None)
            break
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            time.sleep(20)
    jwrite(path, rec)
    return rec


TASK_TEAM: dict = {}


def run(args, arms: list[str], tasks: list[dict]) -> None:
    TASK_TEAM.update({t["task_id"]: t.get("team_id") for t in tasks})
    ports = Ports(args.ports)
    api_slots = {a: threading.BoundedSemaphore(args.api_concurrency) for a in arms if not is_vllm(a)}
    jq: queue.Queue = queue.Queue()
    notes = {t["task_id"]: t.get("grading_notes") for t in tasks if t.get("grading_notes")}
    counts: Counter = Counter()
    lock = threading.Lock()
    t0 = time.time()
    ns = arm_samples(args)
    n_jobs = sum(ns[a] for a in arms) * len(tasks)

    def judge_worker():
        while True:
            item = jq.get()
            if item is None:
                return
            arm, tid, k, tr = item
            rec = judge(f"{args.root}/{arm}/judge/{tid}.s{k}.json", tr, notes.get(tid))
            with lock:
                counts["judged" if rec.get("overall") is not None else "judge_error"] += 1

    def job(arm: str, tid: str, k: int):
        tr = rollout(args, arm, tid, k, ports, api_slots)
        st = (tr or {}).get("status", "missing")
        ok = st not in FAIL and st != "missing"
        with lock:
            counts[f"rollout_{'ok' if ok else 'failed'}"] += 1
            done = counts["rollout_ok"] + counts["rollout_failed"]
            if done % 25 == 0 or done == n_jobs:
                print(f"[bench] rollouts {done}/{n_jobs} {dict(counts)} {time.time() - t0:.0f}s", flush=True)
        if ok and tr.get("messages"):
            jq.put((arm, tid, k, tr))

    judges = [threading.Thread(target=judge_worker, daemon=True) for _ in range(args.judge_workers)]
    for t in judges:
        t.start()
    jobs = [(a, t["task_id"], k) for k in range(max(ns.values())) for t in tasks for a in arms if k < ns[a]]
    # interleave so one team's rollouts (now serialised per team) are spread over the run
    jobs.sort(key=lambda j: (j[2], hashlib.sha256(f"{j[1]}:{j[0]}".encode()).hexdigest()))
    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(lambda j: job(*j), jobs))
    for _ in judges:
        jq.put(None)
    for t in judges:
        t.join()
    print(f"[bench] done {dict(counts)} {time.time() - t0:.0f}s", flush=True)


def cost_wall(tr: dict) -> tuple[float, float]:
    usd = 0.0
    for v in (tr.get("usage_by_model") or {}).values():
        if isinstance(v, dict):
            usd += float(v.get("usd") or v.get("cost_usd") or 0)
    wall = sum(float(t.get("elapsed_s") or 0) for t in (tr.get("turns") or []) if isinstance(t, dict))
    return usd, wall


def report(args, arms: list[str], tasks: list[dict]) -> dict:
    ids = [t["task_id"] for t in tasks]
    per: dict = {a: {} for a in arms}
    meta: dict = {a: {"status": Counter(), "passes": [], "usd": [], "wall": []} for a in arms}
    for a in arms:
        for tid in ids:
            xs, ps = [], []
            for k in range(arm_samples(args)[a]):
                tr = jload(f"{args.root}/{a}/runs/{tid}/r{k}.json")
                if tr:
                    meta[a]["status"][tr.get("status")] += 1
                    u, w = cost_wall(tr)
                    meta[a]["usd"].append(u)
                    meta[a]["wall"].append(w)
                rec = jload(f"{args.root}/{a}/judge/{tid}.s{k}.json")
                if rec and rec.get("overall") is not None:
                    xs.append(rec["overall"])
                    ps.append(E.L.passes(rec, THRESH))
            per[a][tid] = (xs, ps)
    complete = [t for t in ids if all(len(per[a][t][0]) == arm_samples(args)[a] for a in arms)]
    tm = {a: {t: statistics.mean(per[a][t][0]) for t in complete} for a in arms}
    pm = {a: {t: statistics.mean(per[a][t][1]) for t in complete} for a in arms}
    rep: dict = {"tag": args.tag, "tasks_file": args.tasks, "samples": args.samples, "arms": arms,
                 "judge": f"{J.__name__} gpt-6.1-sol", "tasks": len(ids), "tasks_complete": len(complete),
                 "pass_rule": f"overall >= {THRESH} and no material wrong/unsupported error in the final answer",
                 "arms_summary": {}, "pairs": {}}
    for a in arms:
        s = E.mean_ci([tm[a][t] for t in complete]) if len(complete) > 1 else {}
        allp = [p for t in complete for p in per[a][t][1]]
        s["pass_rate"] = round(sum(allp) / max(1, len(allp)), 3)
        s["pass_rate_wilson95"] = wilson(sum(allp), len(allp))
        s["rollout_status"] = dict(meta[a]["status"])
        s["usd_per_rollout"] = round(statistics.mean(meta[a]["usd"]), 4) if meta[a]["usd"] else None
        s["wall_s_median"] = round(statistics.median(meta[a]["wall"]), 1) if meta[a]["wall"] else None
        s["wall_s_p90"] = round(sorted(meta[a]["wall"])[int(0.9 * (len(meta[a]["wall"]) - 1))], 1) if meta[a]["wall"] else None
        rep["arms_summary"][a] = s
    for a, b in itertools.combinations(arms, 2):
        if len(complete) > 5:
            rep["pairs"][f"{a}__vs__{b}"] = E.paired(tm[a], tm[b], complete)
    if len(complete) > 5:
        order = sorted(arms, key=lambda a: -statistics.mean(tm[a].values()))
        rep["ranking"] = order
        top, bottom = order[0], order[-1]
        bands = Counter()
        sep = 0
        for t in complete:
            ps = [pm[a][t] for a in arms]
            if min(ps) == 1:
                bands["all_pass"] += 1
            elif max(ps) == 0:
                bands["none_pass"] += 1
            else:
                bands["mixed"] += 1
            if tm[top][t] - tm[bottom][t] >= 1.5:
                sep += 1
        rep["difficulty"] = {"bands_by_pass": dict(bands), "share_top_minus_bottom_ge_1_5": round(sep / len(complete), 3),
                             "mean_score_all_arms": round(statistics.mean(x for a in arms for x in tm[a].values()), 3)}
        # per-task separation index: Spearman-free, share of tasks where the arm order matches the overall order
        # for the top and bottom arm (strict).
        rep["difficulty"]["top_beats_bottom"] = sum(tm[top][t] > tm[bottom][t] for t in complete)
        rep["difficulty"]["bottom_beats_top"] = sum(tm[top][t] < tm[bottom][t] for t in complete)
    jwrite(f"{args.root}/report.json", rep)
    return rep


def arm_samples(args) -> dict:
    out = {a: args.samples for a in args.arms.split(",")}
    for x in filter(None, (args.arm_samples or "").split(",")):
        a, n = x.split(":")
        out[a] = int(n)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--arms", required=True, help="comma-separated runner model keys")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--arm-samples", default="", help="per-arm sample counts, e.g. opus:1 (others use --samples)")
    ap.add_argument("--task-ids-file", default="", help="optional JSON list of task ids to restrict to")
    ap.add_argument("--workers", type=int, default=40)
    ap.add_argument("--ports", default="18000:6,18010:10,18011:10")
    ap.add_argument("--api-concurrency", type=int, default=6, help="concurrent rollouts per API (proxy) arm")
    ap.add_argument("--judge-workers", type=int, default=6)
    ap.add_argument("--wall-s", type=float, default=900)
    ap.add_argument("--max-turns", type=int, default=4)
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--judge", default="v3i", choices=["v3g", "v3h", "v3i"])
    ap.add_argument("--capture", action="store_true",
                    help="API arms run through opd_env/run_task_capture.py (root calls in Qwen format, <out>.cap.jsonl.gz) for SFT")
    args = ap.parse_args()
    global J
    J = importlib.import_module(f"judge_{args.judge}")
    args.root = f"{RUNNER}/bench/{args.tag}"
    arms = [a for a in args.arms.split(",") if a]
    tasks = [json.loads(x) for x in open(args.tasks) if x.strip()]
    if args.task_ids_file:
        keep = set(json.load(open(args.task_ids_file)))
        tasks = [t for t in tasks if t["task_id"] in keep]
    if args.n:
        tasks = tasks[: args.n]
    os.makedirs(args.root, exist_ok=True)
    if not args.report_only:
        run(args, arms, tasks)
    rep = report(args, arms, tasks)
    print(json.dumps({k: rep.get(k) for k in ("tasks_complete", "ranking", "arms_summary", "difficulty")}, indent=1))


if __name__ == "__main__":
    main()
