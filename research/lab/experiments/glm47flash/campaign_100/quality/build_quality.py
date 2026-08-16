#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path


SEED = 470200


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def with_hash(value):
    result = dict(value)
    result["content_sha256"] = digest(canonical(value))
    return result


def synthetic_long_context(left_marker, right_marker, retrieval_value):
    left = " ".join(f"{left_marker}{index:04x}" for index in range(4096))
    right = " ".join(f"{right_marker}{index:04x}" for index in range(4096))
    return f"{left}\nK-4702: {retrieval_value}\n{right}"


def fixtures(split):
    prefix = "dev" if split == "development" else "hold"
    if split == "development":
        tool_path = "src/math.py"
        code_prompt = "Return only Python defining clamp(value, low, high)."
        code_tests = ["assert clamp(-2, 0, 5) == 0", "assert clamp(3, 0, 5) == 3", "assert clamp(8, 0, 5) == 5"]
        retrieval_value = "amber-orbit-17"
        continuation = "value, low, high"
        history_function = "clamp(value, low, high)"
        readiness = {"status": "ready", "truncated": False}
    else:
        tool_path = "src/range.py"
        code_prompt = "Return only Python defining exclusive_upper(start, stop) as a list."
        code_tests = ["assert exclusive_upper(1, 4) == [1, 2, 3]", "assert exclusive_upper(4, 4) == []"]
        retrieval_value = "cobalt-comet-29"
        continuation = "start, stop, step"
        history_function = "span(start, stop, step)"
        readiness = {"status": "healthy", "truncated": False}
    teacher_forced_text = (
        f"GLM quality sentinel for {split}: deterministic tools preserve arguments, "
        "coding preserves executable behavior, and long context preserves the requested key."
    )
    cases = [
        {
            "case_id": f"{prefix}_tool_01", "split": split, "category": "tool_call", "critical": True,
            "prompt": f"Emit one JSON tool call reading {tool_path}, with keys name and arguments.",
            "scorer": {"kind": "json_exact", "expected": {"name": "read_file", "arguments": {"path": tool_path}}},
        },
        {
            "case_id": f"{prefix}_code_01", "split": split, "category": "coding", "critical": True,
            "prompt": code_prompt,
            "scorer": {"kind": "python_tests", "tests": code_tests},
        },
        {
            "case_id": f"{prefix}_retrieval_01", "split": split, "category": "long_context_retrieval", "critical": True,
            "prompt": "In the supplied synthetic long context, return the value paired with key K-4702.",
            "synthetic_context": synthetic_long_context("A" if split == "development" else "C", "B" if split == "development" else "D", retrieval_value),
            "tokenizer_binding": {
                "status": "required_before_gpu_execution",
                "model": "zai-org/GLM-4.7-Flash",
                "checkpoint_revision": "75fce70",
                "minimum_raw_context_characters": 40_000,
            },
            "scorer": {"kind": "normalized_exact", "expected": retrieval_value},
        },
        {
            "case_id": f"{prefix}_continuation_01", "split": split, "category": "multi_turn_continuation", "critical": True,
            "prompt": "Continue the synthetic agent session by stating the parameter names only.",
            "history": [
                {"role": "user", "content": f"Inspect {history_function.split('(')[0]}."},
                {"role": "assistant", "content": f"{history_function} was found."},
            ],
            "scorer": {"kind": "normalized_exact", "expected": continuation},
        },
        {
            "case_id": f"{prefix}_loss_01", "split": split, "category": "teacher_forced_loss", "critical": True,
            "prompt": "Teacher-force the frozen synthetic sequence through the runtime logprob endpoint.",
            "teacher_forced_text": teacher_forced_text,
            "token_sequence_sha256": digest(teacher_forced_text.encode()),
            "scorer": {"kind": "teacher_forced_logprobs", "max_nll": 2.0, "minimum_scored_tokens": 3},
        },
        {
            "case_id": f"{prefix}_serving_01", "split": split, "category": "serving_correctness", "critical": True,
            "prompt": "Return the exact JSON readiness object without prose.",
            "deterministic_repetitions": 2,
            "scorer": {"kind": "json_exact", "expected": readiness},
        },
    ]
    for case in cases:
        case["prompt"] = f"[{split}] {case['prompt']}"
    return [with_hash(case) for case in cases]


def sample_responses(cases):
    rows = []
    for case in cases:
        kind = case["scorer"]["kind"]
        if kind == "json_exact":
            output = json.dumps(case["scorer"]["expected"], sort_keys=True, separators=(",", ":"))
        elif kind == "normalized_exact":
            output = case["scorer"]["expected"]
        elif kind == "teacher_forced_logprobs":
            output = {
                "source": "runtime_teacher_forced_input_token_logprobs",
                "token_sequence_sha256": case["token_sequence_sha256"],
                "input_token_logprobs": [
                    {"logprob": -1.5, "token_id": 1},
                    {"logprob": -1.5, "token_id": 2},
                    {"logprob": -1.5, "token_id": 3},
                ],
            }
        elif case["split"] == "development":
            output = "def clamp(value, low, high):\n    return max(low, min(high, value))\n"
        else:
            output = "def exclusive_upper(start, stop):\n    return list(range(start, stop))\n"
        rows.append({"case_id": case["case_id"], "output": output})
    return rows


def write_json(path, value):
    path.write_bytes(canonical(value) + b"\n")


def write_jsonl(path, values):
    path.write_bytes(b"".join(canonical(value) + b"\n" for value in values))


def build_quality(output):
    output.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parent
    for script in ["build_quality.py", "validate_quality.py", "score_pair.py", "run_pair.py", "RUNNER_INTERFACE.md"]:
        target = (output / script).resolve()
        if target != (source / script).resolve():
            target.write_bytes((source / script).read_bytes())
    policy = {
        "schema_version": 1,
        "suite_name": "glm47flash_campaign_100_paired_quality_v1",
        "frozen_seed": SEED,
        "max_overall_point_regression": 0.02,
        "max_critical_category_regression": 0.05,
        "catastrophic_category_failure_is_reject": True,
        "paired_bootstrap_samples": 2000,
        "paired_confidence_level": 0.95,
        "uncertainty_rule": "point pass is provisional when paired CI reaches or crosses -0.02 candidate-minus-control",
        "max_teacher_forced_nll_relative_increase": 0.05,
        "mtp_identity_requirement": "exact_normalized_output_identity",
        "mtp_identity_scope": "deterministic greedy fixtures with MTP disabled versus enabled",
        "external_llm_judge_allowed": False,
        "execution_contract": {
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
        },
    }
    provenance = {
        "schema_version": 1,
        "source": "campaign-authored deterministic synthetic fixtures",
        "reuse_status": "synthetic_owned",
        "limitations": [
            "This compact suite is a screening gate, not a quality certification.",
            "No empirical public trajectory content is included because no locally available source had verified reusable provenance.",
            "The teacher-forced sentinel requires runtime-produced NLL bound to the recorded sequence hash.",
        ],
    }
    dev = fixtures("development")
    holdout = fixtures("holdout")
    write_json(output / "policy.json", policy)
    write_json(output / "provenance.json", provenance)
    write_jsonl(output / "development.jsonl", dev)
    write_jsonl(output / "holdout.jsonl", holdout)
    write_jsonl(output / "sample_development_responses.jsonl", sample_responses(dev))
    write_jsonl(output / "sample_holdout_responses.jsonl", sample_responses(holdout))
    names = [
        "policy.json", "provenance.json", "development.jsonl", "holdout.jsonl",
        "sample_development_responses.jsonl", "sample_holdout_responses.jsonl",
        "build_quality.py", "validate_quality.py", "score_pair.py", "run_pair.py", "RUNNER_INTERFACE.md",
    ]
    files = {name: digest((output / name).read_bytes()) for name in names}
    manifest = {
        "schema_version": 1,
        "files": files,
        "bundle_sha256": digest(canonical(files)),
        "immutability": "Any byte change creates a new suite identity and invalidates this manifest.",
    }
    write_json(output / "FROZEN_MANIFEST.json", manifest)
    return manifest


if __name__ == "__main__":
    build_quality(Path(__file__).resolve().parent)
