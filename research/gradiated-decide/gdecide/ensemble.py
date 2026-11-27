"""Combine evaluated runs into one run by weighted averaging of their per-option probabilities.

    python -m gdecide.ensemble --runs RUN_A RUN_B [...] --out RUN_DIR [--weights 0.5 0.5] [--mode linear|log]

Each run is a ``gdecide.evaluate`` directory (``results-<rank>.jsonl`` shards or a merged ``results.jsonl``) or a
kit ``results.jsonl`` file. ``linear`` (default) is REAX 1.3's rule (``engine/probabilities.py``): the weighted mean
of the option probabilities, renormalized for round-off, the choice the most probable option (ties to the first key
in sorted order), and for yes/no questions the weighted mean of ``noul``. ``log`` takes the weighted geometric mean
(log-linear pooling) and renormalizes; a yes/no question is pooled as the two-option distribution (noul, 1 - noul).

Rows or questions a run did not answer (missing, ``unsupported`` or ``error``) are combined from the runs that did,
with their weights renormalized; a row no run answered keeps the first run's record. Output is ``results-0.jsonl``
(and an identical ``results.jsonl``) in kit result format plus ``ensemble.json``, so ``gdecide.score --run RUN_DIR``
scores it like any evaluated run.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

EPS = 1e-12


def read_run(path: str | Path) -> dict[str, dict]:
    """run_id -> record. Shards win over a merged file; within the files read, the last record of a run id wins."""
    path = Path(path)
    if path.is_file():
        files = [path]
    else:
        files = sorted(path.glob("results-*.jsonl")) or [path / "results.jsonl"]
    out: dict[str, dict] = {}
    for f in files:
        if not f.exists():
            raise FileNotFoundError(f"no results in {path}")
        for line in f.read_text().splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "run_id" in record:
                out[record["run_id"]] = record
    return out


def distribution(answer: dict) -> dict[str, float]:
    """An answer's option distribution: ``probabilities`` for choice and score, {true, false} for noul."""
    if answer.get("type") == "noul":
        p = float(answer["noul"])
        values = {"true": p, "false": 1.0 - p}
    else:
        values = {k: float(v) for k, v in (answer.get("probabilities") or {}).items()}
    if not values or any(not math.isfinite(v) or not -1e-9 <= v <= 1 + 1e-9 for v in values.values()):
        raise ValueError("invalid option probabilities")
    total = math.fsum(values.values())
    if total <= 0 or abs(total - 1) > 0.01:
        raise ValueError("option probabilities are not normalized")
    return values


def pool(dists: list[dict[str, float]], weights: list[float], mode: str = "linear") -> dict[str, float]:
    keys = list(dists[0])
    if any(set(d) != set(keys) for d in dists[1:]):
        raise ValueError("runs disagree on the options of a question")
    total_w = math.fsum(weights)
    if mode == "linear":
        probs = {k: math.fsum(w * d[k] for d, w in zip(dists, weights)) / total_w for k in keys}
    elif mode == "log":
        logs = {k: math.fsum(w * math.log(max(d[k], EPS)) for d, w in zip(dists, weights)) / total_w for k in keys}
        peak = max(logs.values())
        probs = {k: math.exp(v - peak) for k, v in logs.items()}
    else:
        raise ValueError(f"unknown mode {mode!r}")
    s = math.fsum(probs.values())
    return {k: v / s for k, v in probs.items()}


def combine_answer(answers: list[dict], weights: list[float], mode: str = "linear") -> dict:
    typ = answers[0].get("type")
    if any(a.get("type") != typ for a in answers):
        raise ValueError("runs disagree on a question's type")
    probs = pool([distribution(a) for a in answers], weights, mode)
    if typ == "noul":
        if mode == "linear":
            noul = math.fsum(w * float(a["noul"]) for a, w in zip(answers, weights)) / math.fsum(weights)
        else:
            noul = probs["true"]
        return {"type": "noul", "noul": min(1.0, max(0.0, noul))}
    out = {"type": typ, "probabilities": probs}
    if typ == "choice":
        out["choice"] = max(sorted(probs), key=probs.get)
    elif typ == "score":
        out["score"] = math.fsum(int(k) * v for k, v in probs.items())
    return out


def combine_record(records: list[dict | None], weights: list[float], mode: str, engine: str) -> tuple[dict, dict]:
    """-> (kit result record, {"members": run indices used, "partial": questions answered by fewer runs})."""
    ok = [(i, r) for i, r in enumerate(records) if r is not None and r.get("status") == "ok" and "response" in r]
    if not ok:
        first = next(r for r in records if r is not None)
        return first, {"members": [], "partial": 0}
    base = ok[0][1]
    qids = list(base["response"]["answers"])
    for _, r in ok[1:]:
        qids += [q for q in r["response"]["answers"] if q not in qids]
    answers, partial = {}, 0
    for qid in qids:
        have = [(i, r["response"]["answers"][qid]) for i, r in ok if qid in r["response"]["answers"]]
        partial += len(have) < len(ok)
        answers[qid] = combine_answer([a for _, a in have], [weights[i] for i, _ in have], mode)
    keep = {k: v for k, v in base.items() if k not in ("response", "raw_output", "payload", "error", "exception", "traceback")}
    wall = max(float(r.get("total_wall_ms", 0) or 0) for _, r in ok)
    record = {**keep, "engine": engine, "status": "ok", "response": {"model": engine, "answers": answers},
              "total_wall_ms": wall, "model_request_wall_ms": wall}
    return record, {"members": [i for i, _ in ok], "partial": partial}


def ensemble(runs: list[dict[str, dict]], weights: list[float], mode: str = "linear", engine: str = "ensemble"):
    if len(runs) != len(weights) or not runs:
        raise ValueError("one weight per run")
    if any(not math.isfinite(w) or w < 0 for w in weights) or math.fsum(weights) <= 0:
        raise ValueError("weights must be nonnegative with a positive sum")
    order = list(runs[0])
    for run in runs[1:]:
        order += [rid for rid in run if rid not in runs[0]]
    out, stats = [], {"rows": 0, "all": 0, "partial_rows": 0, "partial_questions": 0, "none": 0, "by_member": [0] * len(runs)}
    for rid in order:
        record, info = combine_record([run.get(rid) for run in runs], weights, mode, engine)
        out.append(record)
        stats["rows"] += 1
        members = info["members"]
        stats["all" if len(members) == len(runs) else "none" if not members else "partial_rows"] += 1
        stats["partial_questions"] += info["partial"]
        for i in members:
            stats["by_member"][i] += 1
    return out, stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--weights", nargs="+", type=float)
    parser.add_argument("--mode", choices=("linear", "log"), default="linear")
    parser.add_argument("--out", required=True)
    parser.add_argument("--engine", default="gradiated-decide:ensemble")
    args = parser.parse_args()
    weights = args.weights or [1.0] * len(args.runs)
    records, stats = ensemble([read_run(r) for r in args.runs], weights, args.mode, args.engine)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("results-*.jsonl"):
        old.unlink()
    text = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in records)
    (out / "results-0.jsonl").write_text(text)
    (out / "results.jsonl").write_text(text)
    manifest = {"runs": args.runs, "weights": weights, "mode": args.mode, "engine": args.engine, **stats}
    (out / "ensemble.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
