#!/usr/bin/env python3
"""Fail closed when a development-quality capture is not fully executable."""
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PACKET = ROOT / "DEVELOPMENT_CALIBRATION_PACKET.json"
OUTPUT = ROOT / "DEVELOPMENT_CAPTURE_PREREGISTRATION_AUDIT.json"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def missing_fields(case):
    required = ["case_id", "category", "prompt", "scorer", "content_sha256"]
    if case["category"] == "long_context_retrieval":
        required += ["synthetic_context", "tokenizer_binding"]
    if case["category"] == "teacher_forced_loss":
        required += ["teacher_forced_text", "token_sequence_sha256"]
    if case["category"] == "serving_correctness":
        required += ["deterministic_repetitions"]
    return [field for field in required if field not in case]


def main():
    packet_bytes = PACKET.read_bytes()
    packet = json.loads(packet_bytes)
    failures = [{"case_id": case["case_id"], "missing": missing_fields(case)} for case in packet["cases"]]
    failures = [failure for failure in failures if failure["missing"]]
    result = {
        "schema_version": 1,
        "classification": "derived_zero_cost_capture_preregistration_audit",
        "input_packet_sha256": digest(packet_bytes),
        "budget_usd": 0.0,
        "provider_mutation": "prohibited",
        "holdout_access": "prohibited",
        "proposed_capture": {
            "control": "intended BF16 only",
            "captures": 3,
            "representation_candidate": "not_admitted",
            "performance_workload": "not_admitted",
            "runtime_evidence_required": ["raw response bytes", "normalized output bytes", "transform decision", "runtime input-token logprobs", "token-sequence hash", "exact model/runtime/tokenizer identities"],
        },
        "ready": not failures,
        "failure_reason": "development packet is a calibration specification, not an executable fixture suite" if failures else None,
        "incomplete_cases": failures,
        "required_before_model_generation": [
            "Freeze complete development prompt/scorer/context/teacher-forced inputs and their content hashes.",
            "Bind explicit intended BF16 checkpoint, tokenizer, runtime image, request policy, and endpoint capability preflight hashes.",
            "Define capture timeout and spend cap, artifact retrieval, and cleanup owner before provider admission.",
            "Keep holdout generation and access prohibited until the three capture results satisfy the predeclared development gate."
        ],
    }
    OUTPUT.write_bytes(json.dumps(result, sort_keys=True, indent=2).encode() + b"\n")
    print(json.dumps({"ready": result["ready"], "incomplete_case_count": len(failures), "audit_sha256": digest(OUTPUT.read_bytes())}, sort_keys=True))
    if result["ready"]:
        raise SystemExit("unexpected ready state: review required")


if __name__ == "__main__":
    main()
