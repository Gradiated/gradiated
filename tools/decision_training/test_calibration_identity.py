import hashlib
import json
import sys
from types import SimpleNamespace

import pytest
from calibration_identity import (
    TOKEN_PACKAGES,
    calibration_tokenizer,
    verify_calibration_runtime,
)


def implementation():
    return {
        "packages": {name: {"version": "native"} for name in TOKEN_PACKAGES},
        "installed_package_files_sha256": {"transformers/lazy.py": "native-bytes"},
    }


def test_same_version_tokenizer_implementation_and_package_changes_fail():
    expected = implementation()
    actual = implementation()
    verify_calibration_runtime({"runtime": expected}, actual)
    actual["installed_package_files_sha256"]["transformers/lazy.py"] = "altered"
    with pytest.raises(ValueError, match="implementation"):
        verify_calibration_runtime({"runtime": expected}, actual)
    actual = implementation()
    actual["packages"]["jinja2"]["version"] = "other"
    with pytest.raises(ValueError, match="package identity"):
        verify_calibration_runtime({"runtime": expected}, actual)


def test_legacy_comparison_requires_reviewed_runtime(tmp_path, monkeypatch):
    actual = implementation()
    with pytest.raises(ValueError, match="legacy comparison"):
        verify_calibration_runtime({}, actual)
    path = tmp_path / "attestation.json"
    path.write_text(json.dumps({"runtime": actual}))
    with pytest.raises(ValueError, match="not been reviewed"):
        verify_calibration_runtime({}, actual, path)
    approved = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "calibration_identity.approvals", lambda: {"runtime_attestations": [approved]}
    )
    verify_calibration_runtime({}, actual, path)


def test_modified_tokenizer_rejected_and_extra_artifacts_not_loaded(
    tmp_path, monkeypatch
):
    from pathlib import Path

    import calibration_identity as module

    original_read = Path.read_text
    renderer_sha = hashlib.sha256(
        Path(module.__file__).with_name("prompting.py").read_bytes()
    ).hexdigest()
    manifest = {
        "model": "pinned",
        "revision": "revision",
        "prompt": "prompt",
        "prompting_sha256": renderer_sha,
        "files": [
            {
                "file": "tokenizer.json",
                "sha256": hashlib.sha256(b"original").hexdigest(),
            }
        ],
    }
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path, *a, **kw: (
            json.dumps(manifest)
            if path.name == "tokenizer_identity.json"
            else original_read(path, *a, **kw)
        ),
    )
    monkeypatch.setattr(module, "runtime_fingerprint", lambda **kw: implementation())
    loaded = []

    def load(view, local_files_only):
        loaded.append(True)
        assert local_files_only
        assert [p.name for p in view.iterdir()] == ["tokenizer.json"]
        return "verified tokenizer"

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoTokenizer=SimpleNamespace(from_pretrained=load)),
    )
    (tmp_path / "tokenizer.json").write_bytes(b"original")
    (tmp_path / "added_tokens.json").write_text("unverified extra artifact")
    identity = {
        **{k: manifest[k] for k in ("model", "revision", "prompt")},
        "runtime": implementation(),
    }
    with calibration_tokenizer(tmp_path, identity) as tokenizer:
        assert tokenizer == "verified tokenizer"
    (tmp_path / "tokenizer.json").write_bytes(b"modified")
    with (
        pytest.raises(ValueError, match="tokenizer files"),
        calibration_tokenizer(tmp_path, identity),
    ):
        pytest.fail("modified tokenizer reached loading")
    assert len(loaded) == 1
