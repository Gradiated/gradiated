"""Replay calibration only with pinned native tokenizer and implementation bytes."""

import hashlib
import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from native_runtime import approvals
from runtime import runtime_fingerprint

TOKEN_PACKAGES = ("transformers", "tokenizers", "jinja2")


def token_implementations(runtime):
    return {
        name: value
        for name, value in runtime["installed_package_files_sha256"].items()
        if name.split("/", 1)[0] in TOKEN_PACKAGES
    }


def verify_calibration_runtime(identity, implementation, attestation_path=None):
    expected = identity.get("runtime")
    if expected is None:
        if attestation_path is None:
            raise ValueError(
                "legacy comparison requires reviewed --runtime-attestation"
            )
        content = attestation_path.read_bytes()
        if (
            hashlib.sha256(content).hexdigest()
            not in approvals()["runtime_attestations"]
        ):
            raise ValueError("calibration runtime attestation has not been reviewed")
        expected = json.loads(content)["runtime"]
    files = token_implementations(expected)
    if not files or files != token_implementations(implementation):
        raise ValueError("calibration tokenizer implementation differs from run")
    for name in TOKEN_PACKAGES:
        if expected["packages"][name] != implementation["packages"][name]:
            raise ValueError("calibration tokenizer package identity differs from run")


@contextmanager
def calibration_tokenizer(root, identity, attestation_path=None):
    manifest = json.loads(
        Path(__file__).with_name("tokenizer_identity.json").read_text()
    )
    if any(
        identity.get(key) != manifest[key] for key in ("model", "revision", "prompt")
    ):
        raise ValueError("comparison is not the pinned native model and prompt")
    renderer_sha = hashlib.sha256(
        Path(__file__).with_name("prompting.py").read_bytes()
    ).hexdigest()
    recorded_renderer = identity.get("executable_sources_sha256", {}).get(
        "runner/prompting.py", renderer_sha
    )
    if (
        renderer_sha != manifest["prompting_sha256"]
        or recorded_renderer != renderer_sha
    ):
        raise ValueError("calibration renderer differs from native run")
    implementation = runtime_fingerprint(package_names=TOKEN_PACKAGES)
    verify_calibration_runtime(identity, implementation, attestation_path)
    # Load only verified copies; other artifacts in a model directory cannot affect replay.
    with TemporaryDirectory(prefix="inkling-calibration-tokenizer-") as directory:
        view = Path(directory)
        for item in manifest["files"]:
            target = view / item["file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / item["file"], target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("calibration tokenizer files differ from pinned model")
        from transformers import AutoTokenizer

        yield AutoTokenizer.from_pretrained(view, local_files_only=True)
