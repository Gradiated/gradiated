"""Test the saved warm-boot warning-anchor recovery without board access."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy
from types import SimpleNamespace


def load(path):
    return json.loads(path.read_bytes())


def rejects(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError("A changed warning reference or state was accepted")


def test(repo, packet):
    generator = runpy.run_path(str(packet / "prepare_retry_support.py"))
    invocation = load(packet / "invocation.json")
    verified = (packet / "assets.json").read_bytes()
    assert sha256(verified).hexdigest() == invocation["board_pins"]["assets.json"]
    settings = json.loads(verified)
    supervisor = runpy.run_path(str(packet / "observer_validation.py"))
    lifecycle = SimpleNamespace(**runpy.run_path(str(packet / "observer_lifecycle.py")))
    check = supervisor["accepted_warning_anchor"]
    anchor_path = repo / generator["ANCHOR_LOCATION"]
    anchor_bytes = anchor_path.read_bytes()
    assert sha256(anchor_bytes).hexdigest() == generator["ANCHOR_PIN"]
    baseline = load(anchor_path.parents[1] / "preflight/before.state.json")
    anchor = check(settings, lifecycle, baseline)
    aborted = anchor_path.parents[2] / generator["ABORTED"] / "preflight/before.state.json"
    assert aborted.read_bytes() == anchor_bytes
    assert anchor == json.loads(anchor_bytes) and lifecycle.notices(anchor, anchor) == []

    def with_anchor(**changes):
        return {"warning_anchor": {**settings["warning_anchor"], **changes}}

    rejects(lambda: check(with_anchor(raw_text=anchor_bytes.decode() + " "), lifecycle, baseline))
    rejects(lambda: check(with_anchor(raw_text="{}", sha256=sha256(b"{}").hexdigest()), lifecycle, baseline))
    rejects(lambda: lifecycle.check_state(anchor, {**baseline, "boot_id": "wrong-boot"}, "stock"))
    rejects(lambda: lifecycle.notices(anchor, {**anchor, "warnings": anchor["warnings"] + "[ 1] new warning\n"}))
    print("PASS exact anchor and rejection of tampering, rehashing, wrong boot and new warnings")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("packet", type=Path)
    args = parser.parse_args()
    test(args.repo, args.packet)
