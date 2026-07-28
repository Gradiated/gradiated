#!/usr/bin/env python3
"""Source-bound, single-model recovery contract for the later H200 retry.

This module deliberately has no torch or SGLang import: the present director
action is an offline repair.  It binds the *production server* construction
path which previously loaded the exact target on this H200, and the adapter
objects which must be attached to that one resident model before a later
component submission.  It must not be used to instantiate ``ModelRunner``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
TARGET_MODEL_REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
PINNED_IMAGE = "gemma4-dflash-sglang:588d1f7bc942"
MEM_FRACTION_STATIC = 0.85
DEVICE_CAPACITY_GIB = 139.8
# Measured on this exact target/server construction in the retained H200 log.
MEASURED_PRODUCTION_SERVER_MIB = 121_960
SHADOW_KV_BYTES = 1_342_177_280
# Deliberately larger than the observed 194-MiB graph private pool and
# 241-MiB unallocated reserve from the failed direct constructor.  This is a
# conservative derived allowance for graph capture, adapter scratch, and
# allocator headroom, not a measured allocation.
UNMODELED_RESERVE_GIB = 10.5
CONVERTED_LAYERS = (11, 23, 35, 47, 59)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gib_from_mib(value: float) -> float:
    return value / 1024.0


def memory_plan() -> dict[str, float]:
    production_model_gib = gib_from_mib(MEASURED_PRODUCTION_SERVER_MIB)
    shadow_kv_gib = SHADOW_KV_BYTES / (1024**3)
    expected_peak_gib = production_model_gib + shadow_kv_gib + UNMODELED_RESERVE_GIB
    return {
        "device_capacity_gib": DEVICE_CAPACITY_GIB,
        "production_server_measured_gib": production_model_gib,
        "shadow_kv_derived_gib": shadow_kv_gib,
        "unmodeled_reserve_gib": UNMODELED_RESERVE_GIB,
        "expected_peak_gib": expected_peak_gib,
        "margin_gib": DEVICE_CAPACITY_GIB - expected_peak_gib,
    }


def production_server_argv() -> list[str]:
    """The only permitted later construction path; it owns one target model."""
    return [
        "python3",
        "-m",
        "sglang.launch_server",
        "--model-path", "/models/target",
        "--tokenizer-path", "/models/target",
        "--revision", TARGET_MODEL_REVISION,
        "--dtype", "bfloat16",
        "--tp-size", "1",
        "--attention-backend", "triton",
        "--host", "0.0.0.0",
        "--port", "30000",
        "--context-length", "5000",
        "--max-running-requests", "32",
        "--mem-fraction-static", str(MEM_FRACTION_STATIC),
        "--skip-server-warmup",
    ]


def adapter_binding() -> dict[str, Any]:
    """The adapter boundary installed in the resident server before submission."""
    return {
        "one_resident_target_model": True,
        "eager_full_model_reference": "forbidden; compare post-accept output through a sequential eager call on the same model",
        "converted_layers": list(CONVERTED_LAYERS),
        "phase_selector": {
            "TARGET_VERIFY": "proxy_local primary plus stock shadow K/V",
            "all_other_non_idle_modes": "stock primary plus proxy-local shadow K/V",
            "IDLE": "no attention and no cache write",
        },
        "cache_banks": ["stock", "proxy_local"],
        "cache_lifecycle": "mirror_alloc_write_move_free_for_both_banks",
        "target_verify_geometry": {"requests": 32, "draft_depth": 12, "logical_rows": 384},
        "padded_row_policy": "padded rows perform no cache write",
        "insertion_points": [
            "sglang.srt.models.gemma4_causal.Gemma4Attention.forward",
            "sglang.srt.layers.attention.triton_backend.TritonAttnBackend.forward_extend",
            "sglang.srt.speculative.eagle_worker.NGramWorker.forward_batch_generation",
            "sglang.srt.speculative.eagle_info.NGramDraftInput.move_kv_cache",
        ],
        "candidate_submission_boundary": "only after this binding is attached to the single production-server model",
    }


def build_terminal() -> dict[str, Any]:
    files = {
        "recovery_action": ROOT / "DIRECTOR_FULL_MODEL_OOM_RECOVERY.json",
        "scientific_binding": ROOT / "DIRECTOR_PHASE_SELECTIVE_FULL_MODEL_H200_BINDING.json",
        "dispatcher": ROOT / "phase_dispatcher.py",
        "adapter_contract": Path(__file__),
        "future_worker_bridge": ROOT / "phase_selective_full_model_remote.py",
    }
    hashes = {name: {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)} for name, path in files.items()}
    plan = memory_plan()
    if plan["expected_peak_gib"] > 132.0 or plan["margin_gib"] < 7.8:
        raise RuntimeError(f"memory margin contract violated: {plan}")
    bridge_text = (ROOT / "phase_selective_full_model_remote.py").read_text()
    if "from sglang.srt.model_executor.model_runner import" in bridge_text or "runner.load_model(" in bridge_text:
        raise RuntimeError("future worker bridge still contains standalone ModelRunner residency")
    if "install_phase_selective_adapter" not in bridge_text:
        raise RuntimeError("future worker bridge does not bind the phase-selective adapter")
    return {
        "schema_version": 1,
        "classification": "source_complete_operational_repair",
        "scientific_component_consumed": False,
        "candidate_cuda_invocation_started": False,
        "gpu_claimed": False,
        "evidence": {
            "measured": {
                "production_server_gpu_mib": MEASURED_PRODUCTION_SERVER_MIB,
                "source": "gemma4_h200_dflash_endpoint/RESEARCH_LOG.md (exact target server, retained H200)",
                "failed_direct_constructor_allocated_gib": 138.71,
            },
            "derived": memory_plan(),
            "inferred": {
                "construction_change": "official SGLang launch_server path with one target model replaces standalone ModelRunner construction",
                "no_duplicate_model": True,
                "adapter_residency": "adapter attaches to the existing server model and uses stock/proxy cache banks; it does not instantiate a reference model",
            },
        },
        "construction": {
            "producer": "pinned SGLang v0.5.13 production launch_server",
            "image": PINNED_IMAGE,
            "checkpoint_revision": TARGET_MODEL_REVISION,
            "argv": production_server_argv(),
            "forbidden": ["standalone ModelRunner", "eager duplicate full-model reference", "second target model"],
        },
        "adapter": adapter_binding(),
        "changed_executable_inputs": hashes,
        "next_action": "Later director re-admission may launch this single-model server, attach the adapter before the first TARGET_VERIFY submission, and run only the still-unconsumed full-model component gates.",
    }


def main() -> int:
    destination = ROOT / "FULL_MODEL_MEMORY_ADAPTER_READY_TERMINAL.json"
    payload = build_terminal()
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
