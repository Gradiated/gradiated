#!/usr/bin/env python3
"""Build the typed offline mechanism terminal from verified local artifacts."""

from __future__ import annotations

import hashlib
import json
import pathlib


ROOT = pathlib.Path(__file__).resolve().parent


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> dict:
    return json.loads((ROOT / name).read_text())


def main() -> int:
    if (ROOT / "CAUSAL_PARALLEL_OFFSET_HEAD_READY.json").exists():
        raise RuntimeError("ready_artifact_must_not_exist_without_holdout")
    split = load("IMMUTABLE_SPLIT.json")
    cost = load("COST_MODEL.json")
    fixture = load("EXACT_SHAPE_FIXTURE.json")
    capture_fixture = load("artifacts/capture-fixture/CAPTURE_FIXTURE.json")
    source_binding = load("SOURCE_BINDING.json")
    if not (
        split["request_disjoint"]
        and split["train"]["examples"] == 4096
        and split["holdout"]["examples"] == 512
        and fixture["pass"]
        and capture_fixture["pass"]
        and not cost["decision"]["ready"]
    ):
        raise RuntimeError("terminal_input_gate_failed")
    sources = [
        "causal_parallel_offset_head.py",
        "capture_offset_taps.py",
        "capture_bootstrap/sitecustomize.py",
        "train_and_evaluate.py",
        "exact_shape_fixture.py",
        "cost_model.py",
        "build_immutable_split.py",
        "materialize_binding.py",
        "test_causal_parallel_offset_head.py",
    ]
    terminal = {
        "schema_version": 1,
        "classification": "typed_mechanism_result",
        "result": "offline_cost_path_requires_unmeasured_near_perfect_prefix_survival",
        "ready": False,
        "ready_artifact_written": False,
        "reason": (
            "The source-complete head and capture/training path execute through "
            "their offline fixtures, but the optimistic full-cost model requires "
            "16.054 accepted target tokens per verification (94.0875% of the "
            "maximum draft prefix). No disjoint real-tap holdout or trained "
            "checkpoint exists, and the project has $0 GPU authority."
        ),
        "mechanism": {
            "binding": {
                "path": "MECHANISM_BINDING.json",
                "sha256": sha256(ROOT / "MECHANISM_BINDING.json"),
            },
            "source": {
                path: sha256(ROOT / path)
                for path in sources
            },
            "exact_shape_fixture": {
                "path": "EXACT_SHAPE_FIXTURE.json",
                "sha256": sha256(ROOT / "EXACT_SHAPE_FIXTURE.json"),
                "pass": True,
                "evidence": "executed PyTorch meta operator graph, not CUDA",
            },
            "capture_fixture": {
                "path": "artifacts/capture-fixture/CAPTURE_FIXTURE.json",
                "sha256": sha256(
                    ROOT / "artifacts/capture-fixture/CAPTURE_FIXTURE.json"
                ),
                "pass": True,
                "evidence": "executed CPU request-reorder ownership fixture",
            },
        },
        "data": {
            "split": {
                "path": "IMMUTABLE_SPLIT.json",
                "sha256": sha256(ROOT / "IMMUTABLE_SPLIT.json"),
                "train_examples": 4096,
                "holdout_examples": 512,
                "request_disjoint": True,
            },
            "real_target_tap_rows_present": False,
            "synthetic_acceptance_substituted": False,
        },
        "cost": {
            "path": "COST_MODEL.json",
            "sha256": sha256(ROOT / "COST_MODEL.json"),
            "qualified_baseline_seconds_per_request": 0.625149101968745,
            "target_seconds_per_request": 0.500119281574996,
            "required_mean_accepted_target_tokens": cost["service_model"][
                "threshold"
            ]["mean_accepted_target_tokens"],
            "required_draft_prefix_fraction": cost["service_model"]["threshold"][
                "draft_prefix_fraction_of_maximum"
            ],
            "perfect_acceptance_projected_seconds_per_request": cost[
                "service_model"
            ]["sensitivity"][-1]["projected_seconds_per_request"],
            "evidence_labels": cost["evidence_labels"],
        },
        "baseline": {
            "depth": 4,
            "mean_accepted_target_tokens": 3.006315789473684,
            "accepted_target_tokens_per_cuda_event_second": 521.9159530781905,
            "paired_endpoint_improvement_fraction": 0.011349460841934111,
        },
        "binding_defect": source_binding[
            "semantic_localization_binding"
        ],
        "external_boundary": {
            "classification": "zero_spend_no_eligible_capture_or_training_venue",
            "authorized_spend_usd": 0.0,
            "actual_spend_usd": 0.0,
            "gpu_claimed": False,
            "provider_mutation": False,
            "matched_gpu_command": None,
            "why": (
                "A matched GPU command is a READY-only claim. The exact capture "
                "and training commands are preserved in EXPERIMENT_CONTRACT.json, "
                "but executing them is outside the current zero-dollar authority."
            ),
        },
        "experiment_contract": {
            "path": "EXPERIMENT_CONTRACT.json",
            "sha256": sha256(ROOT / "EXPERIMENT_CONTRACT.json"),
        },
        "scientific_samples_consumed_this_turn": 0,
        "provider_spend_usd": 0.0,
        "next_action": (
            "Director consumes this typed result. Reopen only with positive "
            "spend and a compatible H200 for one bound capture/train/holdout "
            "cycle; do not claim readiness before the 16.054-token holdout gate."
        ),
    }
    output = ROOT / "CAUSAL_PARALLEL_OFFSET_HEAD_RESULT.json"
    temporary = output.with_suffix(".json.part")
    temporary.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
