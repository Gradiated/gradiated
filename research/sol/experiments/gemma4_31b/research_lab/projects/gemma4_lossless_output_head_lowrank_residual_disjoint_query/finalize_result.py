#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", type=Path, required=True)
    args = parser.parse_args()
    project = args.project_dir
    raw_path = project / "artifacts" / "disjoint_query_result.json"
    raw = json.loads(raw_path.read_text())
    expected_classification = (
        "typed_falsification_frozen_lowrank_disjoint_net_physical_traffic_nonpositive"
    )
    if (
        raw["classification"] != expected_classification
        or not raw["decision"]["exact_stock_set_pass"]
        or raw["decision"]["net_physical_traffic_positive"]
        or raw["decision"]["promote_to_h200_component"]
        or raw["physical_result"]["physical_union_survivor_rows"] != 262143
        or raw["physical_result"]["traffic"]["net_bytes_saved"] >= 0
        or not all(
            raw["disjointness"][field]
            for field in (
                "storage_indices_disjoint",
                "global_rows_disjoint",
                "ownership_tuples_disjoint",
                "hidden_bf16_row_hashes_disjoint",
            )
        )
    ):
        raise RuntimeError("raw_result_does_not_match_terminal_gate")
    files = {
        "contract": project / "EXPERIMENT_CONTRACT.json",
        "opportunity_register": project / "OPPORTUNITY_REGISTER.json",
        "runner": project / "run_disjoint_query.py",
        "finalizer": project / "finalize_result.py",
        "raw_result": raw_path,
        "stdout": project / "artifacts" / "disjoint_query.stdout.log",
        "stderr": project / "artifacts" / "disjoint_query.stderr.log",
        "frozen_index": project / "artifacts" / "frozen_lowrank_index.pt",
    }
    artifacts = {
        name: {
            "path": str(path.relative_to(project)),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for name, path in files.items()
    }
    head_seconds = 0.03510060919172893
    net_fraction = raw["physical_result"][
        "net_physical_bytes_avoided_fraction"
    ]
    terminal = {
        "schema_version": 1,
        "classification": raw["classification"],
        "completed_at_utc": raw["completed_at_utc"],
        "question": raw["question"],
        "artifacts": artifacts,
        "geometry": raw["geometry"],
        "disjointness": raw["disjointness"],
        "frozen_mechanism": raw["frozen_mechanism"],
        "correctness": raw["correctness"],
        "physical_result": raw["physical_result"],
        "decision": {
            **raw["decision"],
            "close_frozen_rank32_transfer_representation": True,
            "redirect_to_materially_different_output_head_representation": True,
            "reason": (
                "All exact-stock semantics passed, but the preregistered disjoint "
                "query residual expanded the physical union to 262143 of 262144 "
                "rows. Fully charged candidate traffic exceeded dense by "
                "381301888 bytes (13.528193%), so the frozen rank-32 transfer "
                "representation is closed without an H200 component."
            ),
        },
        "economics": {
            "campaign_denominator_seconds_per_request": 0.625149101968745,
            "campaign_target_seconds_per_request": 0.500119281574996,
            "inherited_output_consumer_seconds_per_request": head_seconds,
            "analytical_byte_proportional_seconds_saved_upper_bound": (
                head_seconds * net_fraction
            ),
            "interpretation": (
                "The negative byte-proportional figure is an analytical traffic "
                "regression, not a measured CPU or H200 latency effect."
            ),
        },
        "resource_use": raw["resource_use"],
        "timing": raw["timing"],
        "scope_and_limits": {
            **raw["scope_and_limits"],
            "closed": (
                "Frozen predecessor rank-32 index transfer to disjoint exact "
                "capture rows under the complete physical-union accounting."
            ),
            "open": (
                "Materially different lossless output-head representations; "
                "the independent QKV endpoint lane is unchanged."
            ),
        },
    }
    atomic_json(
        project / "LOSSLESS_LOWRANK_RESIDUAL_DISJOINT_TERMINAL.json", terminal
    )
    print(json.dumps(terminal["decision"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
