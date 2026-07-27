from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from dual_kv4_contract import (
    CHUNKED_PREFILL_TOKENS,
    CONCURRENCY,
    GLOBAL_LAYER_IDS,
    LOCAL_CAPACITY,
    LOCAL_LAYER_IDS,
    MAX_SEQUENCE_TOKENS,
    OLD_CAPACITY,
    PEAK_LIVE_PHYSICAL_ROWS,
    PHYSICAL_CAPACITY,
    RECENT_CAPACITY,
    WINDOW,
    exact_memory_ledger,
)


ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECTS = ROOT.parent
RUNTIME = Path("/root/workspace/.agents/runtime/gemma4_global_kv_sglang")

AUTHORITATIVE = {
    "local_component_ready": (
        PROJECTS
        / "gemma4_l40s_kv4_outlier_sm89_component"
        / "L40S_KV4_OUTLIER_SM89_COMPONENT_READY.json",
        "ac9ea0118c943f33b55cd4f99ce858f70eacba21e3f80f5e7f4d93be59a4043c",
    ),
    "global_tiered_terminal": (
        PROJECTS
        / "gemma4_l40s_global_tiered_kv4_outlier"
        / "L40S_GLOBAL_TIERED_KV4_OUTLIER_OFFLINE_TERMINAL.json",
        "46db0a82a29f1af4299f5e8a6af7ddaf8bf1c859f5c08c823e9bbfb9c4a79e83",
    ),
    "local_kv4_terminal": (
        PROJECTS
        / "gemma4_l40s_local_kv4_outlier_codesign"
        / "L40S_LOCAL_KV4_OUTLIER_OFFLINE_TERMINAL.json",
        "c0a732ef5cf42cb5744a19afab0fe2734ad37cbd5d720ebcc4a16e02a856cfc2",
    ),
    "campaign": (
        LAB / "CAMPAIGN.md",
        "8029d46b12cdc994b14dbd20dc8b0fd12ac95ca6b8926324820e4c9d5a8d065b",
    ),
}

VENDORED_EXPECTED = {
    "sglang_local_kv4_outlier.py": "16bd6477f1be675bbae83492f057fcb37496026ebf1d7ab9c43e9193d66b8163",
    "local_kv4_outlier_bindings.cpp": "903ccfd27fb74e21d498aa5c98ce7c179f20e315c4963ab3be1162983aaaebd6",
    "local_kv4_outlier_cuda.cu": "6d8a84bd5ef5a1fbacbd95a99e1aa7c180b8d39e590ee1fd657d2da51e4e3944",
    "sglang_global_tiered_kv4.py": "0e46017b00515d567a032eaea54672b8add0f7fb1164c5f5451643d277a9893c",
    "global_tiered_kv4_bindings.cpp": "7c4ae8539de2126bcc872520215504c1c7b0534765a19e191dbf2b233930e0cd",
    "global_tiered_kv4_cuda.cu": "42609740a2fe06033bbb56854a1e710da9897d59be5e696f4367f0cc8f36897b",
    "packet/exact_c32_consumer.py": "37f6d5be144a909557de6caca6c70c5db1706987a115a6e428fe7acb9e736e6d",
    "packet/WORKLOAD.json": "7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d",
    "packet/MODEL_CONFIG.json": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
}

PINNED_RUNTIME = {
    "python/sglang/srt/mem_cache/memory_pool.py": "24caf4bf2af6db4f8dc180f65b2ed8153403cdfd87010b70fcac67fe59434a10",
    "python/sglang/srt/mem_cache/swa_memory_pool.py": "d0d8c9ad1a7652978195bfea112611cd281012c6ff9c12dfd05f445c13534724",
    "python/sglang/srt/layers/attention/triton_backend.py": "e2b0fd4a3ec3c783ae7026f4cb8a7292c1203388a6c9ea5b90e604d3a149f3dc",
    "python/sglang/srt/models/gemma4_causal.py": "9c5f5f5739cbec30284302f266fec1d797a86fb98fa1273a27c97fb5d869d001",
    "python/sglang/srt/mem_cache/allocator/swa.py": "unfrozen_direct_below",
    "python/sglang/srt/model_executor/pool_configurator.py": "unfrozen_direct_below",
}

CHANGED_SOURCE = (
    "dual_kv4_contract.py",
    "sglang_dual_kv4.py",
    "sitecustomize.py",
    "test_dual_kv4_contract.py",
    "run_later_current_runtime.sh",
    "build_terminal.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(command: list[str]) -> None:
    completed = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(
            json.dumps(
                {
                    "command": command,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }
            )
        )


def direct(path: Path, evidence: str = "direct") -> dict[str, Any]:
    return {"path": str(path), "sha256": sha256(path), "evidence": evidence}


def main() -> None:
    for _name, (path, expected) in AUTHORITATIVE.items():
        if sha256(path) != expected:
            raise RuntimeError(f"authoritative hash changed: {path}")
    for relative, expected in VENDORED_EXPECTED.items():
        if sha256(ROOT / relative) != expected:
            raise RuntimeError(f"vendored input changed: {relative}")
    for relative, expected in PINNED_RUNTIME.items():
        if expected != "unfrozen_direct_below" and sha256(RUNTIME / relative) != expected:
            raise RuntimeError(f"pinned runtime source changed: {relative}")

    checked(
        [
            "python3",
            "-m",
            "py_compile",
            *CHANGED_SOURCE[:-2],
            "build_terminal.py",
            "packet/exact_c32_consumer.py",
        ]
    )
    checked(["python3", "-m", "unittest", "-v", "test_dual_kv4_contract.py"])
    checked(["bash", "-n", "run_later_current_runtime.sh"])

    direct_bindings = {
        name: {"path": str(path), "sha256": expected, "evidence": "direct"}
        for name, (path, expected) in AUTHORITATIVE.items()
    }
    direct_bindings["vendored_immutable_inputs"] = {
        relative: direct(ROOT / relative, "project-local immutable snapshot")
        for relative in VENDORED_EXPECTED
    }
    direct_bindings["pinned_runtime_source"] = {
        relative: direct(RUNTIME / relative) for relative in PINNED_RUNTIME
    }
    direct_bindings["changed_source"] = {
        relative: direct(ROOT / relative) for relative in CHANGED_SOURCE
    }
    direct_bindings["offline_import_diagnostic"] = direct(
        ROOT / "artifacts/OFFLINE_IMPORT_DIAGNOSTIC.json"
    )

    terminal = {
        "schema_version": 1,
        "kind": "l40s_dual_kv4_allocator_0953_offline_terminal",
        "project": ROOT.name,
        "classification": (
            "offline_source_complete_memory_positive_conditional_endpoint_path"
        ),
        "decision": "admit_later_current_runtime_component_then_one_c32_endpoint",
        "pass": True,
        "direct_bindings": direct_bindings,
        "fixed_contract": {
            "runtime_commit": "c6a6200a1a778a799ba61c395ac292317f01ebc9",
            "runtime_image": (
                "docker.io/lmsysorg/sglang@sha256:"
                "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
            ),
            "model": "google/gemma-4-31B-it",
            "model_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "accelerator": "one NVIDIA L40S SM89",
            "mem_fraction_static": "0.953",
            "concurrency": CONCURRENCY,
            "prompt_tokens": 4_214,
            "output_tokens": 358,
            "page_size": 1,
            "local_window": WINDOW,
            "local_layers": list(LOCAL_LAYER_IDS),
            "global_layers": list(GLOBAL_LAYER_IDS),
            "maximum_sequence_tokens": MAX_SEQUENCE_TOKENS,
        },
        "memory": exact_memory_ledger(),
        "capacities": {
            "canonical_physical_rows_with_sentinel": PHYSICAL_CAPACITY,
            "maximum_live_physical_rows": PEAK_LIVE_PHYSICAL_ROWS,
            "local_swa_rows_excluding_sentinel": LOCAL_CAPACITY,
            "global_recent_rows": RECENT_CAPACITY,
            "global_recent_steady_rows": LOCAL_CAPACITY,
            "global_recent_prefill_spill_rows": CHUNKED_PREFILL_TOKENS,
            "global_old_rows": OLD_CAPACITY,
        },
        "ownership_contracts": {
            "canonical_request_and_page": (
                "ReqToTokenPool and the unchanged SWATokenToKVPoolAllocator own "
                "request slots and canonical full physical ids; compact global "
                "directories only add locations and never create a second page owner"
            ),
            "local_allocator": (
                "the unchanged full-to-SWA map selects one of 32,768 local ring rows; "
                "all 50 local layers share that row identity and own separate packed "
                "K/V payloads"
            ),
            "global_allocator": (
                "two shared int32 arrays map each of 129,688 canonical ids to at most "
                "one recent and one old compact location; the two int32 free stacks "
                "own compact availability and are counted once for all ten layers"
            ),
            "producer_routing": (
                "new rows in the final 1,024-token request tail call store_recent; "
                "older rows in the same prefill chunk call pack_old directly; only "
                "a previously recent row aging out calls retire_recent"
            ),
            "transition": (
                "the first global layer allocates each old target once, packs the "
                "retiring payload for all ten already-resident global-layer arenas, "
                "then clears/releases the shared recent location before any global "
                "consumer; later layers only write their current new K/V rows"
            ),
            "local_consumer": (
                "layers not congruent to 5 mod 6 consume the runtime-provided "
                "window_kv_indptr/window_kv_indices through fused_local_attention"
            ),
            "global_consumer": (
                "layers congruent to 5 mod 6 traverse the unchanged full kv_indices "
                "once through mixed_tier_paged_attention; no dequantized cache exists"
            ),
            "padding": (
                "negative producer/consumer slots no-op before directory or payload "
                "access; page-zero/sentinel storage is included in the static ledger"
            ),
            "release_reuse": (
                "canonical free first returns both compact locations and clears both "
                "directories; a generation increments before that physical id can be "
                "reused, and grouped frees execute the same release exactly once"
            ),
            "canonical_move": (
                "radix canonical moves transfer compact directory ownership without "
                "copying the ten global payload arenas; local packed rows use the "
                "unchanged translated SWA move"
            ),
        },
        "focused_offline_checks": [
            {
                "command": (
                    "python3 -m py_compile dual_kv4_contract.py "
                    "sglang_dual_kv4.py sitecustomize.py "
                    "test_dual_kv4_contract.py build_terminal.py "
                    "packet/exact_c32_consumer.py"
                ),
                "result": "pass",
            },
            {
                "command": "python3 -m unittest -v test_dual_kv4_contract.py",
                "result": "pass",
                "tests": 8,
                "covers": [
                    "1023/1024/1025 global transition",
                    "negative padded rows",
                    "c1/c31/c32 canonical ownership",
                    "maximum live physical rows",
                    "2048-row prefill spill",
                    "maximum recent and old arena exhaustion",
                    "all-global-payload transition barrier",
                    "release/reuse generation",
                    "canonical page move",
                    "five-local/one-global schedule",
                    "real producer/consumer symbol reachability",
                ],
            },
            {
                "command": "bash -n run_later_current_runtime.sh",
                "result": "pass",
            },
            {
                "command": (
                    "fresh pinned-selected-source import with torch+numpy on the "
                    "CPU coordinator"
                ),
                "result": "typed_not_executable",
                "reason": (
                    "the selected clean source snapshot intentionally contains only "
                    "bound SGLang files and lacks sglang.srt.utils; the digest-pinned "
                    "runtime image is the execution environment. No CUDA/runtime "
                    "claim is transferred from this offline source check."
                ),
            },
        ],
        "conditional_latency_bound": {
            "measured_values_invented": False,
            "symbols": {
                "T_e5m2_l40s_s_per_request": (
                    "later exact c32 current-runtime all-E5M2 L40S control"
                ),
                "m_local_ms": (
                    "p05 of 31 paired complete E5M2-minus-local-KV4 "
                    "producer+consumer wall-ms rows for one local layer/decode step"
                ),
                "m_global_ms": (
                    "conservative paired complete E5M2-minus-tiered-KV4 "
                    "producer+consumer wall-ms margin for one global layer/decode step"
                ),
                "O_integration_s_per_request": (
                    "measured nonnegative directory/routing and endpoint interaction "
                    "overhead not already inside the two complete component pairs"
                ),
            },
            "component_conversion": {
                "local_s_per_request": "0.559375 * m_local_ms",
                "global_s_per_request": "0.111875 * m_global_ms",
                "derivation": {
                    "local": "50 layers * 358 decode steps / (1000 * c32)",
                    "global": "10 layers * 358 decode steps / (1000 * c32)",
                },
            },
            "complete_request_equation": (
                "T_dual = T_e5m2_l40s - 0.559375*m_local_ms "
                "- 0.111875*m_global_ms + O_integration"
            ),
            "price_normalized_acceptance_seconds_per_request": 1.4776251501079425,
            "acceptance_inequality": (
                "0.559375*m_local_ms + 0.111875*m_global_ms "
                "- O_integration >= "
                "T_e5m2_l40s_s_per_request - 1.4776251501079425"
            ),
            "campaign_h200_objective_seconds_per_request": 0.500119281574996,
            "current_unmeasured_bound": {
                "lower_seconds_per_request": 0.0,
                "upper_seconds_per_request": "infinity",
                "reason": (
                    "local target result is in flight and global target component, "
                    "integrated overhead, and exact L40S control are unmeasured"
                ),
            },
            "endpoint_claim": False,
        },
        "source_and_sm89_expectations": {
            "local_consumer": {
                "threads_per_cta": 256,
                "static_shared_bytes": 1_036,
                "producer_threads_per_cta": 256,
                "producer_static_shared_bytes": 2_576,
                "compiled_registers_spills_occupancy": "unmeasured",
                "predicted_physical_change": (
                    "unique K/V read payload falls 43.75%, while the no-GQA-reuse "
                    "CTA-issued upper rises from 268,435,456 to 301,989,888 bytes; "
                    "SM89 timing must decide whether reuse prevents the adverse upper"
                ),
            },
            "global_consumer": {
                "threads_per_cta": 512,
                "static_shared_bytes": 2_060,
                "producer_threads_per_cta": 512,
                "producer_static_shared_bytes": 7_208,
                "register_thresholds_per_thread": {
                    "three_blocks_per_sm_at_most": 42,
                    "two_blocks_per_sm_at_most": 64,
                    "one_block_per_sm_at_most": 128,
                },
                "compiled_registers_spills_occupancy": "unmeasured",
                "predicted_physical_change": (
                    "peak unique global K/V read bytes fall from 531,197,952 to "
                    "363,721,920 and CTA-issued upper falls from 4,793,040,896 to "
                    "3,223,961,600, while integer/conversion work rises"
                ),
            },
        },
        "later_current_runtime": {
            "type": "command",
            "preconditions": [
                "the named project-local immutable checkpoint directory exists",
                "the command runs only after an atomic compatible bench claim",
                "the digest-pinned image and all project-local source hashes match",
                "component results remain unconsumed or are imported without replay",
            ],
            "command": (
                "sudo -n docker run --rm --gpus all --ipc host "
                "--entrypoint /bin/bash "
                "-v /root/workspace/research/sol/experiments/gemma4_31b/"
                "research_lab/projects/gemma4_l40s_dual_kv4_allocator_0953_"
                "integration/checkpoint/immutable:/work/checkpoint:ro "
                "-v /root/workspace/research/sol/experiments/gemma4_31b/"
                "research_lab/projects/gemma4_l40s_dual_kv4_allocator_0953_"
                "integration:/work/integration:ro "
                "-v /root/workspace/research/sol/experiments/gemma4_31b/"
                "research_lab/projects/gemma4_l40s_dual_kv4_allocator_0953_"
                "integration/artifacts:/work/output "
                "docker.io/lmsysorg/sglang@sha256:"
                "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6 "
                "/work/integration/run_later_current_runtime.sh "
                "/work/checkpoint /work/output/l40s-dual-kv4-0953"
            ),
        },
        "scope": {
            "actual_spend_usd": 0.0,
            "gpu_pool_claimed": False,
            "gpu_inventory_inspected": False,
            "live_component_claim_inspected": False,
            "ssh_used": False,
            "provider_or_endpoint_used": False,
            "cuda_invoked": False,
            "checkpoint_shards_read_or_copied": False,
            "representation_allocator_kernel_or_workload_sweep": False,
            "candidate_sample_consumed": False,
        },
        "uncertainty": [
            "No current-runtime CUDA import, compile, kernel, graph, or endpoint call was allowed.",
            "The dynamic lower margin is zero after adversarially charging every unitemized runtime byte to the entire reserved 0.047 partition; observed assigned-only headroom is positive but scope-adjacent.",
            "Local and global component timing, compiled resources, integrated routing overhead, endpoint service time, and quality remain conditional.",
        ],
        "next_action": (
            "Import the one in-flight local component terminal without replay, run one "
            "exact global component on SM89, and only if both complete pair margins "
            "support the inequality launch the single project-local command under a "
            "new director-bound claim; otherwise record typed none."
        ),
    }
    output = ROOT / "L40S_DUAL_KV4_ALLOCATOR_0953_OFFLINE_TERMINAL.json"
    output.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
