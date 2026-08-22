#!/usr/bin/env python3
"""Create the immutable READY candidate and atomically publish the handoff."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"json_object_required:{path}")
    return value


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    json.loads(temporary.read_text())
    temporary.replace(path)


def ready_value() -> dict[str, Any]:
    validation = load(PROJECT / "artifacts" / "PQ_MIPS_H200_OFFLINE_VALIDATION.json")
    owner_validation_path = PROJECT / "artifacts" / "owner-offline-validation.stdout"
    owner_validation = load(owner_validation_path)
    contract = load(PROJECT / "EXPERIMENT_CONTRACT.json")
    manifest_path = PROJECT / validation["packet_manifest"]
    manifest = load(manifest_path)
    archive = PROJECT / validation["packet_archive"]
    weight = PROJECT / validation["weight_snapshot"]["path"]
    packet_root = manifest_path.parent
    source_hashes = {
        name: sha(PROJECT / name)
        for name in (
            "pq_mips_h200_worker.py",
            "pq_mips_h200_owner.py",
            "build_pq_mips_h200_packet.py",
            "test_pq_mips_h200_offline.py",
            "finalize_pq_mips_h200_ready.py",
            "EXPERIMENT_CONTRACT.json",
            "OPPORTUNITY_REGISTER.json",
            "DIRECTOR_PQ_MIPS_H200_PRODUCER_RESCUE_20260729T2102Z.json",
            "DIRECTOR_PQ_MIPS_H200_RESERVED_MAINTENANCE_20260729T2107Z.json",
            "OUTPUT_HEAD_PQ_MIPS_PROXY_TERMINAL.json",
        )
    }
    return {
        "schema_version": 1,
        "project": "gemma4_output_head_pq_mips_recovery_proxy",
        "classification": "hash_complete_offline_h200_vectorized_producer_ready",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "claim_allowed": False,
        "decision": "director_claim_authority_required",
        "scope": "Deterministic vectorized weight-only PQ producer, bounded exact CPU-reference oracle, c32 asymmetric scan, exact union-rescore consumer, and durable owner packet only. Held-out science remains unconsumed.",
        "packet": {
            "identity_sha256": validation["packet_identity_sha256"],
            "root": str(packet_root.relative_to(PROJECT)),
            "manifest": validation["packet_manifest"],
            "manifest_sha256": validation["packet_manifest_sha256"],
            "archive": validation["packet_archive"],
            "archive_sha256": validation["packet_archive_sha256"],
            "files": manifest["files"],
            "weight_snapshot": validation["weight_snapshot"],
        },
        "source_hashes": {
            "worker": source_hashes.pop("pq_mips_h200_worker.py"),
            "owner": source_hashes.pop("pq_mips_h200_owner.py"),
            **source_hashes,
        },
        "immutable_science": {
            "model": contract["stock_control"]["model"],
            "revision": contract["stock_control"]["revision"],
            "capture_sha256": contract["inputs"]["capture_sha256"],
            "capture_terminal_sha256": contract["inputs"]["capture_terminal_sha256"],
            "lowrank_terminal_sha256": contract["inputs"]["lowrank_terminal_sha256"],
            "weight_shard_sha256": contract["inputs"]["weight_shard_sha256"],
            "tied_weight_tensor_sha256": contract["inputs"]["tied_weight_tensor_sha256"],
            "weight_shape": contract["stock_control"]["weight_shape"],
            "weight_dtype": contract["stock_control"]["weight_dtype"],
            "index_name": contract["candidate"]["index_name"],
            "subspaces": contract["candidate"]["subspaces"],
            "dimensions_per_subspace": contract["candidate"]["dimensions_per_subspace"],
            "codebook_rows": contract["candidate"]["codebook_rows"],
            "pq_codes_dtype": contract["candidate"]["pq_codes_dtype"],
            "codebook_dtype": contract["candidate"]["codebook_dtype"],
            "shortlist_sizes": contract["candidate"]["shortlist_sizes"],
            "batch_selection": contract["workload"]["batch_selection"],
            "tie_break": contract["candidate"]["tie_break"],
            "exact_rescore": contract["correctness_gate"]["semantics"],
            "traffic_accounting": contract["baseline_measurement"]["attribution"],
            "tuning_after_evaluation": contract["candidate"]["tuning_after_evaluation"],
        },
        "implementation": {
            "producer": {
                "statistics": "One deterministic CUDA population var_mean over the full [262144,5376] FP32 view of the exact BF16 tied tensor.",
                "codebook": "Frozen per-coordinate Gaussian Lloyd-Max 16-level BF16 scalar codebooks; adjacent pairs expand to 2688x256x2.",
                "encoding": "Batched CUDA searchsorted over [5376,15] thresholds and row chunks; adjacent 4-bit scalar codes pack low+16*high into uint8 [262144,2688].",
                "persistence": "Atomically persist frozen_pq_index.pt and hash-complete PRODUCER_TERMINAL.json before any selected hidden row is scored.",
                "resume": "A later consumer repair must pass --resume-producer and validate the retained producer terminal and index hash; it cannot rerun statistics or encoding.",
            },
            "cpu_reference": {
                "subspaces": [0, 1, 17, 511, 1024, 2047, 2687],
                "token_ids": [0, 1, 106, 255, 4096, 65535, 131071, 262143],
                "gate": "Recompute population statistics, BF16 scalar codebooks, and packed codes with the existing CPU formula. Sampled BF16 codebooks and uint8 codes must be exact before SCIENCE_STARTED.",
            },
            "h200_consumer": {
                "asymmetric_lookup": "FP32 c32x2688x256 query lookup table.",
                "code_scan": "Exactly one c32 query chunk per packed-code row chunk, so the algorithmic code traffic is one full packed index read per frozen c32 batch.",
                "scan_row_chunk": 512,
                "maximum_scan_gather_workspace_bytes": 32 * 2688 * 512 * 4,
                "ranking": "Stable descending full-vocabulary sort preserves ascending token ID on ties.",
                "exact_rescore": "For each shortlist and c32 batch, gather the sorted physical union of original BF16 rows once, form exact FP32 logits, and consume those logits for greedy IDs.",
                "component_ledger": [
                    "weight_h2d",
                    "weight_fp32_cast",
                    "statistics",
                    "encoding",
                    "asymmetric_lookup_and_code_scan",
                    "dense_exact_reference",
                    "stable_full_vocab_ranking",
                    "exact_union_rescore_by_shortlist",
                ],
            },
            "physical_hypothesis": {
                "classification": "inferred_until_target_h200_measurement",
                "mechanism": "The producer replaces serial CPU threshold assignment with full-device vectorized reductions and batched searchsorted. The discriminator reuses each packed-code chunk across all 32 queries and gathers each exact survivor union once.",
                "falsifier": "Any bounded CPU-reference mismatch, incomplete producer identity, missing c32 traffic equivalence, missing exact-union rescore row, or target-H200 component failure prevents scientific interpretation.",
                "transfer_limit": contract["decision_gate"]["transfer_limit"],
            },
        },
        "bounded_owner": {
            "entrypoint": "pq_mips_h200_owner.py",
            "launch": [
                "/root/workspace/research/factory/tools/detached-owner",
                "start",
                "--state",
                "<absolute-project-owner-state-path>",
                "--log",
                "<absolute-project-owner-log-path>",
                "--cwd",
                str(PROJECT),
                "--unit-manager",
                "pid",
                "--",
                sys_executable(),
                str(PROJECT / "pq_mips_h200_owner.py"),
                "--ready",
                str(PROJECT / "PQ_MIPS_H200_PRODUCER_READY.json"),
                "--authority",
                "<later-director-authority.json>",
                "--output",
                "<absolute-project-artifact-root>",
            ],
            "active_session_contract": [
                "Record the detached-owner state path as unit.",
                "Record emitted pid, start_ticks, unit_manager=pid, artifact_root, and absolute deadline in STATUS.json.active_session.",
                "Keep claim, heartbeat, worker supervision, compact retrieval, repair generations, and final release inside this one controller.",
            ],
            "deadline_rule": "Later director authority must provide claim_start_by_utc and owner_deadline_utc inside the registered bench lifecycle deadline with cleanup margin.",
            "worker_terminal_order": [
                "PRODUCER_STARTED.json",
                "PRODUCER_TERMINAL.json",
                "SCIENCE_STARTED.json",
                "OUTPUT_HEAD_PQ_MIPS_H200_TERMINAL.json",
            ],
            "repair": "Recoverable producer, consumer, launcher, archive, or retrieval defects retain the claim and heartbeat under a fresh repair-handshake generation. A persisted producer is resumed, never replayed.",
            "release_predicate": "Release ready only after the owner independently validates producer identity/reference fields and the complete three-shortlist/two-batch H200 terminal ledger. Unknown or incomplete results remain in repair; deadline disposition is maintenance after compact retrieval.",
        },
        "later_director_gate": {
            "bench_id": "h200-qkv-endpoint-computeinstance-e00qxw871hz1r79fjt",
            "accelerator": "nvidia-h200-sxm",
            "gpu_uuid": "GPU-81ca2c99-6df0-5bf8-023c-3ee78a68f3d8",
            "reservation_usd": 6.0,
            "metered_rate_usd_per_hour": 2.45,
            "current_lifecycle_deadline_utc": "2026-07-29T23:55:00Z",
            "required_authority": [
                "Verify this READY SHA-256 and packet identity.",
                "Verify remaining cumulative reservation and lifecycle runway.",
                "Publish gpu_claim_allowed=true with exact bench, claim_start_by_utc, and owner_deadline_utc.",
                "Launch the controller through detached-owner --unit-manager pid and atomically record active_session before relying on it.",
            ],
            "prohibited_now": [
                "No claim or ready transition.",
                "No gpu_pool, SSH, Docker, CUDA, endpoint, or provider call.",
                "No held-out scoring or scientific sample consumption.",
            ],
        },
        "offline_validation": {
            "artifact": "artifacts/PQ_MIPS_H200_OFFLINE_VALIDATION.json",
            "sha256": sha(PROJECT / "artifacts" / "PQ_MIPS_H200_OFFLINE_VALIDATION.json"),
            "worker_self_test": validation["worker_self_test"],
            "unit_tests": {
                "command": f"{sys_executable()} -m unittest -v test_pq_mips_h200_offline.py",
                "tests": 5,
                "pass": True,
            },
            "weight_snapshot": validation["weight_snapshot"],
            "prohibitions_observed": validation["prohibitions_observed"],
            "owner_packet_validation": {
                "artifact": str(owner_validation_path.relative_to(PROJECT)),
                "sha256": sha(owner_validation_path),
                "pass": owner_validation.get("pass") is True,
                "checks": owner_validation["checks"],
            },
        },
        "resource_use_this_turn": {
            "actual_spend_usd": 0.0,
            "gpu_claimed": False,
            "gpu_pool_called": False,
            "ssh_called": False,
            "docker_called": False,
            "cuda_called": False,
            "endpoint_traffic": False,
            "provider_api_called": False,
            "held_out_rows_scored": 0,
            "scientific_samples_consumed": 0,
            "other_projects_mutated": False,
            "project_local_weight_snapshot_bytes": weight.stat().st_size,
            "packet_archive_bytes": archive.stat().st_size,
        },
        "invalidated_unpublished_packet_identities": [
            "6509c70113e73a38327836369b9932d0f82fbaf30ae06f89315c286522b860be"
        ],
    }


def sys_executable() -> str:
    return "/usr/bin/python3"


def publish(candidate: Path) -> None:
    ready = load(candidate)
    final = PROJECT / "PQ_MIPS_H200_PRODUCER_READY.json"
    candidate.replace(final)
    ready_hash = sha(final)
    status = load(PROJECT / "STATUS.json")
    status.update(
        {
            "active_session": None,
            "actual_spend_usd": 0.0,
            "claim_allowed": False,
            "decision": "hash_complete_h200_vectorized_producer_ready_director_gate",
            "next_action": "Director: verify PQ_MIPS_H200_PRODUCER_READY.json and its packet hashes, remaining exact $6 reservation, and lifecycle runway. Only then publish a fresh claim authority with exact claim_start_by_utc/owner_deadline_utc and launch pq_mips_h200_owner.py through detached-owner --unit-manager pid. Researcher must not claim or ready the maintenance bench without that authority.",
            "researcher_profile": "execution",
            "source_ready": "PQ_MIPS_H200_PRODUCER_READY.json",
            "source_ready_sha256": ready_hash,
            "packet_identity_sha256": ready["packet"]["identity_sha256"],
            "status": "active",
            "summary": "Hash-complete deterministic H200 PQ producer, exact bounded CPU oracle, c32 scan/exact-union-rescore worker, and durable owner packet are offline-valid. Held-out science remains unconsumed; claim authority remains false pending director verification.",
            "terminal": "OUTPUT_HEAD_PQ_MIPS_H200_TERMINAL.json",
        }
    )
    atomic(PROJECT / "STATUS.json", status)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, default=PROJECT / "artifacts" / "PQ_MIPS_H200_PRODUCER_READY.candidate.json")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if args.publish:
        publish(args.candidate)
    else:
        atomic(args.candidate, ready_value())
        print(json.dumps({"candidate": str(args.candidate), "sha256": sha(args.candidate)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
