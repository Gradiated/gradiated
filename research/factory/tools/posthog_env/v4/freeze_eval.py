"""Freeze gated evaluation inputs before scoring. Reads quality proofs, never rollout/model scores.

Run on the data host. The output directory must be new. Reviewed failures are excluded for quality reasons;
all other gated tasks are retained. A changed dataset, quality review or protocol requires a new manifest.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def eligible(tasks: list[dict], selection: dict, review: dict, forbidden: set[str], min_families: int) -> list[dict]:
    by_id = {t["task_id"]: t for t in tasks}
    if len(by_id) != len(tasks):
        raise ValueError("Duplicate task IDs")
    rows = review.get("results", [])
    ids = [r["task_id"] for r in rows]
    selected = selection.get("task_hashes", {})
    if len(ids) != 15 or len(set(ids)) != 15 or set(ids) != set(selected):
        raise ValueError("Need a complete independently selected 15-task quality review")
    for tid, sha in selected.items():
        if tid not in by_id or digest(by_id[tid]) != sha:
            raise ValueError("Quality review does not match these exact task versions")
    good = [r for r in rows if r.get("verdict") == "SOUND" and r.get("contract_checks")
            and not r.get("error") and r.get("query_count", 0) > 0]
    if len(good) < 14 or not review.get("quality_bar_met"):
        raise ValueError("Independent 14/15 quality bar not met")
    bad = set(ids) - {r["task_id"] for r in good}
    result = [t for t in tasks if t["task_id"] not in bad and not t.get("exclude")
              and t.get("validation", {}).get("verdict") == "SOUND"]
    if any(t.get("split") != "test" or t.get("twin_id") in forbidden for t in result):
        raise ValueError("Evaluation requires disjoint test projects")
    if len({t.get("twin_id") for t in result}) < 2:
        raise ValueError("Evaluation requires at least two disjoint worlds")
    if len({t.get("synth", {}).get("family") for t in result}) < min_families:
        raise ValueError("Insufficient analytical-family breadth")
    return sorted(result, key=lambda t: t["task_id"])


def evidence(path: Path) -> dict:
    d = json.loads(path.read_text())
    if d.get("error") or d.get("defects") or not d.get("queries_run") or d.get("verdict") != "SOUND":
        raise ValueError(f"Incomplete or failed task proof: {path.name}")
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", required=True, type=Path)
    ap.add_argument("--world-freeze", required=True, type=Path)
    ap.add_argument("--review", required=True, type=Path)
    ap.add_argument("--validation", required=True, type=Path)
    ap.add_argument("--protocol", required=True, type=Path)
    ap.add_argument("--calibration-tasks", required=True, help="comma-separated task files with forbidden project IDs")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--min-families", type=int, default=12)
    a = ap.parse_args()
    tasks = [json.loads(l) for l in a.tasks.read_text().splitlines() if l.strip()]
    forbidden = {t["twin_id"] for f in a.calibration_tasks.split(",")
                 for l in Path(f).read_text().splitlines() if l.strip() for t in [json.loads(l)]}
    selection = json.loads((a.review / "selection.json").read_text())
    review = json.loads((a.review / "summary.json").read_text())
    chosen = eligible(tasks, selection, review, forbidden, a.min_families)
    protocol = json.loads(a.protocol.read_text())
    arms = protocol.get("arms", {})
    if len(arms) != 2 or "qwen" not in arms or any(type(n) is not int or n < 1 for n in arms.values()):
        raise ValueError("Freeze exactly two explicitly sampled comparison arms including qwen")
    for key in ("max_turns", "wall_s", "judge", "judge_model", "deadline", "model_identity", "pass_rule"):
        if not protocol.get(key):
            raise ValueError(f"Protocol missing {key}")
    deadline = dt.datetime.fromisoformat(protocol["deadline"])
    if deadline.tzinfo is None or deadline <= dt.datetime.now(dt.timezone.utc):
        raise ValueError("Protocol deadline must be future and timezone aware")
    world = json.loads(a.world_freeze.read_text())
    if world.get("status") != "UNSCORED":
        raise ValueError("Raw world freeze is superseded or already scored")
    proofs = [a.tasks, a.world_freeze, a.protocol, a.review / "selection.json", a.review / "summary.json",
              a.review / "baseline_objects.json"]
    for name, sha in world["files"].items():
        p = a.world_freeze.parent / name
        if hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            raise ValueError("Frozen raw world was modified")
    for t in chosen:
        for p in (a.validation / (t["task_id"] + ".json"), a.validation / "gate" / (t["task_id"] + ".json")):
            evidence(p)
            proofs.append(p)
    for tid in selection["task_hashes"]:
        p = a.review / "reviews" / (tid + ".json")
        r = json.loads(p.read_text())
        if not r.get("queries_run") or not r.get("checks", {}).get("minimal_answer") or not r.get("checks", {}).get("contract_match"):
            raise ValueError("Independent review proof is incomplete")
        proofs.append(p)
    manifest = {"status": "FROZEN_BEFORE_SCORING", "frozen_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "protocol": protocol, "task_ids": [t["task_id"] for t in chosen],
                "task_hashes": {t["task_id"]: digest(t) for t in chosen},
                "twins": sorted({t["twin_id"] for t in chosen}),
                "families": sorted({t["synth"]["family"] for t in chosen}),
                "forbidden_calibration_twins": sorted(forbidden),
                "proof_hashes": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in proofs},
                "selection": "all gated tasks except independently reviewed quality failures; no model-score inputs",
                "scope": "two synthetic worlds sharing one product archetype; no real-customer generalization claim"}
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out / "tasks.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in chosen))
    (a.out / "task_ids.json").write_text(json.dumps(manifest["task_ids"]))
    manifest["taskfile_sha256"] = hashlib.sha256((a.out / "tasks.jsonl").read_bytes()).hexdigest()
    (a.out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"tasks": len(chosen), "families": len(manifest["families"]), "worlds": len(manifest["twins"])}))


if __name__ == "__main__":
    main()
