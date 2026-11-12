"""Mix training sources, augment, tokenize once and write shards for ``gdecide.train_full``.

    python -m gdecide.prepare --checkpoint CKPT --mix mix.json --out DATA_DIR [--workers 32] [--family gemma]

``mix.json``: {"seed": int, "dev_fraction": 0.01, "max_length": 8192,
               "sources": [{"glob": "data/hub/*.jsonl.gz", "max_rows": 100000, "weight": 1.0,
                            "exclude": ["substring of the row's source, id or metadata", ...]}, ...]}
Rows come from the hub and train-split builders (state, questions, expected, source). Each source is
sampled deterministically (hash of the row id) down to ``max_rows``. Choice questions have their options
permuted with probability ``shuffle`` (keys keep their descriptions, so the target is unchanged); this removes
position shortcuts. ``--family gemma`` encodes for KnowLine checkpoints instead (``gdecide.prepare_knowline``: one
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

    lines, max_length, shuffle_p, weight = job
    out, dropped = [], {}
    for line in lines:
        row = json.loads(line)
        rng = random.Random(str(row.get("id")) + row.get("source", ""))
        row = shuffled(row, rng, shuffle_p)
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
        for r in range(repeat):
            lines = [line for _, line in train]
            for i in range(0, len(lines), 500):
                train_jobs.append((lines[i : i + 500], max_length, shuffle_p if r == 0 else 1.0, weight))
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
