#!/usr/bin/env python3
"""Publish the canonical typed terminal and concise project state."""
from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def main() -> int:
    root = Path(__file__).resolve().parent
    raw_path = root / "artifacts/reference_run.json"
    spectrum_path = root / "artifacts/spectrum_oracle.json"
    consumer_path = root / "artifacts/persisted_index_consumer.json"
    raw = json.loads(raw_path.read_text())
    spectrum = json.loads(spectrum_path.read_text())
    consumer = json.loads(consumer_path.read_text())
    if (
        raw["decision"] != "reference_positive_lowrank_net_traffic_in_sample"
        or not raw["promote"]
        or not spectrum["gate"]["passed"]
        or consumer["classification"] != "persisted_lowrank_index_consumer_valid"
        or not consumer["stock_candidate_set_inside_survivors"]
        or not consumer["dense_reference_winner_inside_survivors"]
        or consumer["net_physical_bytes_avoided_fraction"] <= 0
        or consumer["science_replayed"]
    ):
        raise RuntimeError("accepted_positive_contract_not_satisfied")

    opportunity_path = root / "OPPORTUNITY_REGISTER.json"
    opportunity = json.loads(opportunity_path.read_text())
    entry = opportunity["opportunities"][0]
    entry["status"] = "positive_in_scope_requires_disjoint_query_gate"
    entry["result"] = {
        "evidence_class": "measured CPU/reference exact-stock-set containment and derived physical traffic",
        "stock_candidate_set_certified": True,
        "oracle_gross_physical_avoided_fraction": spectrum["oracle"][
            "gross_physical_member_weight_bytes_avoided_fraction"
        ],
        "persisted_consumer_gross_physical_avoided_fraction": consumer[
            "gross_physical_member_weight_bytes_avoided_fraction"
        ],
        "persisted_consumer_net_physical_avoided_fraction": consumer[
            "net_physical_bytes_avoided_fraction"
        ],
        "persisted_consumer_physical_union_rows": consumer[
            "physical_union_survivor_rows"
        ],
        "decision": "promote_to_disjoint_query_reference_not_h200",
    }
    entry["residual_bottleneck"] = (
        "The in-sample span makes projected bounds nearly exact; the remaining "
        "uncertainty is transfer to hidden rows not used to form the basis."
    )
    atomic_json(opportunity_path, opportunity)

    net_fraction = consumer["net_physical_bytes_avoided_fraction"]
    inherited_head_seconds = raw["economics"][
        "inherited_output_consumer_seconds_per_request"
    ]
    canonical_economics = {
        **raw["economics"],
        "analytical_net_seconds_saved_upper_bound": (
            inherited_head_seconds * net_fraction
        ),
        "analytical_service_seconds_per_request_lower_bound": (
            raw["economics"]["campaign_denominator_seconds_per_request"]
            - inherited_head_seconds * net_fraction
        ),
        "interpretation": (
            "The byte-proportional value is an analytical upper bound for the "
            "persisted CPU/reference consumer. It does not transfer through the "
            "same-row basis to held-out queries or H200 latency."
        ),
    }
    terminal = {
        "schema_version": 1,
        "classification": (
            "typed_reference_positive_exact_stock_set_and_net_physical_traffic_"
            "in_sample"
        ),
        "completed_at_utc": datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "question": (
            "Can a query-asymmetric low-rank projection plus conservative per-row "
            "residual certificates preserve the exact pinned stock set and reduce "
            "physical output-head traffic on the same 32 exact rows?"
        ),
        "decision": {
            "in_scope_representation_pass": True,
            "promote_to_disjoint_query_reference": True,
            "promote_to_h200_component": False,
            "reason": (
                "The persisted rank-32 consumer retained the exact stock candidate "
                f"set while its 32-query exact-weight union was "
                f"{consumer['physical_union_survivor_rows']} of 262144 rows. "
                f"After charging all declared index, metadata, score-buffer, "
                f"survivor, and verification traffic, it avoided "
                f"{100 * net_fraction:.6f}% of dense physical bytes. The basis was "
                "trained on these same rows, so held-out transfer is unmeasured."
            ),
        },
        "stock_consumer": raw["stock_consumer"],
        "geometry": raw["geometry"],
        "mechanism": raw["mechanism"],
        "correctness": {
            **raw["correctness"],
            "persisted_index_fresh_process_valid": True,
            "runtime_weight_norm_is_conservative_by_triangle_inequality": True,
            "canonical_physical_union_survivor_rows": consumer[
                "physical_union_survivor_rows"
            ],
            "canonical_logical_survivor_rows": consumer[
                "logical_survivor_rows"
            ],
        },
        "spectrum_oracle_discriminator": {
            "classification": spectrum["classification"],
            "rank": spectrum["rank"],
            "rank_fraction_of_hidden": spectrum["rank_fraction_of_hidden"],
            "basis_gram_spectral_error": spectrum[
                "basis_gram_spectral_error"
            ],
            "query_residual_norm_max": spectrum["query_residual_norm_max"],
            "gate": spectrum["gate"],
            "oracle": spectrum["oracle"],
        },
        "physical_result": {
            "canonical_persisted_consumer": consumer,
            "producer_in_memory_result": raw["results"]["implementable"],
            "causal_result": (
                "The full 32-row query span reduced the query residual to a guarded "
                "maximum of 7.95e-10. Projected scoring therefore isolated a "
                "103-row physical union after the persisted consumer used the "
                "triangle-derived runtime weight-norm guard. The score-buffer and "
                "index traffic, not exact tied-weight verification, dominate the "
                "remaining 281,758,732 bytes."
            ),
        },
        "storage": raw["storage"],
        "economics": canonical_economics,
        "timing": raw["timing"],
        "resource_use": raw["resource_use"],
        "scope_and_limits": {
            "closed": (
                "The strongest admitted rank-32 query-span possibility bound does "
                "not fail the 10% gross-union gate; the same-row representation is "
                "a typed positive."
            ),
            "open": (
                "A disjoint-query reference must establish whether a fixed basis "
                "learned from prior traffic retains selectivity before any H200 "
                "component is admissible."
            ),
            "not_claimed": (
                "No held-out-query pruning, H200 timing, endpoint speed, quality, "
                "or production economics is claimed."
            ),
        },
        "artifacts": {
            "contract": "EXPERIMENT_CONTRACT.json",
            "contract_sha256": sha256_file(root / "EXPERIMENT_CONTRACT.json"),
            "runner": "run_lowrank_residual.py",
            "runner_sha256": sha256_file(root / "run_lowrank_residual.py"),
            "spectrum_oracle": "artifacts/spectrum_oracle.json",
            "spectrum_oracle_sha256": sha256_file(spectrum_path),
            "raw_result": "artifacts/reference_run.json",
            "raw_result_sha256": sha256_file(raw_path),
            "index": "artifacts/lowrank_index.pt",
            "index_sha256": sha256_file(root / "artifacts/lowrank_index.pt"),
            "amendment": "AMENDMENT_001.json",
            "amendment_sha256": sha256_file(root / "AMENDMENT_001.json"),
            "persisted_consumer": "artifacts/persisted_index_consumer.json",
            "persisted_consumer_sha256": sha256_file(consumer_path),
            "persisted_consumer_runner": "validate_persisted_index.py",
            "persisted_consumer_runner_sha256": sha256_file(
                root / "validate_persisted_index.py"
            ),
            "opportunity_register": "OPPORTUNITY_REGISTER.json",
            "opportunity_register_sha256": sha256_file(opportunity_path),
        },
    }
    terminal_path = root / "LOSSLESS_LOWRANK_RESIDUAL_TERMINAL.json"
    atomic_json(terminal_path, terminal)
    terminal_sha256 = sha256_file(terminal_path)
    status = {
        "schema_version": 1,
        "status": "complete",
        "priority": 7900,
        "researcher_profile": "deep",
        "authorized_spend_usd": 0.0,
        "actual_spend_usd": 0.0,
        "reservation_required": False,
        "allocation_limit": 1,
        "active_session": None,
        "wall_clock_budget_minutes": 45,
        "compute_budget": (
            "CPU/reference only; consumed one spectrum/index producer and one "
            "persisted-index consumer repair without replaying the producer."
        ),
        "storage_budget": (
            "4 GiB additional; immutable weights/capture use hard-linked read-only "
            "views and the runtime index is 70,584,754 bytes."
        ),
        "claim_allowed": False,
        "bench_need": None,
        "gpu_need": None,
        "result": {
            "classification": terminal["classification"],
            "terminal": terminal_path.name,
            "terminal_sha256": terminal_sha256,
            "stock_candidate_set_certified": True,
            "rank": spectrum["rank"],
            "oracle_gross_physical_avoided_fraction": spectrum["oracle"][
                "gross_physical_member_weight_bytes_avoided_fraction"
            ],
            "canonical_gross_physical_avoided_fraction": consumer[
                "gross_physical_member_weight_bytes_avoided_fraction"
            ],
            "canonical_net_physical_avoided_fraction": net_fraction,
            "canonical_physical_union_survivor_rows": consumer[
                "physical_union_survivor_rows"
            ],
            "candidate_total_bytes": consumer["traffic"][
                "candidate_total_bytes"
            ],
            "dense_control_bytes": consumer["traffic"]["dense_weight_bytes"],
            "promote_to_disjoint_query_reference": True,
            "promote_to_h200_component": False,
        },
        "summary": (
            "Typed same-row reference positive: the persisted rank-32 residual "
            "index certified the exact stock set, reduced the physical exact-weight "
            "union to 103/262144 rows, and avoided 90.0035% net bytes after all "
            "declared index, metadata, score-buffer, survivor, and verification "
            "traffic. The basis was learned on the evaluation rows."
        ),
        "next_action": (
            "Do not claim H200 yet. Admit one disjoint-query CPU/reference test "
            "using a basis learned from earlier exact hidden rows and a held-out "
            "32-row stock set; promote to an H200 component only if exact "
            "containment and positive net physical traffic survive."
        ),
    }
    atomic_json(root / "STATUS.json", status)
    print(json.dumps({"terminal_sha256": terminal_sha256, "status": "complete"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
