"""Measure untruncated native Inkling token lengths for every canonical candidate."""

import argparse
import collections
import concurrent.futures
import hashlib
import importlib.metadata
import json
import os
import signal
import time
from contextlib import contextmanager
from pathlib import Path

from prepare_scale import digest_file
from prompting import render_prompt
from runtime import runtime_fingerprint

TOKENIZER = None


@contextmanager
def terminating_pool(**kwargs):
    pool = concurrent.futures.ProcessPoolExecutor(**kwargs)
    try:
        yield pool
    except BaseException:
        processes = list(pool._processes.values()) if pool._processes else []
        for process in processes:
            if process.is_alive():
                process.kill()
        pool.shutdown(wait=False, cancel_futures=True)
        for process in processes:
            process.join(timeout=0.1)
        raise
    else:
        pool.shutdown(wait=True)


def verify_tokenizer_directory(root, manifest):
    root = Path(root)
    expected = set()
    for item in manifest["files"]:
        path = Path(item["file"])
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("invalid tokenizer manifest path")
        expected.add(str(path))
    actual = {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
        and not path.relative_to(root).is_relative_to(".cache/huggingface")
    }
    if actual != expected:
        raise ValueError("tokenizer files differ from pinned manifest")
    if (
        not {"tokenizer.json", "tokenizer_config.json", "chat_template.jinja"}
        <= expected
    ):
        raise ValueError("tokenizer manifest lacks required loading artifacts")
    for item in manifest["files"]:
        if digest_file(root / item["file"]) != item["sha256"]:
            raise ValueError("tokenizer file mismatch")


def initialize(tokenizer_dir):
    global TOKENIZER
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    from transformers import AutoTokenizer

    TOKENIZER = AutoTokenizer.from_pretrained(tokenizer_dir, local_files_only=True)


def measure(work):
    offset, records = work
    rows = [json.loads(record) for record in records]
    prompts = [render_prompt(TOKENIZER, row) for row in rows]
    ids = TOKENIZER(prompts, add_special_tokens=False, truncation=False, padding=False)[
        "input_ids"
    ]
    lengths = [len(values) for values in ids]
    samples = []
    if offset % 25000 == 0:
        for j in (0, len(rows) // 2, len(rows) - 1):
            if len(prompts[j]) <= 100000:
                samples.append(
                    {
                        "candidate_n": offset + j,
                        "row": rows[j],
                        "tokens": lengths[j],
                        "ids_sha256": hashlib.sha256(
                            b"".join(value.to_bytes(4, "little") for value in ids[j])
                        ).hexdigest(),
                    }
                )
    return offset, lengths, samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--tokenizer-dir", type=Path, required=True)
    parser.add_argument("--tokenizer-manifest", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seconds", type=int, default=3600)
    args = parser.parse_args()
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not 1 <= args.workers <= 32 or args.seconds < 1:
        raise ValueError("invalid tokenizer audit bounds")
    started = time.monotonic()
    deadline = started + args.seconds

    def check(*alarm):
        if alarm or time.monotonic() >= deadline:
            raise TimeoutError("token audit deadline")

    signal.signal(signal.SIGALRM, check)
    signal.setitimer(signal.ITIMER_REAL, args.seconds)
    root = args.run_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("retain previous token audits; output must be empty")
    candidate_manifest = json.loads((args.candidates / "COMPLETE.json").read_text())[
        "manifest_sha256"
    ]
    if digest_file(args.candidates / "manifest.json") != candidate_manifest:
        raise ValueError("candidate manifest mismatch")
    manifest = json.loads((args.candidates / "manifest.json").read_text())
    tokenizer_manifest = json.loads(args.tokenizer_manifest.read_text())
    if tokenizer_manifest["revision"] != "6e7c8248f75265bdd4fbab5273304243b5d8c2cb":
        raise ValueError("wrong tokenizer revision")
    verify_tokenizer_directory(args.tokenizer_dir, tokenizer_manifest)
    source = root / "source"
    source.mkdir()
    source_hashes = {}
    for name in (
        "audit_tokens.py",
        "prompting.py",
        "prepare_scale.py",
        "data.py",
        "scale_data.py",
        "original_data.py",
        "runtime.py",
    ):
        content = Path(__file__).with_name(name).read_bytes()
        (source / name).write_bytes(content)
        source_hashes[name] = hashlib.sha256(content).hexdigest()
    versions = {
        name: importlib.metadata.version(name)
        for name in ("transformers", "tokenizers", "jinja2", "pyarrow")
    }
    implementation = runtime_fingerprint(check)
    if versions["tokenizers"] != "0.23.3" or versions["jinja2"] != "3.1.6":
        raise ValueError("tokenizer/Jinja must match frozen native runtime")
    direct_url = json.loads(
        importlib.metadata.distribution("transformers").read_text("direct_url.json")
        or "{}"
    )
    if (
        direct_url.get("vcs_info", {}).get("commit_id")
        != "e3a65e2c21abb9c25a03704f2f25852f9ad03a18"
    ):
        raise ValueError("Transformers must use frozen native source commit")
    counts = collections.Counter()
    files = []
    offset = 0
    with (
        terminating_pool(
            max_workers=args.workers,
            initializer=initialize,
            initargs=(str(args.tokenizer_dir.resolve()),),
        ) as pool,
        (root / "conformance-panel.jsonl").open("w") as panel,
    ):
        for item in manifest["files"]:
            if time.monotonic() >= deadline:
                raise TimeoutError("token audit deadline")
            path = args.candidates / item["file"]
            if digest_file(path) != item["sha256"]:
                raise ValueError("candidate shard mismatch")
            work = []
            for batch in pq.ParquetFile(path).iter_batches(
                batch_size=1000, columns=["record_json"]
            ):
                check()
                records = batch.column(0).to_pylist()
                work.append((offset, records))
                offset += len(records)
            lengths = []
            for first, values, samples in pool.map(
                measure, work, timeout=max(0.001, deadline - time.monotonic())
            ):
                if time.monotonic() >= deadline:
                    raise TimeoutError("token audit deadline")
                lengths.extend(
                    {"candidate_n": first + i, "tokens": length}
                    for i, length in enumerate(values)
                )
                counts["questions"] += len(values)
                counts["tokens"] += sum(values)
                counts["maximum_tokens"] = max(counts["maximum_tokens"], max(values))
                for limit in (1024, 2048, 4096, 8192, 16384):
                    fits = [length for length in values if length <= limit]
                    counts[f"fit_{limit}_questions"] += len(fits)
                    counts[f"fit_{limit}_tokens"] += sum(fits)
                for sample in samples:
                    panel.write(json.dumps(sample, ensure_ascii=False) + "\n")
            output = root / item["file"].replace("candidate-", "lengths-")
            pq.write_table(pa.Table.from_pylist(lengths), output, compression="zstd")
            files.append(
                {
                    "file": output.name,
                    "rows": len(lengths),
                    "sha256": digest_file(output),
                }
            )
            print(
                json.dumps(
                    {
                        "file": item["file"],
                        "questions": counts["questions"],
                        "tokens": counts["tokens"],
                        "elapsed": time.monotonic() - started,
                    }
                ),
                flush=True,
            )
    result = {
        "status": "TOKEN_LENGTH_AUDIT_ONLY_NOT_ADMITTED",
        "counts": dict(counts),
        "files": files,
        "candidate_manifest_sha256": candidate_manifest,
        "tokenizer": tokenizer_manifest,
        "runtime_versions": versions,
        "runtime_implementation": implementation,
        "transformers_install": direct_url,
        "executable_sources_sha256": source_hashes,
        "seconds": time.monotonic() - started,
        "remaining": "native conformance check, semantic/source admission, overlap/group holdouts and actual survivor token totals",
    }
    (root / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    (root / "COMPLETE.json").write_text(
        json.dumps(
            {
                "audit_sha256": digest_file(root / "audit.json"),
                "panel_sha256": digest_file(root / "conformance-panel.jsonl"),
            }
        )
        + "\n"
    )
    print(
        json.dumps(
            {"complete": True, "counts": dict(counts), "seconds": result["seconds"]}
        ),
        flush=True,
    )
    signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    main()
