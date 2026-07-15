#!/usr/bin/env python3
"""Audit the archived V9 quality capture without modifying the frozen suite."""
import hashlib
import json
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ARCHIVE = ROOT / "campaign_100/allocations/nebius_h100_32k_quality_mtp_v9/stock_no_cache_fcfs-artifact.tar.gz"
MEMBER = "campaign-100-phase-b-stock/quality-stock_no_cache_fcfs-responses.jsonl"


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def unfence(value, language):
    lines = value.strip().splitlines()
    if len(lines) < 3 or lines[0] != f"```{language}" or lines[-1] != "```":
        return None
    return "\n".join(lines[1:-1])


def main():
    archive_bytes = ARCHIVE.read_bytes()
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        raw = archive.extractfile(MEMBER).read()
    rows = {row["case_id"]: row["output"] for row in map(json.loads, raw.splitlines())}
    tool = json.loads(unfence(rows["dev_tool_01"], "json"))
    code = unfence(rows["dev_code_01"], "python")
    retrieval = rows["dev_retrieval_01"]
    serving = json.loads(unfence(rows["dev_serving_01"], "json"))
    mutations = {
        "json_unfence_accepts_exact_single_block": unfence("```json\n{\"x\":1}\n```", "json") == '{"x":1}',
        "json_unfence_rejects_prose": unfence("Here:\n```json\n{\"x\":1}\n```", "json") is None,
        "json_unfence_rejects_wrong_language": unfence("```python\n{}\n```", "json") is None,
        "retrieval_label_is_not_value_equivalence": retrieval != "amber-orbit-17",
        "tool_file_path_is_not_frozen_path_schema": tool != {"name": "read_file", "arguments": {"path": "src/math.py"}},
        "serving_readiness_is_not_frozen_schema": serving != {"status": "ready", "truncated": False},
        "wrong_retrieval_value_is_rejected": "K-4702: amber-orbit-18".removeprefix("K-4702: ") != "amber-orbit-17",
    }
    result = {
        "schema_version": 1,
        "classification": "derived_offline_archived_response_boundary_audit",
        "input": {
            "archive": str(ARCHIVE.relative_to(ROOT)),
            "archive_sha256": sha256(archive_bytes),
            "member": MEMBER,
            "member_sha256": sha256(raw),
        },
        "case_audit": {
            "dev_tool_01": {"raw_output_sha256": sha256(rows["dev_tool_01"].encode()), "finding": "JSON code fence is a presentation boundary; after deterministic unfencing the object is valid JSON, but file_path is not the frozen path contract. This is not a scorer-only rescue."},
            "dev_code_01": {"raw_output_sha256": sha256(rows["dev_code_01"].encode()), "finding": "Deterministic Python fence removal yields parseable, behaviorally correct clamp code. The frozen scorer's direct ast parse therefore confounds a presentation wrapper with coding behavior."},
            "dev_retrieval_01": {"raw_output_sha256": sha256(retrieval.encode()), "finding": "The requested key and expected value occur in the answer, but the prompt did not require value-only output. Exact normalized equality treats this response convention as a failure; do not post-hoc rescore it."},
            "dev_continuation_01": {"raw_output_sha256": sha256(rows["dev_continuation_01"].encode()), "finding": "[development] supplies none of the requested parameter names. It remains a likely task/reasoning-policy failure under the archived prompt."},
            "dev_loss_01": {"raw_output_sha256": sha256(json.dumps(rows["dev_loss_01"], sort_keys=True, separators=(",", ":")).encode()), "finding": "Runtime-bound logprobs are present, but 7.7076 is compared with an uncalibrated absolute ceiling of 2.0. This cannot distinguish capability loss from an out-of-distribution sentinel."},
            "dev_serving_01": {"raw_output_sha256": sha256(rows["dev_serving_01"].encode()), "finding": "After deterministic JSON unfencing the output is a different readiness schema. The expected schema was not specified in the prompt, so this is an interface-fixture defect plus a schema mismatch, not a pure malformed-response failure."},
        },
        "mutation_controls": mutations,
        "conclusion": "The archived zero score is not interpretable as a six-category capability failure: coding is a confirmed presentation/scorer defect; retrieval and serving have underspecified output contracts; tool has a schema ambiguity; continuation remains a real failure candidate; and NLL is uncalibrated. The frozen result remains unchanged and fails its gate.",
        "next_required_evidence": "Freeze a new suite after development calibration with explicit schemas, value-only instructions, deterministic transport normalization limited to a single fenced block, category-specific mutation controls, and an NLL threshold calibrated from intended controls before any holdout is observed.",
    }
    if not all(mutations.values()):
        raise SystemExit("mutation control failed")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
