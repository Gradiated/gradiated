#!/usr/bin/env python3
import hashlib
import json
import py_compile
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest = json.loads((ROOT / "PACKET_MANIFEST.json").read_text())
    for entry in manifest["files"]:
        path = ROOT / entry["path"]
        assert path.is_file(), path
        assert digest(path) == entry["sha256"], entry
    py_compile.compile(
        str(ROOT / "remote_request217_discriminator.py"),
        doraise=True,
    )
    repair = json.loads((ROOT / "REPAIR_CANDIDATE.json").read_text())
    launch = json.loads((ROOT / repair["candidate"]["launch_path"]).read_text())
    assert launch["args"][-4:] == [
        "--speculative-algorithm",
        "NGRAM",
        "--speculative-attention-mode",
        "decode",
    ]
    packet = json.loads((ROOT / "DISCRIMINATOR_PACKET.json").read_text())
    assert packet["execution"]["requests"] == 218
    assert set(packet["gates"]) == {
        "all_218_complete",
        "failures_zero",
        "native_ngram_activation_observed",
        "normalized_semantics_exact",
        "release_drift_bounded",
        "request_217_token_19_exact",
    }


if __name__ == "__main__":
    main()
