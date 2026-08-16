#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

PACKET = Path(__file__).with_name("upstream_onehead_fp8_packet.py")


def test_packet_self_test() -> None:
    result = subprocess.run([sys.executable, str(PACKET), "--self-test"], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["self_test"] is True
    assert payload["l40s_splits"] == 32
    assert payload["slot_count"] == 64


def test_remote_and_controller_roots_match() -> None:
    remote = Path(__file__).with_name("remote_upstream_onehead_packet.sh").read_text()
    assert "/workspace/campaign-100-mla-microbench" in remote
    assert "/workspace/public-mla-microbench/mla-microbench.tar.gz" in remote
    assert "allocation-result.json" in remote


def test_manifest_contract_is_single_command() -> None:
    manifest = json.loads(Path(__file__).with_name("PACKET_MANIFEST.json").read_text())
    assert manifest["runtime_image"].endswith("94a0aff7a289f23bcefa189d11841e487991405d86da782a63bf6e5f95d0d39a")
    assert manifest["command"][0].endswith("mla_microbench_control.py")
    assert "UPSTREAM_ONEHEAD_FP8_COMPONENT_PASS" in manifest["retention_trigger"]
    assert manifest["ssh_public_key_input"] == "one-line OpenSSH public key, no PEM wrapping"
