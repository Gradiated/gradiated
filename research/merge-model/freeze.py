"""Build a leakage-resistant dataset from committed public-merge shards."""

import argparse
import datetime
import gzip
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

from mine import conflict_hash

CUTOFF = int(datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC).timestamp())
HELDOUT = {"qemu/qemu", "phpmyadmin/phpmyadmin", "mariadb/server", "erlang/otp"}
FAMILIES = {
    "git-for-windows/git": "git/git",
    "litecoin-project/litecoin": "bitcoin/bitcoin",
    "dogecoin/dogecoin": "bitcoin/bitcoin",
    "swiftlang/llvm-project": "llvm/llvm-project",
}


def partition(row):
    repo = row["repo"].lower()
    family = FAMILIES.get(repo, repo)
    if (
        family in HELDOUT
        or int.from_bytes(hashlib.sha256(family.encode()).digest()[:4], "big") % 10 == 0
    ):
        return 2
    return 1 if row["ts"] >= CUTOFF else 0


def render(row):
    path = row["path"]
    sides = [row["ours"], row["base"], row["theirs"]]
    subject = "\n".join(
        f"{s.title()} parent subject: {text}"
        for s, text in row["subjects"].items()
        if text
    )
    prompt = (
        "Resolve this Git conflict. Return only the replacement lines between <resolution> and "
        "</resolution>. Return <abstain/> if you cannot resolve it safely.\n\n"
        f"File: {path}\n{subject}\n\n"
        "Context and conflict:\n"
        + "".join(row["before"])
        + "<<<<<<< ours\n"
        + "".join(sides[0])
        + "||||||| base\n"
        + "".join(sides[1])
        + "=======\n"
        + "".join(sides[2])
        + ">>>>>>> theirs\n"
        + "".join(row["after"])
        + "\nAnswer:\n"
    )
    if len(prompt) > 32_000:
        return None
    target = "<resolution>\n" + "".join(row["resolution"]) + "</resolution>"
    return dict(
        prompt=prompt,
        completion=target,
        repo=row["repo"],
        merge=row["merge"],
        path=path,
        ts=row["ts"],
        language=row["language"],
        license=row["license"],
        cls=row["cls"],
        hash=row["hash"],
        uid=hashlib.sha256(
            json.dumps([row["repo_id"], row["merge"], path, row["hunk_index"]]).encode()
        ).hexdigest()[:24],
        ours=sides[0],
        base=sides[1],
        theirs=sides[2],
        resolution=row["resolution"],
        aligned=True,
        code=True,
        n_hunks_in_file=row["n_hunks_in_file"],
        subset="final",
    )


def load(source, db):
    db.execute("""create table records (
        hash text primary key, split integer, repo text, language text,
        ambiguity integer not null default 0, target text, row text
    )""")
    insert = """insert into records(hash,split,repo,language,target,row) values(?,?,?,?,?,?)
        on conflict(hash) do update set
        split=excluded.split, repo=excluded.repo, language=excluded.language,
        target=excluded.target, row=excluded.row, ambiguity=0 where excluded.split>records.split"""
    conflicts = (
        """update records set ambiguity=1 where hash=? and split=0 and target<>?"""
    )
    counts = Counter()
    for manifest in sorted(source.rglob("*.json")):
        data = json.loads(manifest.read_text())
        if data.get("format_version") != 1 or "gzip_sha256" not in data:
            continue
        count = data["counts"].get("accepted_hunks", 0)
        if not count:
            counts["empty_shards"] += 1
            continue
        f = manifest.with_suffix(".jsonl.gz")
        if (
            not f.is_file()
            or hashlib.sha256(f.read_bytes()).hexdigest() != data["gzip_sha256"]
        ):
            counts["missing_or_invalid_shards"] += 1
            continue
        got = 0
        with gzip.open(f, "rt", encoding="utf-8") as stream:
            with db:
                for line in stream:
                    row = json.loads(line)
                    got += 1
                    example = render(row)
                    if example is None:
                        counts["oversize_examples"] += 1
                        continue
                    split = partition(row)
                    target = json.dumps([x.rstrip() for x in row["resolution"]])
                    if split == 0:
                        db.execute(conflicts, (row["hash"], target))
                    db.execute(
                        insert,
                        (
                            row["hash"],
                            split,
                            row["repo"],
                            row["language"],
                            target,
                            json.dumps(example),
                        ),
                    )
                if got != count:
                    raise ValueError(
                        f"shard row count differs from manifest: {manifest.name}"
                    )
        counts["verified_shards"] += 1
        counts["raw_hunks"] += got
    return counts


def emit(db, out, per_repo):
    splits = {0: "train", 1: "test_time", 2: "test_repo"}
    result = {}
    for split, label in splits.items():
        repos = Counter()
        languages = Counter()
        cap = per_repo if split == 0 else 300
        temp = out / f"{label}.jsonl.gz.tmp"
        with gzip.open(temp, "wt", encoding="utf-8") as stream:
            for repo, lang, row in db.execute(
                "select repo,language,row from records where split=? and ambiguity=0 order by hash",
                (split,),
            ):
                if repos[repo] >= cap:
                    continue
                stream.write(row + "\n")
                repos[repo] += 1
                languages[lang] += 1
        temp.replace(out / f"{label}.jsonl.gz")
        result[label] = dict(
            rows=sum(repos.values()), repos=dict(repos), languages=dict(languages)
        )
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("shards", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--train-per-repo", type=int, default=20_000)
    p.add_argument("--protect", type=Path, action="append", default=[])
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    # A temporary database provides a global exact-dedup index without holding the corpus in RAM.
    index = a.out / "split-index.sqlite"
    if index.exists():
        raise ValueError("use an empty snapshot directory")
    with sqlite3.connect(index) as db:
        counts = load(a.shards, db)
        protected = set()
        for file in a.protect:
            stream = gzip.open(file, "rt") if file.suffix == ".gz" else file.open()
            with stream:
                for r in map(json.loads, stream):
                    if all(key in r for key in ("ours", "base", "theirs")):
                        protected.add(conflict_hash(r["ours"], r["base"], r["theirs"]))
        for h in protected:
            counts["fixed_benchmark_exclusions"] += db.execute(
                "delete from records where hash=? and split=0", (h,)
            ).rowcount
        output = emit(db, a.out, a.train_per_repo)
        counts["ambiguous_training_examples"] = db.execute(
            "select count(*) from records where ambiguity=1"
        ).fetchone()[0]
    index.unlink()
    report = dict(format_version=1, cutoff="2026-01-01", counts=counts, splits=output)
    (a.out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
