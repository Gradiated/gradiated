#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from paged_fp8_contract import (
    EXPECTED_IMAGE,
    EXPECTED_SOURCE_HASHES,
    EXPECTED_VLLM_REVISION,
    EXPECTED_VLLM_VERSION,
    atomic_json,
    sha256_file,
    utc_now,
)

PROJECT = Path(__file__).resolve().parent
OUTPUT = PROJECT / "H100_PAGED_FP8_EXECUTION_READY.json"
READMISSION = PROJECT / "DIRECTOR_EXECUTION_EQUIVALENT_READMISSION_20260726.json"


def resolve_bound_path(path: str) -> Path:
    return (PROJECT / path).resolve()


def main() -> int:
    result = {
        "schema_version": 1,
        "type": "h100_paged_fp8_execution_readiness_terminal",
        "generated_at_utc": utc_now(),
        "project": "h100_hybrid_attention_kernel_mechanism",
        "result": "source_falsified_or_unresolved",
        "pass": False,
        "provider_create_allowed": False,
        "gpu_claim_allowed": False,
        "provider_queried": False,
        "provider_mutated": False,
        "gpu_used": False,
        "gpu_seconds": 0,
        "actual_spend_usd": 0.0,
        "scientific_sample_consumed": False,
    }
    try:
        readmission = json.loads(READMISSION.read_text())
        bound_inputs = {}
        for item in readmission["bound_inputs"]:
            path = resolve_bound_path(item["path"])
            observed = sha256_file(path)
            if observed != item["sha256"]:
                raise RuntimeError(f"bound input changed: {item['path']}")
            bound_inputs[item["path"]] = {
                "sha256": observed,
                "bytes": path.stat().st_size,
            }

        source_files = (
            "paged_fp8_contract.py",
            "paged_fp8_execution.py",
            "test_paged_fp8_execution.py",
            "build_readiness.py",
        )
        sources = {
            name: sha256_file(PROJECT / name)
            for name in source_files
        }
        rejected_hash = readmission["bound_inputs"][3]["sha256"]
        if sources["paged_fp8_execution.py"] == rejected_hash:
            raise RuntimeError("fresh execution program reuses rejected bytes")

        command = [
            sys.executable,
            "-m",
            "unittest",
            "-v",
            "test_paged_fp8_execution.py",
        ]
        completed = subprocess.run(
            command,
            cwd=PROJECT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        test_log = PROJECT / "READINESS_TESTS.txt"
        test_log.write_text(completed.stdout, encoding="utf-8")
        if completed.returncode:
            raise RuntimeError("narrow readiness tests failed")

        result.update(
            {
                "result": "source_complete_start_ready",
                "pass": True,
                "decision": "Source is ready for a later director-authorized "
                            "H100 claim; this terminal does not authorize one.",
                "identity": {
                    "immutable_image": EXPECTED_IMAGE,
                    "observed_runtime_required": EXPECTED_VLLM_VERSION,
                    "observed_revision_required": EXPECTED_VLLM_REVISION,
                    "expected_source_hashes": EXPECTED_SOURCE_HASHES,
                },
                "bound_inputs": bound_inputs,
                "source": {
                    "fresh_vs_rejected": True,
                    "files": sources,
                    "test_log": {
                        "path": "READINESS_TESTS.txt",
                        "sha256": sha256_file(test_log),
                        "bytes": test_log.stat().st_size,
                    },
                },
                "reachable_construction_trace": {
                    "pass": True,
                    "evidence_test": (
                        "NativeConstructionTests."
                        "test_registered_attention_native_spec_and_builder_are_reachable"
                    ),
                    "path": [
                        "with set_current_vllm_config(config)",
                        "Attention(..., attn_backend=TritonAttentionBackend)",
                        "layer.get_kv_cache_spec(config)",
                        "builder_cls(spec, [layer_name], config, cuda_device)",
                        "CommonAttentionMetadata(...)",
                        "builder.build(common_prefix_len=0, "
                        "common_attn_metadata=common, fast_build=False)",
                        "unified_kv_cache_update(full_context_k, full_context_v, "
                        "layer_name)",
                        "unified_attention_with_output(..., layer_name, "
                        "kv_cache_dummy_dep=dependency)",
                    ],
                },
                "implemented_gates": {
                    "registered_attention": True,
                    "native_kv_cache_spec": True,
                    "native_common_metadata_and_builder": True,
                    "full_context_local_16x256_and_global_4x512": True,
                    "concurrency_8_16_32": True,
                    "paired_bf16_fp8_e4m3_timing": True,
                    "independent_dense_reference": True,
                    "finite_nonzero_and_representation_oracles": True,
                    "atomic_sentinel_before_sweep": True,
                    "nvtx_scoped_fail_closed_ncu_counters": True,
                    "conditional_sweep_with_seven_minute_reserve": True,
                    "50_10_layer_by_358_step_economic_aggregation": True,
                    "transitive_runtime_and_source_binding": True,
                },
                "later_execution": {
                    "entrypoint": (
                        "python3 paged_fp8_execution.py run "
                        "--readiness H100_PAGED_FP8_EXECUTION_READY.json "
                        "--output-root <absolute-artifact-root> "
                        "--absolute-deadline-utc <UTC> "
                        f"--image-digest {EXPECTED_IMAGE}"
                    ),
                    "first_stage": "local1024 c8 and global4214 c8 sentinel",
                    "conditional_stage": "c8/c16/c32 local1024 and global "
                                         "4214/4393/4571 sweep",
                    "typed_terminal": "H100_PAGED_FP8_EXECUTION_TERMINAL.json",
                },
                "test": {
                    "command": command,
                    "returncode": completed.returncode,
                    "test_count": completed.stdout.count(" ... ok"),
                },
                "evidence_boundary": "Static and CPU-mocked source-readiness "
                                     "evidence only. No H100 throughput, quality, "
                                     "counter, endpoint, or economic result is claimed.",
            }
        )
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
    atomic_json(OUTPUT, result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
