import hashlib
import json

import pytest
from native_runtime import require_native_runtime


def test_same_version_local_tokenizer_changes_cannot_self_attest(tmp_path, monkeypatch):
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps({"package_files": {"transformers/lazy.py": "reviewed"}}))
    approved = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "native_runtime.approvals", lambda: {"runtime_attestations": [approved]}
    )
    implementation = {
        "installed_package_files_sha256": {"transformers/lazy.py": "reviewed"},
        "packages": {
            "tokenizers": {"version": "0.23.3"},
            "jinja2": {"version": "3.1.6"},
            "transformers": {
                "vcs": {"commit_id": "e3a65e2c21abb9c25a03704f2f25852f9ad03a18"}
            },
        },
    }
    require_native_runtime(path, implementation)
    implementation["installed_package_files_sha256"]["transformers/lazy.py"] = "altered"
    with pytest.raises(ValueError, match="native bytes"):
        require_native_runtime(path, implementation)
    path.write_text(
        json.dumps({"package_files": implementation["installed_package_files_sha256"]})
    )
    with pytest.raises(ValueError, match="not been reviewed"):
        require_native_runtime(path, implementation)
