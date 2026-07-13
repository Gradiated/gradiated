#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


class QualityError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise QualityError(f"invalid JSON {path.name}: {error}") from error


def read_jsonl(path):
    try:
        return [json.loads(line) for line in path.read_text().splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise QualityError(f"invalid JSONL {path.name}: {error}") from error


def load_and_validate(root):
    root = Path(root)
    manifest = read_json(root / "FROZEN_MANIFEST.json")
    expected_files = {
        "policy.json", "provenance.json", "development.jsonl", "holdout.jsonl",
        "sample_development_responses.jsonl", "sample_holdout_responses.jsonl",
        "build_quality.py", "validate_quality.py", "score_pair.py", "run_pair.py", "RUNNER_INTERFACE.md",
    }
    if set(manifest.get("files", {})) != expected_files:
        raise QualityError("manifest file set is not exact")
    for name, expected in manifest["files"].items():
        try:
            actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        except OSError as error:
            raise QualityError(f"missing suite file {name}") from error
        if actual != expected:
            raise QualityError(f"file hash mismatch: {name}")
    if hashlib.sha256(canonical(manifest["files"])).hexdigest() != manifest.get("bundle_sha256"):
        raise QualityError("suite identity mismatch")
    policy = read_json(root / "policy.json")
    provenance = read_json(root / "provenance.json")
    if provenance.get("reuse_status") != "synthetic_owned":
        raise QualityError("quality content provenance is not explicitly reusable")
    frozen = {
        "max_overall_point_regression": 0.02,
        "max_critical_category_regression": 0.05,
        "catastrophic_category_failure_is_reject": True,
        "max_teacher_forced_nll_relative_increase": 0.05,
        "mtp_identity_requirement": "exact_normalized_output_identity",
        "external_llm_judge_allowed": False,
    }
    if any(policy.get(key) != value for key, value in frozen.items()):
        raise QualityError("quality policy differs from controlling contract")
    execution = policy.get("execution_contract", {})
    if execution != {
        "chat_endpoint": "/v1/chat/completions",
        "teacher_forced_logprob_endpoint": "/generate",
        "temperature": 0.0,
        "top_p": 1.0,
        "max_output_tokens": 256,
        "timeout_seconds": 180,
        "request_repetitions": 1,
        "serving_correctness_repetitions": 2,
        "teacher_forced_max_new_tokens": 1,
        "caller_supplied_nll_allowed": False,
        "model_emitted_compliance_flags_allowed": False,
    }:
        raise QualityError("quality execution contract drifted")
    expected_categories = {
        "tool_call", "coding", "long_context_retrieval", "multi_turn_continuation",
        "teacher_forced_loss", "serving_correctness",
    }
    all_ids = set()
    fixtures_by_split = {}
    for split in ["development", "holdout"]:
        rows = read_jsonl(root / f"{split}.jsonl")
        if {row.get("category") for row in rows} != expected_categories:
            raise QualityError(f"{split} category set is not exact")
        for row in rows:
            if row.get("split") != split or row.get("case_id") in all_ids:
                raise QualityError("split mismatch or duplicate case id")
            all_ids.add(row["case_id"])
            payload = dict(row)
            record_hash = payload.pop("content_sha256", None)
            if hashlib.sha256(canonical(payload)).hexdigest() != record_hash:
                raise QualityError(f"fixture hash mismatch: {row.get('case_id')}")
            if row.get("critical") is not True:
                raise QualityError("all compact categories must remain critical")
            if row.get("category") == "long_context_retrieval":
                binding = row.get("tokenizer_binding", {})
                if len(row.get("synthetic_context", "")) < 40_000:
                    raise QualityError("long-context fixture is below frozen raw-content floor")
                if binding.get("status") != "required_before_gpu_execution" or binding.get("checkpoint_revision") != "75fce70":
                    raise QualityError("long-context tokenizer binding is missing")
            if row.get("category") == "teacher_forced_loss":
                text = row.get("teacher_forced_text")
                scorer = row.get("scorer", {})
                if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != row.get("token_sequence_sha256"):
                    raise QualityError("teacher-forced sequence identity mismatch")
                if scorer.get("kind") != "teacher_forced_logprobs" or scorer.get("minimum_scored_tokens") != 3:
                    raise QualityError("teacher-forced scorer must require raw runtime logprobs")
            if row.get("category") == "serving_correctness" and row.get("deterministic_repetitions") != 2:
                raise QualityError("deterministic serving repetitions drifted")
        fixtures_by_split[split] = rows
    return {"manifest": manifest, "policy": policy, "provenance": provenance, "fixtures": fixtures_by_split}


if __name__ == "__main__":
    import sys
    try:
        result = load_and_validate(Path(__file__).resolve().parent)
    except QualityError as error:
        print(f"INVALID: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(result["manifest"]["bundle_sha256"])
