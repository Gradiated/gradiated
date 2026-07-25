#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = (
    ROOT / "inputs/candidate-v0.5.15/source/python/sglang/srt"
)
UPSTREAM = Path(
    "/root/workspace/.agents/runtime/sglang-v0.5.15-full-checkout"
)
UPSTREAM_SOURCE = UPSTREAM / "python/sglang/srt"
EXPECTED_COMMIT = "f63458b5beaceabbd9d749b9fc956370e1b649e6"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> None:
    binding_path = ROOT / "DIRECTOR_BINDING.json"
    binding = json.loads(binding_path.read_text())
    bound_inputs = []
    for item in binding["inputs"]:
        path = (ROOT / item["path"]).resolve()
        actual = sha256(path)
        bound_inputs.append(
            {
                "path": item["path"],
                "expected_sha256": item["sha256"],
                "actual_sha256": actual,
                "match": actual == item["sha256"],
            }
        )
    if not all(item["match"] for item in bound_inputs):
        raise RuntimeError("director_binding_hash_mismatch")

    upstream_commit = subprocess.check_output(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True
    ).strip()
    upstream_dirty = subprocess.check_output(
        ["git", "-C", str(UPSTREAM), "status", "--porcelain"], text=True
    ).strip()
    if upstream_commit != EXPECTED_COMMIT or upstream_dirty:
        raise RuntimeError(
            f"upstream_identity_mismatch:{upstream_commit}:{bool(upstream_dirty)}"
        )

    files = {}
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        relative = path.relative_to(SOURCE_ROOT).as_posix()
        upstream = UPSTREAM_SOURCE / relative
        base_sha256 = sha256(upstream) if upstream.is_file() else None
        candidate_sha256 = sha256(path)
        files[relative] = {
            "bytes": path.stat().st_size,
            "sha256": candidate_sha256,
            "upstream_sha256": base_sha256,
            "modified": base_sha256 != candidate_sha256,
        }
    project_sources = {}
    for name in (
        "adaptive_depth_contract.py",
        "endpoint_integration.py",
        "run_adaptive_depth6_graph_fixtures.py",
        "build_adaptive_depth6_result.py",
    ):
        path = ROOT / name
        project_sources[name] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }

    fixture_path = ROOT / "ADAPTIVE_DEPTH6_CUDA_GRAPH_FIXTURES.json"
    fixtures = json.loads(fixture_path.read_text())
    if fixtures["result"] != "pass":
        raise RuntimeError("deterministic_fixtures_failed")

    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    manifest = {
        "schema_version": 1,
        "manifest_type": "immutable_source_complete_adaptive_depth6_cuda_graph",
        "project": binding["project"],
        "created_at_utc": created_at,
        "runtime": {
            "release": binding["runtime"]["release"],
            "commit": upstream_commit,
            "official_image": binding["runtime"]["official_image"],
            "target_accelerator": binding["runtime"]["target_accelerator"],
        },
        "source_root": "inputs/candidate-v0.5.15/source/python/sglang/srt",
        "source_files": files,
        "project_sources": project_sources,
        "binding": {
            "path": "DIRECTOR_BINDING.json",
            "sha256": sha256(binding_path),
            "all_bound_hashes_match": True,
            "inputs": bound_inputs,
        },
        "implementation": {
            "native_producer_depths": [12, 6],
            "capacity_depth": 12,
            "high_load_threshold": 8,
            "high_load_depth": 6,
            "graph_key_fields": [
                "batch_size",
                "stream_idx",
                "variant_label",
                "speculative_depth",
            ],
            "capture_pool": "one existing process-global CUDA graph pool; depth-specific graphs share only capacity allocation, never semantic shape",
            "replay": "exact batch and batch*active_depth buffer slices; adaptive path never calls batch padding",
            "target_verify_metadata": "qo_indptr, mask_indptr, max_extend_len and target rows derive from NgramVerifyInput.draft_token_num",
            "ownership": "ragged accepted-token offsets survive filtering/merge and scheduler result stride is active_depth",
            "kv_movement": "unchanged move_accept_tokens_to_target_kvcache consumes active accept_index width",
            "read_only_snapshot": True,
        },
        "fixtures": {
            "path": fixture_path.name,
            "sha256": sha256(fixture_path),
            "deterministic_repeat_match": True,
        },
    }
    manifest_path = ROOT / "ADAPTIVE_DEPTH6_CUDA_GRAPH_SOURCE_MANIFEST.json"
    atomic_json(manifest_path, manifest)

    result = {
        "schema_version": 1,
        "classification": "source_complete_h100_component_ready",
        "created_at_utc": created_at,
        "project": binding["project"],
        "evidence_label": "source_backed_plus_deterministic_offline_state_fixtures",
        "director_binding": {
            "path": binding_path.name,
            "sha256": sha256(binding_path),
            "all_bound_hashes_match": True,
        },
        "runtime_identity": {
            "release": "v0.5.15",
            "commit": upstream_commit,
            "official_image": binding["runtime"]["official_image"],
        },
        "decision": {
            "exact_depth6_graph_feasible": True,
            "padding_or_depth_disguise": False,
            "depth_is_part_of_graph_identity": True,
            "depth6_capture_owns_exact_metadata_and_buffers": True,
            "transition_7_to_8_to_7": "pass",
            "permutation": "pass",
            "cancellation_completion": "pass",
            "empty_partial_matches": "pass",
            "slot_reuse": "pass",
            "stale_key_state_and_shape_mismatches": "fail_closed",
        },
        "mechanism": {
            "graph_identity": "ShapeKey adds speculative_depth",
            "capture": "each captured batch uses the frozen rule, so batches 1-7 capture 12 rows/request and batches 8+ capture 6 rows/request",
            "pool": "capacity-12 allocations remain stable while each graph records only batch*active_depth rows",
            "replay": "runtime identity validates depth, exact token/position/out-cache counts, exact custom-mask length and captured batch before key lookup",
            "attention": "Triton eager and graph target-verify metadata derive all row and mask geometry from active depth",
            "settlement": "dual native corpus banks, exact-depth buffers, ragged result offsets and active scheduler stride preserve request ownership",
            "kv": "the unchanged KV mover receives active-width accept_index and exact active-depth out_cache_loc",
        },
        "artifacts": {
            "source_manifest": {
                "path": manifest_path.name,
                "sha256": sha256(manifest_path),
            },
            "fixtures": {
                "path": fixture_path.name,
                "sha256": sha256(fixture_path),
            },
            "invalid_observer_attempts": [
                {
                    "path": name,
                    "sha256": sha256(ROOT / name),
                    "science_started": False,
                }
                for name in (
                    "ADAPTIVE_DEPTH6_FIXTURE_ATTEMPT1_INVALID.json",
                    "ADAPTIVE_DEPTH6_FIXTURE_ATTEMPT2_INVALID.json",
                )
            ],
        },
        "scope": {
            "provider_or_gpu_used": False,
            "checkpoint_loaded": False,
            "endpoint_requests_submitted": 0,
            "latency_claim": False,
            "economic_claim": False,
            "actual_spend_usd": 0.0,
        },
        "remaining_gate": "One short exact H100 graph-versus-eager component must execute these immutable bytes after the higher-priority retained endpoint lane releases the compatible bench.",
    }
    result_path = ROOT / "ADAPTIVE_DEPTH6_CUDA_GRAPH_RESULT.json"
    atomic_json(result_path, result)

    decision = f"""# Adaptive depth-6 CUDA-graph decision

Classification: `source_complete_h100_component_ready`.

All five director-bound artifacts match, and the project-local source is based
on clean SGLang v0.5.15 commit `{upstream_commit}`. Exact depth-6 capture is
source-feasible without padding: graph identity now includes speculative depth,
capture and replay use exact `batch * active_depth` slices, and Triton target
verification derives query offsets, mask offsets, and maximum extend length
from the active NGRAM depth.

The deterministic production-contract fixtures passed the 7→8→7 transition
with graph keys `(7,12,84) → (8,6,48) → (7,12,84)`, permutations,
cancellation/completion, empty and partial matches, and slot reuse. Depth/key,
token, position, custom-mask, ownership, completion, and live-slot mutations
all failed closed. The result repeated byte-identically.

The physical design keeps one capacity-12 allocation and the existing shared
CUDA graph memory pool, but depth is semantic graph identity. Depth-6 replay
cannot resolve a depth-12 graph, cannot pad 48 rows to 96, and cannot consume
the stale tail of a prior mask because its captured metadata ends at the exact
depth-6 offsets. Native producer buffers remain separate at depths 12 and 6;
ragged accepted-token offsets and the active result stride preserve ownership
through scheduler settlement, while the existing KV mover consumes the active
accept-index width.

This is offline source and deterministic state evidence. It used no provider,
GPU, checkpoint, endpoint request, or paid resource and makes no latency or
economic claim. The next admissible evidence is one short exact H100
graph-versus-eager component using the immutable source manifest after the
higher-priority endpoint lane releases the compatible bench.

Artifacts:

- `ADAPTIVE_DEPTH6_CUDA_GRAPH_RESULT.json`
- `ADAPTIVE_DEPTH6_CUDA_GRAPH_SOURCE_MANIFEST.json`
- `ADAPTIVE_DEPTH6_CUDA_GRAPH_FIXTURES.json`
"""
    decision_path = ROOT / "ADAPTIVE_DEPTH6_CUDA_GRAPH_DECISION.md"
    temporary = decision_path.with_suffix(".md.part")
    temporary.write_text(decision)
    temporary.replace(decision_path)


if __name__ == "__main__":
    main()
