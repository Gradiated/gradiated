"""A learned gate for a two-model ensemble: per question, how much to trust model B (KnowLine) over model A (Qwen).

The pooled answer is ``w * p_B + (1 - w) * p_A`` (linear pooling, as in ``gdecide.ensemble``), then sharpened or
flattened by a fitted temperature: ``p ∝ pool^(1/T)``. ``w = sigmoid(theta . x)``, or a one-hidden-layer MLP, from
features of the two answers (each model's top probability, normalized entropy and margin; whether they agree and
their Jensen-Shannon divergence) and of the request (question type, number of options, state length, number of
questions, share of non-ASCII text). No benchmark or source identity is a feature, so the gate has to learn *when*
each model is better from the answers and the input, not *which benchmark* this is.

Training rows are gold decisions neither model was tuned on by us: the held-out part of every source of the
training mix (rows the dev fraction kept back or the per-source cap left out) and the extra licence-checked sources
that no Gradiated Decide run trained on. The Decision Index rows are never used to fit; they are the test.

    python -m gdecide.gate rows --mix mixes/v1.json --extra DIR --per-source 1500 --out gate-items.jsonl
    (run gdecide.external run on gate-items.jsonl for both models)
    python -m gdecide.gate fit --items gate-items.jsonl --a RUN_A --b RUN_B --out gate.json
    python -m gdecide.gate apply --gate gate.json --suite SUITE_DIR --a DI_RUN_A --b DI_RUN_B --out RUN_DIR
"""

from __future__ import annotations

import argparse
import glob
import gzip
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import numpy as np

EPS = 1e-9
FEATURES = ["bias", "a_top", "b_top", "a_ent", "b_ent", "a_margin", "b_margin", "agree", "js", "top_diff",
            "noul", "choice", "score", "log_options", "log_state_chars", "log_questions", "non_ascii"]


# ----------------------------------------------------------------------------------------------- held-out gold rows

def h(text: str) -> float:  # the same hash gdecide.prepare samples with
    return int(hashlib.sha256(text.encode()).hexdigest()[:12], 16) / 16**12


def read_lines(pattern: str):
    for path in sorted(glob.glob(pattern)):
        with gzip.open(path, "rt") if path.endswith(".gz") else open(path) as f:
            yield from (line for line in f if line.strip())


def gold_key(question: dict, expected) -> str | None:
    """The gold option of a question (the most probable one for soft targets)."""
    t = question.get("type")
    if t == "noul":
        if isinstance(expected, dict):
            expected = expected.get("true", 0.0)
        if isinstance(expected, bool):
            return "true" if expected else "false"
        if isinstance(expected, (int, float)):
            return None if abs(expected - 0.5) < 1e-6 else ("true" if expected > 0.5 else "false")
        if isinstance(expected, str):
            return "true" if expected.lower() in ("true", "yes") else "false"
        return None
    if isinstance(expected, dict):
        return str(max(expected, key=expected.get)) if expected else None
    if isinstance(expected, list):
        return str(int(np.argmax(expected))) if expected else None
    return None if expected is None else str(expected)


def rows(args) -> None:
    """Held-out gold rows from every mix source (and extra sources), ``--per-source`` per row ``source`` field."""
    mix = json.loads(Path(args.mix).read_text())
    seed, dev_fraction = mix.get("seed", 0), mix.get("dev_fraction", 0.01)
    sources = [(src["glob"], src.get("max_rows"), True) for src in mix["sources"]]
    if args.extra:
        sources += [(str(p), None, False) for p in sorted(Path(args.extra).glob("*.jsonl.gz"))]
    rng = random.Random(args.seed)
    out, counts = [], defaultdict(int)
    for pattern, cap, trained in sources:
        lines = []
        for line in read_lines(pattern):
            row = json.loads(line)
            lines.append((h(f"{seed}:{row.get('source')}:{row.get('id')}:{line[:200]}"), line))
        lines.sort()
        if trained:  # gdecide.prepare trained on kept[n_dev:]; the dev rows and everything past the cap are held out
            kept = lines[:cap] if cap else lines
            n_dev = max(1, int(len(kept) * dev_fraction)) if kept and dev_fraction else 0
            held = kept[:n_dev] + lines[len(kept):]
        else:
            held = lines
        by_source = defaultdict(list)
        for _, line in held:
            by_source[json.loads(line).get("source") or Path(pattern).name].append(line)
        for name, group in sorted(by_source.items()):
            rng.shuffle(group)
            for line in group[: args.per_source]:
                row = json.loads(line)
                golds = {qid: gold_key(q, row["expected"].get(qid)) for qid, q in row["questions"].items()}
                golds = {k: v for k, v in golds.items() if v is not None}
                if not golds:
                    continue
                out.append({"bench": name, "id": f"{name}:{row.get('id')}", "trained_source": trained,
                            "request": {"state": row["state"], "questions": row["questions"]}, "golds": golds,
                            "target": {k: row["expected"][k] for k in golds}})
                counts[name] += 1
    with open(args.out, "w") as f:
        for item in out:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(json.dumps({"items": len(out), "sources": len(counts), "per_source": dict(sorted(counts.items()))}))


# ------------------------------------------------------------------------------------------------------- features

def text_of(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def entropy(p: dict) -> float:
    return -sum(v * math.log(max(v, EPS)) for v in p.values())


def features(pa: dict, pb: dict, question: dict, state, n_questions: int) -> list[float]:
    k = max(len(pa), 2)
    def stats(p):
        vals = sorted(p.values(), reverse=True)
        return vals[0], entropy(p) / math.log(k), vals[0] - (vals[1] if len(vals) > 1 else 0.0)
    a_top, a_ent, a_margin = stats(pa)
    b_top, b_ent, b_margin = stats(pb)
    m = {key: 0.5 * pa.get(key, 0) + 0.5 * pb.get(key, 0) for key in pa}
    js = 0.5 * sum(pa[x] * math.log(max(pa[x], EPS) / max(m[x], EPS)) for x in pa) + \
        0.5 * sum(pb.get(x, 0) * math.log(max(pb.get(x, 0), EPS) / max(m[x], EPS)) for x in pa)
    text = text_of(state) + text_of(question.get("instructions") or "")
    t = question.get("type")
    return [1.0, a_top, b_top, a_ent, b_ent, a_margin, b_margin, float(max(pa, key=pa.get) == max(pb, key=pb.get)),
            js / math.log(2), a_top - b_top, float(t == "noul"), float(t == "choice"), float(t == "score"),
            math.log(k), math.log1p(len(text)) / 10, math.log(max(n_questions, 1)),
            sum(ord(c) > 127 for c in text[:4000]) / max(1, min(len(text), 4000))]


def soft_target(question: dict, target, keys: list[str]) -> np.ndarray:
    t = np.zeros(len(keys))
    if question.get("type") == "noul" and isinstance(target, (int, float)) and not isinstance(target, bool):
        t[keys.index("true")], t[keys.index("false")] = float(target), 1 - float(target)
    elif isinstance(target, dict) and all(isinstance(v, (int, float)) for v in target.values()):
        for key, v in target.items():
            if str(key) in keys:
                t[keys.index(str(key))] = float(v)
    elif isinstance(target, list) and question.get("type") == "score" and len(target) == len(keys):
        t = np.asarray(target, dtype=float)
    if t.sum() <= 0:
        g = gold_key(question, target)
        if g in keys:
            t[keys.index(g)] = 1.0
    return t / t.sum() if t.sum() > 0 else t


# ---------------------------------------------------------------------------------------------------------- fitting

class Gate:
    """w = sigmoid(MLP(x)) (hidden=0: logistic), temperature T > 0 shared across questions."""

    def __init__(self, n: int, hidden: int = 0, seed: int = 0):
        r = np.random.default_rng(seed)
        self.hidden = hidden
        if hidden:
            self.W1 = r.normal(0, 0.3, (n, hidden))
            self.w2 = r.normal(0, 0.3, hidden)
        else:
            self.theta = np.zeros(n)
        self.log_t = 0.0
        self.mean, self.std = np.zeros(n), np.ones(n)

    def params(self):
        return [self.W1, self.w2] if self.hidden else [self.theta]

    def logit(self, X):
        Z = (X - self.mean) / self.std
        Z[:, 0] = 1.0
        if self.hidden:
            H = np.tanh(Z @ self.W1)
            return H @ self.w2, (Z, H)
        return Z @ self.theta, (Z, None)

    def weight(self, X):
        return 1 / (1 + np.exp(-np.clip(self.logit(X)[0], -30, 30)))

    def to_json(self):
        d = {"features": FEATURES, "hidden": self.hidden, "log_t": self.log_t, "mean": self.mean.tolist(),
             "std": self.std.tolist()}
        if self.hidden:
            d.update(W1=self.W1.tolist(), w2=self.w2.tolist())
        else:
            d["theta"] = self.theta.tolist()
        return d

    @classmethod
    def from_json(cls, d):
        g = cls(len(d["mean"]), d["hidden"])
        g.log_t, g.mean, g.std = d["log_t"], np.array(d["mean"]), np.array(d["std"])
        if g.hidden:
            g.W1, g.w2 = np.array(d["W1"]), np.array(d["w2"])
        else:
            g.theta = np.array(d["theta"])
        return g


def pooled(pa: np.ndarray, pb: np.ndarray, w, log_t: float) -> np.ndarray:
    p = np.maximum(w * pb + (1 - w) * pa, EPS) ** math.exp(-log_t)
    return p / p.sum()


class Batch:
    """Questions padded to the widest option count: X [n, f], PA / PB / T [n, k], mask [n, k]."""

    def __init__(self, data):
        k = max(len(d[1]) for d in data)
        n = len(data)
        self.X = np.array([d[0] for d in data])
        self.PA, self.PB, self.T = np.zeros((n, k)), np.zeros((n, k)), np.zeros((n, k))
        self.mask = np.zeros((n, k), dtype=bool)
        for i, (_, pa, pb, t) in enumerate(data):
            m = len(pa)
            self.PA[i, :m], self.PB[i, :m], self.T[i, :m], self.mask[i, :m] = pa, pb, t, True


def pooled_batch(b: Batch, w: np.ndarray, log_t: float):
    """-> (q [n, k] pooled and tempered, mix [n, k], logmix [n, k]); padding gets probability 0."""
    w = np.broadcast_to(np.asarray(w, dtype=float), (len(b.X),))[:, None]
    mix = np.where(b.mask, np.maximum(w * b.PB + (1 - w) * b.PA, EPS), 1.0)
    logmix = np.log(mix)
    z = np.where(b.mask, math.exp(-log_t) * logmix, -np.inf)
    z -= z.max(1, keepdims=True)
    q = np.exp(z)
    q /= q.sum(1, keepdims=True)
    return q, mix, logmix


def nll(gate: Gate, b: Batch, l2: float):
    """Mean soft cross-entropy of the pooled answers and its gradients (theta or MLP, and log T)."""
    s, (Z, H) = gate.logit(b.X)
    w = 1 / (1 + np.exp(-np.clip(s, -30, 30)))
    inv_t = math.exp(-gate.log_t)
    q, mix, logmix = pooled_batch(b, w, gate.log_t)
    n = len(b.X)
    loss = -float(np.sum(b.T * np.log(np.maximum(q, EPS)))) / n
    g = np.where(b.mask, q - b.T, 0.0)  # d loss / d (inv_t * log mix)
    dw = inv_t * np.sum(g * np.where(b.mask, (b.PB - b.PA) / mix, 0.0), 1)
    dlogt = -inv_t * float(np.sum(g * np.where(b.mask, logmix, 0.0))) / n
    ds = dw * w * (1 - w) / n
    if gate.hidden:
        g2 = H.T @ ds + l2 * gate.w2
        dH = np.outer(ds, gate.w2) * (1 - H**2)
        grads = [Z.T @ dH + l2 * gate.W1, g2]
        reg = 0.5 * l2 * (np.sum(gate.W1**2) + np.sum(gate.w2**2))
    else:
        grads = [Z.T @ ds + l2 * np.r_[0, gate.theta[1:]]]
        reg = 0.5 * l2 * np.sum(gate.theta[1:] ** 2)
    return loss + reg, grads, dlogt


def train(data, hidden: int = 0, l2: float = 1e-3, steps: int = 300, lr: float = 0.05, seed: int = 0) -> Gate:
    b = data if isinstance(data, Batch) else Batch(data)
    gate = Gate(b.X.shape[1], hidden, seed)
    gate.mean, gate.std = b.X.mean(0), b.X.std(0) + 1e-6
    gate.mean[0], gate.std[0] = 0.0, 1.0
    ps = gate.params()
    m = [np.zeros_like(p) for p in ps] + [0.0]
    v = [np.zeros_like(p) for p in ps] + [0.0]
    for step in range(1, steps + 1):  # Adam, full batch
        _, grads, glt = nll(gate, b, l2)
        grads = grads + [glt]
        for i, g in enumerate(grads):
            m[i] = 0.9 * m[i] + 0.1 * g
            v[i] = 0.999 * v[i] + 0.001 * g * g
            upd = lr * (m[i] / (1 - 0.9**step)) / (np.sqrt(v[i] / (1 - 0.999**step)) + 1e-8)
            if i < len(ps):
                ps[i] -= upd
            else:
                gate.log_t -= float(upd)
    return gate


def evaluate(data, w, log_t: float = 0.0) -> dict:
    b = data if isinstance(data, Batch) else Batch(data)
    q, _, _ = pooled_batch(b, w, log_t)
    loss = -float(np.sum(b.T * np.log(np.maximum(q, EPS)))) / len(b.X)
    pick = np.argmax(q, 1)
    acc = float(np.mean(b.T[np.arange(len(b.X)), pick] == b.T.max(1)))
    return {"nll": round(loss, 4), "acc": round(100 * acc, 2)}


def load_external(run: str) -> dict:
    out = {}
    for path in sorted(Path(run).glob("predictions-*.jsonl")):
        for line in open(path):
            r = json.loads(line)
            if "answers" in r:
                out[r["id"]] = r["answers"]
    return out


def gate_data(items_path: str, run_a: str, run_b: str):
    A, B = load_external(run_a), load_external(run_b)
    data, groups = [], []
    for line in open(items_path):
        it = json.loads(line)
        a, b = A.get(it["id"]), B.get(it["id"])
        if not a or not b:
            continue
        qs = it["request"]["questions"]
        for qid in it["golds"]:
            if qid not in a or qid not in b or set(a[qid]) != set(b[qid]):
                continue
            keys = list(a[qid])
            pa = np.array([a[qid][k] for k in keys])
            pb = np.array([b[qid][k] for k in keys])
            t = soft_target(qs[qid], it["target"][qid], keys)
            if t.sum() == 0:
                continue
            data.append((features(a[qid], b[qid], qs[qid], it["request"]["state"], len(qs)), pa, pb, t))
            groups.append(it["bench"])
    return data, groups


def fit(args) -> None:
    data, groups = gate_data(args.items, args.a, args.b)
    names = sorted(set(groups))
    rng = random.Random(0)
    rng.shuffle(names)
    folds = [set(names[i:: args.folds]) for i in range(args.folds)]
    report = {"questions": len(data), "sources": len(names), "cv": "leave-sources-out, %d folds" % args.folds}
    configs = {"logistic": dict(hidden=0), "mlp16": dict(hidden=16)}
    cv = defaultdict(lambda: defaultdict(list))
    for fold in folds:
        train_idx = [i for i, g in enumerate(groups) if g not in fold]
        test_idx = [i for i, g in enumerate(groups) if g in fold]
        if not test_idx:
            continue
        tr, te = Batch([data[i] for i in train_idx]), Batch([data[i] for i in test_idx])
        cv["A"]["fold"].append(evaluate(te, 0.0))
        cv["B"]["fold"].append(evaluate(te, 1.0))
        cv["50/50"]["fold"].append(evaluate(te, 0.5))
        best_w = min((evaluate(tr, w)["nll"], w) for w in np.linspace(0, 1, 21))[1]
        cv[f"global w (train)"]["fold"].append(evaluate(te, best_w))
        for name, cfg in configs.items():
            g = train(tr, **cfg, l2=args.l2, steps=args.steps)
            cv[name]["fold"].append(evaluate(te, g.weight(te.X), g.log_t))
    # Pooled over folds, weighted by questions.
    sizes = [sum(1 for g in groups if g in fold) for fold in folds]
    for name, d in cv.items():
        f = d["fold"]
        report[name] = {k: round(sum(x[k] * s for x, s in zip(f, sizes)) / sum(sizes), 4) for k in ("nll", "acc")}
    choice = min(configs, key=lambda c: report[c]["nll"])
    gate = train(data, **configs[choice], l2=args.l2, steps=args.steps)
    w = gate.weight(Batch(data).X)
    report["chosen"] = choice
    report["final"] = {"w_mean": round(float(w.mean()), 3), "w_p10": round(float(np.quantile(w, 0.1)), 3),
                       "w_p90": round(float(np.quantile(w, 0.9)), 3), "temperature": round(math.exp(gate.log_t), 3)}
    if not gate.hidden:
        report["final"]["theta"] = dict(zip(FEATURES, [round(float(x), 3) for x in gate.theta]))
    Path(args.out).write_text(json.dumps({"gate": gate.to_json(), "report": report}, indent=1))
    print(json.dumps(report, indent=1))


# --------------------------------------------------------------------------------------------------------- applying

def apply(args) -> None:
    from gdecide.ensemble import distribution, read_run

    gate = Gate.from_json(json.loads(Path(args.gate).read_text())["gate"])
    suite = {}
    for name in ("selected-rows.jsonl.gz", "added-rows.jsonl.gz"):
        for line in gzip.open(Path(args.suite) / name, "rt"):
            r = json.loads(line)
            suite[r["_evaluation"]["run_id"]] = (r["state"], r["questions"])
    A, B = read_run(args.a), read_run(args.b)
    out, ws = [], []
    for rid, ra in A.items():
        rb = B.get(rid)
        if rid not in suite or ra.get("status") != "ok" or not rb or rb.get("status") != "ok":
            out.append(ra if ra.get("status") == "ok" or not rb else rb)
            continue
        state, qs = suite[rid]
        answers = {}
        for qid, aa in ra["response"]["answers"].items():
            ab = rb["response"]["answers"].get(qid)
            try:
                da, db = distribution(aa), distribution(ab) if ab else None
            except ValueError:
                db = None
            if db is None or set(da) != set(db) or qid not in qs:
                answers[qid] = aa
                continue
            keys = list(da)
            w = float(gate.weight(np.array([features(da, db, qs[qid], state, len(qs))]))[0])
            ws.append(w)
            p = pooled(np.array([da[k] for k in keys]), np.array([db[k] for k in keys]), w, gate.log_t)
            probs = dict(zip(keys, p.tolist()))
            t = aa["type"]
            if t == "noul":
                answers[qid] = {"type": "noul", "noul": probs["true"]}
            else:
                ans = {"type": t, "probabilities": probs}
                if t == "choice":
                    ans["choice"] = max(sorted(probs), key=probs.get)
                else:
                    ans["score"] = sum(int(k) * v for k, v in probs.items())
                answers[qid] = ans
        out.append({**{k: v for k, v in ra.items() if k not in ("response",)}, "engine": "gradiated-decide:gated",
                    "response": {"model": "gradiated-decide:gated", "answers": answers}})
    for rid, rb in B.items():
        if rid not in A:
            out.append(rb)
    d = Path(args.out)
    d.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in out)
    (d / "results-0.jsonl").write_text(text)
    (d / "results.jsonl").write_text(text)
    summary = {"gate": args.gate, "a": args.a, "b": args.b, "rows": len(out), "questions_gated": len(ws),
               "w_mean": round(float(np.mean(ws)), 3) if ws else None}
    (d / "ensemble.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("rows")
    r.add_argument("--mix", required=True)
    r.add_argument("--extra", help="directory of extra-source .jsonl.gz files no run trained on")
    r.add_argument("--per-source", type=int, default=1500)
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--out", required=True)
    f = sub.add_parser("fit")
    f.add_argument("--items", required=True)
    f.add_argument("--a", required=True, help="gdecide.external run of model A (weight 1 - w)")
    f.add_argument("--b", required=True, help="gdecide.external run of model B (weight w)")
    f.add_argument("--folds", type=int, default=5)
    f.add_argument("--l2", type=float, default=1e-3)
    f.add_argument("--steps", type=int, default=300)
    f.add_argument("--out", required=True)
    a = sub.add_parser("apply")
    a.add_argument("--gate", required=True)
    a.add_argument("--suite", required=True)
    a.add_argument("--a", required=True)
    a.add_argument("--b", required=True)
    a.add_argument("--out", required=True)
    args = parser.parse_args()
    {"rows": rows, "fit": fit, "apply": apply}[args.command](args)


if __name__ == "__main__":
    main()
