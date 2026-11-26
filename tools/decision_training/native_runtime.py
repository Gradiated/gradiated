"""Require reviewed native tokenization bytes, not only self-reported versions."""

import hashlib
import json
from pathlib import Path


def approvals():
    return json.loads(Path(__file__).with_name("release_approvals.json").read_text())


def token_files(files):
    return {
        name: value
        for name, value in files.items()
        if name.split("/", 1)[0] in ("transformers", "tokenizers", "jinja2", "pyarrow")
    }


def require_native_runtime(attestation_path, implementation):
    content = attestation_path.read_bytes()
    if hashlib.sha256(content).hexdigest() not in approvals()["runtime_attestations"]:
        raise ValueError("tokenizer runtime attestation has not been reviewed")
    attestation = json.loads(content)
    expected = token_files(attestation["package_files"])
    actual = token_files(implementation["installed_package_files_sha256"])
    if not expected or actual != expected:
        raise ValueError("tokenizer implementation differs from reviewed native bytes")
    packages = implementation["packages"]
    if (
        packages["tokenizers"]["version"] != "0.23.3"
        or packages["jinja2"]["version"] != "3.1.6"
        or (packages["transformers"].get("vcs") or {}).get("commit_id")
        != "e3a65e2c21abb9c25a03704f2f25852f9ad03a18"
    ):
        raise ValueError("tokenizer runtime is not the frozen native installation")
    return attestation
