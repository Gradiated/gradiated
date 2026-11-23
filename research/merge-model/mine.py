"""Replay Git merges into independently committed, provenance-bearing shards."""

import argparse
import gzip
import hashlib
import itertools
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CODE = set(
    "c h cc cpp cxx hpp rs py pyi js jsx ts tsx java kt kts scala go rb php cs swift erl ex exs lua sh dart zig m mm hs clj fs fsx ml mli vue svelte".split()
)
IGNORE = re.compile(
    r"(^|/)(vendor|third_party|node_modules|generated|dist|locales)/|(\.min\.js|_pb\.go|\.generated\.[^.]+)$",
    re.IGNORECASE,
)
MARKERS = re.compile(r"^(<<<<<<< |\|\|\|\|\|\|\| |=======$|>>>>>>> )")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")
REPO = re.compile(r"[\w.-]+/[\w.-]+", re.ASCII)


def run(args, *, timeout=25, allowed=(0,), env=None):
    p = subprocess.run(args, capture_output=True, timeout=timeout, env=env, check=False)
    if p.returncode not in allowed:
        raise RuntimeError(f"{args[0]} exited {p.returncode}")
    return p


def git(repo, *args, timeout=25, allowed=(0,)):
    env = dict(
        os.environ,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_TERMINAL_PROMPT="0",
        GIT_LFS_SKIP_SMUDGE="1",
    )
    return run(
        ["git", "-C", str(repo), *args], timeout=timeout, allowed=allowed, env=env
    )


def blob(repo, rev, path):
    name = f"{rev}:{path}"
    size = git(repo, "cat-file", "-s", name, allowed=(0, 128))
    if size.returncode or int(size.stdout) > 750_000:
        return None
    body = git(repo, "cat-file", "blob", name).stdout
    if b"\x00" in body:
        return None
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if PRIVATE_KEY.search(text):
        return None
    return text.splitlines(keepends=True)


def segments(lines):
    parts = []
    ordinary = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("<<<<<<< "):
            if MARKERS.match(line.rstrip("\r\n")):
                return None
            ordinary.append(line)
            i += 1
            continue
        if ordinary:
            parts.append(("text", ordinary))
        ordinary = []
        sides = [[], [], []]
        for side, end in zip(sides, ("||||||| ", "=======", ">>>>>>> ")):
            i += 1
            while i < len(lines) and not (
                lines[i].rstrip("\r\n") == end
                if end == "======="
                else lines[i].startswith(end)
            ):
                if MARKERS.match(lines[i].rstrip("\r\n")):
                    return None
                side.append(lines[i])
                i += 1
            if i == len(lines):
                return None
        parts.append(("conflict", sides))
        i += 1
    if ordinary:
        parts.append(("text", ordinary))
    return parts


def align_forward(parts, resolved):
    cursor = 0
    pending = False
    result = []
    for kind, text in parts:
        if kind == "conflict":
            if pending:
                return None
            pending = True
            continue
        if pending:
            start = next(
                (
                    i
                    for i in range(cursor, len(resolved) - len(text) + 1)
                    if resolved[i] == text[0] and resolved[i : i + len(text)] == text
                ),
                None,
            )
            if start is None:
                return None
            result.append(resolved[cursor:start])
            cursor = start
            pending = False
        elif resolved[cursor : cursor + len(text)] != text:
            return None
        cursor += len(text)
    if pending:
        result.append(resolved[cursor:])
        cursor = len(resolved)
    return result if cursor == len(resolved) else None


def aligned(parts, resolved):
    first = align_forward(parts, resolved)
    reverse = align_forward(
        [(k, v[::-1] if k == "text" else v) for k, v in reversed(parts)], resolved[::-1]
    )
    if (
        first is None
        or reverse is None
        or first != [x[::-1] for x in reversed(reverse)]
    ):
        return None
    return first


def conflict_hash(a, base, b):
    normalize = lambda lines: "\n".join(x.rstrip() for x in lines).strip("\n")
    x, y = sorted((normalize(a), normalize(b)))
    return hashlib.sha256(
        json.dumps((x, normalize(base), y), ensure_ascii=False).encode()
    ).hexdigest()


def classify(a, base, b, answer):
    for name, value in (
        ("ours", a),
        ("theirs", b),
        ("base", base),
        ("ours_then_theirs", a + b),
        ("theirs_then_ours", b + a),
        ("empty", []),
    ):
        if answer == value:
            return name
    original = set(a + base + b)
    return "new_lines" if any(line not in original for line in answer) else "interleave"


def replay(repo, meta, head, job):
    ts, merge, p1, p2 = job
    stats = Counter(merges=1)
    hunks = []
    try:
        state = git(
            repo,
            "-c",
            "merge.conflictStyle=diff3",
            "merge-tree",
            "--write-tree",
            "--messages",
            "-z",
            p1,
            p2,
            timeout=24,
            allowed=(0, 1),
        )
        if state.returncode == 0:
            stats["clean"] += 1
            return stats, hunks
        stats["conflicting"] += 1
        tree, *entries = state.stdout.split(b"\0")
        tree = tree.decode("ascii")
        paths = defaultdict(dict)
        for entry in itertools.takewhile(bool, entries):
            fields, path = entry.split(b"\t", 1)
            mode, oid, stage = fields.split()
            if mode.startswith(b"100"):
                paths[path.decode("utf-8")][stage.decode()] = oid.decode()
        subjects = {}
        for path, stages in paths.items():
            ext = Path(path).suffix.lstrip(".").lower()
            if ext not in CODE or IGNORE.search(path) or set(stages) != {"1", "2", "3"}:
                stats["skipped_path"] += 1
                continue
            before_merge, final = blob(repo, tree, path), blob(repo, merge, path)
            if (
                before_merge is None
                or final is None
                or any(MARKERS.match(x.rstrip("\r\n")) for x in final)
            ):
                stats["missing_or_invalid_file"] += 1
                continue
            parsed = segments(before_merge)
            if parsed is None or not any(k == "conflict" for k, _ in parsed):
                stats["missing_or_invalid_markers"] += 1
                continue
            answers = aligned(parsed, final)
            if answers is None:
                stats["unaligned_or_ambiguous"] += 1
                continue
            if not subjects:
                for name, commit in (("ours", p1), ("theirs", p2)):
                    subject = (
                        git(repo, "show", "-s", "--format=%s", commit)
                        .stdout.decode(errors="replace")
                        .strip()[:240]
                    )
                    subjects[name] = "" if PRIVATE_KEY.search(subject) else subject
            count = 0
            for i, (kind, sides) in enumerate(parsed):
                if kind != "conflict":
                    continue
                ours, base, theirs = sides
                answer = answers[count]
                count += 1
                before = (
                    parsed[i - 1][1][-60:]
                    if i > 0 and parsed[i - 1][0] == "text"
                    else []
                )
                after = (
                    parsed[i + 1][1][:30]
                    if i + 1 < len(parsed) and parsed[i + 1][0] == "text"
                    else []
                )
                if sum(len(line) for line in ours + base + theirs + answer) > 24_000:
                    stats["oversize_hunk"] += 1
                    continue
                stats["accepted_hunks"] += 1
                label = classify(ours, base, theirs, answer)
                stats[f"class_{label}"] += 1
                hunks.append(
                    dict(
                        repo=meta["repo"],
                        repo_id=meta["id"],
                        license=meta["license"],
                        language=meta["language"],
                        head=head,
                        merge=merge,
                        ts=int(ts),
                        path=path,
                        hunk_index=count - 1,
                        n_hunks_in_file=len(answers),
                        parents=[p1, p2],
                        stage_blobs=stages,
                        expected_blob=git(repo, "rev-parse", f"{merge}:{path}")
                        .stdout.decode()
                        .strip(),
                        ours=ours,
                        base=base,
                        theirs=theirs,
                        resolution=answer,
                        before=before,
                        after=after,
                        subjects=subjects,
                        cls=label,
                        hash=conflict_hash(ours, base, theirs),
                    )
                )
        return stats, hunks
    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
        stats["replay_error"] += 1
        return stats, hunks


def upload(source, key):
    if key.startswith("s3://"):
        run(["aws", "s3", "cp", "--quiet", str(source), key], timeout=95)
    else:
        dest = Path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)


def committed(key):
    if not key.startswith("s3://"):
        return Path(key).exists()
    p = run(["aws", "s3", "ls", key], timeout=12, allowed=(0, 1))
    return p.returncode == 0 and bool(p.stdout.strip())


def mine_repo(meta, work, prefix, args):
    if not REPO.fullmatch(meta["repo"]):
        raise ValueError("invalid GitHub repository name")
    with tempfile.TemporaryDirectory(dir=work) as temp:
        root = Path(temp)
        repo = root / "history.git"
        git(
            root,
            "-c",
            "protocol.file.allow=never",
            "clone",
            "--bare",
            "--single-branch",
            "--no-tags",
            "--branch",
            meta["branch"],
            "https://github.com/" + meta["repo"] + ".git",
            str(repo),
            timeout=360,
        )
        head = git(repo, "rev-parse", "HEAD").stdout.decode().strip()
        version = git(repo, "--version").stdout.decode().strip()
        out = f"{prefix}/shards/{meta['repo']}/{head}"
        contents = git(
            repo,
            "rev-list",
            "--timestamp",
            "--parents",
            "--min-parents=2",
            "--max-parents=2",
            f"--max-count={args.max_merges}",
            head,
            timeout=60,
        ).stdout.decode("ascii")
        jobs = [x.split() for x in contents.splitlines() if x]
        limit = min(args.deadline, time.time() + args.repo_seconds)
        total = Counter()
        with ThreadPoolExecutor(args.threads) as executor:
            for i in range(0, len(jobs), args.chunk):
                if time.time() + 35 >= limit:
                    break
                stem = f"{i:08d}-{len(jobs[i : i + args.chunk]):04d}"
                done = f"{out}/{stem}.json"
                if committed(done):
                    continue
                shard = root / "data.jsonl.gz"
                counts = Counter()
                with (
                    shard.open("wb") as f,
                    gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as zipped,
                ):
                    for stats, records in executor.map(
                        lambda x: replay(repo, meta, head, x), jobs[i : i + args.chunk]
                    ):
                        counts.update(stats)
                        for row in records:
                            zipped.write(
                                (
                                    json.dumps(
                                        row, ensure_ascii=False, separators=(",", ":")
                                    )
                                    + "\n"
                                ).encode()
                            )
                total.update(counts)
                summary = dict(
                    metadata=meta,
                    head=head,
                    git=version,
                    start=i,
                    counts=counts,
                    gzip_sha256=hashlib.sha256(shard.read_bytes()).hexdigest(),
                    format_version=1,
                )
                manifest = root / "shard.json"
                manifest.write_text(json.dumps(summary) + "\n")
                if counts["accepted_hunks"]:
                    upload(shard, f"{out}/{stem}.jsonl.gz")
                upload(manifest, done)
                print(
                    json.dumps(
                        dict(event="shard", repo=meta["repo"], start=i, counts=counts)
                    ),
                    flush=True,
                )
        print(
            json.dumps(
                dict(
                    event="repo_pass",
                    repo=meta["repo"],
                    head=head,
                    jobs=len(jobs),
                    counts=total,
                )
            ),
            flush=True,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--deadline", type=int, required=True)
    parser.add_argument("--threads", type=int, default=12)
    parser.add_argument("--chunk", type=int, default=256)
    parser.add_argument("--max-merges", type=int, default=60_000)
    parser.add_argument("--repo-seconds", type=int, default=1200)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    for meta in map(json.loads, args.manifest.open()):
        if time.time() + 60 >= args.deadline:
            break
        try:
            mine_repo(meta, args.work, args.out, args)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            print(
                json.dumps(
                    dict(event="repo_error", repo=meta["repo"], reason=str(error)[:200])
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
