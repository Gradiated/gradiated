#!/usr/bin/env python3
"""Adopt the consumed offline producer result into the project terminal."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
PROJECTS = PROJECT.parent
RAW = PROJECT / "artifacts/offline-r512-20260727/OFFLINE_RAW_TERMINAL.json"
OUTPUT = PROJECT / "SPARSE_LOWRANK_RESIDUAL_OFFLINE_TERMINAL.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def identity(path: Path, role: str) -> dict[str, object]:
    return {
        "path": str(path),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "role": role,
    }


def main() -> int:
    raw = json.loads(RAW.read_text())
    checks = raw["focused_offline_checks"]
    if raw["resources"]["ranks_evaluated"] != [512]:
        raise RuntimeError("refuse to adopt a rank sweep or changed rank")
    if not checks["complete_physical_bound_positive_m32"]:
        raise RuntimeError("raw M32 physical result changed")
    if not checks["complete_physical_bound_positive_m384"]:
        raise RuntimeError("raw M384 physical result changed")
    if checks["correction_materially_improves_weight_error"]:
        raise RuntimeError("expected terminal reason no longer holds")
    if checks["correction_materially_improves_output_error"]:
        raise RuntimeError("expected terminal reason no longer holds")

    direct_inputs = [
        identity(PROJECT / "PROJECT.md", "director experiment contract"),
        identity(
            PROJECTS
            / "exact_weight_structure_intervention_screen/WEIGHT_STRUCTURE_SCREEN.json",
            "projection selection, checkpoint identity, and prior 2:4 evidence",
        ),
        identity(
            PROJECTS / "gemma4_h200_fp8_weight_stream_schedule/PHYSICAL_MODEL.json",
            "H200 limits and dense-chain physical model",
        ),
        identity(
            PROJECTS
            / "gemma4_h200_fp8_layer_dataflow_fusion/artifacts/"
            "persisted-real-down-v2-repair-20260722t141230z/remote/component-v2/"
            "ROW_M32.json",
            "measured exact M32 dense down-projection consumer",
        ),
        identity(
            PROJECTS
            / "gemma4_h200_ngram_m384_fp8_cluster_schedule/"
            "COMPONENT_MEASUREMENTS.jsonl",
            "measured exact M384 dense down-projection consumer",
        ),
        identity(
            PROJECTS
            / "gemma4_h200_ngram_decode_equivalent_verifier/artifacts/"
            "h200-verifier-20260724t103131Z/retrieved/artifacts/"
            "candidate-full-c32/TERMINAL.json",
            "locked qualified request result and exact workload accounting",
        ),
        identity(
            PROJECTS
            / "gemma4_current_runtime_frontier/artifacts/"
            "current-sglang-h200-20260722t1557z/remote-retrieved/"
            "current-sglang-c32-r2/image-inspect.json",
            "current serving image capability inventory",
        ),
        identity(
            PROJECTS
            / "gemma4_current_runtime_frontier/artifacts/"
            "current-trtllm-h200-20260722t1642z/remote-retrieved/"
            "current-trtllm-c32-r2/image-inspect.json",
            "alternate current image cuSPARSELt capability inventory",
        ),
    ]
    sources_and_generated = [
        identity(PROJECT / "run_offline_recovery.py", "producer/reference consumer"),
        identity(PROJECT / "test_offline_recovery.py", "focused offline tests"),
        identity(Path(__file__).resolve(), "terminal adopter"),
        identity(RAW, "consumed raw scientific terminal"),
        identity(
            PROJECT
            / "artifacts/offline-r512-20260727/"
            "SPARSE_LOWRANK_RESIDUAL_R512.npz",
            "packed sparse-plus-residual representation",
        ),
        identity(
            PROJECT / "artifacts/offline-r512-20260727/SYNTHETIC_M32_INPUT.npy",
            "deterministic synthetic exact-shape input",
        ),
    ]

    raw["generated_utc"] = datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    raw["classification"] = "typed_none_insufficient_residual_recovery"
    raw["decision"] = {
        "type": "none",
        "reason": "The single maximum admissible rank recovers only 8.435% of "
        "uncorrected exact-weight relative error and 8.487% of synthetic M32 "
        "output relative error, below the pre-payload 25% material-recovery "
        "gate. Positive physical opportunity alone cannot promote a model "
        "intervention that fails its required information-recovery path.",
        "quality_safe": False,
        "gpu_falsifier_prepared": False,
        "replay_or_sweep_authorized": False,
    }
    raw["acceptance"] = {
        "single_projection_and_rank": True,
        "source_complete_producer_and_reference_consumer": True,
        "weight_error_materially_recovered": False,
        "output_error_materially_recovered": False,
        "complete_m32_physical_bound_positive": True,
        "complete_m384_physical_bound_positive": True,
        "complete_locked_request_bound_positive": True,
        "positive_offline_result": False,
    }
    raw["direct_input_identities"] = direct_inputs
    raw["source_and_generated_artifact_identities"] = sources_and_generated
    raw["real_current_runtime_h200_exact_consumer"] = {
        "type": "none",
        "reason": "The qualified SGLang image exposes the dense "
        "sgl_kernel.fp8_scaled_mm chain and records cuSPARSE 12.5, but no "
        "cuSPARSELt library, sparse-E4M3 SGLang adapter, or exact six-launch "
        "consumer command. The separately inspected TensorRT-LLM image records "
        "cuSPARSELt 0.8.1.1, but no repository source owns this Gemma "
        "sparse-plus-two-dense-GEMM consumer and that image is not the qualified "
        "current serving runtime. A library-presence command would not be an "
        "execution-equivalent consumer.",
        "audit_scope": "one repository/source and recorded-image capability check; "
        "no GPU, Docker, endpoint, SSH, or provider use",
    }
    raw["focused_offline_checks_artifact"] = {
        "command": "uv run --with numpy==2.3.1 --with pytest python -m pytest "
        "-q test_offline_recovery.py",
        "result": "4 passed",
    }

    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".part")
    temporary.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
