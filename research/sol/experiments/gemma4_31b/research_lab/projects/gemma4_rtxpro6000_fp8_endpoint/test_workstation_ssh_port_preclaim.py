#!/usr/bin/env python3
"""Offline contract fixture for the Workstation SSH-port owner repair."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("owner", ROOT / "run_rtxpro6000_fp8_endpoint_owner.py")
assert SPEC and SPEC.loader
owner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(owner)


def main() -> int:
    with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as temporary:
        binding_path = Path(temporary) / "fixture.json"
        binding = {
            "project": "gemma4_rtxpro6000_fp8_endpoint", "claim_allowed": True,
            "bench": {"provider": "runpod", "accelerator": "nvidia-rtx-pro-6000-blackwell-workstation", "sm": "sm_120", "gpu_count": 1, "id": "fixture", "checkpoint_reconcile_command": "true", "server_launch_command": "true", "resource": {"public_ipv4": "213.192.6.70", "ssh_user": "root", "known_hosts_namespace": "/root/.config/runpod/gemma4/known_hosts", "ssh_identity_path": "/root/.config/nebius/glm-campaign/ssh_ed25519", "ssh_port": 40070}},
            "lifecycle": {"claim_start_by_utc": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat(), "owner_deadline_utc": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)).isoformat()},
        }
        binding_path.write_text(json.dumps(binding))
        accepted = owner.binding_contract(binding_path)
        argv = owner.ssh_base(accepted)
        assert argv[:3] == ["ssh", "-p", "40070"]
        assert "BatchMode=yes" in argv and "StrictHostKeyChecking=yes" in argv
        assert "/root/.config/runpod/gemma4/known_hosts" in " ".join(argv)
        assert argv[-1] == "root@213.192.6.70"
    print(json.dumps({"binding": "accepted", "argv": argv, "ssh_port_type": "integer"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
