#!/usr/bin/env python3
"""Publish the typed terminal and concise project state."""
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
    raw = json.loads(raw_path.read_text())
    if (
        raw["decision"] != "typed_falsification_cluster_radius_union_too_loose"
        or raw["promote_to_h200_component"]
        or not raw["correctness"][
            "stock_candidate_set_inside_all_reported_survivor_sets"
        ]
    ):
        raise RuntimeError("raw_result_not_accepted_negative")
    oracle = raw["results"]["optimistic_oracle"]
    implementable = raw["results"]["implementable"]
    opportunity_path = root / "OPPORTUNITY_REGISTER.json"
    opportunity = json.loads(opportunity_path.read_text())
    entry = opportunity["opportunities"][0]
    entry["status"] = "falsified"
    entry["result"] = {
        "evidence_class": "measured CPU/reference physical-union simulation",
        "stock_candidate_set_certified": True,
        "implementable_gross_physical_avoided_fraction": implementable[
            "gross_physical_member_weight_bytes_avoided_fraction"
        ],
        "oracle_gross_physical_avoided_fraction": oracle[
            "gross_physical_member_weight_bytes_avoided_fraction"
        ],
        "oracle_net_physical_avoided_fraction": oracle[
            "net_physical_bytes_avoided_fraction"
        ],
        "oracle_physical_union_survivor_rows": oracle[
            "physical_union_survivor_member_rows"
        ],
        "decision": "do_not_promote_to_h200_component",
    }
    entry["residual_bottleneck"] = (
        "No 4096- or 256-row parent pruned; full-vector leaf radii left "
        "99.5239% of vocabulary rows in the 32-query physical union."
    )
    atomic_json(opportunity_path, opportunity)
    terminal = {
        "schema_version": 1,
        "classification": (
            "typed_falsification_hierarchical_cluster_radius_physical_union_"
            "and_net_negative"
        ),
        "completed_at_utc": datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "question": (
            "Can a conservative hierarchical exact-MIPS index certify the pinned "
            "Gemma 4 c32 sampler and avoid material physical output-head traffic?"
        ),
        "decision": {
            "promote_to_h200_component": False,
            "close_mechanism": (
                "balanced random-projection full-vector BF16 centroid/L2-radius "
                "hierarchy with 4096/256/32-row nodes"
            ),
            "reason": (
                "The implementable traversal avoided zero physical member-weight "
                "bytes. Even an optimistic oracle incumbent avoided only "
                f"{100 * oracle['gross_physical_member_weight_bytes_avoided_fraction']:.6f}% "
                "before overhead and regressed net traffic by "
                f"{-100 * oracle['net_physical_bytes_avoided_fraction']:.6f}%."
            ),
        },
        "stock_consumer": raw["stock_consumer"],
        "geometry": raw["geometry"],
        "mechanism": raw["mechanism"],
        "correctness": raw["correctness"],
        "physical_result": {
            "implementable": implementable,
            "optimistic_oracle": oracle,
            "causal_result": (
                "No 4096-row or 256-row node could be rejected. The implementable "
                "32-query union touched all 8192 leaves and every vocabulary row; "
                "the oracle rejected only 39 leaves, leaving 260896 of 262144 rows. "
                "The full-vector radii therefore remain wider than stock-safe "
                "incumbent gaps even after query-independent proximity sorting."
            ),
        },
        "storage": raw["storage"],
        "economics": raw["economics"],
        "timing": raw["timing"],
        "resource_use": raw["resource_use"],
        "scope_and_limits": {
            "closed": (
                "This closes the measured balanced random-projection centroid/"
                "radius decomposition for the exact 32-row capture."
            ),
            "open": (
                "It does not close learned or quality-recovered heads, non-ball "
                "exact indexes with materially stronger bounds, or different "
                "model/workload identities."
            ),
            "performance": (
                "CPU time is diagnostic. No H200 component, endpoint, or production "
                "latency claim was made."
            ),
        },
        "artifacts": {
            "contract": "EXPERIMENT_CONTRACT.json",
            "contract_sha256": sha256_file(root / "EXPERIMENT_CONTRACT.json"),
            "runner": "run_cluster_mips.py",
            "runner_sha256": sha256_file(root / "run_cluster_mips.py"),
            "raw_result": "artifacts/reference_run.json",
            "raw_result_sha256": sha256_file(raw_path),
            "producer_cache": "artifacts/hierarchy.pt",
            "producer_cache_sha256": sha256_file(root / "artifacts/hierarchy.pt"),
            "amendment": "AMENDMENT_001.json",
            "amendment_sha256": sha256_file(root / "AMENDMENT_001.json"),
            "opportunity_register": "OPPORTUNITY_REGISTER.json",
            "opportunity_register_sha256": sha256_file(opportunity_path),
        },
    }
    terminal_path = root / "LOSSLESS_CLUSTER_MIPS_TERMINAL.json"
    atomic_json(terminal_path, terminal)
    terminal_sha256 = sha256_file(terminal_path)
    status = {
        "schema_version": 1,
        "status": "complete",
        "priority": 7800,
        "researcher_profile": "deep",
        "authorized_spend_usd": 0.0,
        "actual_spend_usd": 0.0,
        "reservation_required": False,
        "allocation_limit": 1,
        "active_session": None,
        "wall_clock_budget_minutes": 45,
        "compute_budget": (
            "CPU/reference and source analysis only; consumed one exact hierarchy "
            "producer and one repaired consumer continuation."
        ),
        "storage_budget": (
            "4 GiB additional; immutable weights/capture used through hard-linked "
            "read-only views."
        ),
        "claim_allowed": False,
        "bench_need": None,
        "gpu_need": None,
        "result": {
            "classification": terminal["classification"],
            "terminal": terminal_path.name,
            "terminal_sha256": terminal_sha256,
            "stock_candidate_set_certified": True,
            "implementable_gross_physical_avoided_fraction": implementable[
                "gross_physical_member_weight_bytes_avoided_fraction"
            ],
            "oracle_gross_physical_avoided_fraction": oracle[
                "gross_physical_member_weight_bytes_avoided_fraction"
            ],
            "oracle_net_physical_avoided_fraction": oracle[
                "net_physical_bytes_avoided_fraction"
            ],
            "oracle_physical_union_survivor_rows": oracle[
                "physical_union_survivor_member_rows"
            ],
            "promote_to_h200_component": False,
        },
        "summary": (
            "Typed negative: the exact stock greedy candidate set was certified, "
            "but the implementable hierarchy read every row; even the oracle "
            "incumbent avoided only 0.4761% gross physical member bytes and added "
            "4.3753% net traffic after metadata and survivor traffic."
        ),
        "next_action": (
            "Do not claim or schedule H200 work for this centroid/radius hierarchy. "
            "Preserve the negative; revisit only with a materially stronger non-ball "
            "exact bound or a separately admitted learned/quality-recovered head."
        ),
    }
    atomic_json(root / "STATUS.json", status)
    print(json.dumps({"terminal_sha256": terminal_sha256, "status": "complete"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
