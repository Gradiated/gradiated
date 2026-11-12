"""Mix training sources, augment, tokenize once and write shards for ``gdecide.train_full``.

    python -m gdecide.prepare --checkpoint CKPT --mix mix.json --out DATA_DIR [--workers 32] [--family gemma]

``mix.json``: {"seed": int, "dev_fraction": 0.01, "max_length": 8192,
               "sources": [{"glob": "data/hub/*.jsonl.gz", "max_rows": 100000, "weight": 1.0,
                            "exclude": ["substring of the row's source, id or metadata", ...],
                            "augment": {...per-source override...}}, ...],
               "augment": {"reserialize": 0.3, "abstain": 0.15, "abstain_remove": 0.5}}
Rows come from the hub and train-split builders (state, questions, expected, source). Each source is
sampled deterministically (hash of the row id) down to ``max_rows``. Choice questions have their options
permuted with probability ``shuffle`` (keys keep their descriptions, so the target is unchanged); this removes
position shortcuts. ``augment`` (training rows only, dev rows are never augmented) adds mammoth-1's report's
abstention augmentation (``abstain``: a "none of these / cannot tell" option on choice questions with a hard target,
and with ``abstain_remove`` the correct option is dropped so "none" is the target) and ``reserialize`` (JSON-object
states written in a random text layout). ``--family gemma`` encodes for KnowLine checkpoints instead (``gdecide.prepare_knowline``: one
example per question, KnowLine's own prompts). A ``dev_fraction`` of every source is held out for per-source dev loss. Output:
``train-<k>.pt`` / ``dev.pt`` lists of {"ids", "markers", "counts", "targets", "source", "weight"} and a manifest.
"""

from __future__ import annotations

import argparse
import glob
import gzip
import hashlib
import json
import random
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

_ENCODER = None


def h(text: str) -> float:
    return int(hashlib.sha256(text.encode()).hexdigest()[:12], 16) / 16**12


def shuffled(row: dict, rng: random.Random, p: float) -> dict:
    questions = {}
    for key, q in row["questions"].items():
        if q.get("type") == "choice" and isinstance(q.get("criteria"), dict) and len(q["criteria"]) > 1 and rng.random() < p:
            items = list(q["criteria"].items())
            rng.shuffle(items)
            q = {**q, "criteria": dict(items)}
        questions[key] = q
    return {**row, "questions": questions}


NONE_KEY = "none"
NONE_TEXTS = (
    "None of the other options is correct, or it cannot be determined from the information given.",
    "None of the above: no listed option fits, or the information is not enough to decide.",
    "Cannot tell: the answer is not among the other options or the state does not settle it.",
)
ABSTAIN_WORDS = ("none", "other", "unknown", "cannot", "can't", "not sure", "neither", "n/a", "unsure", "oos", "out of scope")


def _hard_key(question: dict, expected):
    """The option key a choice target puts (almost) all its mass on, else None."""
    if isinstance(expected, dict):
        total = sum(float(v) for v in expected.values())
        if total <= 0:
            return None
        key, mass = max(expected.items(), key=lambda kv: float(kv[1]))
        return str(key) if float(mass) / total >= 0.9 else None
    return str(expected) if expected is not None and not isinstance(expected, (bool, int, float)) else None


def abstain(row: dict, rng: random.Random, p: float, remove: float) -> dict:
    """mammoth-style abstention: add a "none" option to choice questions with a hard target (probability ``p``);
    with probability ``remove`` the correct option is also dropped and "none" becomes the target. Questions that
    already offer an abstain-like option are left alone."""
    questions, expected = dict(row["questions"]), dict(row.get("expected", {}))
    changed = False
    for key, q in row["questions"].items():
        crit = q.get("criteria")
        if q.get("type") != "choice" or not isinstance(crit, dict) or len(crit) < 2 or NONE_KEY in crit or rng.random() >= p:
            continue
        text = " ".join([*map(str, crit), *(str(v) for v in crit.values() if v)]).lower()
        if any(w in text for w in ABSTAIN_WORDS):
            continue
        gold = _hard_key(q, expected.get(key))
        if gold is None or gold not in crit:
            continue
        items = list(crit.items())
        target = gold
        if len(crit) >= 3 and rng.random() < remove:
            items = [(k, v) for k, v in items if k != gold]
            target = NONE_KEY
        items.insert(rng.randrange(len(items) + 1), (NONE_KEY, rng.choice(NONE_TEXTS)))
        questions[key] = {**q, "criteria": dict(items)}
        expected[key] = target
        changed = True
    return {**row, "questions": questions, "expected": expected} if changed else row


def reserialize(row: dict, rng: random.Random, p: float) -> dict:
    """Write a JSON-object state as text in a random layout (probability ``p``), so the model does not key on one
    serialisation. Text states are left alone."""
    state = row.get("state")
    if not isinstance(state, dict) or rng.random() >= p:
        return row
    style = rng.randrange(4)
    if style == 0:
        text = json.dumps(state, ensure_ascii=False, indent=2)
    elif style == 1:
        text = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    else:
        def value(v):
            return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        bullet = "- " if style == 2 else ""
        text = "\n".join(f"{bullet}{k}: {value(v)}" for k, v in state.items())
    return {**row, "state": text}


def augmented(row: dict, rng: random.Random, shuffle_p: float, aug: dict | None = None) -> dict:
    """Every training-time augmentation, in a fixed order: state layout, abstention, then option order."""
    aug = aug or {}
    row = reserialize(row, rng, float(aug.get("reserialize", 0.0)))
    row = abstain(row, rng, float(aug.get("abstain", 0.0)), float(aug.get("abstain_remove", 0.5)))
    return shuffled(row, rng, shuffle_p)


def init(checkpoint: str) -> None:
    global _ENCODER
    import json as j

    from transformers import AutoProcessor

    from pplx_decider.protocol import Encoder

    config = j.loads((Path(checkpoint) / "decision_config.json").read_text())
    processor = AutoProcessor.from_pretrained(checkpoint)
    _ENCODER = Encoder(processor, config["codes"])


def encode(job: tuple[list[str], int, float, float]):
    import torch

    from gdecide.train import target_distribution

    lines, max_length, shuffle_p, weight, *rest = job
    aug = rest[0] if rest else {}
    out, dropped = [], {}
    for line in lines:
        row = json.loads(line)
        rng = random.Random(str(row.get("id")) + row.get("source", ""))
        row = augmented(row, rng, shuffle_p, aug)
        request = {"state": row["state"], "questions": row["questions"]}
        try:
            _ENCODER.validate(request)
            enc = _ENCODER.encode(request)
        except Exception as exc:
            dropped[type(exc).__name__] = dropped.get(type(exc).__name__, 0) + 1
            continue
        if enc.length > max_length:
            dropped["too_long"] = dropped.get("too_long", 0) + 1
            continue
        targets = [target_distribution(q, row.get("expected", {}).get(k)) for k, q in row["questions"].items()]
        if all(t is None for t in targets):
            dropped["no_target"] = dropped.get("no_target", 0) + 1
            continue
        out.append({"ids": enc.input_ids.tolist(), "markers": enc.markers.tolist(), "counts": enc.counts, "targets": targets, "source": row.get("source", "?"), "weight": weight * float(row.get("weight", 1.0))})
    return out, dropped


def tensorize(row: dict) -> dict:
    import torch

    return {**row, "ids": torch.tensor(row["ids"], dtype=torch.int32), "markers": torch.tensor(row["markers"], dtype=torch.int32)}


def read_lines(pattern: str):
    for path in sorted(glob.glob(pattern)):
        opener = gzip.open if path.endswith(".gz") else open
        with opener(path, "rt") as f:
            yield from f


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--mix", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--shard-rows", type=int, default=50000)
    parser.add_argument("--family", choices=("qwen", "gemma"), default="qwen")
    args = parser.parse_args()
    import torch

    mix = json.loads(Path(args.mix).read_text())
    seed, dev_fraction, max_length = mix.get("seed", 0), mix.get("dev_fraction", 0.01), mix.get("max_length", 8192)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    train_jobs, dev_jobs, manifest = [], [], {"mix": mix, "sources": []}
    for src in mix["sources"]:
        rows = []
        exclude = src.get("exclude", [])
        for line in read_lines(src["glob"]):
            row = json.loads(line)
            origin = f"{row.get('source')} {row.get('id')} {json.dumps(row.get('metadata', row.get('meta', {})))}"
            if any(x in origin for x in exclude):
                continue
            rows.append((h(f"{seed}:{row.get('source')}:{row.get('id')}:{line[:200]}"), line))
        rows.sort()
        cap = src.get("max_rows")
        kept = rows[:cap] if cap else rows
        n_dev = max(1, int(len(kept) * dev_fraction)) if kept and dev_fraction else 0
        dev, train = kept[:n_dev], kept[n_dev:]
        repeat = int(src.get("repeat", 1))
        weight = float(src.get("weight", 1.0))
        shuffle_p = float(src.get("shuffle", mix.get("shuffle", 0.5)))
        aug = {**mix.get("augment", {}), **src.get("augment", {})}
        for r in range(repeat):
            lines = [line for _, line in train]
            for i in range(0, len(lines), 500):
                train_jobs.append((lines[i : i + 500], max_length, shuffle_p if r == 0 else 1.0, weight, aug))
        for i in range(0, len(dev), 500):
            dev_jobs.append(([line for _, line in dev[i : i + 500]], max_length, 0.0, 1.0))
        manifest["sources"].append({**src, "available": len(rows), "train": len(train) * repeat, "dev": len(dev)})
        print(json.dumps(manifest["sources"][-1]), flush=True)

    dropped: dict[str, int] = {}
    if args.family == "gemma":
        from gdecide.prepare_knowline import encode as encode_job, init as init_worker
    else:
        encode_job, init_worker = encode, init
    manifest["family"] = args.family
    with ProcessPoolExecutor(args.workers, initializer=init_worker, initargs=(args.checkpoint,)) as pool:
        dev_rows = []
        for rows, d in pool.map(encode_job, dev_jobs):
            dev_rows += [tensorize(r) for r in rows]
        torch.save(dev_rows, out / "dev.pt")
        train_rows = []
        for rows, d in pool.map(encode_job, train_jobs, chunksize=4):
            train_rows += [tensorize(r) for r in rows]
            for k, v in d.items():
                dropped[k] = dropped.get(k, 0) + v
    random.Random(seed).shuffle(train_rows)
    shards = 0
    for i in range(0, len(train_rows), args.shard_rows):
        torch.save(train_rows[i : i + args.shard_rows], out / f"train-{shards:03d}.pt")
        shards += 1
    lengths = sorted(int(r["ids"].numel()) for r in train_rows)
    pct = lambda q: lengths[min(len(lengths) - 1, int(q * len(lengths)))] if lengths else 0
    by_source: dict[str, int] = {}
    for r in train_rows:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
    manifest.update(by_source=by_source, train_rows=len(train_rows), dev_rows=len(dev_rows), shards=shards, dropped=dropped, tokens=sum(lengths), length_percentiles={q: pct(q) for q in (0.5, 0.9, 0.99, 1.0)})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({k: v for k, v in manifest.items() if k != "sources"}), flush=True)


if __name__ == "__main__":
    main()
