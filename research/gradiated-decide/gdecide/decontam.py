"""Remove training rows that overlap any Decision Index suite row, and apply per-source licence filters.

    python -m gdecide.decontam --suite SUITE_DIR --inputs 'data/hub/*.jsonl.gz' 'data/splits/*.jsonl.gz' --out data/clean

A training row is dropped when its normalized state equals a suite state, or when any word 13-gram of its text
(state, instructions and option descriptions) appears in the text of any suite row (all editions' rows, excluded
ones included). Suite n-grams that occur in more than ``--common`` distinct suite rows (boilerplate such as shared
instructions) are ignored so that format alone does not count as overlap. Rows authored by models whose terms
forbid training competing models are dropped (``--exclude-authors``).
"""

from __future__ import annotations

import argparse
import glob
import gzip
import hashlib
import json
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

N = 13
WORD = re.compile(r"[a-z0-9]+")
MASK = (1 << 61) - 1
BASE = 1_000_003
_SUITE: np.ndarray | None = None
_STATES: set[int] | None = None


def words(text: str) -> list[str]:
    return WORD.findall(text.lower())


def flat(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(f"{k} {flat(v)}" for k, v in value.items())
    if isinstance(value, list):
        return " ".join(flat(v) for v in value)
    return "" if value is None else str(value)


def text_of(row: dict) -> str:
    parts = [flat(row.get("state"))]
    for q in row.get("questions", {}).values():
        parts.append(flat(q.get("instructions")))
        parts.append(flat(q.get("criteria")))
    return " ".join(parts)


def token_hash(w: str) -> int:
    return int.from_bytes(hashlib.blake2b(w.encode(), digest_size=8).digest(), "little") & MASK


def grams(text: str) -> np.ndarray:
    toks = words(text)
    if len(toks) < N:
        return np.zeros(0, dtype=np.uint64)
    h = np.array([token_hash(t) for t in toks], dtype=np.uint64)
    out = np.zeros(len(toks) - N + 1, dtype=np.uint64)
    for j in range(N):
        out = (out * np.uint64(BASE) + h[j : len(toks) - N + 1 + j]) & np.uint64(MASK)
    return np.unique(out)


def state_key(row: dict) -> int:
    return token_hash(" ".join(words(flat(row.get("state")))))


def suite_job(lines: list[str]):
    keys, gs = [], []
    for line in lines:
        row = json.loads(line)
        if words(flat(row.get("state"))):
            keys.append(state_key(row))
        gs.append(grams(text_of(row)))
    return keys, gs


def init(path: str) -> None:
    global _SUITE, _STATES
    data = np.load(path)
    _SUITE = data["grams"]
    _STATES = set(int(x) for x in data["states"])


def check_job(job: tuple[str, list[str], list[str]]):
    _, lines, exclude_authors = job
    keep, reasons = [], {}
    for line in lines:
        row = json.loads(line)
        author = (row.get("meta") or {}).get("author_family")
        if author is not None and author in exclude_authors:
            reasons["author"] = reasons.get("author", 0) + 1
            continue
        if words(flat(row.get("state"))) and state_key(row) in _STATES:
            reasons["state_match"] = reasons.get("state_match", 0) + 1
            continue
        g = grams(text_of(row))
        if g.size:
            idx = np.searchsorted(_SUITE, g)
            idx[idx >= _SUITE.size] = 0
            if np.any(_SUITE[idx] == g):
                reasons["ngram13"] = reasons.get("ngram13", 0) + 1
                continue
        keep.append(line)
    return keep, reasons


def lines_of(path: str):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        yield from f


def chunks(it, size):
    buf = []
    for x in it:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--pools", nargs="*", default=[], help="extra eval-side files (the kit's normalized test pools)")
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--common", type=int, default=50)
    parser.add_argument("--exclude-authors", nargs="*", default=["openai", "anthropic", "google", "unknown", "mixed"])
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    index = out / "suite-ngrams.npz"
    if not index.exists():
        suite_files = sorted(glob.glob(str(Path(args.suite) / "*rows.jsonl.gz"))) + sorted(f for p in args.pools for f in glob.glob(p))
        all_grams, states = [], []
        with ProcessPoolExecutor(args.workers) as pool:
            for path in suite_files:
                for keys, gs in pool.map(suite_job, chunks(lines_of(path), 200)):
                    states += keys
                    all_grams += gs
        stacked = np.concatenate(all_grams) if all_grams else np.zeros(0, dtype=np.uint64)
        values, freq = np.unique(stacked, return_counts=True)
        kept = values[freq <= args.common]
        np.savez(index, grams=kept, states=np.array(sorted(set(states)), dtype=np.uint64))
        print(json.dumps({"suite_files": suite_files, "suite_ngrams": int(values.size), "kept_ngrams": int(kept.size), "suite_states": len(set(states))}), flush=True)
    report = {}
    with ProcessPoolExecutor(args.workers, initializer=init, initargs=(str(index),)) as pool:
        for pattern in args.inputs:
            for path in sorted(glob.glob(pattern)):
                name = Path(path).name
                target = out / (name if name.endswith(".gz") else name + ".gz")
                kept_n, total, reasons = 0, 0, {}
                with gzip.open(target, "wt") as f:
                    jobs = ((name, c, args.exclude_authors) for c in chunks(lines_of(path), 500))
                    for keep, r in pool.map(check_job, jobs):
                        total += len(keep) + sum(r.values())
                        kept_n += len(keep)
                        f.writelines(keep)
                        for k, v in r.items():
                            reasons[k] = reasons.get(k, 0) + v
                report[name] = {"rows": total, "kept": kept_n, "dropped": reasons}
                print(json.dumps({name: report[name]}), flush=True)
    (out / "decontam-report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
