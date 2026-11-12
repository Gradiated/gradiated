"""Google's Gemini Decision 1 launch panel (2026-11-11), the text benchmarks we can run, as top-1 accuracy.

Google reported top-1 accuracy (Amazon ESCI: macro-F1) and top-1 ECE over seven shared evals, but did not publish
its prompts, subsets or harness, so these numbers are indicative, not a reproduction. Benchmarks and sources:

- JevBench public split: Benchmark Heaven's 231 public decisions (github.com/fstandhartinger/jevbench, MIT).
- PubMedQA: pqa_labeled, 1,000 expert-labelled yes/no/maybe questions with their abstracts.
- Global-MMLU-Lite, non-English: every language except English, test split.
- Amazon ESCI, When2Call, New Yorker caption matching (text descriptions, so text-only): our Decision Index 0.3
  suite rows. Google's subsets and formulations may differ.

Not run: Mind2Web Multimodal (screenshots), MMAU (audio) and Video-MME (video).

    python -m gdecide.external build --jevbench REPO --suite SUITE_DIR --out items.jsonl
    torchrun --nproc-per-node 8 -m gdecide.external run --items items.jsonl --checkpoint CKPT --out DIR
    python -m gdecide.external score --items items.jsonl --run DIR
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
from collections import defaultdict
from pathlib import Path

JEVBENCH_REVISION = "609a664e81f46e03731600bd7bd9f1b7a61257c5"
PUBMEDQA = ("qiaojin/PubMedQA", "9001f2853fb87cab8d220904e0de81ac6973b318")
GLOBAL_MMLU_LITE = ("CohereLabs/Global-MMLU-Lite", "36c2fd756f19ccf13a9a96c8e53ccecc02192b8b")
SUITE_BENCHMARKS = {"Amazon ESCI": "Amazon ESCI", "When2Call MCQ": "When2Call", "New Yorker caption matching": "New Yorker"}
ORDER = ["JevBench", "Amazon ESCI", "New Yorker", "PubMedQA", "Global-MMLU-Lite", "When2Call"]


def item(bench, id_, state, question, gold):
    return {"bench": bench, "id": id_, "request": {"state": state, "questions": {"q": question}}, "gold": str(gold)}


def jevbench(repo: Path):
    for name in ("original", "easy", "hard"):
        for line in open(repo / "datasets/public" / f"{name}.jsonl"):
            r = json.loads(line)
            q, gold = r["question"], r["expected"]
            if q["type"] == "noul":
                gold = "true" if gold in ("yes", True, "true") else "false"
            yield item("JevBench", r["id"], r["state"], q, gold)


def pubmedqa():
    import pandas as pd
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(PUBMEDQA[0], "pqa_labeled/train-00000-of-00001.parquet", repo_type="dataset",
                           revision=PUBMEDQA[1])
    for r in pd.read_parquet(path).itertuples():
        context = "\n\n".join(f"{label}: {text}" for label, text in zip(r.context["labels"], r.context["contexts"]))
        q = {"type": "choice", "instructions": f"Based on the abstract, answer the research question: {r.question}",
             "criteria": {"yes": "Yes", "no": "No", "maybe": "Maybe: the evidence is inconclusive"}}
        yield item("PubMedQA", f"PubMedQA:{r.pubid}", context, q, r.final_decision)


def global_mmlu_lite():
    import pandas as pd
    from huggingface_hub import HfApi, hf_hub_download

    files = HfApi().list_repo_files(GLOBAL_MMLU_LITE[0], repo_type="dataset", revision=GLOBAL_MMLU_LITE[1])
    for f in sorted(f for f in files if f.endswith("test-00000-of-00001.parquet") and not f.startswith("en/")):
        lang = f.split("/")[0]
        df = pd.read_parquet(hf_hub_download(GLOBAL_MMLU_LITE[0], f, repo_type="dataset", revision=GLOBAL_MMLU_LITE[1]))
        for r in df.itertuples():
            q = {"type": "choice", "instructions": "Choose the correct answer.",
                 "criteria": {k: getattr(r, f"option_{k.lower()}") for k in "ABCD"}}
            yield item("Global-MMLU-Lite", f"Global-MMLU-Lite:{lang}:{r.sample_id}", r.question, q, r.answer)


def suite(suite_dir: Path):
    for name in ("selected-rows.jsonl.gz", "added-rows.jsonl.gz"):
        for line in gzip.open(suite_dir / name, "rt"):
            r = json.loads(line)
            bench = SUITE_BENCHMARKS.get(r["_evaluation"]["dataset"])
            if bench and len(r["questions"]) == 1:
                (key, q), = r["questions"].items()
                yield item(bench, r["id"], r["state"], q, r["expected"][key])


def build(args):
    sources = [jevbench(Path(args.jevbench)), pubmedqa(), global_mmlu_lite(), suite(Path(args.suite))]
    counts = defaultdict(int)
    with open(args.out, "w") as out:
        for source in sources:
            for it in source:
                counts[it["bench"]] += 1
                out.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(json.dumps(counts))


def top(answer):
    """(predicted label, its probability, label -> probability) from a Decider answer."""
    if answer["type"] == "noul":
        p = float(answer["noul"])
        probs = {"true": p, "false": 1 - p}
    else:
        probs = {str(k): float(v) for k, v in answer["probabilities"].items()}
    label = max(probs, key=probs.get)
    return label, probs[label], probs


def run(args):
    import torch

    from gdecide.evaluate import load_decider

    rank, world = int(os.environ.get("RANK", 0)), int(os.environ.get("WORLD_SIZE", 1))
    local = int(os.environ.get("LOCAL_RANK", 0))
    torch.cuda.set_device(local)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"predictions-{rank}.jsonl"
    done = {json.loads(line)["id"] for line in open(path)} if path.exists() else set()
    items = [json.loads(line) for i, line in enumerate(open(args.items)) if i % world == rank]
    items = [it for it in items if it["id"] not in done]
    if args.backend == "knowline":
        from gdecide.backends.knowline import KnowLineDecider
        decider = KnowLineDecider.from_pretrained(args.checkpoint, device=f"cuda:{local}", max_length=args.max_length,
                                                  batch_tokens=args.batch_tokens, temperature=1.0)
    else:
        decider = load_decider(args.checkpoint, None, f"cuda:{local}", args.max_length, args.batch_tokens)
    with open(path, "a") as f:
        for start in range(0, len(items), args.chunk):
            chunk = items[start:start + args.chunk]
            try:
                responses = decider.decide([it["request"] for it in chunk])
            except Exception as error:  # noqa: BLE001  one bad request should not lose the chunk
                responses = []
                for it in chunk:
                    try:
                        responses.append(decider.decide(it["request"]))
                    except Exception as e:  # noqa: BLE001
                        responses.append({"error": f"{type(e).__name__}: {e}"})
                print(json.dumps({"rank": rank, "chunk_error": str(error)[:200]}), flush=True)
            for it, response in zip(chunk, responses):
                record = {"id": it["id"], "bench": it["bench"]}
                if "error" in response:
                    record["error"] = response["error"]
                else:
                    label, p, probs = top(response["answers"]["q"])
                    record.update(pred=label, p=p, probs=probs)
                f.write(json.dumps(record) + "\n")
            f.flush()
            if rank == 0:
                print(json.dumps({"rank": 0, "done": start + len(chunk), "of": len(items)}), flush=True)


def macro_f1(pairs):
    labels = sorted({g for g, _ in pairs})
    f1 = []
    for label in labels:
        tp = sum(g == label and p == label for g, p in pairs)
        fp = sum(g != label and p == label for g, p in pairs)
        fn = sum(g == label and p != label for g, p in pairs)
        f1.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(f1) / len(f1)


def ece(records, bins=15):
    edges = defaultdict(list)
    for conf, correct in records:
        edges[min(int(conf * bins), bins - 1)].append((conf, correct))
    n = len(records)
    return sum(len(b) / n * abs(sum(c for c, _ in b) / len(b) - sum(k for _, k in b) / len(b)) for b in edges.values())


def score(args):
    gold = {}
    for line in open(args.items):
        it = json.loads(line)
        gold[it["id"]] = (it["bench"], it["gold"])
    preds = {}
    for path in sorted(Path(args.run).glob("predictions-*.jsonl")):
        for line in open(path):
            r = json.loads(line)
            preds[r["id"]] = r
    per = defaultdict(list)
    for id_, (bench, g) in gold.items():
        r = preds.get(id_)
        # As in Google's table: anything the model could not answer counts as wrong, over the full benchmark.
        pred, p = (r["pred"], r["p"]) if r and "pred" in r else (None, 0.0)
        per[bench].append((g, pred, p))
    result = {"run": args.run, "benchmarks": {}}
    shared = []
    for bench in ORDER:
        rows = per.get(bench, [])
        if not rows:
            continue
        acc = sum(g == p for g, p, _ in rows) / len(rows)
        entry = {"n": len(rows), "answered": sum(p is not None for _, p, _ in rows), "top1_accuracy": round(100 * acc, 2)}
        if bench == "Amazon ESCI":
            entry["macro_f1"] = round(100 * macro_f1([(g, p) for g, p, _ in rows]), 2)
        entry["headline"] = entry.get("macro_f1", entry["top1_accuracy"])
        entry["top1_ece"] = round(ece([(c, g == p) for g, p, c in rows if p is not None]), 4)
        result["benchmarks"][bench] = entry
        shared.append(entry["top1_ece"])
    result["top1_ece_mean"] = round(sum(shared) / len(shared), 4) if shared else None
    Path(args.run, "external-score.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--jevbench", required=True, help=f"checkout of fstandhartinger/jevbench at {JEVBENCH_REVISION}")
    b.add_argument("--suite", required=True)
    b.add_argument("--out", required=True)
    r = sub.add_parser("run")
    r.add_argument("--items", required=True)
    r.add_argument("--checkpoint", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--backend", choices=["pplx", "knowline"], default="pplx")
    r.add_argument("--max-length", type=int, default=131072)
    r.add_argument("--batch-tokens", type=int, default=32768)
    r.add_argument("--chunk", type=int, default=64)
    s = sub.add_parser("score")
    s.add_argument("--items", required=True)
    s.add_argument("--run", required=True)
    args = parser.parse_args()
    {"build": build, "run": run, "score": score}[args.command](args)


if __name__ == "__main__":
    main()
