#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path


EXPECTED = {
    "DIRECTOR_HOPPER_PACKED_STREAMING_LAUNCH_FAILURE_LOCALIZATION_20260726T2157Z.json": "06e019027131fc901e3649768ef45649e659f22846ecd3fc0902e6f76d8b5449",
    "STREAMING_H100_COMPONENT_INPUT_MANIFEST.json": "618ce17579ca30632c11926e4f5738bffc90c4de30d316df800ff6decf2c320a",
    ".repair-handshakes/streaming-h100-1785101786874608286/cluster_dim_compat.h": "fb97d465b883b589e2110c1ad46b2b8d23792d46cecd04fd13dd0f8f2bdc3ca1",
    "artifacts/h100-streaming-component/build/build.ninja": "7c4f5a47b08bbc96bcab142eb0d1eee2625e6ccf1cc08bc17f656497ab7d22b0",
    "artifacts/h100-streaming-component/build/packed_m384_streaming_2262a4a20e94.so": "9eff840f5ef0ac277b08ba9f7e599b95aa6f058a0315a1ab8cef0088389133f0",
    "artifacts/h100-streaming-component/build/packed_m384_streaming_cluster.cuda.o": "e1c89012cbe506ad12b25944fedd7bfa945ee8477b509e3c54c11a7847de594f",
    "artifacts/h100-streaming-component/cuobjdump-resource-usage.txt": "60e618d2125e9402010862053b218302a6f57332c68ec88677b695a95cf75d5a",
    "artifacts/h100-streaming-component/INVOCATION_STATE.json": "6e130027858719e15f96b88c7f39cff2a42b0428972f18b481d092be894714bf",
    "artifacts/h100-streaming-component/RUNTIME_INCOMPATIBILITY.json": "e7dc8374e8e10ff113e02d244bca66d2c7ebe001dfdb8e606e8674f236e6bed5",
    "artifacts/h100-streaming-component/stdout.log": "ab9d857927e8aee78e4aedf7408cbbb62cffc68fd5f548723cd6b61aa1d94117",
    "artifacts/h100-streaming-component/stderr.log": "7a9837fae99c705420c782ea35fc3efb3125e3de3a5b9dc1c6e97c9673a51bff",
    "packed_m384_streaming_cluster.cu": "2262a4a20e9438671f795eeb8aad7f5db9cbe65ae446a94758e3d4c1cce78656",
    "streaming_accuracy_component_runner.py": "c79612b4bd03fa14bcff5aa14cf1e59582aaa9531f1d388ca6e0d2f1edb58cb0",
    "accuracy_redesign_component_runner.py": "95e904aa1d196ec230d4be62c2e9a7bae83931f399592cd21a9adb978b7ef637",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def geometry(
    *,
    head_dim: int,
    kv_heads: int,
    prefix: int,
    cluster_size: int,
) -> dict[str, object]:
    batch = 32
    rows = 12
    heads = 32
    tile_n = 64
    value_slice = 256
    threads = 256
    total_pages = batch * 4214
    dynamic_shared = (
        tile_n * head_dim
        + tile_n * value_slice
        + rows * head_dim * 2
        + (rows * tile_n + 3 * rows) * 4
    )
    cache_elements = total_pages * kv_heads * head_dim
    return {
        "batch": batch,
        "query_rows": batch * rows,
        "query_heads": heads,
        "kv_heads": kv_heads,
        "head_dim": head_dim,
        "prefix_tokens_per_sequence": prefix,
        "cluster_size": cluster_size,
        "grid_ctas": batch * heads * cluster_size,
        "grid_is_cluster_divisible": (
            batch * heads * cluster_size
        )
        % cluster_size
        == 0,
        "threads_per_cta": threads,
        "prefix_tiles": (prefix + tile_n - 1) // tile_n,
        "dynamic_shared_bytes_per_cta": dynamic_shared,
        "compiled_static_shared_bytes_per_cta": 1024,
        "total_shared_bytes_per_cta": dynamic_shared + 1024,
        "compiled_registers_per_thread": 96,
        "compiled_stack_bytes_per_thread": 0,
        "pointer_bounds": {
            "q_and_output_max_element": batch
            * rows
            * heads
            * head_dim
            - 1,
            "q_and_output_numel": batch * rows * heads * head_dim,
            "extend_kv_max_element": batch
            * rows
            * kv_heads
            * head_dim
            - 1,
            "extend_kv_numel": batch * rows * kv_heads * head_dim,
            "paged_cache_max_element": cache_elements - 1,
            "paged_cache_numel": cache_elements,
            "kv_indices_max_element": batch * prefix - 1,
            "kv_indices_numel": batch * prefix,
            "custom_mask_max_element": batch
            * rows
            * (4214 + rows)
            - 1,
            "custom_mask_numel": batch * rows * (4214 + rows),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    observed: dict[str, str] = {}
    for relative, expected in EXPECTED.items():
        path = root / relative
        actual = digest(path)
        if actual != expected:
            raise RuntimeError(
                f"localization_input_digest_mismatch:{relative}:{actual}"
            )
        observed[relative] = actual

    invocation = json.loads(
        (args.artifact_root / "INVOCATION_STATE.json").read_text()
    )
    incompatibility = json.loads(
        (args.artifact_root / "RUNTIME_INCOMPATIBILITY.json").read_text()
    )
    terminal = {
        "schema_version": 1,
        "type": "packed_m384_streaming_launch_localization_terminal",
        "recorded_at_utc": dt.datetime.now(dt.UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "classification": "preserved_evidence_insufficient_for_unique_source_level_fault_localization",
        "scientific_result": False,
        "performance_interpretation_permitted": False,
        "component_replay_permitted": False,
        "v2_replay_performed": False,
        "endpoint_action_performed": False,
        "cuda_invocation_performed_by_localization": False,
        "preserved_attempt": {
            "classification": incompatibility["classification"],
            "candidate_cuda_invocation_started": invocation[
                "candidate_cuda_invocation_started"
            ],
            "runner_first_evaluation_geometry": "local_d256",
            "synchronization_boundary": (
                "two stock calls and one candidate call share the first "
                "torch.cuda.synchronize boundary"
            ),
        },
        "source_invariant_results": {
            "local_d256": geometry(
                head_dim=256,
                kv_heads=16,
                prefix=1024,
                cluster_size=1,
            ),
            "global_d512_unreached": geometry(
                head_dim=512,
                kv_heads=4,
                prefix=4214,
                cluster_size=2,
            ),
            "frozen_bounds": "all derived maxima equal numel_minus_one and are in bounds",
            "launch_capacity": (
                "compiled SM90a metadata shows 96 registers/thread, "
                "0 stack bytes, and 1024 static shared bytes; generated "
                "dynamic shared memory is 42128 bytes for the first local arm"
            ),
            "cluster_contract": (
                "generated local grid 1024 is divisible by cluster size 1; "
                "the unreached global grid 2048 is divisible by cluster size 2"
            ),
        },
        "first_invalid_invariant": None,
        "localization_limit": {
            "reason": (
                "the only CUDA error is asynchronous and reported at the "
                "shared post-control/post-candidate synchronization boundary"
            ),
            "missing_decisive_evidence": [
                "per-arm completion markers or synchronizations",
                "device fault program counter or failing source line",
                "a typed CUDA fault class more specific than unspecified launch failure",
            ],
            "inference": (
                "the local candidate remains suspect because it is the first "
                "new kernel in evaluation order, but the immutable evidence "
                "does not prove that it, rather than either preceding stock "
                "call, produced the asynchronous fault"
            ),
        },
        "later_retry_gate": (
            "requires a later director binding; the minimal discriminator is "
            "arm-isolated completion evidence before any corrected candidate retry"
        ),
        "evidence_sha256": observed,
    }
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    atomic(
        args.artifact_root
        / "PACKED_M384_STREAMING_LAUNCH_LOCALIZATION_TERMINAL.json",
        terminal,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
