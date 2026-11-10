"""Training rows from the official train/dev splits of Decision Index 0.3 benchmarks.

Every benchmark is rendered by the Decision Index kit's own normalizer (``decision_index.suite.build``): the
train/dev file is placed, under the name the normalizer expects, in a private layout root
(``<out>/layout-<name>/``), the normalizer is called, and its normalized output is read back.  Instructions, option
keys, option order and state construction are therefore the kit's.  Where no normalizer can read the upstream
train format (GSM8K 0.3 answer groups, When2Call, API-Bank, ToolRet, ChessBench) the rows are built with the kit's
row helpers and constants, and the result is checked against the eval rows (``format_check`` in the manifest).

Decontamination: every training row whose normalized state+instructions text equals an eval row's, or that shares
a word 13-gram with an eval row of the same benchmark, is dropped.  Template 13-grams (those present in more than
max(10, 2%) of a benchmark's eval rows, e.g. fixed instructions, label descriptions, shared hypotheses) are not
counted.  Eval rows are the rebuilt suite files under ``--work`` (release-v1 selected rows, release-v2 added rows,
release-v3 GSM8K rows).

    python -m gdecide.data.train_splits --work .agents/runtime/gdecide/work --out .agents/runtime/gdecide/data/splits

Downloads land in ``<out>/dl/`` and are treated as data only (no code from them is executed).
"""

from __future__ import annotations

import argparse
import collections
import csv
import gzip
import hashlib
import io
import json
import math
import os
import random
import re
import shutil
import struct
import sys
import time
import urllib.request
import zipfile
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
csv.field_size_limit(1 << 30)

PREFIX = "gdecide-train-splits"
NGRAM = 13
CAP = 60_000


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def prio(tag, key):
    return hashlib.sha256(f"{PREFIX}:{tag}:{key}".encode()).hexdigest()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


# ----------------------------------------------------------------------------------------------------------------
# context, downloads, layouts


class Ctx:
    def __init__(self, work, out):
        from decision_index.suite.build.layout import Layout

        self.work = Layout(work) if (Path(work) / "artifacts/benchmark-suite").exists() else None
        if self.work is None:
            raise SystemExit(f"{work}: no artifacts/benchmark-suite")
        self.out = Path(out).resolve()
        self.dl = self.out / "dl"
        self.pins = collections.defaultdict(list)
        self.memo = {}
        self.current = None

    def pin(self, **kw):
        self.pins[self.current].append(kw)

    def layout(self, name):
        from decision_index.suite.build.layout import Layout

        root = self.out / f"layout-{name}"
        if root.exists():
            shutil.rmtree(root)
        return Layout(root)

    def hf(self, repo, rev, path):
        from huggingface_hub import hf_hub_download

        local = self.dl / "hf" / repo.replace("/", "__")
        target = local / path
        if not target.exists():
            log("hf", repo, rev[:8], path)
            hf_hub_download(repo, path, repo_type="dataset", revision=rev, local_dir=str(local))
        self.pin(kind="hf", repo=repo, revision=rev, file=path, sha256=sha256(target))
        return target

    def http(self, url, rel, expected=None):
        target = self.dl / "http" / rel
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            log("GET", url)
            tmp = target.with_suffix(target.suffix + ".part")
            with urllib.request.urlopen(url, timeout=600) as r, tmp.open("wb") as f:
                shutil.copyfileobj(r, f)
            tmp.replace(target)
        digest = sha256(target)
        if expected and digest != expected:
            raise ValueError(f"{url}: sha256 {digest} != {expected}")
        self.pin(kind="http", url=url, sha256=digest)
        return target

    def local(self, path, note=None):
        """A file the suite rebuild already fetched at its pinned revision (read-only)."""
        path = Path(path)
        self.pin(kind="work", file=str(path.relative_to(self.work.root)), sha256=sha256(path), note=note)
        return path


def link(src, dst):
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    dst.symlink_to(Path(src).resolve())
    return dst


def patch_git_revision(revisions):
    """Kit normalizers call ``git rev-parse HEAD`` on their repo; layout repos are not git checkouts."""
    from decision_index.suite.build import adapters_scored, layout as layout_mod, normalize_text

    def rev(repo):
        name = Path(repo).name
        return revisions.get(name, "unknown")

    for m in (normalize_text, adapters_scored, layout_mod):
        m.git_revision = rev
    # the kit hashes the source file once per emitted row (fine for test files, quadratic on train files): memoize
    from decision_index.suite.build import adapters_added, adapters_mechanical, adapters_retrieval, adapters_selection, normalize_direct

    cache = {}

    def cached(path):
        st = Path(path).stat()
        key = (str(Path(path).resolve()), st.st_size, st.st_mtime_ns)
        if key not in cache:
            cache[key] = sha256(path)
        return cache[key]

    for m in (normalize_direct, normalize_text, adapters_added, adapters_mechanical, adapters_retrieval, adapters_selection, adapters_scored, layout_mod):
        if hasattr(m, "sha256"):
            m.sha256 = cached


REVISIONS = {
    "contractnli": "eced6528dd3c1d14d73f9a87df8f7bdbc03126f9",
    "nli4ct": "7f32fa6c7db43e577f22e9fc6c28eef1cc6d223e",
    "isarcasm": "dfc708b53bde1bb571abfb5692f63231c2232195",
    "esci": "7916cdf6ab75a462e77f20ab40428a10923998d5",
    "searchless_chess": "90ae0e6b121673fc3079aaeffa047580bb600c0a",
}


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in fieldnames})


def read_csv_text(text):
    return list(csv.DictReader(io.StringIO(text)))


# ----------------------------------------------------------------------------------------------------------------
# builders: each yields kit-normalized rows (dicts with state/questions/expected and an id)


def b_anli(ctx):
    from decision_index.suite.build import normalize_direct

    rev = "8e4813d81f46d313dac7892e1c28076917cfcdf9"
    L = ctx.layout("anli")
    for split in ("train", "dev"):
        for k in (1, 2, 3):
            p = ctx.hf("facebook/anli", rev, f"plain_text/{split}_r{k}-00000-of-00001.parquet")
            # the normalizer globs test_*.parquet and takes the split from the stem before the first '-'
            link(p, L.raw / "anli/plain_text" / f"test_{split}{k}-00000-of-00001.parquet")
    normalize_direct.anli(L)
    for r in read_jsonl(L.normalized / "ANLI.jsonl"):
        r["id"] = r["id"].replace(":test_", ":", 1)
        yield r


KNOWLEDGE_REV = {"mmlu": "c30699e8356da336a370243923dbaf21066bb9fe", "arc": "210d026faf9955653af8916fad021475a3f00453", "winogrande": "01e74176c63542e6b0bcb004dcdea22d94fb67b5", "hellaswag": "218ec52e09a7e7462a5400043bb9a69a41d06b76"}


def knowledge_layout(ctx):
    """One layout for the kit's ``knowledge`` normalizer (MMLU, ARC-Easy/Challenge, WinoGrande, HellaSwag)."""
    if "knowledge" in ctx.memo:
        return ctx.memo["knowledge"]
    import pyarrow as pa
    import pyarrow.parquet as pq
    from decision_index.suite.build import normalize_direct

    L = ctx.layout("knowledge")
    # MMLU auxiliary_train: 60k hash sample; half rendered in the MMLU (24) format, half in the MMLU-Pro (57) format
    aux = ctx.hf("cais/mmlu", KNOWLEDGE_REV["mmlu"], "all/auxiliary_train-00000-of-00001.parquet")
    rows = pq.read_table(aux).to_pylist()
    order = sorted(range(len(rows)), key=lambda i: prio("mmlu-aux", i))[:CAP]
    mmlu_ids, pro_ids = sorted(order[: CAP // 2]), sorted(order[CAP // 2 :])
    mm = [dict(rows[i], subject=rows[i]["subject"] or "auxiliary_train") for i in mmlu_ids]
    (L.sources / "mmlu/all").mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(mm), L.sources / "mmlu/all/test-00000-of-00001.parquet")
    ctx.memo["mmlu_ids"] = mmlu_ids
    pro = [{"question_id": i, "question": rows[i]["question"], "options": rows[i]["choices"], "answer": "ABCDEFGHIJ"[rows[i]["answer"]], "answer_index": rows[i]["answer"], "category": "auxiliary_train", "src": "cais/mmlu:auxiliary_train"} for i in pro_ids]
    (L.raw / "mmlu_pro/data").mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(pro), L.raw / "mmlu_pro/data/test-00000-of-00001.parquet")
    for fam in ("ARC-Easy", "ARC-Challenge"):
        parts = [pq.read_table(ctx.hf("allenai/ai2_arc", KNOWLEDGE_REV["arc"], f"{fam}/{s}-00000-of-00001.parquet")) for s in ("train", "validation")]
        (L.sources / "arc" / fam).mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.concat_tables(parts), L.sources / "arc" / fam / "test-00000-of-00001.parquet")
    link(ctx.hf("allenai/winogrande", KNOWLEDGE_REV["winogrande"], "winogrande_xl/train-00000-of-00001.parquet"), L.sources / "winogrande/winogrande_xl/validation-00000-of-00001.parquet")
    link(ctx.hf("Rowan/hellaswag", KNOWLEDGE_REV["hellaswag"], "data/train-00000-of-00001.parquet"), L.sources / "hellaswag/data/validation-00000-of-00001.parquet")
    normalize_direct.knowledge(L)
    ctx.memo["knowledge"] = L
    return L


def _knowledge(ctx, family, split):
    L = knowledge_layout(ctx)
    for r in read_jsonl(L.normalized / f"{family}.jsonl"):
        r["id"] = r["id"].replace(f"{family}:test:", f"{family}:{split}:", 1).replace(f"{family}:validation:", f"{family}:{split}:", 1)
        yield r


def b_mmlu(ctx):
    ids = None
    for r in _knowledge(ctx, "MMLU", "auxiliary_train"):
        ids = ids or ctx.memo["mmlu_ids"]
        n = int(r["id"].rsplit(":", 1)[1])
        r["id"] = f"MMLU:auxiliary_train:{ids[n]}"
        yield r


def b_mmlu_pro(ctx):
    from decision_index.suite.build import adapters_added

    L = knowledge_layout(ctx)
    for r in adapters_added.mmlu_pro(L):
        r["id"] = f"MMLU-Pro-format:auxiliary_train:{r['metadata']['source_id']}"
        yield r


def b_arc_easy(ctx):
    yield from _knowledge(ctx, "ARC-Easy", "train+validation")


def b_arc_challenge(ctx):
    yield from _knowledge(ctx, "ARC-Challenge", "train+validation")


def b_winogrande(ctx):
    yield from _knowledge(ctx, "WinoGrande", "train_xl")


def b_hellaswag(ctx):
    yield from _knowledge(ctx, "HellaSwag", "train")


GSM_INSTRUCTIONS = "Choose the numeric answer to the problem in state. Do not provide reasoning. This is a named multiple-choice adaptation of GSM8K."


def b_gsm8k(ctx):
    """0.3 answer-groups-v1 rebuilt on the train split: every distractor is the gold of another TRAIN problem."""
    import pyarrow.parquet as pq
    from decision_index.suite.build import gsm8k_v3 as g

    p = ctx.hf("openai/gsm8k", "740312add88f781978c0658806c59bc2815b9866", "main/train-00000-of-00001.parquet")
    train = pq.read_table(p).to_pylist()
    golds = {i: g.gold_of(r["answer"]) for i, r in enumerate(train)}
    sets = g.option_sets(golds)
    for count in (4, 10):
        for i, r in enumerate(train):
            ordered, correct = g.options(golds[i], sets[i][count], count, i)
            assert ordered[correct] == g.num(golds[i]) and len(set(ordered)) == count
            yield {"id": f"GSM8K-{count}:train:{i}", "family": f"GSM8K-{count}", "split": "train", "state": {"question": r["question"], "task": f"GSM8K deterministic {count}-choice numeric selection"}, "questions": {"answer": {"type": "choice", "instructions": GSM_INSTRUCTIONS, "criteria": {f"option_{j}": v for j, v in enumerate(ordered)}}}, "expected": {"answer": f"option_{correct}"}, "metadata": {"group_id": f"GSM8K:train:{i}", "answer_group": sets[i]["group"], "distractor_method": "answer-groups-v1 over the GSM8K train split"}}


def b_banking77(ctx):
    from decision_index.suite.build import normalize_direct

    L = ctx.layout("banking77")
    train = ctx.http("https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/train.csv", "banking77/train.csv")
    link(train, L.raw / "banking77/test.csv")
    link(ctx.local(ctx.work.raw / "banking77/categories.json"), L.raw / "banking77/categories.json")
    normalize_direct.banking77(L)
    for r in read_jsonl(L.normalized / "BANKING77.jsonl"):
        r["id"] = r["id"].replace(":test:", ":train:", 1)
        yield r


def b_clinc(ctx):
    from decision_index.suite.build import normalize_direct

    L = ctx.layout("clinc")
    obj = json.loads(ctx.local(ctx.work.raw / "clinc150/data_full.json").read_text())
    derived = {"train": obj["train"], "test": obj["train"] + obj["val"], "oos_test": obj["oos_train"] + obj["oos_val"]}
    (L.raw / "clinc150").mkdir(parents=True, exist_ok=True)
    (L.raw / "clinc150/data_full.json").write_text(json.dumps(derived))
    normalize_direct.clinc150(L)
    nt = len(obj["train"])
    for r in read_jsonl(L.normalized / "CLINC150+OOS.jsonl"):
        _, split, i = r["id"].rsplit(":", 2)
        i = int(i)
        if split == "test":
            r["id"] = f"CLINC150+OOS:train:{i}" if i < nt else f"CLINC150+OOS:val:{i - nt}"
        else:
            r["id"] = f"CLINC150+OOS:oos_train:{i}" if i < len(obj["oos_train"]) else f"CLINC150+OOS:oos_val:{i - len(obj['oos_train'])}"
        yield r


def b_contractnli(ctx):
    from decision_index.suite.build import normalize_text

    L = ctx.layout("contractnli")
    src = ctx.local(ctx.work.repos / "contractnli/resources/contract-nli.zip", "train.json + dev.json members")
    with zipfile.ZipFile(src) as z:
        train = json.loads(z.read("contract-nli/train.json"))
        dev = json.loads(z.read("contract-nli/dev.json"))
    assert train["labels"] == dev["labels"]
    merged = {"documents": train["documents"] + dev["documents"], "labels": train["labels"]}
    splits = {d["id"]: "train" for d in train["documents"]} | {d["id"]: "dev" for d in dev["documents"]}
    target = L.repos / "contractnli/resources/contract-nli.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("contract-nli/test.json", json.dumps(merged))
    for r in normalize_text.contracts(L):
        sid = r["metadata"]["source_id"]
        r["id"] = f"ContractNLI:{splits[sid]}:{sid}"
        yield r


def b_nli4ct(ctx):
    from decision_index.suite.build import normalize_text

    L = ctx.layout("nli4ct")
    archive = ctx.local(ctx.work.repos / "nli4ct/training_data.zip", "train.json + dev.json members; CT json documents")
    with zipfile.ZipFile(archive) as z:
        train = json.loads(z.read("train.json"))
        dev = json.loads(z.read("dev.json"))
    assert not set(train) & set(dev)
    merged = {**train, **dev}
    repo = L.repos / "nli4ct"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "test.json").write_text(json.dumps(merged))
    (repo / "gold_test.json").write_text(json.dumps(merged))
    link(archive, repo / "training_data.zip")
    for r in normalize_text.clinical(L):
        uid = r["metadata"]["source_id"]
        r["id"] = f"NLI4CT-2024:{'train' if uid in train else 'dev'}:{uid}"
        yield r


def b_humicroedit(ctx):
    from decision_index.suite.build import normalize_text

    L = ctx.layout("humicroedit")
    src = ctx.local(ctx.work.downloads / "humicroedit-full.zip", "subtask-2 train.csv, dev.csv, train_funlines.csv")
    rows, fields = [], None
    with zipfile.ZipFile(src) as z:
        for part in ("train", "dev", "train_funlines"):
            data = read_csv_text(z.read(f"semeval-2020-task-7-dataset/subtask-2/{part}.csv").decode("utf-8-sig"))
            fields = fields or list(data[0])
            for r in data:
                r["id"] = f"{part}/{r['id']}"
                rows.append(r)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
    target = L.downloads / "humicroedit-full.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("semeval-2020-task-7-dataset/subtask-2/test.csv", buf.getvalue())
    info = normalize_text.humor(L)
    ctx.memo["humicroedit_ties"] = info.get("tie_rows")
    for r in read_jsonl(L.normalized / "Humicroedit.jsonl"):
        part, sid = r["metadata"]["source_id"].split("/", 1)
        r["id"] = f"Humicroedit:{part}:{sid}"
        yield r


def b_vast(ctx):
    from decision_index.suite.build import normalize_text

    L = ctx.layout("vast")
    rows, fields = [], None
    for part in ("train", "dev"):
        p = ctx.local(ctx.work.raw / f"vast/data/VAST/vast_{part}.csv")
        with p.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields = fields or reader.fieldnames
            for r in reader:
                r["new_id"] = f"{part}/{r['new_id']}"
                rows.append(r)
    write_csv(L.raw / "vast/data/VAST/vast_test.csv", fields, rows)
    normalize_text.vast(L)
    for r in read_jsonl(L.normalized / "VAST.jsonl"):
        part, sid = r["provenance"]["source_id"].split("/", 1)
        r["id"] = f"VAST:{part}:{sid}"
        yield r


B_LABELS = ["sarcasm", "irony", "satire", "understatement", "overstatement", "rhetorical_question"]


def b_isarcasm(ctx):
    """Train split rewritten into the test file layouts: A (binary), B (labels; non-sarcastic = all 0, as in the
    test file), C (sarcastic tweet vs its author's non-sarcastic rephrase, order by a fixed hash)."""
    from decision_index.suite.build import normalize_text

    L = ctx.layout("isarcasm")
    test = L.repos / "isarcasm/test"
    en = list(csv.DictReader(ctx.local(ctx.work.repos / "isarcasm/train/train.En.csv").open(encoding="utf-8-sig", newline="")))
    ar = list(csv.DictReader(ctx.local(ctx.work.repos / "isarcasm/train/train.Ar.csv").open(encoding="utf-8-sig", newline="")))
    en = [r for r in en if r["tweet"].strip() and r["sarcastic"] in {"0", "1"}]
    ar = [r for r in ar if r["text"].strip() and r["sarcastic"] in {"0", "1"}]
    write_csv(test / "task_A_En_test.csv", ["text", "sarcastic"], [{"text": r["tweet"], "sarcastic": r["sarcastic"]} for r in en])
    b = []
    for r in en:
        labels = {k: (r[k] if r["sarcastic"] == "1" else "0") for k in B_LABELS}
        if all(v in {"0", "1"} for v in labels.values()):
            b.append({"text": r["tweet"], **labels})
    write_csv(test / "task_B_En_test.csv", ["text", *B_LABELS], b)
    write_csv(test / "task_A_Ar_test.csv", ["text", "dialect", "sarcastic"], ar)

    def pairs(rows, key, lang):
        out = []
        for i, r in enumerate(rows):
            if r["sarcastic"] != "1" or not r["rephrase"].strip():
                continue
            sid = random.Random(prio(f"isarcasm-C-{lang}", i)).randrange(2)
            texts = [r["rephrase"], r["rephrase"]]
            texts[sid] = r[key]
            out.append({"text_0": texts[0], "text_1": texts[1], "dialect": r.get("dialect", ""), "sarcastic_id": str(sid)})
        return out

    write_csv(test / "task_C_En_test.csv", ["text_0", "text_1", "sarcastic_id"], pairs(en, "tweet", "En"))
    write_csv(test / "task_C_Ar_test.csv", ["text_0", "text_1", "dialect", "sarcastic_id"], pairs(ar, "text", "Ar"))
    normalize_text.isarcasm(L)
    for fam in ("iSarcasmEval-A-Ar", "iSarcasmEval-A-En", "iSarcasmEval-B-En", "iSarcasmEval-C-Ar", "iSarcasmEval-C-En"):
        for r in read_jsonl(L.normalized / f"{fam}.jsonl"):
            r["id"] = r["id"].replace(":test:", ":train:", 1)
            yield r


def b_acos(ctx):
    """Train and dev files renamed *_test.tsv so the kit emits them; the real test file stays in the layout under a
    non-emitted name so the per-domain category inventory (and so every question set) is identical to the eval's."""
    from decision_index.suite.build import adapters_mechanical

    L = ctx.layout("acos")
    for path in sorted((ctx.work.repos / "acos/data").glob("*/*_quad_*.tsv")):
        ctx.local(path)
        stem = path.stem
        name = f"{stem}_heldout.tsv" if stem.endswith("_test") else f"{stem}_test.tsv"
        name = name.replace("_test_heldout", "_heldout")
        link(path, L.repos / "acos/data" / path.parent.name / name)
    adapters_mechanical.build_acos(L)
    for r in read_jsonl(L.normalized / "ACOS-category-sentiment.jsonl"):
        r["id"] = r["id"].replace("_test:", ":", 1)
        r["metadata"]["group_id"] = r["metadata"]["group_id"].replace("_test:", ":", 1)
        yield r


def b_esci(ctx):
    """60k train query-product pairs (hash sample of example_id), products filtered to those pairs."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    from decision_index.suite.build import normalize_text

    L = ctx.layout("esci")
    base = ctx.work.repos / "esci/shopping_queries_dataset"
    ex_path = ctx.local(base / "shopping_queries_dataset_examples.parquet")
    pr_path = ctx.local(base / "shopping_queries_dataset_products.parquet")
    ex = pq.read_table(ex_path, filters=[("split", "=", "train")])
    ids = ex["example_id"].to_pylist()
    keep = sorted(ids, key=lambda i: prio("esci", i))[:CAP]
    ex = ex.filter(pc.is_in(ex["example_id"], value_set=pa.array(keep, type=ex.schema.field("example_id").type)))
    ex = ex.set_column(ex.schema.get_field_index("split"), "split", pa.array(["test"] * ex.num_rows))
    out = L.repos / "esci/shopping_queries_dataset"
    out.mkdir(parents=True, exist_ok=True)
    pq.write_table(ex, out / "shopping_queries_dataset_examples.parquet")
    wanted = set(zip(ex["product_locale"].to_pylist(), ex["product_id"].to_pylist()))
    del ex
    writer = None
    pf = pq.ParquetFile(pr_path)
    for batch in pf.iter_batches(batch_size=65536):
        mask = [(a, b) in wanted for a, b in zip(batch.column("product_locale").to_pylist(), batch.column("product_id").to_pylist())]
        part = pa.Table.from_batches([batch]).filter(pa.array(mask))
        if writer is None:
            writer = pq.ParquetWriter(out / "shopping_queries_dataset_products.parquet", pf.schema_arrow)
        writer.write_table(part)
    writer.close()
    normalize_text.esci(L)
    for r in read_jsonl(L.normalized / "Amazon-ESCI.jsonl"):
        r["id"] = r["id"].replace(":test:", ":train:", 1)
        yield r


def b_ragtruth(ctx):
    from decision_index.suite.build import adapters_added

    L = ctx.layout("ragtruth")
    folder = L.repos / "cand-RAGTruth/dataset"
    folder.mkdir(parents=True, exist_ok=True)
    src = ctx.local(ctx.work.repos / "cand-RAGTruth/dataset/response.jsonl")
    sources = {"train": set(), "test": set()}
    with src.open(encoding="utf-8") as f, (folder / "response.jsonl").open("w", encoding="utf-8") as g:
        for line in f:
            r = json.loads(line)
            sources[r["split"]].add(r["source_id"])
            if r["split"] == "train":
                r["split"] = "test"
                g.write(json.dumps(r, ensure_ascii=False) + "\n")
    ctx.memo["ragtruth_source_overlap"] = {"train_sources": len(sources["train"]), "test_sources": len(sources["test"]), "shared": len(sources["train"] & sources["test"])}
    link(ctx.local(ctx.work.repos / "cand-RAGTruth/dataset/source_info.jsonl"), folder / "source_info.jsonl")
    for r in adapters_added.ragtruth(L):
        r["id"] = f"RAGTruth:train:{r['metadata']['source_id']}"
        yield r


def b_hover(ctx):
    import sqlite3
    import unicodedata
    from decision_index.suite.build import adapters_added

    L = ctx.layout("hover")
    train = json.loads(ctx.local(ctx.work.repos / "cand-hover/data/hover/hover_train_release_v1.1.json").read_text(encoding="utf-8"))
    db_path = ctx.work.raw / "hover/wiki_wo_links.db"
    ctx.pin(kind="work", file=str(db_path.relative_to(ctx.work.root)), sha256="c37ee397916ec0bffacfe8902db454a5cda88a7a188409217b2e15231fe5ee2f (pinned by the kit, not re-hashed)")
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    ok = []
    for r in train:
        if all(len(db.execute("SELECT id FROM documents WHERE id=?", (unicodedata.normalize("NFD", t),)).fetchall()) == 1 for t in dict.fromkeys(t for t, _ in r["supporting_facts"])):
            ok.append(r)
    db.close()
    ctx.memo["hover_missing_docs"] = len(train) - len(ok)
    p = L.repos / "cand-hover/data/hover/hover_dev_release_v1.1.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ok), encoding="utf-8")
    link(db_path, L.raw / "hover/wiki_wo_links.db")
    for r in adapters_added.hover(L):
        r["id"] = f"HoVer:train:{r['metadata']['source_id']}"
        yield r


W2C_ORDER = ["direct", "tool_call", "request_for_info", "cannot_answer"]
CANNOT = re.compile(r"\b(unable|can't|cannot|can not|not able|don't have (access|the ability|a tool|the capability)|do not have|apologi[sz]e|sorry|I'm afraid|not possible|no (tool|function|api))\b", re.I)


def w2c_category(text):
    t = text.strip()
    if t.startswith("<TOOLCALL>"):
        return "tool_call"
    if CANNOT.search(t):
        return "cannot_answer"
    if t.endswith("?"):
        return "request_for_info"
    return "direct"


def w2c_text(text):
    t = text.strip()
    if not t.startswith("<TOOLCALL>"):
        return t
    calls = json.loads(t.removeprefix("<TOOLCALL>").removesuffix("</TOOLCALL>"))
    if not isinstance(calls, list) or len(calls) != 1:
        return None
    return json.dumps(calls[0])


def b_when2call(ctx):
    """train_pref: chosen vs rejected response, keyed by the eval's fixed letters (A direct, B tool call, C request for
    information, D cannot answer); category of each response is inferred (TOOLCALL tag; refusal wording; question)."""
    from decision_index.suite.build import adapters_added as A

    p = ctx.hf("nvidia/When2Call", "0582f7749df63a96fdc3070932e83e72396ace53", "train/when2call_train_pref.jsonl")
    letters = A.letters(4)
    skipped = collections.Counter()
    for i, r in enumerate(read_jsonl(p)):
        msgs = r["messages"]
        if len(msgs) != 1 or msgs[0]["role"] != "user":
            skipped["multi_turn"] += 1
            continue
        c, j = w2c_category(r["chosen_response"]["content"]), w2c_category(r["rejected_response"]["content"])
        ct, jt = w2c_text(r["chosen_response"]["content"]), w2c_text(r["rejected_response"]["content"])
        if c == j or ct is None or jt is None:
            skipped["same_category_or_multi_call"] += 1
            continue
        texts = {c: ct, j: jt}
        criteria = {letters[W2C_ORDER.index(k)]: texts[k] for k in W2C_ORDER if k in texts}
        row = A.candidate_row(62, f"train_pref:{i}", {"tools": [json.loads(t) for t in r["tools"]], "question": msgs[0]["content"]}, {"q": dict(type="choice", instructions=A.WHEN2CALL_INSTRUCTIONS, criteria=criteria)}, {"q": letters[W2C_ORDER.index(c)]}, track=c, answer_key_map={letters[W2C_ORDER.index(k)]: k for k in texts}, inferred_categories=True)
        row["id"] = f"When2Call:train_pref:{i}"
        yield row
    ctx.memo["when2call_skipped"] = dict(skipped)


def b_newyorker(ctx):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from decision_index.suite.build import adapters_added

    rev = "d81cbab7d0392708d5371d3a4960e69261824db4"
    L = ctx.layout("newyorker")
    cols = ["contest_number", "image_location", "image_description", "image_uncanny_description", "entities", "caption_choices", "label", "instance_id"]
    parts = []
    for f, split in (("matching/train-00000-of-00002.parquet", "train"), ("matching/train-00001-of-00002.parquet", "train"), ("matching/validation-00000-of-00001.parquet", "validation")):
        t = pq.read_table(ctx.hf("jmhessel/newyorker_caption_contest", rev, f), columns=cols)
        parts.append(t.append_column("source_split", pa.array([split] * t.num_rows)))
    table = pa.concat_tables(parts)
    target = L.raw / "newyorker/matching/test-00000-of-00001.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, target)
    splits = dict(zip(table["instance_id"].to_pylist(), table["source_split"].to_pylist()))
    for r in adapters_added.newyorker(L):
        sid = r["metadata"]["source_id"]
        r["id"] = f"NewYorker:{splits[sid]}:{sid}"
        yield r


APIBANK_INSTRUCTIONS = "Select the single API tool to invoke for the dialogue prefix in state. Use the published catalog in state. Do not infer arguments or use the current/future API result."
TURN = re.compile(r"^(User|AI|API-Request): ?", re.M)


def b_apibank(ctx):
    """lv1 training dialogues (API descriptions given): options are the sample's own APIs (2-4), not the 53-tool
    eval catalog; dialogue turns are rendered as the eval's role/text records."""
    from decision_index.suite.build.adapters_selection import APIBANK_SEED

    p = ctx.hf("liminghao1630/API-Bank", "12e8158b7628c168f07e8f31fbbe3445e99f44cf", "training-data/lv1-api-train.json")
    skipped = collections.Counter()
    for i, x in enumerate(json.loads(p.read_text())):
        lines = x["input"].split("\n")
        tools = {}
        rest = []
        for line in lines:
            if line.startswith('{"apiCode"'):
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    skipped["bad_api_json"] += 1
                    continue
                tools[d["apiCode"]] = {"name": d["apiCode"], "description": d.get("description", ""), "input_parameters": d.get("parameters", {}), "output_parameters": d.get("response", {})}
            else:
                rest.append(line)
        text = "\n".join(rest).strip()
        text = re.sub(r"\n?Generate API Request:\s*$", "", text)
        m = re.match(r"API-Request: \[([A-Za-z0-9_\.]+)\(", x["output"].strip())
        gold = m.group(1) if m else None
        if gold not in tools or len(tools) < 2:
            skipped["gold_not_in_listed_apis" if m else "unparsed_output"] += 1
            continue
        turns = []
        pieces = TURN.split(text)
        for role, body in zip(pieces[1::2], pieces[2::2]):
            body = body.strip()
            if role == "API-Request":
                api = re.match(r"\[([A-Za-z0-9_\.]+)\(", body)
                turns.append({"role": "API", "api_name": api.group(1) if api else None, "text": body})
            else:
                turns.append({"role": role, "text": body})
        if not turns:
            skipped["empty_dialogue"] += 1
            continue
        names = sorted(tools)
        order = list(range(len(names)))
        random.Random(f"{APIBANK_SEED}:train-lv1:{i}").shuffle(order)
        labels = {f"option_{k}": names[j] for k, j in enumerate(order)}
        goldkey = next(k for k, v in labels.items() if v == gold)
        yield {"id": f"API-Bank-tool-selection:train-lv1:{i}", "family": "API-Bank-tool-selection", "split": "train", "state": {"dialogue": turns, "available_tools": [tools[k] for k in names], "task": "API-Bank current API tool selection"}, "questions": {"tool": {"type": "choice", "instructions": APIBANK_INSTRUCTIONS, "criteria": labels}}, "expected": {"tool": goldkey}, "metadata": {"gold_tool": gold, "candidate_policy": "the training sample's own listed APIs"}}
    ctx.memo["apibank_skipped"] = dict(skipped)


TOOLRET_QUERIES = 20_000
TOOLRET_SHARDS = 2


def b_toolret(ctx):
    """ToolRet-Training-20w (2 of 6 shards, 20k hash-sampled queries): candidates are the listed positives and hard
    negatives (deduplicated, at most 32, hash order), rendered by the kit's retrieval projector; negatives are 'no'."""
    import pyarrow.parquet as pq
    import tiktoken
    from decision_index.suite.build import adapters_retrieval as R

    enc = tiktoken.get_encoding("cl100k_base")
    rev = "fdf5a317455b1e60785de7ba587496aa6cc878e4"
    rows = []
    for k in range(TOOLRET_SHARDS):
        p = ctx.hf("mangopy/ToolRet-Training-20w", rev, f"ToolRet-Training-20w/train-{k:05d}-of-00006.parquet")
        for batch in pq.ParquetFile(p).iter_batches(batch_size=4096, columns=["id", "query", "positive", "negative"]):
            rows.extend(batch.to_pylist())
    rows.sort(key=lambda r: prio("toolret", r["id"]))
    for q in rows[:TOOLRET_QUERIES]:
        pos = list(dict.fromkeys(q["positive"] or []))
        neg = [d for d in dict.fromkeys(q["negative"] or []) if d not in set(pos)]
        if not pos:
            continue
        docs = pos + neg[: max(0, 32 - len(pos))]
        docs = docs[:32]
        if len(docs) < 2:
            continue
        hits = sorted(((hashlib.sha256(d.encode()).hexdigest()[:16], d) for d in docs), key=lambda h: prio("toolret-order:" + q["id"], h[0]))
        qrels = {did: 1 for did, d in hits if d in set(pos)}
        out, _ = R.project("ToolRet-retrieval", "train:" + q["id"], q["query"], hits, qrels, {"domain": "ToolRet-Training-20w"}, enc)
        for r in out:
            r["expected"] = {f: ("yes" if v == "yes" else "no") for f, v in r["expected"].items()}
            r.pop("scoring", None)
            yield r


CHESS_RECORDS = 200_000
CHESS_URL = "https://storage.googleapis.com/searchless_chess/data/train/behavioral_cloning_data.bag"


def b_chess(ctx):
    """Train action-value shards are shuffled at the (position, move) level, so one shard has no position with all
    legal moves valued.  The train behavioral-cloning bag (position, Stockfish best move) is read instead: its
    first 200k records by HTTP range (bag index), 60k hash-sampled positions, rendered by the kit's chessbench
    normalizer with value 1 for the best move and 0 otherwise (so gold = the best move; hard targets, no ties)."""
    from decision_index.suite.build import adapters_scored

    target = ctx.dl / "http/chess/behavioral_cloning_data.first200k.bag"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)

        def rng(a, b):
            req = urllib.request.Request(CHESS_URL, headers={"Range": f"bytes={a}-{b}"})
            with urllib.request.urlopen(req, timeout=600) as r:
                return r.read()

        head = urllib.request.urlopen(urllib.request.Request(CHESS_URL, method="HEAD"), timeout=60)
        size = int(head.headers["Content-Length"])
        index = struct.unpack("<Q", rng(size - 8, size - 1))[0]
        ends = struct.unpack(f"<{CHESS_RECORDS}Q", rng(index, index + 8 * CHESS_RECORDS - 1))
        data = rng(0, ends[-1] - 1)
        recs, start = [], 0
        for e in ends:
            recs.append(data[start:e])
            start = e
        target.write_bytes(json.dumps({"size": size, "index": index}).encode() + b"\n" + b"".join(len(x).to_bytes(4, "little") + x for x in recs))
    ctx.pin(kind="http-range", url=CHESS_URL, records=f"first {CHESS_RECORDS} records by the bag index", sha256=sha256(target))
    raw = target.read_bytes()
    nl = raw.index(b"\n")
    recs, off = [], nl + 1
    while off < len(raw):
        n = int.from_bytes(raw[off:off + 4], "little")
        recs.append(raw[off + 4:off + 4 + n])
        off += 4 + n

    def decode(rec):
        length = shift = o = 0
        while True:
            byte = rec[o]
            o += 1
            length |= (byte & 127) << shift
            if byte < 128:
                break
            shift += 7
        return rec[o:o + length].decode(), rec[o + length:].decode()

    import chess

    best = {}
    for rec in recs:
        fen, move = decode(rec)
        best.setdefault(fen, move)
    fens = sorted(best, key=lambda f: prio("chess", f))
    # write a test-format action-value bag: every legal move, value 1 for the best move, 0 for the others
    L = ctx.layout("chess")
    out, npos = [], 0
    for fen in fens:
        board = chess.Board(fen)
        legal = [m.uci() for m in board.legal_moves]
        if best[fen] not in legal or not 2 <= len(legal) <= 255:
            continue
        for m in legal:
            f, mv = fen.encode(), m.encode()
            out.append(_varint(len(f)) + f + _varint(len(mv)) + mv + struct.pack(">d", 1.0 if m == best[fen] else 0.0))
        npos += 1
        if npos >= CAP:
            break
    bag = L.downloads / "chessbench-test-action-value.bag"
    with bag.open("wb") as f:
        ends, pos = [], 0
        for o in out:
            f.write(o)
            pos += len(o)
            ends.append(pos)
        # bag footer: the end offset of every record; the last one (= where the index starts) doubles as the pointer
        for e in ends:
            f.write(struct.pack("<Q", e))
    (L.repos / "searchless_chess").mkdir(parents=True, exist_ok=True)
    adapters_scored.chessbench(L)
    for r in read_jsonl(L.normalized / "ChessBench-legal-move.jsonl"):
        r["id"] = r["id"].replace("ChessBench:test:", "ChessBench:train-bc:", 1)
        r["expected"] = {"move": r["scoring"]["accepted"][0]}
        r["scoring"] = {"type": "behavioral_cloning_best_move", "accepted": r["scoring"]["accepted"]}
        yield r


def _varint(n):
    out = bytearray()
    while True:
        b = n & 127
        n >>= 7
        out.append(b | (128 if n else 0))
        if not n:
            return bytes(out)


SGD_CAP = 30_000


def b_sgd(ctx):
    from decision_index.suite.build import acquire, adapters_mechanical

    repo = ctx.dl / "git/sgd"
    acquire.git_fetch(repo, "https://github.com/google-research-datasets/dstc8-schema-guided-dialogue.git", "e852981ae34990f4358979625854259302feaa78", ["train", "dev"], log=log)
    ctx.pin(kind="git", repo="google-research-datasets/dstc8-schema-guided-dialogue", revision="e852981ae34990f4358979625854259302feaa78", paths=["train/", "dev/"])
    for split in ("train", "dev"):
        L = ctx.layout(f"sgd-{split}")
        link(repo / split, L.repos / "sgd/test")
        adapters_mechanical.build_sgd(L)
        for r in read_jsonl(L.normalized / "SGD-service-given-intent.jsonl"):
            r["id"] = r["id"].replace(":test:", f":{split}:", 1)
            yield r


# ----------------------------------------------------------------------------------------------------------------
# registry


NC = "NON-COMMERCIAL"
BENCHES = {
    "ANLI": dict(catalog=12, fn=b_anli, splits="train_r1-3 + dev_r1-3", license=f"CC BY-NC 4.0 ({NC})"),
    "MMLU": dict(catalog=24, fn=b_mmlu, decontam_catalogs=[24, 57], splits="auxiliary_train (30k of a 60k hash sample)", license="MIT (cais/mmlu); auxiliary_train pools ARC, MCTest, OBQA and RACE: RACE is research-only/non-commercial, MCTest per its own terms", cap="60k auxiliary_train rows split 30k MMLU format / 30k MMLU-Pro format"),
    "MMLU-Pro-format": dict(catalog=57, fn=b_mmlu_pro, splits="cais/mmlu auxiliary_train (the other 30k of the 60k sample) in the MMLU-Pro row format", license="as MMLU auxiliary_train (RACE research-only)", eval_catalog=57, decontam_catalogs=[57, 24]),
    "ARC-Easy": dict(catalog=26, fn=b_arc_easy, splits="train + validation", license="CC BY-SA 4.0"),
    "ARC-Challenge": dict(catalog=27, fn=b_arc_challenge, splits="train + validation", license="CC BY-SA 4.0"),
    "WinoGrande": dict(catalog=28, fn=b_winogrande, splits="winogrande_xl train", license="see dataset card (allenai/winogrande; CC-BY per the AI2 release)"),
    "HellaSwag": dict(catalog=29, fn=b_hellaswag, splits="train", license="MIT"),
    "GSM8K": dict(catalog=30, fn=b_gsm8k, splits="main train", license="MIT"),
    "BANKING77": dict(catalog=4, fn=b_banking77, splits="train.csv", license="CC BY 4.0"),
    "CLINC150+OOS": dict(catalog=5, fn=b_clinc, splits="train + val + oos_train + oos_val", license="CC BY 3.0"),
    "ContractNLI": dict(catalog=11, fn=b_contractnli, splits="train + dev", license="CC BY 4.0 plus Hitachi America ContractNLI Terms and Conditions of Use (TERMS in the zip)"),
    "NLI4CT": dict(catalog=42, fn=b_nli4ct, splits="train + dev", license="SemEval-2024 Task 2 terms (no licence file in the repository)"),
    "Humicroedit": dict(catalog=21, fn=b_humicroedit, splits="subtask-2 train + dev + train_funlines (ties dropped as in the eval)", license="SemEval-2020 Task 7 terms (no explicit licence)"),
    "VAST": dict(catalog=41, fn=b_vast, splits="vast_train + vast_dev", license="not stated in the repository"),
    "iSarcasmEval": dict(catalog=40, fn=b_isarcasm, splits="train.En / train.Ar rendered as tasks A, B (En), C", license="MIT (repository LICENSE); tweets subject to X/Twitter terms"),
    "ACOS": dict(catalog=38, fn=b_acos, splits="train + dev (Laptop, Restaurant)", license="not stated in the repository"),
    "Amazon-ESCI": dict(catalog=37, fn=b_esci, splits="shopping_queries_dataset split=='train' (60k hash-sampled pairs)", license="Apache-2.0"),
    "RAGTruth": dict(catalog=59, fn=b_ragtruth, splits="response.jsonl split=='train'", license=f"MIT annotations; contexts from CNN/Daily Mail, MS MARCO ({NC}) and Yelp Open Dataset (no redistribution): train locally, never republish rows"),
    "HoVer": dict(catalog=61, fn=b_hover, splits="hover_train_release_v1.1 (oracle supporting documents)", license="CC BY-SA 4.0 (data), Wikipedia text CC BY-SA"),
    "When2Call": dict(catalog=62, fn=b_when2call, splits="train_pref (2-option adaptation)", license="CC BY 4.0"),
    "NewYorker": dict(catalog=64, fn=b_newyorker, splits="matching train + validation (fold 0)", license="CC BY 4.0 annotations (no images used)"),
    "API-Bank": dict(catalog=3, fn=b_apibank, splits="training-data/lv1-api-train.json", license="Apache-2.0 (api-bank/LICENSE)"),
    "ToolRet": dict(catalog=2, fn=b_toolret, splits="mangopy/ToolRet-Training-20w (2 of 6 shards, 20k queries)", license="not stated on the dataset card; aggregates upstream tool datasets with their own terms"),
    "ChessBench": dict(catalog=31, fn=b_chess, splits="train behavioral_cloning_data.bag (first 200k records, 60k positions)", license="CC BY 4.0 (dataset), lichess portions CC0"),
    "SGD": dict(catalog=10, fn=b_sgd, splits="train + dev", license="CC BY-SA 4.0", cap=f"{SGD_CAP} rows, hash sample by dialogue"),
}

SKIPPED = {
    "BFCL": "no train split (evaluation-only leaderboard data)",
    "RouterBench": "no train/test split upstream (the kit derives a calibration split from the eval pool itself)",
    "Home appliance simulator": "generated by the kit; its dev split is part of the 0.2.1 dedup rule, not a training source",
    "BPoMP": "single released pool, no train split",
    "POP909-CL": "no official split",
    "cfcolor": "no official split",
    "GPQA Diamond": "no train split; GPQA main/extended contain the Diamond questions",
    "GSM8K": None,
    "MuSR": "no train split",
    "SATA-Bench": "no train split",
    "SimpleBench": "public items only",
    "BRIGHT": "no train split",
    "FinEntity": "single file, no split",
    "CRUXEval": "no train split",
    "CLadder": "no train split",
    "HLE": "no train split (and gated)",
    "MMLU-Pro": "only a 70-item validation (few-shot) split; covered instead by MMLU auxiliary_train rendered in its format",
    "BBH": "no train split; carries the BIG-bench canary",
    "PhishNChips": "no train split",
    "Habermas Machine": "no train split",
    "ForecastBench": "retired in 0.3",
}
SKIPPED = {k: v for k, v in SKIPPED.items() if v}

# what text of a row is matched for 13-gram overlap (exact matching always uses state + instructions)
FIELDS = {2: "query", 3: "dialogue", 31: "fen", 62: "question", 59: "response"}


# ----------------------------------------------------------------------------------------------------------------
# text normalization, 13-grams, eval index


def strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from strings(v)
    elif x is not None and not isinstance(x, bool):
        yield str(x)


def norm(s):
    return " ".join(s.lower().split())


def exact_key(row):
    st = row["state"] if isinstance(row["state"], str) else json.dumps(row["state"], sort_keys=True, ensure_ascii=False)
    ins = [q.get("instructions") for _, q in sorted(row["questions"].items())]
    # criteria are part of the key: for Humicroedit / iSarcasm C the state is empty and the instruction fixed, so
    # the items differ only in their options
    crit = [q.get("criteria") for _, q in sorted(row["questions"].items())]
    text = norm(st) + "\n" + norm(" ".join(strings(ins))) + "\n" + norm(" ".join(strings(crit)))
    return hashlib.blake2b(text.encode(), digest_size=16).digest()


def qkey(k, questions):
    """Instruction template group of a question: its key, or the key pattern for option_i / doc_i style keys."""
    return re.sub(r"\d+$", "#", k) if re.fullmatch(r"(option|doc|entity)_.*\d", k) else k


def ins_text(q):
    ins = q.get("instructions")
    return ins if isinstance(ins, str) else " ".join(strings(ins))


def segments(row, catalog, strip=None):
    """Texts matched for 13-grams, one segment per field (n-grams never cross fields).  Each instruction has its
    benchmark-wide common prefix/suffix (the fixed template, computed over the eval rows) removed first."""
    mode = FIELDS.get(catalog)
    st = row["state"]
    if mode == "query":
        return [st.get("query", "")] if isinstance(st, dict) else []
    if mode == "dialogue":
        return list(strings(st.get("dialogue", []))) if isinstance(st, dict) else []
    if mode == "fen":
        return []
    crit = [t for q in row["questions"].values() for t in strings(q.get("criteria"))]
    if mode == "response":  # RAGTruth: contexts are source documents whose ids are disjoint across splits (checked)
        return [st.get("response", "")] if isinstance(st, dict) else []
    if mode == "question":  # When2Call: the candidate responses are templated model text (shared refusal phrasing)
        return [st.get("question", "")] if isinstance(st, dict) else []
    out = list(strings(st))
    for k, q in row["questions"].items():
        t = ins_text(q)
        pre, suf = (strip or {}).get(qkey(k, row["questions"]), ("", ""))
        if pre and t.startswith(pre):
            t = t[len(pre):]
        if suf and t.endswith(suf):
            t = t[: len(t) - len(suf)]
        out.append(t)
    return out + crit


def grams(segs):
    out = set()
    for text in segs:
        toks = norm(text).split()
        out.update(hash(" ".join(toks[i:i + NGRAM])) for i in range(len(toks) - NGRAM + 1))
    return out


def word_prefix(strs, reverse=False):
    strs = [s[::-1] for s in strs] if reverse else list(strs)
    p = os.path.commonprefix(strs)
    if len(set(strs)) > 1:  # cut back to a word boundary so the variable part keeps whole words
        cut = max(p.rfind(" "), p.rfind("\n"))
        p = p[: cut + 1] if cut >= 0 else ""
    return p[::-1] if reverse else p


class EvalIndex:
    def __init__(self, catalog):
        self.catalog = catalog
        self.n = 0
        self.exact = set()
        self.rows = []
        self.ins = collections.defaultdict(set)
        self.fens = set()
        self.samples = collections.defaultdict(list)
        self.sources = set()
        self.gram_set = None
        self.strip = {}
        self.templates = 0

    def add(self, row, track, source):
        self.n += 1
        self.sources.add(source)
        self.exact.add(exact_key(row))
        light = {"state": row["state"], "questions": {k: {"instructions": q.get("instructions"), "criteria": q.get("criteria")} for k, q in row["questions"].items()}}
        if FIELDS.get(self.catalog) in ("query", "dialogue", "fen", "question", "response"):
            light["questions"] = {}
        self.rows.append(light)
        for k, q in light["questions"].items():
            if len(self.ins[qkey(k, light["questions"])]) < 50000:
                self.ins[qkey(k, light["questions"])].add(ins_text(q))
        if self.catalog == 31 and isinstance(row["state"], dict):
            self.fens.add(row["state"].get("fen"))
        if len(self.samples[track]) < 300:
            self.samples[track].append({"state": row["state"], "questions": row["questions"], "expected": row.get("expected")})

    def finish(self):
        for k, v in self.ins.items():
            pre = word_prefix(v)
            suf = "" if len(v) == 1 else word_prefix(v, reverse=True)
            self.strip[k] = (pre, suf)
        self.ins = None
        df = collections.Counter()
        for r in self.rows:
            df.update(grams(segments(r, self.catalog, self.strip)))
        self.rows = None
        limit = max(10, 0.02 * self.n)
        self.templates = sum(1 for v in df.values() if v > limit)
        self.gram_set = {g for g, v in df.items() if v <= limit}


def eval_files(work):
    s = Path(work) / "artifacts/benchmark-suite"
    files = []
    for p in (s / "release-v1-rebuilt/selected-rows.jsonl", s / "release-v2-rebuilt/added-rows.jsonl", s / "release-v3-rebuilt/gsm8k-rows.jsonl"):
        if p.exists():
            files.append(p)
        elif p.with_suffix(".jsonl.gz").exists():
            files.append(p.with_suffix(".jsonl.gz"))
    return files


def load_eval(work, catalogs, wait_minutes=60):
    deadline = time.time() + 60 * wait_minutes
    while True:
        files = eval_files(work)
        have = set()
        for f in files:
            if "release-v1" in str(f):
                have |= {n for n in catalogs if n < 56 and n != 30}
            if "release-v2" in str(f) and "added" in str(f):
                have |= {n for n in catalogs if n >= 56}
            if "release-v3" in str(f):
                have |= {30}
        missing = set(catalogs) - have
        if not missing or time.time() > deadline:
            break
        log("waiting for the suite rebuild; missing eval rows for catalogs", sorted(missing))
        time.sleep(120)
    idx = {n: EvalIndex(n) for n in catalogs}
    pats = {n: f'"catalog_id":{n},' for n in catalogs}
    for f in files:
        log("reading eval rows", f.name)
        opener = gzip.open if str(f).endswith(".gz") else open
        with opener(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                hit = [n for n, p in pats.items() if p in line]
                if not hit:
                    continue
                r = json.loads(line)
                e = r["_evaluation"]
                n = e["catalog_id"]
                if n not in idx or (n == 30 and "release-v3" not in str(f)):
                    continue
                idx[n].add(r, e.get("track", ""), str(f.relative_to(Path(work))))
    if 31 in idx:  # every test position of the ChessBench pool, not only the 5,000 frozen ones
        p = Path(work) / "artifacts/benchmark-suite/normalized/ChessBench-legal-move.jsonl"
        if p.exists():
            for r in read_jsonl(p):
                idx[31].fens.add(r["state"]["fen"])
    for i in idx.values():
        i.finish()
    return idx


# ----------------------------------------------------------------------------------------------------------------
# format check: a training row must be shaped like the eval rows of its track


def shape(x):
    if isinstance(x, dict):
        return "dict:" + ",".join(sorted(x))
    return type(x).__name__


def keypattern(keys):
    ks = sorted(keys)
    if all(re.fullmatch(r"option_\d+", k) for k in ks):
        return "option_i"
    if all(re.fullmatch(r"[A-Z]", k) for k in ks):
        return "letters"
    if all(re.fullmatch(r"doc_\d+", k) for k in ks):
        return "doc_i"
    return ",".join(ks)


def common_prefix(strs):
    s = os.path.commonprefix(list(strs))
    return s


class FormatCheck:
    def __init__(self, samples):
        self.ref = {}
        for track, rows in samples.items():
            info = {"state": collections.Counter(shape(r["state"]) for r in rows), "qtypes": collections.Counter(), "qkeys": collections.Counter(keypattern(r["questions"]) for r in rows), "ins": {}, "crit": {}, "ckeys": collections.Counter()}
            ins = collections.defaultdict(set)
            crit = collections.defaultdict(set)
            for r in rows:
                for k, q in r["questions"].items():
                    info["qtypes"][q["type"]] += 1
                    kk = keypattern([k]) if keypattern(r["questions"]) in ("option_i", "letters", "doc_i") else k
                    ins[kk].add(json.dumps(q["instructions"], sort_keys=True) if not isinstance(q["instructions"], str) else q["instructions"])
                    crit[kk].add(json.dumps(q["criteria"], sort_keys=True))
                    info["ckeys"][keypattern(q["criteria"])] += 1
            info["ins"] = {k: (next(iter(v)) if len(v) == 1 else ("prefix", common_prefix(v))) for k, v in ins.items()}
            info["crit"] = {k: (next(iter(v)) if len(v) == 1 else None) for k, v in crit.items()}
            # option keys that are per-row by design (SGD intent names, ChessBench UCI moves): compare value shapes
            info["ckeys_vary"] = len(info["ckeys"]) > 5
            info["cvals"] = collections.Counter(shape(v) for r in rows for q in r["questions"].values() for v in q["criteria"].values())
            self.ref[track] = info
        self.stats = collections.Counter()
        self.examples = collections.defaultdict(list)

    def check(self, row, track):
        ref = self.ref.get(track) or (next(iter(self.ref.values())) if len(self.ref) == 1 else None)
        if ref is None:
            ref = self._closest(row)
        if ref is None:
            self.stats["no_reference_track"] += 1
            return
        problems = []
        if shape(row["state"]) not in ref["state"]:
            problems.append(f"state {shape(row['state'])} not in {list(ref['state'])[:3]}")
        qk = keypattern(row["questions"])
        multi = qk in ("option_i", "letters", "doc_i")
        if qk not in ref["qkeys"] and not any(set(row["questions"]) <= set(k.split(",")) for k in ref["qkeys"]):
            problems.append(f"question keys {qk[:80]}")
        for k, q in row["questions"].items():
            kk = keypattern([k]) if multi else k
            if q["type"] not in ref["qtypes"]:
                problems.append(f"question type {q['type']}")
            want = ref["ins"].get(kk)
            got = q["instructions"] if isinstance(q["instructions"], str) else json.dumps(q["instructions"], sort_keys=True)
            if isinstance(want, tuple):
                if not got.startswith(want[1]):
                    problems.append(f"instructions prefix differs for {kk}")
            elif want is not None and got != want:
                problems.append(f"instructions differ for {kk}")
            cw = ref["crit"].get(kk)
            if cw is not None and json.dumps(q["criteria"], sort_keys=True) != cw:
                problems.append(f"criteria differ for {kk}")
            if ref["ckeys_vary"]:
                if any(shape(v) not in ref["cvals"] for v in q["criteria"].values()):
                    problems.append("option value shape")
            elif keypattern(q["criteria"]) not in ref["ckeys"]:
                problems.append(f"option keys {keypattern(q['criteria'])[:60]}")
        if problems:
            self.stats["mismatch"] += 1
            for p in problems:
                self.stats["problem: " + re.sub(r"for .*", "", p)[:60]] += 1
            if len(self.examples["mismatch"]) < 3:
                self.examples["mismatch"].append({"id": row.get("id"), "problems": problems[:5]})
        else:
            self.stats["match"] += 1

    def _closest(self, row):
        keys = set(row["questions"])
        for info in self.ref.values():
            if any(keys <= set(k.split(",")) for k in info["qkeys"]):
                return info
        return None


def eval_track(catalog, row):
    fam = row.get("family", "")
    if catalog == 30:
        return fam + "choice"
    if catalog == 40:
        return fam
    if catalog == 38:
        return "ACOS-category-sentiment"
    return None


# ----------------------------------------------------------------------------------------------------------------
# soft targets / output rows


def to_train(row, name, spec, decontaminated):
    out = {"id": "split/" + row["id"], "catalog_id": spec["catalog"], "source": f"split/{name}", "license": spec["license"], "state": row["state"], "questions": row["questions"], "expected": row["expected"], "decontaminated": decontaminated}
    if row.get("family"):
        out["track"] = row["family"]
    if row.get("scoring", {}).get("accepted"):
        out["accepted"] = row["scoring"]["accepted"]
    return out


def build(ctx, name, spec, evidx):
    ctx.current = name
    catalogs = spec.get("decontam_catalogs", [spec["catalog"]])
    idxs = [evidx[c] for c in catalogs if c in evidx and evidx[c].n]
    decon = bool(idxs)
    fc = FormatCheck(evidx[spec.get("eval_catalog", spec["catalog"])].samples) if spec.get("eval_catalog", spec["catalog"]) in evidx and evidx[spec.get("eval_catalog", spec["catalog"])].n else None
    stats = collections.Counter()
    seen = set()
    target = ctx.out / f"{spec['catalog']}-{name}.jsonl.gz"
    tmp = target.with_suffix(".tmp")
    stage = ctx.out / f".stage-{name}.jsonl"
    rows_iter = spec["fn"](ctx)
    if name == "SGD":
        rows_iter = sgd_sample(rows_iter)
    # pass 1: exact matches are dropped; 13-grams shared with eval rows are recorded with the row
    train_df = collections.Counter()
    with stage.open("w", encoding="utf-8") as st:
        for r in rows_iter:
            stats["built"] += 1
            if r["id"] in seen:
                stats["duplicate_id"] += 1
                continue
            seen.add(r["id"])
            drop, hits = None, []
            for idx in idxs:
                if exact_key(r) in idx.exact:
                    drop = "exact"
                    break
                if idx.catalog == 31 and r["state"].get("fen") in idx.fens:
                    drop = "exact_fen"
                    break
                if idx.gram_set:
                    hits.extend(grams(segments(r, idx.catalog, idx.strip)) & idx.gram_set)
            if drop:
                stats["dropped_" + drop] += 1
                continue
            hits = sorted(set(hits))
            train_df.update(hits)
            st.write(json.dumps([hits, r], ensure_ascii=False, separators=(",", ":")) + "\n")
            if stats["built"] % 50000 == 0:
                log(name, dict(stats))
    # boilerplate: a shared 13-gram that also occurs in many of this benchmark's own training rows (standard contract
    # clauses, RECIST definitions, Wikipedia stock phrases) does not identify an eval item
    n_rows = stats["built"] - stats["duplicate_id"] - sum(v for k, v in stats.items() if k.startswith("dropped_"))
    limit = max(10, 0.01 * n_rows)
    boiler = {g for g, c in train_df.items() if c > limit}
    stats["boilerplate_ngrams"] = len(boiler)
    del train_df
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f, stage.open(encoding="utf-8") as st:
        for line in st:
            hits, r = json.loads(line)
            if hits:
                if any(h not in boiler for h in hits):
                    stats["dropped_ngram13"] += 1
                    continue
                stats["kept_boilerplate_only_overlap"] += 1
            if fc is not None and stats["format_checked"] < 2000:
                stats["format_checked"] += 1
                fc.check(r, eval_track(spec["catalog"], r))
            f.write(json.dumps(to_train(r, name, spec, decon), ensure_ascii=False, separators=(",", ":")) + "\n")
            stats["written"] += 1
    stage.unlink()
    tmp.replace(target)
    entry = {"catalog_id": spec["catalog"], "file": target.name, "splits": spec["splits"], "license": spec["license"], "non_commercial": NC in spec["license"] or "research-only" in spec["license"], "rows_built": stats["built"], "rows_written": stats["written"], "dropped": {k.removeprefix("dropped_"): v for k, v in stats.items() if k.startswith("dropped_")}, "kept_boilerplate_only_overlap": stats["kept_boilerplate_only_overlap"], "strict_any_13gram_drops": stats["dropped_ngram13"] + stats["kept_boilerplate_only_overlap"], "boilerplate_ngrams": stats["boilerplate_ngrams"], "duplicate_ids": stats["duplicate_id"], "decontaminated": decon, "decontaminated_against": {str(i.catalog): {"eval_rows": i.n, "template_ngrams_ignored": i.templates, "ngram_field": FIELDS.get(i.catalog, "state+instructions+criteria"), "instruction_templates_stripped": {k: [len(p), len(q)] for k, (p, q) in list(i.strip.items())[:20]}, "sources": sorted(i.sources)} for i in idxs}, "upstream": ctx.pins.get(name, []), "doc": (spec["fn"].__doc__ or "").strip() or None}
    if spec.get("cap"):
        entry["cap"] = spec["cap"]
    if fc is not None:
        entry["format_check"] = {"checked": stats["format_checked"], **{k: v for k, v in fc.stats.items()}, "examples": dict(fc.examples)}
    for k in ("when2call_skipped", "apibank_skipped", "hover_missing_docs", "humicroedit_ties", "ragtruth_source_overlap"):
        if k in ctx.memo and k.split("_")[0] in name.lower().replace("-", ""):
            entry[k] = ctx.memo[k]
    return entry


def sgd_sample(rows):
    rows = list(rows)
    dialogues = sorted({r["id"].rsplit(":", 2)[0] for r in rows}, key=lambda d: prio("sgd", d))
    keep, n = set(), 0
    counts = collections.Counter(r["id"].rsplit(":", 2)[0] for r in rows)
    for d in dialogues:
        if n + counts[d] > SGD_CAP:
            break
        keep.add(d)
        n += counts[d]
    for r in rows:
        if r["id"].rsplit(":", 2)[0] in keep:
            yield r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", nargs="*", help=f"benchmark names: {', '.join(BENCHES)}")
    ap.add_argument("--wait-minutes", type=float, default=60)
    args = ap.parse_args(argv)
    names = args.only or list(BENCHES)
    unknown = [n for n in names if n not in BENCHES]
    if unknown:
        raise SystemExit(f"unknown benchmarks {unknown}; choose from {list(BENCHES)}")
    ctx = Ctx(args.work, args.out)
    ctx.out.mkdir(parents=True, exist_ok=True)
    patch_git_revision(REVISIONS)
    catalogs = sorted({c for n in names for c in BENCHES[n].get("decontam_catalogs", [BENCHES[n]["catalog"]])})
    evidx = load_eval(args.work, catalogs, args.wait_minutes)
    manifest_path = ctx.out / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.setdefault("benchmarks", {})
    for name in names:
        log("building", name)
        t0 = time.time()
        try:
            entry = build(ctx, name, BENCHES[name], evidx)
        except Exception as e:  # a failed benchmark is a recorded result, not a stop
            import traceback

            traceback.print_exc()
            entry = {"catalog_id": BENCHES[name]["catalog"], "error": f"{type(e).__name__}: {e}"}
        entry["seconds"] = round(time.time() - t0, 1)
        manifest["benchmarks"][name] = entry
        log(name, {k: entry.get(k) for k in ("rows_written", "dropped", "error")})
        manifest.update(
            generator="research/gradiated-decide/gdecide/data/train_splits.py",
            created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            kit="Decision Index kit (decision_index.suite.build normalizers) at .agents/runtime/gdecide/di",
            row_format={"state": "as the eval row", "questions": "as the eval row", "expected": "{question key: gold option key} (RAGTruth: bool for the noul question)", "source": "split/<Benchmark>", "license": "upstream terms", "id": "split/<benchmark>:<upstream split>:<source id>", "catalog_id": "Decision Index catalog id", "decontaminated": "true when eval rows of the benchmark were loaded and matched"},
            decontamination={"exact": "lowercased, whitespace-collapsed state (JSON, sorted keys) + instructions + criteria equal to an eval row's (criteria added because Humicroedit and iSarcasm C have an empty state and a fixed instruction)", "ngram": f"any shared word {NGRAM}-gram (lowercase, whitespace-collapsed, whitespace tokens) with an eval row of the same catalog id, over state+instructions+criteria unless noted in ngram_field", "templates": "each instruction's benchmark-wide common prefix/suffix (computed over the eval rows) is stripped and n-grams never cross fields; 13-grams present in more than max(10, 2% of) the benchmark's eval rows are ignored (fixed instructions, label descriptions, shared hypotheses/catalogs)", "boilerplate": "a shared 13-gram that also occurs in more than max(10, 1% of) the benchmark's training rows is boilerplate and does not by itself drop a row; strict_any_13gram_drops reports what the plain any-shared-13-gram rule would drop", "chess": "exact FEN against every ChessBench test-pool position", "eval_sources": [str(p.relative_to(Path(args.work))) for p in eval_files(args.work)]},
            skipped=SKIPPED,
            totals={"rows_written": sum(b.get("rows_written", 0) for b in manifest["benchmarks"].values())},
        )
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


if __name__ == "__main__":
    main()
