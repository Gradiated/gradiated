import json
from pathlib import Path

import pytest
from cached_data import digest, verified_release, verify_cache_runtime


def test_cache_runtime_compares_the_installed_implementation_contract(
    tmp_path, monkeypatch
):
    import cached_data

    monkeypatch.setattr(
        cached_data,
        "require_native_runtime",
        lambda path, implementation: pytest.fail(
            "embedded runtime must not read external attestation"
        ),
    )

    metadata = tmp_path / "metadata"
    metadata.mkdir()
    (metadata / "COMPLETE.json").write_text("nested completion record")
    (metadata / "tokenizer-manifest.json").write_text(json.dumps({"files": []}))
    monkeypatch.setattr(cached_data, "digest", lambda path: "sha")
    monkeypatch.setattr(cached_data.importlib.metadata, "version", lambda name: "1")
    manifest = {
        "prompting_sha256": "sha",
        "tokenizer_manifest_sha256": "sha",
        "tokenizer_runtime": {"tokenizers": "1"},
        "tokenizer_implementation": {"transformers/lazy.py": "original"},
    }
    verify_cache_runtime(
        tmp_path,
        tmp_path / "model",
        manifest,
        {"installed_package_files_sha256": {"transformers/lazy.py": "original"}},
    )
    with pytest.raises(ValueError, match="implementation bytes"):
        verify_cache_runtime(
            tmp_path,
            tmp_path / "model",
            manifest,
            {"installed_package_files_sha256": {"transformers/lazy.py": "altered"}},
        )


def test_release_requires_byte_identity_and_reviewed_candidate_generation(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("cached_data.verify_benchmark", lambda path: "frozen")
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    (metadata / "COMPLETE.json").write_text("nested completion record")
    source = tmp_path / "source"
    source.mkdir()
    stage = source / "release_export.py"
    stage.write_text("reviewed stage")
    stage_sha = digest(stage)
    approvals = json.loads(
        Path(__file__).with_name("candidate_approvals.json").read_text()
    )
    index = metadata / "index.json"
    index.write_text(
        json.dumps({"input_manifests": [{"sha256": next(iter(approvals))}]})
    )
    (tmp_path / "dev.jsonl").write_text("{}\n")
    (tmp_path / "jevbench-231.jsonl").write_text("{}\n")
    manifest = {
        "status": "ADMITTED_RESEARCH_RELEASE",
        "max_length": 2048,
        "files": [],
        "index_identity": {"index_sha256": digest(index)},
        "dev_sha256": digest(tmp_path / "dev.jsonl"),
        "benchmark_sha256": digest(tmp_path / "jevbench-231.jsonl"),
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    files = [
        {"file": str(path.relative_to(tmp_path)), "sha256": digest(path)}
        for path in tmp_path.rglob("*")
        if path.is_file()
    ]
    (tmp_path / "COMPLETE.json").write_text(
        json.dumps(
            {"manifest_sha256": digest(tmp_path / "manifest.json"), "files": files}
        )
    )
    monkeypatch.setattr(
        "cached_data.approvals",
        lambda: {
            "releases": {
                digest(tmp_path / "manifest.json"): {
                    "stage_sources": {"source/release_export.py": stage_sha}
                }
            }
        },
    )
    assert verified_release(tmp_path, 2048) == manifest
    original_marker = (tmp_path / "COMPLETE.json").read_bytes()
    stage.write_text("locally altered builder")
    marker = json.loads(original_marker)
    for item in marker["files"]:
        if item["file"] == "source/release_export.py":
            item["sha256"] = digest(stage)
    (tmp_path / "COMPLETE.json").write_text(json.dumps(marker))
    with pytest.raises(ValueError, match="executable bytes"):
        verified_release(tmp_path, 2048)
    stage.write_text("reviewed stage")
    (tmp_path / "COMPLETE.json").write_bytes(original_marker)
    with pytest.raises(ValueError, match="token limit"):
        verified_release(tmp_path, 4096)
    (tmp_path / "dev.jsonl").write_text("altered data")
    with pytest.raises(ValueError, match="bytes changed"):
        verified_release(tmp_path, 2048)


def test_cache_deadline_is_checked_before_loading_a_shard(tmp_path):
    from cached_data import read_cached

    def expired():
        raise TimeoutError("cache owner deadline")

    with pytest.raises(TimeoutError, match="cache owner deadline"):
        list(read_cached(tmp_path, {}, expired))
    with pytest.raises(TimeoutError, match="cache owner deadline"):
        verified_release(tmp_path, 2048, expired)
