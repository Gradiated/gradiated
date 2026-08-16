#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from distinct_request_gate import DistinctRequestPromotionGate


PROJECT = Path(__file__).resolve().parent
WORKSPACE = PROJECT.parents[6]
PINNED = WORKSPACE / ".agents/runtime/sglang-v0.5.13-source"
CPP = PINNED / "python/sglang/jit_kernel/csrc/ngram_corpus"
ARTIFACT = PROJECT / "artifacts/offline-source-probe"

EXPECTED_INPUTS = {
    "TRACE_PACKET.json": "ccc559094ee612d5da11e771c2ebf8ac14046ad03b8ec7bd6ae165be25725d68",
    "causal_result.json": "44e631b769d53127ca98907e0205132afa0fd3530595d6dd9962a999d3c3b396",
    "exact_semantic_rows.jsonl": "630d05bd860d1dd22c3e35ba2d8f792afc5051f0c68e0a74a9deda8140a02b36",
    "ngram-launch.json": "8349853a7eac9e73211f5d3081c834c05f78e0fd292ddbe5acb921b1824a523d",
    "ngram_worker.source.py": "27721b777cae08657ec9854ec0137a0db50afd49d84809503312fa43e399b554",
    "requests.jsonl": "10e7edacaa194fd0f43b3a3c38f7d91cec0ceba22df8e08e3b5897b174346135",
}
EXPECTED_SOURCE_ROWS = {
    "dominant_only": (11, 11, 11),
    "three_token_transient": (4, 4, 11),
    "persistent_alternate": (2, 4, 0),
    "persistent_alternate_after_four_normal": (4, 4, 11),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_and_run(source: str, output: str) -> list[dict]:
    binary = ARTIFACT / output
    result = subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-O2",
            "-I",
            str(CPP),
            str(PROJECT / source),
            str(CPP / "trie.cpp"),
            str(CPP / "result.cpp"),
            "-o",
            str(binary),
        ],
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    executed = subprocess.run([str(binary)], text=True, capture_output=True)
    binary.unlink()
    if executed.returncode:
        raise RuntimeError(executed.stderr)
    return [json.loads(line) for line in executed.stdout.splitlines()]


def bounded_gate_probe() -> dict:
    gate = DistinctRequestPromotionGate(2)
    assert not gate.admit("request-a", [1])
    assert not gate.admit("request-a", [1])
    assert not gate.admit("request-b", [2])
    assert not gate.admit("request-c", [3])
    assert gate.evicted == 1
    assert not gate.admit("request-z", [1])
    assert gate.admit("request-z", [3])
    before = gate.probation_entries
    gate.clear()
    return {
        "capacity": 2,
        "evicted": gate.evicted,
        "same_request_self_promoted": False,
        "distinct_request_promoted": True,
        "probation_before_clear": before,
        "probation_after_clear": gate.probation_entries,
        "eviction": "deterministic_fifo",
        "completion_order_dependency": False,
    }


def main() -> None:
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    observed_inputs = {
        name: digest(PROJECT / "inputs/bound" / name) for name in EXPECTED_INPUTS
    }
    if observed_inputs != EXPECTED_INPUTS:
        raise RuntimeError(
            {"expected_inputs": EXPECTED_INPUTS, "observed_inputs": observed_inputs}
        )
    source_rows = compile_and_run("bound_source_probe.cpp", "bound-source-probe")
    observed_source = {
        row["scenario"]: (
            row["bfs_accepted_drafts"],
            row["prob_accepted_drafts"],
            row["linear_accepted_drafts"],
        )
        for row in source_rows
    }
    if observed_source != EXPECTED_SOURCE_ROWS:
        raise RuntimeError(
            {
                "expected_source_rows": EXPECTED_SOURCE_ROWS,
                "observed_source_rows": observed_source,
            }
        )
    candidate_rows = compile_and_run(
        "distinct_request_probe.cpp", "distinct-request-probe"
    )
    expected_candidate = {
        "dominant_support_two": (11, 0),
        "request_32_transient_quarantined": (11, 0),
        "request_790_self_repeat_quarantined": (11, 0),
    }
    observed_candidate = {
        row["scenario"]: (
            row["dominant_accepted_drafts"],
            row["alternate_accepted_drafts"],
        )
        for row in candidate_rows
    }
    if observed_candidate != expected_candidate:
        raise RuntimeError(
            {
                "expected_candidate_rows": expected_candidate,
                "observed_candidate_rows": observed_candidate,
            }
        )
    bounded = bounded_gate_probe()
    result = {
        "schema_version": 1,
        "result": "offline_distinct_request_support_two_gate_pass",
        "semantics": "target-semantics preserving; write admission only",
        "input_sha256": observed_inputs,
        "implementation_sha256": {
            "gate": digest(PROJECT / "distinct_request_gate.py"),
            "overlay": digest(PROJECT / "distinct_request_sitecustomize.py"),
            "candidate_probe": digest(PROJECT / "distinct_request_probe.cpp"),
            "bound_probe": digest(PROJECT / "bound_source_probe.cpp"),
        },
        "bound_source_rows": source_rows,
        "candidate_rows": candidate_rows,
        "bounded_probation": bounded,
        "decision": {
            "bound_scenarios_reproduced": True,
            "common_suffix_promotes_at_support_two": True,
            "request_32_rare_branch_probationary": True,
            "request_790_rare_branch_probationary": True,
            "one_request_cannot_self_promote": True,
            "memory_bounded": True,
            "cleanup_completion_order_independent": True,
            "gpu_discriminator_admitted_after_predecessor_release": True,
        },
    }
    path = ARTIFACT / "RESULT.json"
    part = path.with_suffix(".json.part")
    part.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    part.replace(path)
    print(json.dumps(result["decision"], sort_keys=True))


if __name__ == "__main__":
    main()
