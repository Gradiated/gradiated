"""Consume a byte-verified release cache bound to the actual renderer/tokenizer."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

from data import validate_row


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verified_release(root, max_length):
    marker = json.loads((root / "COMPLETE.json").read_text())
    if digest(root / "manifest.json") != marker["manifest_sha256"]:
        raise ValueError("release manifest mismatch")
    manifest = json.loads((root / "manifest.json").read_text())
    approvals = json.loads(
        Path(__file__).with_name("candidate_approvals.json").read_text()
    )
    index = json.loads((root / "metadata" / "index.json").read_text())
    if (
        digest(root / "metadata" / "index.json")
        != manifest["index_identity"]["index_sha256"]
    ):
        raise ValueError("release index identity mismatch")
    if any(item["sha256"] not in approvals for item in index["input_manifests"]):
        raise ValueError("release contains an unapproved candidate builder")
    if (
        manifest["status"] != "ADMITTED_RESEARCH_RELEASE"
        or manifest["max_length"] != max_length
    ):
        raise ValueError("release is not admitted at the requested token limit")
    expected = set()
    for item in marker["files"]:
        relative = Path(item["file"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe release file path")
        if item["file"] in expected:
            raise ValueError("duplicate release file")
        expected.add(item["file"])
        if digest(root / relative) != item["sha256"]:
            raise ValueError("release bytes changed: " + item["file"])
    actual = {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and path.name != "COMPLETE.json"
    }
    if actual != expected:
        raise ValueError("release file set changed")
    for item in manifest["files"]:
        if (
            item["file"] not in expected
            or digest(root / item["file"]) != item["sha256"]
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
        attestation = json.loads((model.parent / "cache-runtime.json").read_text())
        if attestation["manifest_sha256"] != digest(root / "manifest.json"):
            raise ValueError("cache runtime attestation belongs to another release")
        recorded = attestation["package_files"]
    if not token_files(recorded) or token_files(recorded) != token_files(
        implementation["package_files"]
    ):
        raise ValueError("cache tokenization implementation bytes differ")


def read_cached(root, manifest):
    import pyarrow.parquet as pq

    count = 0
    for item in manifest["files"]:
        for batch in pq.ParquetFile(root / item["file"]).iter_batches(batch_size=2048):
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
