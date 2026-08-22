#!/usr/bin/env python3
"""Atomically derive the R7 owner proof and its claim-specific binding."""
from __future__ import annotations

import argparse
import json
import pathlib
import tempfile
import os
import hashlib


PROJECT = pathlib.Path(__file__).resolve().parent
DIRECTOR = PROJECT / "DIRECTOR_DFLASH_R7_NGRAM_FLASHINFER_WARM_EXECUTION_20260730T0325Z.json"
OWNER = PROJECT / "dflash_component_direct_recovery_owner_r7.py"
PACKET = PROJECT / "artifacts/dflash-h200-r6-ngram-flashinfer-repair/dflash-component-ngram-flashinfer-repair-packet.tar"
ROOT = PROJECT / "artifacts/dflash-h200-r7-ngram-flashinfer"


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True); handle.write("\n")
        tmp = pathlib.Path(handle.name)
    json.loads(tmp.read_text()); os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claim-json", type=pathlib.Path)
    args = parser.parse_args()
    director = json.loads(DIRECTOR.read_text())
    proof = {
        "schema_version": 1, "director": DIRECTOR.name, "director_sha256": digest(DIRECTOR),
        "owner_source": OWNER.name, "owner_source_sha256": digest(OWNER),
        "packet_archive": str(PACKET.relative_to(PROJECT)), "packet_archive_sha256": digest(PACKET),
        "worker_generation": 7, "retry_scope": "classify", "arm": "ngram_only",
    }
    atomic(ROOT / "R7_OWNER_OFFLINE_BOUND.json", proof)
    if args.claim_json is None:
        return
    claim = json.loads(args.claim_json.read_text())
    if claim.get("claim", {}).get("project") != director["project"]:
        raise SystemExit("claim project mismatch")
    if claim.get("id") != director["bench"]["id"] or claim.get("resource", {}).get("gpu_uuid") != director["bench"]["gpu_uuid"]:
        raise SystemExit("claim identity mismatch")
    binding = {
        "schema_version": 1, "project": director["project"], "bench_id": claim["id"],
        "claimed_at": claim["claim"]["claimed_at"], "gpu_uuid": claim["resource"]["gpu_uuid"],
        "director_sha256": proof["director_sha256"], "owner_source": OWNER.name,
        "owner_source_sha256": proof["owner_source_sha256"], "initial_worker_generation": 7,
        "generation": "dflash-h200-r7-ngram-flashinfer-20260730t0325z",
        "retry_scope": "classify", "packet_archive": proof["packet_archive"],
        "packet_archive_sha256": proof["packet_archive_sha256"],
        "remote_run": director["immutable_inputs"]["remote_run"],
        "remote_target_path": director["immutable_inputs"]["remote_target_path"],
        "target_manifest_sha256": director["immutable_inputs"]["target_manifest_sha256"],
        "repair_namespace": director["owner_contract"]["repair_namespace"],
        "attribution_start_utc": claim["lifecycle"]["provider_started_at_utc"],
        "prior_actual_spend_usd": director["spend"]["actual_through_r6_release_usd"],
        "owner_deadline_utc": director["lifecycle"]["owner_release_by_utc"],
    }
    atomic(ROOT / "EXECUTION_BINDING_R7.json", binding)


if __name__ == "__main__":
    main()
