#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import pathlib
import sqlite3

from install_fused_qkv_cache import patch_source


REQUESTS = 32
PROFILE_SECONDS = 23.038600455
QUALIFIED_SECONDS_PER_REQUEST = 0.625149101968745
CAMPAIGN_TARGET_SECONDS_PER_REQUEST = 0.500119281574996


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def extract_chain(profile: pathlib.Path) -> dict[str, object]:
    connection = sqlite3.connect(f"file:{profile}?mode=ro", uri=True)
    rows = connection.execute(
        """
        SELECT k.start, k.end, s.value, k.gridX, k.gridY, k.blockX,
               k.registersPerThread, k.dynamicSharedMemory
        FROM CUPTI_ACTIVITY_KIND_KERNEL AS k
        JOIN StringIds AS s ON s.id = k.shortName
        ORDER BY k.start
        """
    ).fetchall()
    connection.close()
    stages = {
        "local": {
            "protective_clone": [0, 0],
            "scale_divide": [0, 0],
            "bf16_to_e5m2_cast": [0, 0],
            "store_kvcache": [0, 0],
        },
        "global": {
            "protective_clone": [0, 0],
            "scale_divide": [0, 0],
            "bf16_to_e5m2_cast": [0, 0],
            "store_kvcache": [0, 0],
        },
    }
    qkv = {
        "local": {"count": 0, "token_layer_rows": 0, "seconds_ns": 0, "registers": set()},
        "global": {"count": 0, "token_layer_rows": 0, "seconds_ns": 0, "registers": set()},
    }
    expected = [
        "elementwise_kernel",
        "elementwise_kernel",
        "elementwise_kernel",
        "elementwise_kernel",
        "vectorized_elementwise_kernel",
        "vectorized_elementwise_kernel",
        "store_kvcache",
    ]
    matched = 0
    for index, row in enumerate(rows):
        start, end, name, grid_x, grid_y, block_x, registers, dynamic_smem = row
        if name != "_qkv_norm_rope_inplace_kernel":
            continue
        kind = "local" if grid_y == 64 else "global" if grid_y == 40 else None
        if kind is None:
            raise AssertionError(f"unexpected QKV gridY {grid_y}")
        if block_x != 128 or dynamic_smem != 16:
            raise AssertionError("unexpected measured QKV block or dynamic shared memory")
        qkv[kind]["count"] += 1
        qkv[kind]["token_layer_rows"] += grid_x
        qkv[kind]["seconds_ns"] += end - start
        qkv[kind]["registers"].add(registers)
        following = rows[index + 1 : index + 8]
        names = [item[2] for item in following]
        if names != expected:
            raise AssertionError(f"unrecognized cache chain after QKV: {names}")
        matched += 1
        mappings = [
            "protective_clone",
            "protective_clone",
            "scale_divide",
            "scale_divide",
            "bf16_to_e5m2_cast",
            "bf16_to_e5m2_cast",
            "store_kvcache",
        ]
        for stage, item in zip(mappings, following, strict=True):
            stages[kind][stage][0] += 1
            stages[kind][stage][1] += item[1] - item[0]

    if matched != 3660:
        raise AssertionError(f"expected 3660 exact QKV chains, found {matched}")
    for kind, expected_count in (("local", 3050), ("global", 610)):
        if qkv[kind]["count"] != expected_count:
            raise AssertionError(f"{kind} QKV count mismatch")
        qkv[kind]["seconds"] = qkv[kind].pop("seconds_ns") / 1e9
        qkv[kind]["registers_per_thread"] = sorted(qkv[kind].pop("registers"))
        for stage in stages[kind].values():
            stage[:] = [stage[0], stage[1] / 1e9]

    retained_removed_seconds = (
        sum(stages["local"][name][1] for name in (
            "scale_divide",
            "bf16_to_e5m2_cast",
            "store_kvcache",
        ))
        + sum(stage[1] for stage in stages["global"].values())
    )
    local_rows = qkv["local"]["token_layer_rows"]
    global_rows = qkv["global"]["token_layer_rows"]
    local_elements = local_rows * 2 * 16 * 256
    global_elements = global_rows * 2 * 4 * 512
    avoided_bytes = local_elements * 8 + global_elements * 12
    compulsory_candidate_write_bytes = local_elements + global_elements
    return {
        "qkv": qkv,
        "cache_chain": stages,
        "retained_stack_removable_seconds": retained_removed_seconds,
        "retained_stack_eliminated_launches": 3050 * 5 + 610 * 7,
        "physical_bytes": {
            "local_kv_elements": local_elements,
            "global_kv_elements": global_elements,
            "avoided_bytes": avoided_bytes,
            "compulsory_candidate_write_bytes": compulsory_candidate_write_bytes,
            "avoided_to_compulsory_write_ratio": (
                avoided_bytes / compulsory_candidate_write_bytes
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=pathlib.Path, required=True)
    parser.add_argument("--gemma4-causal", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    project = pathlib.Path(__file__).resolve().parent
    candidate = project / "fused_qkv_kv_cache.py"
    installer = project / "install_fused_qkv_cache.py"
    consumer = project / "exact_consumer.py"
    for source in (candidate, installer, consumer):
        ast.parse(source.read_text(), filename=str(source))
    patched = patch_source(args.gemma4_causal.read_bytes())
    patched_text = patched.decode()
    if "qkv_norm_rope_cache_store(" not in patched_text:
        raise AssertionError("candidate invocation was not installed")
    if "save_kv_cache=False" not in patched_text:
        raise AssertionError("baseline consumer was not disabled after fused commit")

    chain = extract_chain(args.profile)
    measured_fraction = chain["retained_stack_removable_seconds"] / PROFILE_SECONDS
    measured_ceiling_per_request = (
        chain["retained_stack_removable_seconds"] / REQUESTS
    )
    conservative_realization = 0.5
    conservative_saving = (
        QUALIFIED_SECONDS_PER_REQUEST * measured_fraction * conservative_realization
    )
    candidate_bound = QUALIFIED_SECONDS_PER_REQUEST - conservative_saving
    result = {
        "schema_version": 1,
        "validation_type": "offline_source_and_trace_reconstruction",
        "passed": True,
        "profile": {
            "path": str(args.profile.resolve()),
            "sha256": sha256(args.profile),
            "profile_seconds": PROFILE_SECONDS,
            "requests": REQUESTS,
        },
        "source": {
            "candidate_sha256": sha256(candidate),
            "installer_sha256": sha256(installer),
            "consumer_sha256": sha256(consumer),
            "pinned_gemma4_causal_sha256": sha256(args.gemma4_causal),
            "patched_gemma4_causal_sha256": hashlib.sha256(patched).hexdigest(),
            "all_python_ast_valid": True,
            "patch_applies_to_exact_pinned_source": True,
        },
        "trace_reconstruction": chain,
        "whole_request_bound": {
            "evidence_label": "derived",
            "qualified_seconds_per_request": QUALIFIED_SECONDS_PER_REQUEST,
            "profile_measured_removable_fraction": measured_fraction,
            "profile_zero_added_cost_ceiling_seconds_per_request": (
                measured_ceiling_per_request
            ),
            "conservative_realization_fraction": conservative_realization,
            "conservative_saving_seconds_per_request": conservative_saving,
            "conservative_candidate_seconds_per_request": candidate_bound,
            "conservative_complete_request_reduction_fraction": (
                conservative_saving / QUALIFIED_SECONDS_PER_REQUEST
            ),
            "campaign_target_seconds_per_request": CAMPAIGN_TARGET_SECONDS_PER_REQUEST,
            "crosses_campaign_target": candidate_bound
            <= CAMPAIGN_TARGET_SECONDS_PER_REQUEST,
        },
    }
    atomic_json(args.output, result)


if __name__ == "__main__":
    main()
