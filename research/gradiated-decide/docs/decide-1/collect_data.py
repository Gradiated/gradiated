"""Collect the numbers behind the decide-1 post into data.json.

Inputs (downloaded from s3://$DEV_TRAINING_S3_BUCKET/gradiated-decide/ into POST_DATA, default
.agents/runtime/gdecide/post-data): runs/{gd-kl1,gd-kl2}/{args.json,train.log.jsonl,candidates.jsonl},
data/{v1-knowline,kl2}/manifest.json (as manifest-NAME.json), runs/evals/*/gdecide-score.json,
runs/external/*/external-score.json; the suite manifest (SUITE, default .agents/runtime/gdecide/suite-0.3) for
benchmark names; .agents/runtime/gdecide/ens/e-3way for the three-way ensemble (local, measured).
Usage: python3 collect_data.py [POST_DATA] [SUITE]
"""
import json, os, statistics, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PD = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / ".agents/runtime/gdecide/post-data"
SUITE = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / ".agents/runtime/gdecide/suite-0.3"
GPUS = 8


def jl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def run(name, manifest):
    rows = jl(PD / name / "train.log.jsonl")
    m = json.load(open(PD / f"manifest-{manifest}.json"))
    data = [r for r in rows if r["event"] == "data"][-1]
    spe, total = data["steps_per_epoch"], data["total_steps"]
    tok_per_step = m["tokens"] / spe  # mean real (unpadded) tokens per optimizer step over the epoch plan
    train = {}
    for r in rows:  # a resumed run re-logs steps; keep the last value of each step
        if r["event"] == "train":
            train[r["step"]] = r
    steps = sorted(train)
    dev = {}
    for r in rows:
        if r["event"] == "dev":
            dev[r["step"]] = r["dev"]
    devsum = []
    for s in sorted(dev):
        d = {k: v for k, v in dev[s].items() if isinstance(v, dict) and "n" in v}
        n = sum(v["n"] for v in d.values())
        devsum.append({"step": s, "n": n, "acc": round(sum(v["acc"] * v["n"] for v in d.values()) / n, 4),
                       "ce": round(sum(v["ce"] * v["n"] for v in d.values()) / n, 4)})
    first, last = min(dev), max(dev)
    moves = sorted(((round((dev[last][k]["acc"] - dev[first][k]["acc"]) * 100, 1), k, dev[first][k]["n"])
                    for k in dev[last] if k in dev[first] and isinstance(dev[last][k], dict) and "acc" in dev[last][k]),
                   reverse=True)
    # Active training time: 10-step logging intervals shorter than 30 minutes (longer gaps are restarts).
    times = [(s, train[s]["time"]) for s in steps]
    active, gaps = 0.0, []
    for (s0, t0), (s1, t1) in zip(times, times[1:]):
        dt = t1 - t0
        if dt < 1800:
            active += dt
            gaps.append(dt / (s1 - s0))
    step_s = statistics.median(gaps)
    active += step_s * steps[0]  # steps before the first log line
    starts = [r["time"] for r in rows if r["event"] == "model"]
    finish = [r["time"] for r in rows if r["event"] == "finished"][-1]
    return {
        "manifest": {k: m[k] for k in ("train_rows", "dev_rows", "tokens", "length_percentiles", "dropped")},
        "sources": m["by_source"],
        "steps_per_epoch": spe, "steps": total, "epoch_fraction": round(total / spe, 4),
        "real_tokens_per_step": round(tok_per_step), "real_tokens_seen": round(tok_per_step * total),
        "examples_seen": round(m["train_rows"] * total / spe),
        "token_budget_per_step": GPUS * json.load(open(PD / name / "args.json"))["tokens_per_batch"],
        "args": json.load(open(PD / name / "args.json")),
        "resumes": [r["step"] for r in rows if r["event"] == "resumed"],
        "process_starts": len(starts),
        "wall_clock_h": round((finish - starts[0]) / 3600, 2),
        "active_train_h": round(active / 3600, 2), "median_step_s": round(step_s, 2),
        "gpu_hours_active": round(active / 3600 * GPUS, 1),
        "train": [{"step": s, "ce": train[s]["ce"], "brier": train[s]["brier"], "lr": train[s]["lr"],
                   "recent_tokens_per_s": train[s].get("recent_tokens_per_s")} for s in steps],
        "dev": devsum,
        "dev_moves_first_to_last": [{"source": k, "acc_delta_pts": d, "n": n} for d, k, n in moves],
        # Blend sweep from the scored dev-sample runs (candidates.jsonl of gd-kl2 also holds the failed first attempts).
        "blend_sample_index": {a: score(PD / "evals" / f"{name}-s{total}-a{a}-sample" / "gdecide-score.json")["index"]
                               for a in ("1.0", "0.7", "0.5")},
    }


def score(path):
    return json.load(open(path))


names = {}
man = json.load(open(SUITE / "manifest.json"))
for b in man["benchmarks"] + man["added"]:
    names[str(b["catalog_id"])] = b["dataset"]

panels = {}
for d in sorted((PD / "evals").iterdir()):
    f = d / "gdecide-score.json"
    if f.exists():
        s = score(f)
        panels[d.name] = {"index": s["index"], "areas": s["areas"], "benchmarks": s["benchmarks"]}
e3 = REPO / ".agents/runtime/gdecide/ens/e-3way/gdecide-score.json"
if e3.exists():
    s = score(e3)
    panels["ens-3way-local-panel"] = {"index": s["index"], "areas": s["areas"], "benchmarks": s["benchmarks"]}

external = {}
for d in sorted((PD / "external").iterdir()):
    f = d / "external-score.json"
    if f.exists():
        s = score(f)
        if "JevBench" in s["benchmarks"]:
            external[d.name] = {"benchmarks": {k: v["headline"] for k, v in s["benchmarks"].items()},
                                "ece": {k: v["top1_ece"] for k, v in s["benchmarks"].items()},
                                "ece_mean": s["top1_ece_mean"]}

kl, d1 = panels["knowline-sgl-panel"]["benchmarks"], panels["gd-kl2-s1000-a0.5-panel"]["benchmarks"]
k1 = panels["gd-kl1-s1155-a0.5-panel"]["benchmarks"]
per_bench = sorted(({"id": i, "name": names.get(i, i), "knowline": kl[i], "gd_kl1_a05": k1[i], "decide1": d1[i],
                     "delta_pts": round((d1[i] - kl[i]) * 100, 2)} for i in d1), key=lambda r: r["delta_pts"])

out = {
    "decide1": "0.5 x gd-kl2 export-1000 + 0.5 x KnowLine-31B-Gen1.5 (runs/merges/gd-kl2-s1000-a0.5)",
    "runs": {"gd-kl1": run("gd-kl1", "v1-knowline"), "gd-kl2": run("gd-kl2", "kl2")},
    "panels": panels, "per_benchmark_decide1_vs_knowline": per_bench, "external": external,
    "vendor_reported": {
        "Gemini Decision 1": {"JevBench": 92.2, "Amazon ESCI": 58.7, "New Yorker": 79.7, "PubMedQA": 79.8,
                              "Global-MMLU-Lite": 86.0, "When2Call": 79.9, "ece_mean_7": 0.025},
        "Jev 1.14": {"JevBench": 90.0, "Amazon ESCI": 56.7, "New Yorker": 72.0, "PubMedQA": 78.2,
                     "Global-MMLU-Lite": 85.0, "When2Call": 82.0, "ece_mean_7": 0.049},
        "pplx-decider-v1.2 model card DI 0.3": 68.09, "KnowLine-31B-Gen1.5 card DI 0.3 (self-run)": 70.50},
}
json.dump(out, open(HERE / "data.json", "w"), indent=1)
print("wrote", HERE / "data.json")
