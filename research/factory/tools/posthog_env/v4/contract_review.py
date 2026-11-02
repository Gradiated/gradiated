"""Independent, live-query task-contract review; run on the data host before final model scoring.

Selection uses only accepted task IDs and family labels, never rollout scores. This is a separate model review,
not a substitute for controlled grader interventions or executing object-creation tasks.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import hashlib
import json
from pathlib import Path
import random
import sys
import time


CONTRACT = """Perform an independent USER-CONTRACT audit with fresh live read-only queries. Do not trust author
SQL or findings. Recompute using a different aggregation or cross-check where possible. Keep all existing quality
rules. Derive the shortest correct answer to each explicit user turn, in its original language, and compare every
required grading point against that answer. Reject unasked details, hidden definitions, unsupported conclusions,
wrong denominators, right-censored cohorts, incorrect weighted aggregates or global quantiles. Optional exact dates
in a period-level summary cannot be required unless the user asks for a dated timeline. SOUND means no caveat.
Add checks.minimal_answer with concrete minimal findings, or a precise artifact specification for a creation request.
Add checks.contract_match mapping required findings to explicit requests, or identifying mismatches. Object creation
feasibility is analytical in this review; do not pretend to create anything. The supplied object list is a frozen
baseline captured before model scoring; do not use artifacts from concurrent model runs as preexisting objects."""


def review_model(task: dict, default: str, alternate: str | None = None) -> str:
    if alternate is None:
        return default
    author = (task.get("synth") or {}).get("author_model")
    if not author:
        raise ValueError("Independent-author review requires explicit author_model provenance")
    if alternate == default:
        raise ValueError("Alternate reviewer must differ from the default")
    return alternate if author == default else default


def select(tasks: list[dict], count: int, seed: int, min_per_author: int = 0) -> list[dict]:
    if count < 1 or min_per_author < 0:
        raise ValueError("Review count must be positive")
    ids = [t["task_id"] for t in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate task IDs")
    groups = {}
    for t in sorted(tasks, key=lambda t: t["task_id"]):
        if t.get("exclude") or (t.get("validation") or {}).get("verdict") != "SOUND":
            continue
        groups.setdefault((t.get("synth") or {}).get("family", "unclassified"), []).append(t)
    candidates = [t for rows in groups.values() for t in rows]
    if len(candidates) < count:
        raise ValueError(f"Need {count} gated tasks; have {len(candidates)}")
    if len(groups) > count:
        raise ValueError("Review count must cover every candidate family")
    rng = random.Random(seed)
    chosen = [rng.choice(groups[f]) for f in sorted(groups)]
    if min_per_author:
        authors = {}
        for task in candidates:
            author = task.get("synth", {}).get("author_model")
            if not author:
                raise ValueError("Author-stratified review requires author_model provenance")
            authors.setdefault(author, []).append(task)
        for author, rows in sorted(authors.items()):
            if len(rows) < min_per_author:
                raise ValueError("Insufficient candidates for the requested author stratum")
            have = sum(t.get("synth", {}).get("author_model") == author for t in chosen)
            remaining = [t for t in rows if t not in chosen]
            chosen.extend(rng.sample(remaining, max(0, min_per_author - have)))
        if len(chosen) > count:
            raise ValueError("Review count cannot cover both family and author strata")
    rest = [t for t in candidates if t not in chosen]
    rng.shuffle(rest)
    return (chosen + rest)[:count]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", required=True, help="comma-separated gated JSONL files")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model", required=True)
    ap.add_argument("--count", type=int, default=15)
    ap.add_argument("--required", type=int, default=14)
    ap.add_argument("--seed", type=int, default=20261102)
    ap.add_argument("--known-data-issue", default="")
    ap.add_argument("--alternate-model", help="review tasks authored by --model with this different reviewer")
    ap.add_argument("--min-per-author", type=int, default=0)
    ap.add_argument("--deadline", required=True, help="aware ISO UTC deadline; also wrap process in timeout")
    a = ap.parse_args()
    deadline = dt.datetime.fromisoformat(a.deadline)
    if deadline.tzinfo is None or deadline.timestamp() <= time.time() or not 1 <= a.required <= a.count:
        ap.error("Use a future aware deadline and required in 1..count")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import validate_tasks as v
    tasks = [json.loads(l) for f in a.tasks.split(",") for l in Path(f).read_text().splitlines() if l.strip()]
    selected = select(tasks, a.count, a.seed, a.min_per_author)
    models = {t["task_id"]: review_model(t, a.model, a.alternate_model) for t in selected}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "reviews").mkdir(exist_ok=True)
    manifest = {"seed": a.seed, "model": a.model, "required": a.required,
                "known_data_issue": a.known_data_issue,
                "task_hashes": {t["task_id"]: hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest()
                                for t in selected}}
    if a.alternate_model or a.min_per_author:
        manifest.update(review_models=models, min_per_author=a.min_per_author)
    path = a.out / "selection.json"
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise ValueError("Preserve prior selection: use a new review directory for changed inputs")
    path.write_text(json.dumps(manifest, indent=2))
    snapshot = a.out / "baseline_objects.json"
    if snapshot.exists():
        objects = json.loads(snapshot.read_text())
    else:
        objects = {str(t["team_id"]): v.SC.team_objects(t["team_id"]) for t in selected}
        snapshot.write_text(json.dumps(objects, indent=2))
    extra = CONTRACT
    if a.known_data_issue:
        extra += "\nKnown data issue: " + a.known_data_issue + ". Verify relevance; affected tasks cannot be SOUND."

    def review(t):
        if time.time() >= deadline.timestamp():
            return {"task_id": t["task_id"], "verdict": None, "error": "deadline", "contract_checks": False}
        task = dict(t)
        task.pop("validation", None)
        task["_audit_objects_snapshot"] = objects[str(t["team_id"])]
        r = v.validate_one(task, None, models[t["task_id"]], str(a.out / "reviews"), extra=extra, max_rounds=5,
                           required_checks=("minimal_answer", "contract_match"))
        return {"task_id": t["task_id"], "family": t.get("synth", {}).get("family"),
                "review_model": models[t["task_id"]], "author_model": t.get("synth", {}).get("author_model"),
                "verdict": r.get("verdict"), "error": r.get("error"),
                "contract_checks": v.has_checks(r, ("minimal_answer", "contract_match")),
                "query_count": len(r.get("queries_run", []))}

    rows = []
    with ThreadPoolExecutor(2) as pool:
        for f in as_completed([pool.submit(review, t) for t in selected]):
            rows.append(f.result())
            (a.out / "progress.json").write_text(json.dumps(rows, indent=2))
    passed = sum(r["verdict"] == "SOUND" and r["contract_checks"] and not r["error"] for r in rows)
    summary = {"evidence": "independent model contract review with live queries; creation feasibility analytical",
               "tasks": len(rows), "sound": passed, "required": a.required,
               "quality_bar_met": len(rows) == a.count and passed >= a.required, "results": rows}
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: val for k, val in summary.items() if k != "results"}))


if __name__ == "__main__":
    main()
