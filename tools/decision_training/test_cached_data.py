import json
from pathlib import Path

import pytest
from cached_data import digest, verified_release, verify_cache_runtime


def test_cache_runtime_compares_the_installed_implementation_contract(
    tmp_path, monkeypatch
):
    import cached_data

    metadata = tmp_path / "metadata"
    metadata.mkdir()
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
    assert verified_release(tmp_path, 2048) == manifest
    with pytest.raises(ValueError, match="token limit"):
        verified_release(tmp_path, 4096)
    (tmp_path / "dev.jsonl").write_text("altered data")
    with pytest.raises(ValueError, match="bytes changed"):
        verified_release(tmp_path, 2048)
