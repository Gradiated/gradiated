"""Aggregate task breadth and matched frontier/student results without exposing task text.

Run on fbf8: python3 task_quality.py --tasks validated.jsonl --bench runner/bench/TAG
Reports all eligible tasks as well as complete pairs; missing judge/rollout results are not model failures.
Pass-rate gaps are descriptive, task-weighted measurements. This does not select a held-out eval set based
on model performance; use calibration tasks to tune difficulty and freeze eval inputs before measuring.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import statistics


EXPECTED_FAMILIES = ("metric_lookup", "trend_breakdown", "funnel_conversion", "retention_engagement",
                     "anomaly_investigation", "attribution_marketing", "entity_lookup", "sql_help",
                     "build_insight_dashboard", "session_replay", "flags_experiments", "surveys", "errors_logs",
                     "llm_analytics", "warehouse", "product_howto", "tracking_quality")


def pass_result(judge: dict | None, rollout: dict | None) -> bool | None:
    if not judge or not rollout or rollout.get("status") in (None, "running", "infra_error", "crash", "exception"):
        return None
    score = judge.get("overall")
    if (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score)
            or not 0 <= score <= 10 or judge.get("error")):
        return None
    if any(judge.get(k) is None for k in ("material_wrong_final", "material_unsupported_final")):
        return None
    return score >= 7.5 and judge["material_wrong_final"] == 0 and judge["material_unsupported_final"] == 0


def summarize(tasks: list[dict], results: dict, student: str, frontier: str,
              samples: dict[str, int]) -> dict:
    ids = [t["task_id"] for t in tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate task IDs; reconcile task versions before measuring")
    if any(samples.get(arm, 0) < 1 for arm in (student, frontier)):
        raise ValueError("Both arms need at least one expected sample")
    excluded = Counter()
    groups = defaultdict(list)
    pairs = []
    for t in tasks:
        if t.get("exclude") or (t.get("validation") or {}).get("verdict") != "SOUND":
            excluded["not_sound_or_excluded"] += 1
            continue
        family = (t.get("synth") or {}).get("family") or "unclassified"
        groups[family].append(t)
        rates = {}
        for arm in (student, frontier):
            values = [results.get((t["task_id"], arm, k)) for k in range(samples[arm])]
            if all(isinstance(v, bool) for v in values):
                rates[arm] = statistics.mean(values)
        if len(rates) == 2:
            pairs.append((t, rates))
        else:
            excluded["incomplete_pair"] += 1

    def metrics(rows):
        if not rows:
            return {"complete_tasks": 0, "student_pass_rate": None, "frontier_pass_rate": None,
                    "frontier_minus_student": None, "bands": {}}
        sp = statistics.mean(r[student] for _, r in rows)
        fp = statistics.mean(r[frontier] for _, r in rows)
        bands = Counter("frontier_advantage" if r[frontier] > r[student] else
                        "student_advantage" if r[student] > r[frontier] else
                        "both_always_pass" if r[student] == 1 else
                        "both_always_fail" if r[student] == 0 else "equal_mixed" for _, r in rows)
        return {"complete_tasks": len(rows), "student_pass_rate": sp, "frontier_pass_rate": fp,
                "frontier_minus_student": fp - sp, "bands": dict(bands)}

    eligible = [t for ts in groups.values() for t in ts]
    return {"evidence": "measured, descriptive; repeated samples averaged within each task",
            "tasks_total": len(tasks), "tasks_eligible": len(eligible), "excluded": dict(excluded),
            "twins": len({t.get("twin_id") for t in eligible}),
            "splits": dict(Counter(t.get("split", "unknown") for t in eligible)),
            "difficulty_labels": dict(Counter((t.get("curation") or {}).get("difficulty", "unknown") for t in eligible)),
            "missing_families": sorted(set(EXPECTED_FAMILIES) - set(groups)),
            "paired": metrics(pairs),
            "families": {f: {"eligible_tasks": len(ts), "twins": len({t.get("twin_id") for t in ts}),
                              **metrics([(t, r) for t, r in pairs if t in ts])} for f, ts in sorted(groups.items())}}


def load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", required=True, help="comma-separated validated JSONL files")
    ap.add_argument("--bench", required=True)
    ap.add_argument("--student", default="qwen")
    ap.add_argument("--frontier", default="opus")
    ap.add_argument("--student-samples", type=int, default=2)
    ap.add_argument("--frontier-samples", type=int, default=1)
    a = ap.parse_args()
    tasks = [json.loads(line) for file in a.tasks.split(",") for line in Path(file).read_text().splitlines() if line.strip()]
    samples = {a.student: a.student_samples, a.frontier: a.frontier_samples}
    results = {}
    for task in tasks:
        for arm, n in samples.items():
            base = Path(a.bench) / arm
            for k in range(n):
                tid = task["task_id"]
                results[tid, arm, k] = pass_result(load(base / "judge" / f"{tid}.s{k}.json"),
                                                 load(base / "runs" / tid / f"r{k}.json"))
    print(json.dumps(summarize(tasks, results, a.student, a.frontier, samples), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
