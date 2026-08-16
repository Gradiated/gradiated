#!/usr/bin/env python3
"""Materialize hash-verified producer, consumer, and telemetry bytes locally."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil


BINDINGS = {
    "source/gemma4_causal.py": (
        "projects/gemma4_h200_ngram_verification_critical_path/inputs/source/gemma4_causal.py",
        "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989",
    ),
    "source/logits_processor.py": (
        "projects/gemma4_h200_ngram_verification_critical_path/inputs/source/logits_processor.py",
        "e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14",
    ),
    "source/ngram_info.py": (
        "projects/gemma4_h200_ngram_verification_critical_path/inputs/source/ngram_info.py",
        "ffa88c663e1893c306710ac801da0693d8248ebcfd1a5bc705c157f90657af1c",
    ),
    "source/ngram_worker.py": (
        "projects/gemma4_h200_ngram_verification_critical_path/inputs/source/ngram_worker.py",
        "27721b777cae08657ec9854ec0137a0db50afd49d84809503312fa43e399b554",
    ),
    "source/config.json": (
        "projects/gemma4_h200_ngram_verification_critical_path/inputs/checkpoint/config.json",
        "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    ),
    "evidence/DFLASH_C32_DEPTH_COST_TERMINAL.json": (
        "projects/gemma4_h200_dflash_endpoint/DFLASH_C32_DEPTH_COST_TERMINAL.json",
        "c2cdc9bedbe4de8120ef9641ec7c9d745657e21352c3d388291ef5020ecdf637",
    ),
    "evidence/GROUPED_LM_HEAD_H200_GRAPH_REPLAY_TERMINAL.json": (
        "projects/gemma4_h200_ngram_persistent_grouped_lm_head/GROUPED_LM_HEAD_H200_GRAPH_REPLAY_TERMINAL.json",
        "d6ce199adc0debcc5e10380e71b219009858c160efc60be56c81d571f240bda1",
    ),
    "evidence/CONTROL_PRODUCER_STAGE.json": (
        "projects/gemma4_h200_ngram_persistent_grouped_lm_head/artifacts/graph-safe-endpoint-20260725t210418z/retrieved/CONTROL_PRODUCER_STAGE.json",
        "de7512df1428a77810902df196c228df9328f33ecdb5ffcdef72b754365d641d",
    ),
    "evidence/TRACE_ANALYSIS_REPAIR.json": (
        "projects/gemma4_h200_ngram_verification_critical_path/artifacts/ngram-critical-20260724t115729Z/TRACE_ANALYSIS_REPAIR.json",
        "a22e25b3e911891d75e1008f22a03ad2a7d160584e1c83e660b8a3238602304f",
    ),
    "evidence/PARALLEL_DRAFT_FRONTIER.json": (
        "projects/gemma4_lossless_parallel_draft_frontier/PARALLEL_DRAFT_FRONTIER.json",
        "59e35a96d00f370ad7eb6eb9721195a939265091f47094cff9947b62577c4f8b",
    ),
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lab-root", required=True, type=pathlib.Path)
    parser.add_argument("--output-root", required=True, type=pathlib.Path)
    args = parser.parse_args()
    rows = []
    for local_name, (relative_source, expected) in BINDINGS.items():
        source = args.lab_root / relative_source
        observed = sha256(source)
        if observed != expected:
            raise RuntimeError(
                f"binding_hash_mismatch:{relative_source}:{observed}:{expected}"
            )
        destination = args.output_root / "inputs" / local_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        os.chmod(destination, 0o444)
        rows.append(
            {
                "path": str(pathlib.Path("inputs") / local_name),
                "source": relative_source,
                "sha256": observed,
                "bytes": destination.stat().st_size,
            }
        )
    binding = {
        "schema_version": 1,
        "classification": "immutable_project_local_source_and_evidence_binding",
        "rows": rows,
        "runtime": {
            "name": "SGLang",
            "commit": "588d1f7bc9424201f89957e145f9d5af633a3eb8",
        },
        "model": {
            "id": "google/gemma-4-31B-it",
            "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        },
        "semantic_localization_binding": {
            "director_expected_sha256": "7fef9d24407d7cc9bb78a76b7caa7ceea32ba6a6460670f6d0fb30eca57c34f2",
            "observed_sha256": "7e59aab982b1f6c833a444d4635c1347db6995cfdcb749902d556eb57ab8a46b",
            "consumed": False,
            "classification": "cross_project_binding_digest_mismatch",
        },
    }
    output = args.output_root / "SOURCE_BINDING.json"
    temporary = output.with_suffix(".json.part")
    temporary.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
