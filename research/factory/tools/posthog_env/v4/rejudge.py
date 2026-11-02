"""Matched secondary judging of frozen rollouts, with arm metadata hidden from the judge.

Run on the data host. No task selection or rollout generation occurs here. Missing/failed judgements remain
incomplete; results are a judge-sensitivity check, not independent model samples.
"""
from __future__ import annotations

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time

from rubric_probe import complete_judgement
from task_quality import pass_result, summarize


def blinded(trace: dict, task: dict) -> dict:
    result = copy.deepcopy(trace)
    for key in ("model", "model_key", "model_name", "arm", "root_model", "provider", "port", "judge"):
        result.pop(key, None)
    result["grading_notes"] = task.get("grading_notes")
    return result


def key_for(trace: dict, task: dict, model: str, judge: str) -> str:
    return hashlib.sha256(json.dumps([trace, task, model, judge], sort_keys=True).encode()
                          + Path(__file__).read_bytes()).hexdigest()


def read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", type=Path, required=True)
    ap.add_argument("--bench", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--judge-model", required=True)
    ap.add_argument("--judge", default="judge_v3i")
    ap.add_argument("--student", default="qwen")
    ap.add_argument("--frontier", default="gpt-sol")
    ap.add_argument("--student-samples", type=int, default=2)
    ap.add_argument("--frontier-samples", type=int, default=1)
    ap.add_argument("--follow-until", help="aware absolute deadline; also wrap the process in timeout")
    a = ap.parse_args()
    end = dt.datetime.fromisoformat(a.follow_until) if a.follow_until else None
    if end and end.tzinfo is None:
        ap.error("Use an aware deadline")
    sys.path[:0] = ["/opt/posthog-env/runner", "/opt/posthog-env/runner/judge_v3", "/opt/posthog-env"]
    judge = importlib.import_module(a.judge)
    tasks = [json.loads(l) for l in a.tasks.read_text().splitlines() if l.strip()]
    samples = {a.student: a.student_samples, a.frontier: a.frontier_samples}
    a.out.mkdir(parents=True, exist_ok=True)

    def one(job):
        task, arm, k = job
        tid = task["task_id"]
        trace = read(a.bench / arm / "runs" / tid / f"r{k}.json")
        if not trace or trace.get("status") in (None, "running", "infra_error", "crash", "exception"):
            return (tid, arm, k), None
        path = a.out / arm / "judge" / f"{tid}.s{k}.json"
        key = key_for(trace, task, a.judge_model, a.judge)
        rec = read(path)
        same = rec and rec.get("input_key") == key
        if same and complete_judgement(rec):
            return (tid, arm, k), pass_result(rec, trace)
        attempts = rec.get("attempts", 0) if same else 0
        if attempts >= 3 or end and time.time() >= end.timestamp():
            return (tid, arm, k), None
        try:
            rec = judge.score_transcript(blinded(trace, task), a.judge_model)
        except Exception as exc:
            # Keep provider error strings on the data host; do not expose request bodies or credentials.
            rec = {"error": type(exc).__name__}
        rec.update({"input_key": key, "attempts": attempts + 1, "judge_model": a.judge_model,
                    "evidence": "secondary judge on the same observed rollout, arm metadata omitted"})
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=2))
        tmp.replace(path)
        return (tid, arm, k), pass_result(rec, trace) if complete_judgement(rec) else None

    jobs = [(t, arm, k) for t in tasks for arm, n in samples.items() for k in range(n)]
    # Deterministic order independent of primary scores or which arm finished first.
    jobs.sort(key=lambda j: hashlib.sha256(f"{j[0]['task_id']}:{j[1]}:{j[2]}".encode()).hexdigest())
    while True:
        with ThreadPoolExecutor(2) as pool:
            results = dict(pool.map(one, jobs))
        report = summarize(tasks, results, a.student, a.frontier, samples)
        report.update({"judge_model": a.judge_model, "judge": a.judge,
                       "evidence": "judge-sensitivity analysis on unchanged model samples; no extra model rollouts"})
        (a.out / "quality_report.json").write_text(json.dumps(report, indent=2))
        if not end or time.time() >= end.timestamp():
            print(json.dumps({"judge_model": a.judge_model, "paired": report["paired"]}))
            break
        time.sleep(min(30, max(0, end.timestamp() - time.time())))


if __name__ == "__main__":
    main()
