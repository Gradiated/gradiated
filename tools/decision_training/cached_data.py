"""Consume a byte-verified release cache bound to the actual renderer/tokenizer."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

from benchmark_identity import verify_benchmark
from data import validate_row
from native_runtime import approvals, require_native_runtime


def digest(path, check=lambda: None):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            check()
            value.update(block)
    return value.hexdigest()


def verified_release(root, max_length, check=lambda: None):
    check()
    verify_benchmark(root / "jevbench-231.jsonl")
    marker = json.loads((root / "COMPLETE.json").read_text())
    if digest(root / "manifest.json") != marker["manifest_sha256"]:
        raise ValueError("release manifest mismatch")
    manifest = json.loads((root / "manifest.json").read_text())
    approved_release = approvals()["releases"].get(marker["manifest_sha256"])
    if approved_release is None:
        raise ValueError("release-stage builders have not been reviewed")
    for name, expected_sha in approved_release["stage_sources"].items():
        if digest(root / name, check) != expected_sha:
            raise ValueError("release-stage executable bytes differ from approval")
    candidate_approvals = json.loads(
        Path(__file__).with_name("candidate_approvals.json").read_text()
    )
    index = json.loads((root / "metadata" / "index.json").read_text())
    if (
        digest(root / "metadata" / "index.json")
        != manifest["index_identity"]["index_sha256"]
    ):
        raise ValueError("release index identity mismatch")
    if any(
        item["sha256"] not in candidate_approvals for item in index["input_manifests"]
    ):
        raise ValueError("release contains an unapproved candidate builder")
    if (
        manifest["status"]
        not in ("ADMITTED_RESEARCH_RELEASE", "EXPORTED_RESEARCH_RELEASE_PENDING_REVIEW")
        or manifest["max_length"] != max_length
    ):
        raise ValueError("release is not admitted at the requested token limit")
    expected = set()
    for item in marker["files"]:
        check()
        relative = Path(item["file"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe release file path")
        if item["file"] in expected:
            raise ValueError("duplicate release file")
        expected.add(item["file"])
        if digest(root / relative, check) != item["sha256"]:
            raise ValueError("release bytes changed: " + item["file"])
    actual = {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and path != root / "COMPLETE.json"
    }
    if actual != expected:
        raise ValueError("release file set changed")
    for item in manifest["files"]:
        if (
            item["file"] not in expected
            or digest(root / item["file"], check) != item["sha256"]
        ):
            raise ValueError("cached training shard mismatch")
    for name, field in (
        ("dev.jsonl", "dev_sha256"),
        ("jevbench-231.jsonl", "benchmark_sha256"),
    ):
        if digest(root / name) != manifest[field]:
            raise ValueError("release scored-data identity mismatch")
    return manifest


def verify_cache_runtime(root, model, manifest, implementation):
    if digest(Path(__file__).with_name("prompting.py")) != manifest["prompting_sha256"]:
        raise ValueError("cache renderer differs from running renderer")
    token_path = root / "metadata" / "tokenizer-manifest.json"
    if digest(token_path) != manifest["tokenizer_manifest_sha256"]:
        raise ValueError("cache tokenizer manifest mismatch")
    tokens = json.loads(token_path.read_text())
    for item in tokens["files"]:
        if digest(model / item["file"]) != item["sha256"]:
            raise ValueError("cached IDs belong to another tokenizer")
    if any(
        importlib.metadata.version(name) != version
        for name, version in manifest["tokenizer_runtime"].items()
    ):
        raise ValueError("cache tokenizer runtime differs")

    def token_files(files):
        return {
            name: value
            for name, value in files.items()
            if name.split("/", 1)[0]
            in ("transformers", "tokenizers", "jinja2", "pyarrow")
        }

    recorded = manifest.get("tokenizer_implementation")
    if recorded is None:
        attestation = require_native_runtime(
            model.parent / "cache-runtime.json", implementation
        )
        if attestation["manifest_sha256"] != digest(root / "manifest.json"):
            raise ValueError("cache runtime attestation belongs to another release")
        recorded = attestation["package_files"]
    if not token_files(recorded) or token_files(recorded) != token_files(
        implementation["installed_package_files_sha256"]
    ):
        raise ValueError("cache tokenization implementation bytes differ")


def read_cached(root, manifest, check=lambda: None):
    check()
    import pyarrow.parquet as pq

    count = 0
    for item in manifest["files"]:
        check()
        for batch in pq.ParquetFile(root / item["file"]).iter_batches(batch_size=2048):
            check()
            for cached in batch.to_pylist():
                row = validate_row(json.loads(cached["record_json"]))
                ids = cached["input_ids"]
                if (
                    not ids
                    or len(ids) > manifest["max_length"]
                    or any(not isinstance(value, int) or value < 0 for value in ids)
                ):
                    raise ValueError("invalid cached token sequence")
                count += 1
                yield {**row, "ids": ids}
    if count != manifest["counts"]["train_questions"]:
        raise ValueError("cached row count mismatch")


def main():
    import argparse
    import signal
    import time

    from data import read_jsonl
    from runtime import runtime_fingerprint

    parser = argparse.ArgumentParser(
        description="Read-only reviewed release/runtime verification, with optional checkpoint and baseline checks"
    )
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--seconds", type=int, default=180)
    args = parser.parse_args()
    if args.seconds < 1:
        parser.error("--seconds must be positive")
    deadline = time.monotonic() + args.seconds

    def check(*alarm):
        if alarm or time.monotonic() >= deadline:
            raise TimeoutError("read-only release verification deadline")

    signal.signal(signal.SIGALRM, check)
    signal.setitimer(signal.ITIMER_REAL, args.seconds)
    manifest = verified_release(args.release_root, 2048, check)
    implementation = runtime_fingerprint(check)
    verify_cache_runtime(args.release_root, args.model, manifest, implementation)
    if args.checkpoint or args.baseline_dir:
        from train import baseline_complete, verify_checkpoint_payloads

        if args.checkpoint:
            verify_checkpoint_payloads(
                args.checkpoint,
                json.loads((args.checkpoint / "checkpoint-complete.json").read_text()),
                check,
            )
        if args.baseline_dir:
            for name, rows in (
                ("baseline-dev", read_jsonl(args.release_root / "dev.jsonl")[:256]),
                (
                    "baseline-jevbench",
                    read_jsonl(args.release_root / "jevbench-231.jsonl"),
                ),
            ):
                if not baseline_complete(args.baseline_dir, name, rows):
                    raise ValueError("baseline consumed fields invalid: " + name)
    print(
        json.dumps(
            {
                "status": "reviewed_sources_runtime_payloads_verified",
                "manifest_sha256": digest(args.release_root / "manifest.json", check),
                "counts": manifest["counts"],
                "checkpoint": str(args.checkpoint) if args.checkpoint else None,
                "baseline_dir": str(args.baseline_dir) if args.baseline_dir else None,
            }
        ),
        flush=True,
    )
    signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == "__main__":
    main()
