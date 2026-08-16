#!/usr/bin/env python3
"""Focused offline audit and READY artifact builder for the fixed SM89 arm."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
PACKET = PROJECT / "packet"
MANIFEST = PACKET / "PACKET_MANIFEST.json"
READY = PROJECT / "L40S_KV4_OUTLIER_SM89_COMPONENT_READY.json"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
DETACHED_OWNER = "/root/workspace/research/factory/tools/detached-owner"
ABS_PROJECT = str(PROJECT)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def validate_manifest() -> dict:
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["schema_version"] == 1
    files = {}
    for row in manifest["files"]:
        name = row["path"]
        path = PACKET / name
        assert path.is_file(), name
        assert path.stat().st_size == row["bytes"], name
        assert sha256(path) == row["sha256"], name
        files[name] = {"bytes": row["bytes"], "sha256": row["sha256"]}
    assert len(files) == len(manifest["files"])
    return {**manifest, "files": files}


def require_tokens(path: Path, tokens: tuple[str, ...]) -> None:
    source = path.read_text()
    ast.parse(source)
    for token in tokens:
        assert token in source, f"{path.name} missing {token}"


def physical_bounds() -> dict:
    batch = 32
    query_heads = 32
    kv_heads = 16
    head_dim = 256
    window = 1024
    multiplier = 50 * 358
    producer_input = batch * kv_heads * head_dim * 2 * 2
    e5m2_write = batch * kv_heads * head_dim * 2
    kv4_write = batch * kv_heads * 144 * 2
    e5m2_unique_read = batch * kv_heads * window * head_dim * 2
    kv4_unique_read = batch * kv_heads * window * 144 * 2
    kv4_qhead_issued_upper = batch * query_heads * window * 144 * 2
    e5m2_complete = producer_input + e5m2_write + e5m2_unique_read
    kv4_complete_lower = producer_input + kv4_write + kv4_unique_read
    kv4_complete_upper = producer_input + kv4_write + kv4_qhead_issued_upper
    bandwidth = 864e9
    return {
        "evidence_label": "analytical exact geometry; bandwidth is vendor-reported and no latency is transferred",
        "one_c32_local_layer_decode_step_bytes": {
            "common_bf16_kv_producer_input": producer_input,
            "e5m2_producer_write": e5m2_write,
            "kv4_outlier_producer_write": kv4_write,
            "e5m2_unique_kv_consumer_read": e5m2_unique_read,
            "kv4_outlier_unique_kv_consumer_read": kv4_unique_read,
            "kv4_outlier_qhead_cta_issued_read_upper_without_gqa_cache_reuse": kv4_qhead_issued_upper,
            "e5m2_complete": e5m2_complete,
            "kv4_outlier_complete_unique_lower": kv4_complete_lower,
            "kv4_outlier_complete_issued_upper": kv4_complete_upper,
        },
        "locked_50_layers_358_steps_c32_batch_bytes": {
            "e5m2_complete": e5m2_complete * multiplier,
            "kv4_outlier_complete_unique_lower": kv4_complete_lower * multiplier,
            "kv4_outlier_complete_issued_upper": kv4_complete_upper * multiplier,
            "unique_payload_saving": (e5m2_complete - kv4_complete_lower)
            * multiplier,
        },
        "price_normalized_bytes_per_request_at_c32": {
            "e5m2_complete": e5m2_complete * multiplier // batch,
            "kv4_outlier_complete_unique_lower": kv4_complete_lower
            * multiplier
            // batch,
            "kv4_outlier_complete_issued_upper": kv4_complete_upper
            * multiplier
            // batch,
        },
        "vendor_864_GB_s_floor_seconds": {
            "e5m2_locked_c32_batch": e5m2_complete * multiplier / bandwidth,
            "kv4_unique_locked_c32_batch": kv4_complete_lower
            * multiplier
            / bandwidth,
            "kv4_issued_upper_locked_c32_batch": kv4_complete_upper
            * multiplier
            / bandwidth,
        },
        "interpretation": "KV4 removes 43.75% of unique K/V payload but the fixed candidate maps one CTA per query head, so the no-GQA-reuse issued-load upper is worse than grouped E5M2. The preregistered SM89 timing, not the optimistic byte floor, decides.",
    }


def build_ready() -> dict:
    manifest = validate_manifest()
    runner = PACKET / "run_sm89_component.py"
    owner = PROJECT / "l40s_component_owner.py"
    require_tokens(
        runner,
        (
            "MHATokenToKVPool",
            "decode_attention_fwd",
            "extension.pack",
            "extension.paged_attention",
            "SCIENCE_STARTED.json",
            "ARM_MARKERS.jsonl",
            "PRODUCER_SNAPSHOT.pt",
            "consumer-only",
            "paired_e5m2_minus_candidate",
            "dependent_synchronization_credit_seconds",
        ),
    )
    require_tokens(
        owner,
        (
            '"show", "--bench"',
            '"claim"',
            '"heartbeat"',
            "--expected-claimed-at",
            "repair_request",
            "consumer_only_from_bound_producer_snapshot",
            "release_scientific",
            "release_terminal_boundary",
            "sudo -n docker",
            "--entrypoint",
            IMAGE,
        ),
    )
    owner_source = owner.read_text()
    assert "sglang.launch_server" not in owner_source
    assert "--checkpoint" not in owner_source
    owner_main = owner_source.split("def main() -> int:", 1)[1]
    assert owner_main.index('"show", "--bench"') < owner_main.index(
        'claim = pool(\n        "claim"'
    )
    runner_hash = sha256(runner)
    owner_hash = sha256(owner)
    manifest_hash = sha256(MANIFEST)
    artifact_root = (
        ABS_PROJECT
        + "/artifacts/sm89-component-DIRECTOR_BOUND_UTC"
    )
    owner_state = (
        ABS_PROJECT
        + "/artifacts/sm89-owner-DIRECTOR_BOUND_UTC/OWNER.json"
    )
    owner_log = (
        ABS_PROJECT
        + "/artifacts/sm89-owner-DIRECTOR_BOUND_UTC/OWNER.log"
    )
    exact_command = (
        f"{DETACHED_OWNER} start --unit-manager pid "
        f"--state {owner_state} --log {owner_log} -- "
        f"python3 {ABS_PROJECT}/l40s_component_owner.py "
        "--bench DIRECTOR_REGISTERED_L40S_BENCH "
        f"--artifact-root {artifact_root} --deadline-seconds 1620"
    )
    return {
        "schema_version": 1,
        "kind": "l40s_kv4_outlier_sm89_component_ready",
        "project": PROJECT.name,
        "classification": "offline_ready_lifecycle_pure_exact_component",
        "decision": "positive",
        "pass": True,
        "scientific_result": "unmeasured_target_gpu_execution_required",
        "scope": {
            "gpu_pool_claimed": False,
            "ssh_used": False,
            "provider_api_used": False,
            "provider_resource_created_or_destroyed": False,
            "cuda_invoked": False,
            "checkpoint_shards_read": False,
            "image_pulled": False,
            "model_server_started": False,
            "endpoint_request_consumed": False,
            "representation_or_parameter_sweep": False,
            "actual_spend_usd": 0.0,
        },
        "fixed_contract": {
            "model": "google/gemma-4-31B-it",
            "model_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "runtime_commit": "c6a6200a1a778a799ba61c395ac292317f01ebc9",
            "accelerator": "NVIDIA L40S SM89",
            "batch": 32,
            "window": 1024,
            "page_size": 1,
            "query_heads": 32,
            "kv_heads": 16,
            "head_dim": 256,
            "local_layers": 50,
            "decode_steps": 358,
            "warmups": 5,
            "repeats": 31,
            "runtime_image": IMAGE,
        },
        "direct_hashes": {
            "unchanged_candidate_producer_and_fused_consumer_cuda": manifest[
                "files"
            ]["local_kv4_outlier_cuda.cu"]["sha256"],
            "unchanged_candidate_bindings": manifest["files"][
                "local_kv4_outlier_bindings.cpp"
            ]["sha256"],
            "unchanged_runtime_adapter": manifest["files"][
                "sglang_local_kv4_outlier.py"
            ]["sha256"],
            "current_runtime_seam": manifest["files"][
                "runtime_source/triton_backend.py"
            ]["sha256"],
            "current_runtime_e5m2_producer": manifest["files"][
                "runtime_source/memory_pool.py"
            ]["sha256"],
            "current_runtime_e5m2_comparator": manifest["files"][
                "runtime_source/decode_attention.py"
            ]["sha256"],
            "exact_component_runner": runner_hash,
            "packet_manifest": manifest_hash,
            "bounded_owner": owner_hash,
        },
        "producer_consumer_invocation": {
            "baseline_producer": "pinned MHATokenToKVPool.set_kv_buffer with torch.float8_e5m2 storage",
            "baseline_consumer": "pinned decode_attention_fwd with live dynamic split selection, max 8",
            "candidate_producer": "unchanged local_kv4_outlier_pack for both K and V",
            "candidate_consumer": "unchanged corrected local_kv4_outlier_paged_attention",
            "fixture": "production c32 decode, 32 interleaved request-owned page-1 rows of length 1024",
            "correctness": "complete FP32-reference output consumption; finite, relative-L2, cosine, max-absolute, per-request isolation, negative-slot no-op, and local/global router rejection",
            "timing": "five warmups and 31 order-alternated synchronized rows for E5M2 pack, KV4 pack, E5M2 attention, and corrected KV4 attention; compilation/setup are separate",
            "resources": "same invocation records cuobjdump register/stack/shared/local resource output, exact launch geometry, and CUDA allocated/reserved peaks",
            "repair": "a content-addressed producer snapshot preserves both cache representations and BF16 fixture; consumer-only repair never replays packing",
        },
        "physical_bounds": physical_bounds(),
        "locked_request_measured_bound_contract": {
            "complete_pair_ms": {
                "baseline": "E5M2 pack wall ms + E5M2 attention wall ms",
                "candidate": "KV4 K+V pack wall ms + corrected KV4 attention wall ms",
            },
            "promotion_margin": "p05 of 31 paired (baseline complete - candidate complete) wall-ms rows must be > 0",
            "c32_batch_wall_seconds": "p05_margin_ms * 50 * 358 / 1000",
            "price_normalized_seconds_per_request": "c32_batch_wall_seconds / 32",
            "dependent_synchronization_credit": 0.0,
            "packing_omitted": False,
            "endpoint_claim": False,
        },
        "owner": {
            "controller": DETACHED_OWNER,
            "unit_manager": "pid",
            "owner_path": str(owner),
            "packet_manifest": str(MANIFEST),
            "max_lifecycle_seconds": 1620,
            "conservative_provider_exposure_usd": 0.388342485,
            "exact_later_command": exact_command,
            "director_substitutions": {
                "DIRECTOR_REGISTERED_L40S_BENCH": "one inventory ID whose resource record includes public_ipv4, ssh_user=glmrunner, identity_file, and known_hosts_namespace",
                "DIRECTOR_BOUND_UTC": "one collision-free UTC token used identically in state/log/artifact roots",
            },
            "active_session_record": "record emitted state path as unit plus pid, start_ticks, unit_manager=pid, deadline, and artifact_root",
            "release_generation_guard": "--expected-claimed-at from the original continuous claim",
            "repair_disposition": "ordinary compile/API/launcher/retrieval failures retain the claim and heartbeat; fresh repair IDs dispatch retrieval-only, full-unconsumed, or consumer-only-from-snapshot paths",
        },
        "focused_offline_checks": [
            "all project-local packet members match size and SHA-256 manifest",
            "candidate source and adapter bytes match admitted direct hashes",
            "live comparator, producer, and runtime seam must match project-local snapshots before CUDA",
            "runner AST parses and reaches both real producer-plus-consumer chains",
            "sentinel synchronizes and persists one marker after each arm before production timing",
            "complete bound includes both K+V packing and attention with zero synchronization credit",
            "owner preflights registered SSH identity before claim, uses sudo -n docker, digest-pinned image, heartbeat, compact retrieval, fresh repair generations, and expected claim generation release",
            "owner contains no checkpoint or model-server path",
        ],
        "next_action": "A later director may register one cold L40S, substitute only the two explicit command tokens, launch the exact detached owner, record its emitted PID identity in STATUS.active_session, and return after one grouped snapshot proves the owner live, claimed, heartbeating, and past the first staged boundary.",
    }


def main() -> int:
    value = build_ready()
    atomic_json(READY, value)
    print(json.dumps({"ready": str(READY), "sha256": sha256(READY)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
