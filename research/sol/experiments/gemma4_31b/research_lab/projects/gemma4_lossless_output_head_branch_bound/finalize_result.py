#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parent
RAW = PROJECT / "artifacts" / "reference_run.json"
TERMINAL = PROJECT / "LOSSLESS_BRANCH_BOUND_TERMINAL.json"
STATUS = PROJECT / "STATUS.json"
TRACE_ARTIFACT = (
    PROJECT.parent
    / "gemma4_hierarchical_tied_head_codesign"
    / "HIERARCHICAL_TIED_HEAD_PHYSICAL_SCREEN.json"
)
TRACE_SHA256 = "40b00f5bd09dfbb02420ca4535f80d024a9f2df01e3cfecedaf9f24afb54f206"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    json.loads(temporary.read_text())
    temporary.replace(path)


def main() -> None:
    raw = json.loads(RAW.read_text())
    trace = json.loads(TRACE_ARTIFACT.read_text())
    if sha256_file(TRACE_ARTIFACT) != TRACE_SHA256:
        raise RuntimeError("trace_artifact_hash_mismatch")
    if (
        raw["decision"] != "typed_falsification_lossless_bound_too_loose"
        or raw["promote_to_h200_component"]
        or not raw["correctness"]["all_reference_winners_inside_all_survivor_sets"]
        or raw["resource_use"]["provider_spend_usd"] != 0.0
        or raw["resource_use"]["gpu_invocations"] != 0
    ):
        raise RuntimeError("raw_terminal_gate_mismatch")
    best_oracle = raw["best_oracle_stock_bf16"]
    best_implementable = raw["best_implementable_stock_bf16"]
    head_fraction = trace["trace_attribution"][
        "all_identified_output_consumer_fraction_of_window"
    ]
    oracle_request_fraction = (
        head_fraction * best_oracle["physical_weight_bytes_avoided_fraction"]
    )
    baseline = 0.625149101968745
    target = 0.500119281574996
    completed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    terminal = {
        "schema_version": 1,
        "classification": "typed_falsification_lossless_bound_too_loose",
        "completed_at_utc": completed,
        "question": "Can an exact partial-dot branch-and-bound search materially prune Gemma 4's 262144-way tied output head?",
        "decision": {
            "promote_to_h200_component": False,
            "close_mechanism": "fixed-coordinate partial-dot plus residual-Cauchy bound",
            "reason": "The strongest oracle-incumbent stock-safe operating point avoided only 4.43246023995536% of physical 32-row union weight bytes, versus the preregistered 20% gate. The implementable incumbent avoided 3.745778401692712%.",
        },
        "geometry_and_stock_consumer": raw["geometry"] | raw["stock_consumer"],
        "mechanism": raw["mechanism"],
        "correctness": raw["correctness"]
        | {
            "lossless_semantics": "Every skipped row has a conservative upper bound below a feasible incumbent's conservative lower bound. Exact stock rescoring of all survivors therefore preserves the stock winner even though the CPU interval does not itself identify a unique H200 BF16 winner.",
            "softcap": "The stock 30.0 tanh softcap is monotone, so the certified pre-softcap survivor set remains safe for top-1.",
        },
        "pruning_result": {
            "best_implementable_stock_bf16": best_implementable,
            "best_oracle_stock_bf16": best_oracle,
            "best_oracle_exact_real": max(
                (
                    {
                        "selected_dimensions": row["selected_dimensions"],
                        **row["oracle_incumbent_exact_real"],
                    }
                    for row in raw["sweep"]
                ),
                key=lambda row: row["physical_weight_bytes_avoided_fraction"],
            ),
            "zero_physical_pruning_through_dimensions": 3072,
            "dense_tied_weight_bytes": 262144 * 5376 * 2,
            "causal_result": "Residual norms remain wider than logit margins until most coordinates are consumed. Across 32 rows, different logical survivors union into most vocabulary rows, erasing more pruning than the per-row averages suggest.",
        },
        "h200_context": {
            "evidence_class": "derived from inherited exact-c32 measured trace and the new analytical byte bound",
            "trace_artifact": str(TRACE_ARTIFACT.relative_to(PROJECT.parent)),
            "trace_artifact_sha256": TRACE_SHA256,
            "all_output_consumer_interval_fraction": head_fraction,
            "oracle_proportional_request_reduction_fraction": oracle_request_fraction,
            "oracle_proportional_seconds_saved": baseline * oracle_request_fraction,
            "oracle_proportional_service_seconds_per_request": baseline
            * (1.0 - oracle_request_fraction),
            "campaign_target_seconds_per_request": target,
            "interpretation": "This deliberately overcredits byte avoidance as proportional elimination of the entire measured head/materialization/softcap/argmax interval. It yields only 0.24887191575671277% request reduction and remains far above target.",
        },
        "scope_and_limits": {
            "sample": "32 real rows, exactly one deterministic row from each request in the immutable 1536-row c32 capture",
            "performance": "CPU runtime is diagnostic only. No H200 traversal, gather, dispatch, component latency, endpoint, or synthetic performance claim was made.",
            "mechanism_scope": "This closes the fixed common-coordinate L2 residual certificate. It does not close learned, approximate, quality-recovered, tree, or materially stronger exact MIPS indexes.",
            "stock_identity_limit": "The conservative CPU BF16 interval could not name a unique stock H200 dense winner; the pruning proof is set-safe and requires exact stock rescoring of survivors.",
        },
        "artifacts": {
            "raw_result": str(RAW.relative_to(PROJECT)),
            "raw_result_sha256": sha256_file(RAW),
            "runner": "run_lossless_branch_bound.py",
            "runner_sha256": sha256_file(PROJECT / "run_lossless_branch_bound.py"),
            "contract": "EXPERIMENT_CONTRACT.json",
            "contract_sha256": sha256_file(PROJECT / "EXPERIMENT_CONTRACT.json"),
            "amendments": [
                {
                    "path": "AMENDMENT_001.json",
                    "sha256": sha256_file(PROJECT / "AMENDMENT_001.json"),
                },
                {
                    "path": "AMENDMENT_002.json",
                    "sha256": sha256_file(PROJECT / "AMENDMENT_002.json"),
                },
            ],
        },
        "resource_use": raw["resource_use"]
        | {
            "actual_spend_usd": 0.0,
            "additional_project_bytes": sum(
                path.stat().st_size
                for path in PROJECT.rglob("*")
                if path.is_file() and path.stat().st_nlink == 1
            ),
        },
    }
    atomic_json(TERMINAL, terminal)
    terminal_sha256 = sha256_file(TERMINAL)
    status = json.loads(STATUS.read_text())
    status.update(
        {
            "status": "complete",
            "active_session": None,
            "actual_spend_usd": 0.0,
            "claim_allowed": False,
            "bench_need": None,
            "gpu_need": None,
            "decision": "typed_falsification_lossless_bound_too_loose",
            "scientific_sample_consumed": True,
            "summary": "A stock-safe partial-dot plus residual-Cauchy reference preserved every possible stock winner in its survivor set but was intrinsically too loose: the best implementable 32-row physical union avoided 3.7458% of head-weight bytes, and even an oracle incumbent avoided only 4.4325%.",
            "result": {
                "classification": terminal["classification"],
                "sample_rows": 32,
                "requests": 32,
                "best_implementable_physical_weight_bytes_avoided_fraction": best_implementable[
                    "physical_weight_bytes_avoided_fraction"
                ],
                "best_oracle_physical_weight_bytes_avoided_fraction": best_oracle[
                    "physical_weight_bytes_avoided_fraction"
                ],
                "best_oracle_selected_dimensions": best_oracle[
                    "selected_dimensions"
                ],
                "promote_to_h200_component": False,
                "gpu_invocations": 0,
                "provider_spend_usd": 0.0,
                "terminal": TERMINAL.name,
                "terminal_sha256": terminal_sha256,
                "raw_result": str(RAW.relative_to(PROJECT)),
                "raw_result_sha256": sha256_file(RAW),
            },
            "next_action": "Preserve the typed negative. Do not claim the warm H200 for this fixed-coordinate residual-Cauchy mechanism. A successor must use a materially stronger exact index or a learned/quality-recovered non-lossless head.",
            "completed_at_utc": completed,
        }
    )
    atomic_json(STATUS, status)


if __name__ == "__main__":
    main()
