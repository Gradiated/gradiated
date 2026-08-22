#!/usr/bin/env python3
"""Build the immutable offline packet and PRECLAIM terminal for this project."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import argparse
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
FACTORY = ROOT.parents[6] / "research" / "factory" / "tools"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-update", action="store_true")
    args = parser.parse_args()
    packet_path = ROOT / "RTXPRO6000_FP8_EXECUTION_PACKET.json"
    packet_sha = sha256(packet_path)
    files = [
        "run_rtxpro6000_fp8_endpoint_owner.py",
        "materialize_rtxpro6000_c32_workload.py",
        "inputs/c32_identity.json",
        "inputs/c32_requests.jsonl",
        "inputs/qualified_c32_request_payloads.json",
        "inputs/model_inputs/chat_template.jinja",
        "inputs/model_inputs/config.json",
        "inputs/model_inputs/processor_config.json",
        "inputs/model_inputs/tokenizer.json",
        "inputs/model_inputs/tokenizer_config.json",
    ]
    members = [
        {"path": relative, "bytes": (ROOT / relative).stat().st_size, "sha256": sha256(ROOT / relative)}
        for relative in files
    ]
    manifest = {
        "schema_version": 1,
        "project": "gemma4_rtxpro6000_fp8_endpoint",
        "kind": "immutable_preclaim_execution_packet",
        "checkpoint_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "checkpoint_manifest_sha256": "864f24f4631315cd17cc8a3ff1ea57b2725d2a24f29c45778b101f16b5228a4f",
        "checkpoint_expected_bytes": 62546338248,
        "tokenizer_sha256": "cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f",
        "request_identity_sha256": "7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d",
        "payloads_sha256": "60630a80335d5a95ebae87dd2d852c6cb8749a0b92e8617261ec6750b64a794c",
        "jsonl_workload_sha256": sha256(ROOT / "inputs/c32_requests.jsonl"),
        "concurrency": 32,
        "prompt_tokens": 4214,
        "output_tokens": 358,
        "maximum_canonical_samples": 1,
        "accelerator": {"id": "nvidia-rtx-pro-6000-blackwell-server", "architecture": "sm_120", "gpu_count": 1, "provider": "runpod"},
        "runtime": {"representation": "supported dynamic FP8", "endpoint_scheduler": "research/factory/tools/lab-endpoint-pair", "scheduler_arm": "control", "scheduler_concurrency": 32},
        "lifecycle": {"provider_creation": "director_only", "claim_before_staging": True, "repair": "retain_claim_with_repair_handshake", "release": "only_terminal_or_unsafe_deadline"},
        "files": members,
    }
    manifest_path = packet_path
    archive = ROOT / "artifacts" / "rtxpro6000-fp8-preclaim" / "RTXPRO6000_FP8_EXECUTION_PACKET.tar"
    if packet_sha != "f7c932bb6684ceaed67092123a2737ba14234c89dcf23aa878683fac080fc1b1":
        raise RuntimeError("authoritative_execution_packet_changed")
    runtime_path = ROOT / "RTXPRO6000_WORKSTATION_SSH_PORT_PRECLAIM_RUNTIME_MANIFEST.json"
    runtime = {
        "schema_version": 1, "project": "gemma4_rtxpro6000_fp8_endpoint",
        "packet_sha256": packet_sha, "owner_sha256": sha256(ROOT / "run_rtxpro6000_fp8_endpoint_owner.py"),
        "accelerator": "nvidia-rtx-pro-6000-blackwell-workstation", "sm": "sm_120", "ssh_port": 40070,
        "checkpoint_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4", "checkpoint_manifest_sha256": "864f24f4631315cd17cc8a3ff1ea57b2725d2a24f29c45778b101f16b5228a4f",
        "tokenizer_sha256": "cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f", "request_identity_sha256": "7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d",
        "payloads_sha256": "60630a80335d5a95ebae87dd2d852c6cb8749a0b92e8617261ec6750b64a794c", "concurrency": 32, "maximum_canonical_samples": 1,
    }
    atomic(runtime_path, runtime)
    if args.execution_update:
        print(json.dumps({"packet_sha256": packet_sha, "runtime_manifest_sha256": sha256(runtime_path), "owner_sha256": runtime["owner_sha256"]}, sort_keys=True))
        return 0
    terminal = {
        "schema_version": 1,
        "classification": "offline_preparation_terminal",
        "science_consumed": False,
        "candidate_cuda_invocation_started": False,
        "provider_create_or_claim_attempted": False,
        "actual_spend_usd": 0.0,
        "packet": {"path": str(manifest_path), "sha256": packet_sha, "archive": str(archive), "archive_sha256": sha256(archive)},
        "runtime_manifest": {"path": str(runtime_path), "sha256": sha256(runtime_path)},
        "owner": {"path": str(ROOT / "run_rtxpro6000_fp8_endpoint_owner.py"), "sha256": sha256(ROOT / "run_rtxpro6000_fp8_endpoint_owner.py")},
        "detached_owner_command_template": f"{FACTORY / 'detached-owner'} start --state {ROOT}/artifacts/rtxpro6000-fp8-endpoint-<claim>/OWNER_STATE.json --log {ROOT}/artifacts/rtxpro6000-fp8-endpoint-<claim>/OWNER.log --cwd {ROOT} --unit-manager pid -- python3 {ROOT}/run_rtxpro6000_fp8_endpoint_owner.py --execution-packet {manifest_path} --runtime-manifest {runtime_path} --execution-binding <fresh-director-workstation-execution-binding.json> --artifact-root {ROOT}/artifacts/rtxpro6000-fp8-endpoint-<claim>",
        "next_director_action": "Issue a fresh claim-authorizing Workstation lifecycle binding, then launch the exact command above.",
    }
    atomic(ROOT / "PRECLAIM_RTXPRO6000_WORKSTATION_SSH_PORT_REPAIR_TERMINAL.json", terminal)
    status = json.loads((ROOT / "STATUS.json").read_text())
    status.update({
        "actual_spend_usd": 0.0,
        "active_session": None,
        "offline_preparation": {"terminal": "PRECLAIM_RTXPRO6000_WORKSTATION_SSH_PORT_REPAIR_TERMINAL.json", "packet": "RTXPRO6000_FP8_EXECUTION_PACKET.json", "packet_sha256": packet_sha, "runtime_manifest": runtime_path.name, "runtime_manifest_sha256": terminal["runtime_manifest"]["sha256"], "owner_sha256": terminal["owner"]["sha256"], "claim_allowed": False},
        "next_action": "Director: issue a fresh claim-authorizing Workstation lifecycle binding and launch the hash-bound detached-owner command in PRECLAIM_RTXPRO6000_WORKSTATION_SSH_PORT_REPAIR_TERMINAL.json.",
        "summary": "Workstation SSH-port preclaim repair complete: packet f7c932bb remains immutable, while a separate runtime manifest binds the corrected owner and SSH port 40070. No claim, SSH, staging, model load, or request occurred; actual provider exposure remains $0.00.",
    })
    atomic(ROOT / "STATUS.json", status)
    ready = {
        "schema_version": 1,
        "classification": "preclaim_ready_fresh_execution_binding_required",
        "claim_allowed": False,
        "science_consumed": False,
        "provider_operation_attempted": False,
        "repair_binding": "DIRECTOR_RTXPRO6000_WORKSTATION_SSH_PORT_PRECLAIM_REPAIR_20260729T0328Z.json",
        "repair_binding_sha256": "2890137a098f21dd6685d5787ddadb23d11d5689ecbe29afbfed027eb3b6f7f2",
        "packet_sha256": packet_sha,
        "runtime_manifest_sha256": sha256(runtime_path),
        "owner_sha256": sha256(ROOT / "run_rtxpro6000_fp8_endpoint_owner.py"),
        "terminal_sha256": sha256(ROOT / "PRECLAIM_RTXPRO6000_WORKSTATION_SSH_PORT_REPAIR_TERMINAL.json"),
        "status_sha256": sha256(ROOT / "STATUS.json"),
        "detached_owner_command": terminal["detached_owner_command_template"],
    }
    atomic(ROOT / "RTXPRO6000_WORKSTATION_SSH_PORT_PRECLAIM_READY.json", ready)
    print(json.dumps({"packet_sha256": terminal["packet"]["sha256"], "runtime_manifest_sha256": terminal["runtime_manifest"]["sha256"], "owner_sha256": terminal["owner"]["sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
